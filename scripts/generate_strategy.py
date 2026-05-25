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


PROMPT_TEMPLATE = """당신은 한국의 시니어 전략 컨설턴트입니다. 사용자는 전략·기획과 AI 업무를 함께 수행하는 실무자입니다.

{period_label}({period_range}) 수집된 AI·리걸테크·논문 뉴스 상위 {n}개를 아래에 제시합니다 (각 항목 앞 번호가 인덱스).

[뉴스 목록]
{news_blob}

위 흐름을 종합하여 **{period_label} 전략·기획 시사점 카드 5~7개**를 작성하세요.

[응답 형식 — JSON 배열만]
[
  {{
    "tag": "TREND 01 · [한 줄 주제]",
    "title": "[20자 이내 헤드라인]",
    "body": "[2~3문장. 흐름 + 근거 + 의미. 단정적 어조 지양.]",
    "action": "[1~2문장. 사용자가 본인 업무에 바로 시도해볼 수 있는 액션.]",
    "sources": [번호1, 번호2, ...]
  }},
  ...
]

규칙:
- 한국어
- 각 카드는 서로 다른 관점/주제 (중복 금지)
- {period_focus}
- 일반론 금지, 실무자가 행동할 수 있는 디테일 포함
- 5~7개 사이
- `sources`는 실제로 근거가 된 뉴스 인덱스만 (1~5개)
- JSON 배열 외 다른 텍스트 절대 금지
"""

PERIOD_FOCUS = {
    "daily": "오늘 발생한 구체적 사실(회사명·금액·날짜)을 중심으로",
    "weekly": "이번 주를 관통하는 큰 흐름·반복 패턴·축적된 신호를 중심으로 (단일 사건이 아닌 흐름)",
    "monthly": "이번 달의 구조적 변화·산업 지형 이동·반복되는 패턴을 중심으로 (전략적 큰 그림)",
}


def kst_today():
    return datetime.now(KST).date()


def kst_iso_year_week(d: date) -> str:
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def kst_month_str(d: date) -> str:
    return d.strftime("%Y-%m")


def filter_items_by_period(items: list, period: str, ref_date: date) -> tuple:
    """period에 해당하는 항목들 + range 문자열 반환"""
    if period == "daily":
        target = ref_date.isoformat()
        filtered = [it for it in items if it.get("date", "")[:10] == target]
        return filtered, target
    elif period == "weekly":
        iso_year, iso_week, iso_dow = ref_date.isocalendar()
        # ISO week 시작일 (월요일)
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

    result = call_llm_json(prompt, max_tokens=2500, temperature=0.4)
    if not isinstance(result, list):
        print(f"  [warn] {period}: LLM did not return a list", flush=True)
        return []

    cards = []
    for c in result:
        if not isinstance(c, dict):
            continue
        if not all(k in c for k in ("tag", "title", "body", "action")):
            continue

        # citation 변환
        cited = []
        raw_sources = c.get("sources") or []
        if isinstance(raw_sources, list):
            for idx in raw_sources[:5]:
                try:
                    i = int(idx) - 1
                    if 0 <= i < len(sorted_items):
                        ref = sorted_items[i]
                        cited.append({
                            "title": ref.get("title", "")[:140],
                            "url": ref.get("url", ""),
                            "source": ref.get("source", ""),
                            "date": ref.get("date", "")[:10],
                        })
                except (ValueError, TypeError):
                    continue

        cards.append({
            "tag": str(c["tag"]).strip(),
            "title": str(c["title"]).strip(),
            "body": str(c["body"]).strip(),
            "action": str(c["action"]).strip(),
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
        daily_cards = fallback_strategy
    history["daily"][today_iso] = daily_cards

    # === Weekly === (월요일 또는 이번 주 weekly 없을 때)
    is_monday = today.weekday() == 0
    weekly_missing = week_key not in history["weekly"]
    if backend != "none" and (is_monday or weekly_missing):
        weekly_items, _ = filter_items_by_period(items, "weekly", today)
        if len(weekly_items) >= 20:
            weekly_cards = generate_cards(weekly_items, "weekly", today, items)
            if weekly_cards:
                history["weekly"][week_key] = weekly_cards

    # === Monthly === (매월 1일 또는 이번 달 monthly 없을 때)
    is_month_start = today.day == 1
    monthly_missing = month_key not in history["monthly"]
    if backend != "none" and (is_month_start or monthly_missing):
        monthly_items, _ = filter_items_by_period(items, "monthly", today)
        if len(monthly_items) >= 30:
            monthly_cards = generate_cards(monthly_items, "monthly", today, items)
            if monthly_cards:
                history["monthly"][month_key] = monthly_cards

    # 히스토리 정리
    prune_history(history)

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

    print(f"[done] daily={len(daily_cards)} cards, "
          f"weekly_buckets={len(history['weekly'])}, "
          f"monthly_buckets={len(history['monthly'])}", flush=True)


if __name__ == "__main__":
    main()
