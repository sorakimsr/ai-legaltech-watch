"""
3단계 — LLM 한국어 요약·시사점 생성 (v2.1)

deduped_news.json 을 읽어 **영문 항목 전부** + **상위 시사점 후보**에
한국어 요약·시사점을 추가합니다.

전략:
- 영문(lang=en) 항목 → 한국어 요약 필수, 시사점은 score >= 65일 때만
- 한국어(lang=ko) 항목 → 한국어 요약 불필요 (원문이 이미 한국어), 시사점만 score >= 70일 때 추가
- 캐시: 기존 enriched_news.json 의 항목은 URL 기준으로 재사용
- 부분 저장: 매 10건마다 저장
- 비용 제어: ENRICH_MAX_PER_RUN 환경변수로 1회 호출 수 상한

결과는 data/enriched_news.json 으로 저장
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_client import call_llm_json, detect_backend


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_PATH = os.path.join(ROOT_DIR, "data", "deduped_news.json")
OUTPUT_PATH = os.path.join(ROOT_DIR, "data", "enriched_news.json")
KST = timezone(timedelta(hours=9))

# 1회 실행에서 최대 호출 수
MAX_PER_RUN = int(os.environ.get("ENRICH_MAX_PER_RUN", "300"))

# 시사점은 일정 점수 이상만
INSIGHT_THRESHOLD_EN = int(os.environ.get("INSIGHT_THRESHOLD_EN", "65"))
INSIGHT_THRESHOLD_KO = int(os.environ.get("INSIGHT_THRESHOLD_KO", "70"))

# v2.8.5: 최근 N일 이내 항목은 캐시 무시하고 강제 재 enrich
# (프롬프트 변경 후 새 음영 정책 적용용)
REFRESH_RECENT_DAYS = int(os.environ.get("ENRICH_REFRESH_DAYS", "0"))


# v6.8 (Phase 2): persona_score — 대형로펌 대표 페르소나 가치 평가 (0~10).
#                 enrich 프롬프트에 필드 추가해 추가 LLM 호출 없이 함께 받음.
# v6.10 (Phase 3): 사용자(대형로펌 경영전략팀)가 직접 ⭐ 북마크한 시사점 카드 35건
#                 + 직접 ⭐ 기사 30건 통계 분석 기반의 "CEO가 선호한 패턴" 주입.
_PERSONA_SCORE_RULES = """
[페르소나 가치 평가]
이 article을 **한국 대형로펌 경영전략팀 시니어 컨설턴트** 페르소나로 평가.
독자는 전략·기획과 AI 업무를 동시 수행하며, **AI×법조 교차점이 가장 결정적인 관심사**.

- persona_score: 0~10 정수.
  · 9~10 = 의사결정 직접 영향 (AI×법조 교차 핵심 어젠다·규제 신설·경쟁 로펌 도입·시장 구도 변화)
  · 7~8  = 검토·논의 가치 (산업 동향, 정책 흐름, 기술 발전)
  · 4~6  = 참고 (일반 AI 동향, 해외 사례)
  · 1~3  = 약한 관련성 (단순 보도, 의례적 행사)
  · 0    = 무관 (PR, 단신, 시찰)
- persona_reason: 1문장. 그 점수의 핵심 근거 (회사명·정책명 구체).

평가 시 우선:
- 행동 가치 (즉시·중기 검토할 사항인가) > 정보 가치
- 한국 시장·로펌 영향 > 글로벌 일반론
- 구체 사실 (회사명·금액·정책명) > 추상 트렌드
- AI×법조 교차 어젠다 > 산업 일반 trend

[★ 사용자 명시 핵심 어젠다 6개군 — 매칭 시 persona_score 8 이상 평가 (2026-05-28 사용자 정책)]
독자가 "사라지면 안 되는 어젠다"로 명시한 영역. 의미·표현이 다른 기사여도
아래 6개군 중 하나에 해당하면 9~10으로 평가하라.

① 판결문 공개·데이터 인프라
   · 판결문 공개 범위 확대 논의, 비실명화·익명화 수준, 법인명 실명 공개 여부
   · 공개 판결문 데이터셋 접근성 변화, 사법정책연구원·법원행정처 정책 동향
   · 예시: "사법정책연구원, 판결문 공개제도 학술대회", "판사 70% 판결문 공개 찬성",
           "비실명화 최소화 논의", "AI 학습용 판결문 활용 정책"

② AI 서비스 규제·개인정보
   · 공정거래위원회의 AI 서비스 시장 실태조사 (대상·범위·조사 항목)
   · AI 개발 목적의 개인정보 처리 특례 입법 흐름
   · 개인정보보호법·정보통신망법·AI 기본법의 교차 적용 가능성
   · 예시: "공정위 AI 서비스 시장 실태조사", "AI 개발 개인정보 처리 특례",
           "AI 기본법 시행령", "EU AI Act × 한국 AI 기본법 충돌"

③ 로펌·법무팀 AI 도입
   · 대형로펌(김앤장·광장·세종·율촌·태평양·화우·지평·바른) AI 솔루션 도입
   · 변호사 AI 활용, 법무팀 ChatGPT·Copilot·Harvey 도입 사례
   · 예시: "세종, Harvey 도입", "법무법인 광장 Tech&AI팀", "기업 법무팀 AI 도입"

④ 법조계 AI 정책
   · 대법원·법무부·헌법재판소의 AI 관련 입장
   · 변협·각종 법조 단체의 AI 가이드라인
   · 예시: "변협 AI 가이드", "법무부 AI 정책 방향", "대법원 AI 활용 방안"

⑤ AI 책임·소송·판례
   · AI 저작권·생성물 책임 판결, 모델 학습 데이터 분쟁
   · AI 환각·오작동 관련 소송 사례
   · 예시: "AI 저작권 판결", "AI 환각 변호사 징계", "AI 학습 데이터 라이선스 분쟁"

⑥ 글로벌 AI 거버넌스 (법무 직접 영향)
   · EU AI Act, GPAI 의무, 미국 AI 행정명령 핵심 조항
   · 한국 법무·로펌에 영향 가는 해외 입법 흐름
   · 예시: "EU AI Act 시행 100일", "미국 AI 행정명령 개정"

[★ 산업 일반 trend는 7~8점 cap]
DeepSeek/Qwen/Cursor/Midjourney 등 모델·코딩 도구·자본 흐름 기사는
법조·법무 함의가 명시되지 않으면 persona_score 8 초과 부여 금지.
독자에게는 보조 정보이지 의사결정 어젠다가 아님.

[v6.10 — CEO가 선호한 시사점 패턴 (북마크 ground truth 기반)]
다음은 사용자가 실제로 ⭐ 북마크한 시사점 카드의 공통 패턴이다.
유사한 결을 가진 기사는 persona_score를 +1~+2 끌어올려 평가하라.

A) Title 스타일 예시 (실제 북마크된 카드 제목):
  - "AI 거버넌스, 선택이 아닌 생존 조건으로 전환 중"
  - "정부 가이드라인 1년째 공백, 법률 AI는 이미 시장을 점령 중"
  - "Harvey·Legora·EvenUp이 그리는 법률 AI 3분할 지형"
  - "에이전트 스프롤이 만드는 '보이지 않는 부채'"
  - "AI 데이터 거버넌스, 규제 준수 비용이 아닌 시장 진입 자격증이 됐다"
  - "에이전트 안전성은 모델 정렬이 아닌 상호작용 구조가 결정한다"
  - "시간 기반 과금이 무너지는 자리에 무엇을 채울 것인가"
  → 공통: 시장 구조 전환을 "X가 아니라 Y" 형태로 한 문장에 압축. 결론·방향성 명시.

B) Body 인사이트 마커 패턴 (강조해야 할 구절):
  - "X가 아니라 Y로 전환되고 있다는 신호"
  - "선택이 아닌 [생존 조건/통행증/요건]"
  - "단순 도구 판매가 아니라 운영 수탁"
  - "AI 도입 속도가 통제 속도를 이미 초과했다"
  - "벤치마크 점수가 실무 성능을 보장하지 않는다"
  - "에이전트 간 상호작용 구조가 안전성을 결정한다"
  - "이 흐름이 가속되면 ... 격차가 벌어질 가능성이 크다"

C) 등장 시 우선 평가 키워드 (+1):
  에이전트 스프롤 / 거버넌스 공백 / 책임 공백·경계 / 시간 기반 과금 /
  Contract Intelligence / Pre-Litigation / 탈숙련(deskilling) / Brainrot /
  벤치마크 신뢰성 / 데이터 거버넌스 통행증 / interaction topology / sLLM·온프레미스

D) 등장 시 우선 평가 인물·기업·기관 (+1):
  Harvey, Legora, EvenUp, Anthropic, OpenAI, Cloudflare, Cerebras, Ammune.ai,
  Icertis, SpotDraft, KB금융 31개 통제 항목, 기업은행 IBK GenAI,
  한국부동산원 sLLM 다중 에이전트, 그리드원, 율촌 아이율, 세종(Harvey 도입),
  법무법인 광장 Tech&AI팀, 산업부 AI 혁신 자문단, 자블리 XAI, 엘박스 IPO

E) 자동 -2 (북마크 0건 — 사용자가 명시적으로 안 본 패턴):
  단순 행사·MOU·체험 부스·인재 양성 본격화 / 매거진 호 preview /
  지자체 시찰·총수 회동 / 매출 증가·주가 변동 단신 /
  AI 무관 정치·연예 / 회사 AI 도입 본격화 단발 보도
"""

# v2.8: 의미론적 강조로 전환 — 고유명사가 아니라 의사결정·영향력 구절에만 **굵게**
_HIGHLIGHT_RULES = """- **굵게(`**...**`)는 "의미론적으로 의사결정에 직결되는 구절"에만 적용** (사용자 정책):

  강조해야 할 것 (✅ 인과·필요·판단·시사 구절):
    예시) "단일 LLM 선택은 이미 낡은 질문이고, 에이전트 간 신뢰·조정 계층이 새 병목",
    "RAG 파이프라인을 구축하고 방치하는 운영 방식은 재검토가 필요한 시점",
    "성공한 목표당 비용으로 KPI를 재설계해야",
    "온프레미스 또는 폐쇄망 요구가 도입 속도를 제한하는 현실적 제약",
    "책임 경계가 명확히 설계된 아키텍처를 선택",
    "협상 레버리지가 옮겨갔다", "벤더 종속이 풀린다",
    "한국 기업 환경에서는 개인정보보호법상 국외 데이터 이전 제한이 도입의 현실적 장벽"
  → "X는 Y다", "A가 B의 병목", "C 요구가 D를 제한" 같은 인과·판단 구절만.

  강조 금지 (❌ 단순 고유명사·금액·기법명·기관명):
    "OpenAI", "Anthropic", "Sequoia Capital", "수출입은행", "KB금융",
    "Harvey", "Foundation Protocol", "40억 달러", "RAG"
  → 회사명·금액·기법명은 그대로 적되 절대 굵게 X. 강조는 그 사실의 "해석·의미·행동 지침"에만."""

# v5.1: NER + 관계 추출 가이드 (영문·한국어 prompt 공통)
_NER_RULES = """
[엔티티·관계 추출]
본문에서 다음을 추출:
1) entities: 본문에 명시적으로 등장한 회사·기관·정부 부처·로펌·제품·정책·기술명 (인물명 제외).
   - 영문 원문 그대로 또는 한국어 표기로 (예: "OpenAI", "Anthropic", "삼성전자", "법무법인 광장", "EU AI Act", "Codex for Legal", "RAG").
   - 일반명사·약어(AI, ML, LLM 단독)·국가명 단독 제외.
   - 최대 12개.
2) relations: 본문에서 명확히 추론 가능한 엔티티 간 관계 triple. entities에 등록된 이름만 사용.
   - type: competes_with(경쟁), partners_with(제휴), acquires(인수), invests_in(투자), regulates(규제), adopts(도입), launches(출시), implements(정책구현), mentions(단순 언급 — 위 어디에도 안 맞을 때)
   - evidence: 본문에서 해당 관계를 설명하는 핵심 문구 80~150자 (단순 회사명 나열 X, "왜·어떻게·무엇이" 포함).
   - 본문에 명확히 언급되지 않은 관계는 빼라. false positive보다 missing이 낫다.
   - 최대 6개 triple."""

PROMPT_EN_FULL = """다음 영문 뉴스를 한국 전략·기획·AI 업무 담당자 관점에서 분석해주세요.

[뉴스]
제목: {title}
출처: {source} ({date})
요약: {summary}
카테고리: {categories}

규칙:
""" + _HIGHLIGHT_RULES + _NER_RULES + _PERSONA_SCORE_RULES + """
- '시사점:' 같은 접두어 없이 본문만.
- 시점 표현(지금 당장 / 이번 주 안에 / 이번 달 내 / 즉시 등) 사용 금지.

JSON만 응답하세요. 다른 텍스트 없이.

{{
  "summary_ko": "2~3문장. 핵심 사실 중심. 80~150자. 단정 어조 지양.",
  "insight_ko": "1~2문장. 본인 업무에 적용할 액션 가능한 시사점. 60~120자.",
  "entities": ["회사·기관·제품·정책명 리스트 (최대 12개)"],
  "relations": [
    {{"src": "엔티티A", "tgt": "엔티티B", "type": "competes_with|partners_with|acquires|invests_in|regulates|adopts|launches|implements|mentions", "evidence": "본문 80~150자 컨텍스트"}}
  ],
  "persona_score": 0,
  "persona_reason": "1문장 근거"
}}
"""

PROMPT_KO_INSIGHT_ONLY = """다음 한국어 뉴스에 대한 전략·기획·AI 업무 시사점을 작성하고 등장 엔티티·관계를 추출해주세요.

[뉴스]
제목: {title}
출처: {source} ({date})
요약: {summary}
카테고리: {categories}

규칙:
""" + _HIGHLIGHT_RULES + _NER_RULES + _PERSONA_SCORE_RULES + """
- 시점 표현(지금 당장 / 이번 주 안에 / 이번 달 내 / 즉시 등) 사용 금지.

JSON만 응답하세요. 다른 텍스트 없이.

{{
  "insight_ko": "1~2문장. 본인 업무에 적용할 액션 가능한 시사점. 60~120자.",
  "entities": ["회사·기관·제품·정책명 리스트 (최대 12개)"],
  "relations": [
    {{"src": "엔티티A", "tgt": "엔티티B", "type": "competes_with|partners_with|acquires|invests_in|regulates|adopts|launches|implements|mentions", "evidence": "본문 80~150자 컨텍스트"}}
  ],
  "persona_score": 0,
  "persona_reason": "1문장 근거"
}}
"""

# v5.2: 논문 전용 prompt — abstract 전체 + authors + arXiv Subjects 태그 활용
PROMPT_PAPER = """다음 AI/ML 학술 논문을 분석해주세요. abstract 전체와 저자·소속·arXiv Subjects 태그가 제공됩니다.

[논문]
제목: {title}
출처: {source} ({date})
arXiv ID: {arxiv_id}
저자: {authors}
arXiv 태그(Subjects): {arxiv_tags}

Abstract (원문):
{summary}

규칙:
""" + _HIGHLIGHT_RULES + """
[엔티티·관계 추출 — 논문 특화]
본문(abstract)에서 다음을 모두 추출:
1) entities (최대 15개):
   - 저자명 (위 [저자] 목록 그대로 1~3명 우선, 본문에 'we' 등은 X)
   - 소속 기관 (Stanford, MIT, Google DeepMind, Meta FAIR, KAIST, Tsinghua 등)
   - 비교·사용된 시스템·제품 (Claude Code, GPT-4, Gemini, OpenClaw, CheetahClaws 등)
   - 사용·소개된 벤치마크 (MMLU, SWE-bench, HumanEval, ARC-AGI 등)
   - 핵심 기법·아키텍처명 (RAG, MoE, CoT, Tree-of-Thought, DPO, Constitutional AI 등)
   - arXiv 태그(cs.AI, cs.CL 등)도 entities에 포함 (단 한국어 표기 X, 원문 그대로)
2) relations (최대 5개):
   - 저자 ↔ 소속 기관: launches (저자가 소속에서 시스템 출시·발표한 경우)
   - 새 시스템 ↔ 비교 대상: competes_with (예: CheetahClaws ↔ Claude Code)
   - 소속 기관 ↔ 시스템: launches
   - 시스템 ↔ 벤치마크: mentions
   - evidence: abstract 본문에서 인용 (80~150자, 결과·메커니즘 포함)

""" + _PERSONA_SCORE_RULES + """

JSON만 응답하세요. 다른 텍스트 없이.

{{
  "summary_ko": "2~3문장. 논문의 핵심 기여·방법·결과 중심. 100~200자.",
  "insight_ko": "1~2문장. 대형로펌 경영전략팀 관점에서 이 논문이 시사하는 바. 60~120자.",
  "entities": ["저자·기관·시스템·벤치마크·기법·arXiv 태그 리스트 (최대 15개)"],
  "relations": [
    {{"src": "엔티티A", "tgt": "엔티티B", "type": "competes_with|partners_with|acquires|invests_in|regulates|adopts|launches|implements|mentions", "evidence": "abstract 인용 80~150자"}}
  ],
  "persona_score": 0,
  "persona_reason": "1문장 근거 — 논문이 대형로펌 실무에 시사하는 바 중심"
}}
"""

# v5.1: 낮은 점수 한국어 article (insight 가치 낮지만 NER은 필요)
PROMPT_KO_NER_ONLY = """다음 한국어 뉴스에서 등장 엔티티와 엔티티 간 관계만 추출해주세요. 시사점·요약은 작성하지 마세요.

[뉴스]
제목: {title}
출처: {source} ({date})
요약: {summary}
카테고리: {categories}

규칙:
""" + _NER_RULES + """

JSON만 응답하세요. 다른 텍스트 없이.

{{
  "entities": ["회사·기관·제품·정책명 리스트 (최대 12개)"],
  "relations": [
    {{"src": "엔티티A", "tgt": "엔티티B", "type": "competes_with|partners_with|acquires|invests_in|regulates|adopts|launches|implements|mentions", "evidence": "본문 80~150자"}}
  ]
}}
"""


def _absorb_ner_fields(item: dict, result: dict) -> None:
    """v5.1: LLM 응답에서 entities + relations 필드를 item에 흡수.
    엔티티는 최대 12개 string, 관계는 최대 6개 dict.
    v6.8: persona_score (0~10) + persona_reason 추가 흡수.
    """
    ents = result.get("entities")
    if isinstance(ents, list):
        cleaned = []
        for e in ents:
            if isinstance(e, str):
                s = e.strip()
                if 1 < len(s) < 60:
                    cleaned.append(s)
        item["entities"] = cleaned[:12]
    rels = result.get("relations")
    if isinstance(rels, list):
        cleaned_r = []
        VALID_TYPES = {"competes_with", "partners_with", "acquires", "invests_in",
                       "regulates", "adopts", "launches", "implements", "mentions"}
        for r in rels:
            if not isinstance(r, dict):
                continue
            src = (r.get("src") or "").strip()
            tgt = (r.get("tgt") or "").strip()
            rtype = (r.get("type") or "").strip()
            ev = (r.get("evidence") or "").strip()[:200]
            if not src or not tgt or src == tgt:
                continue
            if rtype not in VALID_TYPES:
                continue
            cleaned_r.append({"src": src, "tgt": tgt, "type": rtype, "evidence": ev})
        item["relations"] = cleaned_r[:6]
    # v6.8 (Phase 2): persona_score 흡수 — 0~10 정수 cap, 음수·문자열 방어.
    ps = result.get("persona_score")
    if ps is not None:
        try:
            ps_int = int(ps)
            if 0 <= ps_int <= 10:
                item["persona_score"] = ps_int
        except (ValueError, TypeError):
            pass
    pr = result.get("persona_reason")
    if isinstance(pr, str):
        pr_clean = pr.strip()
        if pr_clean:
            item["persona_reason"] = pr_clean[:200]


def enrich_item(item: dict) -> dict:
    """단일 항목 enrichment.

    v5.1 분기:
    - 영문: summary + insight + entities + relations (threshold 무관)
    - 한국어 + 점수>=threshold: insight + entities + relations
    - 한국어 + 점수<threshold: entities + relations만 (NER lightweight)
    """
    lang = item.get("lang", "en")
    score = item.get("score", 0)
    title = item.get("title", "")
    source = item.get("source", "")
    date = item.get("date", "")[:10]
    categories = ", ".join(item.get("categories", []))
    is_paper = (item.get("source_type") == "arxiv") or ("papers" in (item.get("categories") or []))
    paper_meta = item.get("paper_meta") or {}

    # v5.2: 논문은 abstract 전체 활용 (1800자), 일반은 400자
    summary = item.get("summary", "")[:1800 if is_paper else 400]

    # v5.2: 논문은 전용 prompt 사용 (저자·태그·전체 abstract 포함)
    if is_paper:
        authors_str = ", ".join(paper_meta.get("authors") or []) or "(정보 없음)"
        tags_str = ", ".join(paper_meta.get("arxiv_tags") or []) or "(없음)"
        arxiv_id = paper_meta.get("arxiv_id") or "(없음)"
        prompt = PROMPT_PAPER.format(
            title=title, source=source, date=date,
            arxiv_id=arxiv_id, authors=authors_str, arxiv_tags=tags_str,
            summary=summary,
        )
        result = call_llm_json(prompt, max_tokens=1400, temperature=0.3)
        if isinstance(result, dict):
            if "summary_ko" in result:
                item["summary_ko"] = result["summary_ko"].strip()
            if "insight_ko" in result:
                item["insight_ko"] = result["insight_ko"].strip()
            _absorb_ner_fields(item, result)
            item["llm_enriched"] = True
        return item

    if lang == "en":
        prompt = PROMPT_EN_FULL.format(
            title=title, source=source, date=date,
            summary=summary, categories=categories,
        )
        result = call_llm_json(prompt, max_tokens=900, temperature=0.3)
        if isinstance(result, dict):
            if "summary_ko" in result:
                item["summary_ko"] = result["summary_ko"].strip()
            if "insight_ko" in result:
                item["insight_ko"] = result["insight_ko"].strip()
            _absorb_ner_fields(item, result)
            item["llm_enriched"] = True

    elif lang == "ko":
        if score >= INSIGHT_THRESHOLD_KO:
            prompt = PROMPT_KO_INSIGHT_ONLY.format(
                title=title, source=source, date=date,
                summary=summary, categories=categories,
            )
            result = call_llm_json(prompt, max_tokens=700, temperature=0.3)
            if isinstance(result, dict):
                if "insight_ko" in result:
                    item["insight_ko"] = result["insight_ko"].strip()
                _absorb_ner_fields(item, result)
                item["llm_enriched"] = True
        else:
            # v5.1: 점수 낮은 한국어도 NER lightweight 패스 — entities + relations만
            prompt = PROMPT_KO_NER_ONLY.format(
                title=title, source=source, date=date,
                summary=summary, categories=categories,
            )
            result = call_llm_json(prompt, max_tokens=500, temperature=0.2)
            if isinstance(result, dict):
                _absorb_ner_fields(item, result)
                item["ner_only"] = True  # insight 없이 NER만 처리됐음 표시

    # v6.8 (Phase 2): persona_score가 새로 부여됐으면 score 재계산.
    #   keyword_score는 유지되고 persona boost (+0~+30)가 가산됨.
    if item.get("persona_score") is not None:
        try:
            from common import score_item as _rescore
            new_score = _rescore(
                item.get("title", ""),
                item.get("summary", ""),
                item.get("date"),
                item.get("categories", []),
                persona_score=item.get("persona_score"),
                # v6.10 (Phase 3): source 전달 → BOOKMARK_BONUS_SOURCES 매칭
                source=f"{item.get('source', '')} {item.get('url', '')}",
            )
            item["score"] = new_score
        except Exception:
            pass  # rescore 실패해도 enrich 결과는 보존

    return item


def needs_enrich(item: dict) -> bool:
    """이 항목이 enrich 대상인지 판단

    v2.7.1: 모든 영문 카드는 summary_ko + insight_ko 둘 다 있어야 함.
    v5.1: entities 필드도 필요 (없으면 재 enrich) — 856건 NER 자동 채움.
    """
    lang = item.get("lang", "en")
    score = item.get("score", 0)

    has_entities = "entities" in item  # v5.1: NER 결과 보유 여부

    if lang == "en":
        # 영문은 summary_ko + insight_ko + entities 모두 필요
        if not item.get("summary_ko") or not item.get("insight_ko"):
            return True
        if not has_entities:
            return True
        return False
    elif lang == "ko":
        # 한국어: 점수 높으면 insight + entities 필요, 낮으면 entities만 필요
        if score >= INSIGHT_THRESHOLD_KO:
            if not item.get("insight_ko") or not has_entities:
                return True
        else:
            if not has_entities:
                return True
        return False
    return False


def main():
    backend = detect_backend()
    model_env = os.environ.get("ANTHROPIC_MODEL") or os.environ.get("OPENAI_MODEL") or "(default)"
    print(f"[start] enrich_with_llm @ {datetime.now(KST).isoformat()}", flush=True)
    print(f"  [llm] backend: {backend} · model: {model_env}", flush=True)

    if backend == "none":
        print("  [warn] No LLM backend available. Skipping enrichment.", flush=True)
        with open(INPUT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["enriched_at"] = datetime.now(KST).isoformat()
        data["llm_backend"] = "none"
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data["items"]

    # 캐시 적용
    existing_cache = {}
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                prev = json.load(f)
                for it in prev.get("items", []):
                    # v5.1: enriched 또는 ner_only(점수 낮은 ko NER 패스) 둘 다 캐시
                    if it.get("llm_enriched") or it.get("ner_only"):
                        existing_cache[it["url"]] = {
                            "summary_ko": it.get("summary_ko"),
                            "insight_ko": it.get("insight_ko"),
                            "entities": it.get("entities"),
                            "relations": it.get("relations"),
                            "llm_enriched": it.get("llm_enriched"),
                            "ner_only": it.get("ner_only"),
                        }
        except Exception:
            pass

    # v2.8.5: 최근 N일 항목은 캐시 무시 (force refresh)
    refresh_cutoff = None
    if REFRESH_RECENT_DAYS > 0:
        from datetime import datetime as _dt
        cutoff_dt = _dt.now(KST) - timedelta(days=REFRESH_RECENT_DAYS)
        refresh_cutoff = cutoff_dt.strftime("%Y-%m-%d")
        print(f"  [refresh] 최근 {REFRESH_RECENT_DAYS}일치 (>= {refresh_cutoff}) 캐시 무시하고 재 enrich", flush=True)

    def is_recent(it):
        if not refresh_cutoff:
            return False
        d = (it.get("date", "") or "")[:10]
        if not d:
            return False
        return d >= refresh_cutoff

    cached_count = 0
    refresh_count = 0
    for it in items:
        # 최근 N일 항목 → 캐시 무시하고 enrich 대상으로 → 기존 필드 모두 삭제
        if is_recent(it):
            if it.get("summary_ko") or it.get("insight_ko") or it.get("entities"):
                refresh_count += 1
            it.pop("summary_ko", None)
            it.pop("insight_ko", None)
            it.pop("entities", None)
            it.pop("relations", None)
            it.pop("llm_enriched", None)
            it.pop("ner_only", None)
            continue
        if it["url"] in existing_cache:
            cache = existing_cache[it["url"]]
            if cache.get("summary_ko"):
                it["summary_ko"] = cache["summary_ko"]
            if cache.get("insight_ko"):
                it["insight_ko"] = cache["insight_ko"]
            # v5.1: entities + relations 캐시 복원
            if cache.get("entities") is not None:
                it["entities"] = cache["entities"]
            if cache.get("relations") is not None:
                it["relations"] = cache["relations"]
            if cache.get("llm_enriched"):
                it["llm_enriched"] = True
                cached_count += 1
            elif cache.get("ner_only"):
                it["ner_only"] = True
                cached_count += 1

    need_list = [it for it in items if needs_enrich(it)]
    if REFRESH_RECENT_DAYS > 0:
        print(f"  cached: {cached_count}, refreshed (cleared): {refresh_count}, need enrich: {len(need_list)} (max per run: {MAX_PER_RUN})", flush=True)
    else:
        print(f"  cached: {cached_count}, need enrich: {len(need_list)} (max per run: {MAX_PER_RUN})", flush=True)

    def save_partial():
        data["enriched_at"] = datetime.now(KST).isoformat()
        data["llm_backend"] = backend
        data["enriched_total"] = sum(1 for it in items if it.get("llm_enriched"))
        data["items"] = items
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    save_partial()

    enriched_count = 0
    for i, it in enumerate(need_list[:MAX_PER_RUN]):
        print(f"  [{i+1}/{min(len(need_list), MAX_PER_RUN)}] [{it.get('lang','?')}] {it['title'][:60]}", flush=True)
        enrich_item(it)
        enriched_count += 1
        time.sleep(0.3)
        if enriched_count % 10 == 0:
            save_partial()

    save_partial()
    print(f"[done] enriched +{enriched_count} (total {data['enriched_total']}/{len(items)})", flush=True)


if __name__ == "__main__":
    main()
