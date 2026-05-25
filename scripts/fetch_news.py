"""
1단계 — 뉴스 수집

50+개 소스에서 RSS·arXiv 항목을 수집해서 data/raw_news.json 으로 저장합니다.
"""

import json
import os
import socket
import sys
import time
from datetime import datetime, timezone, timedelta

import feedparser
from dateutil import parser as dateparser

# 각 RSS 호출에 8초 socket timeout
socket.setdefaulttimeout(8)

# 같은 폴더 모듈 import 가능하게
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (
    clean_text, truncate, parse_date_safe, categorize, score_item, normalize_url
)
from sources import get_active_sources


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(ROOT_DIR, "data", "raw_news.json")
KST = timezone(timedelta(hours=9))

MAX_AGE_DAYS = 30
MAX_PER_SOURCE = 20


def fetch_source(source_def):
    name, url, source_type, default_cats, lang = source_def
    items = []
    try:
        print(f"  [fetch] {name}", flush=True)
        feed = feedparser.parse(url, request_headers={
            "User-Agent": "AI-Legaltech-Watch/2.0 (+https://github.com)"
        })
        if feed.bozo and feed.bozo_exception and not feed.entries:
            print(f"    -> error: {feed.bozo_exception}", flush=True)
            return [], "error"

        entries = feed.entries[:MAX_PER_SOURCE]
        for e in entries:
            title = clean_text(getattr(e, "title", "") or "")
            link = normalize_url(getattr(e, "link", "") or "")

            raw_summary = (
                getattr(e, "summary", None)
                or getattr(e, "description", None)
                or ""
            )
            summary = truncate(clean_text(raw_summary), 400)

            date_str = (
                getattr(e, "published", None)
                or getattr(e, "updated", None)
                or getattr(e, "pubDate", None)
            )
            dt = parse_date_safe(date_str)
            if not dt and hasattr(e, "published_parsed") and e.published_parsed:
                dt = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)

            if not title or not link:
                continue

            categories = categorize(title, summary, default_cats)
            score = score_item(title, summary, dt, categories)

            items.append({
                "title": title,
                "url": link,
                "source": name,
                "source_type": source_type,
                "lang": lang,
                "date": (dt or datetime.now(timezone.utc)).isoformat(),
                "summary": summary,
                "categories": categories,
                "score": score,
            })

        return items, ("active" if items else "idle")
    except Exception as exc:
        print(f"    -> exception: {exc}", flush=True)
        return [], "error"


def main():
    print(f"[start] fetch_news @ {datetime.now(KST).isoformat()}", flush=True)
    sources = get_active_sources()
    print(f"  {len(sources)} sources configured", flush=True)

    all_items = []
    source_status = []

    for src in sources:
        name, url, *_ = src
        items, status = fetch_source(src)
        source_status.append({
            "name": name,
            "url": url,
            "status": status,
            "count": len(items),
        })
        all_items.extend(items)
        time.sleep(0.3)

    # 중복 제거 (URL 기준)
    seen = set()
    deduped = []
    for it in all_items:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        deduped.append(it)

    # 오래된 항목 제거
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    filtered = []
    for it in deduped:
        try:
            dt = dateparser.parse(it["date"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                filtered.append(it)
        except Exception:
            filtered.append(it)

    filtered.sort(key=lambda x: (x.get("score", 0), x.get("date", "")), reverse=True)

    payload = {
        "fetched_at": datetime.now(KST).isoformat(),
        "sources": source_status,
        "items": filtered,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    active_cnt = sum(1 for s in source_status if s["status"] == "active")
    print(f"[done] {len(filtered)} items, {active_cnt}/{len(sources)} sources active", flush=True)


if __name__ == "__main__":
    main()
