# AI & Legaltech Watch

한국 전략·기획·AI 실무자를 위한 자동 큐레이션 대시보드.
KST 기준 하루 3회 글로벌·국내 AI / 리걸테크 / arXiv 논문을 수집해 LLM으로 한국어 요약과 시사점을 만들어 보여줍니다.

🌐 **Live:** [daibfy.com](https://daibfy.com)

---

## 무엇을 하나

매일 80여 개 소스에서 AI·리걸테크 뉴스와 arXiv 논문을 모아, Claude(Sonnet 4.6 / Haiku 4.5)로 한국어 요약·시사점·전략 카드를 생성합니다. 결과는 Daily / Weekly / Monthly 시계열로 정리되고, 시사점마다 근거 출처가 함께 따라옵니다.

대형 로펌 경영전략팀 페르소나에 맞춰, 단순 출시 뉴스보다 **시장 구도·정책 공백·도입 사례·규제** 같은 행동 가치가 높은 신호를 상단에 노출합니다.

## 어떻게 만드나

```
fetch_news → dedupe_similar → enrich_with_llm → generate_strategy / analyze_papers
   ↓             ↓                  ↓                          ↓
  80개 소스   유사 기사 병합       한국어 요약·시사점        Daily/Weekly/Monthly 카드
   ↓
data/*.json → GitHub Pages → daibfy.com
```

- **스케줄:** GitHub Actions cron으로 KST 06·18·24시 (UTC 9·15·21) 자동 실행
- **AI 분석 모달:** 사용자가 선택한 카드들을 즉시 Claude/OpenAI로 분석. Cloudflare Worker 프록시 경유 (IP당 일 5회 무료 + 본인 키 무제한)

## 주요 화면

- **시사점** — Daily/Weekly/Monthly 전략 카드 (TREND + ACTION 좌우 2단, 근거 출처 드롭다운)
- **뉴스 피드** — 카테고리·날짜·언어 필터, 정렬(중요도/최신/오늘)
- **AI 논문 흐름** — 최근 흐름·실무 시사점·부상 주제·키워드·핵심 논문 목록
- **엔티티 / 지식그래프** — 회사·로펌·정책·기술 추적 + 관계 시각화(D3)
- **저장한 항목 / AI 분석 결과** — localStorage 기반 북마크와 분석 히스토리
- **소스 현황** — 80개 소스 상태와 7일 추이

## 디렉토리

```
ai-legaltech-watch/
├── index.html · app.js · app.util.js · styles.css   # SPA
├── scripts/         # 수집·dedupe·enrich·전략 생성 파이프라인
├── cloudflare-worker/   # AI 분석 프록시
├── .github/workflows/   # daily-update.yml (4단계 빌드)
└── data/            # 빌드 산출물 (news.json, strategy_history.json, ...)
```

더 자세한 운영 방법(GitHub Secrets, KV namespace 설정, 수동 재빌드)은 [`SETUP.md`](SETUP.md) 참고.

## 변경 이력

- **v6.0** — 코드 리뷰 일괄 반영: LEGAL_SIGNALS 분리, Worker CORS/KV/키검증 보안 강화, CSP·session-only 키 토글, news.json CDN 캐싱 복구, dedupe O(N²) 완화, `app.util.js`·`blacklist.py` 모듈 분리, 빌드 알림. 자세한 변경 내역은 [`CODE_REVIEW_FIXES_2026-05-26.md`](CODE_REVIEW_FIXES_2026-05-26.md) 참고.
- **v3~v5** — 4축 시그널 매트릭스(DECISION/REGULATORY/MARKET/LEGAL) + AI 관련성 게이트, BLACKLIST 정교화, 엔티티/지식그래프, 논문 abstract 전체 활용, NER lightweight 패스.
- **v2.x** — 시사점 시계열(Daily/Weekly/Monthly), 유사 기사 병합, citation 강제, AI 분석 모달, Cloudflare Workers 백엔드.

## License & Disclaimer

수집된 컨텐츠의 저작권은 원 매체에 있습니다. 본 사이트는 큐레이션·요약·시사점 제공을 위한 **비상업 연구 프로젝트**입니다.
