"""
5단계 — 논문 흐름 분석

arXiv 논문 항목들을 LLM에 보내서 다음을 추출:
- 최근 트렌드 (주제·기법)
- 주요 저자
- 주요 기관 (소속)
- 핵심 키워드 빈도
- 종합 흐름 분석 (마크다운)

저장: data/paper_trends.json (사이트가 읽음)

매일 1회 실행 (weekly와 비슷한 빈도가 더 적절할 수도 — 매일 실행은 비용 ~$0.05)
"""

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_client import call_llm, call_llm_json, detect_backend

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_PATH = os.path.join(ROOT_DIR, "data", "enriched_news.json")
OUTPUT_PATH = os.path.join(ROOT_DIR, "data", "paper_trends.json")
KST = timezone(timedelta(hours=9))

# 분석 대상 최근 일수
RECENT_DAYS = 14
# LLM에 보낼 최대 논문 수
MAX_PAPERS_FOR_LLM = 60


PROMPT_TEMPLATE = """당신은 한국 기업의 시니어 전략·기획 컨설턴트입니다. 독자는 전략·기획·AI 업무를 동시에 수행하는 한국 실무자이며, AI 연구자가 아니라 '이 흐름이 내 업무·우리 회사에 어떤 의미인가'를 알고 싶어합니다.

다음은 최근 {days}일간 발표된 AI 관련 논문 {n}편입니다.

[논문 목록]
{paper_blob}

위 논문들을 종합 분석해주세요. JSON 응답만, 다른 텍스트 없이:

{{
  "narrative": "최근 흐름을 한국 전략·기획 담당자 관점에서 풀어쓴 분석. 마크다운 형식, 800~1500자 (충분히 길게, 풍부하게). 다음 구조 권장:\\n\\n## 한 줄 요약\\n(이번 14일을 한 문장으로)\\n\\n## 1) 무엇이 부상하고 있는가\\n구체 논문/주제 2~3개를 회사명·기법명 그대로 인용하면서 풀어 설명. 연구자용 용어는 한국어로 풀어쓰기 (예: 'retrieval-augmented generation' → '검색-증강 생성·RAG').\\n\\n## 2) 한국 실무자에게 이 흐름이 무슨 의미인가\\n전략·기획 담당자가 '아 그래서 어떻게 해야 하지'를 떠올릴 수 있도록 구체 사례로 풀어쓰기. 예: '예전엔 RAG가 필수였지만 1M 토큰 컨텍스트가 보편화되며 단순화 가능 → 사내 RAG 파이프라인 재검토 시점'\\n\\n## 3) 산업 적용 흐름\\n어떤 분야(법률·금융·제조·콘텐츠 등)에 먼저 들어올 가능성이 높은가, 한국 기업이 채택 시 어떤 제약(개인정보·국외이전·on-prem 요구)이 있을 가능성이 있는가.",
  "hot_topics": [
    {{"topic": "주제명 (한국어 풀어쓴 표현 + 영문 병기)", "description": "한 줄 설명 — 한국 전략·기획자가 이해할 수 있는 평이한 표현", "paper_count": 정수}}
  ],
  "key_techniques": [
    {{"technique": "기법명 (한국어 풀어쓴 표현 + 영문 병기)", "description": "한 줄 설명 — '왜 이 기법이 중요한가'를 한국 실무자 관점에서"}}
  ],
  "actionable_insights": [
    "실무자가 본인 업무에 바로 시도해볼 수 있는 구체 시사점 (어떤 업무 → 어떤 시도 → 어떤 가설). '주 1회 반복 + 3단계 이상 절차'를 자동화 후보로 검토 같은 디테일 수준.",
    "시사점 2 — 다른 관점/주제",
    "시사점 3 — 다른 관점/주제",
    "시사점 4 — 다른 관점/주제 (5개까지 가능)"
  ]
}}

규칙:
- 모든 텍스트는 한국어 (영문 용어는 괄호 병기)
- 구체적 사실(논문 제목·회사명·기법명) 근거로
- 일반론·교과서적 설명 금지. '한국 실무자 시점'을 시종일관 유지
- hot_topics 3~6개, key_techniques 3~5개, actionable_insights 4~5개
- narrative는 800~1500자 (짧지 않게)
- JSON 외 텍스트 절대 금지
"""


def extract_authors_institutions(papers: list) -> tuple:
    """arXiv 항목의 author/institution을 단순 빈도로 카운트.
    arXiv RSS는 보통 author를 안 주고 본문에 텍스트만 줌 → summary에서 추출 시도.
    이 함수는 단순 추정. 더 정확하려면 arXiv API 호출 필요."""
    author_counter = Counter()
    institution_counter = Counter()

    # 주요 기관 키워드 (휴리스틱)
    KNOWN_INSTITUTIONS = [
        "Google", "Google DeepMind", "DeepMind", "Google Research",
        "OpenAI", "Anthropic", "Meta", "Meta AI", "FAIR",
        "Microsoft", "Microsoft Research",
        "Stanford", "Stanford University", "MIT", "Berkeley", "UC Berkeley",
        "Carnegie Mellon", "CMU", "Princeton", "Harvard",
        "Oxford", "Cambridge", "ETH Zurich", "ETH",
        "Tsinghua", "Peking University", "PKU",
        "KAIST", "Seoul National University", "SNU",
        "NVIDIA", "Salesforce", "Apple", "Amazon", "AWS",
        "Allen Institute", "AI2",
        "EleutherAI", "Hugging Face",
    ]
    for p in papers:
        text = (p.get("title", "") + " " + p.get("summary", "")).lower()
        for inst in KNOWN_INSTITUTIONS:
            if inst.lower() in text:
                institution_counter[inst] += 1

    return author_counter, institution_counter


def extract_keywords(papers: list) -> list:
    """제목에서 자주 등장하는 키워드 (3+ 단어 또는 명사구 추출)"""
    counter = Counter()
    STOPWORDS = {
        "a", "an", "the", "and", "or", "of", "for", "to", "with", "in", "on", "at",
        "by", "from", "is", "are", "was", "were", "be", "been", "being",
        "via", "using", "based", "towards", "toward",
        "novel", "new", "method", "models", "model", "approach", "study", "analysis",
        "ai", "ml", "deep", "neural", "learning",
    }
    for p in papers:
        title = p.get("title", "").lower()
        # 2-gram 추출
        words = re.findall(r"[a-z]{4,}", title)
        for w in words:
            if w not in STOPWORDS:
                counter[w] += 1
        # bigram
        for i in range(len(words) - 1):
            if words[i] not in STOPWORDS and words[i+1] not in STOPWORDS:
                bg = f"{words[i]} {words[i+1]}"
                counter[bg] += 1
    return counter.most_common(20)


def filter_papers(items: list, days: int) -> list:
    """최근 N일 발표된 논문 — arXiv + Semantic Scholar 모두 포함"""
    cutoff = (datetime.now(KST).date() - timedelta(days=days)).isoformat()
    PAPER_TYPES = {"arxiv", "semantic_scholar"}
    return [
        it for it in items
        if it.get("source_type") in PAPER_TYPES
        and not it.get("date_unknown", False)
        and it.get("date", "")[:10] >= cutoff
    ]


def main():
    print(f"[start] analyze_papers @ {datetime.now(KST).isoformat()}", flush=True)

    if not os.path.exists(INPUT_PATH):
        print("  [error] enriched_news.json not found", flush=True)
        return

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", [])
    papers = filter_papers(items, RECENT_DAYS)
    print(f"  found {len(papers)} arXiv papers in last {RECENT_DAYS} days", flush=True)

    if len(papers) < 5:
        print("  [warn] too few papers to analyze, skipping", flush=True)
        return

    backend = detect_backend()

    # 빈도 분석 (LLM 무관)
    _, institution_counter = extract_authors_institutions(papers)
    keyword_freq = extract_keywords(papers)

    top_institutions = institution_counter.most_common(15)
    top_keywords = keyword_freq[:20]

    # LLM 분석
    llm_result = {}
    if backend != "none":
        sorted_papers = sorted(papers, key=lambda x: x.get("score", 0), reverse=True)[:MAX_PAPERS_FOR_LLM]
        paper_lines = []
        for i, p in enumerate(sorted_papers, 1):
            summary = p.get("summary_ko") or p.get("summary", "")[:300]
            paper_lines.append(
                f"{i}. [{p.get('source', 'arXiv')}, {p.get('date', '')[:10]}] "
                f"{p.get('title', '')[:140]}\n   {summary[:300]}"
            )
        paper_blob = "\n".join(paper_lines)

        prompt = PROMPT_TEMPLATE.format(
            days=RECENT_DAYS,
            n=len(sorted_papers),
            paper_blob=paper_blob,
        )

        # narrative 800~1500자로 늘렸으므로 max_tokens 확대
        llm_result = call_llm_json(prompt, max_tokens=4000, temperature=0.4)
        if not isinstance(llm_result, dict):
            llm_result = {}

    payload = {
        "analyzed_at": datetime.now(KST).isoformat(),
        "llm_backend": backend,
        "days_window": RECENT_DAYS,
        "paper_count": len(papers),
        "narrative": llm_result.get("narrative", ""),
        "hot_topics": llm_result.get("hot_topics", []),
        "key_techniques": llm_result.get("key_techniques", []),
        "actionable_insights": llm_result.get("actionable_insights", []),
        "top_institutions": [
            {"name": name, "count": count} for name, count in top_institutions
        ],
        "top_keywords": [
            {"keyword": kw, "count": count} for kw, count in top_keywords
        ],
        "recent_papers": [
            {
                "title": p.get("title", ""),
                "url": p.get("url", ""),
                "source": p.get("source", ""),
                "date": p.get("date", "")[:10],
                "summary_ko": p.get("summary_ko") or p.get("summary", "")[:200],
                "score": p.get("score", 0),
            }
            for p in sorted(papers, key=lambda x: x.get("score", 0), reverse=True)[:30]
        ],
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[done] paper_trends.json saved ({len(papers)} papers, "
          f"{len(payload['hot_topics'])} hot topics, "
          f"{len(payload['top_institutions'])} institutions)", flush=True)


if __name__ == "__main__":
    main()
