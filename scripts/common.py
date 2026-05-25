"""
공통 유틸리티 — 텍스트 정제, 날짜 파싱, 카테고리 분류, 점수 산정
"""

import html
import re
from datetime import datetime, timezone

from dateutil import parser as dateparser


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
    ],
    "domestic": [
        # 출처 기반이 더 정확하지만 키워드도 보강
        "한국", "korea ", "korean ", "korean firm", "korean lawyer",
    ],
    "policy": [
        "regulation", "regulator", "compliance",
        "eu ai act", "white house ai", "fcc", "ftc ", "doj ",
        "executive order", "ai standards",
        # 한국어 — "규제·법안" 단독은 일반 정치 뉴스 잡으니 AI/리걸 맥락 구문만
        "ai 규제", "ai규제", "데이터 규제", "개인정보 규제",
        "ai 거버넌스", "ai act", "ai 윤리", "알고리즘 규제",
        "ai기본법", "ai 기본법", "ai 법안",
    ],
    "ai-industry": [
        # 회사명 — 다른 카테고리에 속하지 않는 경우의 fallback
        "openai", "anthropic", "claude ", "gpt-", "chatgpt", "gemini",
        "deepmind", "meta ai", "llama", "mistral", "xai", "grok",
        "nvidia ai", "microsoft ai", "perplexity",
    ],
}

# 카테고리 우선순위 (정렬 시 사용)
CATEGORY_PRIORITY = {
    "papers": 1,
    "legaltech": 2,
    "funding": 3,
    "adoption": 4,
    "policy": 5,
    "product": 6,
    "domestic": 7,
    "ai-industry": 8,
}

# 사전 컴파일
COMPILED_KEYWORDS = {
    cat: [kw_regex(kw) for kw in kws]
    for cat, kws in CATEGORY_KEYWORDS.items()
}


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
    # AI 도메인 명확
    "생성형 ai", "생성ai", "인공지능", "ai 에이전트", "agentic ai",
    "multi-agent", "autonomous agent",
    "llm",
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
]

# AI 시그널 (도메인 시그널과 조합되어야 통과)
AI_SIGNALS = [
    "ai", "인공지능", "ml", "machine learning",
    "agent", "에이전트", "model",
    "gpt", "claude", "gemini", "llm",
]

# 도메인 시그널 (AI 시그널과 조합되어야 통과)
LEGAL_SIGNALS = [
    "법률", "리걸", "법무", "변호사", "로펌", "법조",
    "계약", "소송", "판례", "법원", "특허",
    "legal", "lawyer", "law firm", "litigation", "patent",
]

# 정치·선거·일반 시사 등 무관한 뉴스 차단 (즉시 제외)
BLACKLIST_KEYWORDS = [
    # 선거·정치
    "선거", "후보", "공약", "지지율", "당선",
    "여당", "야당", "민주당", "국민의힘", "정의당", "더민주",
    "지방의회", "도의회", "시의회",
    "지방선거", "교육감", "도지사", "시장 후보",
    "정근식", "맹수석", "진동규", "오석진", "성광진",
    # 일반 시사·사건
    "사망", "체포", "기소", "구속", "성폭행", "살해", "방화",
    "교통사고", "화재", "흉기",
    "급식 중단", "급식대란",
    # 연예·스포츠
    "연예인", "아이돌", "k-pop", "kpop", "야구", "축구",
    # 종교
    "교황",  # 일반적으로 AI 관련 아님 (예외 케이스는 본문에서 다른 강력 신호로 통과)
    # 운세·라이프·건강 컬럼 (v2.7)
    "운세", "mbti", "오늘의 운세", "이번주 운세", "별자리",
    "하루건강", "장마철", "불면증", "다이어트", "혈압", "당뇨",
    # 부음·장례
    "부음", "별세", "모친상", "부친상", "장모상", "장인상",
    "장례식장", "발인", "빈소", "조문",
    # 상표·브랜드 마케팅 (AI 관련성 약함)
    "라이프집", "집덕후", "향기 굿즈", "라이프스타일 커뮤니티",
    "상표 출원", "상표 등록", "지정상품", "디퓨저", "핸드크림",
    # 일반 라이프스타일·취미
    "캠핑", "차박", "낚시", "등산", "맛집", "여행지 추천",
]


# Naver hankookilbo 등에서 자동 생성한 AI 보일러플레이트 기사 차단
# (제목·요약에 "AI"가 등장하지만 실제 콘텐츠는 AI 관련 없음)
BOILERPLATE_PATTERNS = [
    "이 기사는 생성형 ai 로 제작",
    "이 기사는 생성형 ai로 제작",
    "이 기사는 ai로 작성",
    "ai 활용 준칙을 준수합니다",
    "본 기사는 ai가 작성",
    "ai가 자동으로 작성한",
]


def is_relevant(title: str, summary: str, source_type: str = "rss") -> bool:
    """관련성 체크 — Naver/Google News 결과 + 모든 소스에 보일러플레이트/블랙리스트 적용.

    규칙 (v2.7):
    0. AI 생성 보일러플레이트(생성형 AI로 제작) 패턴이 본문에 있으면 모든 소스에서 즉시 제외
    1. 블랙리스트 키워드가 제목 또는 요약에 있으면 즉시 제외 (Naver/Google News만)
    2. STRONG_KEYWORDS 중 하나라도 있으면 통과
    3. AI_SIGNALS + LEGAL_SIGNALS 둘 다 있으면 통과 (법률 AI 관련)
    4. 그 외 제외
    """
    text = (title + " " + summary).lower()
    title_lower = title.lower()

    # 0. AI 생성 보일러플레이트 — 모든 소스에서 즉시 차단 (Naver/hankookilbo 등의 lifestyle 자동기사)
    for pat in BOILERPLATE_PATTERNS:
        if pat in text:
            return False

    # RSS·arXiv는 보일러플레이트만 체크하고 통과
    if source_type not in ("naver", "google_news"):
        return True

    # 1. 블랙리스트 — 제목 또는 요약에 있으면 즉시 제외
    for kw in BLACKLIST_KEYWORDS:
        if kw in title_lower or kw in text:
            return False

    # 2. Strong keyword 단독 통과
    for kw in STRONG_KEYWORDS:
        if kw in text:
            return True

    # 3. AI 시그널 + 도메인 시그널 조합 (둘 다 있어야)
    has_ai = any(kw in text for kw in AI_SIGNALS)
    has_legal = any(kw in text for kw in LEGAL_SIGNALS)
    if has_ai and has_legal:
        return True

    # 4. 도메인 시그널 단독은 제외 (예: 단순 "변호사 회견" 같은 정치 뉴스)
    # 5. AI 시그널 단독도 STRONG에 없으면 제외 (모호한 일반 표현 차단)
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


def parse_date_safe(date_str: str):
    """다양한 형식의 날짜를 datetime으로 변환. 실패 시 None."""
    if not date_str:
        return None
    try:
        dt = dateparser.parse(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
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

    # 우선순위 순으로 정렬, 최대 3개
    sorted_cats = sorted(cats, key=lambda c: CATEGORY_PRIORITY.get(c, 99))
    return sorted_cats[:3]


def score_item(title: str, summary: str, date, categories: list) -> int:
    """간단한 중요도 점수 (0~100)"""
    score = 50
    text = (title + " " + summary).lower()

    for kw, pts in HIGH_VALUE_KEYWORDS.items():
        if kw in text:
            score += pts

    if "legaltech" in categories:
        score += 8
    if "papers" in categories:
        score += 5
    if "funding" in categories:
        score += 4
    if "domestic" in categories:
        score += 3

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

    # v2.7: 0~150 범위 — 시장 분석/정책 공백 같은 다중 시그널 기사가
    # 단순 출시 뉴스보다 충분히 높게 노출되도록 캡 상향 (UI 표시는 그대로 숫자).
    return max(0, min(150, score))


def normalize_url(url: str) -> str:
    """URL 정규화 (utm 등 트래킹 파라미터 제거)"""
    if not url:
        return ""
    url = re.sub(r"[?&](utm_[^=]+|fbclid|gclid|mc_cid|mc_eid)=[^&]*", "", url)
    url = re.sub(r"\?$", "", url)
    return url.strip()
