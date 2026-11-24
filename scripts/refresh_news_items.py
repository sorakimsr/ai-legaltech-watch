"""v8.1 (2026-11-24): 카드 생성 → enrich 순서 전환에 따른 news.json items 갱신.

generate_strategy.py가 enrich 이전 시점의 items로 data/news.json을 쓰므로,
enrich 이후 이 스크립트가 enriched_news.json의 items/sources/stats만 news.json에 반영한다.
strategy 관련 필드(strategy, strategy_summary, strategy_periods 등)는 그대로 유지. LLM 호출 없음.
"""
import json
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS_PATH = os.path.join(ROOT_DIR, "data", "news.json")
ENRICHED_PATH = os.path.join(ROOT_DIR, "data", "enriched_news.json")


def main():
    if not (os.path.exists(NEWS_PATH) and os.path.exists(ENRICHED_PATH)):
        print("  [refresh-items] news.json 또는 enriched_news.json 없음 — skip", flush=True)
        return 0
    with open(NEWS_PATH, "r", encoding="utf-8") as f:
        news = json.load(f)
    with open(ENRICHED_PATH, "r", encoding="utf-8") as f:
        enriched = json.load(f)

    items = enriched.get("items") or []
    if not items:
        print("  [refresh-items] enriched items 0건 — skip", flush=True)
        return 0

    news["items"] = items
    if enriched.get("sources"):
        news["sources"] = enriched["sources"]
    stats = news.get("stats") or {}
    stats["total_items"] = len(items)
    stats["enriched_items"] = sum(1 for it in items if it.get("llm_enriched"))
    stats["with_related"] = sum(1 for it in items if it.get("related_count", 0) > 0)
    news["stats"] = stats

    with open(NEWS_PATH, "w", encoding="utf-8") as f:
        json.dump(news, f, ensure_ascii=False, indent=2)
    print(f"  [refresh-items] news.json items 갱신: {len(items)}건 "
          f"(enriched {stats['enriched_items']})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
