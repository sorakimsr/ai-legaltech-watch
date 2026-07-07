# v6.16.0 — CLI 모드 전환 (API key → 구독 OAuth)

> 2026-07-07. API 종량 과금($50/2~3일) → Claude Max 구독 한도 내 사용으로 전환.
> LLM 백엔드를 Claude Code CLI(`claude --print`)로 일원화.

## 변경된 파일

| 파일 | 변경 |
|---|---|
| `scripts/llm_client.py` | ① `call_claude_cli`: prompt를 argv→stdin 전달(대형 프롬프트 안전), 재시도·백오프 3회(5s·20s — v6.15.57 SDK 방어를 CLI에도 적용), max_tokens>8000이면 timeout 300→900s. ② `detect_backend`: 자동감지 우선순위 CLI 최우선으로 역전 |
| `.github/workflows/daily-update.yml` | ① Node 20 + Claude Code CLI 설치 step 재도입. ② 인증 smoke test step(fail fast — 토큰 무효 시 1시간 빌드 낭비 방지). ③ Step 3/4/4d의 `ANTHROPIC_API_KEY` 제거 → `CLAUDE_CODE_OAUTH_TOKEN` + `LLM_BACKEND=claude-cli`. `OPENAI_API_KEY`(gpt-4o-mini)는 최후 비상 폴백으로 유지 |

## 사용자가 해야 할 일 (push 전)

1. **로컬 PC에서 토큰 생성**: 터미널에서 `claude setup-token` 실행 → 브라우저 인증 → 출력된 토큰 복사 (Max 구독 계정, 약 1년 유효)
2. **GitHub secret 등록**: repo → Settings → Secrets and variables → Actions → New repository secret
   - Name: `CLAUDE_CODE_OAUTH_TOKEN`, Value: 위 토큰
3. **이 변경사항 commit & push**
4. **테스트 빌드**: Actions → Daily News Update → Run workflow (`skip_fetch=true`로 캐시 재사용하면 빠름). "Verify Claude CLI auth" step 통과 여부 확인
5. **(권장) 기존 `ANTHROPIC_API_KEY` secret 삭제** — 과금 원천 차단. 코드가 더 이상 참조하지 않으므로 남겨둬도 무해하나, 실수 재유입 방지 차원

## 주의사항

- **CLI는 max_tokens/temperature 미지원** — 호출부 값은 무시됨. 잘림·형식 이슈는 기존 `call_llm_json`의 다단 복구(json_repair·bracket salvage)가 흡수. 전략 카드(기존 max_tokens 24000)는 CLI 출력 한도 내에서 정상 생성 예상되나, 첫 1~2빌드는 daily 카드 수 확인 권장
- **Max 20x 한도**: 빌드당 enrich ≤400건(Haiku) + 전략/논문/관계(Sonnet·Haiku) ≈ 대략 100~150만 토큰. 하루 2회(KST 06/18)는 5시간 window가 분리되어 있어 감당 가능할 것으로 예상. 만약 한도 도달 로그(429류)가 반복되면 `ENRICH_MAX_PER_RUN` 400→300 축소가 1차 조치 (backlog는 다음 빌드가 캐시 기반으로 자동 이어 처리)
- **토큰 만료**: 약 1년. 만료 시 smoke test step이 즉시 실패하므로 발견 용이 — `claude setup-token` 재실행 후 secret 갱신
- **Cloudflare Worker(`/analyze`)는 별개**: 사이트 방문자용 AI 분석 프록시는 여전히 Worker의 `ANTHROPIC_API_KEY` secret 사용 (IP당 일 5회 제한이라 비용 미미). CLI는 Worker 환경에서 실행 불가이므로 유지
- **동시 실행**: Step 4에서 strategy/papers가 CLI 프로세스 2개로 병렬 실행 — `--print` 일회성 호출이라 세션 충돌 없음

## 검증 기록 (2026-07-07)

- `test_llm_json_repair.py` 5/5 통과
- fake CLI로 재시도 검증: 2회 실패(exit 1) 후 3회째 성공, 백오프 5s+20s, stdin 프롬프트 전달, JSON 파싱 정상
- 자동감지 우선순위: CLI 최우선 확인
- YAML/py 문법 검사 통과
- `test_dedupe_2stage.py` 1건 실패는 GitHub main 기존 이슈(이번 변경과 무관)
