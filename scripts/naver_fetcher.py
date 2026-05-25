"""
Naver Search API fetcher

환경변수 필요:
- NAVER_CLIENT_ID
- NAVER_CLIENT_SECRET

API: https://openapi.naver.com/v1/search/news.json?query={query}&display=20&sort=date
응답 항목: title, originallink, link, description, pubDate
"""

import os
import sys
import time
import re
import html
from datetime import datetime, timezone, timedelta

import requests
from dateutil import parser as dateparser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import clean_text, truncate, normalize_url, categorize, score_item

KST = timezone(timedelta(hours=9))

NAVER_API_URL = "https://openapi.naver.com/v1/search/news.json"


# 키워드 → (default_categories, display 갯수)
NAVER_QUERIES = [
    ("리걸테크", ["legaltech", "domestic"], 20),
    ("법률 AI", ["legaltech", "domestic"], 20),
    ("BHSN", ["legaltech", "domestic"], 10),
    ("로앤컴퍼니", ["legaltech", "domestic"], 10),
    ("로앤굿", ["legaltech", "domestic"], 10),
    ("엘박스", ["legaltech", "domestic"], 10),
    ("AI 에이전트", ["ai-industry", "domestic"], 20),
    ("생성형 AI", ["ai-industry", "domestic"], 15),
    ("AI 규제", ["policy", "domestic"], 15),
    ("AI 투자", ["funding", "domestic"], 15),
    ("Claude Anthropic", ["ai-industry", "domestic"], 10),
    ("OpenAI GPT", ["ai-industry", "domestic"], 10),
    ("Google Gemini", ["ai-industry", "domestic"], 10),
]


def has_credentials():
    return bool(os.environ.get("NAVER_CLIENT_ID")) and bool(os.environ.get("NAVER_CLIENT_SECRET"))


def fetch_naver_query(query: str, default_cats: list, display: int = 20):
    """단일 키워드에 대해 Naver Search News API 호출"""
    if not has_credentials():
        return [], "error"

    headers = {
        "X-Naver-Client-Id": os.environ["NAVER_CLIENT_ID"],
        "X-Naver-Client-Secret": os.environ["NAVER_CLIENT_SECRET"],
    }
    params = {
        "query": query,
        "display": min(display, 100),
        "sort": "date",
    }
    try:
        r = requests.get(NAVER_API_URL, headers=headers, params=params, timeout=10)
        if r.status_code != 200:
            print(f"    -> naver api error {r.status_code}: {r.text[:120]}", flush=True)
            return [], "error"
        data = r.json()
    except Exception as exc:
        print(f"    -> exception: {exc}", flush=True)
        return [], "error"

    items = []
    for entry in data.get("items", []):
        # Naver API는 HTML 엔티티/태그가 섞여 있음 — clean_text가 처리
        title = clean_text(entry.get("title", ""))
        link = normalize_url(entry.get("originallink") or entry.get("link") or "")
        desc = truncate(clean_text(entry.get("description", "")), 400)
        pub_str = entry.get("pubDate", "")
        try:
            dt = dateparser.parse(pub_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = datetime.now(timezone.utc)

        if not title or not link:
            continue

        cats = categorize(title, desc, default_cats, "naver")
        score = score_item(title, desc, dt, cats)

        # 출처 추출: link 도메인에서
        source_name = _extract_naver_source(link)

        items.append({
            "title": title,
            "url": link,
            "source": source_name,
            "source_type": "naver",
            "lang": "ko",
            "date": dt.isoformat(),
            "first_seen": datetime.now(KST).isoformat(),
            "summary": desc,
            "categories": cats,
            "score": score,
            "naver_query": query,  # 디버깅용
        })

    return items, "active" if items else "idle"


def _extract_naver_source(url: str) -> str:
    """URL에서 매체명 추정"""
    KNOWN = {
        "lawtimes.co.kr": "법률신문",
        "aitimes.com": "AI타임스",
        "zdnet.co.kr": "ZDNet Korea",
        "etnews.com": "전자신문",
        "dt.co.kr": "디지털타임스",
        "byline.network": "바이라인네트워크",
        "thelec.kr": "디일렉",
        "platum.kr": "플래텀",
        "venturesquare.net": "벤처스퀘어",
        "themiilk.com": "더밀크",
        "mk.co.kr": "매일경제",
        "hankyung.com": "한국경제",
        "yna.co.kr": "연합뉴스",
        "yonhapnews.co.kr": "연합뉴스",
        "joongang.co.kr": "중앙일보",
        "chosun.com": "조선일보",
        "donga.com": "동아일보",
        "hani.co.kr": "한겨레",
        "khan.co.kr": "경향신문",
        "news1.kr": "뉴스1",
        "newsis.com": "뉴시스",
        "kmib.co.kr": "국민일보",
        "edaily.co.kr": "이데일리",
        "fnnews.com": "파이낸셜뉴스",
        "sedaily.com": "서울경제",
        "asiae.co.kr": "아시아경제",
        "businesspost.co.kr": "비즈니스포스트",
    }
    m = re.search(r"//(?:www\.|m\.)?([^/]+)", url)
    if not m:
        return "Naver 검색"
    host = m.group(1)
    for k, v in KNOWN.items():
        if k in host:
            return v
    # 알려지지 않은 매체는 도메인을 그대로
    return f"Naver / {host.split('.')[0]}"


def fetch_all_naver():
    """모든 Naver 키워드 쿼리 실행. fetch_news.py에서 호출.

    Returns:
        items: 모든 항목 통합
        source_status: 키워드별 상태 (fetch_news 형식과 호환)
    """
    if not has_credentials():
        print("  [naver] credentials missing, skipping", flush=True)
        return [], []

    print(f"  [naver] {len(NAVER_QUERIES)} queries", flush=True)
    all_items = []
    source_status = []

    for query, cats, display in NAVER_QUERIES:
        items, status = fetch_naver_query(query, cats, display)
        name = f"Naver: {query}"
        source_status.append({
            "name": name,
            "url": f"naver-search:{query}",
            "status": status,
            "count": len(items),
        })
        all_items.extend(items)
        time.sleep(0.15)  # 네이버 API rate-limit 안전 마진

    return all_items, source_status
