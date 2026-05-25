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
    "ai-industry": 7,
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
    # 선거·정치 — 일반 키워드
    "선거", "후보", "공약", "지지율", "당선",
    "여당", "야당", "민주당", "국민의힘", "정의당", "더민주",
    "지방의회", "도의회", "시의회",
    "지방선거", "교육감", "도지사", "시장 후보", "도지사 후보", "경기지사",
    "31개 시·군", "원팀", "원팀 선거", "원팀 승리", "광역단체장",
    # 선거·정치 — 인물명
    "정근식", "맹수석", "진동규", "오석진", "성광진",
    "추미애", "이재명", "한동훈", "윤석열", "오세훈", "조국", "김동연",
    # 일반 시사·사건
    "사망", "체포", "기소", "구속", "성폭행", "살해", "방화",
    "교통사고", "화재", "흉기",
    "급식 중단", "급식대란",
    # 연예·스포츠
    "연예인", "아이돌", "k-pop", "kpop", "야구", "축구",
    # 종교
    "교황",
    # 운세·라이프·건강 컬럼 (v2.7 확장)
    "운세", "mbti", "오늘의 운세", "이번주 운세", "별자리", "사주", "타로",
    "하루건강", "장마철", "불면증", "다이어트", "혈압", "당뇨", "갱년기",
    "열돔", "폭염", "한파", "장마", "꽃샘추위", "황사",  # 기상·날씨 lifestyle 컬럼
    # v2.7.5: 기상·재해 키워드 대폭 확장 (폭우/호우 케이스 차단)
    "폭우", "호우", "호우경보", "호우주의보", "물폭탄", "출근길",
    "퇴근길", "남해안", "동해안", "서해안", "남부지방", "중부지방",
    "강수량", "강풍", "강풍주의보", "강설", "폭설", "대설",
    "산불", "태풍", "지진", "쓰나미", "한파주의보", "강추위",
    "비 예보", "눈 예보", "기상청", "예년 대비", "관측 이래",
    "150mm", "200mm", "100mm",  # 강수량 단위
    "수해", "침수", "역대 최고", "역대 최대 강수",
    # v2.7.5: 스포츠 토토·복권·도박
    "토토", "로또", "스포츠토토", "로또복권",
    # v2.7.5: 부동산·시세 lifestyle
    "아파트값", "전세값", "월세값", "분양가",
    # v2.7.5: 정치/선거 추가 (경기지사·예상 강수량 케이스 보강)
    "경기지사", "경기지사 후보", "경기 대도약", "대도약 추진",
    "민주당 후보들", "원팀 승리", "원팀 선거",
    "예상 강수량", "예상강수량",
    # v2.7.5: 헤드라인 보일러플레이트 (AI 자동 생성 lifestyle 컬럼 헤드라인 확장)
    "[ai 와 함께", "[ai와 함께", "[ai가 쓰는", "[ai 와 함께 쓴",
    "ai 와 함께 쓴 날씨", "ai와 함께 쓴 날씨",
    "그여름 홍천", "올해도 열돔",
    "[mbti 오늘의 운세]", "[mbti오늘의 운세]",
    "장마철 심해지는", "줄어든 햇빛",
    # v2.7.5: 강수량 단위 헤드라인
    "150㎜", "150mm", "100㎜", "100mm", "80㎜", "80mm", "50㎜",
    # v2.7.8: 지자체 AI 유치·홍보 패턴 (광주·부산·대구·인천·대전·울산·세종·전남·경북 등)
    "ai 허브 유치", "허브 유치 추진",
    "ai 수도", "ai 수도로", "글로벌 ai 수도", "글로벌 ai 도시",
    "ai 거점 유치", "ai 허브 도시", "ai 거점 도시",
    "유엔 ai 허브", "un ai 허브", "유엔 ai", "un 기구 유치",
    "글로벌 ai 거점", "아시아 ai 허브",
    "광주를 글로벌", "부산을 글로벌", "대구를 글로벌", "인천을 글로벌",
    "대전을 글로벌", "울산을 글로벌", "세종을 글로벌",
    "광주 ai 허브", "부산 ai 허브", "대구 ai 허브", "인천 ai 허브",
    "전남광주특별시", "전남광주 특별시",
    "ai 정책 시범", "ai 시범도시", "ai 특별시",
    "ai 산업 유치", "ai 기업 유치", "ai 투자 유치 발표",
    # v2.7.8: 일반 지자체 보도자료 패턴
    "조례 통과", "조례 시행", "기념식", "현판식", "착공",
    "표창", "포상", "장학금 전달",
    "스마트시티 ai", "스마트도시 ai",
    "ai 교육 운영", "ai 교육 과정 운영",
    # v2.7.8: PR-style 헤드라인 마커
    "선포", "선포식", "발족", "발족식", "비전 선포",
    "출정식", "킥오프", "kick-off", "킥-오프",
    "기념행사",
    # 부음·장례
    "부음", "별세", "모친상", "부친상", "장모상", "장인상",
    "장례식장", "발인", "빈소", "조문",
    # 상표·브랜드 마케팅 (AI 관련성 약함)
    "라이프집", "집덕후", "향기 굿즈", "라이프스타일 커뮤니티",
    "상표 출원", "상표 등록", "지정상품", "디퓨저", "핸드크림",
    # 일반 라이프스타일·취미
    "캠핑", "차박", "낚시", "등산", "맛집", "여행지 추천",
    # v2.8.3: 경마·도박·레저 (Ironclad/AI 무관)
    "경마", "경마장", "렛츠런파크", "한국마사회", "경륜", "경정",
    # v2.8.3: 외교·정치 정상회담 (Ironclad 회사명 우연 매칭 차단)
    "vucic", "putin", "trump", "biden", "macron", "merkel",
    "xi jinping", "시진핑", "푸틴", "트럼프", "바이든", "마크롱",
    "china-serbia", "ironclad friendship", "blood brothers",
    "전략적 동반자", "정상회담", "외교 정상화", "외교부 장관 회담",
    "north korea", "kim jong un", "북한", "김정은",
    # v2.8.3: 연예인 사생활·법적 분쟁 (AI 음성 조작 언급은 부수적)
    "김수현", "김세의", "정치탄압", "녹취파일", "녹취록 공개",
    "사생활 폭로", "열애설", "결별설", "공개 연애",
    "이혼 소송", "친자 확인", "양육권",
    # AI 자동 생성 lifestyle 컬럼 시리즈명 (v2.7)
    "ai 와 함께 쓴", "ai와 함께 쓴",
    "ai 와 함께", "ai가 쓰는",
    "ai 와 함께 한", "ai와 함께 한",
]


# Naver hankookilbo, 전자신문 등에서 자동 생성한 AI 보일러플레이트 기사 차단
BOILERPLATE_PATTERNS = [
    # 한국일보 패턴
    "이 기사는 생성형 ai 로 제작",
    "이 기사는 생성형 ai로 제작",
    "이 기사는 ai로 작성",
    "ai 활용 준칙을 준수합니다",
    "ai 활용준칙을 준수",
    "본 기사는 ai가 작성",
    "ai가 자동으로 작성한",
    # "도움을 받아" 패턴 (v2.7 추가 — 전자신문 등)
    "ai 도움을 받아 작성",
    "ai의 도움을 받아",
    "생성형 ai 도움을 받아",
    "생성형 ai(챗gpt) 도움",
    "생성형 ai (챗gpt) 도움",
    "chatgpt 도움을 받아",
    "챗gpt 도움을 받아",
    "챗gpt의 도움",
    # 시리즈 라벨
    "[ai 와 함께 쓴",
    "[ai와 함께 쓴",
]


def is_relevant(title: str, summary: str, source_type: str = "rss") -> bool:
    """관련성 체크 — 모든 소스에 보일러플레이트 + 블랙리스트 적용.

    규칙 (v2.7 강화):
    0. AI 생성 보일러플레이트 패턴이 본문에 있으면 모든 소스에서 즉시 제외
    1. 블랙리스트 키워드가 제목 또는 요약에 있으면 모든 소스에서 즉시 제외
       (이전: Naver/Google News만 → RSS 일부 매체가 정치·라이프 기사 섞어 보내는 케이스가 있어 모든 소스로 확장)
    2. Naver·Google News는 STRONG 또는 (AI+LEGAL) 시그널 추가 검증
    3. RSS·arXiv·OpenAlex는 블랙리스트만 통과하면 OK (큐레이션된 소스로 가정)
    """
    text = (title + " " + summary).lower()
    title_lower = title.lower()

    # 0. AI 생성 보일러플레이트 — 모든 소스에서 즉시 차단
    for pat in BOILERPLATE_PATTERNS:
        if pat in text:
            return False

    # 1. 블랙리스트 — 모든 소스에 적용 (RSS도 정치·lifestyle 기사 종종 포함)
    for kw in BLACKLIST_KEYWORDS:
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
    has_ai = any(kw in text for kw in AI_SIGNALS)
    has_legal = any(kw in text for kw in LEGAL_SIGNALS)
    if has_ai and has_legal:
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
    """4개 버킷별 매칭 강도 (0~1)"""
    text = (title + " " + summary).lower()
    title_lower = title.lower()

    buckets = {"law": 0.0, "global": 0.0, "policy": 0.0, "promo": 0.0}

    for kw in LAW_AI_KEYWORDS:
        if kw in text:
            buckets["law"] = min(1.0, buckets["law"] + 0.5)
    for kw in GLOBAL_MARKET_KEYWORDS:
        if kw in text:
            buckets["global"] = min(1.0, buckets["global"] + 0.4)
    for kw in POLICY_KEYWORDS:
        if kw in text:
            buckets["policy"] = min(1.0, buckets["policy"] + 0.45)
    # PROMO는 헤드라인 위주
    for pat in PROMO_PATTERNS:
        if pat in title_lower:
            buckets["promo"] = 1.0
            break
    return buckets


def score_item(title: str, summary: str, date, categories: list) -> int:
    """가중치 기반 중요도 (v2.8.2)

    버킷별 최대 보너스:
      LAW(로펌)  : +40  (weight 0.40)
      GLOBAL     : +25  (weight 0.25)
      POLICY     : +25  (weight 0.25)
      PROMO      : +10  (weight 0.10)

    PROMO 헤드라인 매칭 시 → 40점 이하로 강제 캡 (홍보 weight 0.1 정책)
    """
    # v2.8.2: base 40→50 + 카테고리 보너스 상향 (자본·논문 복원)
    score = 50
    text = (title + " " + summary).lower()

    buckets = detect_score_buckets(title, summary)

    # 가중치 보너스
    score += buckets["law"]    * 40
    score += buckets["global"] * 25
    score += buckets["policy"] * 25
    score += buckets["promo"]  * 10

    # v2.8.2: 카테고리 보너스 상향 — papers·funding·legaltech 정상 컨텐츠 점수 복원
    if "legaltech" in categories:
        score += 10  # 6 → 10
    if "papers" in categories:
        score += 10  # 4 → 10 (논문 점수 복원)
    if "funding" in categories:
        score += 8   # 3 → 8 (자금조달 점수 복원)

    # 시간 가중치
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

    # v2.7.6: PROMO 헤드라인 hard cap — 본문에 우연히 POLICY 키워드가 섞여도 dampening 유지
    # 헤드라인이 [AI 클로즈업]/TIPS 선정/~기업 선언 같은 홍보성이면 본질이 광고이므로
    # POLICY/LAW가 본문에 부수적으로 매칭돼도 강제 cap 40 (홍보 weight 0.1 정책 반영).
    if buckets["promo"] > 0:
        score = min(score, 40)

    return max(0, min(150, int(score)))


def normalize_url(url: str) -> str:
    """URL 정규화 (utm 등 트래킹 파라미터 제거)"""
    if not url:
        return ""
    url = re.sub(r"[?&](utm_[^=]+|fbclid|gclid|mc_cid|mc_eid)=[^&]*", "", url)
    url = re.sub(r"\?$", "", url)
    return url.strip()
