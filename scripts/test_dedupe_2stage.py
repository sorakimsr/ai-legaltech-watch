"""
v6.15.36 (P2-7): dedupe 2단계 병합 판정 회귀 테스트.

불변식: "회사명 일치(first_token/proper_noun)는 필요조건 게이트일 뿐,
        내용 유사도(content_similarity)가 floor를 넘어야만 병합한다."
  → 같은 회사를 다룬 *다른 사건*은 병합 안 됨(과병합 차단),
    내용이 충분히 겹치는 *같은 사건*은 병합 유지.

실행: python3 scripts/test_dedupe_2stage.py   (성공 시 exit 0)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dedupe_similar as D

D_ = "2026-05-28T0{}:00:00+00:00"


def _items():
    return [
        # A) 같은 회사(Anthropic) 다른 사건 — 과병합 차단 대상
        {"title": "Anthropic, 새 모델 Claude 4.8 공개", "summary": "Anthropic이 OpenAI와 경쟁 구도에서 신모델을 내놨다",
         "date": D_.format(0), "source": "S1", "score": 50, "url": "a1"},
        {"title": "Anthropic, 유럽 밀라노 사무소 개설", "summary": "Anthropic은 OpenAI 대비 유럽 시장 확장에 나선다",
         "date": D_.format(1), "source": "S2", "score": 40, "url": "a2"},
        # B) 같은 사건, 매체만 다름 — 병합 유지 대상 (제목 내용 충분히 겹침)
        {"title": "앤트로픽 프레시필즈 법률 AI 제휴 발표", "summary": "두 회사가 법률 AI 협력",
         "date": D_.format(0), "source": "S3", "score": 60, "url": "b1"},
        {"title": "앤트로픽 프레시필즈 법률 AI 협력 체결", "summary": "법률 AI 분야 제휴",
         "date": D_.format(2), "source": "S4", "score": 55, "url": "b2"},
        # C) 회사명(OpenAI)만 겹치는 다른 사건 — 병합 안 됨
        {"title": "OpenAI 신제품 출시", "summary": "오픈AI 새 제품",
         "date": D_.format(0), "source": "S5", "score": 45, "url": "c1"},
        {"title": "OpenAI 데이터센터 대규모 투자", "summary": "오픈AI 인프라 투자 확대",
         "date": D_.format(3), "source": "S6", "score": 48, "url": "c2"},
    ]


def _group_of(groups, items, url):
    for gi, g in enumerate(groups):
        if any(items[i]["url"] == url for i in g):
            return gi
    return -1


def test_overmerge_blocked_same_company_different_event():
    items = _items()
    groups = D.group_items(items)
    assert _group_of(groups, items, "a1") != _group_of(groups, items, "a2"), \
        "같은 회사 다른 사건(a1,a2)이 병합됨 — 과병합 차단 실패"


def test_legit_same_event_merge_preserved():
    items = _items()
    groups = D.group_items(items)
    assert _group_of(groups, items, "b1") == _group_of(groups, items, "b2"), \
        "같은 사건(b1,b2)이 분리됨 — 정상 병합 손실"


def test_company_only_anchor_not_merged():
    items = _items()
    groups = D.group_items(items)
    assert _group_of(groups, items, "c1") != _group_of(groups, items, "c2"), \
        "회사명만 겹치는 다른 사건(c1,c2)이 병합됨"


def test_content_similarity_no_company_bonus():
    # content_similarity는 회사명 보너스를 포함하지 않는다 (순수 내용).
    s = D.content_similarity("Anthropic, 새 모델 공개", "Anthropic, 사무소 개설")
    assert s < D.ANCHORED_CONTENT_SIM, f"회사명만 겹치는 제목의 content_similarity가 너무 높음: {s}"


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1; print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests)-failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
