"""call_llm_json 파싱 견고성 회귀 테스트 (v6.15.58).

배경: 빌드 #122에서 daily 전략이 임시카드로 고착된 진짜 원인은 'LLM 빈 응답'이 아니라
LLM이 반환한 cards JSON의 파싱 실패였다. 한국어 본문에 escape 안 된 큰따옴표·줄바꿈이
섞여 json.loads + 수작업 salvage가 모두 깨짐. json_repair fallback으로 복구.
이 테스트는 그 실패 모드들이 다시 0 카드로 떨어지지 않도록 고정한다.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm_client


def _parse(monkeypatched_response):
    llm_client.call_llm = lambda *a, **k: monkeypatched_response
    return llm_client.call_llm_json("x", max_tokens=100)


def _cards(res):
    if isinstance(res, dict):
        return res.get("cards") or []
    if isinstance(res, list):
        return res
    return []


def test_valid_json_fast_path():
    res = _parse('{"summary":"ok","cards":[{"tag":"T1","title":"정상","body":"b","action":"a"}]}')
    assert _cards(res) and _cards(res)[0]["title"] == "정상"


def test_unescaped_quotes_in_korean_body_cards_first():
    # #122 실제 실패 모드: cards-first + 본문/제목에 escape 안 된 큰따옴표
    broken = '''```json
{"cards":[
 {"tag":"TREND 01","title":"美, 앤트로픽 차단 — "AI가 안보 자산"이 됐다","body":"3,5번 보도.","action":"모니터링","sources":[3,5]},
 {"tag":"TREND 02","title":"AI 모의해킹 일상화","body":"금융권 도입.","action":"검토","sources":[7]}
]}'''
    assert len(_cards(_parse(broken))) == 2


def test_truncated_at_max_tokens_recovers_complete_cards():
    # 토큰 한도로 마지막 카드 중간에서 잘림 → 완성 카드는 살려야 함
    broken = '''```json
{"cards":[
 {"tag":"T1","title":"첫 카드","body":"본문1","action":"a1"},
 {"tag":"T2","title":"둘째 카드","body":"본문2","action":"a2"},
 {"tag":"T3","title":"잘린 카드","body":"여기서 토큰 한'''
    assert len(_cards(_parse(broken))) >= 2


def test_literal_newline_in_string():
    broken = '{"cards":[{"tag":"T1","title":"줄바꿈\n포함","body":"본문","action":"a"}]}'
    assert len(_cards(_parse(broken))) == 1


def test_empty_response_returns_empty_dict():
    assert _parse("") == {}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)
    print("all ok")
