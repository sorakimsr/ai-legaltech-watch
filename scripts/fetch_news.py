"""
1단계 — 뉴스 수집 (v2.2: 누적·중복 방지 + 소스 이력 추적)

처리 흐름:
1. 기존 data/news.json 로드 (이전 빌드 결과)
2. 모든 소스에서 신규 fetch
3. URL 기준으로 기존 항목과 합치고 중복 제거 (기존 항목의 enriched 필드 유지)
4. 30일 지난 항목 제거
5. 결과를 data/raw_news.json 저장
6. data/source_history.json 갱신 (소스별 일일 카운트)

핵심: 어제 본 항목은 다시 LLM에 안 보내짐 → 비용·시간 절감
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (
    clean_text, truncate, parse_date_safe, categorize, score_item, normalize_url,
    is_relevant
)
from sources import get_active_sources
from naver_fetcher import fetch_all_naver, has_credentials as has_naver
from semantic_scholar_fetcher import fetch_papers as fetch_semantic_scholar


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(ROOT_DIR, "data", "raw_news.json")
PREV_NEWS_PATH = os.path.join(ROOT_DIR, "data", "news.json")
SOURCE_HISTORY_PATH = os.path.join(ROOT_DIR, "data", "source_history.json")
KST = timezone(timedelta(hours=9))

MAX_AGE_DAYS = 30
MAX_PER_SOURCE = 20
SOURCE_HISTORY_RETAIN_DAYS = 30


# 보존할 필드 — 기존 항목과 새 항목 merge 시 이전 enriched 값을 잃지 않게
PRESERVE_FIELDS = [
    "summary_ko", "insight_ko", "llm_enriched",
    "entities", "relations",  # Phase 2에서 추가될 필드
    "related", "related_count",  # dedupe 단계 결과
]


def fetch_source(source_def):
    name, url, source_type, default_cats, lang = source_def
    items = []
    try:
        print(f"  [fetch] {name}", flush=True)
        # v2.7: arXiv API는 응답이 무거워서 전역 8초 timeout으로는 잘림 →
        # urllib로 별도 호출 (25s timeout) 후 raw text를 feedparser에 전달
        if source_type == "arxiv" and "api/query" in url:
            try:
                from urllib.request import Request, urlopen
                req = Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; AI-Legaltech-Watch/2.7)"
                })
                with urlopen(req, timeout=25) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                feed = feedparser.parse(body)
            except Exception as exc:
                print(f"    -> arxiv api fetch error: {exc}", flush=True)
                return [], "error"
        else:
            feed = feedparser.parse(url, request_headers={
                "User-Agent": "Mozilla/5.0 (compatible; AI-Legaltech-Watch/2.7)"
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

            # v2.7: arxiv는 updated(최신 revision) 우선 사용 — v2 revision 같은 실제 컨텐츠 수정일 잡기 위해
            if source_type == "arxiv":
                date_str = (
                    getattr(e, "updated", None)
                    or getattr(e, "published", None)
                    or getattr(e, "pubDate", None)
                )
                dt = parse_date_safe(date_str)
                if not dt and hasattr(e, "updated_parsed") and e.updated_parsed:
                    dt = datetime(*e.updated_parsed[:6], tzinfo=timezone.utc)
                if not dt and hasattr(e, "published_parsed") and e.published_parsed:
                    dt = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
            else:
                date_str = (
                    getattr(e, "published", None)
                    or getattr(e, "updated", None)
                    or getattr(e, "pubDate", None)
                )
                dt = parse_date_safe(date_str)
                if not dt and hasattr(e, "published_parsed") and e.published_parsed:
                    dt = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
                if not dt and hasattr(e, "updated_parsed") and e.updated_parsed:
                    dt = datetime(*e.updated_parsed[:6], tzinfo=timezone.utc)

            if not title or not link:
                continue

            # 관련성 필터 — Naver/Google News만 적용 (RSS는 패스)
            if not is_relevant(title, summary, source_type):
                continue

            categories = categorize(title, summary, default_cats, source_type)
            score = score_item(title, summary, dt, categories)

            # 발행일 처리 — 못 파싱하면 None (오늘로 fallback 안 함 — 시사점 분석 오염 방지)
            date_iso = dt.isoformat() if dt else None
            date_unknown = dt is None

            items.append({
                "title": title,
                "url": link,
                "source": name,
                "source_type": source_type,
                "lang": lang,
                "date": date_iso or datetime.now(timezone.utc).isoformat(),  # UI 표시용 (없으면 수집일)
                "date_unknown": date_unknown,  # 시사점 필터에서 제외용
                "first_seen": datetime.now(KST).isoformat(),
                "summary": summary,
                "categories": categories,
                "score": score,
            })

        return items, ("active" if items else "idle")
    except Exception as exc:
        print(f"    -> exception: {exc}", flush=True)
        return [], "error"


def load_previous_items():
    """이전 빌드 결과 로드. URL → item 매핑."""
    if not os.path.exists(PREV_NEWS_PATH):
        return {}
    try:
        with open(PREV_NEWS_PATH, "r", encoding="utf-8") as f:
            prev = json.load(f)
        return {it["url"]: it for it in prev.get("items", []) if "url" in it}
    except Exception as exc:
        print(f"  [warn] failed to load previous news.json: {exc}", flush=True)
        return {}


def merge_items(prev_map: dict, new_items: list) -> tuple:
    """
    이전 항목 + 새 항목 merge.

    Returns:
        merged_items: 합쳐진 리스트
        new_count: 진짜 새로 추가된 항목 수
    """
    new_urls = set()
    merged = []

    # 새 항목 먼저: 신선한 데이터 우선
    for new_it in new_items:
        url = new_it["url"]
        if url in new_urls:
            continue
        new_urls.add(url)

        if url in prev_map:
            # 기존 항목 — enriched 필드 보존, 새 메타데이터로 갱신
            prev = prev_map[url]
            merged_it = dict(new_it)  # 새 fetch 결과 베이스
            # 보존 필드 복원
            for field in PRESERVE_FIELDS:
                if field in prev:
                    merged_it[field] = prev[field]
            # 최초 수집 시점은 이전 것 유지
            if "first_seen" in prev:
                merged_it["first_seen"] = prev["first_seen"]
            merged.append(merged_it)
        else:
            # 진짜 새 항목
            merged.append(new_it)

    # 이전에만 있던 항목 (소스에서 더 이상 노출 안 되지만 30일 이내면 유지)
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    for url, prev_it in prev_map.items():
        if url in new_urls:
            continue
        try:
            dt = dateparser.parse(prev_it.get("date", ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                merged.append(prev_it)
        except Exception:
            pass

    # 30일 컷오프 한 번 더
    final = []
    for it in merged:
        try:
            dt = dateparser.parse(it.get("date", ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                final.append(it)
        except Exception:
            final.append(it)  # 날짜 못 읽으면 일단 유지

    # 진짜 신규 (이전에 없던) 항목 수
    new_count = len([it for it in new_items if it["url"] not in prev_map])

    return final, new_count


def update_source_history(source_status: list, new_items_by_source: dict):
    """소스별 일일 카운트 누적 (data/source_history.json)"""
    today = datetime.now(KST).strftime("%Y-%m-%d")
    history = {}
    if os.path.exists(SOURCE_HISTORY_PATH):
        try:
            with open(SOURCE_HISTORY_PATH, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = {}

    cutoff = (datetime.now(KST) - timedelta(days=SOURCE_HISTORY_RETAIN_DAYS)).strftime("%Y-%m-%d")

    for src in source_status:
        name = src["name"]
        if name not in history:
            history[name] = {}
        # 오래된 날짜 제거
        history[name] = {d: v for d, v in history[name].items() if d >= cutoff}
        # 오늘 데이터
        history[name][today] = {
            "fetched": src.get("count", 0),
            "new": new_items_by_source.get(name, 0),
            "status": src.get("status", "unknown"),
        }

    os.makedirs(os.path.dirname(SOURCE_HISTORY_PATH), exist_ok=True)
    with open(SOURCE_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def main():
    print(f"[start] fetch_news v2.2 @ {datetime.now(KST).isoformat()}", flush=True)
    sources = get_active_sources()
    print(f"  {len(sources)} sources configured", flush=True)

    # 1. 이전 항목 로드
    prev_map = load_previous_items()
    print(f"  loaded {len(prev_map)} previous items", flush=True)

    # 2. 모든 소스 fetch
    all_new_items = []
    source_status = []
    new_items_by_source = {}

    for src in sources:
        name = src[0]
        source_type = src[2]
        items, status = fetch_source(src)
        source_status.append({
            "name": name,
            "url": src[1],
            "status": status,
            "count": len(items),
        })
        # 진짜 신규 카운트 (이전 prev_map에 없던 URL)
        new_in_src = sum(1 for it in items if it["url"] not in prev_map)
        new_items_by_source[name] = new_in_src
        all_new_items.extend(items)
        # v2.7: arXiv API는 권장 호출 간격 3초 (429 방지)
        if source_type == "arxiv":
            time.sleep(3)
        else:
            time.sleep(0.3)

    # 2-b. Naver Search API 추가 fetch (credentials 있을 때만)
    if has_naver():
        naver_items, naver_status = fetch_all_naver()
        all_new_items.extend(naver_items)
        for s in naver_status:
            new_in_src = sum(
                1 for it in naver_items
                if it.get("naver_query") and f"Naver: {it['naver_query']}" == s["name"]
                and it["url"] not in prev_map
            )
            new_items_by_source[s["name"]] = new_in_src
        source_status.extend(naver_status)
        print(f"  [naver] +{len(naver_items)} items from {len(naver_status)} queries", flush=True)
    else:
        print("  [naver] no credentials, skipped", flush=True)

    # 2-c. Semantic Scholar 논문 fetch (Google Scholar 대안)
    try:
        ss_items = fetch_semantic_scholar(per_query_limit=10, days_back=30)
        all_new_items.extend(ss_items)
        new_ss = sum(1 for it in ss_items if it["url"] not in prev_map)
        new_items_by_source["Semantic Scholar"] = new_ss
        source_status.append({
            "name": "Semantic Scholar",
            "url": "https://api.semanticscholar.org",
            "status": "active" if ss_items else "idle",
            "count": len(ss_items),
        })
        print(f"  [semantic-scholar] +{len(ss_items)} papers ({new_ss} new)", flush=True)
    except Exception as exc:
        print(f"  [semantic-scholar] failed: {exc}", flush=True)
        source_status.append({
            "name": "Semantic Scholar",
            "url": "https://api.semanticscholar.org",
            "status": "error",
            "count": 0,
        })

    # 3. 같은 빌드 내 URL 중복 제거
    seen = set()
    new_unique = []
    for it in all_new_items:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        new_unique.append(it)
    print(f"  fetched {len(all_new_items)} ({len(new_unique)} unique)", flush=True)

    # 4. 기존 항목과 merge
    merged, new_count = merge_items(prev_map, new_unique)
    print(f"  merged: {len(merged)} total ({new_count} new, {len(merged) - new_count} retained)", flush=True)

    # 5. 정렬
    merged.sort(key=lambda x: (x.get("score", 0), x.get("date", "")), reverse=True)

    # 6. 저장
    payload = {
        "fetched_at": datetime.now(KST).isoformat(),
        "new_count_this_run": new_count,
        "retained_count": len(merged) - new_count,
        "sources": source_status,
        "items": merged,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # 7. 소스 히스토리 갱신
    update_source_history(source_status, new_items_by_source)

    active_cnt = sum(1 for s in source_status if s["status"] == "active")
    print(f"[done] {len(merged)} total, +{new_count} new, {active_cnt}/{len(sources)} sources active", flush=True)


if __name__ == "__main__":
    main()
