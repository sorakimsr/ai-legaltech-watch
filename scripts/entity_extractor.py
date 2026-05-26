"""
Phase 2a — 엔티티 휴리스틱 추출 (LLM 없이).

대형로펌 경영전략팀 페르소나가 가장 자주 추적할 엔티티 카탈로그를 정의하고,
각 article·trend·논문 본문에서 매칭되는 엔티티를 자동 식별.

산출물: data/entities.json
{
  "entities": {
    "openai": {
      "name": "OpenAI",
      "type": "ai_company",
      "aliases": ["OpenAI", "openai", "오픈AI", "오픈에이아이"],
      "mentioned_articles": ["url1", "url2", ...],
      "mentioned_trends": [{"period": "daily", "key": "2026-05-26", "tag": "..."}],
      "mentioned_papers": [...],
      "first_seen": "2026-05-26",
      "last_seen": "2026-05-26",
      "total_mentions": 142,
      "avg_score": 67.5
    },
    ...
  },
  "generated_at": "2026-05-26T...",
  "total_entities": 73
}
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import _normalize_text_for_match  # type: ignore


KST = timezone(timedelta(hours=9))
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS_PATH = os.path.join(ROOT_DIR, "data", "news.json")
STRATEGY_HISTORY_PATH = os.path.join(ROOT_DIR, "data", "strategy_history.json")
PAPER_TRENDS_PATH = os.path.join(ROOT_DIR, "data", "paper_trends_history.json")
OUTPUT_PATH = os.path.join(ROOT_DIR, "data", "entities.json")


# ============================================================================
# 엔티티 카탈로그
# 대형로펌 경영전략팀이 추적할 가치 있는 엔티티만 (잡음 제외).
# 각 엔티티: id, name, type, aliases[]
# ============================================================================

ENTITY_CATALOG = [
    # ─── AI 회사 (글로벌 빅테크 + Foundation Model) ───
    ("openai", "OpenAI", "ai_company", ["openai", "오픈ai", "오픈에이아이", "샘 알트만", "sam altman"]),
    ("anthropic", "Anthropic", "ai_company", ["anthropic", "claude", "클로드", "다리오 아모데이", "dario amodei"]),
    ("google_ai", "Google AI", "ai_company", ["google deepmind", "google ai", "gemini", "제미니", "구글 ai", "deepmind"]),
    ("meta_ai", "Meta AI", "ai_company", ["meta ai", "meta llama", "llama", "라마", "fair", "메타 ai"]),
    ("microsoft_ai", "Microsoft AI", "ai_company", ["microsoft ai", "copilot", "코파일럿", "microsoft copilot"]),
    ("nvidia", "NVIDIA", "ai_company", ["nvidia", "엔비디아", "젠슨 황", "jensen huang"]),
    ("mistral", "Mistral AI", "ai_company", ["mistral", "미스트랄"]),
    ("cohere", "Cohere", "ai_company", ["cohere", "코히어"]),
    ("perplexity", "Perplexity", "ai_company", ["perplexity", "퍼플렉시티"]),
    ("xai", "xAI", "ai_company", ["xai", "grok", "그록", "일론 머스크 ai"]),
    ("apple_ai", "Apple Intelligence", "ai_company", ["apple intelligence", "애플 인텔리전스", "apple ai"]),
    ("deepseek", "DeepSeek", "ai_company", ["deepseek", "딥시크"]),
    ("qwen", "Qwen (Alibaba)", "ai_company", ["qwen", "퀀", "큐원", "알리바바 qwen"]),

    # ─── 리걸테크 회사 ───
    ("harvey", "Harvey", "legaltech_company", ["harvey", "하비", "harvey ai"]),
    ("legora", "Legora", "legaltech_company", ["legora", "레고라"]),
    ("ironclad", "Ironclad", "legaltech_company", ["ironclad", "아이언클래드"]),
    ("spellbook", "Spellbook", "legaltech_company", ["spellbook", "스펠북"]),
    ("robin_ai", "Robin AI", "legaltech_company", ["robin ai", "로빈 ai"]),
    ("everlaw", "Everlaw", "legaltech_company", ["everlaw"]),
    ("casetext", "Casetext", "legaltech_company", ["casetext"]),
    ("mike_legal", "Mike Legal", "legaltech_company", ["mike legal", "mike oss"]),
    ("evenup", "EvenUp", "legaltech_company", ["evenup"]),
    ("spotdraft", "SpotDraft", "legaltech_company", ["spotdraft"]),
    ("bhsn", "BHSN", "legaltech_company", ["bhsn", "비에이치에스엔"]),
    ("loanc", "로앤컴퍼니", "legaltech_company", ["로앤컴퍼니", "로앤컴", "lawandcompany"]),
    ("lawgood", "로앤굿", "legaltech_company", ["로앤굿"]),
    ("casenote", "케이스노트", "legaltech_company", ["케이스노트", "casenote"]),

    # ─── 한국 7대 로펌 ───
    ("law_gwangjang", "법무법인 광장", "korean_law_firm", ["법무법인 광장", "광장 변호사", "광장 tech", "광장 ai"]),
    ("law_kimchang", "김앤장 법률사무소", "korean_law_firm", ["김앤장", "kim & chang"]),
    ("law_taepyung", "법무법인 태평양", "korean_law_firm", ["법무법인 태평양", "태평양 변호사"]),
    ("law_sejong", "법무법인 세종", "korean_law_firm", ["법무법인 세종", "세종 변호사"]),
    ("law_yulchon", "법무법인 율촌", "korean_law_firm", ["법무법인 율촌", "율촌 변호사"]),
    ("law_jipyong", "법무법인 지평", "korean_law_firm", ["법무법인 지평", "지평 변호사"]),
    ("law_hwawoo", "법무법인 화우", "korean_law_firm", ["법무법인 화우", "화우 변호사"]),

    # ─── 글로벌 로펌 (AI 도입 관련) ───
    ("freshfields", "Freshfields", "global_law_firm", ["freshfields"]),
    ("dla_piper", "DLA Piper", "global_law_firm", ["dla piper"]),
    ("clifford_chance", "Clifford Chance", "global_law_firm", ["clifford chance"]),
    ("allen_overy", "Allen & Overy", "global_law_firm", ["allen & overy", "a&o shearman"]),
    ("cooley", "Cooley", "global_law_firm", ["cooley"]),

    # ─── 한국 금융·제조 대기업 ───
    ("kb_finance", "KB금융그룹", "korean_finance", ["kb금융", "kb금융그룹", "kb국민은행"]),
    ("shinhan_finance", "신한금융그룹", "korean_finance", ["신한금융", "신한은행"]),
    ("hana_finance", "하나금융그룹", "korean_finance", ["하나금융", "하나은행"]),
    ("woori_finance", "우리금융그룹", "korean_finance", ["우리금융", "우리은행"]),
    ("ibk", "기업은행 (IBK)", "korean_finance", ["기업은행", "ibk", "ibk genai"]),
    ("eximbank", "수출입은행", "korean_finance", ["수출입은행", "kexim"]),
    ("lg_ensol", "LG에너지솔루션", "korean_manufacturing", ["lg에너지솔루션", "lg엔솔", "lg energy solution"]),
    ("samsung_sdi", "삼성SDI", "korean_manufacturing", ["삼성sdi", "samsung sdi"]),
    ("sk_innovation", "SK이노베이션", "korean_manufacturing", ["sk이노베이션", "sk on", "sk온"]),

    # ─── 정부 부처 / 규제 기관 ───
    ("ministry_industry", "산업통상자원부", "kr_government", ["산업부", "산업통상자원부"]),
    ("ministry_science", "과학기술정보통신부", "kr_government", ["과기정통부", "과학기술정보통신부"]),
    ("ministry_sme", "중소벤처기업부", "kr_government", ["중기부", "중소벤처기업부"]),
    ("fsc", "금융위원회", "kr_government", ["금융위", "금융위원회"]),
    ("fss", "금융감독원", "kr_government", ["금감원", "금융감독원"]),
    ("ftc", "공정거래위원회", "kr_government", ["공정위", "공정거래위원회"]),
    ("pipc", "개인정보보호위원회", "kr_government", ["개인정보보호위원회", "개인정보위", "pipa"]),
    ("kisa", "한국인터넷진흥원", "kr_government", ["kisa", "한국인터넷진흥원"]),

    # ─── 정책·법안 ───
    ("ai_basic_law", "AI 기본법 (한국)", "policy", ["ai 기본법", "ai 기본법안"]),
    ("eu_ai_act", "EU AI Act", "policy", ["eu ai act", "eu ai 법", "유럽 ai 법"]),
    ("ai_guidelines", "AI 가이드라인 (정부)", "policy", ["ai 가이드라인", "ai 윤리 가이드라인"]),
    ("data_sovereignty", "디지털·데이터 주권", "policy", ["디지털 주권", "데이터 주권", "sovereign ai"]),
    ("on_premise_ai", "온프레미스 AI 요건", "policy", ["온프레미스 ai", "on-premise ai", "망분리"]),

    # ─── 기술·플랫폼 ───
    ("rag", "RAG (Retrieval-Augmented Generation)", "tech", ["rag", "retrieval augmented generation", "검색 증강 생성"]),
    ("mcp", "Model Context Protocol", "tech", ["mcp", "model context protocol"]),
    ("agent_ai", "AI 에이전트", "tech", ["ai 에이전트", "ai agent", "multi-agent", "multi agent", "에이전트 ai"]),
    ("digital_twin", "디지털 트윈", "tech", ["digital twin", "디지털 트윈", "디지털트윈"]),
    ("codex_for_legal", "Codex for Legal (OpenAI)", "ai_product", ["codex for legal", "openai codex legal"]),
    ("claude_for_legal", "Claude for Legal (Anthropic)", "ai_product", ["claude for legal"]),
    ("chatgpt", "ChatGPT", "ai_product", ["chatgpt", "챗gpt"]),
    ("claude", "Claude (Anthropic)", "ai_product", ["claude opus", "claude sonnet", "claude haiku", "claude 3", "claude 4"]),
    ("mythos", "Claude Mythos", "ai_product", ["mythos", "claude mythos"]),
    ("gemma", "Gemma (Google)", "ai_product", ["gemma"]),

    # ─── 벤치마크 ───
    ("mmlu", "MMLU", "benchmark", ["mmlu"]),
    ("humaneval", "HumanEval", "benchmark", ["humaneval"]),
    ("gpqa", "GPQA", "benchmark", ["gpqa"]),
    ("swe_bench", "SWE-bench", "benchmark", ["swe-bench", "swe bench", "swebench"]),
    ("arc_agi", "ARC-AGI", "benchmark", ["arc-agi", "arc agi", "arcagi"]),
    ("chatbot_arena", "Chatbot Arena (LMSYS)", "benchmark", ["chatbot arena", "lmsys"]),

    # ─── M.AX·정책 이니셔티브 ───
    ("max_policy", "M.AX 정책 (산업부)", "policy", ["m.ax", "m·ax", "max 정책"]),
]


def _make_alias_text(text: str) -> str:
    """매칭용 정규화 — common._normalize_text_for_match와 동일."""
    return _normalize_text_for_match(text or "")


def _entity_matches(entity_aliases: list, normalized_text: str) -> bool:
    """엔티티 alias 중 하나라도 텍스트에 포함되면 True."""
    for alias in entity_aliases:
        a = alias.lower()
        if a in normalized_text:
            return True
    return False


def _empty_entity_record(eid: str, name: str, etype: str, aliases: list) -> dict:
    return {
        "id": eid,
        "name": name,
        "type": etype,
        "aliases": aliases,
        "mentioned_articles": [],
        "mentioned_trends": [],
        "mentioned_papers": [],
        "first_seen": None,
        "last_seen": None,
        "total_mentions": 0,
        "score_sum": 0.0,
    }


def extract_from_articles(items: list, records: dict):
    """각 article의 title+summary에서 엔티티 매칭 → records 누적."""
    for it in items:
        text = _make_alias_text((it.get("title") or "") + " " + (it.get("summary") or ""))
        if not text:
            continue
        url = it.get("url", "")
        date = (it.get("date") or "")[:10]
        score = it.get("score", 0) or 0

        for eid, rec in records.items():
            if _entity_matches(rec["aliases"], text):
                rec["mentioned_articles"].append({
                    "url": url,
                    "title": (it.get("title") or "")[:120],
                    "date": date,
                    "source": it.get("source", ""),
                    "score": score,
                })
                rec["total_mentions"] += 1
                rec["score_sum"] += score
                if not rec["first_seen"] or (date and date < rec["first_seen"]):
                    rec["first_seen"] = date
                if not rec["last_seen"] or (date and date > rec["last_seen"]):
                    rec["last_seen"] = date


def extract_from_strategy(strategy_history: dict, records: dict):
    """시사점 trend 카드 (daily/weekly/monthly)에서 엔티티 매칭."""
    if not isinstance(strategy_history, dict):
        return
    for period in ("daily", "weekly", "monthly"):
        period_data = strategy_history.get(period) or {}
        for key, cards in period_data.items():
            if not isinstance(cards, list):
                continue
            for card in cards:
                if not isinstance(card, dict):
                    continue
                text = _make_alias_text(
                    (card.get("title") or "") + " " + (card.get("body") or "") + " " + (card.get("action") or "")
                )
                if not text:
                    continue
                tag = card.get("tag") or ""
                for eid, rec in records.items():
                    if _entity_matches(rec["aliases"], text):
                        rec["mentioned_trends"].append({
                            "period": period,
                            "key": key,
                            "tag": tag[:100],
                            "title": (card.get("title") or "")[:100],
                        })


def extract_from_papers(paper_trends_history: dict, records: dict):
    """논문 trend (narrative·hot_topics·key_techniques)에서 엔티티 매칭."""
    if not isinstance(paper_trends_history, dict):
        return
    for period in ("daily", "weekly", "monthly"):
        period_data = paper_trends_history.get(period) or {}
        for key, entry in period_data.items():
            if not isinstance(entry, dict):
                continue
            text_parts = [entry.get("narrative", "")]
            for ht in entry.get("hot_topics") or []:
                if isinstance(ht, dict):
                    text_parts.append(ht.get("topic", ""))
                    text_parts.append(ht.get("description", ""))
            for kt in entry.get("key_techniques") or []:
                if isinstance(kt, dict):
                    text_parts.append(kt.get("technique", ""))
                    text_parts.append(kt.get("description", ""))
            for ai in entry.get("actionable_insights") or []:
                if isinstance(ai, str):
                    text_parts.append(ai)
            full_text = _make_alias_text(" ".join(text_parts))
            if not full_text:
                continue
            for eid, rec in records.items():
                if _entity_matches(rec["aliases"], full_text):
                    rec["mentioned_papers"].append({
                        "period": period,
                        "key": key,
                        "paper_count": entry.get("paper_count", 0),
                    })


def main():
    print(f"[start] entity_extractor @ {datetime.now(KST).isoformat()}", flush=True)

    # 1. 데이터 로드
    items = []
    strategy_history = {}
    paper_trends_history = {}
    try:
        with open(NEWS_PATH, "r", encoding="utf-8") as f:
            news = json.load(f)
        items = news.get("items", [])
        print(f"  loaded {len(items)} articles from news.json", flush=True)
    except Exception as e:
        print(f"  [warn] news.json load failed: {e}", flush=True)
    try:
        with open(STRATEGY_HISTORY_PATH, "r", encoding="utf-8") as f:
            strategy_history = json.load(f)
        d_count = sum(len(v) for v in strategy_history.values() if isinstance(v, dict))
        print(f"  loaded strategy_history ({d_count} entries)", flush=True)
    except Exception as e:
        print(f"  [warn] strategy_history.json load failed: {e}", flush=True)
    try:
        with open(PAPER_TRENDS_PATH, "r", encoding="utf-8") as f:
            paper_trends_history = json.load(f)
        p_count = sum(len(v) for v in paper_trends_history.values() if isinstance(v, dict))
        print(f"  loaded paper_trends_history ({p_count} entries)", flush=True)
    except Exception as e:
        print(f"  [warn] paper_trends_history.json load failed: {e}", flush=True)

    # 2. 엔티티 records 초기화
    records = {}
    for eid, name, etype, aliases in ENTITY_CATALOG:
        records[eid] = _empty_entity_record(eid, name, etype, aliases)

    # 3. 매칭 수행
    extract_from_articles(items, records)
    extract_from_strategy(strategy_history, records)
    extract_from_papers(paper_trends_history, records)

    # 4. avg_score 계산 + 정렬용 메트릭
    for eid, rec in records.items():
        if rec["total_mentions"] > 0:
            rec["avg_score"] = round(rec["score_sum"] / rec["total_mentions"], 1)
        else:
            rec["avg_score"] = 0
        # mentioned_articles는 최근 30개로 제한 (날짜 내림차순)
        rec["mentioned_articles"].sort(key=lambda x: x.get("date", ""), reverse=True)
        rec["mentioned_articles"] = rec["mentioned_articles"][:30]
        # mentioned_trends는 최근 20개로 제한
        rec["mentioned_trends"] = rec["mentioned_trends"][:20]
        rec["mentioned_papers"] = rec["mentioned_papers"][:15]
        # score_sum은 산출용이라 출력에서는 제거
        del rec["score_sum"]

    # 5. mention 0 엔티티는 제외, 나머지만 출력
    active = {eid: rec for eid, rec in records.items() if rec["total_mentions"] > 0}
    print(f"  active entities: {len(active)} / total catalog: {len(records)}", flush=True)

    # 6. 타입별 카운트
    type_count = defaultdict(int)
    for rec in active.values():
        type_count[rec["type"]] += 1
    print("  by type:")
    for t, c in sorted(type_count.items(), key=lambda x: -x[1]):
        print(f"    {t}: {c}")

    # 7. 상위 10개 출력 (debug)
    top10 = sorted(active.values(), key=lambda x: -x["total_mentions"])[:10]
    print("  top10 mentioned:")
    for rec in top10:
        print(f"    {rec['name']:<35} ({rec['type']:<20}) mentions={rec['total_mentions']:>4} avg_score={rec['avg_score']}")

    # 8. 저장
    payload = {
        "generated_at": datetime.now(KST).isoformat(),
        "total_entities": len(active),
        "entities": active,
    }
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[done] wrote {OUTPUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
