"""
v6.15.35 (P2-5): 공통 회사·제품명 단일 소스(SSOT).

배경(감사 P2-5): dedupe_similar·pr_patterns·entity_extractor가 회사·제품·로펌 이름을
  각자 중복 보유 → 신규 회사 추가 시 일부 모듈만 갱신되는 동기화 누락이 구조적으로 발생.
해결: 공통 회사·제품·로펌 이름을 여기 한 곳에 모은다. 신규 회사는 이 파일만 갱신하면
  import한 모듈로 전파된다.

원칙:
- 매칭 키는 소문자(영문)·원형(한글). substring/경계 매칭에 그대로 쓰일 수 있는 형태.
- 각 모듈은 자기 용도에 맞는 그룹 + 자기 도메인 extra를 조합한다(여기엔 도메인 키워드·
  정책·이벤트·제조사 같은 비(非)회사 항목은 두지 않는다).
- 동작 보존: 이 파일은 기존 모듈 리스트의 회사·제품·로펌 부분을 합집합으로 정규화한 것.
"""

# ── AI 프론티어 회사 (bare 회사명) ───────────────────────────────
AI_COMPANIES = [
    "openai", "anthropic", "perplexity", "mistral", "meta", "microsoft",
    "nvidia", "deepseek", "qwen", "deepmind", "cohere", "xai", "grok",
    "stability ai", "scale ai", "hugging face", "huggingface",
]

# ── AI 제품·모델 ────────────────────────────────────────────────
AI_PRODUCTS = [
    "claude", "claude opus", "claude sonnet", "claude haiku",
    "chatgpt", "gpt-4", "gpt-5", "gpt-6",
    "gemini", "llama", "gemma", "mythos", "copilot",
]

# ── 리걸테크 회사·제품 ──────────────────────────────────────────
LEGALTECH_COMPANIES = [
    "harvey", "legora", "ironclad", "spellbook", "robin ai",
    "mike legal", "mike oss", "everlaw", "casetext", "evenup",
    "hebbia", "deepjudge", "bhsn", "lboxai", "엘박스", "인텔리콘",
    "로앤컴퍼니", "로앤굿", "케이스노트", "casenote",
]

# ── 한국 7대 로펌 (단축명 + 법무법인 표기) ──────────────────────
KOREAN_LAW_FIRMS = [
    "광장", "김앤장", "태평양", "세종", "율촌", "지평", "화우",
    "법무법인 광장", "법무법인 김앤장", "법무법인 태평양",
    "법무법인 세종", "법무법인 율촌", "법무법인 지평", "법무법인 화우",
]

# 편의용 합집합 (회사·제품·리걸테크 — 로펌 제외)
AI_AND_LEGALTECH = AI_COMPANIES + AI_PRODUCTS + LEGALTECH_COMPANIES
