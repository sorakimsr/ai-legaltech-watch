# AI & Legaltech Watch — v2.7

> 한국 전략·기획 + AI 실무자를 위한 자동 큐레이션 대시보드
> KST 4시간마다 글로벌·국내 AI / 리걸테크 / 논문을 수집하고, LLM으로 한국어 요약·전략 시사점·논문 흐름 분석까지 생성합니다.

🌐 **Live:** [daibfy.com](https://daibfy.com)
📂 **Vault (Obsidian) 백업:** 별도 private repo로 매일 자동 sync

---

## 1. 무엇을 하는 사이트인가

- 매일 **80여 개 글로벌·국내 소스**에서 AI / 리걸테크 / arXiv 논문을 수집
- **유사 기사 자동 병합** — Legora aOS 같이 매체별 표현이 달라도 묶임
- **Claude Sonnet 4.6**으로 영문 항목 한국어 요약 + 개별 카드 시사점 생성
- **Daily / Weekly / Monthly 전략·기획 시사점 카드** 자동 생성 — 발행일 기준으로 정확히 분리
- 시사점마다 **근거 출처 N건 드롭다운**으로 어떤 컨텐츠를 참조했는지 확인 가능
- **AI 논문 흐름 분석** — 14일치 논문을 부상 주제 / 핵심 기법 / 주요 기관 / 키워드 / 실무 시사점으로 압축, 각 항목마다 관련 논문 드롭다운
- **AI 분석 모달** — 선택한 카드 N개에 대해 Claude / OpenAI 자유 모델로 즉시 분석

---

## 2. 핵심 설계 원칙

1. **실무자 시점** — "Harvey가 무엇을 출시했다"보다 "이 흐름이 내 업무에 무슨 의미인가"를 우선
2. **발행일 = 컨텐츠 실제 발행/수정일** — 수집일 아님. arXiv는 API의 `updated`(v2 revision date) 사용
3. **시장 분석/정책 공백 기사가 단순 출시 뉴스보다 상위 노출** — score 가중치에 시장 구도·정책 공백·in-house 키워드 우선
4. **citation 강제** — 모든 시사점에 근거 출처 보장 (LLM 누락 시 점수 상위 자동 첨부)
5. **TREND/ACTION 좌우 분할** — 한 트렌드 안에서 본문(좌)과 실행 액션(우)을 2단 그리드로 한눈에

---

## 3. 데이터 파이프라인 (매 4시간)

```
scripts/fetch_news.py            # 80여 소스 RSS·API·Naver·Semantic Scholar 수집
        ↓
scripts/dedupe_similar.py        # 유사 기사 그룹화 (회사명·매체-일자 보너스)
        ↓
scripts/enrich_with_llm.py       # Claude Sonnet 4.6 한국어 요약·개별 시사점
        ↓
scripts/generate_strategy.py     # Daily/Weekly/Monthly 시사점 카드 생성
scripts/analyze_papers.py        # AI 논문 흐름 분석 (narrative + topics + techniques)
        ↓
data/news.json + data/strategy_history.json + data/paper_trends.json
        ↓
GitHub Pages → daibfy.com
        ↓
Obsidian Vault repo로 markdown export (옵션)
```

스케줄: `cron: "0 */4 * * *"` (UTC) = **KST 매 9, 13, 17, 21, 1, 5시 자동 실행**

---

## 4. 소스 카탈로그 (총 80개)

| 카테고리 | 개수 | 비고 |
|---|---|---|
| RSS (안정) | 21 | OpenAI, Google AI, MSFT, NVIDIA, Hugging Face, TechCrunch, Wired, Above the Law 등 |
| Google News site: 우회 | 42 | RSS feed가 없거나 막힌 소스 (Anthropic, Meta AI, Mistral, Stability, Perplexity, Harvey, Legora, The Verge, The Information, Law.com 등) + 실무자 관점 키워드 검색 |
| arXiv API | 6 | cs.AI · cs.CL · cs.LG · cs.IR · cs.MA · cs.CY — `lastUpdatedDate` 기준 |
| Semantic Scholar API | 1 | Google Scholar 대체. AI 8개 쿼리 |
| 국내 RSS | 9 | AI타임스, ZDNet Korea, 전자신문, 바이라인, 디일렉, 플래텀 등 |
| Naver Search API | (선택) | NAVER_CLIENT_ID 등록 시 활성화. 리걸테크·BHSN·로앤컴퍼니 등 키워드 검색 |

---

## 5. 필터링·스코어

**Boilerplate 즉시 차단** — "이 기사는 생성형 AI로 제작" 같은 자동 생성 라이프스타일 기사는 모든 소스에서 제외

**Blacklist** — 선거·정치, 부음·장례, 운세·MBTI, 라이프집·상표출원 등 비관련 토픽 차단

**Score 가중치 (실무자 관점, 0~150)**

- 시장 구도/경쟁 분석: `borrowed time` `commoditising` `wrappers` `in-house` `open source` `disruption` → +12~22
- 정책 공백: `가이드라인 공백` `규제 공백` `기준 못` `AI 거버넌스` `EU AI Act` → +12~22
- 단순 출시 (`launches` `announces` `unveils`): +3만 (이전 6에서 하향)
- 도메인 보너스: legaltech +8, papers +5, funding +4, domestic +3
- 최신성: 24h 이내 +10, 72h +5, 1주일 +2

---

## 6. UI

### 사이드바 (관점·뷰)
- **전략·기획 시사점** (Daily / Weekly / Monthly) — 시사점 카드는 TREND(좌) + ACTION(우) 2단 그리드, 근거 출처 N건 드롭다운
- **중요도 TOP** — score 기준 상위
- **오늘 추가됨** — 오늘 첫 수집
- **최신순** — 발행일 정렬
- **AI 논문 흐름** — 한국 시사점 narrative → 실무 시사점 → 부상 주제·핵심 기법 → 기관·키워드 → 논문 목록
- **소스 현황** (현재 상태 / 7일 추이)

### 카드 (메인 view)
- 다중 선택 후 **AI 분석 모달** → Claude / OpenAI 모델 선택해 분석 실행
- 유사 기사 그룹화 시 "관련 N건" 배지

### 소스 현황
- 기간 dropdown (오늘 / 7일 / 30일 / 전체) — 카테고리 탭 row 우측 inline
- 7일 추이 차트는 **소스별 / 컨텐츠 태그별** 토글
- 컬럼: 소스 / 유형 / 상태 / 기간 내 수집 / 신규 / 마지막 활성 / URL

---

## 7. AI 분석 백엔드 (Cloudflare Worker)

- `cloudflare-worker/worker.js` — `POST /analyze` 엔드포인트
- 모델 화이트리스트: Claude (opus-4-6 / sonnet-4-6 / haiku-4-5 / 3-7-sonnet / 3-5-haiku) + OpenAI (gpt-4o / gpt-4o-mini / gpt-4-turbo / o1 / o1-mini)
- Smart Placement(`mode = "smart"`)로 OpenAI HKG 차단 우회
- IP당 일 5회 무료, 본인 API 키 입력 시 무제한 (`X-User-Api-Key` 헤더)
- 배포: `cd cloudflare-worker && npx wrangler deploy`

---

## 8. 디렉토리

```
ai-legaltech-watch/
├── index.html              # 대시보드 SPA
├── app.js                  # state + 렌더링
├── styles.css
├── scripts/
│   ├── sources.py          # 80개 소스 카탈로그
│   ├── fetch_news.py       # 수집 + 중복 방지
│   ├── dedupe_similar.py   # 유사 기사 병합
│   ├── enrich_with_llm.py  # LLM 한국어 요약·시사점
│   ├── generate_strategy.py # Daily/Weekly/Monthly 시사점
│   ├── analyze_papers.py   # 논문 흐름 분석
│   ├── llm_client.py       # Claude/OpenAI 백엔드 추상화 (Sonnet 4.6 기본)
│   ├── naver_fetcher.py    # Naver Search API
│   ├── semantic_scholar_fetcher.py # 논문 API
│   ├── common.py           # 카테고리·blacklist·score
│   └── export_to_vault.py  # Obsidian Vault sync
├── cloudflare-worker/      # AI 분석 백엔드
│   ├── worker.js
│   └── wrangler.toml
├── .github/workflows/
│   ├── daily-update.yml    # 매 4시간 자동 빌드
│   └── deploy-pages.yml    # push 시 자동 deploy
└── data/                   # 빌드 결과 (news.json / strategy_history.json / paper_trends.json / source_history.json)
```

---

## 9. 직접 운영 시

GitHub Secrets에 다음 등록:
- `ANTHROPIC_API_KEY` — 시사점·논문 분석용 Claude API 키
- `OPENAI_API_KEY` — fallback / AI 분석 백엔드용
- `NAVER_CLIENT_ID` + `NAVER_CLIENT_SECRET` — Naver Search 활성화 (선택)
- `VAULT_PAT` — Obsidian Vault 자동 sync (선택)

Workflow 환경변수:
- `ANTHROPIC_MODEL = "claude-sonnet-4-6"` — 기본 모델
- `ENRICH_TOP_N = 40` — 빌드당 enrich할 상위 N개
- `ENRICH_MAX_PER_RUN = 40` — 비용 캡

수동 트리거: Actions → Daily News Update → Run workflow

---

## 10. 변경 이력 요약

- **v2.7** (현재) — 시사점 본문 4~5문장 + ACTION 동사형 2~3문장, TREND/ACTION 좌우 2단 분할, 발행일 = 실제 컨텐츠 발행/수정일(arXiv API 교체로 v2 revision date 정확히), Semantic Scholar 통합, dedupe 임계값·매체-일자 보너스, 시장·정책 시그널 가중치, 보일러플레이트·운세·부음 등 차단 강화, 실패 RSS 23개 Google News 우회, cron 매 4시간, AI 모달 HTTPS redirect, 논문 부상 주제/핵심 기법에 관련 논문 드롭다운, 소스 현황 기간 필터·태그별 추이 토글, Sonnet 4.6 명시
- **v2.6** — 논문 흐름 분석 메뉴, push 시 자동 deploy, Cloudflare Workers 백엔드
- **v2.5** — 관련성 필터, 카드 태그 오분류 수정
- **v2.4** — Daily/Weekly/Monthly 시계열, 사이드바 expandable, 시사점 시계열 UI
- **v2.3** — NEW 배지, 오늘 신규 카운트
- **v2.2** — 누적·중복 방지, Citation, Vault export
- **v2.1** — 카테고리 엄격 분류, 영문 전체 한국어 요약
- **v2.0** — UI 전면 재설계, 소스 확장, LLM enrichment, 유사 뉴스 병합

---

## License & Disclaimer

수집된 컨텐츠 자체의 저작권은 원 매체에 있습니다. 본 사이트는 큐레이션·요약·시사점 제공을 위한 비상업 연구 프로젝트입니다.
