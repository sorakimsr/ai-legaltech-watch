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
from common import clean_text, truncate, normalize_url, categorize, score_item, is_relevant

KST = timezone(timedelta(hours=9))

NAVER_API_URL = "https://openapi.naver.com/v1/search/news.json"


# 키워드 → (default_categories, display 갯수)
# v2.7 확장: 한국 사정 반영 — 영문/한국어 발음 동시 검색, AI 회사 개별 분리, 정책·도입·로펌까지
NAVER_QUERIES = [
    # === 리걸테크 코어 ===
    ("리걸테크", ["legaltech", "domestic"], 20),
    ("\"법률 AI\"", ["legaltech", "domestic"], 20),
    ("\"법률 인공지능\"", ["legaltech", "domestic"], 15),
    ("\"계약서 AI\"", ["legaltech", "domestic"], 10),

    # === 국내 리걸테크 회사 ===
    ("BHSN", ["legaltech", "domestic"], 10),
    ("로앤컴퍼니", ["legaltech", "domestic"], 10),
    ("로앤굿", ["legaltech", "domestic"], 10),
    ("엘박스", ["legaltech", "domestic"], 10),
    ("케이스노트", ["legaltech", "domestic"], 10),

    # === 국내 로펌 (AI 도입 동향) ===
    ("\"김앤장 AI\"", ["legaltech", "domestic"], 10),
    ("\"광장 AI\"", ["legaltech", "domestic"], 10),
    ("\"세종 AI\"", ["legaltech", "domestic"], 10),
    ("\"율촌 AI\"", ["legaltech", "domestic"], 10),
    ("\"테크앤로\"", ["legaltech", "domestic"], 10),

    # === AI 회사 — 영문/한국어 발음 동시 ===
    ("OpenAI OR 오픈AI", ["ai-industry", "domestic"], 15),
    ("ChatGPT OR 챗GPT", ["ai-industry", "domestic"], 15),
    ("Anthropic OR 앤트로픽", ["ai-industry", "domestic"], 15),
    ("Claude OR 클로드", ["ai-industry", "domestic"], 15),
    ("Gemini OR 제미나이", ["ai-industry", "domestic"], 15),
    ("xAI OR 그록 OR Grok", ["ai-industry", "domestic"], 10),
    ("\"Meta AI\" OR 라마 OR Llama", ["ai-industry", "domestic"], 10),
    ("Mistral OR 미스트랄", ["ai-industry", "domestic"], 10),
    ("Perplexity OR 퍼플렉시티", ["ai-industry", "domestic"], 10),

    # === AI 분야·실무 ===
    ("\"AI 에이전트\"", ["ai-industry", "domestic"], 20),
    ("\"생성형 AI\"", ["ai-industry", "domestic"], 15),
    ("\"AI 도입\"", ["ai-industry", "domestic"], 15),
    ("\"AI 전환\" OR AX", ["ai-industry", "domestic"], 15),
    ("\"사내 AI\" OR \"엔터프라이즈 AI\"", ["ai-industry", "domestic"], 10),
    ("\"AI 활용 사례\"", ["ai-industry", "domestic"], 10),

    # === 정책·규제·거버넌스 ===
    ("\"AI 규제\"", ["policy", "domestic"], 15),
    ("\"AI 기본법\"", ["policy", "domestic"], 15),
    ("\"AI 가이드라인\"", ["policy", "domestic"], 10),
    ("\"AI 거버넌스\"", ["policy", "domestic"], 10),
    ("\"AI 윤리\"", ["policy", "domestic"], 10),
    ("\"EU AI Act\"", ["policy", "domestic"], 10),

    # === 투자·M&A ===
    ("\"AI 스타트업\" 투자", ["funding", "domestic"], 15),
    ("\"AI 투자 유치\"", ["funding", "domestic"], 10),
    ("\"AI 인수\" OR \"AI 합병\"", ["funding", "domestic"], 10),

    # === v3.8: 오픈소스 AI ===
    ("\"오픈소스 AI\" OR \"open source AI\"", ["ai-industry", "domestic"], 15),
    ("\"오픈소스 LLM\" OR \"open source LLM\"", ["ai-industry", "domestic"], 10),
    ("\"open weight\" OR \"오픈웨이트\"", ["ai-industry", "domestic"], 10),

    # === v3.8: AI 오케스트레이션·에이전트 인프라 ===
    ("\"AI 오케스트레이션\" OR \"AI orchestration\"", ["ai-industry", "domestic"], 15),
    ("\"오케스트레이터\" OR orchestrator", ["ai-industry", "domestic"], 10),
    ("\"에이전트 오케스트레이션\" OR \"agent orchestration\"", ["ai-industry", "domestic"], 10),
    ("\"멀티 에이전트\" OR \"multi-agent\"", ["ai-industry", "domestic"], 10),

    # === v3.8: AI 엔지니어링 새 직무·실무 영역 ===
    ("\"프롬프트 엔지니어링\" OR \"prompt engineering\"", ["ai-industry", "domestic"], 15),
    ("\"컨텍스트 엔지니어링\" OR \"context engineering\"", ["ai-industry", "domestic"], 10),
    ("\"하네스 엔지니어링\" OR \"harness engineering\"", ["ai-industry", "domestic"], 10),
    ("\"클론 엔지니어링\" OR \"clone engineering\"", ["ai-industry", "domestic"], 10),

    # === v3.8: FDE (Forward Deployed Engineer) — 글로벌 AI 회사 신규 직무 ===
    ("FDE OR \"forward deployed engineer\"", ["adoption", "domestic"], 10),
    ("\"포워드 디플로이드\"", ["adoption", "domestic"], 5),

    # === v3.9-A: AI 코딩 툴 · vibe coding · MCP ===
    ("\"Claude Code\" OR \"클로드 코드\"", ["ai-industry", "domestic"], 10),
    ("Cursor OR \"커서\" AI", ["ai-industry", "domestic"], 10),
    ("Windsurf OR \"GitHub Copilot\" OR \"깃허브 코파일럿\"", ["ai-industry", "domestic"], 10),
    ("\"vibe coding\" OR \"바이브 코딩\"", ["ai-industry", "domestic"], 10),
    ("MCP OR \"Model Context Protocol\" OR \"모델 컨텍스트 프로토콜\"", ["ai-industry", "domestic"], 10),

    # === v3.9-B: AI 감사·안전·레드팀팅·설명가능성 (거버넌스·리스크) ===
    ("\"AI 감사\" OR \"AI audit\"", ["governance", "domestic"], 10),
    ("\"AI 레드팀\" OR \"AI red teaming\"", ["governance", "domestic"], 10),
    ("\"AI 안전\" OR \"AI safety\"", ["governance", "domestic"], 10),
    ("\"설명가능 AI\" OR XAI OR \"explainable AI\"", ["governance", "domestic"], 10),
    ("\"신뢰성 AI\" OR \"trustworthy AI\"", ["governance", "domestic"], 5),
    ("\"model card\" OR \"system card\" OR \"모델 카드\"", ["governance", "domestic"], 5),

    # === v3.9-C: Sovereign AI · 한국형 AI · 디지털 주권 ===
    ("\"Sovereign AI\" OR \"소버린 AI\"", ["policy", "domestic"], 10),
    ("\"한국형 AI\" OR \"국산 AI\" OR \"K-AI\"", ["policy", "domestic"], 10),
    ("\"디지털 주권\" OR \"AI 주권\" OR \"data sovereignty\"", ["policy", "domestic"], 10),
    ("\"온프레미스 AI\" OR \"on-prem AI\"", ["adoption", "domestic"], 5),

    # === v3.9-D: 실무 도입 지표 · ROI · 파일럿 ===
    ("\"AI 파일럿\" OR \"AI POC\" OR \"AI 검증 실험\"", ["adoption", "domestic"], 10),
    ("\"AI ROI\" OR \"AI 투자수익\"", ["adoption", "domestic"], 10),
    ("\"AI 도입 사례\"", ["adoption", "domestic"], 15),
    ("\"AI 운영 비용\" OR \"AI 비용\" OR \"token 비용\"", ["ai-industry", "domestic"], 10),
    ("\"AI 효율\" OR \"AI 생산성\"", ["adoption", "domestic"], 10),
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

        # 관련성 필터 — AI/리걸테크 핵심 키워드 매칭 안 되면 제외
        if not is_relevant(title, desc, "naver"):
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
