"""
v6.6: PR pattern detector — title regex + 조건부 처리.

핵심: 사용자가 매번 신고하는 PR 기사들의 명시적 표지를 한 곳에 모음.
      score_item의 keyword bag-of-words 한계를 우회해 title 패턴부터 차단/강등.

처리 단계:
  1) 무조건 BLACKLIST  ([게시판], [주간투자동향], [책 소개] 등 — 100% PR)
  2) 무조건 NEGATIVE   ([AI&빅데이터쇼], [#클라우드 월드] 등 — 행사 부스)
  3) 조건부 NEGATIVE   ([기고], [칼럼] 등 — AI 핵심 키워드 3+이면 통과)
  4) 조건부 BLACKLIST  ([로펌이슈], [로펌스토리] 등 — AI 핵심 키워드 3+이면 통과)
  5) PR 동사 NEGATIVE  (선보인다, 공장 방문, 전폭 지원, 성료 등 — body level)

사용:
    from pr_patterns import classify_pr_pattern
    verdict = classify_pr_pattern(title, summary)
    # verdict: ('block', None) | ('cap', max_score) | ('pass', None)
"""

import re


# ============================================================================
# 1) 무조건 BLACKLIST — title prefix 매칭 시 즉시 drop
# ============================================================================
# 사용자 결정: 1차 그룹 (2026-05-27)
PREFIX_BLACKLIST_ALWAYS = [
    r'^\s*\[\s*게시판\s*\]',
    r'^\s*\[\s*주간투자동향\s*\]',
    r'^\s*\[\s*월간투자동향\s*\]',
    r'^\s*\[\s*책\s*소개\s*\]',
    r'^\s*\[\s*신간\s*\]',
    r'^\s*\[\s*도서\s*\]',
]

# ============================================================================
# 2) 무조건 NEGATIVE — title prefix 매칭 시 score cap 25 (cut-off 미만)
# ============================================================================
# 사용자 결정: 2차 그룹
PREFIX_NEGATIVE_ALWAYS = [
    r'^\s*\[\s*AI\s*&\s*빅데이터쇼\s*\]',
    r'^\s*\[\s*#\s*클라우드\s*월드\s*\]',
    r'^\s*\[\s*클라우드\s*월드\s*\]',
    r'^\s*\[\s*ZD\s*SW\s*투데이\s*\]',
    r'^\s*\[\s*ZD\s*투데이\s*\]',
]

# ============================================================================
# 3) 조건부 NEGATIVE — 의견란·칼럼. AI 핵심 키워드 3+ 매칭 시 우회.
# ============================================================================
# 사용자 결정: 3차 그룹 — "내용이 AI에 깊숙히 관련있다면 노출해야지"
PREFIX_CONDITIONAL_OPINION = [
    r'^\s*\[\s*기고\s*\]',
    r'^\s*\[\s*칼럼\s*\]',
    r'^\s*\[\s*명탐말\s*\]',
    r'^\s*\[\s*명칼럼\s*\]',
    r'^\s*\[\s*사설\s*\]',
    r'^\s*\[\s*오피니언\s*\]',
    r'^\s*\[\s*조세\s*\]',
    r'^\s*\[\s*조세육의',  # 조세육의 다시 쓰는 ...
]

# ============================================================================
# 4) 조건부 BLACKLIST — 로펌 기획 시리즈. AI 핵심 3+ 시 우회.
# ============================================================================
# 사용자 결정: 4차 그룹 — "기본적으로는 blacklist지만, ai에 특화된 내용이라면 노출"
PREFIX_CONDITIONAL_LAWFIRM = [
    r'^\s*\[\s*로펌이슈\s*\]',
    r'^\s*\[\s*로펌스토리\s*\]',
    r'^\s*\[\s*차식의\s*변호사',
    r'^\s*\[\s*변호사\s*가이드\s*\]',
    r'^\s*\[\s*법률[^]]*가이드\s*\]',
]

# ============================================================================
# AI 핵심 키워드 — 3+ 매칭 시 conditional prefix 통과 (3차·4차 우회 조건)
# ============================================================================
# v6.15.35 (P2-5): 회사·제품·리걸테크 이름은 catalog.py(SSOT)에서 import.
#   신규 회사 추가 시 catalog만 갱신하면 pr_patterns·dedupe 등에 함께 전파.
#   ※ 한국 로펌명(KOREAN_LAW_FIRMS)은 'AI 핵심 시그널'이 아니므로 여기엔 넣지 않음(의도 보존).
#   _PR_DOMAIN은 PR 우회 판정용 도메인·정책 키워드(비회사)만 로컬 보유.
from catalog import AI_COMPANIES, AI_PRODUCTS, LEGALTECH_COMPANIES

_PR_DOMAIN = [
    # AI 도메인 명시 키워드
    '리걸테크', 'legaltech', 'legal tech',
    'legal ai', '법률 ai', '법무 ai', '변호사 ai',
    'law firm ai', 'biglaw ai',
    '생성형 ai', '생성ai',
    'ai 에이전트', 'agentic ai', 'multi-agent', 'autonomous agent',
    'llm', 'large language model',
    'transformer model', 'diffusion model',
    # 정책·규제 명시
    'ai 기본법', 'ai기본법', 'eu ai act', 'ai act',
    'ai 거버넌스', 'ai governance',
]

AI_CORE_KEYWORDS = list(dict.fromkeys(
    AI_COMPANIES + AI_PRODUCTS + LEGALTECH_COMPANIES + _PR_DOMAIN
))


# ============================================================================
# 5) PR 동사 NEGATIVE — body/title 어디든 매칭 시 cap.
#    "선보인다", "공장 방문", "전폭 지원", "성료" 등 의례적 PR 표현.
# ============================================================================
PR_VERBS = [
    # 행사·시찰 의례적 동사
    '선보인다', '선보였다', '선보일', '선보일 예정',
    '공장 방문', '현장 방문', '현장 격려', '시찰',
    '성료', '성황리에', '성공적으로 마무리',
    '동참', '출범식', '발족식', '비전 선포',
    # 정책 의례적 표현 (사용자 지적: LG엔솔 케이스)
    '전폭 지원', '전폭적 지원', '전폭적인 지원',
    'mou 체결', '협약 체결', '업무협약',
    # 단신 / round-up 시리즈 표지
    '특허 등록 등', '등 단신', '단신 모음',
    # 행사 알림
    '컨퍼런스 열린다', '컨퍼런스가 열린다', '포럼 열린다',
    '개막한다', '개막했다', '개최한다고 밝혔다',
]


# ============================================================================
# 메인 함수
# ============================================================================

# 컴파일된 패턴 캐시 (모듈 로드 시 한 번만)
_BLACKLIST_PATTERNS = [re.compile(p, re.IGNORECASE) for p in PREFIX_BLACKLIST_ALWAYS]
_NEGATIVE_PATTERNS = [re.compile(p, re.IGNORECASE) for p in PREFIX_NEGATIVE_ALWAYS]
_OPINION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in PREFIX_CONDITIONAL_OPINION]
_LAWFIRM_PATTERNS = [re.compile(p, re.IGNORECASE) for p in PREFIX_CONDITIONAL_LAWFIRM]


def count_ai_core_hits(text: str) -> int:
    """본문에서 AI 핵심 키워드가 몇 개 매칭되는지 (조건부 prefix 우회 판정용)."""
    text_lower = text.lower()
    return sum(1 for kw in AI_CORE_KEYWORDS if kw.lower() in text_lower)


def count_pr_verb_hits(text: str) -> int:
    """본문에서 PR 동사 매칭 개수."""
    text_lower = text.lower()
    return sum(1 for v in PR_VERBS if v.lower() in text_lower)


def classify_pr_pattern(title: str, summary: str = "") -> tuple:
    """PR title pattern 분류 → 처리 verdict 반환.

    Returns:
        ('block', None)        — BLACKLIST drop
        ('cap', max_score)     — score를 max_score로 cap
        ('pass', None)         — 통과 (다른 score 로직에 위임)

    조건부 우회: AI 핵심 키워드 3+ 시 3차/4차 prefix는 통과.
    """
    title = title or ""
    text = title + " " + (summary or "")

    # 1차 무조건 BLACKLIST
    for pat in _BLACKLIST_PATTERNS:
        if pat.search(title):
            return ('block', None)

    # 2차 무조건 NEGATIVE
    for pat in _NEGATIVE_PATTERNS:
        if pat.search(title):
            return ('cap', 25)

    # 3차·4차 조건부 — AI 핵심 3+ 시 우회
    ai_core_hits = count_ai_core_hits(text)

    for pat in _OPINION_PATTERNS:
        if pat.search(title):
            if ai_core_hits >= 3:
                return ('pass', None)  # AI 깊은 의견 → 통과
            return ('cap', 28)  # 일반 의견 → NEGATIVE 강등

    for pat in _LAWFIRM_PATTERNS:
        if pat.search(title):
            if ai_core_hits >= 3:
                return ('pass', None)  # AI 핵심 로펌 시리즈 → 통과
            return ('block', None)  # 일반 로펌 시리즈 → BLACKLIST

    # PR 동사 — title 또는 summary에 강력한 PR 동사 2+ 매칭 시 cap
    # (1개 매칭은 일반 단어일 수 있으므로 2+ 요구)
    pr_verb_hits = count_pr_verb_hits(text)
    if pr_verb_hits >= 2:
        # AI 핵심 시그널이 있으면 cap 완화 (관련 행사도 살림)
        if ai_core_hits >= 3:
            return ('cap', 45)  # 후순위지만 노출
        return ('cap', 30)  # 강한 강등

    return ('pass', None)
