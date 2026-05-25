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


PROMPT_TEMPLATE = """다음은 최근 {days}일간 발표된 AI 관련 arXiv 논문 {n}편입니다.

[논문 목록]
{paper_blob}

위 논문들을 종합 분석해주세요. JSON 응답만, 다른 텍스트 없이:

{{
  "narrative": "최근 흐름을 종합한 분석 (마크다운 형식, 400~700자). ## 헤딩과 - 불릿 사용 가능. 다음을 포함: (1) 어떤 연구 주제가 부상하고 있는가 (2) 어떤 기법이 인기인가 (3) 산업/응용 vs 기초 연구 비중 (4) 한국 전략·기획·AI 업무 담당자가 주목할 만한 점",
  "hot_topics": [
    {{"topic": "주제명", "description": "한 줄 설명", "paper_count": 정수}}
  ],
  "key_techniques": [
    {{"technique": "기법명", "description": "한 줄 설명"}}
  ],
  "actionable_insights": [
    "실무자가 본인 업무에 적용할 수 있는 시사점 1",
    "시사점 2",
    "시사점 3"
  ]
}}

규칙:
- 한국어
- 구체적 사실 (논문 제목·키워드) 근거로
- 일반론 금지
- hot_topics는 3~6개, key_techniques는 3~5개
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
    """최근 N일 발표된 arXiv 논문"""
    cutoff = (datetime.now(KST).date() - timedelta(days=days)).isoformat()
    return [
        it for it in items
        if it.get("source_type") == "arxiv"
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

        llm_result = call_llm_json(prompt, max_tokens=2500, temperature=0.4)
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
