# v6.17.0 — 시사점 품질 구조 개선 (2026-07-07)

## 계기

7/7 daily에서 같은 기사 1건(LG 멀티에이전트 주가예측)이 TREND 01·TREND 06 두 카드의
유일한 근거로 재사용됨 (사용자 발견). 원인 진단:

1. 60:40 균형 룰이 법조·기술 양면 기사를 두 버킷에서 재활용하도록 유도
2. "sources 3~5개 필수" 룰이 프롬프트에만 있고 코드 검증 없음
3. **주제 선정 단계가 없음** — 기사 30개 → 24K 토큰 단일 호출에 '주제 선정 + 근거 배분 + 본문 작성'이 뒤엉킴
4. 증분 빌드 중복 방지도 프롬프트 의존 (deterministic 검증 없음)

이 영역은 프롬프트 패치 다수 누적 지점(v6.15.20/.21/.26/.51) → 구조 개선으로 대응.

## 변경

### 신규: `scripts/strategy_quality.py`

- **Stage A `cluster_topics()`** — 기사 → 주제 클러스터 LLM 호출. 핵심 규칙: **각 기사는 최대 1개 클러스터** (배타적 근거 배분, 코드 후처리로 강제). 단일 기사 클러스터는 6대 어젠다·플래그십급만 허용. 북마크 ground-truth 힌트 주입.
- **Stage B `write_cluster_cards()`** — 클러스터별 소형 호출(max_tokens 2200)로 카드 작성. 24K 단일 호출의 truncation 실패 모드 구조적 제거 + 클러스터 간 실패 격리.
- **검증 게이트 `validate_cards()`** — deterministic (LLM 비용 0): 카드 간 근거 URL Jaccard ≥ 0.5 또는 부분집합 → drop, 주제 토큰 유사도 ≥ 0.6 → drop. full/증분/weekly/monthly 모든 경로 적용. 증분에서는 기존 카드 대비 검증.
- **`load_bookmark_hints()`** — `data/bookmarks_export_*.json`(+ `_local_bookmarks.json`)의 ⭐ 저장 기사를 주제 선정 가중치 힌트로 변환 (news.json 매칭 제목 또는 URL slug).

### 수정: `scripts/generate_strategy.py`

- `generate_cards()`: daily는 2단계 경로 우선, 실패 시 레거시 단일 호출 자동 폴백. `STRATEGY_TWO_STAGE=0`으로 비활성화 가능. weekly/monthly는 효과 검증 후 확대 예정 (검증 게이트는 즉시 적용).
- 증분 경로: `validate_cards(add_cards, existing_cards=...)` 추가.
- PROMPT_TEMPLATE·증분 템플릿: "동일 기사 인덱스 재사용 절대 금지, 양면 이슈는 카드 1개 안에서 서술" 룰 추가 (레거시 폴백·weekly/monthly용).

### 신규: `scripts/test_strategy_quality.py` — 16 tests

7/7 LG 사례 재현 테스트 포함. 전체 33 passed (기존 테스트 회귀 없음).

## 운영 노트

- LLM 호출 수: daily 기준 1회 → 최대 12회(클러스터 1 + 카드 5~10 + summary 1). CLI 모드(구독)라 종량 비용 증가 없음. 빌드 시간 +5~10분 예상 (timeout 180분 내 여유).
- 북마크 힌트를 최신화하려면 사이트에서 북마크 export를 `data/bookmarks_export_YYYYMMDD.json`으로 갱신.
- 모니터링 포인트: 빌드 로그의 `[stage-A]`(클러스터 수·legal:frontier 비율), `[검증 게이트 drop]`(중복 차단 발동), `[two-stage] 예외`(폴백 발생).
