"""
Phase 3 — LLM 관계 추출 (Haiku 사용, 저비용).

각 trend card의 body·action 텍스트와 entities.json의 엔티티 카탈로그를 LLM에 보내서
(entity_a_id, relation_type, entity_b_id) triple을 추출.

산출물: data/relations.json
{
  "relations": [
    {
      "source": "openai",
      "target": "anthropic",
      "type": "competes_with",
      "evidence": "OpenAI plans Codex for Legal joining Anthropic in legal AI competition",
      "trend_period": "daily",
      "trend_key": "2026-05-26",
      "trend_tag": "TREND 03 · ...",
      "weight": 1.0
    },
    ...
  ],
  "generated_at": "...",
  "total_relations": 42
}

relation_type 카테고리:
  - competes_with    : 경쟁 (제품·시장 충돌)
  - partners_with    : 제휴·협력
  - acquires         : 인수
  - invests_in       : 투자
  - regulates        : 규제·감독 (정부 → 회사)
  - adopts           : 도입 (회사 → 제품·기술)
  - launches         : 출시·발표
  - implements       : 정책 구현 (정책 → 회사 의무)
  - mentions         : 단순 언급 (약한 관계, 보조용)
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm_client import call_llm_json  # type: ignore


KST = timezone(timedelta(hours=9))
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTITIES_PATH = os.path.join(ROOT_DIR, "data", "entities.json")
STRATEGY_HISTORY_PATH = os.path.join(ROOT_DIR, "data", "strategy_history.json")
ENRICHED_NEWS_PATH = os.path.join(ROOT_DIR, "data", "enriched_news.json")  # v5.1
OUTPUT_PATH = os.path.join(ROOT_DIR, "data", "relations.json")


RELATION_TYPES = [
    "competes_with", "partners_with", "acquires", "invests_in",
    "regulates", "adopts", "launches", "implements", "complies_with", "mentions",
]

# ============================================================================
# v7.2: 관계 타입-방향 검증 (엔티티 타입 페어 화이트리스트)
# 실측 문제: implements가 역방향·의미 붕괴 상태로 누적
#   (law_yulchon→ai_basic_law, samsung→eu_ai_act, ai_basic_law→ftc 등).
# 원인: "준수" 개념이 타입에 없어 LLM이 전부 implements로 출력 + 검증 부재.
# 해결: complies_with 신설 + 타입별 (src그룹, tgt그룹) 화이트리스트 검증.
#   위반 시 ① 방향 뒤집어 유효하면 flip ② ORG→POLICY implements는 complies_with로
#   교정 ③ 그래도 무효면 mentions로 강등 (그래프에선 기본 숨김).
# ============================================================================
_ORG_TYPES = {"ai_company", "legaltech_company", "korean_law_firm", "global_law_firm",
              "korean_finance", "korean_manufacturing", "academic_inst"}
_GOV_TYPES = {"kr_government"}
_POLICY_TYPES = {"policy"}
_PRODUCT_TYPES = {"ai_product"}
_TECH_TYPES = {"tech", "benchmark"}

# 타입별 (허용 src 그룹, 허용 tgt 그룹)
_RELATION_RULES = {
    "competes_with": (_ORG_TYPES | _PRODUCT_TYPES, _ORG_TYPES | _PRODUCT_TYPES),
    "partners_with": (_ORG_TYPES | _GOV_TYPES, _ORG_TYPES | _GOV_TYPES),
    "acquires":      (_ORG_TYPES, _ORG_TYPES),
    "invests_in":    (_ORG_TYPES | _GOV_TYPES, _ORG_TYPES | _TECH_TYPES),
    "regulates":     (_GOV_TYPES | _POLICY_TYPES, _ORG_TYPES | _PRODUCT_TYPES | _TECH_TYPES),
    "adopts":        (_ORG_TYPES | _GOV_TYPES, _PRODUCT_TYPES | _TECH_TYPES),
    "launches":      (_ORG_TYPES | _GOV_TYPES, _PRODUCT_TYPES | _TECH_TYPES | _POLICY_TYPES),
    "implements":    (_POLICY_TYPES | _GOV_TYPES, _ORG_TYPES | _PRODUCT_TYPES | _TECH_TYPES | _POLICY_TYPES),
    "complies_with": (_ORG_TYPES | _PRODUCT_TYPES, _POLICY_TYPES | _GOV_TYPES),
    # mentions: 제한 없음
}


def validate_relation(src_id: str, tgt_id: str, rtype: str, entities: dict):
    """(src, tgt, type) 검증·교정. 반환 (src, tgt, type) 또는 None(무효).

    교정 규칙:
      1) ORG/PRODUCT → POLICY/GOV 의 implements → complies_with (의미 교정)
      2) 타입 규칙 위반이지만 방향을 뒤집으면 유효 → flip
      3) 그래도 무효 → mentions로 강등
    """
    st = (entities.get(src_id) or {}).get("type", "")
    tt = (entities.get(tgt_id) or {}).get("type", "")
    if rtype == "mentions" or rtype not in _RELATION_RULES:
        return (src_id, tgt_id, "mentions") if rtype == "mentions" else None
    src_ok, tgt_ok = _RELATION_RULES[rtype]
    # 규칙 1: 기업이 정책을 "implements" → 실제 의미는 준수
    if rtype == "implements" and st in (_ORG_TYPES | _PRODUCT_TYPES) and tt in (_POLICY_TYPES | _GOV_TYPES):
        return (src_id, tgt_id, "complies_with")
    if st in src_ok and tt in tgt_ok:
        return (src_id, tgt_id, rtype)
    # 규칙 2: 방향 flip으로 유효해지면 flip
    if tt in src_ok and st in tgt_ok:
        return (tgt_id, src_id, rtype)
    # 규칙 3: mentions 강등
    return (src_id, tgt_id, "mentions")


PROMPT_TEMPLATE = """당신은 대형로펌 경영전략팀을 위한 관계 추출 분석가입니다.

다음 시사점 카드 텍스트와 사전 정의된 엔티티 목록을 보고, **명확하게 본문에서 언급된 엔티티 간 관계**를 추출하세요.

[엔티티 목록 (id : 이름 : 타입)]
{entity_list}

[시사점 카드]
TAG: {tag}
TITLE: {title}

BODY:
{body}

ACTION:
{action}

[관계 타입]
- competes_with    : 경쟁 (제품·시장 충돌)
- partners_with    : 제휴·협력
- acquires         : 인수
- invests_in       : 투자
- regulates        : 규제·감독 (정부·정책 → 회사 방향)
- adopts           : 도입 (회사·로펌 → 제품·기술 방향)
- launches         : 출시·발표 (회사 → 제품)
- implements       : 정책 시행·의무 부과 (반드시 정책·정부 → 영향받는 회사·산업 방향)
- complies_with    : 준수·대응 (반드시 회사·로펌 → 법령·규제 방향. 예: 삼성전자 → EU AI Act)
- mentions         : 위 어디에도 안 맞지만 같이 언급됨 (보조)

[지시]
- 양쪽 엔티티가 위 목록에 모두 있을 때만 관계 추출
- 본문에서 명확히 추론 가능한 관계만 (추측 금지)
- 최대 8개 triple
- evidence는 본문에서 해당 관계를 설명하는 핵심 문구 (80~150자)
  · "왜 그런 관계인지"가 분석가에게 한눈에 보이도록 컨텍스트 포함
  · 단순히 "A와 B 경쟁" 보다는 "A의 Codex for Legal 진입으로 B의 시장 점유 잠식 우려" 같은 결과·메커니즘 포함
- 같은 사실을 양방향으로 중복 보고 금지 (예: A→B 경쟁이면 B→A 추가 X)
- 모호하면 빼라 (false positive보다 missing이 낫다)

JSON으로만 응답:
{{
  "relations": [
    {{"source": "<id>", "target": "<id>", "type": "<relation_type>", "evidence": "<구절>"}}
  ]
}}
"""


def load_entities():
    if not os.path.exists(ENTITIES_PATH):
        print(f"  [warn] {ENTITIES_PATH} not found", flush=True)
        return {}
    with open(ENTITIES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("entities") or {}


def load_strategy_history():
    if not os.path.exists(STRATEGY_HISTORY_PATH):
        return {}
    with open(STRATEGY_HISTORY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_enriched_news():
    """v5.1: enriched_news.json에서 article 단위 relations 필드 활용."""
    if not os.path.exists(ENRICHED_NEWS_PATH):
        return []
    try:
        with open(ENRICHED_NEWS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("items") or []
    except Exception as e:
        print(f"  [warn] enriched_news.json load failed: {e}", flush=True)
        return []


def _build_name_to_id_index(entities: dict):
    """v5.1: LLM이 자유롭게 출력한 엔티티 이름을 catalog ID로 매칭하기 위한 index.
    name·aliases를 모두 lowercase로 indexing.
    """
    name_to_id = {}
    for eid, rec in entities.items():
        # 정식 이름
        nm = (rec.get("name") or "").lower().strip()
        if nm and nm not in name_to_id:
            name_to_id[nm] = eid
        # 모든 alias
        for alias in rec.get("aliases") or []:
            al = alias.lower().strip()
            if al and al not in name_to_id:
                name_to_id[al] = eid
    return name_to_id


def _resolve_entity_name(name: str, name_to_id: dict):
    """LLM 출력 엔티티 이름을 catalog ID로 매칭.

    v7.2: 양방향 substring 매칭 제거 — "Meta"가 meta_ai/meta_fair 중 dict 순서에
    따라 아무 데나 붙는 오매핑의 구조적 원인이었음. 정확 매칭 + 괄호 제거 후
    정확 매칭만 허용 (예: "Claude (Anthropic)" → "claude"). 미매칭은 로그로 관찰.
    """
    if not name: return None
    n = name.lower().strip()
    if n in name_to_id:
        return name_to_id[n]
    # 괄호 부가 정보 제거 후 재시도: "gemini (google)" → "gemini"
    import re as _re
    n2 = _re.sub(r"\s*\([^)]*\)\s*", " ", n).strip()
    if n2 and n2 in name_to_id:
        return name_to_id[n2]
    return None


def extract_relations_from_articles(articles: list, entities: dict) -> list:
    """v5.1: enriched_news.json의 각 article에서 LLM이 추출한 relations 필드를
    catalog와 매칭해서 정식 triple 리스트로 변환.
    """
    name_to_id = _build_name_to_id_index(entities)
    rels = []
    unmatched_names = {}  # 디버깅용 — catalog에 없는 엔티티 이름 빈도
    # v7.2: 90일 이내 기사만 — 그래프가 "역대 누적"이 아니라 최신 구도를 반영하게
    cutoff = (datetime.now(KST) - timedelta(days=90)).date().isoformat()
    for art in articles:
        art_rels = art.get("relations") or []
        if not isinstance(art_rels, list): continue
        date = (art.get("date") or "")[:10]
        if date and date < cutoff:
            continue
        url = art.get("url", "")
        score = art.get("score", 0) or 0
        for r in art_rels:
            if not isinstance(r, dict): continue
            src_name = r.get("src") or ""
            tgt_name = r.get("tgt") or ""
            rtype = r.get("type") or ""
            ev = r.get("evidence") or ""
            if rtype not in RELATION_TYPES: continue
            s = _resolve_entity_name(src_name, name_to_id)
            t = _resolve_entity_name(tgt_name, name_to_id)
            if not s:
                unmatched_names[src_name] = unmatched_names.get(src_name, 0) + 1
            if not t:
                unmatched_names[tgt_name] = unmatched_names.get(tgt_name, 0) + 1
            if not s or not t or s == t: continue
            validated = validate_relation(s, t, rtype, entities)
            if not validated: continue
            s, t, rtype = validated
            rels.append({
                "source": s,
                "target": t,
                "type": rtype,
                "evidence": ev[:200],
                "source_type": "article",  # v5.1: article 본문 출처
                "trend_period": "",  # article은 period 없음
                "trend_key": date,
                "trend_tag": (art.get("title") or "")[:80],
                "weight": 1.0 + min(score / 50.0, 1.0),  # 점수 높은 article일수록 weight 증가 (1.0~2.0)
                "article_url": url,
            })
    if unmatched_names:
        top_unmatched = sorted(unmatched_names.items(), key=lambda x: -x[1])[:10]
        print(f"  [info] article relations에서 catalog 미매칭 상위 10:", flush=True)
        for nm, c in top_unmatched:
            print(f"    {c:>3}회  {nm}", flush=True)
    return rels


def build_entity_list_text(entities: dict, card_text: str) -> str:
    """카드 본문에 등장하는 엔티티만 prompt에 포함 (token 절약)."""
    text_lower = card_text.lower()
    candidates = []
    for eid, rec in entities.items():
        aliases = rec.get("aliases", [])
        for alias in aliases:
            if alias.lower() in text_lower:
                candidates.append(f"  {eid} : {rec['name']} : {rec['type']}")
                break
    return "\n".join(candidates) if candidates else "(매칭된 엔티티 없음)"


def extract_relations_from_card(card: dict, entities: dict, period: str, key: str) -> list:
    """단일 카드에서 관계 triple 추출."""
    tag = card.get("tag", "")
    title = card.get("title", "")
    body = card.get("body", "")
    action = card.get("action", "")
    card_text = " ".join([tag, title, body, action])

    # 본문에 매칭된 엔티티 2개 이상 있어야 의미 있음
    matched = []
    text_lower = card_text.lower()
    for eid, rec in entities.items():
        for alias in rec.get("aliases", []):
            if alias.lower() in text_lower:
                matched.append(eid)
                break
    if len(matched) < 2:
        return []

    entity_list_text = build_entity_list_text(entities, card_text)
    prompt = PROMPT_TEMPLATE.format(
        entity_list=entity_list_text,
        tag=tag, title=title, body=body[:800], action=action[:400],
    )

    try:
        result = call_llm_json(prompt, max_tokens=1500, temperature=0.2)
    except Exception as e:
        print(f"    [warn] LLM call failed: {e}", flush=True)
        return []
    if not isinstance(result, dict):
        return []

    rels = []
    for r in (result.get("relations") or []):
        if not isinstance(r, dict):
            continue
        s = r.get("source") or ""
        t = r.get("target") or ""
        rtype = r.get("type") or ""
        ev = r.get("evidence") or ""
        if s not in entities or t not in entities:
            continue
        if rtype not in RELATION_TYPES:
            continue
        if s == t:
            continue
        validated = validate_relation(s, t, rtype, entities)
        if not validated:
            continue
        s, t, rtype = validated
        rels.append({
            "source": s,
            "target": t,
            "type": rtype,
            "evidence": ev[:160],  # v5.0: 80자 → 160자 (관계 맥락 더 풍부하게)
            "source_type": "trend",  # v5.0: 'trend' | 'paper' (frontend 토글용)
            "trend_period": period,
            "trend_key": key,
            "trend_tag": tag[:80],
            "weight": 1.0,
        })
    return rels


def main():
    print(f"[start] relation_extractor @ {datetime.now(KST).isoformat()}", flush=True)
    entities = load_entities()
    if not entities:
        print("  [skip] no entities", flush=True)
        return
    print(f"  loaded {len(entities)} entities", flush=True)
    history = load_strategy_history()

    # v5.1: enriched_news.json의 article 단위 relations를 가장 먼저 ingest
    articles = load_enriched_news()
    print(f"  loaded {len(articles)} enriched articles", flush=True)
    article_rels = extract_relations_from_articles(articles, entities)
    print(f"  article-level relations: {len(article_rels)}", flush=True)

    # 최근 trend만 처리 (비용 절약)
    # daily는 최근 7일, weekly는 최근 4주, monthly는 최근 3개월
    today = datetime.now(KST).date()
    daily_cutoff = (today - timedelta(days=7)).isoformat()

    all_relations = list(article_rels)  # v5.1: article relations 먼저 추가
    card_count = 0
    skip_count = 0

    # v6.15.2 hotfix: strategy_history entry가 v6.15부터 dict({summary, cards, _summary_addons}) 포맷.
    #   옛 list 포맷도 지원하기 위해 cards 추출 헬퍼 사용.
    def _extract_cards(entry):
        if isinstance(entry, list):
            return entry  # 옛 포맷
        if isinstance(entry, dict):
            cards = entry.get("cards")
            return cards if isinstance(cards, list) else []
        return []

    # ===== v6.18.2 (2026-07-08): 카드별 순차 호출 → 병렬 =====
    # 빌드 #193에서 이 단계만 1h 43m (전체 3h13m의 절반) — enrich와 동일한
    # '순차 CLI 호출' 병목. 잡 목록을 모아 4워커 스레드 병렬 처리 (subprocess I/O
    # 바운드라 안전). 항목별 예외 격리 포함. RELATION_CONCURRENCY로 조정.
    jobs = []  # (card, period, key)

    # daily — 최근 7일만
    for key in sorted((history.get("daily") or {}).keys(), reverse=True):
        if key < daily_cutoff:
            continue
        for c in _extract_cards(history["daily"][key]):
            jobs.append((c, "daily", key))

    # weekly — 최근 4주만
    for key in sorted((history.get("weekly") or {}).keys(), reverse=True)[:4]:
        for c in _extract_cards(history["weekly"][key]):
            jobs.append((c, "weekly", key))

    # monthly — 최근 3개월만
    for key in sorted((history.get("monthly") or {}).keys(), reverse=True)[:3]:
        for c in _extract_cards(history["monthly"][key]):
            jobs.append((c, "monthly", key))

    from concurrent.futures import ThreadPoolExecutor
    workers = max(1, int(os.environ.get("RELATION_CONCURRENCY", "4")))
    if workers > 1 and len(jobs) > 1:
        print(f"  [parallel] {len(jobs)} cards · {workers} workers (RELATION_CONCURRENCY)", flush=True)

    def _safe_extract(job):
        c, period, key = job
        try:
            return extract_relations_from_card(c, entities, period, key)
        except Exception as exc:
            print(f"    [relation 실패 — skip] {str(c.get('tag', ''))[:30]} · "
                  f"{type(exc).__name__}: {str(exc)[:80]}", flush=True)
            return []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for (c, period, key), rels in zip(jobs, pool.map(_safe_extract, jobs)):
            card_count += 1
            if rels:
                all_relations.extend(rels)
                print(f"    {period}/{key} [{c.get('tag', '')[:30]}] → {len(rels)} relations", flush=True)
            else:
                skip_count += 1

    print(f"  processed {card_count} cards ({skip_count} no-relation)", flush=True)
    print(f"  total relations: {len(all_relations)}", flush=True)

    # v5.0: 중복 제거 (대칭 관계는 방향 무관)
    # 대칭 타입: competes_with, partners_with, mentions → (min, max, type)
    # 비대칭 타입: acquires/invests_in/regulates/adopts/launches/implements → (s, t, type)
    SYMMETRIC_TYPES = {"competes_with", "partners_with", "mentions"}  # complies_with는 비대칭
    seen = {}
    unique = []
    for r in all_relations:
        if r["type"] in SYMMETRIC_TYPES:
            a, b = sorted([r["source"], r["target"]])
            sig = (a, b, r["type"])
        else:
            sig = (r["source"], r["target"], r["type"])
        if sig in seen:
            # weight 증가 + evidence 누적 (더 풍부한 게 있으면 교체)
            existing = unique[seen[sig]]
            existing["weight"] += 0.5
            if len(r.get("evidence", "")) > len(existing.get("evidence", "")):
                existing["evidence"] = r["evidence"]
            continue
        seen[sig] = len(unique)
        unique.append(r)
    print(f"  unique relations: {len(unique)} (dedup -{len(all_relations) - len(unique)})", flush=True)

    # 타입별 분포
    type_count = {}
    for r in unique:
        type_count[r["type"]] = type_count.get(r["type"], 0) + 1
    print("  by type:")
    for t in RELATION_TYPES:
        if type_count.get(t):
            print(f"    {t}: {type_count[t]}")

    payload = {
        "generated_at": datetime.now(KST).isoformat(),
        "total_relations": len(unique),
        "relations": unique,
    }
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[done] wrote {OUTPUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
