"""
Semantic Scholar API 논문 fetcher (Google Scholar 대안)

- 공식 API: https://api.semanticscholar.org/graph/v1
- 무료: 100 req/5min (rate limit), API 키 없이도 가능 (있으면 1 req/sec)
- 검색 쿼리: AI, machine learning, agent, retrieval, legal AI 등
- 반환: arXiv·NeurIPS·ICML 등 메이저 컨퍼런스 논문 다수 포함 → Google Scholar 80%+ 중복

환경 변수 (선택):
  SEMANTIC_SCHOLAR_API_KEY — 있으면 더 높은 한도

사용:
    from semantic_scholar_fetcher import fetch_papers
    papers = fetch_papers(["artificial intelligence", "large language model"], limit=15)
"""

import os
import sys
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json as _json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import clean_text, truncate, categorize, score_item, normalize_url


API_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
KST = timezone(timedelta(hours=9))


# v2.7: 쿼리 8 → 5개로 축소 (rate limit 회피, 가장 중요한 주제 우선)
SEARCH_QUERIES = [
    "large language model",
    "AI agent",
    "legal AI",
    "multi-agent system",
    "retrieval augmented generation",
]


def _api_request(url: str, retries: int = 4):
    """API GET with optional key + exponential backoff on 429."""
    headers = {
        "User-Agent": "AI-Legaltech-Watch/2.7 (research)",
    }
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    last_err = None
    for attempt in range(retries + 1):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=15) as r:
                return _json.loads(r.read().decode("utf-8"))
        except HTTPError as e:
            last_err = f"HTTP {e.code}: {e.reason}"
            if e.code == 429:
                # Rate limited — exponential backoff (3s → 10s → 30s → 60s)
                wait = [3, 10, 30, 60, 120][min(attempt, 4)]
                print(f"    [s2] 429 rate limit — waiting {wait}s before retry", flush=True)
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


def fetch_papers(queries=None, per_query_limit: int = 12, days_back: int = 30):
    """Semantic Scholar에서 논문 수집.

    Returns: list of items in fetch_news.py 형식.
    """
    if queries is None:
        queries = SEARCH_QUERIES

    cutoff_year = (datetime.now(timezone.utc) - timedelta(days=days_back)).year
    seen_ids = set()
    items = []

    fields = "title,abstract,authors,year,publicationDate,url,externalIds,venue,citationCount"

    # v2.7: 시작 전 5초 wait — 같은 IP의 직전 빌드 잔여 카운터 정리
    print("  [semantic-scholar] warm-up wait 5s for rate-limit window", flush=True)
    time.sleep(5)

    for q in queries:
        url = f"{API_BASE}?query={quote(q)}&limit={per_query_limit}&year={cutoff_year}-&fields={fields}"
        print(f"  [semantic-scholar] {q!r}", flush=True)
        try:
            data = _api_request(url)
        except Exception as e:
            print(f"    -> error: {e}", flush=True)
            continue

        for paper in data.get("data", []) or []:
            pid = paper.get("paperId") or ""
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)

            title = clean_text(paper.get("title") or "")
            abstract = clean_text(paper.get("abstract") or "")
            if not title:
                continue

            # URL — arXiv URL 우선, 없으면 Semantic Scholar paper URL
            ext = paper.get("externalIds") or {}
            arxiv_id = ext.get("ArXiv")
            doi = ext.get("DOI")
            paper_url = ""
            if arxiv_id:
                paper_url = f"https://arxiv.org/abs/{arxiv_id}"
            elif paper.get("url"):
                paper_url = paper["url"]
            elif doi:
                paper_url = f"https://doi.org/{doi}"
            else:
                paper_url = f"https://www.semanticscholar.org/paper/{pid}"

            paper_url = normalize_url(paper_url)

            # 발행일
            pub_date = paper.get("publicationDate")  # YYYY-MM-DD 형식
            year = paper.get("year")
            dt = None
            date_unknown = False
            if pub_date:
                try:
                    dt = datetime.strptime(pub_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except Exception:
                    pass
            if not dt and year:
                # 연도만 알면 1월 1일로
                try:
                    dt = datetime(int(year), 1, 1, tzinfo=timezone.utc)
                    date_unknown = True  # 정확한 발행일 모름
                except Exception:
                    pass
            if not dt:
                continue

            # cutoff 한 번 더
            if dt < datetime.now(timezone.utc) - timedelta(days=days_back):
                continue

            authors = paper.get("authors") or []
            author_str = ", ".join((a.get("name") or "")[:50] for a in authors[:3])
            venue = paper.get("venue") or ""
            cite_n = paper.get("citationCount") or 0

            summary = abstract[:400] if abstract else ""
            if venue:
                summary = f"[{venue}] " + summary
            if author_str:
                summary = f"{author_str} — " + summary

            default_cats = ["papers"]
            categories = categorize(title, summary, default_cats, "semantic_scholar")
            score = score_item(title, summary, dt, categories)
            # citation 보너스
            if cite_n >= 50:
                score += 8
            elif cite_n >= 10:
                score += 4

            items.append({
                "title": title,
                "url": paper_url,
                "source": "Semantic Scholar",
                "source_type": "semantic_scholar",
                "lang": "en",
                "date": dt.isoformat(),
                "date_unknown": date_unknown,
                "first_seen": datetime.now(KST).isoformat(),
                "summary": summary,
                "categories": categories,
                "score": score,
            })

        # Rate limit 친화적으로 잠시 대기 (v2.7: 1.2 → 3s)
        time.sleep(3)

    print(f"  [semantic-scholar] total: {len(items)} papers", flush=True)
    return items


if __name__ == "__main__":
    # 로컬 테스트
    papers = fetch_papers(["AI agent", "large language model"], per_query_limit=5)
    for p in papers[:5]:
        print(f"  {p['date'][:10]} | cite-? | {p['title'][:80]}")
        print(f"    {p['url']}")
