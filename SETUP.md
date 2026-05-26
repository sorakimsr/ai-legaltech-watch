# 운영 가이드

본 문서는 fork·재배포할 때 필요한 설정만 모아둔 운영자용 문서입니다.

## 1. GitHub Secrets

| 이름 | 용도 | 필수 |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude 호출 (요약·시사점·논문 분석) | ✅ |
| `OPENAI_API_KEY` | fallback / AI 분석 백엔드 | 선택 |
| `NAVER_CLIENT_ID` + `NAVER_CLIENT_SECRET` | Naver 검색 API | 선택 |
| `VAULT_PAT` + `VAULT_REPO` | Obsidian Vault 자동 sync | 선택 |
| `OPENALEX_API_KEY` | OpenAlex polite-pool 진입 | 선택 |

## 2. 워크플로우 환경변수

- `ANTHROPIC_MODEL` — 기본 `claude-sonnet-4-6` (enrich는 `claude-haiku-4-5-20251001`)
- `ENRICH_TOP_N` / `ENRICH_MAX_PER_RUN` — 빌드당 enrich 상위 N개 (기본 500)
- `STRATEGY_FORCE_REFRESH` / `PAPERS_FORCE_REFRESH` — 프롬프트 변경 후 weekly/monthly 강제 재생성

## 3. Cloudflare Worker (AI 분석 프록시)

```bash
cd cloudflare-worker
wrangler login
wrangler secret put ANTHROPIC_API_KEY    # sk-ant-...
wrangler secret put OPENAI_API_KEY       # sk-...

# Rate limit KV (v6.0부터 필수)
wrangler kv namespace create RATE_LIMIT
# 출력된 ID를 wrangler.toml의 [[kv_namespaces]] 블록에 붙여넣기

wrangler deploy
```

`wrangler.toml`의 KV ID가 비어 있으면 worker가 **503**을 반환합니다(서버 키 무방비 노출 방지).
본인 API 키 모드(`X-User-Api-Key` 헤더)는 KV 없이도 동작.

프론트엔드 `app.js`의 `WORKER_ENDPOINT` 상수를 본인 worker URL로 변경.

## 4. 수동 트리거

Actions → **Daily News Update** → Run workflow.

| 입력 | 효과 |
|---|---|
| `skip_fetch=true` | 기존 `raw_news.json` 재사용 (빠른 재처리) |
| `skip_enrich=true` | LLM enrichment 건너뜀 (비용 절약) |
| `skip_strategy=true` | Daily/Weekly/Monthly 카드 생성 건너뜀 |
| `deploy_only=true` | 데이터 갱신 없이 Pages만 재배포 (UI 변경 후) |
| `refresh_recent_days=N` | 최근 N일 항목 enrich 재실행 (캐시 무시) |
| `strategy_force_refresh=true` | weekly/monthly 시사점 강제 재생성 |

## 5. 로컬 분석 도구

```bash
# 사용자 북마크 ↔ score 회귀 분석
# DevTools → Application → Local Storage → daibfy_saved_v1 export
#   → data/_local_bookmarks.json 으로 저장 (gitignored)
python scripts/analyze_bookmark_signals.py
```

## 6. 점수·BLACKLIST 정책

- `scripts/common.py` — 카테고리 분류, 4축 시그널, `score_item()`
- `scripts/blacklist.py` — BLACKLIST·BOILERPLATE·정치 인물 가드 (v6.0 분리)
- 점수 구간: `0~34` drop / `35~49` 약한 시그널 / `50~69` 검토 / `70~89` f/u / `90+` 즉시 보고
