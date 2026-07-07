"""strategy_quality (v6.17.0) 단위 테스트 — 검증 게이트·클러스터링·북마크 힌트."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import strategy_quality as sq  # noqa: E402


def _card(title, urls, tag="TREND 01 · 주제", emergency=False):
    c = {
        "tag": tag,
        "title": title,
        "body": "본문",
        "action": "액션",
        "citations": [{"url": u, "title": "t", "source": "s", "date": "2026-07-07"} for u in urls],
    }
    if emergency:
        c["_emergency"] = True
    return c


# ---- validate_cards: 근거 URL 겹침 ----

def test_identical_urls_dropped():
    """7/7 LG 사례 재현: 같은 기사 1건이 두 카드의 유일 근거 → 뒤 카드 drop."""
    c1 = _card("AI 에이전트와 금융 예측 모델의 책임 구조", ["http://a.com/lg"])
    c2 = _card("멀티에이전트 AI의 산업 확산과 기술 구조", ["http://a.com/lg"],
               tag="TREND 06 · 멀티에이전트")
    kept, dropped = sq.validate_cards([c1, c2])
    assert len(kept) == 1 and kept[0] is c1
    assert len(dropped) == 1 and dropped[0][0] is c2


def test_subset_urls_dropped():
    c1 = _card("큰 카드", ["http://a.com/1", "http://a.com/2", "http://a.com/3"])
    c2 = _card("부분집합 카드", ["http://a.com/2"], tag="TREND 02 · 다른 주제")
    kept, dropped = sq.validate_cards([c1, c2])
    assert len(kept) == 1 and len(dropped) == 1


def test_disjoint_urls_kept():
    c1 = _card("판결문 공개 정책", ["http://a.com/1", "http://a.com/2"])
    c2 = _card("플래그십 모델 발표", ["http://b.com/1", "http://b.com/2"],
               tag="TREND 02 · 프런티어")
    kept, dropped = sq.validate_cards([c1, c2])
    assert len(kept) == 2 and not dropped


def test_low_overlap_kept():
    """겹침 1/4 (Jaccard 0.25 < 0.5, 부분집합 아님) → 유지."""
    c1 = _card("카드A", ["http://a.com/1", "http://a.com/2", "http://a.com/3"])
    c2 = _card("카드B", ["http://a.com/3", "http://b.com/1"], tag="TREND 02 · 별개")
    kept, dropped = sq.validate_cards([c1, c2])
    assert len(kept) == 2


# ---- validate_cards: 주제 유사도 ----

def test_similar_titles_dropped():
    c1 = _card("로펌 AI 도입 가속", ["http://a.com/1", "http://a.com/2"],
               tag="TREND 01 · 로펌 AI 도입 가속화")
    c2 = _card("로펌 AI 도입 가속", ["http://b.com/1"],
               tag="TREND 02 · 로펌 AI 도입 가속화")
    kept, dropped = sq.validate_cards([c1, c2])
    assert len(kept) == 1 and len(dropped) == 1


# ---- validate_cards: 증분 경로 ----

def test_incremental_dup_vs_existing_dropped():
    existing = [_card("기존 카드", ["http://a.com/lg"])]
    new = [_card("신규지만 같은 사건", ["http://a.com/lg"], tag="TREND 08 · 재탕")]
    kept, dropped = sq.validate_cards(new, existing_cards=existing)
    assert kept == [] and len(dropped) == 1  # 증분: 전부 중복이면 0건이 올바름


def test_full_path_safeguard_keeps_one():
    """full 경로: 병리적 전멸 시 첫 카드 보존."""
    c1 = _card("카드", ["http://a.com/1"])
    kept, _ = sq.validate_cards([c1])
    assert kept == [c1]


def test_emergency_cards_exempt():
    e1 = _card("임시1", ["http://a.com/1"], emergency=True)
    e2 = _card("임시2", ["http://a.com/1"], tag="TREND 02 · 임시", emergency=True)
    kept, dropped = sq.validate_cards([e1, e2])
    assert len(kept) == 2 and not dropped


# ---- cluster_topics: deterministic 후처리 ----

def _items(n):
    return [{"title": f"기사{i}", "summary_ko": f"요약{i}", "source": "S",
             "date": "2026-07-07", "url": f"http://x.com/{i}", "score": 50}
            for i in range(1, n + 1)]


def test_cluster_exclusive_assignment(monkeypatch):
    """LLM이 같은 인덱스를 두 클러스터에 배정해도 후처리가 선착순 배타 배분."""
    monkeypatch.setattr(sq, "call_llm_json", lambda *a, **k: {
        "clusters": [
            {"topic": "주제 A", "bucket": "legal", "indexes": [1, 2], "reason": "r"},
            {"topic": "주제 B", "bucket": "frontier", "indexes": [2, 3], "reason": "r"},
            {"topic": "빈 클러스터", "bucket": "legal", "indexes": [2], "reason": "r"},
        ]
    })
    clusters = sq.cluster_topics(_items(5), "오늘")
    assert [c["indexes"] for c in clusters] == [[1, 2], [3]]  # 2는 첫 클러스터만, 빈 것 제거


def test_cluster_invalid_indexes_filtered(monkeypatch):
    monkeypatch.setattr(sq, "call_llm_json", lambda *a, **k: {
        "clusters": [{"topic": "주제", "bucket": "legal",
                      "indexes": [0, 1, 99, "x", 2], "reason": "r"}]
    })
    clusters = sq.cluster_topics(_items(3), "오늘")
    assert clusters[0]["indexes"] == [1, 2]


def test_cluster_llm_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(sq, "call_llm_json", lambda *a, **k: {})
    assert sq.cluster_topics(_items(3), "오늘") == []


# ---- write_cluster_cards ----

def test_write_cards_sources_restricted_to_cluster(monkeypatch):
    """LLM이 클러스터 밖 인덱스를 sources로 반환해도 배정 인덱스로 제한."""
    monkeypatch.setattr(sq, "call_llm_json", lambda *a, **k: {
        "title": "제목", "body": "본문", "action": "액션", "sources": [1, 4, 5],
    })
    clusters = [{"topic": "주제", "bucket": "legal", "indexes": [1, 2], "reason": "r"}]
    cards = sq.write_cluster_cards(clusters, _items(5), "오늘")
    assert len(cards) == 1
    assert cards[0]["sources"] == [1]  # 4, 5는 클러스터 밖 → 제외
    assert cards[0]["tag"].startswith("TREND 01 · 주제")


def test_write_cards_partial_failure_isolated(monkeypatch):
    """클러스터 1개 실패해도 나머지는 생성 (구조적 격리)."""
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return {}  # 첫 클러스터 실패
        return {"title": "제목", "body": "본문", "action": "액션", "sources": [3]}

    monkeypatch.setattr(sq, "call_llm_json", fake)
    clusters = [
        {"topic": "실패 주제", "bucket": "legal", "indexes": [1, 2], "reason": "r"},
        {"topic": "성공 주제", "bucket": "frontier", "indexes": [3], "reason": "r"},
    ]
    cards = sq.write_cluster_cards(clusters, _items(3), "오늘")
    assert len(cards) == 1 and cards[0]["sources"] == [3]


# ---- load_bookmark_hints ----

def test_slug_to_text():
    assert sq._slug_to_text(
        "https://www.legalcheek.com/2026/05/ex-latham-associate-unveils-free-legal-ai-tool"
    ) == "ex latham associate unveils free legal ai tool"
    assert sq._slug_to_text("https://example.com/") == "example.com"


def test_bookmark_hints_from_export(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    export = {
        "items": {
            "https://site.com/2026/07/court-ruling-data-opened-for-ai-training": {"savedAt": 2},
            "https://site.com/x": {"savedAt": 1},  # slug 짧음 → netloc, 8자 초과라 포함
        },
        "_meta": {},
    }
    (data_dir / "bookmarks_export_test.json").write_text(
        json.dumps(export), encoding="utf-8")
    hints = sq.load_bookmark_hints(str(tmp_path))
    assert any("court ruling data opened" in h for h in hints)


def test_bookmark_hints_missing_files(tmp_path):
    assert sq.load_bookmark_hints(str(tmp_path)) == []


# ---- v6.18.0: 트렌드 연속성 ----

from datetime import date as _date  # noqa: E402


def _write_history(tmp_path, daily: dict):
    p = tmp_path / "strategy_history.json"
    p.write_text(json.dumps({"daily": daily}, ensure_ascii=False), encoding="utf-8")
    return str(p)


def test_recent_context_loads_topics_and_actions(tmp_path):
    hp = _write_history(tmp_path, {
        "2026-07-06": {"summary": "", "cards": [
            {"tag": "TREND 01 · AI 거버넌스", "title": "거버넌스 제도화", "action": "액션 A"},
            {"tag": "TREND 02 · 임시", "title": "임시", "action": "x", "_emergency": True},
        ]},
        "2026-07-01": [  # 옛 list 포맷도 지원
            {"tag": "TREND 01 · 판결문", "title": "판결문 공개", "action": "액션 B"},
        ],
    })
    ctx = sq.load_recent_daily_context(hp, _date(2026, 7, 7), days=7)
    assert len(ctx["topics"]) == 2  # _emergency 제외
    assert ctx["topics"][0]["date"] == "2026-07-06"
    assert "액션 A" in ctx["actions"] and "액션 B" in ctx["actions"]


def test_recent_context_missing_file(tmp_path):
    ctx = sq.load_recent_daily_context(str(tmp_path / "none.json"), _date(2026, 7, 7))
    assert ctx == {"topics": [], "actions": []}


def test_cluster_continuity_parsed(monkeypatch):
    captured = {}

    def fake(prompt, **k):
        captured["prompt"] = prompt
        return {"clusters": [
            {"topic": "거버넌스 전개", "bucket": "legal", "indexes": [1],
             "continuity": "developing", "prior_ref": "거버넌스 제도화", "reason": "r"},
            {"topic": "새 흐름", "bucket": "frontier", "indexes": [2],
             "continuity": "이상한값", "reason": "r"},
        ]}

    monkeypatch.setattr(sq, "call_llm_json", fake)
    topics = [{"date": "2026-07-06", "tag": "TREND 01 · AI 거버넌스", "title": "거버넌스 제도화"}]
    clusters = sq.cluster_topics(_items(3), "오늘", recent_topics=topics)
    assert "거버넌스 제도화" in captured["prompt"]  # 히스토리 주입 확인
    assert clusters[0]["continuity"] == "developing"
    assert clusters[0]["prior_ref"] == "거버넌스 제도화"
    assert clusters[1]["continuity"] == "new"  # 잘못된 값 → new 정규화


def test_write_cards_continuity_metadata_and_negatives(monkeypatch):
    captured = {"prompts": []}

    def fake(prompt, **k):
        captured["prompts"].append(prompt)
        return {"title": "제목", "body": "본문", "action": "새로운 관점의 액션", "sources": [1]}

    monkeypatch.setattr(sq, "call_llm_json", fake)
    clusters = [{"topic": "전개 주제", "bucket": "legal", "indexes": [1],
                 "continuity": "developing", "prior_ref": "기존 카드 제목", "reason": "r"}]
    cards = sq.write_cluster_cards(clusters, _items(2), "오늘",
                                   recent_actions=["파일럿을 진행하고 KPI로 설정한다"])
    assert cards[0]["continuity"] == "developing"
    assert cards[0]["prior_ref"] == "기존 카드 제목"
    p = captured["prompts"][0]
    assert "기존 카드 제목" in p and "delta" in p  # 연속성 블록
    assert "파일럿을 진행하고" in p  # negative example 주입


# ---- v6.18.0: action 템플릿 감지 ----

def test_flag_template_actions_vs_history():
    c = _card("카드", ["http://a.com/1"])
    c["action"] = "자사 AI 프로젝트를 분류하고 파일럿을 진행하며 KPI로 설정한다"
    n = sq.flag_template_actions([c], recent_actions=[
        "자사 AI 프로젝트를 분류하고 파일럿을 진행해 KPI로 설정하자"])
    assert n == 1 and c.get("_action_template") is True


def test_flag_template_actions_within_batch():
    c1 = _card("카드1", ["http://a.com/1"])
    c2 = _card("카드2", ["http://b.com/1"], tag="TREND 02 · 별개")
    c1["action"] = "판결문 공개 대응 자문 패키지를 기획해 클라이언트 세미나로 연결한다"
    c2["action"] = "판결문 공개 대응 자문 패키지를 기획해 클라이언트 세미나로 연결해보자"
    n = sq.flag_template_actions([c1, c2])
    assert n == 1 and c2.get("_action_template") is True and not c1.get("_action_template")


def test_flag_template_actions_distinct_pass():
    c1 = _card("카드1", ["http://a.com/1"])
    c2 = _card("카드2", ["http://b.com/1"], tag="TREND 02 · 별개")
    c1["action"] = "금융 AI 책임 법리 메모를 작성해 대기업 법무팀 대상 세미나로 연결한다"
    c2["action"] = "EU AI Act 시행 일정에 맞춰 규제 대응 뉴스레터 발행 여부를 검토한다"
    assert sq.flag_template_actions([c1, c2]) == 0
