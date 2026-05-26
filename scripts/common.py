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
    "ai-industry": [
        # 회사명 — 다른 카테고리에 속하지 않는 경우의 fallback
        "openai", "anthropic", "claude ", "gpt-", "chatgpt", "gemini",
        "deepmind", "meta ai", "llama", "mistral", "xai", "grok",
        "nvidia ai", "microsoft ai", "perplexity",
        # v3.8: AI 엔지니어링·인프라 새 영역
        "오픈소스 ai", "open source ai", "오픈소스 llm", "open weight", "오픈웨이트",
        "ai 오케스트레이션", "ai orchestration", "오케스트레이터", "orchestrator",
        "에이전트 오케스트레이션", "agent orchestration",
        "멀티 에이전트", "multi-agent",
        "프롬프트 엔지니어링", "prompt engineering",
        "컨텍스트 엔지니어링", "context engineering",
        "하네스 엔지니어링", "harness engineering",
        "클론 엔지니어링", "clone engineering",
        "fde", "forward deployed engineer", "포워드 디플로이드",
        # v3.9-A: AI 코딩 툴·vibe coding·MCP
        "claude code", "클로드 코드", "cursor", "windsurf", "github copilot",
        "vibe coding", "바이브 코딩",
        "mcp", "model context protocol", "모델 컨텍스트 프로토콜",
        "ai 코딩", "ai coding", "ai code generation", "ai coding assistant",
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
    "funding": 3,
    "adoption": 4,
    "governance": 5,  # v3.0: 사내 거버넌스 (정부 정책보다 실무 가까움)
    "policy": 6,
    "market": 7,      # v3.0: 시장·경쟁 구도
    "product": 8,
    "ai-industry": 9,
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
    # v2.8.9: 육아·감성·라이프 컬럼 (AI/리걸테크 무관)
    "그림책", "힐링 된다", "내가 되려", "내가 되어", "엄마가 되어",
    "육아", "유아", "초등 자녀", "초등생", "유치원",
    "감성 에세이", "에세이", "수필",
    "독서 후기", "도서 리뷰", "책을 펼친다",
    # v2.8.9: 전자담배·흡연·금연 (AI 앵커 광고 등 우회 케이스 차단)
    "전자담배", "무니코틴", "니코틴 액상", "액상 흡연",
    "흡연", "금연", "담배", "ai 앵커 광고", "ai 의사 광고",
    "사후 광고", "광고 심의", "광고 규제 우회",
    # v3.0: 일반 산업 PR·이모저모 패턴 (AI 무관 retail/heavy industry PR 차단)
    "이모저모", "유통 이모저모", "패션 이모저모", "식품 이모저모",
    "브랜드 엑스포", "대한민국 브랜드 엑스포",
    "조선소", "조선소 인수", "해양종합기업", "해양 종합기업",
    "기자재사", "기자재사들", "조선 기자재",
    "철강사", "정유사", "석유화학",
    # v3.0: 일반 유통·소비재 회장·총수 인사 동정 (AI 무관)
    "이재현 회장", "구광모 회장", "정의선 회장", "신동빈 회장",
    "회장 인사", "총수 회동", "총수 회담",
    "그룹 인사", "임원 인사 이모저모",
    # v3.1: 주가·시세 일일 보도 (AI 무관 단순 시세 변동)
    "연중 최저가", "연중 최고가", "주가 폭락", "주가 급락", "주가 급등",
    "52주 최저", "52주 신저가", "52주 최고", "52주 신고가",
    "개미들 탄식", "개미 탄식", "개미 패닉", "개미 손절",
    "외국인 매도", "기관 매도", "공매도 폭증",
    # v3.1: 범죄·성매매·유흥 (AI/리걸테크 무관 사회면 사건)
    "사이버 포주", "포주", "성매매", "유흥업소", "성매매 알선",
    "성착취", "딥페이크 음란물",  # 단, 'AI 딥페이크 규제'는 POLICY 키워드로 통과
    "마약", "필로폰", "대마", "투약 혐의",
    "도박장", "불법 도박", "사설 도박",
    # v3.1: 투자 사기·다단계 (일반 사회면 사기 사건, AI/법무 무관)
    "투자 사기", "유사수신", "다단계 사기",
    "금수저", "흙수저", "고급정보 절대", "주변에 절대 알리지",
    "리딩방", "주식 리딩방", "리딩방 사기",
    "보이스피싱", "메신저피싱", "스미싱",
    # v3.5: 게임·애니메·콘텐츠 (AI 무관)
    "사이버펑크", "엣지러너", "cdpr", "애니메 엑스포",
    "게임 e3", "게임쇼", "콘솔 게임",
    # v3.5: 일반 행정 공모전·상금 (AI 무관)
    "논문공모", "상금 1500만원", "상금 1,500만원", "상금 1억원",
    "공모전 시상", "공모전 우수상",
    # v3.5: 화학·환경·소재 (AI 무관)
    "순환경제 실험", "플라스틱을 다시", "원료 가스",
    "수소 생산 전극", "차세대 수소", "수소 연료",
    "탄소중립 실증", "ccus", "전극 개발", "촉매 개발",
    "에코프로", "lg화학 신소재", "포스코 수소",
    # v3.5: 금융 통계 (단순 수치 발표, AI 무관)
    "대출 연체율", "부실채권", "연체율 하락", "연체율 상승",
    "은행 연체율", "기업대출 부실", "가계대출 부실",
    # v3.5: 외교·전쟁·국제유가 (AI 무관)
    "수도 총공세", "키이우", "키이우 떠나라",
    "호르무즈", "국제유가 폭락", "국제유가 급등",
    "전선 확대", "휴전 협상", "정상 통화",
    # v3.5: K-뷰티·푸드·수출 (AI 무관)
    "k-뷰티", "k뷰티", "k-푸드", "k푸드",
    "유럽 정조준", "프라하 홀린", "체코 넘어",
    "한류 마케팅", "유럽 진출 가속",
    # v3.5: 시험소·연구소 준공 (AI 무관)
    "시험소 준공", "센터 준공식", "솔루션 센터 준공",
    "전장 emc", "emc 시험",
    # v3.5: 체험기·생활 컬럼 (AI 무관)
    "체험기", "직접 가보니", "방문기", "후기 체험",
    "가보니", "와이프와 함께",
    # v3.5: 방산·조선·중공업 입찰 (AI 무관)
    "kddx", "차세대 함정", "방산 입찰", "함정 입찰",
    "hd현대중 한화오션", "전투기 입찰",
    # v3.5: 변호사 사회면 (AI 무관)
    "antisemitic", "antisemitic tweets",
    "judicial pay rise", "judiciary pay", "pay rise for judiciary",
    "lammy rejects", "lammy approves",
    # v3.5.1: 연예인 사생활·투병 (AI 무관)
    "남규리", "20년 투병", "父 투병", "母 투병",
    "투병 고백", "투병 눈물", "생활보호대상자로 자랐",
    "암 투병", "지병 별세", "지병 사망",
    # v3.15: 연예/예능 토크쇼 PR (AI 무관, 본문이 ai-related라도 본질은 연예)
    "슈주", "신동", "장성규", "유재석", "조세호", "이수근",
    "장비빨", "스포츠는 장비빨",
    "확 달라진", "충격 고백", "깜짝 고백",
    "예능 출연", "토크쇼 출연", "예능 깜짝", "예능 복귀",
    "방송 출연", "TV 출연", "예능감",
    "아이돌", "걸그룹", "보이그룹",
    # v3.19: 드라마·연예 (안방극장·캐릭터 몰입도 PR)
    "안방극장", "안방 극장",
    "매력 캐릭터", "캐릭터 몰입도", "몰입도 up",
    "드라마 출연", "드라마 캐스팅", "드라마 주연",
    "주연 발탁", "광고 모델 발탁", "광고모델 발탁",
    "광고 모델로", "광고모델로", "전속모델", "전속 모델",
    "신규 광고", "광고 캠페인",
    # v3.19: 산학협력·MOU 일반 PR (AI 무관 인재 양성)
    "맞손", "인재 양성 맞손", "양성 맞손",
    "디지털 마케팅 인재", "마케팅 인재 양성",
    "ai 인재 양성 협약", "인재 양성 협약",
    "산학협력 mou", "업무협약 체결", "업무협약 mou",
    "기관 mou", "공동 인재 양성",
    # v3.19: 지자체·교육청 AI 연수·교육 PR (AI 무관 행사)
    "ai 활용 연수", "ai 연수 진행", "활용 연수 진행",
    "교육청 ai 연수", "도서관 ai 활용", "도서관 관계자",
    "학교도서관 관계자", "학교 도서관 연수",
    "교사 ai 연수", "관계자 대상", "교원 대상 ai",
    "ai 교육 사업", "ai 교육 운영 사업",
    # v3.5.1: 유통·패션업계 (AI 무관)
    "쿠팡 무신사", "자사몰로 반격", "고객 탈환",
    "패션업계 반격", "패션 자사몰", "마트 반격",
    "이커머스 반격", "유통업체 자사몰",
    # v3.5.1: 미국·국내 증시 일일 시황 (AI 무관)
    "미국 증시", "다우 지수", "다우지수", "나스닥 지수",
    "주요 지수 일제히", "반도체 강세", "반도체 약세",
    "서울데이터랩", "코스피 강세", "코스닥 강세",
    "코스피 약세", "코스닥 약세", "기관 순매수", "외국인 순매수",
    # v3.9: 일본·중국·홍콩 증시 일일 시황
    "닛케이", "닛케이 지수", "닛케이 평균", "닛케이 종가",
    "6만5000엔", "6만엔", "7만 엔 시대", "7만엔",
    "도쿄 증시", "상하이 종합지수", "항셍 지수", "항셍",
    "엔화 강세", "엔화 약세", "엔달러", "위안화",
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


# v3.0: 외교·정치 인물명 — AI 정책 시그널이 함께 있으면 차단 우회 (regulation/executive order 관련 기사 보호)
POLITICAL_FIGURES = {
    "vucic", "putin", "trump", "biden", "macron", "merkel",
    "xi jinping", "시진핑", "푸틴", "트럼프", "바이든", "마크롱",
    "kim jong un", "김정은",
}

# AI 정책·규제 화이트리스트 — 이 시그널이 본문에 있으면 정치 인물명 차단을 우회
POLICY_GUARD_SIGNALS = [
    "ai 규제", "ai규제", "ai 정책", "ai정책", "ai 법안", "ai법안",
    "ai 입법", "ai 행정명령", "행정명령 ai",
    "ai act", "eu ai act", "ai 액트",
    "ai 거버넌스", "ai governance",
    "ai 기본법", "ai기본법",
    "executive order", "ai standards", "ai 표준",
    "ai regulation", "regulation ai",
    "데이터 규제", "개인정보 규제", "알고리즘 규제",
]


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

    # v3.0: AI 정책 시그널 존재 여부 사전 계산 (정치 인물명 차단 우회용)
    has_policy_guard = any(g in text for g in POLICY_GUARD_SIGNALS)

    # 1. 블랙리스트 — 모든 소스에 적용 (RSS도 정치·lifestyle 기사 종종 포함)
    for kw in BLACKLIST_KEYWORDS:
        if kw in title_lower or kw in text:
            # v3.0: 정치 인물명 매칭이지만 AI 정책 시그널이 있으면 통과
            if kw in POLITICAL_FIGURES and has_policy_guard:
                continue
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

LEGAL_SIGNALS = [
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
]


def count_signal_hits(text: str, signals: list) -> int:
    """텍스트에서 시그널 키워드 hit 개수 (중복 제외)"""
    return sum(1 for s in signals if s.lower() in text)


def score_item(title: str, summary: str, date, categories: list) -> int:
    """v4.0: 행동 시그널 기반 중요도 — 대형로펌 경영전략팀 페르소나.

    설계 원칙:
      1) 단순 "AI" 언급으로는 통과 못함 (의미 페어 강제)
      2) base 30 → 행동 시그널 없으면 자동 cut-off 미만
      3) DECISION/REGULATORY/MARKET/LEGAL 4축 시그널 매트릭스 (각 최대 +25)
      4) NEGATIVE 시그널은 강력한 -30
      5) AI 단순 언급 (1~2회) + 시그널 0 → score 20 hard cap

    점수 구간 가이드 (cut-off 35):
      0~34   = drop (광고/PR/연예/일상)
      35~49  = 약한 시그널 (참고)
      50~69  = 의미 있는 시그널 (검토)
      70~89  = 명확한 행동 가치 (f/u 필요)
      90+    = 핵심 검토 사항 (즉시 보고)
    """
    score = 30.0  # v4.0: base 50 → 30 (시그널 없으면 자동 cut-off)
    text = (title + " " + summary).lower()
    title_lower = title.lower()

    # === v4.0 행동 시그널 매트릭스 (각 축 최대 +25) ===
    decision_hits = count_signal_hits(text, DECISION_SIGNALS)
    regulatory_hits = count_signal_hits(text, REGULATORY_SIGNALS)
    market_hits = count_signal_hits(text, MARKET_SIGNALS)
    legal_hits = count_signal_hits(text, LEGAL_SIGNALS)

    # hits → strength (1 - 0.78^n): 1→0.22, 2→0.39, 3→0.53, 4→0.63, 5→0.71, 6→0.78
    def strength(n: int) -> float:
        return round(1.0 - 0.78 ** n, 3) if n > 0 else 0.0

    decision_s = strength(decision_hits)
    regulatory_s = strength(regulatory_hits)
    market_s = strength(market_hits)
    legal_s = strength(legal_hits)

    # 가중치 (사용자 페르소나: 대형로펌 경영전략팀)
    score += decision_s   * 25  # 의사결정 시그널 가장 중요
    score += regulatory_s * 25  # 규제 시그널 (로펌 본업)
    score += market_s     * 20  # 시장구조
    score += legal_s      * 22  # 법률·로펌

    total_signal = decision_s + regulatory_s + market_s + legal_s

    # === v4.0 NEGATIVE 시그널 — 행동 가치 명백히 없음 ===
    negative_hits = count_signal_hits(text, NEGATIVE_SIGNALS)
    if negative_hits >= 1:
        # 시그널이 매우 강하지 않으면 강력 감점 (cut-off 미만)
        if total_signal < 1.0:
            score = min(score, 18)  # 자동 drop 구간
        else:
            score -= 30  # 강한 시그널 있어도 NEGATIVE는 강등

    # === v4.0 AI 단순 언급 자동 강등 ===
    # "AI"가 본문에 1~2회뿐이고 행동 시그널 없으면 단순 언급 — drop
    ai_mentions = (text.count(" ai ") + text.count("ai ") +
                   text.count(" ai") + text.count("인공지능"))
    if ai_mentions <= 2 and total_signal < 0.3:
        score = min(score, 22)

    # 시그널 0개 — 행동 가치 없음
    if total_signal < 0.1:
        score = min(score, 25)

    # === 카테고리 보너스 (정상 컨텐츠 보호) ===
    if "legaltech" in categories:
        score += 12  # 리걸테크는 본질적으로 우리 관심
    if "papers" in categories:
        score += 8   # 학술 논문
    if "funding" in categories:
        score += 6   # 자본 흐름

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

    return max(0, min(150, int(round(score))))


def normalize_url(url: str) -> str:
    """URL 정규화 (utm 등 트래킹 파라미터 제거)"""
    if not url:
        return ""
    url = re.sub(r"[?&](utm_[^=]+|fbclid|gclid|mc_cid|mc_eid)=[^&]*", "", url)
    url = re.sub(r"\?$", "", url)
    return url.strip()
