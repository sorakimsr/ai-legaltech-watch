"""arXiv abstract 역보강 — 탐지 로직 회귀 테스트 (v6.15.59, 네트워크 불필요).

SIA처럼 제목만 수집된 논문을 골라내되(option A 넓은 탐지), 비논문은 거르는지 고정.
실제 arXiv 조회(_fetch_arxiv_abstract)는 네트워크 의존이라 여기선 제외 — 수동 검증함.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import enrich_with_llm as e


def test_thin_detection():
    assert e._summary_is_thin({"summary": "shared on Hacker News, 1 point"})
    assert not e._summary_is_thin({"summary": "x" * 200})


def test_paper_ref_arxiv_link():
    assert e._looks_like_paper_ref({"url": "https://arxiv.org/abs/2605.30052", "title": "Foo"})


def test_paper_ref_paper_source():
    assert e._looks_like_paper_ref(
        {"source": "Hacker News (AI/ML)", "title": "SIA: Self Improving AI", "lang": "en", "url": "https://news.ycombinator.com/x"}
    )


def test_paper_ref_academic_title():
    # 논문형 영문 제목 ("Name: Subtitle" + 학술 키워드)
    assert e._looks_like_paper_ref(
        {"source": "Reddit", "title": "RePoT: Recoverable Program-of-Thought via Checkpoint Repair", "lang": "en", "url": "https://x"}
    )


def test_non_paper_rejected():
    # 일반 기업/뉴스 제목은 역보강 대상 아님
    assert not e._looks_like_paper_ref(
        {"source": "Reuters", "title": "Samsung launches new phone", "lang": "en", "url": "https://x"}
    )
    assert not e._looks_like_paper_ref(
        {"source": "TechCrunch", "title": "Apple Q3 earnings beat estimates", "lang": "en", "url": "https://x"}
    )


def test_korean_title_not_paper_ref_by_title():
    # 한국어 제목은 제목 패턴 경로로는 후보 아님 (소스/링크 신호 없으면)
    assert not e._looks_like_paper_ref(
        {"source": "AI타임스", "title": "삼성: 새 AI 모델 공개", "lang": "ko", "url": "https://x"}
    )


if __name__ == "__main__":
    for n, f in sorted(globals().items()):
        if n.startswith("test_") and callable(f):
            f(); print("PASS", n)
    print("all ok")
