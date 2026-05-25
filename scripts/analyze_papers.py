"""
5단계 — 논문 흐름 분석 (v2.7.1: Daily/Weekly/Monthly 시계열)

arXiv + OpenAlex 논문 항목들을 LLM에 보내서 다음을 추출:
- 최근 흐름 narrative (한국 실무자 관점)
- 부상 주제 (hot_topics)
- 핵심 기법 (key_techniques)
- 실무 시사점 (actionable_insights)
- 주요 기관·키워드 빈도

저장:
- data/paper_trends.json = 가장 최신 weekly 분석 (사이트 기본 뷰)
- data/paper_trends_history.json = 모든 daily/weekly/monthly 누적
"""

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_client import call_llm_json, detect_backend

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_PATH = os.path.join(ROOT_DIR, "data", "enriched_news.json")
OUTPUT_PATH = os.path.join(ROOT_DIR, "data", "paper_trends.json")
HISTORY_PATH = os.path.join(ROOT_DIR, "data", "paper_trends_history.json")
KST = timezone(timedelta(hours=9))

# v2.7.1: Daily/Weekly/Monthly 시계열 — 각 기간별 별도 윈도우·논문 상한
PERIOD_CONFIG = {
    "daily":   {"days": 1,  "max_papers": 40,  "label": "오늘",     "min_papers": 3},
    "weekly":  {"days": 7,  "max_papers": 80,  "label": "최근 7일",  "min_papers": 10},
    "monthly": {"days": 30, "max_papers": 120, "label": "최근 30일", "min_papers": 20},
}

# 보존 기간 (시사점과 동일 정책)
RETAIN_DAILY_DAYS = 60
RETAIN_WEEKLY_WEEKS = 26
RETAIN_MONTHLY_MONTHS = 12


PROMPT_TEMPLATE = """당신은 한국 기업의 시니어 전략·기획 컨설턴트입니다. 독자는 전략·기획·AI 업무를 동시에 수행하는 한국 실무자이며, AI 연구자가 아니라 '이 흐름이 내 업무·우리 회사에 어떤 의미인가'를 알고 싶어합니다.

다음은 {period_label}({days}일 윈도우) 발표된 AI 관련 논문 {n}편입니다.

[논문 목록]
{paper_blob}

위 논문들을 종합 분석해주세요. JSON 응답만, 다른 텍스트 없이:

{{
  "narrative": "최근 흐름을 한국 전략·기획 담당자 관점에서 풀어쓴 분석. 마크다운 형식, 800~1500자 (충분히 길게, 풍부하게). 다음 구조 권장:\\n\\n## 한 줄 요약\\n(이번 {period_label}을(를) 한 문장으로)\\n\\n## 1) 무엇이 부상하고 있는가\\n구체 논문/주제 2~3개를 회사명·기법명 그대로 인용하면서 풀어 설명. 연구자용 용어는 한국어로 풀어쓰기 (예: 'retrieval-augmented generation' → '검색-증강 생성·RAG').\\n\\n## 2) 한국 실무자에게 이 흐름이 무슨 의미인가\\n전략·기획 담당자가 '아 그래서 어떻게 해야 하지'를 떠올릴 수 있도록 구체 사례로 풀어쓰기.\\n\\n## 3) 산업 적용 흐름\\n어떤 분야(법률·금융·제조·콘텐츠 등)에 먼저 들어올 가능성이 높은가, 한국 기업이 채택 시 어떤 제약(개인정보·국외이전·on-prem 요구)이 있을 가능성이 있는가.",
  "hot_topics": [
    {{"topic": "주제명 (한국어 풀어쓴 표현 + 영문 병기)", "description": "한 줄 설명 — 한국 전략·기획자가 이해할 수 있는 평이한 표현.", "paper_count": 정수, "paper_indices": [실제 해당 논문의 위 목록 인덱스 번호들]}}
  ],
  "key_techniques": [
    {{"technique": "기법명 (한국어 풀어쓴 표현 + 영문 병기)", "description": "한 줄 설명 — '왜 이 기법이 중요한가'를 한국 실무자 관점에서.", "paper_count": 정수, "paper_indices": [실제 해당 논문의 위 목록 인덱스 번호들]}}
  ],
  "actionable_insights": [
    "실무자가 본인 업무에 바로 시도해볼 수 있는 구체 시사점. 시점 표현(지금 당장 / 즉시 / 이번 주 / 이번 달 등) 금지.",
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
- **narrative 문단 사이는 반드시 `\\n\\n` (빈 줄)으로 명확히 구분**. 각 `## 헤더` 앞에 빈 줄을 두고, 본문 내 문단도 의미 단위로 빈 줄 분리. inline으로 이어 쓰지 말 것.
- **빈 헤더(`#` 만 있고 내용 없는 줄) 절대 출력 금지**. 모든 헤더 라인은 `## 한 줄 요약`처럼 텍스트가 반드시 따라와야 함.
- **굵게 강조(`**...**`)는 "의미론적으로 의사결정에 직결되는 구절"에만 적용**.

  강조해야 할 것 (✅ 사용자 정책 예시 그대로):
    1) "**단일 LLM 선택은 이미 낡은 질문이고, 에이전트 간 신뢰·조정 계층이 새 병목**"
    2) "**기존 API 호출 단위 비용 측정이 다단계 에이전트 오케스트레이션 환경에서는 무의미**"
    3) "**'성공한 목표당 에너지'라는 새 단위**"
    4) "**RAG 파이프라인을 한 번 구축하고 방치하는 운영 방식은 재검토가 필요한 시점**"
    5) "**성공한 목표당 비용으로 KPI를 재설계해야**"
    6) "**온프레미스(on-premise) 또는 폐쇄망 요구가 도입 속도를 제한하는 현실적 제약으로 작동**"
    7) "**국내 금융·공공 분야의 내부통제 자동화 수요와 직결**"
    8) "**한국 기업 환경에서는 개인정보보호법상 국외 데이터 이전 제한, 금융위·금감원의 AI 모델 설명 요구, 공공기관의 망분리 정책이 클라우드 기반 멀티에이전트 도입의 현실적 장벽으로 작용**"
    9) "**책임 경계가 명확히 설계된 아키텍처를 선택**"
  → 핵심: "X는 Y다", "A가 B의 병목", "C 요구가 D를 제한", "E로 재설계해야", "F가 G의 장벽" 같은
     인과·필요·판단 구절 — **읽고 나서 행동·전략 의사결정에 영향 주는 통찰**만 강조.

  강조 금지 (❌ 단순 고유명사·논문제목·기법명·금액·기관명):
    "OpenAI", "Anthropic", "Sequoia Capital", "수출입은행", "KB금융",
    "Foundation Protocol 논문", "AAIA-RAG-LEGAL", "Redrawing the AI Map",
    "MAS-Orchestra", "EVE-Agent", "Ontological Knowledge Blocks", "CHRONOS",
    "Query-Adaptive Semantic Chunking", "40억 달러", "110억 달러"
  → 회사명·논문제목·기법명·금액은 본문에 그대로 적되 절대 굵게 처리 X.

  분량: narrative 800~1500자 안에 위 같은 의미 구절 5~10개 강조 (촘촘하게).
- **시점·기한 표현 절대 금지** (지금 당장 / 즉시 / 이번 주 안에 / 이번 달 내 등)
- `paper_indices`는 위 [논문 목록]의 실제 번호 (1부터 시작). 각 항목 당 2~6개 정도.
- JSON 외 텍스트 절대 금지
"""


# v2.7.1: ACTION/insights에서 자주 등장하는 시점/기한 표현 (사후 제거용)
_TIMING_PATTERNS = [
    r"지금\s*당장[,\s]*",
    r"즉시[,\s]*",
    r"우선[적]*으로[,\s]*",
    r"이번\s*주\s*(안에|내에)?[,\s]*",
    r"이번\s*달\s*(안에|내에|내)?[,\s]*",
    r"이번\s*분기\s*(안에|내에|내)?[,\s]*",
    r"빠른\s*시일\s*내(에)?[,\s]*",
    r"단기간\s*내(에)?[,\s]*",
    r"한\s*달\s*(안에|내에)[,\s]*",
    r"\d+\s*(일|주|개월)\s*(안에|내에|내)[,\s]*",
    r"가까운\s*시일\s*내(에)?[,\s]*",
    r"곧[,\s]*",
]


def _strip_timing(text: str) -> str:
    if not text:
        return text
    out = text
    for pat in _TIMING_PATTERNS:
        out = re.sub(pat, "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([.,!?])", r"\1", out)
    return out.strip()


def extract_authors_institutions(papers: list) -> tuple:
    """주요 기관 빈도 카운트 (휴리스틱)"""
    author_counter = Counter()
    institution_counter = Counter()

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
    """제목에서 자주 등장하는 키워드 빈도"""
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
        words = re.findall(r"[a-z]{4,}", title)
        for w in words:
            if w not in STOPWORDS:
                counter[w] += 1
        for i in range(len(words) - 1):
            if words[i] not in STOPWORDS and words[i+1] not in STOPWORDS:
                bg = f"{words[i]} {words[i+1]}"
                counter[bg] += 1
    return counter.most_common(20)


def filter_papers(items: list, days: int) -> list:
    """최근 N일 발표된 논문 — arXiv + OpenAlex 통합. date_unknown 제외."""
    cutoff = (datetime.now(KST).date() - timedelta(days=days)).isoformat()
    PAPER_TYPES = {"arxiv", "openalex"}
    return [
        it for it in items
        if it.get("source_type") in PAPER_TYPES
        and not it.get("date_unknown", False)
        and it.get("date", "")[:10] >= cutoff
    ]


def kst_today_iso() -> str:
    return datetime.now(KST).date().isoformat()


def kst_iso_year_week(d: date) -> str:
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def kst_month_str(d: date) -> str:
    return d.strftime("%Y-%m")


def load_history() -> dict:
    if not os.path.exists(HISTORY_PATH):
        return {"daily": {}, "weekly": {}, "monthly": {}}
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            h = json.load(f)
        for k in ("daily", "weekly", "monthly"):
            h.setdefault(k, {})
        return h
    except Exception:
        return {"daily": {}, "weekly": {}, "monthly": {}}


def prune_history(history: dict):
    """오래된 항목 제거"""
    today = datetime.now(KST).date()
    daily_cutoff = (today - timedelta(days=RETAIN_DAILY_DAYS)).isoformat()
    history["daily"] = {k: v for k, v in history["daily"].items() if k >= daily_cutoff}
    weekly_cutoff_date = today - timedelta(weeks=RETAIN_WEEKLY_WEEKS)
    weekly_cutoff = kst_iso_year_week(weekly_cutoff_date)
    history["weekly"] = {k: v for k, v in history["weekly"].items() if k >= weekly_cutoff}
    monthly_cutoff_date = date(
        today.year - (1 if today.month <= RETAIN_MONTHLY_MONTHS else 0),
        ((today.month - RETAIN_MONTHLY_MONTHS - 1) % 12) + 1, 1,
    )
    monthly_cutoff = monthly_cutoff_date.strftime("%Y-%m")
    history["monthly"] = {k: v for k, v in history["monthly"].items() if k >= monthly_cutoff}


def attach_papers(items_list, ref_papers):
    """LLM이 준 paper_indices → 실제 논문 정보로 매핑"""
    out = []
    for it in (items_list or []):
        if not isinstance(it, dict):
            continue
        cited = []
        for idx in (it.get("paper_indices") or [])[:8]:
            try:
                i = int(idx) - 1
                if 0 <= i < len(ref_papers):
                    p = ref_papers[i]
                    cited.append({
                        "title": p.get("title", "")[:160],
                        "url": p.get("url", ""),
                        "source": p.get("source", "arXiv"),
                        "date": p.get("date", "")[:10],
                    })
            except (ValueError, TypeError):
                continue
        new_item = dict(it)
        # description에 시점 표현이 남았으면 제거
        if isinstance(new_item.get("description"), str):
            new_item["description"] = _strip_timing(new_item["description"])
        new_item["papers"] = cited
        if "paper_count" not in new_item or not isinstance(new_item.get("paper_count"), int):
            new_item["paper_count"] = len(cited)
        out.append(new_item)
    return out


def analyze_for_period(items: list, period: str, backend: str) -> dict:
    """단일 기간(daily/weekly/monthly) 논문 흐름 분석 수행.

    Returns: payload dict (저장하지는 않음) 또는 papers가 부족하면 None.
    """
    cfg = PERIOD_CONFIG[period]
    papers = filter_papers(items, cfg["days"])
    if len(papers) < cfg["min_papers"]:
        print(f"  [{period}] too few papers ({len(papers)} < {cfg['min_papers']}), skip", flush=True)
        return None

    _, institution_counter = extract_authors_institutions(papers)
    keyword_freq = extract_keywords(papers)
    top_institutions = institution_counter.most_common(15)
    top_keywords = keyword_freq[:20]

    llm_result = {}
    sorted_for_ref = sorted(papers, key=lambda x: x.get("score", 0), reverse=True)[:cfg["max_papers"]]

    if backend != "none":
        paper_lines = []
        for i, p in enumerate(sorted_for_ref, 1):
            summary = p.get("summary_ko") or p.get("summary", "")[:300]
            paper_lines.append(
                f"{i}. [{p.get('source', 'arXiv')}, {p.get('date', '')[:10]}] "
                f"{p.get('title', '')[:140]}\n   {summary[:300]}"
            )
        paper_blob = "\n".join(paper_lines)

        prompt = PROMPT_TEMPLATE.format(
            period_label=cfg["label"],
            days=cfg["days"],
            n=len(sorted_for_ref),
            paper_blob=paper_blob,
        )
        # v2.7.1: max_tokens 4000 → 8000 (응답 잘림으로 빈 결과 나오던 문제 해결)
        llm_result = call_llm_json(prompt, max_tokens=8000, temperature=0.4)
        if not isinstance(llm_result, dict):
            print(f"  [{period}] LLM did not return JSON dict", flush=True)
            llm_result = {}

    # narrative / insights에서 시점 표현 제거
    narrative = _strip_timing(llm_result.get("narrative", "") or "")
    actionable = [_strip_timing(s) for s in (llm_result.get("actionable_insights") or []) if isinstance(s, str)]

    hot_topics_enriched = attach_papers(llm_result.get("hot_topics"), sorted_for_ref)
    key_techniques_enriched = attach_papers(llm_result.get("key_techniques"), sorted_for_ref)

    payload = {
        "analyzed_at": datetime.now(KST).isoformat(),
        "llm_backend": backend,
        "period": period,
        "period_label": cfg["label"],
        "days_window": cfg["days"],
        "paper_count": len(papers),
        "narrative": narrative,
        "hot_topics": hot_topics_enriched,
        "key_techniques": key_techniques_enriched,
        "actionable_insights": actionable,
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
    return payload


def main():
    print(f"[start] analyze_papers v2.7.1 @ {datetime.now(KST).isoformat()}", flush=True)

    if not os.path.exists(INPUT_PATH):
        fallback = os.path.join(ROOT_DIR, "data", "deduped_news.json")
        if os.path.exists(fallback):
            input_path = fallback
        else:
            print("  [error] no input", flush=True)
            return
    else:
        input_path = INPUT_PATH

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", [])
    backend = detect_backend()

    today = datetime.now(KST).date()
    today_iso = today.isoformat()
    week_key = kst_iso_year_week(today)
    month_key = kst_month_str(today)

    history = load_history()

    # === Daily ===
    daily_payload = analyze_for_period(items, "daily", backend)
    if daily_payload:
        history["daily"][today_iso] = daily_payload

    # === Weekly ===
    weekly_payload = analyze_for_period(items, "weekly", backend)
    if weekly_payload:
        # 이번 주 weekly는 매일 덮어쓴다 (가장 최신 분석을 유지)
        history["weekly"][week_key] = weekly_payload

    # === Monthly === (월초 또는 이번 달 monthly 없으면)
    monthly_payload = None
    is_month_start = today.day <= 3
    monthly_missing = month_key not in history["monthly"]
    if is_month_start or monthly_missing:
        monthly_payload = analyze_for_period(items, "monthly", backend)
        if monthly_payload:
            history["monthly"][month_key] = monthly_payload
    else:
        # 이번 달 monthly가 이미 있으면 새로 생성하지 않고 기존 사용 (LLM 비용 절감)
        monthly_payload = history["monthly"].get(month_key)

    # 히스토리 정리
    prune_history(history)

    # 저장 — history
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    # 저장 — paper_trends.json (사이트 기본 뷰: weekly가 있으면 weekly, 없으면 monthly, 없으면 daily)
    primary = weekly_payload or monthly_payload or daily_payload
    if primary is None:
        # 모든 period가 데이터 부족 → 최소 페이로드만 저장
        primary = {
            "analyzed_at": datetime.now(KST).isoformat(),
            "llm_backend": backend,
            "period": "weekly",
            "period_label": PERIOD_CONFIG["weekly"]["label"],
            "days_window": 7,
            "paper_count": 0,
            "narrative": "",
            "hot_topics": [],
            "key_techniques": [],
            "actionable_insights": [],
            "top_institutions": [],
            "top_keywords": [],
            "recent_papers": [],
        }

    # 사이트가 시계열 메뉴를 그리기 위해 메타 추가
    primary["available_periods"] = {
        "daily": sorted(history["daily"].keys(), reverse=True),
        "weekly": sorted(history["weekly"].keys(), reverse=True),
        "monthly": sorted(history["monthly"].keys(), reverse=True),
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(primary, f, ensure_ascii=False, indent=2)

    print(f"[done] daily={'OK' if daily_payload else 'skip'}, "
          f"weekly={'OK' if weekly_payload else 'skip'}, "
          f"monthly={'OK' if monthly_payload else 'skip'} | "
          f"history: daily={len(history['daily'])}, weekly={len(history['weekly'])}, monthly={len(history['monthly'])}",
          flush=True)


if __name__ == "__main__":
    main()
