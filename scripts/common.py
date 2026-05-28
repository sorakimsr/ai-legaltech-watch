"""
공통 유틸리티 — 텍스트 정제, 날짜 파싱, 카테고리 분류, 점수 산정.

v6.0 (P3-2): BLACKLIST 관련 데이터·상수는 ``scripts/blacklist.py`` 로 분리되었습니다.
common.py는 backward compat을 위해 그대로 재노출하므로
기존 ``from common import BLACKLIST_KEYWORDS`` 같은 코드는 변경 없이 동작합니다.

추후 분리 후보 (TODO):
- ``taxonomy.py`` : CATEGORY_KEYWORDS, CATEGORIES, categorize()
- ``score.py``    : 4축 시그널 + score_item()
"""

import html
import re
from datetime import datetime, timezone, timedelta
from functools import lru_cache

from dateutil import parser as dateparser

# v6.0 (P3-2): BLACKLIST 관련 데이터는 blacklist.py로 이동. 여기선 재노출.
from blacklist import (
    BLACKLIST_KEYWORDS,
    BOILERPLATE_PATTERNS,
    POLITICAL_FIGURES,
    POLICY_GUARD_SIGNALS,
    POLITICAL_FIGURES_TITLE_ONLY,
)


# ============================================================================
# 카테고리 분류 정책 (v2.1 — 엄격화)
# ============================================================================
# 원칙:
# 1. papers = arXiv·Papers With Code 소스만 (키워드 매칭 X)
# 2. 키워드 매칭은 word boundary로 엄격하게
# 3. funding은 raises + 금액 패턴이 같이 있을 때만
# 4. 카테고리 우선순위: papers > legaltech > funding > adoption > policy > product > ai-industry
# 5. 항목당 카테고리 최대 3개 (UI에서는 2개만 표시)

# 키워드 매칭 시 단어 경계 정규식
def kw_regex(kw):
    """키워드를 word boundary regex로 컴파일.
    한국어는 word boundary 적용 불가하므로 일반 includes."""
    if re.search(r"[가-힣]", kw):
        return re.compile(re.escape(kw), re.IGNORECASE)
    return re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)


CATEGORY_KEYWORDS = {
    "legaltech": [
        # 회사명 (확실한 시그널 — 단독 매칭 OK)
        "harvey", "legora", "mike oss", "mike legal",
        "hebbia", "ironclad", "spellbook", "robin ai",
        "evenup", "deepjudge", "lexis nexis", "thomson reuters",
        "bhsn", "lboxai", "엘박스", "인텔리콘",
        "로앤컴퍼니", "로앤굿",
        # 도메인 키워드 (구체적·명확)
        "legal ai", "legal tech", "legaltech", "리걸테크", "리걸 테크",
        "리걸 ai", "법률 ai", "법무 ai", "변호사 ai",
        "law firm ai", "biglaw ai", "ai for lawyers",
        "contract ai", "contract intelligence", "clm",
        "e-discovery", "ediscovery",
        "계약 검토 ai", "법률 자동화",
        # ※ "변호사", "법률", "법무" 같은 단독 단어는 제외 (정치·일반 뉴스 잡음)
    ],
    "papers": [
        # papers는 출처 기반으로만 부여하지만, 명시적 키워드는 추가 보강
        "arxiv", "neurips", "icml", "iclr", "acl", "emnlp",
        "preprint", "peer-reviewed",
    ],
    "product": [
        # 영문은 단어 경계
        "launches", "released", "rolls out", "unveils", "introduces",
        "general availability", "ga release",
        # 한국어
        "출시", "공개", "선보였", "발표",
    ],
    "funding": [
        # 금액·시리즈 (엄격하게)
        "raises $", "raised $", "series a", "series b", "series c", "series d",
        "valuation", "billion valuation", "ipo", "acquires", "acquired",
        # 한국어 — "유치"·"조달" 단독은 정치 뉴스 잡으니 명확한 구문만
        "투자 유치", "투자유치", "자금 조달", "자금조달", "시리즈 a", "시리즈 b",
        "시리즈 c", "시리즈 d", "라운드 마감", "기업가치", "인수합병", "m&a",
    ],
    "adoption": [
        "adopts", "deploys", "deployed", "implementing", "integrating",
        "case study", "rolls out across", "firm-wide adoption",
        "도입 사례", "활용 사례", "전사 도입", "적용 사례",
        # v3.9-D: 실무 도입 지표·ROI·파일럿
        "ai 파일럿", "ai pilot", "ai poc", "검증 실험",
        "ai roi", "ai 투자수익", "ai 운영 비용", "ai 비용",
        "token 비용", "토큰 비용", "ai 생산성", "ai 효율",
        "ai deployment", "ai 도입 효과",
        # v3.9-C: 온프레미스 AI 도입
        "온프레미스 ai", "on-prem ai", "on-premise ai",
    ],
    # v2.8.3: 'domestic' 카테고리 제거 — 언어 필터(ko/en)로 대체
    "policy": [
        "regulation", "regulator", "compliance",
        "eu ai act", "white house ai", "fcc", "ftc ", "doj ",
        "executive order", "ai standards",
        # 한국어 — "규제·법안" 단독은 일반 정치 뉴스 잡으니 AI/리걸 맥락 구문만
        "ai 규제", "ai규제", "데이터 규제", "개인정보 규제",
        "ai 거버넌스", "ai act", "ai 윤리", "알고리즘 규제",
        "ai기본법", "ai 기본법", "ai 법안",
    ],
    # v6.7 (2026-05-27): 사용자 요청 — 한국 중앙정부 부처 + 대관기관 (사법·입법) actor 명시.
    #   기존 'policy'는 광범위 (해외 + 국내 + 추상). 'gov_policy'는 한국 중앙기관 actor specific.
    #   지방정부·지자체 (서울시·경기도 등)는 명시적으로 매칭하지 않음.
    #   AI 관련 맥락에서만 의미 — categorize() 호출 시 다른 카테고리와 함께 부여됨.
    "gov_policy": [
        # 중앙정부 부처 (명시적 actor)
        "산업통상자원부", "산업부",
        "과학기술정보통신부", "과기정통부",
        "금융위", "금융위원회", "금융감독원", "금감원",
        "공정거래위원회", "공정위",
        "방송통신위원회", "방통위",
        "개인정보보호위원회", "개인정보위", "개인정보보호위",
        "행정안전부", "행안부",
        "법무부",
        "보건복지부",
        "중소벤처기업부", "중기부",
        "기획재정부", "기재부",
        # 사법·법조 대관기관 (v6.7.1 추가) — narrow 매칭으로 false-positive 차단
        #   ("대법원" 단독은 미국·일본 대법원 언급도 매칭하므로 outcome 시그널과 페어로만)
        "대법원 판결", "대법원 결정", "대법원 전원합의체",
        "한국 대법원", "supreme court of korea",
        "검찰청", "대검찰청", "검찰 수사", "검찰 기소",
        "헌법재판소", "헌재", "constitutional court",
        "법제처",
        # 입법기관 (v6.7.1 추가) — "국회" 단독 빼고 입법 활동 명시 시그널만
        "국회 본회의", "국회 입법", "국회의장",
        "국회 법사위", "국회 과방위", "국회 정무위", "국회 산자위",
        "법안 발의", "법안 통과", "법안 의결",
        "ai 관련 법안", "ai 법안 발의",
        # 정책 결과물 (정책 outcome)
        "행정명령", "executive order",
        "ai 기본법", "ai기본법",
        "ai 가이드라인", "ai 지침",
        "정책 수립", "법안 제정",
        "고시 개정", "시행령 개정", "시행 규칙",
        "범정부 ai", "범정부 정책",
        # 판례·법령
        "대법원 판결", "헌재 결정", "위헌 결정",
    ],
    "ai-industry": [
        # 회사명 — 다른 카테고리에 속하지 않는 경우의 fallback
        "openai", "anthropic", "claude ", "gpt-", "chatgpt", "gemini",
        "deepmind", "meta ai", "llama", "mistral", "xai", "grok",
        "nvidia ai", "microsoft ai", "perplexity",
        # v3.8: AI 엔지니어링·인프라 새 영역
        "ai 오케스트레이션", "ai orchestration", "오케스트레이터", "orchestrator",
        "에이전트 오케스트레이션", "agent orchestration",
        "멀티 에이전트", "multi-agent",
        "프롬프트 엔지니어링", "prompt engineering",
        "컨텍스트 엔지니어링", "context engineering",
        "하네스 엔지니어링", "harness engineering",
        "클론 엔지니어링", "clone engineering",
        "fde", "forward deployed engineer", "포워드 디플로이드",
        "mcp", "model context protocol", "모델 컨텍스트 프로토콜",
    ],
    # v6.15.17: 신규 카테고리 3개 — AI 단독 통과 기사들의 세분화 (사용자 요청 "태그 더 넓게")
    # models: 모델 release/비교/벤치마크/가격/오픈웨이트/미디어 생성 — 모델 비즈니스 핵심
    "models": [
        # 신흥 모델 회사·제품 (텍스트 LLM)
        "deepseek", "딥시크", "qwen", "큐원", "gemma", "젬마",
        "claude opus", "claude sonnet", "claude haiku",
        "gpt-4", "gpt-5", "o1", "o3",
        "llama 3", "llama 4", "mistral large", "command r", "codestral",
        "xai", "grok", "그록",
        # 이미지·영상·음악 생성 모델
        "midjourney", "미드저니",
        "dall-e", "dalle", "달이",
        "sora", "openai sora",
        "veo", "google veo",
        "runway",  # 영상 생성
        "ideogram", "pika",
        "suno", "udio",  # 음악 생성
        "stable diffusion", "스테이블 디퓨전",
        # release·비교·벤치마크
        "모델 출시", "모델 공개", "모델 release", "신모델",
        "모델 비교", "벤치마크", "ai 벤치마크", "llm 벤치마크",
        "mmlu", "gpqa", "humaneval", "swe-bench", "swe bench", "arc-agi", "arc agi",
        "livebench", "chatbot arena", "lmsys", "ai 리더보드",
        # 가격·요금
        "ai 가격", "ai api 가격", "모델 가격", "api 가격", "토큰 가격", "token price",
        "가격 인하", "가격 인상", "price cut", "permanent price",
        # 오픈소스·오픈웨이트
        "open weight", "오픈웨이트", "오픈소스 llm", "open source llm",
        "오픈소스 ai", "open source ai", "open-source model",
    ],
    # coding: AI 코딩 도구 (개발자가 가장 자주 보는 sub-domain)
    "coding": [
        "github copilot", "깃허브 코파일럿", "copilot",
        "cursor ai", "cursor 코드", "cursor editor",
        "windsurf", "codeium", "phind",
        "claude code", "클로드 코드",
        "ai 코딩", "ai coding", "ai code generation",
        "ai coding assistant", "코딩 ai 어시스턴트",
        "vibe coding", "바이브 코딩",
        "codex",  # OpenAI Codex
        "ai 페어 프로그래밍", "ai pair programming",
    ],
    # infra: AI 칩·인프라 (Groq/Cerebras/GPU/sLLM/온프레미스)
    "infra": [
        "groq", "cerebras", "ai 칩", "ai accelerator",
        "ai 인프라", "ai infrastructure",
        "gpu 클러스터", "ai gpu", "h100", "h200", "b100", "b200", "blackwell",
        "tpu", "google tpu",
        "sllm", "slm", "소형 언어모델", "small language model",
        "온프레미스 ai", "on-prem ai", "on-premise ai",
        "edge ai", "엣지 ai",
        "ai data center", "ai 데이터센터", "ai cloud",
    ],
    # v3.0: AI 거버넌스·리스크 — 사내 거버넌스 (정부 규제와 구분)
    "governance": [
        "ai 거버넌스", "ai governance", "governance gap",
        "거버넌스 공백", "거버넌스 부재",
        "ai 리스크", "ai risk", "ai risk management",
        "에이전트 거버넌스", "agent governance",
        "엔터프라이즈 ai 거버넌스", "enterprise ai governance",
        "ai 윤리", "ai ethics", "responsible ai",
        "ai 평가", "ai evaluation", "ai eval", "ai 벤치마크", "ai benchmark",
        "evaluation challenges", "ai 안전성", "ai safety",
        "ai 리터러시", "ai literacy",
        "compliance ai", "ai audit", "ai impact assessment",
        # v3.9-B: AI 감사·레드팀팅·설명가능성
        "ai 감사", "ai 레드팀", "ai red teaming", "red team ai",
        "explainable ai", "xai", "설명가능 ai", "설명 가능 ai",
        "trustworthy ai", "신뢰성 ai", "신뢰할 수 있는 ai",
        "model card", "system card", "모델 카드",
        "ai accountability", "ai 책임", "책임 ai",
    ],
    # v3.0: 시장·경쟁 구도 — 벤더 종속·모트·자체 구축 등 시장 구조 변화
    "market": [
        "borrowed time", "commoditising", "commoditizing",
        "wrappers", "wrapper", "in-house tool", "build their own", "self-hosted",
        "vendor lock", "lock-in", "벤더 종속", "moat", "differentiation",
        "alternative to", "challenger", "disrupt", "disruption",
        "competitive landscape", "market shift", "consolidation",
        "frontrunner", "incumbent", "market commoditization",
        "단일 llm", "단일 모델",
    ],
}

# 카테고리 우선순위 (정렬 시 사용)
CATEGORY_PRIORITY = {
    "papers": 1,
    "legaltech": 2,
    "gov_policy": 3,  # v6.7: 중앙정부 actor 명시된 정책 (가장 구체적)
    "funding": 4,
    "adoption": 5,
    "governance": 6,  # v3.0: 사내 거버넌스 (정부 정책보다 실무 가까움)
    "policy": 7,      # 광범위한 정책·규제 (해외 + 추상)
    "models": 8,      # v6.15.17: 모델 release/가격/벤치마크 (사용자 핵심 관심)
    "market": 9,      # v3.0: 시장·경쟁 구도
    "coding": 10,     # v6.15.17: AI 코딩 도구
    "infra": 11,      # v6.15.17: AI 칩·인프라
    "product": 12,
    "ai-industry": 13,  # fallback — 위 분류 안 되는 일반 AI 산업
}

# v6.0 (P3-7): module-level pre-compile → lazy lru_cache 함수로 변경.
#              테스트 격리·핫리로드 시 CATEGORY_KEYWORDS 수정 후 캐시 비우기 쉬워짐:
#              `common._compiled_keywords.cache_clear()` 호출 후 재사용.
@lru_cache(maxsize=1)
def _compiled_keywords():
    """카테고리별 컴파일된 키워드 regex 리스트. 첫 호출 시 lazy 컴파일."""
    return {
        cat: tuple(kw_regex(kw) for kw in kws)
        for cat, kws in CATEGORY_KEYWORDS.items()
    }

# Backward compat — 기존 호출자가 dict처럼 접근하는 케이스 유지.
# 모듈 import 시 한 번만 실행되므로 비용 동일.
COMPILED_KEYWORDS = _compiled_keywords()


# ============================================================================
# 관련성 필터 (Naver/Google News 결과 사후 검증) — v2.5 엄격화
# ============================================================================
# 두 그룹으로 나눔:
# - STRONG_KEYWORDS: 단독으로 통과 가능 (회사명·명확한 도메인 용어)
# - AI_SIGNALS + LEGAL_SIGNALS: 둘 다 있어야 통과 (조합 시그널)

# 단독 통과 키워드 — 매우 명확한 AI/리걸테크 시그널
STRONG_KEYWORDS = [
    # AI 회사·제품 (단독으로 확실)
    "openai", "anthropic", "claude", "chatgpt", "gpt-4", "gpt-5",
    "deepmind", "gemini", "llama", "mistral",
    "perplexity", "hugging face", "stability ai",
    "scale ai", "databricks ai", "cohere",
    "huggingface",
    # v6.15.17: 신흥 모델·제품 추가 (사용자 지적 — DeepSeek/Qwen 등 다수 누락으로 한국 매체 보도 80%+ REJECT됐던 문제)
    "deepseek", "딥시크",
    "qwen", "큐원",
    "gemma", "젬마",
    "codex",          # OpenAI Codex
    "copilot", "코파일럿", "github copilot",
    "cursor ai", "cursor 코드",
    "windsurf",
    "codeium", "phind",
    "sora",           # OpenAI Sora 영상
    "veo",            # Google Veo 영상
    "midjourney", "미드저니",
    "dall-e", "dalle", "달이",
    "suno", "udio",   # 음악 생성
    "runway",         # 영상 생성
    "ideogram",
    "pika",
    "moshi",          # 음성 AI
    "groq", "cerebras",  # AI 칩
    "xai", "grok", "그록",
    "meta ai", "메타 ai",
    "ai 모델", "ai api", "llm api",  # 일반 모델/API 표현
    # AI 도메인 명확
    "생성형 ai", "생성ai", "인공지능", "ai 에이전트", "agentic ai",
    "multi-agent", "autonomous agent",
    "llm", "slm", "sllm",
    "transformer model", "diffusion model",
    # 리걸테크 회사·제품 (단독으로 확실)
    "harvey", "legora", "mike oss", "mike legal",
    "hebbia", "ironclad", "spellbook", "robin ai",
    "evenup", "deepjudge", "lexis nexis", "thomson reuters",
    "bhsn", "lboxai", "엘박스", "인텔리콘", "로앤컴퍼니", "로앤굿",
    # 리걸테크 도메인 명확
    "리걸테크", "리걸 테크", "legaltech", "legal tech",
    "legal ai", "법률 ai", "법무 ai", "변호사 ai",
    "law firm ai", "biglaw ai", "ai for lawyers",
    "contract ai", "contract intelligence", "clm software",
    # 규제·정책 (AI 맥락 명확)
    "eu ai act", "ai 기본법", "ai기본법",
    "ai 규제", "ai규제", "ai governance", "ai 거버넌스",
    "ai standards", "ai 표준",
    # v6.15.17: 비즈니스 이벤트 (AI 맥락 명확) — 가격 인하·release·벤치마크
    "ai 가격", "ai api 가격", "모델 가격",
    "open weight", "오픈웨이트",
    "open source llm", "오픈소스 llm", "오픈소스 ai",
]

# AI 시그널 (도메인 시그널과 조합되어야 통과)
AI_SIGNALS = [
    "ai", "인공지능", "ml", "machine learning",
    "agent", "에이전트", "model",
    "gpt", "claude", "gemini", "llm",
]

# 도메인 시그널 (AI 시그널과 조합되어야 통과) — is_relevant() 전용 (넓은 키워드)
# v6.0: 변수 이름을 RELEVANCE_LEGAL_SIGNALS로 변경.
#       기존 LEGAL_SIGNALS는 line 865의 score_item용 LEGAL_SIGNALS에 덮어써지는 버그였음.
RELEVANCE_LEGAL_SIGNALS = [
    "법률", "리걸", "법무", "변호사", "로펌", "법조",
    "계약", "소송", "판례", "법원", "특허",
    "legal", "lawyer", "law firm", "litigation", "patent",
]

# v6.0 (P3-2): 위 BLACKLIST 관련 데이터는 scripts/blacklist.py로 이동.
#               common.py 상단의 "from blacklist import *" 로 backward compat 유지.


def is_relevant(title: str, summary: str, source_type: str = "rss") -> bool:
    """관련성 체크 — 모든 소스에 보일러플레이트 + 블랙리스트 적용.

    규칙 (v3.0 강화):
    0. AI 생성 보일러플레이트 패턴이 본문에 있으면 모든 소스에서 즉시 제외
    1. 블랙리스트 키워드가 제목 또는 요약에 있으면 모든 소스에서 즉시 제외
       (v3.0) 단, 정치 인물명(trump/biden 등)이 매칭된 경우에도
       본문에 AI 정책·규제 시그널이 함께 있으면 통과 (AI 정책 동향 보호)
    2. Naver·Google News는 STRONG 또는 (AI+LEGAL) 시그널 추가 검증
    3. RSS·arXiv·OpenAlex는 블랙리스트만 통과하면 OK (큐레이션된 소스로 가정)
    """
    text = (title + " " + summary).lower()
    title_lower = title.lower()

    # 0. AI 생성 보일러플레이트 — 모든 소스에서 즉시 차단
    for pat in BOILERPLATE_PATTERNS:
        if pat in text:
            return False

    # 0-b. v6.6: PR pattern 'block' (title prefix가 명백한 PR 시리즈) — 즉시 차단
    pr_verdict, _ = classify_pr_pattern(title or "", summary or "")
    if pr_verdict == 'block':
        return False

    # v3.0: AI 정책 시그널 존재 여부 사전 계산 (정치 인물명 차단 우회용)
    has_policy_guard = any(g in text for g in POLICY_GUARD_SIGNALS)

    # 1. 블랙리스트 — 모든 소스에 적용 (RSS도 정치·lifestyle 기사 종종 포함)
    # v6.0 (P1-5): 정치 인물명은 title-only 엄격 모드 + 확장된 POLICY_GUARD 우회.
    for kw in BLACKLIST_KEYWORDS:
        is_political = kw in POLITICAL_FIGURES
        if is_political:
            # 정치 인물명: title에만 등장하면 매칭, 본문 단독 언급은 통과
            matched = (kw in title_lower) if POLITICAL_FIGURES_TITLE_ONLY else (kw in title_lower or kw in text)
            if not matched:
                continue
            # title에 매칭됐어도 AI 정책·도입·활용 시그널이 있으면 보호
            if has_policy_guard:
                continue
            return False
        # 일반 BLACKLIST 키워드: title 또는 본문 어디든
        if kw in title_lower or kw in text:
            return False

    # RSS·arXiv·OpenAlex는 큐레이션된 소스이므로 블랙리스트 통과만으로 OK
    if source_type not in ("naver", "google_news"):
        return True

    # 2. Strong keyword 단독 통과
    for kw in STRONG_KEYWORDS:
        if kw in text:
            return True

    # 3. AI 시그널 + 도메인 시그널 조합
    # v6.0: LEGAL_SIGNALS 이중 정의 버그 수정 — RELEVANCE_LEGAL_SIGNALS 사용
    has_ai = any(kw in text for kw in AI_SIGNALS)
    has_legal = any(kw in text for kw in RELEVANCE_LEGAL_SIGNALS)
    if has_ai and has_legal:
        return True

    # v6.15.17: AI 시그널 강한 단독 통과 (한국 매체 + Google News의 순수 AI 기사 보호)
    #   기존엔 AI+LEGAL 페어 강제로 신흥 모델 가격 인하·벤치마크·release 등
    #   순수 AI 기사가 모두 REJECT됐던 문제 해결.
    #   2가지 조건 중 하나 충족 시 통과:
    #     (a) AI 시그널 종류 2+ (예: "ai" + "model" 같이 다른 키워드 결합)
    #     (b) AI 핵심 단어 등장 횟수 2+ ("ai", "인공지능", "llm", "gpt" 누적)
    #   noise는 score_item이 2차 cut-off (score < 35 drop)로 잡음.
    ai_kind_count = sum(1 for kw in AI_SIGNALS if kw in text)
    if ai_kind_count >= 2:
        return True
    # AI 등장 횟수 — substring count (대부분 한국 매체가 AI를 본문에 여러 번 언급)
    ai_text_count = (
        text.count(" ai ") + text.count("ai ") + text.count(" ai") +
        text.count("ai.") + text.count("ai,") + text.count("ai)") +
        text.count("인공지능") +
        text.count("llm") + text.count("gpt") + text.count("챗gpt")
    )
    if ai_text_count >= 2:
        return True

    return False


HIGH_VALUE_KEYWORDS = {
    # 회사·제품 (브랜드 가중치는 약간 낮춤 — 출시 뉴스가 무조건 1등 되지 않게)
    "harvey": 10, "legora": 10, "mike oss": 12, "mike legal": 10, "mikeoss": 12,
    "openai": 8, "anthropic": 8, "gpt-5": 10, "claude opus": 8, "claude sonnet": 6,

    # === 시장 구도·경쟁 분석 (가장 중요 — 실무자가 알아야 할 흐름) ===
    "borrowed time": 22, "commoditising": 20, "commoditizing": 20,
    "wrappers": 18, "wrapper": 14,
    "in-house": 15, "in house tool": 15, "build their own": 16, "self-hosted": 14,
    "open source": 14, "open-source": 14, "오픈소스": 14,
    "alternative to": 14, "rival": 12, "challenger": 12,
    "disrupt": 14, "disruption": 14, "shift": 8, "market shift": 16,
    "competitive landscape": 14, "frontrunner": 12,
    "moat": 16, "differentiation": 12,
    "vendor lock": 16, "lock-in": 12, "벤더 종속": 16,
    "pay-as-you-go": 10, "contract length": 8,

    # === 정책·규제·거버넌스 (한국 실무자 필독) ===
    "ai 기본법": 20, "ai act": 16, "eu ai act": 16,
    "가이드라인": 14, "가이드라인 공백": 22, "가이드라인 부재": 22, "기준 마련": 16, "기준 못": 18,
    "규제 공백": 22, "규제 부재": 20, "정책 공백": 18,
    "ai 거버넌스": 16, "ai governance": 14,
    "정부": 6, "법무부": 12, "과기정통부": 12,
    "개인정보": 10, "데이터 주권": 14, "data sovereignty": 14,
    "compliance": 8, "audit": 6,

    # === 자금·M&A (가치 있지만 출시 뉴스보다는 낮게) ===
    "raises $": 7, "funding": 5, "valuation": 7, "billion": 9, "series ": 5,
    "acquires": 10, "acquired by": 12, "merger": 10,

    # === 출시·발표 (가중치 낮춤 — 그 자체로는 시장 의미가 약함) ===
    "launches": 3, "announces": 3, "introduces": 3, "unveils": 3,
    "release": 3, "available now": 4,

    # === 연구·기술 시그널 ===
    "breakthrough": 10, "state-of-the-art": 8, "sota": 8,
    "agent": 5, "agentic": 6, "multi-agent": 7,
    "1m context": 12, "long context": 10, "long-horizon": 14,

    # === 도메인 ===
    "리걸테크": 10, "법률 ai": 8, "리걸 ai": 10,
    "한국": 4, "korea": 4,

    # === 한국 시장·실무 ===
    "법무법인": 6, "로펌": 6, "변호사": 4,
    "ai 도입": 12, "ai 활용": 10, "ai 전환": 12,
    "사내 ai": 14, "엔터프라이즈 ai": 12,
    "한국형": 10, "한국 시장": 8,
    "나홀로 소송": 14, "소송장": 8,
}


def clean_text(text: str) -> str:
    """HTML 태그 제거 + 공백 정규화"""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def truncate(text: str, max_len: int = 280) -> str:
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


_KST = timezone(timedelta(hours=9))


def parse_date_safe(date_str: str, default_tz=None):
    """다양한 형식의 날짜를 datetime으로 변환. 실패 시 None.

    v6.9 (2026-05-27): timezone 없는 datetime의 default tz를 호출자가 명시 가능.
        default_tz=None 또는 timezone.utc → UTC 가정 (기존 동작, 영문 매체용)
        default_tz=_KST 또는 timezone(timedelta(hours=9)) → KST 가정 (한국 매체용)

    한국 매체 RSS의 pubDate는 거의 항상 KST이지만 timezone offset이 없음.
    예: AI타임스 RSS '2026-05-26 18:58:52' (실제로는 KST). UTC로 가정하면 9시간 어긋남.
    """
    if not date_str:
        return None
    try:
        dt = dateparser.parse(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=default_tz or timezone.utc)
        return dt
    except Exception:
        return None


def categorize(title: str, summary: str, default_cats: list, source_type: str = "rss") -> list:
    """제목·요약·출처 기반 카테고리 추론. v2.1 엄격 분류.

    규칙:
    - papers: arXiv·blog source_type만 부여 가능 (default_cats에 있을 때만)
    - 다른 카테고리도 키워드 매칭은 정밀하게 (word boundary)
    - 결과는 우선순위 순서로 정렬, 최대 3개
    """
    text = title + " " + summary
    cats = set(default_cats)

    # papers는 default_cats에 이미 있을 때만 유지 (소스 기반)
    # 키워드 매칭으로 추가 안 함
    has_papers_default = "papers" in default_cats

    for cat, patterns in COMPILED_KEYWORDS.items():
        if cat == "papers":
            # papers는 소스 기반만 — 키워드 매칭으로 새로 추가 X
            continue
        if cat in cats:
            continue
        for pat in patterns:
            if pat.search(text):
                cats.add(cat)
                break

    # papers가 default에 있어도, 회사 발표 같은 product/funding 시그널이 강하면 papers 제거
    # → arXiv 소스에서는 그대로 두지만, 'blog' source_type의 papers default는 키워드 검증
    if has_papers_default and source_type != "arxiv":
        # blog source에서는 실제 논문 관련 키워드가 있을 때만 papers 유지
        if not any(pat.search(text) for pat in COMPILED_KEYWORDS["papers"]):
            cats.discard("papers")

    # v6.15.17: AI + LEGAL 페어 자동 → legaltech 카테고리 강제 부여
    #   기존 categorize의 legaltech 키워드(harvey/legora/리걸테크 등)에 안 잡혀도,
    #   본문에 AI 시그널 + 법률 도메인 시그널 페어 있으면 legaltech 인정.
    #   효과: score_item의 legaltech +12 보너스 + 핵심 도메인 NEGATIVE cap 완화
    #   (v6.15.13) 자동 적용. "AI 변호사", "법무팀 ChatGPT 도입" 같은 기사 보호.
    if "legaltech" not in cats:
        text_lower = text.lower()
        has_ai_kw = any(kw in text_lower for kw in AI_SIGNALS)
        has_legal_kw = any(kw in text_lower for kw in RELEVANCE_LEGAL_SIGNALS)
        if has_ai_kw and has_legal_kw:
            cats.add("legaltech")

    # v6.15.21: 핵심 법령은 policy 태그 무조건 부여 (사용자 정책 — 2026-05-28)
    #   AI 기본법·정보통신망법·개인정보보호법 + 관련 시행령·시행규칙 본문 등장 시
    #   본문 기타 시그널 부족해도 policy 카테고리 강제 부여 → 사용자 핵심 어젠다 보호.
    #   가중치는 score_item에서 별도 부여 (정보통신망법·개인정보보호법은 AI 조건부).
    text_for_law = text.lower()
    if _has_core_law_mention(text_for_law):
        cats.add("policy")

    # v6.15.21 SUPER_BOOST: 사용자 명시 8개 어젠다 매칭 시 legaltech 강제 부여
    #   (판결문 공개·공정위 AI·개인정보 특례 등 prompt 단계에서 누락되던 어젠다 보호)
    if _has_super_boost(text_for_law):
        cats.add("legaltech")

    # 우선순위 순으로 정렬, 최대 3개
    sorted_cats = sorted(cats, key=lambda c: CATEGORY_PRIORITY.get(c, 99))
    return sorted_cats[:3]


# ============================================================================
# v6.15.21 (2026-05-28): 핵심 법령 검출 — 사용자 정책
#   판결문 공개·AI 규제·개인정보 어젠다가 prompt 단계에서 누락되던 문제 보완.
#   AI 기본법 → 무조건 가중치.
#   정보통신망법·개인정보보호법 → AI 관련일 때만 가중치.
#   "관련 시행령·시행규칙"도 별도 매칭.
# ============================================================================

# 카테고리 부여용 — 본문에 등장하면 policy 강제
CORE_LAW_PATTERNS = [
    # AI 기본법 (한국)
    "ai 기본법", "ai기본법", "인공지능 기본법", "인공지능기본법",
    "ai 산업 진흥 및 신뢰", "인공지능 산업 진흥",
    # 정보통신망법
    "정보통신망법", "정보통신망 이용촉진", "정보통신망 이용 촉진",
    # 개인정보보호법
    "개인정보보호법", "개인정보 보호법", "개인정보보호 법",
    # 시행령·시행규칙 (법명과 함께 등장할 때만 의미 있음 → score_item에서 같이 검증)
    "ai 기본법 시행령", "ai 기본법 시행규칙",
    "정보통신망법 시행령", "정보통신망법 시행규칙",
    "개인정보보호법 시행령", "개인정보보호법 시행규칙",
    "개인정보 보호법 시행령", "개인정보 보호법 시행규칙",
]

# 가중치 종류 — score_item에서 사용
AI_BASIC_LAW_PATTERNS = [
    "ai 기본법", "ai기본법", "인공지능 기본법", "인공지능기본법",
    "ai 산업 진흥 및 신뢰", "인공지능 산업 진흥",
]

CONDITIONAL_LAW_PATTERNS = [
    # 정보통신망법 + 개인정보보호법 — AI 관련일 때만 가중치
    "정보통신망법", "정보통신망 이용촉진", "정보통신망 이용 촉진",
    "개인정보보호법", "개인정보 보호법", "개인정보보호 법",
]


def _has_core_law_mention(text_lower: str) -> bool:
    """본문에 AI 기본법·정보통신망법·개인정보보호법 또는 시행령·시행규칙 등장 여부."""
    return any(pat in text_lower for pat in CORE_LAW_PATTERNS)


def _is_ai_basic_law(text_lower: str) -> bool:
    """AI 기본법 (시행령·시행규칙 포함) 등장 여부."""
    if any(pat in text_lower for pat in AI_BASIC_LAW_PATTERNS):
        return True
    # 시행령·시행규칙: AI 기본법 시행령 같은 결합 표현
    for pat in AI_BASIC_LAW_PATTERNS:
        if f"{pat} 시행" in text_lower:
            return True
    return False


def _is_conditional_law(text_lower: str) -> bool:
    """정보통신망법·개인정보보호법 (시행령·시행규칙 포함) 등장 여부."""
    return any(pat in text_lower for pat in CONDITIONAL_LAW_PATTERNS)


# ============================================================================
# v6.15.21 — SUPER_BOOST: 사용자 명시 핵심 어젠다 강력 보호 (2026-05-28)
#   사용자가 사라졌다고 지적한 8개 어젠다를 absolute priority로 보호.
#   매칭 시:
#     1) AI gate 면제 (AI 시그널 없어도 score 0 안 됨)
#     2) legaltech 카테고리 자동 부여 (+16 가중치, score floor 35)
#     3) +18 absolute boost
#   효과: 짧은 본문/AI 시그널 없어도 borderline 안 떨어지고 상위 진입.
# ============================================================================

SUPER_BOOST_KEYWORDS = [
    # ① 판결문 공개·데이터 인프라
    "판결문 공개", "판결문 데이터", "판결문 데이터셋",
    "비실명화", "익명화 판결", "법인명 실명 공개", "법인 실명 공개",
    "사법정책연구원", "판결문 공개제도",
    # ② AI 서비스 규제·개인정보
    "공정위 ai", "공정거래위 ai", "ai 서비스 시장 실태", "ai 시장 실태조사",
    "ai 개인정보 처리 특례", "개인정보 처리 특례", "ai 개발 개인정보 특례",
    "개인정보 ai 특례", "ai 학습 개인정보",
    "ai 기본법", "ai기본법", "인공지능 기본법",
    # 법령 교차 적용
    "ai 기본법 개인정보보호법", "ai 기본법 정보통신망법",
    "개인정보보호법 ai 기본법", "정보통신망법 ai 기본법",
]


def _has_super_boost(text_lower: str) -> bool:
    """사용자 명시 핵심 어젠다 매칭 여부."""
    return any(kw in text_lower for kw in SUPER_BOOST_KEYWORDS)


# ============================================================================
# v2.7.3: 가중치 기반 중요도 — 사용자 정책
#   로펌·법조 AI 도입:  0.40
#   글로벌 AI 시장·자본: 0.25
#   AI 정책·규제:       0.25
#   홍보·소개:          0.10 (필요한 경우만)
# ============================================================================

LAW_AI_KEYWORDS = [
    # Big Law (글로벌)
    "kirkland", "cleary gottlieb", "skadden", "latham", "sullivan & cromwell",
    "davis polk", "wachtell", "freshfields", "linklaters", "clifford chance",
    "allen & overy", "white & case", "baker mckenzie", "dentons",
    "a&o shearman", "paul hastings", "weil gotshal",
    # 한국 대형 로펌
    "김앤장", "광장", "법무법인 광장", "세종", "법무법인 세종",
    "율촌", "태평양", "화우", "지평", "바른", "케이씨엘", "법무법인",
    # AI 도입·활용
    "law firm ai", "biglaw ai", "ai for lawyers", "legal generative ai",
    "legal ai adoption", "lawyer copilot", "associate productivity ai",
    "법무 ai 도입", "로펌 ai 도입", "법조 ai", "변호사 ai",
    "법률 자동화", "법률 검토 ai", "계약 검토 ai",
    # 리걸테크 핵심 파트너십
    "harvey partnership", "harvey for", "harvey rollout",
    "thomson reuters ai", "lexis ai", "lexis+ ai", "co-counsel",
    # 지식관리 + AI
    "knowledge management ai", "법률 지식관리", "지식관리 ai",
    "legal knowledge graph", "matter management ai", "clm",
    "contract intelligence", "contract lifecycle",
    # v3.0: 일반인 법률 접근·소송 자동화 (대형로펌이 모니터링할 시장 변화)
    "나홀로 소송", "셀프 소송", "self-represented litigant",
    "소송 자동화", "litigation automation",
    "ai 변호", "변호 자동화", "법률 챗봇", "legal chatbot",
    "온라인 법률 상담", "ai 법률 상담",
    # v3.5: AI 가격 정책·청구 모델 (로펌 비즈니스 모델 변화 — 대형로펌 매우 중요)
    "ai pricing", "ai 가격", "ai 요금",
    "alternative fee", "value billing", "fixed fee ai",
    "billable hour ai", "billing model ai",
    "subscription pricing legal", "legal subscription",
    "firms need to move faster on ai", "ai pricing pressure",
    # v3.5: 변호사 AI 활용·사고 사례 (도입 리스크 사례 — 모니터링 필수)
    "ai drafting", "ai-drafted", "ai 초안",
    "misleading letters ai", "ai hallucination court",
    "junior solicitor used ai", "solicitor used ai",
    "ai sanction", "court sanction ai", "ai 제재",
    "fake citations ai", "ai 환각 법정",
    "ai 사용 변호사 징계", "변호사 ai 오용",
]

GLOBAL_MARKET_KEYWORDS = [
    # 빅테크 흐름·시장 구조
    "borrowed time", "commoditising", "commoditizing",
    "wrappers", "in-house tool", "build their own", "self-hosted",
    "vendor lock", "lock-in", "moat", "differentiation",
    "alternative to", "challenger", "disrupt", "disruption",
    "competitive landscape", "market shift", "consolidation",
    "frontrunner", "incumbent",
    # 대형 자본 흐름
    "billion", "$1b", "$5b", "$10b", "조 원 투자",
    "acquires", "acquired by", "merger", "m&a",
    "ipo", "valuation", "series f", "series g",
    # 빅테크 전략 발표
    "openai revenue", "openai earnings", "anthropic revenue",
    "google search ai", "meta llama", "deepseek", "kimi", "qwen",
    "xai grok", "mistral", "perplexity",
    "frontier model", "model race", "model launch",
    # v3.5.1: 글로벌 거점 확장·해외 진출 (대형 AI 기업 전략)
    "openai expansion", "anthropic expansion", "openai office",
    "openai singapore", "openai milan", "anthropic singapore",
    "해외 거점 확장", "신규 기지", "거점 확장",
    "글로벌 사무소", "해외 사무소", "거점 마련",
    "asia pacific office", "europe office",
    # v3.5.1: 에이전트 스프롤·관리 이슈 (기업 도입 흐름)
    "agent sprawl", "에이전트 스프롤",
    "agent governance crisis", "agent proliferation",
    "ai agent management",
    # v3.8: AI 엔지니어링 새 직무·실무 영역 (시장 인재 흐름)
    "ai orchestration", "ai 오케스트레이션", "orchestrator",
    "에이전트 오케스트레이션", "agent orchestration",
    "prompt engineering", "프롬프트 엔지니어링",
    "context engineering", "컨텍스트 엔지니어링",
    "harness engineering", "하네스 엔지니어링",
    "clone engineering", "클론 엔지니어링",
    "forward deployed engineer", "포워드 디플로이드", "fde role",
    "오픈소스 ai", "open source ai", "open weight", "오픈웨이트",
    "오픈소스 llm", "open source llm",
]

POLICY_KEYWORDS = [
    "ai 기본법", "ai act", "eu ai act", "ai 액트",
    "ai 거버넌스", "ai governance",
    "ai 규제", "ai 정책", "규제 공백", "규제 부재",
    "가이드라인 공백", "가이드라인 부재", "기준 마련",
    "정책 공백", "법무부", "과기정통부", "개인정보보호위원회",
    "방통위", "공정위", "금융위 ai",
    "data sovereignty", "데이터 주권",
    "ai 저작권", "ai copyright", "copyright ai", "fair use ai",
    "compliance ai", "ai audit", "ai impact assessment",
    "executive order ai", "행정명령 ai", "ai 행정명령",
    # v3.0: AI 거버넌스·리스크·평가 (사내 거버넌스 영역)
    "governance gap", "거버넌스 공백", "거버넌스 부재",
    "ai 리스크", "ai risk", "ai risk management",
    "에이전트 거버넌스", "agent governance",
    "엔터프라이즈 ai 거버넌스", "enterprise ai governance",
    "ai 윤리", "ai ethics", "responsible ai",
    "ai 평가", "ai evaluation", "ai eval", "ai 벤치마크", "ai benchmark",
    "evaluation challenges", "ai 안전성", "ai safety",
    "ai 리터러시", "ai literacy", "ai 문해력",
    # v3.0: 기준 마련 변형 (정책 공백 케이스 추가 매칭)
    "기준 마련 못", "기준 못 마련", "기준이 없",
    "1년째 기준", "수년째 기준", "기준 부재",
    # v3.5.1: AI 자가진화·자율 진화·정렬 문제 (실존적 거버넌스 이슈)
    "ai evolves on its own", "self-evolving ai", "ai self-improvement",
    "ai 자가진화", "ai 자율진화", "ai 진화 통제",
    "autonomous ai evolution", "recursive self-improvement",
    "ai alignment", "ai 정렬", "alignment problem",
    "human oversight ai", "인간 감독 ai",
    # v3.9-C: Sovereign AI · 디지털 주권 · 한국형 AI
    "sovereign ai", "소버린 ai", "ai 주권",
    "디지털 주권", "data sovereignty",
    "한국형 ai", "국산 ai", "k-ai",
    "ai 자립", "ai 독립", "ai self-reliance",
]

PROMO_PATTERNS = [
    # 헤드라인 보일러플레이트 (소문자 비교)
    "[ai 클로즈업]", "[ai 인사이드]", "[ai 트렌드]",
    "tips 선정", "팁스 선정",
    "글로벌 ai os 기업 선언", "글로벌 기업 선언", "글로벌 도약",
    "혁신 출시", "신제품 출시", "공식 출범", "본격 출범",
    "정식 출시", "베타 출시", "베타 오픈",
    "유망 스타트업", "주목받는 스타트업", "주목 받는 스타트업",
    "[기고]", "[칼럼]",
    "공식 파트너", "공식 파트너십 체결",
    "수상", "대상 수상", "최우수상",
    "행정 자동화 플랫폼으로 글로", "플랫폼으로 글로벌",
]


def detect_score_buckets(title: str, summary: str) -> dict:
    """4개 버킷별 매칭 강도 (0~1) — v3.2: 매칭 수 기반 연속 분포"""
    text = (title + " " + summary).lower()
    title_lower = title.lower()

    buckets = {"law": 0.0, "global": 0.0, "policy": 0.0, "promo": 0.0}

    # v3.2: 매칭된 키워드 개수를 세고 logarithm으로 매핑 → 다양한 분포
    law_hits = sum(1 for kw in LAW_AI_KEYWORDS if kw in text)
    global_hits = sum(1 for kw in GLOBAL_MARKET_KEYWORDS if kw in text)
    policy_hits = sum(1 for kw in POLICY_KEYWORDS if kw in text)

    # 매칭 n개 → 강도: 1개=0.2, 2개=0.35, 3개=0.5, 4개=0.65, 5개=0.75, 6개=0.85, 7개+=1.0
    # (1 - 0.85^n) 의 형태로 빠르게 차오르되 1을 넘지 않는 연속 분포
    def hits_to_strength(n: int) -> float:
        if n == 0:
            return 0.0
        # 1 - 0.78^n: 1→0.22, 2→0.39, 3→0.53, 4→0.63, 5→0.71, 6→0.78, 7→0.83, 8→0.87
        return round(1.0 - 0.78 ** n, 3)

    buckets["law"] = hits_to_strength(law_hits)
    buckets["global"] = hits_to_strength(global_hits)
    buckets["policy"] = hits_to_strength(policy_hits)

    # PROMO는 헤드라인 위주 (옛 동작 유지)
    for pat in PROMO_PATTERNS:
        if pat in title_lower:
            buckets["promo"] = 1.0
            break
    return buckets


# v4.0: "행동 시그널" 키워드 그룹 — 대형로펌 경영전략팀이 f/u할 가치 신호
#
# 페르소나: 대형로펌 경영전략팀이 AI 관련 검토·행동이 필요한 사항을 찾는 도구.
# 행동 가치 = "이 기사를 보고 나서 우리 로펌·고객사에 무엇을 검토·변경해야 하는가" 시그널.
#
# 4축 시그널 매트릭스:
#  - DECISION   (의사결정·전략·도입·거버넌스): 도입·채택·재설계·통제·감사·검토·평가
#  - REGULATORY (규제·정책·법규): AI 기본법·EU AI Act·금감원·컴플라이언스·가이드라인
#  - MARKET     (시장구조·M&A·진출): 인수·합병·투자·진출·거점·신사업·경쟁
#  - LEGAL      (법률·로펌·소송·계약): 변호사·로펌·소송·계약·판결·합의·자문
#
# 단순 "AI" 언급으로는 절대 시그널 hit 안 되도록 — 모두 의미 페어로 설계.

DECISION_SIGNALS = [
    # 의사결정·도입 동사
    "도입", "채택", "도입 결정", "도입 검토", "선정", "결정",
    "재설계", "재구축", "재정비", "전면 개편", "구축", "운영체계",
    # 거버넌스·통제·감사
    "거버넌스", "통제 체계", "내부통제", "내부 통제", "위험 관리",
    "리스크 관리", "감사", "감사 체계", "감사 시스템",
    # 검토·평가
    "검토", "재검토", "평가", "평가 체계", "검증", "벤치마크",
    # 책임·역할
    "책임 경계", "책임 귀속", "책임 할당", "역할 정의",
    "accountability", "governance", "compliance",
    # 행동 결정 패턴
    "전략 수립", "전략 재설계", "정책 마련", "기준 설정",
    "프레임워크", "체크리스트", "kpi 재설계", "지표 재정의",
]

REGULATORY_SIGNALS = [
    "ai 기본법", "ai act", "eu ai act", "ai 가이드라인", "ai 규제",
    "ai 거버넌스 법", "디지털 주권", "데이터 주권", "sovereign ai",
    "금감원", "금융위", "금융감독원", "공정위", "방통위",
    "개인정보보호위원회", "개인정보보호법", "개인정보위", "pipa",
    "망분리", "국외 이전", "데이터 이전 제한", "주권 클라우드",
    "컴플라이언스", "규제 준수", "심의", "인허가", "감독",
    "ai 윤리", "윤리 기준", "ai 모델 설명", "설명 가능성",
    "model card", "system card",
    "fda 승인", "regulatory approval",
    # v4.0: 한국 정부 부처 (정책 시그널)
    "산업부", "산업통상자원부", "과기정통부", "과학기술정보통신부",
    "중기부", "중소벤처기업부", "기재부", "기획재정부",
    "정책 지원", "전폭 지원", "정책 협력", "범정부",
]

MARKET_SIGNALS = [
    # M&A·투자
    "인수", "합병", "m&a", "인수합병", "지분 인수", "지분 매각",
    "투자 유치", "투자 단행", "투자 라운드", "시리즈 a", "시리즈 b",
    "시리즈 c", "시드 투자", "기업가치", "valuation",
    # 시장 진출·거점
    "한국 진출", "아시아 진출", "거점 확장", "거점 신설",
    "오피스 개설", "한국 법인", "지사 설립",
    "신사업", "신규 사업", "사업 확장",
    # 경쟁 구도
    "경쟁사", "경쟁 구도", "시장 점유율", "지배력",
    "ipo", "상장", "기업공개", "공모",
]

# v6.0: score_item()의 LEGAL 축 시그널 — RELEVANCE_LEGAL_SIGNALS와 의도가 다름.
# 이쪽은 "행동 가치 있는 법률 시그널"(로펌·소송·계약·자문 등) 위주.
SCORE_LEGAL_SIGNALS = [
    # 로펌·변호사
    "법무법인", "로펌", "변호사", "법무팀", "사내 변호사", "법무실",
    "광장", "김앤장", "태평양", "세종", "율촌", "지평", "화우",
    "harvey", "legora", "ironclad", "everlaw", "bhsn", "robin ai",
    # 소송·계약·판결
    "소송", "판결", "법원", "법원 판단", "기각", "각하",
    "계약", "계약서", "계약 검토", "약관",
    "자문", "법률 자문", "법무 자문",
    # 법률 AI 도입·사례
    "법률 ai", "리걸테크", "legal ai", "ai 변호사",
    "ai 계약 검토", "ai 법률 검색",
    # v6.15.12 추가: 사용자 핵심 도메인 — 판결문 공개·법조계 정책 논쟁
    "판결문", "판결문 공개", "판례 공개", "법조계", "법조 고심",
    "공개 확대", "상업활용", "데이터 활용", "데이터셋 공개",
    "지식재산권", "특허청", "kipo", "inta", "ip 업계",
    "법조계 논쟁", "법조계 우려", "공익적 활용", "민간 활용",
    # v6.15.19 추가: 사용자 명시 — AI×법조 교차 페어 키워드 강화
    # "AI 활용을 위한 판결문 공개, 로펌 AI 도입 및 활용 현황, 변호사 AI 활용 등
    #  법조계 전반이 AI와 교차되는 지점 → 가중치 高"
    "로펌 ai 도입", "로펌 ai 활용", "로펌 ai", "biglaw ai",
    "변호사 ai 활용", "변호사 ai", "ai 변호사 활용",
    "법무 ai 도입", "법무팀 ai", "법무 ai 활용", "사내 법무 ai",
    "판결문 ai", "판결문 데이터 활용", "판결문 학습", "판결문 데이터",
    "법조 ai", "법조계 ai", "법원 ai",
    "법률 데이터", "법률 데이터셋", "법률 코퍼스",
    "ai for lawyers", "legal ai adoption", "law firm ai adoption",
    "contract ai", "contract intelligence", "ai contract review",
]

# 행동 가치 없음 (강력한 NEGATIVE 시그널)
NEGATIVE_SIGNALS = [
    # 마케팅·프로모션
    "스탬프", "프로모션", "쿠폰", "이벤트", "선착순",
    "구독하면", "구독 시", "추가 제공", "사은품",
    "거래액 증가", "거래액 ↑", "매출 증가",
    # 광고 모델·연예
    "광고 모델", "광고모델", "전속모델", "전속 모델", "광고 캠페인",
    "발탁", "안방극장", "드라마 출연", "캐릭터 몰입도",
    "예능 출연", "토크쇼", "아이돌", "걸그룹", "보이그룹",
    "스포츠는 장비빨",
    # 단순 PR·MOU·체험 행사
    "맞손", "인재 양성 맞손", "체험 부스", "체험부스",
    "위탁운영 시작", "위탁운영 계약", "한국예선", "교두보",
    "선포식", "기념식", "현판식", "발족식",
    # 임원·총수 동정
    "회장 인사", "총수 회동", "임원 인사 이모저모",
    "내 책임", "탱크데이",
    # 일상 시세·증시
    "주가 폭락", "주가 급등", "52주 신저가", "52주 신고가",
    "코스피 강세", "코스닥 강세", "닛케이",
    # 라이프스타일·여행
    "맛집", "여행지 추천", "관광 명소", "캠핑", "낚시", "등산",
    # v4.2: 단순 행사·포럼·세미나 개최 PR (인사이트 없는 행사 알림)
    "포럼 개최", "세미나 개최", "워크숍 개최", "심포지엄 개최",
    "컨퍼런스 개최", "포럼 진행", "세미나 진행", "워크숍 진행",
    "포럼이 열렸", "세미나가 열렸", "행사를 개최", "행사가 열렸",
    "기조강연", "기조 강연", "환영사", "개회사", "축사",
    # v4.8: 지역 매체 회사·지자체 PR 일반 패턴 (사용자 직접 지적)
    # — v6.15.12: "본격화" 단독 제거. 정상 기사의 "자금전 본격화", "논쟁이
    #   본격화" 같은 자연 표현까지 false-positive로 잡아 사용자 핵심 도메인 기사가
    #   다수 score<35 drop됨. PR 패턴은 페어 키워드("양성 본격화", "도입 본격화")만 유지.
    "양성 본격화", "사업 본격화",
    "구축 나선다", "구축에 나선다", "구축을 본격화",
    "AI 접목", "AI 접목하는", "AI 도입 본격화",
    "딥테크 팁스", "팁스 선정", "지원사업 선정",
    "사업 선정", "공모사업 선정",
    "30년 노하우", "노하우 공개",
    "에듀테크", "에듀테크 학습", "AI 에듀테크",
    "전문인력 양성", "AI 인재 양성", "전문 인력 양성",
    "통합체계 구축", "통합 체계 구축",
    # v4.8: 일반 신문 1면 시황·경제면 PR (AI 부수적)
    "오늘의 1면", "1면 시황",
    "오늘의 브릿지경제", "오늘의 매일경제", "오늘의 한국경제",
    "실탄 장전", "조 단위 실탄",
    # v4.8: 지방선거·지자체 정치 (AI 무관)
    "vs 시장", "시장 vs", "양주시장", "도지사 후보",
    "지방선거", "공약 발표",
    # v6.1: 사용자 피드백 (2026-05-26) — 매거진/MOU/포럼/직무교육/경진대회/세미나 PR 차단
    # 6개 기사 대상 (예: topclass 6월호, 경북대-업스테이지 업무협약, 중기중앙회 AI 전환 해법,
    #              LG 1000명 직무교육, 개인정보위 가명정보 경진대회, 클라우드 월드 R&D 세미나)
    # — 매거진·잡지 preview
    "미리 보는", "월호", "월호 스페셜", "스페셜 이슈", "특집호", "이번 호",
    "topclass", "탑클래스",
    # — 대학-기업 업무협약 PR
    "와 업무협약", "와의 업무협약", "업무협약 체결",
    "ai 네이티브 캠퍼스", "ai 네이티브", "국가거점국립대",
    # — 포럼·컨퍼런스·해법 논의 PR
    "해법 논의", "방안 논의", "방안 마련 논의", "전환 해법",
    "컨퍼런스 개최", "컨퍼런스를 개최", "컨퍼런스가 개최",
    "지원 필요성", "필요성 제기", "협동조합 중심",
    # — 청년 직무교육·실전형 인재 PR
    "직무교육", "직무 교육", "직무역량",
    "실전형 인재", "취업준비 청년", "취업 준비 청년",
    "1000명 직무", "1000명 교육", "수료자", "수료 청년",
    "ax 전문가", "ax 자격", "ax 자격 취득",
    # — 정부·기관 경진대회·공모
    "경진대회", "경진 대회", "응모작", "응모작 공모",
    "공모한다고 밝혔다", "공모전 응모", "가명정보 경진",
    # — 산업 세미나·이벤트 PR
    "r&d 세미나", "ai r&d", "ai 활용 사례 부족", "활용 사례 부족",
    "투자 대비 roi", "투자자본수익률",
    "[#클라우드 월드]", "클라우드 월드", "씨플랫폼", "세종디엑스",
    # v6.4: 사용자 피드백 2차 (2026-05-26 KST 22:50) — 후순위 NEGATIVE 패턴만.
    # (BLACKLIST 직행 키워드는 별도로 blacklist.py에 추가)
    # — 책 출간 / 학술 발간 PR
    "출간", "도서 출간", "신간 출간", "신지평",
    "법연구소", "법연구원 출간", "데이터법 출간",
    "[책 소개]", "[신간]", "[도서]",
    # — 컨퍼런스 / 행사 예고 (BLACKLIST보다 약함 — 산학 contexts 보호)
    "krnet", "krnet 컨퍼런스", "ai 시대 인터넷",
    "내달 개막", "내달 22일", "다음달 개막", "다음 달 개막",
    # — 일반 투자 round-up 시리즈 (legaltech/AI 직접 무관)
    "[주간투자동향]", "주간투자동향", "주간 투자 동향",
    "[월간투자동향]", "월간투자동향",
    "[투자 동향]", "투자 동향]", "프리ipo 투자",
    # v6.4.1 fix: " 외" 제거 (외산/외부/해외 등 일반 단어 false-positive 발생).
    # "外" 한자만 유지 — 시리즈명 종결자로만 사용됨 (일반 텍스트엔 거의 안 등장).
    "外",
]


# ============================================================================
# v6.10 (Phase 3, 2026-05-27): BOOKMARK LEARNING BONUS
# ============================================================================
# 사용자(대형로펌 경영전략팀)가 daibfy.com에서 ⭐ 북마크한 기사·시사점 카드
# 30+35건의 통계 분석 기반. ground truth signal — 매뉴얼 분석 결과 [[daibfy-content-value-signal]].
#
# 구성:
#   1) BOOKMARK_BONUS_ENTITIES — 북마크에서 반복 등장한 핵심 회사·기관·인물
#   2) BOOKMARK_BONUS_KEYWORDS — 북마크 카드 title/body에서 반복 등장한 시장 구조 키워드
#   3) BOOKMARK_BONUS_SOURCES  — 직접 ⭐ 비율이 평균 이상인 매체
#
# score_item에 합산: 매칭 시 +2~+4점, 항목 전체 합 최대 +12점 cap.
# PR cap에는 적용 안 함 (cap 우회 방지).

# 핵심 회사·기관·인물 (매칭 시 +3점, 단어 단위)
BOOKMARK_BONUS_ENTITIES = {
    # 글로벌 리걸테크 / AI 플랫폼 (CEO 직접 관심)
    "harvey": 4, "legora": 4, "evenup": 4, "spotdraft": 3,
    "anthropic": 3, "openai": 3, "cloudflare": 3, "cerebras": 3,
    "ammune": 4, "icertis": 4, "informatica": 3, "snowflake": 3,
    # 국내 대형 로펌 (광장은 NEGATIVE에서 행사로 cap되지만 본질적으로 관심 대상)
    "광장": 3, "율촌": 4, "세종": 4, "김앤장": 4,
    # 국내 금융권 AI 거버넌스 선도 사례
    "KB금융": 3, "기업은행": 3, "수출입은행": 3, "신한": 2,
    # 공공·산업 AI 도입 선도 기관
    "한국부동산원": 3, "그리드원": 3,
    "산업부": 2, "금융위": 3, "금감원": 3, "법제처": 3,
    "LG에너지솔루션": 2, "한국 AI 교육진흥협회": 3,
    # 한국 리걸테크
    "엘박스": 4, "BHSN": 3, "아이율": 3,
    # 학계·연구
    "자블리": 3, "한국부동산원": 2, "DeepMind": 2,
}

# 시장 구조·전환 키워드 (매칭 시 +2점)
BOOKMARK_BONUS_KEYWORDS = {
    # 거버넌스 핵심
    "에이전트 스프롤": 3, "agent sprawl": 3, "섀도우 AI": 3, "shadow ai": 3,
    "에이전트 거버넌스": 3, "AI 거버넌스": 2, "거버넌스 공백": 3,
    "거버넌스 의무화": 3, "런타임 거버넌스": 3, "거버넌스 통행증": 3,
    # 책임·신뢰
    "책임 공백": 3, "책임 경계": 3, "책임 귀속": 2,
    "accountability": 2, "감사 추적": 2, "흐름 가시성": 2,
    # 시장 구조 재편
    "법률 AI": 2, "리걸테크": 2, "사내 변호사": 2, "contract intelligence": 3,
    "pre-litigation": 3, "도구 판매에서": 3, "업무 수탁": 3,
    "시간 기반 과금": 3, "성과 기반 과금": 3, "billable hour": 3,
    "가격 모델": 2, "비즈니스 모델 충돌": 3,
    # 평가·벤치마크
    "벤치마크": 2, "LAB": 2, "legal agent benchmark": 3,
    "평가 프레임워크": 2, "구성 타당성": 2,
    # 인지·역량
    "탈숙련": 3, "deskilling": 3, "brainrot": 3,
    "인지 능력 저하": 2, "역량 잠식": 2,
    # 멀티에이전트·인프라
    "멀티에이전트": 2, "다중 에이전트": 2, "오케스트레이션": 2,
    "interaction topology": 3, "에이전트 간 상호작용": 2,
    "sLLM": 2, "온프레미스": 2, "소버린 AI": 2, "sovereign ai": 2,
    # XAI·설명 가능성
    "XAI": 3, "설명 가능": 2, "explainable ai": 3,
    # AI 규제·법
    "AI 기본법": 2, "AI Act": 2, "EU AI Act": 2,
    "고위험 AI": 2, "고위험 분류": 2,
    "워터마크": 2, "메타데이터 표시": 2,
    # 가치 시그널 (insight marker)
    "선택이 아닌": 2, "통행증": 3, "사실상 표준": 2,
    "새 통행증": 3, "조달 자격": 2, "입찰 자격": 2,
    "역설": 2, "구조적 변화": 2, "구조적 전환": 2,
}

# 사용자가 직접 ⭐ 비율이 높은 매체 (매칭 시 +2점)
BOOKMARK_BONUS_SOURCES = {
    # 영문 리걸 (직접 북마크 다수)
    "legalcheek": 3, "lawnext": 3, "legalfutures": 3, "artificiallawyer": 3,
    # 영문 일반
    "lawsites": 3,
    # 국내 IT/AI 전문
    "aitimes.com": 2, "ddaily.co.kr": 2, "zdnet.co.kr": 2,
    "etnews.com": 2, "fntimes.com": 2,
    # 국내 경제지 (수준 있는 AI 보도)
    "sedaily.com": 2, "fnnews.com": 2, "hankyung.com": 2,
    # 학술
    "arxiv.org": 2,
}


def _normalize_text_for_match(text: str) -> str:
    """v4.5: 한국어/영어 따옴표·이상한 공백을 정규화해 키워드 매칭 신뢰도 향상.
    예: "AI 법정책포럼' 개최" 의 ' 때문에 "포럼 개최" 매칭 실패 → normalize 후 매칭 성공.
    """
    if not text:
        return ""
    # 한국어 인용부호 → 정규 따옴표
    text = text.translate(str.maketrans(
        "‘’“”«»「」『』",
        "''\"\"''\"\"\"\""
    ))
    # 따옴표·괄호·중점 등을 공백으로 (키워드 매칭에서 방해)
    import re as _re
    text = _re.sub(r"[''\"`·]+", " ", text)
    # 연속 공백 정리
    text = _re.sub(r"\s+", " ", text)
    return text.lower()


def count_signal_hits(text: str, signals: list) -> int:
    """텍스트에서 시그널 키워드 hit 개수 (중복 제외).
    v4.5: text가 이미 normalize됐다고 가정 (score_item에서 _normalize_text_for_match 적용)
    """
    return sum(1 for s in signals if s.lower() in text)


# v6.6: PR pattern detector — title regex + 조건부 AI 핵심 우회.
#       score_item과 is_relevant에서 호출.
from pr_patterns import classify_pr_pattern  # noqa: E402


def score_item(title: str, summary: str, date, categories: list, persona_score: int = None, source: str = "") -> int:
    """v4.3: AI 관련성 게이트 + 행동 시그널 기반 중요도 — 대형로펌 경영전략팀 페르소나.

    v6.8 (Phase 2): persona_score (0~10, LLM 평가) 가산형 보정.
        final = keyword_score + persona_score × 3 (max +30)
        persona_score=None이면 가산 없음 (enrich 안 받은 항목 또는 LLM 응답 누락).

    v6.10 (Phase 3, 2026-05-27): BOOKMARK_LEARNING 가산.
        BOOKMARK_BONUS_ENTITIES / _KEYWORDS / _SOURCES 매칭 점수 합산 (max +12).
        사용자가 ⭐ 북마크한 30+35건의 통계 기반 — ground truth value signal.
        PR cap 위반 항목엔 적용 안 함 (cap 우회 방지).

    설계 원칙:
      1) **AI 관련성 게이트** (v4.3): 4축 시그널은 모두 AI 컨텍스트 안에서만 의미.
         - 본문 AI 언급 0회 + 카테고리도 AI 무관 → score 0 (자동 drop)
         - AI 언급 1~2회 → 시그널 50% 인정 (약한 컨텍스트)
         - AI 언급 3회+ → 시그널 100% 인정 (강한 컨텍스트)
      2) base 30 → 행동 시그널 없으면 자동 cut-off 미만
      3) DECISION/REGULATORY/MARKET/LEGAL 4축 시그널 (각 +28/+28/+18/+12)
      4) NEGATIVE 시그널은 강력한 -30 또는 hard cap
      5) cut-off 35 미만은 fetch + prev_map 단계에서 자동 drop

    점수 구간 가이드:
      0~34   = drop (AI 무관 / 광고 / PR / 연예 / 일상)
      35~49  = 약한 시그널 (참고)
      50~69  = 의미 있는 시그널 (검토)
      70~89  = 명확한 행동 가치 (f/u 필요)
      90+    = 핵심 검토 사항 (즉시 보고)
    """
    score = 30.0

    # v6.6: PR pattern detector — 가장 먼저 실행.
    #   title prefix가 PR 시리즈로 명백한 경우 즉시 처리.
    #   조건부 prefix는 AI 핵심 키워드 카운트로 우회 판정.
    pr_verdict, pr_cap = classify_pr_pattern(title or "", summary or "")
    if pr_verdict == 'block':
        return 0  # BLACKLIST drop (cut-off 자동 미만)
    # 'cap'은 모든 가산 후 최종 단계에서 적용 (아래 끝 부분 참조)

    # v4.5: 한국어 따옴표·특수문자 정규화 후 매칭 (e.g. "포럼' 개최" → "포럼 개최")
    text = _normalize_text_for_match((title or "") + " " + (summary or ""))
    title_lower = _normalize_text_for_match(title or "")

    # === v4.3 AI 관련성 게이트 ===
    # 4축 시그널은 AI 컨텍스트 안에서만 의미. AI 언급 없으면 점수 자체를 강등.
    ai_mentions = (text.count(" ai ") + text.count("ai ") +
                   text.count(" ai") + text.count("인공지능") +
                   text.count("llm") + text.count("gpt") +
                   text.count("머신러닝") + text.count("딥러닝"))
    # AI 무관 article 자동 drop (papers/legaltech/models/coding/infra 카테고리는 AI 도메인 내재라 보호)
    # v6.15.17: 신규 카테고리 (models/coding/infra)도 AI 도메인 내재라 게이트 면제.
    #   예: "Midjourney v8 출시" — AI 단어 없어도 models 카테고리 부여되면 보호.
    if ai_mentions == 0:
        ai_intrinsic_cats = {"papers", "legaltech", "models", "coding", "infra"}
        # v6.15.21: SUPER_BOOST 매칭은 AI gate 면제 (사용자 명시 어젠다 보호)
        if not any(c in ai_intrinsic_cats for c in categories) and not _has_super_boost(text):
            return 0  # AI 키워드 0회 → score 0 (cut-off 자동 drop)
    # 시그널 multiplier: AI 컨텍스트 강도에 따라
    if ai_mentions >= 3:
        signal_multiplier = 1.0
    elif ai_mentions >= 1:
        signal_multiplier = 0.7  # 약한 AI 컨텍스트도 의미 있게 인정 (1~2회)
    else:
        signal_multiplier = 0.5  # papers/legaltech 카테고리 보호받는 경우
    # papers/legaltech/models/coding/infra는 AI/리걸테크 도메인 자체라 multiplier 보강
    # v6.15.17: 신규 카테고리도 핵심 도메인이라 0.85 보강 적용
    core_ai_cats = {"papers", "legaltech", "models", "coding", "infra"}
    if any(c in core_ai_cats for c in categories):
        signal_multiplier = max(signal_multiplier, 0.85)
    # v6.15.13: 한국 매체 title-only RSS 보호 — LEGAL/REGULATORY signal 2+이면
    # 사용자 핵심 도메인으로 인식 → multiplier 보강 (categorize가 못 잡은 경우 대비)

    # === v4.0 행동 시그널 매트릭스 (각 축 최대 +25) ===
    decision_hits = count_signal_hits(text, DECISION_SIGNALS)
    regulatory_hits = count_signal_hits(text, REGULATORY_SIGNALS)
    market_hits = count_signal_hits(text, MARKET_SIGNALS)
    legal_hits = count_signal_hits(text, SCORE_LEGAL_SIGNALS)  # v6.0: LEGAL_SIGNALS 분리

    # hits → strength (1 - 0.78^n): 1→0.22, 2→0.39, 3→0.53, 4→0.63, 5→0.71, 6→0.78
    def strength(n: int) -> float:
        return round(1.0 - 0.78 ** n, 3) if n > 0 else 0.0

    decision_s = strength(decision_hits)
    regulatory_s = strength(regulatory_hits)
    market_s = strength(market_hits)
    legal_s = strength(legal_hits)

    # v4.3 가중치 + AI 관련성 게이트 — 시그널은 AI 컨텍스트와 페어일 때만 인정
    # signal_multiplier:
    #   1.0 = AI 언급 3+ (정상 AI 기사)
    #   0.5 = AI 언급 1~2 (약한 AI 컨텍스트, 보너스 절반)
    #   0.3 = AI 무관이지만 papers/legaltech 카테고리 보호
    score += decision_s   * 28 * signal_multiplier  # 의사결정 (도입·통제·재설계)
    score += regulatory_s * 28 * signal_multiplier  # 규제 (정책·법안·컴플라이언스)
    score += market_s     * 18 * signal_multiplier  # 시장구조 (M&A·진출·투자)
    score += legal_s      * 12 * signal_multiplier  # 법률·로펌 (보조 시그널)

    total_signal = decision_s + regulatory_s + market_s + legal_s

    # === v4.6 MARKET 단독 dominance cap ===
    # 의도: 대형로펌 경영전략팀 페르소나 — AI adoption·governance 고민이 핵심.
    # MARKET 시그널만 강함 + LEGAL/REGULATORY/DECISION 부족 → 단순 산업 투자 트렌드.
    # 하크 1조 시리즈A 같은 case가 상단 노출 안 되도록 cap 적용.
    if market_s >= 0.5 and (decision_s + regulatory_s + legal_s) < 0.4:
        score = min(score, 55)  # MARKET 단독 = 참고 구간 상한

    # === v4.5 NEGATIVE 시그널 — 강화된 단계적 감점 ===
    # 의도: 명백한 광고/연예/PR은 drop. 경쟁사 행사는 살리되 절대 상단 X (45점 cap).
    # v6.15.13: 사용자 핵심 도메인 카테고리(legaltech/papers/funding)는 NEGATIVE cap 완화.
    #   "AI시대 판결문 두고 법조계 고심" 본문에 "축사" 한 단어가 들어 있다는 이유로
    #   score 32까지 떨어지던 false-positive 해결. legaltech 도메인은 본문에
    #   부수적 PR 표현이 들어가도 핵심 가치는 보존되어야 함.
    negative_hits = count_signal_hits(text, NEGATIVE_SIGNALS)
    is_core_domain = ("legaltech" in categories or "papers" in categories
                       or "funding" in categories)
    if negative_hits >= 1:
        if is_core_domain:
            # 핵심 도메인은 NEGATIVE cap 약화 — drop 안 시키되 상단 cap만 적용
            if total_signal < 0.5:
                score = min(score, 38)  # 18 → 38 (cut-off 35 약간 위)
            elif total_signal < 1.0:
                score = min(score, 50)  # 28 → 50
            else:
                score = min(score, 65)  # 45 → 65 (강한 시그널 + 핵심 도메인)
        else:
            # 일반 항목 — 기존 빡빡한 cap 유지
            if total_signal < 0.5:
                score = min(score, 18)
            elif total_signal < 1.0:
                score = min(score, 28)
            else:
                score -= 25
                score = min(score, 45)

    # === v4.0 AI 단순 언급 자동 강등 (v4.3: ai_mentions 위에서 이미 계산됨) ===
    if ai_mentions <= 2 and total_signal < 0.3:
        score = min(score, 22)

    # 시그널 0개 — 행동 가치 없음
    if total_signal < 0.1:
        score = min(score, 25)

    # v4.8: AI mention은 많은데 의미 시그널 약한 케이스 cap
    # — 지역 매체 PR (춘천시 AI 인재 양성, 회사 + AI 통합체계 구축 등)
    # — AI를 여러 번 언급하지만 실제 행동 가치(DECISION/REGULATORY/MARKET/LEGAL) 약함
    if ai_mentions >= 3 and total_signal < 0.4:
        score = min(score, 33)  # 참고 구간 아래로 강등 (cut-off 35 미만)

    # === 카테고리 보너스 (정상 컨텐츠 보호) ===
    # v6.15.19: legaltech 가중치 12→16 인상. 사용자 정책 — AI×법조 교차 (판결문 공개,
    #   로펌 AI 도입, 변호사 AI 활용 등 법조 전반)는 상단 노출. 단순 ai-industry보다 우선.
    if "legaltech" in categories:
        score += 16  # 리걸테크 + AI×법조 교차 — 사용자 핵심 도메인, 상단 노출 보장
    if "papers" in categories:
        score += 8   # 학술 논문
    if "funding" in categories:
        score += 6   # 자본 흐름
    # v6.15.17: 신규 카테고리 보너스 — AI 모델 비즈니스·개발자 도구·인프라
    if "models" in categories:
        score += 10  # 모델 release/벤치마크/가격 — 사용자 핵심 관심 (legaltech 다음 우선순위)
    if "coding" in categories:
        score += 7   # AI 코딩 도구 (Cursor/Copilot)
    if "infra" in categories:
        score += 7   # AI 칩·인프라 (Groq/Cerebras)

    # === 본문 깊이 보너스 ===
    summary_len = len(summary or "")
    if summary_len >= 80:
        import math as _math
        score += min(6.0, _math.log2(summary_len / 40.0) * 1.2)
    else:
        score -= 3

    # === 제목 길이 ===
    title_len = len((title or "").strip())
    if 20 <= title_len <= 80:
        score += 1
    elif title_len > 120:
        score -= 1

    # === 시간 가중치 (신선도) ===
    if date:
        now = datetime.now(timezone.utc)
        if isinstance(date, str):
            date = parse_date_safe(date)
        if date and date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        if date:
            delta_h = (now - date).total_seconds() / 3600
            if delta_h < 24:
                score += 10
            elif delta_h < 72:
                score += 5
            elif delta_h < 168:
                score += 2

    # === PROMO 패턴 hard cap (옛 로직 유지) ===
    buckets = detect_score_buckets(title, summary)
    if buckets["promo"] > 0 and total_signal < 0.5:
        score = min(score, 25)  # PROMO 단독은 강제 강등

    # === v6.4: NEGATIVE final cap re-apply ===
    # 의도: 위 v4.5 NEGATIVE cap (line ~877) 이후에 카테고리 보너스(legaltech +12, funding +6),
    #       recency 보너스(+10), 본문 깊이 보너스(+6) 등이 더해져 cap을 우회하는 버그 해결.
    #       모든 가산 후 다시 NEGATIVE cap 적용 → 후순위 강등이 실효성 있게 동작.
    # v6.15.13: 핵심 도메인 카테고리는 final cap도 약화 (위 위쪽 cap과 일관)
    if negative_hits >= 1:
        if is_core_domain:
            if total_signal < 0.5:
                score = min(score, 38)
            elif total_signal < 1.0:
                score = min(score, 50)
            else:
                score = min(score, 65)
        else:
            if total_signal < 0.5:
                score = min(score, 18)
            elif total_signal < 1.0:
                score = min(score, 28)
            else:
                score = min(score, 45)

    # === v6.6: PR pattern detector final cap ===
    # title prefix가 PR 시리즈(NEGATIVE/조건부)로 분류된 경우 최종 cap 적용.
    # (block은 위에서 이미 score 0 처리됨.)
    if pr_verdict == 'cap' and pr_cap is not None:
        score = min(score, pr_cap)

    # === v6.8 → v6.15.22 (Phase A): persona_score dominant 재설계 ===
    # 사용자 지적(2026-05-28): "이렇게 강제 조정하면 끝도 없지 않겠어? 애초에 중요도
    # 산정 기준 자체를 보완해야 되는 거 아니야?"
    # 본질: keyword hit 기반 score는 표현 다양성·의미 매칭에 약함. LLM 페르소나 평가가
    # 사용자 가치 판단을 더 정확히 표현하므로, persona_score 비중을 압도적으로 올림.
    #
    # 변경: persona_score × 3 (max +30) → × 8 (max +80)
    # 의미: LLM이 10점 부여 시 +80점 → score의 dominant 결정 요소가 됨
    #       (기존 keyword 점수 30~60점은 보조 시그널로 강등)
    # 단 PR cap 위반 항목엔 적용 안 함 (cap 우회 방지).
    if persona_score is not None and pr_verdict != 'cap':
        try:
            ps = int(persona_score)
            if 0 <= ps <= 10:
                score += ps * 8
        except (ValueError, TypeError):
            pass

    # === v6.15.21: 핵심 법령 가중치 (사용자 정책 — 2026-05-28) ===
    # AI 기본법 → 무조건 +12 (AI 도메인 자체이므로 조건 없이 가중치)
    # 정보통신망법·개인정보보호법 → AI 관련일 때만 +12
    #   (ai_mentions ≥ 1 OR legaltech/policy/governance 카테고리 보유)
    # 시행령·시행규칙 매칭 별도 처리(_is_ai_basic_law·_is_conditional_law에 포함됨).
    # 두 조건 동시 충족 시(예: AI 기본법 + 개인정보보호법 동시 등장) 최대 +18로 cap.
    law_bonus = 0
    text_lower_for_law = text  # 이미 lower + normalize됨
    if _is_ai_basic_law(text_lower_for_law):
        law_bonus += 12
    if _is_conditional_law(text_lower_for_law):
        # AI 관련 조건: ai_mentions ≥ 1 또는 AI 도메인 카테고리 보유
        ai_related_cats = {"legaltech", "policy", "governance", "gov_policy",
                           "papers", "models", "coding", "infra"}
        if ai_mentions >= 1 or any(c in ai_related_cats for c in categories):
            law_bonus += 12
    if law_bonus > 0:
        law_bonus = min(law_bonus, 18)  # 동시 충족도 18로 cap
        score += law_bonus
        # v6.15.21: 핵심 법령 매칭 항목 floor 78 — monthly TOP 80 cut(76) 통과 보장
        # (AI 기본법 단독 매칭이 SUPER_BOOST에 안 잡혀도 monthly 시사점 진입)
        if score < 78:
            score = 78

    # === v6.15.21 SUPER_BOOST: 사용자 명시 8개 어젠다 강력 보호 ===
    # 판결문 공개·공정위 AI 실태조사·개인정보 처리 특례 등은 짧은 본문이어도
    # daily/weekly/monthly 시사점 카드 후보 풀에 무조건 진입.
    #
    # 실제 시사점 cut-off (2026-05-28 daibfy.com 측정):
    #   daily TOP 30 cut: 81 / weekly TOP 50 cut: 79 / monthly TOP 80 cut: 76
    # SUPER_BOOST 매칭 항목은 위 cut 모두 통과 보장 — score floor 85.
    # (LLM은 후보 풀 안에서 prompt 우선순위 룰로 1-3번 카드 배치)
    if _has_super_boost(text):
        score += 18
        if score < 85:
            score = 85  # daily/weekly/monthly TOP N 모두 진입 보장

    # === v6.15.19/.21: 핵심 도메인 카테고리 score floor (cut-off 통과 보장) ===
    # 사용자 정책: "기존에 걸러지던 AI 일반 소식도 스크롤로 확인할 수 있도록".
    # 신규 카테고리(models/coding/infra)와 papers/legaltech는 본질적으로 사용자
    # 관심 도메인이므로 borderline score(29-33)여도 cut-off 35 통과 보장 → 하단
    # 노출. noise는 카테고리 안 잡혀 floor 미적용 → 기존 drop 정책 유지.
    # v6.15.21: AI + 정보통신망법/개인정보보호법 매칭은 짧은 본문이어도 floor 35 적용.
    floor_cats = {"papers", "legaltech", "models", "coding", "infra"}
    if any(c in floor_cats for c in categories):
        if score < 35:
            score = 35  # cut-off 통과 보장 (점수 차등으로 자연스럽게 하단 노출)
    elif _is_conditional_law(text) and ai_mentions >= 1:
        # AI 관련 정보통신망법·개인정보보호법은 짧은 본문이어도 cut-off 통과
        if score < 35:
            score = 35

    # === v6.10 (Phase 3): BOOKMARK_LEARNING 가산 ===
    # 사용자가 ⭐ 북마크한 30+35건 통계 분석 기반 — ground truth value signal.
    # 매칭: ENTITIES (회사·기관) + KEYWORDS (시장 구조) + SOURCES (선호 매체).
    # max +12 cap. PR cap 위반 항목엔 적용 안 함.
    if pr_verdict != 'cap':
        bookmark_bonus = 0
        # text는 이미 normalize됨 (line ~883). source는 lowercase.
        src_lower = (source or "").lower()
        # 1) entities (text에 회사·기관명 매칭 — case-insensitive substring)
        text_lc = text  # 이미 lower
        for ent_kw, weight in BOOKMARK_BONUS_ENTITIES.items():
            if ent_kw.lower() in text_lc:
                bookmark_bonus += weight
        # 2) keywords (시장 구조 키워드)
        for kw, weight in BOOKMARK_BONUS_KEYWORDS.items():
            if kw.lower() in text_lc:
                bookmark_bonus += weight
        # 3) sources (선호 매체 도메인)
        if src_lower:
            for src_token, weight in BOOKMARK_BONUS_SOURCES.items():
                if src_token in src_lower:
                    bookmark_bonus += weight
                    break  # source는 1개 매체만 매칭 (중복 방지)
        # cap +12
        bookmark_bonus = min(bookmark_bonus, 12)
        score += bookmark_bonus

    return max(0, min(150, int(round(score))))


def normalize_url(url: str) -> str:
    """URL 정규화 (utm 등 트래킹 파라미터 제거)"""
    if not url:
        return ""
    url = re.sub(r"[?&](utm_[^=]+|fbclid|gclid|mc_cid|mc_eid)=[^&]*", "", url)
    url = re.sub(r"\?$", "", url)
    return url.strip()
