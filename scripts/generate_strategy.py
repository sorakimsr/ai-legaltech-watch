"""
4단계 — 매일 전략 카드 자동 갱신 (v2.4: Daily/Weekly/Monthly)

매일 실행 시:
- Daily: 오늘 데이터로 5~7개 카드 (필수)
- Weekly: 매주 월요일에 (또는 이번 주 weekly가 없으면) 최근 7일 데이터로 생성
- Monthly: 매월 1일에 (또는 이번 달 monthly가 없으면) 최근 30일 데이터로 생성

저장:
- data/news.json["strategy"] = 오늘자 daily (현재와 호환, 프론트엔드 기존 동작)
- data/strategy_history.json = 모든 daily/weekly/monthly 누적
  {
    "daily":   {"2026-05-25": [...], "2026-05-26": [...]},
    "weekly":  {"2026-W21": [...], "2026-W22": [...]},
    "monthly": {"2026-05": [...], "2026-04": [...]}
  }
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_client import call_llm_json, detect_backend


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_PATH = os.path.join(ROOT_DIR, "data", "enriched_news.json")
OUTPUT_PATH = os.path.join(ROOT_DIR, "data", "news.json")
HISTORY_PATH = os.path.join(ROOT_DIR, "data", "strategy_history.json")
KST = timezone(timedelta(hours=9))

# 각 시계열에 사용할 항목 개수
TOP_DAILY = 30
TOP_WEEKLY = 50
TOP_MONTHLY = 80

# 보존 기간
RETAIN_DAILY_DAYS = 60
RETAIN_WEEKLY_WEEKS = 26
RETAIN_MONTHLY_MONTHS = 12


PROMPT_TEMPLATE = """당신은 한국의 시니어 전략 컨설턴트입니다. 독자는 전략·기획과 AI 업무를 동시에 수행하는 한국 실무자이며, '이 흐름이 내 업무·우리 회사에 어떤 의미인가'와 '그래서 내가 뭘 하면 되는가'를 알고 싶어합니다.

{period_label}({period_range}) 수집된 AI·리걸테크·논문 뉴스 상위 {n}개를 아래에 제시합니다 (각 항목 앞 번호가 인덱스).

[뉴스 목록]
{news_blob}

위 흐름을 종합하여 **{period_label} 전략·기획 시사점 카드 5~7개**를 작성하세요.

[응답 형식 — JSON 배열만]
[
  {{
    "tag": "TREND 01 · [한 줄 주제]",
    "title": "[20~35자 헤드라인]",
    "body": "[4~5문장, 250~450자. (1) 어떤 흐름이 관찰되는가 (구체 회사명·제품명·금액·날짜) (2) 왜 이게 한국 실무자에게 의미가 있는가 (3) 표면적 해석이 아닌 그 아래 깔린 시장 구조·역학 (4) 이 흐름이 향후 어디로 갈 가능성이 큰가. 일반론·교과서적 표현 금지. 한 줄 짜리 단정형 절대 금지.]",
    "action": "[2~3문장, 150~280자. 명사형 종결 금지(예: '~수립.', '~검토.' X). 동사형·서술형으로 '~한다', '~하자', '~해보면 좋다' 식으로 구체 동작을 적는다. (1) 첫 단계로 무엇을 한다 (2) 그 다음 무엇을 검증하거나 만든다 (3) 어떤 지표·기준으로 성공·실패를 판단한다 — 이 셋 중 최소 둘을 포함. **시점 표현 절대 금지(지금 당장 / 즉시 / 이번 주 안에 / 이번 달 내 / 빠른 시일 내 / 우선 / 곧 등 일체 사용 금지)**.]",
    "sources": [번호1, 번호2, ...]
  }},
  ...
]

규칙:
- 모든 텍스트는 한국어 (영문 용어는 괄호 병기)
- 각 카드는 서로 다른 관점/주제 (중복 금지)
- {period_focus}
- 구체 사실(회사명·금액·날짜·기법명) 근거로. 일반론·교과서적 설명 금지
- body는 4~5문장으로 풍부하게. 한 줄로 끝내지 말 것. 줄 사이에 흐름이 이어지도록.
- action은 동사형·서술형 2~3문장. "~를 수립.", "~검토." 같은 명사형 종결 금지. "~한다", "~해보자" 같이 행동을 직접 명령 또는 권유.
- **시점/기한 표현 절대 금지**: "지금 당장", "즉시", "이번 주 (안에)", "이번 달 (내)", "빠른 시일 내", "우선", "곧", "단기간 내", "1주일 내", "한 달 안에" 등 시간 한정어 금지. ACTION은 "무엇을 한다"에 집중하고 언제는 빼라.
- **굵게 강조(`**...**`)는 "의미론적으로 의사결정에 직결되는 구절"에만 적용** (사용자 정책):

  강조해야 할 것 (✅ 예시 그대로 — 인과·필요·판단 구절):
    1) "**단일 LLM 선택은 이미 낡은 질문이고, 에이전트 간 신뢰·조정 계층이 새 병목**"
    2) "**기존 API 호출 단위 비용 측정이 다단계 에이전트 환경에서는 무의미**"
    3) "**RAG 파이프라인을 한 번 구축하고 방치하는 운영 방식은 재검토가 필요한 시점**"
    4) "**성공한 목표당 비용으로 KPI를 재설계해야**"
    5) "**온프레미스(on-premise) 또는 폐쇄망 요구가 도입 속도를 제한하는 현실적 제약으로 작동**"
    6) "**한국 기업 환경에서는 개인정보보호법상 국외 데이터 이전 제한, 금융위·금감원의 AI 모델 설명 요구, 공공기관의 망분리 정책이 클라우드 기반 멀티에이전트 도입의 현실적 장벽으로 작용**"
    7) "**책임 경계가 명확히 설계된 아키텍처를 선택**"
  → 핵심 패턴: "X는 Y다", "A가 B의 병목", "C 요구가 D를 제한", "E로 재설계해야", "F가 G의 장벽" 같은
     **읽고 나서 행동·전략 의사결정에 영향 주는 통찰**.

  강조 금지 (❌ 단순 고유명사·금액·기법명·기관명):
    "OpenAI", "Anthropic", "Sequoia Capital", "수출입은행", "KB금융", "Harvey", "Mike OSS",
    "Foundation Protocol", "AAIA-RAG-LEGAL", "Redrawing the AI Map", "MAS-Orchestra",
    "40억 달러", "110억 달러", "Pre-Litigation-as-a-Service", "AWS 서밋 서울"
  → 회사명·금액·기법명·논문제목은 본문에 그대로 적되 절대 굵게 처리 X.

  분량: 시사점 카드 1개(body+action)에 위 같은 의미 구절 3~6개 강조 (촘촘하게). 한 문장 1~2개.
  ★ 동일 기준이 daily / weekly / monthly 모두 적용됨.
- 5~7개 사이
- **`sources`는 trend의 핵심 근거가 되는 실제 뉴스 인덱스만 (위 목록의 1부터 시작 번호). 카드 당 3~5개 필수**. body에 인용한 회사·사건·금액·날짜가 실제로 등장하는 인덱스만 포함. 본문과 직접 관련 없는 인덱스는 절대 넣지 말 것.
- **body 첫 문장에 sources의 인덱스 번호를 명시 권장** (예: "오늘 KB금융(16, 29번), 기업은행(22번) ..."). 이는 향후 검증 가능하도록 하는 사용자 요구사항.
- 한 카드의 sources 인덱스들은 모두 같은 주제/이슈/회사군을 다뤄야 함. 약하게라도 매칭이 어색하면 차라리 sources를 3개로 줄여라 (5개를 억지로 채우지 말 것).
- JSON 배열 외 다른 텍스트 절대 금지
"""

PERIOD_FOCUS = {
    "daily": "오늘 발생한 구체적 사실(회사명·금액·날짜)을 중심으로",
    "weekly": "이번 주를 관통하는 큰 흐름·반복 패턴·축적된 신호를 중심으로 (단일 사건이 아닌 흐름)",
    "monthly": "이번 달의 구조적 변화·산업 지형 이동·반복되는 패턴을 중심으로 (전략적 큰 그림)",
}


import re as _re

# v2.7.1: ACTION에서 자주 등장하는 시점/기한 표현
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
    r"오늘\s*안에[,\s]*",
    r"내일\s*까지[,\s]*",
]


def _strip_timing_phrases(text: str) -> str:
    """ACTION 텍스트에서 시점/기한 표현 제거.

    문장 첫머리의 '지금 당장 ~한다' → '~한다'.
    문장 중간의 '~을 이번 주 안에 검토한다' → '~을 검토한다'.
    """
    if not text:
        return text
    out = text
    for pat in _TIMING_PATTERNS:
        out = _re.sub(pat, "", out, flags=_re.IGNORECASE)
    # v3.10: \n 보존 — 공백·탭만 합침
    out = _re.sub(r"[ \t]{2,}", " ", out)
    out = _re.sub(r"[ \t]+([.,!?])", r"\1", out)
    return out.strip()


# v3.12: 시사점 카드에서 회사명·고유명사 강조 제거 (analyze_papers.py와 동기화)
_STRATEGY_UNBOLD_NAMES = [
    "OpenAI", "Anthropic", "Sequoia Capital", "Google", "DeepMind", "Meta",
    "Microsoft", "NVIDIA", "Apple", "Amazon", "AWS",
    "수출입은행", "KB금융", "신한금융", "하나금융", "우리금융",
    "Harvey", "Legora", "Ironclad", "Spellbook", "Robin AI",
    "Mike Legal", "Casetext", "Everlaw",
    "BHSN", "로앤컴퍼니", "로앤굿", "케이스노트",
    "AI 기본법", "AI Act", "AI 가이드라인",
]


def _unbold_strategy_names(text: str) -> str:
    """v3.12: LLM이 회사명·기관명·법안명 등 단순 고유명사에 적용한 **강조** 제거.
    유의미한 시사점 문구만 음영 유지 (사용자 정책).
    """
    if not text:
        return text
    out = text
    for name in _STRATEGY_UNBOLD_NAMES:
        pattern = r"\*\*([^*\n]{0,40}?" + _re.escape(name) + r"[^*\n]{0,15}?)\*\*"
        out = _re.sub(pattern, r"\1", out)
    # 6자 이하 짧은 키워드도 풀기
    out = _re.sub(r"\*\*([^*\n]{1,6})\*\*", r"\1", out)
    return out


def _ensure_action_emphasis(action_text: str) -> str:
    """v3.14: ACTION에 **강조** 마크업이 전혀 없으면 마지막 핵심 문장을 자동 강조.

    monthly 등에서 LLM이 action에 `**` 마크업을 누락하는 경우가 잦음.
    body와 동일하게 의미 구절 강조 정책 적용을 강제하기 위한 후처리.

    동작:
    - 이미 `**...**` 가 1개 이상 있으면 그대로 반환
    - 없으면 마지막 종결문 (마침표 끝 직전 문장)을 추출해 `**...**`로 감쌈
      예: "~한다. ~을 측정한다." → "~한다. **~을 측정한다.**"
    """
    if not action_text or not isinstance(action_text, str):
        return action_text
    # 이미 강조 있으면 OK
    if "**" in action_text:
        return action_text
    text = action_text.strip()
    if not text:
        return text
    # 마지막 종결 문장 분리 (마침표·물음표·느낌표 기준)
    # 한국어 종결 어미가 자주 마침표로 끝나므로, 끝에서 두 번째 마침표 위치 찾기
    # 텍스트 끝에서 가장 가까운 종결 부호 찾기
    text_no_trail = text.rstrip(".!? ")
    # 마지막 문장의 시작 위치 찾기 — 직전 종결 부호 위치 + 1
    cut = max(text_no_trail.rfind(". "), text_no_trail.rfind("! "), text_no_trail.rfind("? "))
    if cut < 0:
        # 종결 부호 없음 = 단일 문장 → 전체를 강조 (단, 30~120자 범위만)
        if 10 <= len(text_no_trail) <= 150:
            return f"**{text_no_trail}**" + text[len(text_no_trail):]
        return text  # 너무 짧거나 너무 길면 강조 안 함
    last_sentence = text_no_trail[cut + 2:].strip()
    if not last_sentence or len(last_sentence) > 150:
        return text
    # 마지막 문장만 강조
    before = text_no_trail[:cut + 2]
    trail = text[len(text_no_trail):]
    return before + "**" + last_sentence + "**" + trail


def _postprocess_card(card: dict) -> dict:
    """v3.12: 시사점 카드 body/action 후처리 — timing 제거 + 음영 정리.
    캐시된 카드에도 매 빌드마다 재적용하여 정책 변경 시 즉시 반영.
    v3.14: ACTION 강조 누락 시 마지막 문장 자동 강조.
    """
    if not isinstance(card, dict):
        return card
    out = dict(card)
    if "body" in out and isinstance(out["body"], str):
        out["body"] = _unbold_strategy_names(out["body"])
    if "action" in out and isinstance(out["action"], str):
        action = _unbold_strategy_names(_strip_timing_phrases(out["action"]))
        action = _ensure_action_emphasis(action)
        out["action"] = action
    return out


def kst_today():
    return datetime.now(KST).date()


def kst_iso_year_week(d: date) -> str:
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def kst_month_str(d: date) -> str:
    return d.strftime("%Y-%m")


def filter_items_by_period(items: list, period: str, ref_date: date) -> tuple:
    """period에 해당하는 항목들 + range 문자열 반환.
    발행일(date) 기준. date_unknown=True (발행일 불명) 항목은 제외."""
    # 발행일 불명 항목 우선 제외
    items = [it for it in items if not it.get("date_unknown", False)]

    if period == "daily":
        target = ref_date.isoformat()
        filtered = [it for it in items if it.get("date", "")[:10] == target]
        return filtered, target
    elif period == "weekly":
        iso_year, iso_week, iso_dow = ref_date.isocalendar()
        start = date.fromisocalendar(iso_year, iso_week, 1)
        end = date.fromisocalendar(iso_year, iso_week, 7)
        filtered = [it for it in items
                    if start.isoformat() <= it.get("date", "")[:10] <= end.isoformat()]
        return filtered, f"{start.isoformat()} ~ {end.isoformat()} (W{iso_week})"
    elif period == "monthly":
        month_str = ref_date.strftime("%Y-%m")
        filtered = [it for it in items if it.get("date", "")[:10].startswith(month_str)]
        return filtered, month_str
    return items, ""


def generate_cards(items: list, period: str, ref_date: date, all_items: list) -> list:
    """LLM으로 카드 생성. items가 period에 해당하는 필터된 항목."""
    if not items:
        return []

    # 점수 상위 N개
    top_n_map = {"daily": TOP_DAILY, "weekly": TOP_WEEKLY, "monthly": TOP_MONTHLY}
    top_n = top_n_map.get(period, 30)

    sorted_items = sorted(items, key=lambda x: x.get("score", 0), reverse=True)[:top_n]

    news_lines = []
    for i, it in enumerate(sorted_items, 1):
        summary = it.get("summary_ko") or it.get("summary", "")[:200]
        news_lines.append(
            f"{i}. [{it.get('source', '?')}, {it.get('date', '')[:10]}] "
            f"{it.get('title', '')[:120]}\n   요약: {summary[:200]}"
        )
    news_blob = "\n".join(news_lines)

    label_map = {"daily": "오늘", "weekly": "이번 주", "monthly": "이번 달"}
    period_label = label_map.get(period, period)

    _, period_range = filter_items_by_period(items, period, ref_date)

    prompt = PROMPT_TEMPLATE.format(
        period_label=period_label,
        period_range=period_range,
        n=len(sorted_items),
        news_blob=news_blob,
        period_focus=PERIOD_FOCUS.get(period, ""),
    )

    # v2.7 추가: weekly/monthly는 50~80 items 컨텍스트라 응답도 김 → 8000으로 더 상향
    # (5000에서 잘려 ```json까지만 와서 JSON 파싱 실패하는 케이스 방지)
    result = call_llm_json(prompt, max_tokens=8000, temperature=0.4)
    if not isinstance(result, list):
        print(f"  [warn] {period}: LLM did not return a list", flush=True)
        return []

    cards = []
    for c in result:
        if not isinstance(c, dict):
            continue
        if not all(k in c for k in ("tag", "title", "body", "action")):
            continue

        # === v3.15: citation 정합성 강화 ===
        # 1) LLM이 sources 반환 → 인덱스 그대로 사용 (정확한 매칭)
        # 2) sources 누락 → 본문·제목과 강하게 일치하는 항목만 매칭 (임계값 ↑)
        # 3) 끝까지 비어 있어도 자동 채우지 않음 — 잘못된 citation은 차라리 없는 게 나음 (사용자 정책)
        cited = []
        raw_sources = c.get("sources") or []
        if isinstance(raw_sources, list):
            for idx in raw_sources[:5]:
                try:
                    i = int(idx) - 1
                    if 0 <= i < len(sorted_items):
                        ref = sorted_items[i]
                        cited.append({
                            "num": int(idx),  # v4.9: 본문 (N번) 매칭용 1-index
                            "title": ref.get("title", "")[:140],
                            "url": ref.get("url", ""),
                            "source": ref.get("source", ""),
                            "date": ref.get("date", "")[:10],
                        })
                except (ValueError, TypeError):
                    continue

        # Citation fallback (엄격) — LLM이 sources 누락 시
        # 본문에 직접 등장한 회사/기관/제품명만 매칭. 단순 일반어(AI, 기술 등) 제외.
        if not cited:
            body_text = (str(c.get("body", "")) + " " + str(c.get("title", ""))).lower()
            # 너무 일반적인 단어는 매칭에서 제외 (false positive 방지)
            GENERIC_WORDS = {
                "ai", "ml", "llm", "tech", "news", "한국", "기업", "정부", "발표", "기술",
                "서비스", "시장", "산업", "글로벌", "신규", "관련", "통한", "위한", "지원",
                "강화", "확대", "체계", "구축", "도입", "운영", "활용", "분석", "데이터",
                "the", "and", "for", "with", "from", "this", "that", "have"
            }
            for ref in sorted_items[:30]:
                ref_text = (ref.get("title", "")).lower()
                ref_tokens = [t for t in ref_text.split() if len(t) > 3 and t not in GENERIC_WORDS]
                # 의미 있는 토큰 3개 이상 일치해야 채택 (이전 2 → 3)
                hit_count = sum(1 for t in ref_tokens[:10] if t in body_text)
                if hit_count >= 3:
                    cited.append({
                        "title": ref.get("title", "")[:140],
                        "url": ref.get("url", ""),
                        "source": ref.get("source", ""),
                        "date": ref.get("date", "")[:10],
                    })
                if len(cited) >= 5:
                    break

        # v3.15: 끝까지 비어 있어도 자동 채우지 않음
        # — citation이 0개여도 본문이 잘못된 reference로 오염되는 것보다 낫다는 사용자 정책
        # — frontend에서 citation이 비어 있으면 "근거 기사 매핑 누락" 표시

        # v2.7.1: ACTION에서 시점/기한 표현 사후 제거 (LLM이 어겼을 경우 안전망)
        action_text = str(c["action"]).strip()
        action_text = _strip_timing_phrases(action_text)

        cards.append({
            "tag": str(c["tag"]).strip(),
            "title": str(c["title"]).strip(),
            "body": str(c["body"]).strip(),
            "action": action_text,
            "citations": cited,
        })

    print(f"  {period}: {len(cards)} cards generated (avg citations: {sum(len(c['citations']) for c in cards) / max(1, len(cards)):.1f})", flush=True)
    return cards


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
    today = kst_today()
    # daily: 60일
    daily_cutoff = (today - timedelta(days=RETAIN_DAILY_DAYS)).isoformat()
    history["daily"] = {k: v for k, v in history["daily"].items() if k >= daily_cutoff}
    # weekly: 26주
    weekly_cutoff_date = today - timedelta(weeks=RETAIN_WEEKLY_WEEKS)
    weekly_cutoff = kst_iso_year_week(weekly_cutoff_date)
    history["weekly"] = {k: v for k, v in history["weekly"].items() if k >= weekly_cutoff}
    # monthly: 12개월
    monthly_cutoff_date = date(today.year - (1 if today.month <= RETAIN_MONTHLY_MONTHS else 0),
                                ((today.month - RETAIN_MONTHLY_MONTHS - 1) % 12) + 1, 1)
    monthly_cutoff = monthly_cutoff_date.strftime("%Y-%m")
    history["monthly"] = {k: v for k, v in history["monthly"].items() if k >= monthly_cutoff}


def main():
    print(f"[start] generate_strategy v2.4 @ {datetime.now(KST).isoformat()}", flush=True)

    # 입력
    input_path = INPUT_PATH
    if not os.path.exists(INPUT_PATH):
        fallback = os.path.join(ROOT_DIR, "data", "deduped_news.json")
        if os.path.exists(fallback):
            input_path = fallback
        else:
            print("  [error] no input file", flush=True)
            return

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data["items"]
    backend = detect_backend()

    # 기존 news.json 의 fallback 카드
    fallback_strategy = []
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                prev = json.load(f)
                fallback_strategy = prev.get("strategy", [])
        except Exception:
            pass

    # 히스토리 로드
    history = load_history()

    today = kst_today()
    today_iso = today.isoformat()
    week_key = kst_iso_year_week(today)
    month_key = kst_month_str(today)

    # === Daily ===
    daily_cards = []
    if backend != "none":
        daily_items, _ = filter_items_by_period(items, "daily", today)
        # 오늘 데이터가 적으면 최근 3일로 확장
        if len(daily_items) < 10:
            cutoff = (today - timedelta(days=3)).isoformat()
            daily_items = [it for it in items if it.get("date", "")[:10] >= cutoff]
        daily_cards = generate_cards(daily_items, "daily", today, items)
    if not daily_cards:
        # 폴백 카드도 citations 누락 시 점수 상위 3개를 자동 첨부 (citation 강제)
        sorted_top = sorted(items, key=lambda x: x.get("score", 0), reverse=True)[:3]
        default_cites = [{
            "title": r.get("title", "")[:140],
            "url": r.get("url", ""),
            "source": r.get("source", ""),
            "date": r.get("date", "")[:10],
        } for r in sorted_top]
        fixed = []
        for card in fallback_strategy:
            c = dict(card)
            if not c.get("citations"):
                c["citations"] = default_cites
            fixed.append(c)
        daily_cards = fixed
    history["daily"][today_iso] = daily_cards

    # v3.2: 강제 재생성 옵션 — 프롬프트 정책 변경 후 weekly/monthly도 새 음영 적용
    force_refresh = os.environ.get("STRATEGY_FORCE_REFRESH", "0") == "1"

    # === Weekly === (월요일 또는 이번 주 weekly 없을 때, 또는 force_refresh)
    is_monday = today.weekday() == 0
    weekly_missing = week_key not in history["weekly"]
    if backend != "none" and (is_monday or weekly_missing or force_refresh):
        weekly_items, _ = filter_items_by_period(items, "weekly", today)
        if len(weekly_items) >= 20:
            print(f"  weekly: regenerating ({'force' if force_refresh else 'missing' if weekly_missing else 'monday'})", flush=True)
            weekly_cards = generate_cards(weekly_items, "weekly", today, items)
            if weekly_cards:
                history["weekly"][week_key] = weekly_cards

    # === Monthly === (매월 1일 또는 이번 달 monthly 없을 때, 또는 force_refresh)
    is_month_start = today.day == 1
    monthly_missing = month_key not in history["monthly"]
    if backend != "none" and (is_month_start or monthly_missing or force_refresh):
        monthly_items, _ = filter_items_by_period(items, "monthly", today)
        if len(monthly_items) >= 30:
            print(f"  monthly: regenerating ({'force' if force_refresh else 'missing' if monthly_missing else 'month-start'})", flush=True)
            monthly_cards = generate_cards(monthly_items, "monthly", today, items)
            if monthly_cards:
                history["monthly"][month_key] = monthly_cards

    # 히스토리 정리
    prune_history(history)

    # v3.12: 캐시된 시사점 카드에도 매 빌드마다 후처리 재적용 (음영 정책 변경 시 즉시 반영)
    print("[v3.12] re-applying card post-processing to all history entries", flush=True)
    for period_name in ("daily", "weekly", "monthly"):
        for k, cards in list(history.get(period_name, {}).items()):
            if isinstance(cards, list):
                history[period_name][k] = [_postprocess_card(c) for c in cards]
    # daily_cards reference 갱신 (위 루프에서 history 덮어썼으므로)
    if today_iso in history.get("daily", {}):
        daily_cards = history["daily"][today_iso]

    # 저장
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    # news.json (오늘자 daily를 strategy 필드로 + history 메타)
    payload = {
        "last_updated": datetime.now(KST).isoformat(),
        "build_count": (data.get("build_count", 0) or 0) + 1,
        "llm_backend": backend,
        "sources": data.get("sources", []),
        "items": items,
        "strategy": daily_cards,  # 호환성: 오늘자 daily
        "strategy_periods": {
            "today_daily": today_iso,
            "current_week": week_key,
            "current_month": month_key,
            "available_weekly": sorted(history["weekly"].keys(), reverse=True),
            "available_monthly": sorted(history["monthly"].keys(), reverse=True),
        },
        "stats": {
            "total_items": len(items),
            "enriched_items": sum(1 for it in items if it.get("llm_enriched")),
            "with_related": sum(1 for it in items if it.get("related_count", 0) > 0),
        },
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # v6.0 (P2-1): data/version.json — 작은 cache-buster 파일.
    #   브라우저는 이 파일만 no-cache로 가져오고, 큰 news.json 등은 ?v=<build>로 캐시 활용.
    version_path = os.path.join(os.path.dirname(OUTPUT_PATH), "version.json")
    try:
        with open(version_path, "w", encoding="utf-8") as vf:
            json.dump({
                "build": datetime.now(KST).strftime("%Y%m%d%H%M%S"),
                "last_updated": datetime.now(KST).isoformat(),
            }, vf, ensure_ascii=False)
    except Exception as exc:
        print(f"  [version.json] write failed: {exc}", flush=True)

    print(f"[done] daily={len(daily_cards)} cards, "
          f"weekly_buckets={len(history['weekly'])}, "
          f"monthly_buckets={len(history['monthly'])}", flush=True)


if __name__ == "__main__":
    main()
