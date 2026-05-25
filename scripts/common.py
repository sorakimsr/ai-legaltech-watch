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
        # 회사명 (확실한 시그널)
        "harvey", "legora", "mike oss", "hebbia", "ironclad", "spellbook",
        "robin ai", "evenup", "deepjudge", "lexis nexis", "thomson reuters",
        "bhsn", "lboxai", "엘박스", "인텔리콘", "로앤컴퍼니", "로앤굿",
        # 도메인 키워드
        "legal ai", "legal tech", "legaltech", "리걸테크", "리걸 ai", "법률 ai",
        "law firm", "law firms", "big law", "in-house counsel",
        "contract ai", "contract intelligence", "clm", "e-discovery",
        "변호사", "로펌", "계약 검토", "법무",
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
# 관련성 필터 (Naver/Google News 결과 사후 검증)
# ============================================================================
# AI·리걸테크와 관련 있다고 볼 수 있는 핵심 키워드.
# Naver Search API 같은 키워드 검색은 무관한 뉴스도 잡으므로 사후 필터링.
RELEVANCE_KEYWORDS = [
    # AI 일반
    "ai ", " ai", "인공지능", "생성형 ai", "생성 ai",
    "llm", "agent", "agentic", "에이전트", "ai 에이전트",
    "gpt", "chatgpt", "claude", "gemini", "llama", "mistral",
    "openai", "anthropic", "deepmind", "meta ai", "nvidia",
    "perplexity", "hugging face", "stability",
    "machine learning", "deep learning", "neural", "model",
    "transformer", "diffusion", "rag", "retrieval",
    # 리걸테크
    "법률", "리걸", "법무", "변호사", "로펌", "계약",
    "legal", "lawyer", "law firm", "biglaw", "litigation",
    "harvey", "legora", "mike oss", "hebbia", "ironclad", "spellbook",
    "bhsn", "로앤컴퍼니", "로앤굿", "엘박스", "인텔리콘",
    # 투자·산업
    "스타트업", "유니콘", "투자 유치",
    "series a", "series b", "valuation", "startup",
    # 규제·정책 (AI 맥락)
    "ai 규제", "ai 거버넌스", "ai 법", "ai 윤리",
    "ai regulation", "ai governance", "ai ethics",
]

# 정치·선거·일반 시사 등 무관한 뉴스 차단 (Naver/Google News 사후 필터)
BLACKLIST_KEYWORDS = [
    # 선거·정치
    "지방선거", "대선", "총선", "보궐선거", "재선거",
    "후보 공약", "공약 발표", "지지율",
    "여당", "야당", "민주당", "국민의힘", "정의당", "더민주",
    "지방의회", "도의회", "시의회",
    # 일반 시사
    "사망", "사고", "체포", "기소", "구속",
    "교통사고", "화재",
    # 연예·스포츠
    "연예인", "아이돌", "k-pop", "kpop",
]


def is_relevant(title: str, summary: str, source_type: str = "rss") -> bool:
    """관련성 체크 — Naver/Google News 결과만 사후 필터링.
    RSS·arXiv는 이미 큐레이션된 소스라 통과."""
    if source_type not in ("naver", "google_news"):
        return True
    text = (title + " " + summary).lower()
    # 블랙리스트 매칭이면 즉시 제외
    for kw in BLACKLIST_KEYWORDS:
        if kw in text:
            return False
    # 핵심 키워드 매칭 필수
    for kw in RELEVANCE_KEYWORDS:
        if kw in text:
            return True
    return False


HIGH_VALUE_KEYWORDS = {
    "harvey": 15, "legora": 15, "mike oss": 15, "mike legal": 12,
    "openai": 10, "anthropic": 10, "gpt-5": 12, "claude opus": 10, "claude sonnet": 8,
    "raises $": 8, "funding": 6, "valuation": 8, "billion": 10, "series ": 6,
    "launches": 6, "announces": 5, "introduces": 5, "unveils": 6,
    "breakthrough": 10, "state-of-the-art": 8, "sota": 8,
    "리걸테크": 10, "법률 ai": 8, "리걸 ai": 10,
    "한국": 4, "korea": 4,
    "agent": 5, "agentic": 6, "multi-agent": 7,
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

    return max(0, min(100, score))


def normalize_url(url: str) -> str:
    """URL 정규화 (utm 등 트래킹 파라미터 제거)"""
    if not url:
        return ""
    url = re.sub(r"[?&](utm_[^=]+|fbclid|gclid|mc_cid|mc_eid)=[^&]*", "", url)
    url = re.sub(r"\?$", "", url)
    return url.strip()
