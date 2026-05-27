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
    """v5.1: LLM 출력 엔티티 이름을 catalog ID로 매칭. 정확 매칭 우선, 실패 시 substring 시도."""
    if not name: return None
    n = name.lower().strip()
    if n in name_to_id:
        return name_to_id[n]
    # substring 매칭 (LLM이 "OpenAI Codex" 같이 풀네임 출력한 경우)
    for k, eid in name_to_id.items():
        if len(k) >= 3 and (k in n or n in k):
            return eid
    return None


def extract_relations_from_articles(articles: list, entities: dict) -> list:
    """v5.1: enriched_news.json의 각 article에서 LLM이 추출한 relations 필드를
    catalog와 매칭해서 정식 triple 리스트로 변환.
    """
    name_to_id = _build_name_to_id_index(entities)
    rels = []
    unmatched_names = {}  # 디버깅용 — catalog에 없는 엔티티 이름 빈도
    for art in articles:
        art_rels = art.get("relations") or []
        if not isinstance(art_rels, list): continue
        date = (art.get("date") or "")[:10]
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

    # === daily — 최근 7일만 ===
    for key in sorted((history.get("daily") or {}).keys(), reverse=True):
        if key < daily_cutoff:
            continue
        cards = _extract_cards(history["daily"][key])
        if not cards:
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
        cards = _extract_cards(history["weekly"][key])
        if not cards:
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
        cards = _extract_cards(history["monthly"][key])
        if not cards:
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

    # v5.0: 중복 제거 (대칭 관계는 방향 무관)
    # 대칭 타입: competes_with, partners_with, mentions → (min, max, type)
    # 비대칭 타입: acquires/invests_in/regulates/adopts/launches/implements → (s, t, type)
    SYMMETRIC_TYPES = {"competes_with", "partners_with", "mentions"}
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
