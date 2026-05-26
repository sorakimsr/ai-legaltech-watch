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
import re
import socket
import sys
import time
from datetime import datetime, timezone, timedelta

import feedparser
from dateutil import parser as dateparser

# v4.6: 각 RSS 호출 timeout 8s → 20s (Artificial Lawyer 등 글로벌 RSS timeout 잦음)
socket.setdefaulttimeout(20)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (
    clean_text, truncate, parse_date_safe, categorize, score_item, normalize_url,
    is_relevant
)
from sources import get_active_sources
from naver_fetcher import fetch_all_naver, has_credentials as has_naver
from openalex_fetcher import fetch_papers as fetch_openalex


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(ROOT_DIR, "data", "raw_news.json")
PREV_NEWS_PATH = os.path.join(ROOT_DIR, "data", "news.json")
SOURCE_HISTORY_PATH = os.path.join(ROOT_DIR, "data", "source_history.json")
KST = timezone(timedelta(hours=9))

MAX_AGE_DAYS = 30
MAX_PER_SOURCE = 20
SOURCE_HISTORY_RETAIN_DAYS = 30

# v2.7.5: fetch 단계에서 최근 N일(KST) 항목만 수집. 누적은 merge에서 30일 유지.
# date_unknown=True 인 항목은 일단 통과 (수집일 = 오늘이라 가정).
# 자정 경계 누락 방지 위해 today + yesterday = 2일 (사용자 정책).
FETCH_DAYS = 2


# 보존할 필드 — 기존 항목과 새 항목 merge 시 이전 enriched 값을 잃지 않게
PRESERVE_FIELDS = [
    "summary_ko", "insight_ko", "llm_enriched",
    "entities", "relations",  # Phase 2에서 추가될 필드
    "persona_score", "persona_reason",  # v6.8 Phase 2: LLM 페르소나 평가
    "related", "related_count",  # dedupe 단계 결과
]


def _arxiv_fetch_with_retry(url: str, max_retries: int = 3):
    """v3.0: arXiv API HTTP 429 대응 — Retry-After 헤더 + exponential backoff.

    arXiv 권장 정책: 호출 간격 최소 3초, 트래픽 많을 때 429 반환 후 Retry-After 제공.
    """
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError

    headers = {"User-Agent": "Mozilla/5.0 (compatible; AI-Legaltech-Watch/3.4)"}
    # v3.4: arXiv 429가 retry 후에도 fail하는 케이스가 잦음 — backoff 더 길게
    delays = [10, 30, 90]  # 1차 10초, 2차 30초, 3차 90초

    for attempt in range(max_retries + 1):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=25) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            if exc.code == 429 and attempt < max_retries:
                # Retry-After 헤더 우선, 없으면 backoff 시퀀스 사용
                ra = exc.headers.get("Retry-After") if exc.headers else None
                wait = delays[attempt]
                if ra:
                    try:
                        wait = max(wait, int(ra))
                    except (TypeError, ValueError):
                        pass
                print(f"    -> arxiv 429, retry in {wait}s (attempt {attempt+1}/{max_retries})", flush=True)
                time.sleep(wait)
                continue
            raise
        except Exception:
            if attempt < max_retries:
                wait = delays[attempt]
                print(f"    -> arxiv transient error, retry in {wait}s (attempt {attempt+1}/{max_retries})", flush=True)
                time.sleep(wait)
                continue
            raise
    return None  # unreachable


def fetch_source(source_def):
    name, url, source_type, default_cats, lang = source_def
    items = []
    try:
        print(f"  [fetch] {name}", flush=True)
        # v2.7: arXiv API는 응답이 무거워서 전역 8초 timeout으로는 잘림 →
        # urllib로 별도 호출 (25s timeout) 후 raw text를 feedparser에 전달
        # v3.0: HTTP 429 대응 retry 로직 추가
        if source_type == "arxiv" and "api/query" in url:
            try:
                body = _arxiv_fetch_with_retry(url, max_retries=3)
                if not body:
                    print(f"    -> arxiv api fetch error: empty body", flush=True)
                    return [], "error"
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
            # v5.2: 논문(arxiv)은 abstract 전문 활용 — 400자 → 1800자
            if source_type == "arxiv":
                summary = truncate(clean_text(raw_summary), 1800)
            else:
                summary = truncate(clean_text(raw_summary), 400)

            # v5.2: arXiv 메타데이터 추출 — authors, Subjects 태그, arxiv_id
            paper_meta = None
            if source_type == "arxiv":
                authors_list = []
                for a in (getattr(e, "authors", None) or []):
                    nm = a.get("name") if isinstance(a, dict) else str(a)
                    if nm and nm.strip():
                        authors_list.append(nm.strip())
                arxiv_tags = []
                for t in (getattr(e, "tags", None) or []):
                    term = t.get("term") if isinstance(t, dict) else str(t)
                    if term and re.match(r"^[a-z\-]+\.[A-Z]{2,}$", term):  # cs.AI, cs.LG, stat.ML 패턴
                        arxiv_tags.append(term)
                primary_cat = None
                pc = getattr(e, "arxiv_primary_category", None)
                if pc:
                    primary_cat = pc.get("term") if isinstance(pc, dict) else str(pc)
                arxiv_id = None
                m = re.search(r"arxiv\.org/abs/([\d\.]+)", link or "")
                if m:
                    arxiv_id = m.group(1)
                paper_meta = {
                    "authors": authors_list[:10],
                    "arxiv_tags": arxiv_tags,
                    "primary_category": primary_cat,
                    "arxiv_id": arxiv_id,
                }

            # v6.9: 한국 매체(lang=='ko')의 RSS pubDate는 거의 항상 KST이지만 timezone offset 없음.
            #       parse_date_safe의 default_tz를 KST로 지정해야 9시간 어긋남 방지.
            #       영문 매체는 UTC default (기존 동작).
            KST = timezone(timedelta(hours=9))
            default_tz = KST if lang == "ko" else timezone.utc

            # v2.7: arxiv는 updated(최신 revision) 우선 사용 — v2 revision 같은 실제 컨텐츠 수정일 잡기 위해
            if source_type == "arxiv":
                date_str = (
                    getattr(e, "updated", None)
                    or getattr(e, "published", None)
                    or getattr(e, "pubDate", None)
                )
                dt = parse_date_safe(date_str, default_tz=default_tz)
                if not dt and hasattr(e, "updated_parsed") and e.updated_parsed:
                    dt = datetime(*e.updated_parsed[:6], tzinfo=default_tz)
                if not dt and hasattr(e, "published_parsed") and e.published_parsed:
                    dt = datetime(*e.published_parsed[:6], tzinfo=default_tz)
            else:
                date_str = (
                    getattr(e, "published", None)
                    or getattr(e, "updated", None)
                    or getattr(e, "pubDate", None)
                )
                dt = parse_date_safe(date_str, default_tz=default_tz)
                if not dt and hasattr(e, "published_parsed") and e.published_parsed:
                    dt = datetime(*e.published_parsed[:6], tzinfo=default_tz)
                if not dt and hasattr(e, "updated_parsed") and e.updated_parsed:
                    dt = datetime(*e.updated_parsed[:6], tzinfo=default_tz)

            if not title or not link:
                continue

            # 관련성 필터 — Naver/Google News만 적용 (RSS는 패스)
            if not is_relevant(title, summary, source_type):
                continue

            categories = categorize(title, summary, default_cats, source_type)
            score = score_item(title, summary, dt, categories)

            # v4.0: score cut-off 35 — 행동 가치 시그널 없는 article 자동 drop
            # (BLACKLIST 일일이 추가하는 대신 score 시스템이 자동 거름망 역할)
            if score < 35:
                continue

            # 발행일 처리 — 못 파싱하면 None (오늘로 fallback 안 함 — 시사점 분석 오염 방지)
            date_iso = dt.isoformat() if dt else None
            date_unknown = dt is None

            # v2.7.5: 최근 N일(KST) 항목만 수집 — N=2 (오늘+어제, 자정 경계 방어)
            if FETCH_DAYS > 0 and dt is not None:
                today_kst = datetime.now(KST).date()
                cutoff_kst = today_kst - timedelta(days=FETCH_DAYS - 1)
                # dt를 KST로 변환 후 날짜 비교
                if dt.tzinfo is None:
                    dt_with_tz = dt.replace(tzinfo=timezone.utc)
                else:
                    dt_with_tz = dt
                dt_kst_date = dt_with_tz.astimezone(KST).date()
                if dt_kst_date < cutoff_kst:
                    continue  # 어제 이전 → skip (누적 30일은 prev_map에서 유지됨)

            new_item = {
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
            }
            # v5.2: 논문 메타 (arxiv only) — authors, arxiv_tags, primary_category, arxiv_id
            if paper_meta:
                new_item["paper_meta"] = paper_meta
            items.append(new_item)

        return items, ("active" if items else "idle")
    except Exception as exc:
        print(f"    -> exception: {exc}", flush=True)
        return [], "error"


def load_previous_items():
    """이전 빌드 결과 로드. URL → item 매핑.

    v2.7.5: 과거 항목도 새 BLACKLIST/BOILERPLATE 규칙으로 재검증 →
    이전 빌드에서 들어온 추미애·폭우·MBTI·하루건강 등 불용 기사를 즉시 drop.
    """
    if not os.path.exists(PREV_NEWS_PATH):
        return {}
    try:
        with open(PREV_NEWS_PATH, "r", encoding="utf-8") as f:
            prev = json.load(f)
        out = {}
        dropped = 0
        dropped_examples = []
        rescored = 0
        rescored_examples = []
        for it in prev.get("items", []):
            url = it.get("url")
            if not url:
                continue
            # 1. 새 is_relevant 규칙으로 재평가 — 통과 못 하면 drop
            if not is_relevant(
                it.get("title", ""),
                it.get("summary", ""),
                it.get("source_type", "rss"),
            ):
                dropped += 1
                if len(dropped_examples) < 5:
                    dropped_examples.append(it.get("title", "")[:60])
                continue
            # 1-b. v2.8.9: 옛 'domestic' 카테고리 자동 제거 (v2.8.3에서 카테고리 폐기)
            if "categories" in it:
                it["categories"] = [c for c in it["categories"] if c != "domestic"]
            # 2. v2.7.9: 새 PROMO hard cap (v2.7.6) + 가중치(v2.7.3) 재 scoring 일괄 적용
            # v6.8: persona_score 가산형 보정 (LLM이 부여한 0~10) 함께 전달
            old_score = it.get("score", 0)
            new_score = score_item(
                it.get("title", ""),
                it.get("summary", ""),
                it.get("date", ""),
                it.get("categories", []),
                persona_score=it.get("persona_score"),
            )
            if abs(new_score - old_score) >= 5:
                rescored += 1
                if len(rescored_examples) < 5 and new_score < old_score:
                    rescored_examples.append(f"{old_score}→{new_score} {it.get('title', '')[:55]}")
            # v4.0: cut-off 35 미만이면 prev_map에서도 drop (행동 가치 없는 옛 article 자동 정화)
            if new_score < 35:
                dropped += 1
                if len(dropped_examples) < 5:
                    dropped_examples.append(f"[score<35] {it.get('title', '')[:55]}")
                continue
            it["score"] = new_score
            out[url] = it
        if dropped:
            print(f"  [prune] dropped {dropped} previously-stored items (new BLACKLIST)", flush=True)
            for ex in dropped_examples:
                print(f"    - {ex}", flush=True)
        if rescored:
            print(f"  [rescore] re-scored {rescored} items (new PROMO hard cap / 가중치)", flush=True)
            for ex in rescored_examples:
                print(f"    - {ex}", flush=True)
        return out
    except Exception as exc:
        print(f"  [warn] failed to load previous news.json: {exc}", flush=True)
        return {}


def _is_suspicious_collection_date(prev: dict) -> bool:
    """과거 빌드에서 발행일을 못 구해 수집일을 date로 박아둔 항목인지 추정.

    조건: date_unknown 필드가 없거나 False지만, date == first_seen (분 단위 동일)
    인 경우. v2.7 이전 빌드에서 date_unknown 플래그 도입 전 수집 데이터를 보정.
    """
    if prev.get("date_unknown") is True:
        return True  # 이미 unknown 으로 표시됨
    date_s = prev.get("date", "")
    first_s = prev.get("first_seen", "")
    if not date_s or not first_s:
        return False
    # 같은 분 안에 발행=수집인 경우 거의 확실히 fallback
    try:
        dt1 = dateparser.parse(date_s)
        dt2 = dateparser.parse(first_s)
        if dt1.tzinfo is None:
            dt1 = dt1.replace(tzinfo=timezone.utc)
        if dt2.tzinfo is None:
            dt2 = dt2.replace(tzinfo=timezone.utc)
        return abs((dt1 - dt2).total_seconds()) < 120  # 2분 이내
    except Exception:
        return False


def merge_items(prev_map: dict, new_items: list) -> tuple:
    """
    이전 항목 + 새 항목 merge.

    v2.7.1: date 보정 규칙
    - 새 fetch가 실제 발행일을 줬으면(date_unknown=False) 이전 fallback을 덮어쓴다.
    - 새 fetch도 fallback이면(date_unknown=True) 이전 값을 유지 (= 일단 표시)
    - 이전 항목만 남았고 수집일이 의심스러우면 date_unknown=True로 마킹.

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
            # v2.7.1: 날짜 보정 — 새 fetch가 fallback이고 이전 fetch에는 진짜 발행일이 있으면 이전 보존
            new_unknown = bool(merged_it.get("date_unknown"))
            prev_unknown = bool(prev.get("date_unknown")) or _is_suspicious_collection_date(prev)
            if new_unknown and not prev_unknown and prev.get("date"):
                merged_it["date"] = prev["date"]
                merged_it["date_unknown"] = False
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
                # 의심스러운 수집일이면 date_unknown=True로 보정 (시사점 분석 오염 방지)
                if _is_suspicious_collection_date(prev_it):
                    prev_it["date_unknown"] = True
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
        # v3.4: arXiv 권장 3초이지만 카테고리 6개 연속 시 IP 누적 rate limit으로 fail 잦음.
        # 카테고리 사이 sleep 5초 → 8초로 상향. 첫 호출 전 sleep도 추가 권장이지만
        # 그건 fetch_source 호출 측에서 처리.
        if source_type == "arxiv":
            time.sleep(8)
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

    # 2-c. OpenAlex API 논문 fetch (v2.7 — Semantic Scholar 대체)
    # OPENALEX_API_KEY 등록 시 polite pool 진입 → 안정적 수집
    try:
        # v2.7.5: OpenAlex도 최근 N일만 (publication_date >= today-N+1). 누적은 prev_map 유지.
        oa_items = fetch_openalex(per_query_limit=25, days_back=FETCH_DAYS if FETCH_DAYS > 0 else 30)
        all_new_items.extend(oa_items)
        new_oa = sum(1 for it in oa_items if it["url"] not in prev_map)
        new_items_by_source["OpenAlex"] = new_oa
        source_status.append({
            "name": "OpenAlex",
            "url": "https://api.openalex.org",
            "status": "active" if oa_items else "idle",
            "count": len(oa_items),
        })
        print(f"  [openalex] +{len(oa_items)} papers ({new_oa} new)", flush=True)
    except Exception as exc:
        print(f"  [openalex] failed: {exc}", flush=True)
        source_status.append({
            "name": "OpenAlex",
            "url": "https://api.openalex.org",
            "status": "error",
            "count": 0,
        })

    # v2.7.5: 모든 소스(Naver/OpenAlex/RSS) 통합 후 최근 N일(KST) 필터를 한 번 더 적용
    # — Naver처럼 fetch_source 밖에서 들어온 항목도 동일 정책으로 거름
    if FETCH_DAYS > 0:
        today_kst = datetime.now(KST).date()
        cutoff_kst = today_kst - timedelta(days=FETCH_DAYS - 1)
        before = len(all_new_items)
        kept = []
        for it in all_new_items:
            try:
                dt = dateparser.parse(it.get("date", ""))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt.astimezone(KST).date() >= cutoff_kst:
                    kept.append(it)
            except Exception:
                # 날짜 못 읽으면 보수적으로 keep (date_unknown=True 항목 등)
                kept.append(it)
        all_new_items = kept
        print(f"  [today-filter] {before} → {len(all_new_items)} (cutoff {cutoff_kst.isoformat()})", flush=True)

    # v4.5: 수동 추가 article (data/manual_articles.json) 자동 prepend
    # 사용자가 RSS에서 누락된 article을 별도 채널로 추가하는 통로
    manual_path = os.path.join(os.path.dirname(__file__), "..", "data", "manual_articles.json")
    if os.path.exists(manual_path):
        try:
            with open(manual_path, "r", encoding="utf-8") as f:
                manual_data = json.load(f)
            manual_items = manual_data.get("items", [])
            manual_count = 0
            for m in manual_items:
                if not isinstance(m, dict) or not m.get("url"):
                    continue
                # 필수 필드 보완
                m.setdefault("source_type", "rss")
                m.setdefault("lang", "en")
                m.setdefault("first_seen", datetime.now(KST).isoformat())
                m.setdefault("date_unknown", False)
                m.setdefault("categories", [])
                # 카테고리 분류 자동 보강
                cats = m.get("categories", [])
                cats = categorize(m.get("title", ""), m.get("summary", ""), cats, m.get("source_type", "rss"))
                m["categories"] = cats
                # score 재계산 (manual에서 score 적어도 v4.x 로직 적용)
                dt_obj = None
                try:
                    dt_obj = datetime.fromisoformat(m.get("date", "").replace("Z", "+00:00"))
                except Exception:
                    pass
                m["score"] = score_item(m.get("title", ""), m.get("summary", ""), dt_obj, cats)
                all_new_items.insert(0, m)  # prepend (최우선 fetch)
                manual_count += 1
            if manual_count:
                print(f"  [manual] prepended {manual_count} articles from manual_articles.json", flush=True)
        except Exception as e:
            print(f"  [manual] failed: {e}", flush=True)

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
