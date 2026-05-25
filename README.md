# AI & Legaltech Watch v2

매일 KST 오전 6시 자동으로 50+ 신뢰 소스에서 글로벌 AI 산업·리걸테크·AI 논문 뉴스를 수집하고, Claude로 한국어 요약·시사점·전략 카드를 자동 생성하는 라이브 대시보드입니다.

## 핵심 기능

### 데이터 파이프라인 (매일 오전 6시 자동 실행)

1. **Fetch** — 50+개 RSS·arXiv 소스에서 최신 항목 수집
2. **Dedupe** — 유사 뉴스(같은 사건을 다룬 여러 출처) 자동 그룹화. 대표 1개 + 관련 N건으로 표시
3. **Enrich** — 상위 40개 항목에 Claude로 한국어 요약·시사점 자동 생성
4. **Strategy** — 오늘 수집된 흐름 종합 → 전략·기획 시사점 카드 5~7개 매일 자동 갱신
5. **Deploy** — GitHub Pages로 자동 배포

### 데이터 소스 (50+)

**글로벌 AI 산업 (영문)**: OpenAI Blog, Anthropic News, Google AI / DeepMind / Research, Meta AI, Microsoft AI, NVIDIA, Hugging Face, Mistral, Stability AI, Perplexity Blog

**AI 매체**: MIT Technology Review AI, TechCrunch AI, VentureBeat AI, The Verge AI, Wired AI, Ars Technica, Axios AI, Semianalysis, The Decoder, Import AI, Ben's Bites, The Batch, AI Snake Oil, Last Week in AI

**리걸테크**: Artificial Lawyer, Legal IT Insider, Legal Cheek, LawSites, ABA Journal, Above the Law, Law.com Legal Tech, Legal Futures, Global Legal Post, Stanford CodeX, Harvey Blog, Legora Blog

**AI 논문**: arXiv cs.AI / cs.CL / cs.LG / cs.IR / cs.MA / cs.CY, Papers With Code

**국내 매체**: AI타임스, 법률신문(테크/전체), ZDNet Korea, 디지털타임스, 전자신문, 바이라인네트워크, 디일렉, 플래텀, 벤처스퀘어, 더밀크, 매일경제, 한국경제

### LLM 백엔드 (자동 선택)

우선순위:
1. **Claude Code CLI** (`claude --print`) — GitHub Actions에서 가장 안정적
2. **Anthropic SDK** — ANTHROPIC_API_KEY 등록 시
3. **OpenAI SDK** — OPENAI_API_KEY 등록 시 (폴백)

LLM이 없거나 호출 실패해도 파이프라인은 정상 동작 — 룰 기반 분류·점수·유사도만으로 사이트가 갱신됩니다.

### UI 특징

- 좌측 사이드바: 뉴스 / 리걸테크 / AI 논문 / 국내 동향 / 전략 카드 / 소스 현황
- 상단 통계: 전체 항목 수, AI 분석 완료 수, 유사 뉴스 병합 수, 활성 소스 수, LLM 백엔드
- 카테고리·언어·기간·정렬 필터, 키워드 검색
- 각 카드에 한국어 요약 + 시사점 + 유사 뉴스 그룹 토글
- 모든 항목에 명확한 출처·발행일자 표시

## 프로젝트 구조

```
ai-legaltech-watch/
├── index.html              메인 페이지
├── styles.css              스타일
├── app.js                  프론트엔드
├── data/
│   ├── raw_news.json       1단계: 수집된 원본
│   ├── deduped_news.json   2단계: 유사 뉴스 병합 후
│   ├── enriched_news.json  3단계: 한국어 요약·시사점 추가
│   └── news.json           4단계: 최종 (전략 카드 포함, 프론트엔드가 읽음)
├── scripts/
│   ├── common.py           공통 유틸 (정제·분류·점수)
│   ├── sources.py          소스 카탈로그 (50+ 소스 정의)
│   ├── llm_client.py       LLM 클라이언트 (Claude CLI / SDK / OpenAI 폴백)
│   ├── fetch_news.py       1단계
│   ├── dedupe_similar.py   2단계
│   ├── enrich_with_llm.py  3단계
│   ├── generate_strategy.py 4단계
│   └── requirements.txt
├── .github/
│   └── workflows/
│       └── daily-update.yml  5단계 자동 파이프라인
└── README.md
```

## 배포 가이드 (GitHub Pages)

### 1단계: GitHub 레포지토리 생성

1. GitHub.com 로그인 → 우측 상단 `+` → **New repository**
2. Repository name: `ai-legaltech-watch` (원하는 이름)
3. **Public** 선택 (GitHub Pages 무료 사용)
4. **Create repository** 클릭

### 2단계: 코드 업로드

방법 A) **웹에서 직접 업로드** (가장 쉬움)
1. 생성된 빈 레포에서 **uploading an existing file** 클릭
2. 이 폴더의 모든 파일을 드래그 (숨김 폴더 `.github` 포함)
3. **Commit changes**

방법 B) **터미널에서 Git 사용**
```bash
cd ai-legaltech-watch
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/ai-legaltech-watch.git
git push -u origin main
```

### 3단계: API 키를 GitHub Secrets에 등록 (필수)

LLM 한국어 요약·시사점·전략 카드를 자동 생성하려면 API 키가 필요합니다.

1. 레포지토리 **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** 클릭
3. 다음 두 개 등록:

| Name | Value |
|------|-------|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com/ 에서 발급 |
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys 에서 발급 |

> 둘 다 등록하면 Claude를 메인으로, GPT를 폴백으로 사용. 하나만 등록해도 동작.
> 키가 없어도 파이프라인은 돌아가지만 한국어 요약·시사점은 비어있게 됩니다.

### 4단계: GitHub Pages 활성화

1. 레포지토리 **Settings** → **Pages**
2. **Source**: **GitHub Actions** 선택 (중요!)

### 5단계: 첫 실행

1. **Actions** 탭 → 좌측 **Daily News Update** 워크플로우
2. 우측 **Run workflow** → **Run workflow** 클릭
3. 약 3~5분 후 초록 체크 ✓ (LLM 호출 시간 포함)
4. **Settings → Pages**에서 사이트 URL 확인

기본 URL: `https://YOUR_USERNAME.github.io/ai-legaltech-watch/`

### 6단계: 커스텀 도메인 연결

1. DNS에 CNAME 추가:
   - Host: `www` (또는 원하는 서브도메인)
   - Value: `YOUR_USERNAME.github.io`
2. GitHub **Settings → Pages → Custom domain** 에 도메인 입력
3. **Enforce HTTPS** 체크

### 7단계: 매일 자동 갱신

매일 UTC 21:00 = **KST 06:00** 자동 실행. Public 레포는 GitHub Actions 무제한 무료.

## 로컬 실행

```bash
cd ai-legaltech-watch

# 의존성
pip install -r scripts/requirements.txt

# (선택) Claude Code CLI 설치
npm install -g @anthropic-ai/claude-code

# 환경 변수 (둘 중 하나)
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."

# 5단계 순차 실행
python scripts/fetch_news.py        # 1단계
python scripts/dedupe_similar.py    # 2단계
python scripts/enrich_with_llm.py   # 3단계
python scripts/generate_strategy.py # 4단계

# 로컬 서버 (브라우저 fetch 차단 회피)
python -m http.server 8000
# → http://localhost:8000 열기
```

## 비용 가이드 (LLM)

- **Enrichment**: 매일 상위 40개에만 호출, 중복 호출 캐시. 1회 ~$0.05 (Claude Sonnet 기준) / ~$0.01 (GPT-4o-mini 기준)
- **Strategy**: 매일 1회 큰 프롬프트 1번. 1회 ~$0.02 (Claude Sonnet) / ~$0.005 (GPT-4o-mini)
- **월 예상**: Claude $2~3 / GPT $0.5 안팎

비용 절약 옵션:
- workflow 수동 실행 시 `skip_enrich: true` 입력하면 LLM 단계 건너뜀
- `ENRICH_TOP_N` 환경 변수로 enrich 항목 수 조정

## 커스터마이징

### 새 소스 추가

`scripts/sources.py` 의 `SOURCES` 리스트에 한 줄 추가하면 끝.

```python
("새 소스 이름", "https://example.com/rss", "rss", ["ai-industry"], "en"),
```

### 카테고리 키워드 / 점수 가중치

`scripts/common.py` 의 `CATEGORY_KEYWORDS`, `HIGH_VALUE_KEYWORDS` 수정.

### 유사도 임계값

`scripts/dedupe_similar.py` 의 `SIMILARITY_THRESHOLD` (기본 0.55) 조정.

### LLM 프롬프트

`scripts/enrich_with_llm.py` / `scripts/generate_strategy.py` 의 `PROMPT_TEMPLATE` 직접 수정.

## 라이선스

개인 사용 / 내부용.
