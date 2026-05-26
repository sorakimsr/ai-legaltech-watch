"""
OpenAlex API 논문 fetcher (v2.7 — Semantic Scholar 대체)

- 공식 API: https://api.openalex.org
- 무료: 100,000 calls/day. API key 없어도 동작, 있으면 polite pool로 우선처리·안정성 ↑
- AI/ML 논문: arXiv·NeurIPS·ICML·ACL 등 거의 모두 인덱싱

환경 변수 (선택):
  OPENALEX_API_KEY — Authorization Bearer 헤더용
  OPENALEX_MAILTO  — polite pool 진입용 이메일 (key 없을 때 사용)

abstract는 inverted_index 형식 → 짧은 함수로 재구성.
"""

import os
import sys
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json as _json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import clean_text, truncate, categorize, score_item, normalize_url


API_BASE = "https://api.openalex.org/works"
KST = timezone(timedelta(hours=9))

# 검색 쿼리 — v3.9: 핵심 AI 영역 + 사용자 추가 키워드 (논문에서도 같은 흐름 잡힘)
SEARCH_QUERIES = [
    # 코어 AI
    "large language model",
    "AI agent",
    "retrieval augmented generation",
    "legal AI",
    "AI safety alignment",
    "multi-agent system",
    "AI reasoning",
    "generative AI",
    # v3.8: 오케스트레이션·엔지니어링·오픈소스 인프라
    "AI orchestration",
    "agent orchestration",
    "prompt engineering",
    "context engineering",
    "open source LLM",
    # v3.9-A: AI 코딩 툴·MCP (논문에서도 다뤄짐)
    "AI code generation",
    "AI coding assistant",
    "model context protocol",
    # v3.9-B: 거버넌스·감사·안전·설명가능성
    "AI audit",
    "AI red teaming",
    "AI safety evaluation",
    "explainable AI",
    "trustworthy AI",
    "AI governance",
    # v3.9-C: Sovereign AI·디지털 주권
    "sovereign AI",
    "AI data sovereignty",
    "on-premise AI deployment",
    # v3.9-D: 실무 도입·평가
    "AI deployment case study",
    "AI cost efficiency",
    "AI ROI",
    "AI benchmark evaluation",
    # v3.9 보강: v3.8 영문 키워드를 논문 검색에도 등록
    "harness engineering AI",
    "clone engineering AI",
    "forward deployed engineer AI",
    "AI agent infrastructure",
    "vibe coding AI",
    # v3.12: 주요 frontier·open-source LLM 모델 (논문에서 평가·벤치마크 비교 빈번)
    "Claude Mythos",
    "Gemma language model",
    "DeepSeek LLM",
    "Qwen language model",
    # v3.12: AI 모델 벤치마크·평가 — 논문에서 매우 빈번하게 등장
    "MMLU benchmark",
    "HumanEval benchmark",
    "GPQA benchmark",
    "SWE-bench evaluation",
    "ARC-AGI reasoning",
    "LiveBench LLM",
    "Chatbot Arena LMSYS",
    "LLM benchmark evaluation",
    "LLM leaderboard",
    "Korean language model benchmark",
]


def _api_request(url: str, retries: int = 3):
    """OpenAlex API GET — api_key query parameter (공식 방식) 사용."""
    headers = {
        "User-Agent": "AI-Legaltech-Watch/2.7 (https://daibfy.com)",
    }

    last_err = None
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=15) as r:
                return _json.loads(r.read().decode("utf-8"))
        except HTTPError as e:
            last_err = f"HTTP {e.code}: {e.reason}"
            if e.code == 429:
                wait = [2, 5, 15, 30][min(attempt, 3)]
                print(f"    [openalex] 429 — waiting {wait}s", flush=True)
                time.sleep(wait)
                continue
            break
        except URLError as e:
            last_err = f"URL error: {e.reason}"
            time.sleep(2)
            continue
        except Exception as e:
            last_err = f"Exception: {e}"
            break
    raise RuntimeError(last_err or "Unknown error")


def _reconstruct_abstract(inverted_index):
    """OpenAlex의 abstract_inverted_index (word → [positions]) 를 평문 abstract로 복원."""
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            try:
                word_positions.append((int(pos), word))
            except (ValueError, TypeError):
                continue
    word_positions.sort()
    return " ".join(w for _, w in word_positions)


def fetch_papers(queries=None, per_query_limit: int = 25, days_back: int = 30):
    """OpenAlex에서 논문 수집. Returns: fetch_news.py 형식 items."""
    if queries is None:
        queries = SEARCH_QUERIES

    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    seen_ids = set()
    items = []

    api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
    mailto = os.environ.get("OPENALEX_MAILTO", "").strip()
    print(f"  [openalex] API key: {'yes' if api_key else 'no'}, mailto: {'yes' if mailto else 'no'}", flush=True)

    for q in queries:
        # OpenAlex 필터:
        #   - from/to publication_date 둘 다 지정 → 미래 발행 예정작(2027/2033 등) 제외
        #   - type:article → 학술 논문만 (book, dataset, preprint 등 정리 — preprint도 article로 분류됨)
        #   - is_paratext:false → 표지/색인/요약 페이지 제외
        filter_parts = [
            f"from_publication_date:{cutoff_date}",
            f"to_publication_date:{today_date}",
            "type:article",
            "is_paratext:false",
        ]
        # 정렬: relevance_score:desc → 검색어 매칭도 최우선, 같은 점수면 최신순
        url = (
            f"{API_BASE}"
            f"?search={quote_plus(q)}"
            f"&filter={','.join(filter_parts)}"
            f"&per-page={per_query_limit}"
            f"&sort=relevance_score:desc"
        )
        if api_key:
            url += f"&api_key={quote_plus(api_key)}"
        elif mailto:
            url += f"&mailto={quote_plus(mailto)}"

        print(f"  [openalex] {q}", flush=True)
        try:
            data = _api_request(url)
        except Exception as e:
            print(f"    -> error: {e}", flush=True)
            continue

        for work in (data.get("results") or []):
            oid = work.get("id") or ""
            if not oid or oid in seen_ids:
                continue
            seen_ids.add(oid)

            title = clean_text(work.get("title") or work.get("display_name") or "")
            if not title:
                continue

            # 발행일 — publication_date(YYYY-MM-DD)만 신뢰. year-only는 정확도 떨어져 제외
            pub_date = work.get("publication_date")
            dt = None
            date_unknown = False
            if pub_date:
                try:
                    dt = datetime.strptime(pub_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except Exception:
                    pass
            if not dt:
                # publication_date 없는 항목은 미래·과거 잘못 매핑 위험 있어 skip
                continue
            # 최근 N일 cutoff
            if dt < datetime.now(timezone.utc) - timedelta(days=days_back):
                continue
            # 미래 발행 예정 논문 제외 (OpenAlex는 future-dated work 포함)
            if dt > datetime.now(timezone.utc) + timedelta(days=1):
                continue

            # URL — 우선순위: open_access landing → primary_location.landing_page_url → doi → OpenAlex id
            primary = work.get("primary_location") or {}
            oa_url = (work.get("open_access") or {}).get("oa_url")
            doi = work.get("doi")  # 보통 "https://doi.org/..."
            paper_url = (
                oa_url
                or primary.get("landing_page_url")
                or doi
                or oid
            )
            paper_url = normalize_url(paper_url or "")

            # 저자·소속·학술지
            authorships = work.get("authorships") or []
            author_str = ", ".join(
                (a.get("author", {}).get("display_name") or "")[:50]
                for a in authorships[:3]
                if a.get("author", {}).get("display_name")
            )
            venue = (primary.get("source") or {}).get("display_name") or ""
            cite_n = work.get("cited_by_count") or 0

            # Abstract 복원
            abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))
            abstract = clean_text(abstract)[:400]

            summary = abstract
            if venue:
                summary = f"[{venue}] " + summary
            if author_str:
                summary = f"{author_str} — " + summary

            default_cats = ["papers"]
            categories = categorize(title, summary, default_cats, "openalex")
            score = score_item(title, summary, dt, categories)
            # citation 부스트
            if cite_n >= 100:
                score += 12
            elif cite_n >= 30:
                score += 8
            elif cite_n >= 10:
                score += 4

            items.append({
                "title": title,
                "url": paper_url,
                "source": "OpenAlex",
                "source_type": "openalex",
                "lang": "en",
                "date": dt.isoformat(),
                "date_unknown": False,
                "first_seen": datetime.now(KST).isoformat(),
                "summary": summary,
                "categories": categories,
                "score": score,
                "cited_by_count": cite_n,
            })

        # Rate limit 친화적 sleep
        time.sleep(1)

    print(f"  [openalex] total: {len(items)} papers", flush=True)
    return items


if __name__ == "__main__":
    papers = fetch_papers(["AI agent", "large language model"], per_query_limit=5)
    for p in papers[:5]:
        print(f"  cite={p.get('cited_by_count', 0):>3} | {p['date'][:10]} | {p['title'][:90]}")
        print(f"    {p['url']}")
