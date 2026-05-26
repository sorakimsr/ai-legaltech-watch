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
OUTPUT_PATH = os.path.join(ROOT_DIR, "data", "relations.json")


RELATION_TYPES = [
    "competes_with", "partners_with", "acquires", "invests_in",
    "regulates", "adopts", "launches", "implements", "mentions",
]


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
- regulates        : 규제·감독 (정부 → 회사 방향)
- adopts           : 도입 (회사·로펌 → 제품·기술 방향)
- launches         : 출시·발표 (회사 → 제품)
- implements       : 정책 구현 (정책 → 영향받는 회사·산업)
- mentions         : 위 어디에도 안 맞지만 같이 언급됨 (보조)

[지시]
- 양쪽 엔티티가 위 목록에 모두 있을 때만 관계 추출
- 본문에서 명확히 추론 가능한 관계만 (추측 금지)
- 최대 8개 triple
- evidence는 본문 중 해당 구절 (40자 이내)
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
        rels.append({
            "source": s,
            "target": t,
            "type": rtype,
            "evidence": ev[:120],
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

    # 최근 trend만 처리 (비용 절약)
    # daily는 최근 7일, weekly는 최근 4주, monthly는 최근 3개월
    today = datetime.now(KST).date()
    daily_cutoff = (today - timedelta(days=7)).isoformat()

    all_relations = []
    card_count = 0
    skip_count = 0

    # === daily — 최근 7일만 ===
    for key in sorted((history.get("daily") or {}).keys(), reverse=True):
        if key < daily_cutoff:
            continue
        cards = history["daily"][key]
        if not isinstance(cards, list):
            continue
        for c in cards:
            card_count += 1
            rels = extract_relations_from_card(c, entities, "daily", key)
            if rels:
                all_relations.extend(rels)
                print(f"    daily/{key} [{c.get('tag','')[:30]}] → {len(rels)} relations", flush=True)
            else:
                skip_count += 1
            time.sleep(0.3)  # API rate limit 친화

    # === weekly — 최근 4주만 ===
    weekly_keys = sorted((history.get("weekly") or {}).keys(), reverse=True)[:4]
    for key in weekly_keys:
        cards = history["weekly"][key]
        if not isinstance(cards, list):
            continue
        for c in cards:
            card_count += 1
            rels = extract_relations_from_card(c, entities, "weekly", key)
            if rels:
                all_relations.extend(rels)
                print(f"    weekly/{key} [{c.get('tag','')[:30]}] → {len(rels)} relations", flush=True)
            else:
                skip_count += 1
            time.sleep(0.3)

    # === monthly — 최근 3개월만 ===
    monthly_keys = sorted((history.get("monthly") or {}).keys(), reverse=True)[:3]
    for key in monthly_keys:
        cards = history["monthly"][key]
        if not isinstance(cards, list):
            continue
        for c in cards:
            card_count += 1
            rels = extract_relations_from_card(c, entities, "monthly", key)
            if rels:
                all_relations.extend(rels)
                print(f"    monthly/{key} [{c.get('tag','')[:30]}] → {len(rels)} relations", flush=True)
            else:
                skip_count += 1
            time.sleep(0.3)

    print(f"  processed {card_count} cards ({skip_count} no-relation)", flush=True)
    print(f"  total relations: {len(all_relations)}", flush=True)

    # 중복 제거 (같은 source-target-type 조합)
    seen = set()
    unique = []
    for r in all_relations:
        sig = (r["source"], r["target"], r["type"])
        if sig in seen:
            # weight 증가
            for u in unique:
                if (u["source"], u["target"], u["type"]) == sig:
                    u["weight"] += 0.5
                    break
            continue
        seen.add(sig)
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
