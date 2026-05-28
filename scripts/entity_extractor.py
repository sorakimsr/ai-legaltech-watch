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
import re
import sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from functools import lru_cache

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
    # v5.0: claude alias 제거 — 별도 ai_product 노드 'claude'로 분리
    ("anthropic", "Anthropic", "ai_company", ["anthropic", "앤트로픽", "다리오 아모데이", "dario amodei"]),
    # v5.0: Gemini는 별도 ai_product 노드로 분리 (Google AI는 회사 단위 유지)
    ("google_ai", "Google AI", "ai_company", ["google deepmind", "google ai", "구글 ai", "deepmind", "alphabet ai"]),
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
    # v5.0: 한국 IT·전자 대기업
    ("samsung_electronics", "삼성전자", "korean_manufacturing", ["삼성전자", "samsung electronics", "samsung dx", "삼성 dx부문", "삼성 mx"]),
    ("lg_electronics", "LG전자", "korean_manufacturing", ["lg전자", "lg electronics"]),
    ("lg_chem", "LG화학", "korean_manufacturing", ["lg화학", "lg chem"]),
    ("sk_hynix", "SK하이닉스", "korean_manufacturing", ["sk하이닉스", "sk hynix"]),
    ("naver", "네이버", "korean_manufacturing", ["네이버", "naver", "naver cloud", "네이버 클라우드", "하이퍼클로바", "hyperclova"]),
    ("kakao", "카카오", "korean_manufacturing", ["카카오", "kakao", "kakao brain", "카카오브레인"]),
    ("krafton", "크래프톤", "korean_manufacturing", ["크래프톤", "krafton"]),

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
    # v5.0: Claude를 회사 alias가 아닌 별도 제품 노드로
    ("claude", "Claude (Anthropic)", "ai_product", ["claude", "클로드", "claude opus", "claude sonnet", "claude haiku", "claude 3", "claude 4"]),
    ("mythos", "Claude Mythos", "ai_product", ["mythos", "claude mythos"]),
    ("gemma", "Gemma (Google)", "ai_product", ["gemma"]),
    # v5.0: Gemini 별도 ai_product 노드 (지식그래프에서 별도 노드로 표시)
    ("gemini", "Gemini (Google)", "ai_product", ["gemini", "제미니", "gemini pro", "gemini ultra", "gemini 2", "gemini nano"]),
    ("llama", "Llama (Meta)", "ai_product", ["llama", "라마", "llama 3", "llama 4"]),
    ("copilot", "Copilot (Microsoft)", "ai_product", ["copilot", "코파일럿", "github copilot", "m365 copilot"]),
    # v5.0: 한국 AI 제품
    ("hyperclova", "HyperCLOVA X (Naver)", "ai_product", ["하이퍼클로바", "hyperclova", "clova x", "클로바 x"]),
    ("kanana", "Kanana (Kakao)", "ai_product", ["kanana", "카나나"]),

    # ─── v5.2: 학술 기관 (논문 NER 강화용) ───
    ("stanford", "Stanford University", "academic_inst", ["stanford", "스탠퍼드", "stanford ai lab", "stanford hai"]),
    ("mit_csail", "MIT (CSAIL)", "academic_inst", ["mit csail", "mit ai", "mit lcs", "massachusetts institute of technology"]),
    ("cmu", "Carnegie Mellon University", "academic_inst", ["carnegie mellon", "cmu", "cmu ai", "lti cmu"]),
    ("berkeley", "UC Berkeley", "academic_inst", ["uc berkeley", "berkeley ai", "bair", "berkeley artificial intelligence"]),
    ("oxford_ai", "Oxford University", "academic_inst", ["oxford university", "university of oxford", "oxford ai"]),
    ("cambridge_ai", "Cambridge University", "academic_inst", ["cambridge university", "university of cambridge"]),
    ("eth_zurich", "ETH Zürich", "academic_inst", ["eth zurich", "eth zürich", "eth ai"]),
    ("tsinghua", "Tsinghua University", "academic_inst", ["tsinghua", "tsinghua university", "칭화대"]),
    ("peking_uni", "Peking University", "academic_inst", ["peking university", "pku", "베이징대"]),
    ("nanyang_ntu", "NTU Singapore", "academic_inst", ["nanyang technological university", "ntu singapore"]),
    ("nus", "NUS Singapore", "academic_inst", ["national university of singapore", "nus"]),
    ("kaist", "KAIST", "academic_inst", ["kaist", "한국과학기술원"]),
    ("snu", "Seoul National University", "academic_inst", ["seoul national university", "서울대학교", "서울대"]),
    ("postech", "POSTECH", "academic_inst", ["postech", "포스텍", "포항공대"]),
    ("yonsei", "Yonsei University", "academic_inst", ["yonsei university", "연세대학교", "연세대"]),
    ("korea_uni", "Korea University", "academic_inst", ["korea university", "고려대학교", "고려대"]),
    # ─── v5.2: 산업 연구소 (별도 노드 — google_ai/meta_ai에서 분리) ───
    ("deepmind", "Google DeepMind", "academic_inst", ["google deepmind", "deepmind research"]),
    ("meta_fair", "Meta FAIR", "academic_inst", ["meta fair", "fair labs", "facebook ai research"]),
    ("ms_research", "Microsoft Research", "academic_inst", ["microsoft research", "msr"]),
    ("apple_ml", "Apple ML Research", "academic_inst", ["apple ml", "apple machine learning research"]),
    ("nvidia_research", "NVIDIA Research", "academic_inst", ["nvidia research"]),
    ("ibm_research", "IBM Research", "academic_inst", ["ibm research"]),
    ("allen_ai", "Allen AI (AI2)", "academic_inst", ["allen institute for ai", "allen ai", "ai2"]),
    ("hf_research", "Hugging Face", "academic_inst", ["hugging face", "huggingface"]),
    ("salesforce_ai", "Salesforce AI Research", "academic_inst", ["salesforce ai", "salesforce research"]),
    # ─── v5.2: arXiv Subjects 태그 ───
    ("arxiv_cs_ai", "cs.AI (Artificial Intelligence)", "tech", ["cs.ai"]),
    ("arxiv_cs_cl", "cs.CL (Computation and Language)", "tech", ["cs.cl"]),
    ("arxiv_cs_lg", "cs.LG (Machine Learning)", "tech", ["cs.lg"]),
    ("arxiv_cs_cv", "cs.CV (Computer Vision)", "tech", ["cs.cv"]),
    ("arxiv_cs_ne", "cs.NE (Neural and Evolutionary Computing)", "tech", ["cs.ne"]),
    ("arxiv_cs_ro", "cs.RO (Robotics)", "tech", ["cs.ro"]),
    ("arxiv_cs_cr", "cs.CR (Cryptography and Security)", "tech", ["cs.cr"]),
    ("arxiv_cs_ir", "cs.IR (Information Retrieval)", "tech", ["cs.ir"]),
    ("arxiv_cs_ma", "cs.MA (Multiagent Systems)", "tech", ["cs.ma"]),
    ("arxiv_cs_se", "cs.SE (Software Engineering)", "tech", ["cs.se"]),
    ("arxiv_stat_ml", "stat.ML (Machine Learning - Statistics)", "tech", ["stat.ml"]),
    # ─── v5.2: 핵심 기법·아키텍처 ───
    ("moe", "MoE (Mixture of Experts)", "tech", ["mixture of experts", "moe architecture", "sparse moe"]),
    ("cot", "Chain-of-Thought", "tech", ["chain of thought", "chain-of-thought", "cot reasoning"]),
    ("tot", "Tree of Thoughts", "tech", ["tree of thoughts", "tree-of-thought", "tot prompting"]),
    ("react_prompt", "ReAct (Reasoning + Acting)", "tech", ["react prompting", "react agent", "reasoning and acting"]),
    ("reflexion", "Reflexion", "tech", ["reflexion agent", "self-reflection"]),
    ("rlhf", "RLHF", "tech", ["rlhf", "reinforcement learning from human feedback"]),
    ("dpo", "DPO (Direct Preference Optimization)", "tech", ["direct preference optimization", "dpo training"]),
    ("constitutional_ai", "Constitutional AI", "tech", ["constitutional ai", "rlaif", "constitution-based"]),
    ("foundation_model", "Foundation Model", "tech", ["foundation model", "foundation models", "기반 모델"]),
    # ─── 벤치마크 (v5.2: 논문 NER 보강) ───
    ("mmlu", "MMLU", "benchmark", ["mmlu"]),
    ("mmlu_pro", "MMLU-Pro", "benchmark", ["mmlu-pro", "mmlu pro"]),
    ("humaneval", "HumanEval", "benchmark", ["humaneval"]),
    ("mbpp", "MBPP", "benchmark", ["mbpp"]),
    ("gpqa", "GPQA", "benchmark", ["gpqa"]),
    ("gsm8k", "GSM8K", "benchmark", ["gsm8k", "gsm-8k"]),
    ("math_bench", "MATH Benchmark", "benchmark", ["math benchmark", "math dataset"]),
    ("swe_bench", "SWE-bench", "benchmark", ["swe-bench", "swe bench", "swebench"]),
    ("arc_agi", "ARC-AGI", "benchmark", ["arc-agi", "arc agi", "arcagi"]),
    ("bigbench", "BIG-bench", "benchmark", ["big-bench", "big bench", "bbh", "big-bench hard"]),
    ("agentbench", "AgentBench", "benchmark", ["agentbench"]),
    ("webarena", "WebArena", "benchmark", ["webarena", "web arena"]),
    ("chatbot_arena", "Chatbot Arena (LMSYS)", "benchmark", ["chatbot arena", "lmsys"]),
    ("livecodebench", "LiveCodeBench", "benchmark", ["livecodebench", "live code bench"]),

    # ─── M.AX·정책 이니셔티브 ───
    ("max_policy", "M.AX 정책 (산업부)", "policy", ["m.ax", "m·ax", "max 정책"]),
]


def _make_alias_text(text: str) -> str:
    """매칭용 정규화 — common._normalize_text_for_match와 동일."""
    return _normalize_text_for_match(text or "")


@lru_cache(maxsize=4096)
def _alias_pattern(alias_lower: str):
    """v6.15.34 (P2-5): alias 매칭 정규식 — ASCII 단어 내부 오탐 차단.

    배경(감사 P2-5): 기존 substring 매칭은 짧은 ASCII alias가 더 큰 단어에 무차별 매칭됐다.
      "fair"→"fairness"(meta_ai 오탐 10건), "rag"→"leveraging"(rag 오탐 18건), "nus"→"bonus".
    교정: alias 앞뒤가 ASCII 알파벳(a-z)이면 매칭 차단하는 lookaround.
      - 한국어 조사 결합("Copilot을", "오픈ai를")은 그대로 매칭 (조사는 a-z가 아님).
      - 숫자·구두점·한글 인접도 매칭 유지 ("llama3", "claude-3", "claude의").
      - 한글 포함 alias는 lookaround가 a-z만 보므로 사실상 substring과 동일(동작 불변).
    """
    return re.compile(r'(?<![a-z])' + re.escape(alias_lower) + r'(?![a-z])')


def _entity_matches(entity_aliases: list, normalized_text: str) -> bool:
    """엔티티 alias 중 하나라도 텍스트에 (ASCII 단어경계 고려하여) 포함되면 True."""
    for alias in entity_aliases:
        if _alias_pattern(alias.lower()).search(normalized_text):
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


def extract_from_articles(items: list, records: dict, auto_counter=None):
    """v5.1: article의 title + summary + summary_ko + LLM-extracted entities 모두 활용.
    v5.2: 논문은 abstract 전체 + arxiv_tags(Subjects) + authors도 추가.
    catalog 매칭은 기존 alias 방식, 추가로 LLM이 추출한 entity 이름을 auto_counter에 누적.
    """
    for it in items:
        # v5.1: summary_ko도 매칭 텍스트에 포함 (한국어 본문)
        text_parts = [it.get("title") or "", it.get("summary") or "", it.get("summary_ko") or ""]
        # v5.1: LLM이 추출한 entity 이름들도 매칭 텍스트에 추가
        llm_entities = it.get("entities") or []
        if isinstance(llm_entities, list):
            text_parts.extend([str(e) for e in llm_entities if isinstance(e, str)])
        # v5.2: 논문 메타 (arxiv_tags, authors)도 매칭 텍스트에 포함
        paper_meta = it.get("paper_meta") or {}
        if isinstance(paper_meta, dict):
            text_parts.extend(paper_meta.get("arxiv_tags") or [])
            text_parts.extend(paper_meta.get("authors") or [])
            if paper_meta.get("primary_category"):
                text_parts.append(paper_meta["primary_category"])
        text = _make_alias_text(" ".join(text_parts))
        if not text:
            continue
        url = it.get("url", "")
        date = (it.get("date") or "")[:10]
        score = it.get("score", 0) or 0

        matched_eids = set()
        for eid, rec in records.items():
            if _entity_matches(rec["aliases"], text):
                matched_eids.add(eid)
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

        # v5.1: LLM이 추출한 entity 중 catalog에 매칭 안 된 것 → auto_entities 후보
        if auto_counter is not None and isinstance(llm_entities, list):
            for ent_name in llm_entities:
                if not isinstance(ent_name, str): continue
                ent_name = ent_name.strip()
                if len(ent_name) < 2 or len(ent_name) > 60: continue
                low = ent_name.lower()
                # catalog의 어느 alias에든 정확/부분 매칭되면 자동 후보에서 제외
                catalog_hit = False
                for eid in matched_eids:
                    for al in records[eid]["aliases"]:
                        if low == al.lower() or low in al.lower() or al.lower() in low:
                            catalog_hit = True; break
                    if catalog_hit: break
                if catalog_hit: continue
                key = low
                if key not in auto_counter:
                    auto_counter[key] = {"name": ent_name, "count": 0, "score_sum": 0, "sample_titles": []}
                auto_counter[key]["count"] += 1
                auto_counter[key]["score_sum"] += score
                if len(auto_counter[key]["sample_titles"]) < 3:
                    auto_counter[key]["sample_titles"].append((it.get("title") or "")[:80])


def extract_from_strategy(strategy_history: dict, records: dict):
    """시사점 trend 카드 (daily/weekly/monthly)에서 엔티티 매칭.

    v6.15.2 hotfix: strategy_history entry가 v6.15부터 dict({summary, cards, _summary_addons}).
                    옛 list 포맷도 지원.
    """
    if not isinstance(strategy_history, dict):
        return
    for period in ("daily", "weekly", "monthly"):
        period_data = strategy_history.get(period) or {}
        for key, entry in period_data.items():
            # v6.15.2: entry가 dict({summary, cards, ...}) 또는 list(옛 포맷) 모두 지원
            if isinstance(entry, list):
                cards = entry
            elif isinstance(entry, dict):
                cards = entry.get("cards", [])
                if not isinstance(cards, list):
                    cards = []
            else:
                continue
            if not cards:
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

    # v5.1: catalog에 없는 LLM-추출 엔티티 후보 누적
    auto_counter = {}

    # 3. 매칭 수행
    extract_from_articles(items, records, auto_counter=auto_counter)
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

    # v5.1: auto_entities 정리 — 2회 이상 등장한 후보만 (노이즈 컷)
    auto_filtered = []
    for key, info in auto_counter.items():
        if info["count"] < 2:
            continue
        avg = round(info["score_sum"] / info["count"], 1)
        auto_filtered.append({
            "name": info["name"],
            "count": info["count"],
            "avg_score": avg,
            "sample_titles": info["sample_titles"],
        })
    auto_filtered.sort(key=lambda x: (-x["count"], -x["avg_score"]))
    print(f"  auto entities (catalog에 없지만 LLM이 추출, ≥2회): {len(auto_filtered)}", flush=True)
    for x in auto_filtered[:15]:
        print(f"    {x['count']:>3}회  avg={x['avg_score']:>5}  {x['name']}")

    # 8. 저장
    payload = {
        "generated_at": datetime.now(KST).isoformat(),
        "total_entities": len(active),
        "entities": active,
        "auto_entities": auto_filtered,  # v5.1: catalog 승격 후보 (사용자 검토용)
    }
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[done] wrote {OUTPUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
