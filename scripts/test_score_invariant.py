"""
v6.15.33 (P1-3): score_item 어젠다 floor 불변식 단위 테스트.

핵심 불변식: "어젠다 보호 floor(법령 78·SUPER_BOOST 70·핵심도메인 35)는
            persona-aware cap(30+ps×10)보다 항상 우선한다."

실행: python3 scripts/test_score_invariant.py   (성공 시 exit 0, 실패 시 exit 1)
pytest로도 수집됨 (test_* 함수).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import score_item

LONG = "이 사안은 AI 서비스와 법무·전략 의사결정에 직접 영향을 주는 내용으로 충분한 본문 길이를 확보한 요약 문장이다." * 2


def test_law_floor_survives_low_persona_cap():
    # 조건부 법령(개인정보보호법) + AI 맥락 → law floor 78.
    # persona_score=3 → ps_cap=60. 불변식 위반이면 60으로 깎임. 수정 후 >=78 보장.
    s = score_item(
        "개인정보보호법 개정으로 AI 서비스 규제가 강화된다",
        "AI 서비스 사업자에 대한 개인정보보호법 적용 범위가 " + LONG,
        None, [], persona_score=3,
    )
    assert s >= 78, f"law floor 78 should survive ps_cap(60); got {s}"


def test_superboost_floor_survives_low_persona_cap():
    # SUPER_BOOST(판결문 공개) → floor 70. persona_score=2 → ps_cap=50.
    s = score_item(
        "판결문 공개 범위 확대 논의 본격화",
        "사법정책연구원이 판결문 공개제도 개선을 논의한다. " + LONG,
        None, [], persona_score=2,
    )
    assert s >= 70, f"SUPER_BOOST floor 70 should survive ps_cap(50); got {s}"


def test_core_domain_floor_survives_zero_persona_cap():
    # legaltech 카테고리 핵심도메인 floor 35. persona_score=0 → ps_cap=30.
    s = score_item(
        "어느 법률 AI 도구 짧은 소식",
        "짧은 본문.",
        None, ["legaltech"], persona_score=0,
    )
    assert s >= 35, f"core-domain floor 35 should survive ps_cap(30); got {s}"


def test_non_agenda_cap_still_binds():
    # 어젠다 아님 + persona_score=7 → ps_cap=100. floor 0이므로 cap이 그대로 작동.
    s = score_item(
        "어떤 AI 스타트업이 새 제품을 선보였다",
        "일반 AI 산업 소식. AI 제품 출시. " + LONG,
        None, ["ai-industry"], persona_score=7,
    )
    assert s <= 100, f"non-agenda ps=7 must not exceed ps_cap 100; got {s}"


def test_absolute_cap_120():
    # 최고 조건(법령 + persona 10)이어도 절대 cap 120.
    s = score_item(
        "AI 기본법 시행령 확정, 개인정보보호법 교차 적용 핵심 쟁점",
        "AI 기본법과 개인정보보호법, 정보통신망법 교차 적용. " + LONG,
        None, ["legaltech", "policy"], persona_score=10,
    )
    assert 0 <= s <= 120, f"absolute cap 120 violated; got {s}"


def test_high_persona_agenda_reaches_top():
    # 어젠다 + persona=9 → 상단(>=90) 도달해야 함 (정상 동작 회귀 가드).
    s = score_item(
        "판결문 공개제도와 AI 학습 데이터 정책의 교차 쟁점",
        "AI 학습용 판결문 데이터 활용과 규제. " + LONG,
        None, ["legaltech"], persona_score=9,
    )
    assert s >= 90, f"high-persona agenda should reach top tier; got {s}"


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests)-failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
