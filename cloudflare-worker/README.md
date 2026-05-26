# AI Analysis Proxy (Cloudflare Workers)

`daibfy.com` 정적 사이트에서 AI 분석 기능을 안전하게 호출하기 위한 서버리스 프록시.

## 무엇을 하나
- 브라우저(daibfy.com) → 이 Worker → OpenAI/Anthropic API → 결과 반환
- API 키는 Worker Secrets에 저장 (브라우저 노출 X)
- IP당 일 5회 무료 + 본인 API 키 입력 시 무제한

## 셋업 (10분)

### 1. Cloudflare 계정 생성
- https://dash.cloudflare.com/sign-up — 이메일만으로 가입 (결제 정보 X)

### 2. Wrangler CLI 설치
```bash
npm install -g wrangler
wrangler login   # 브라우저 OAuth
```

### 3. 이 폴더에서 배포
```bash
cd cloudflare-worker
wrangler deploy
```
→ `https://daibfy-ai-proxy.<username>.workers.dev` 같은 URL이 출력됨. 메모.

### 4. Secrets 등록 (이미 GitHub에 있는 키 그대로)
```bash
wrangler secret put ANTHROPIC_API_KEY
# 프롬프트에 sk-ant-... 붙여넣기
wrangler secret put OPENAI_API_KEY
# 프롬프트에 sk-... 붙여넣기
```

(선택) 허용 도메인 명시:
```bash
wrangler secret put ALLOWED_ORIGINS
# "https://daibfy.com,https://sorakimsr.github.io,http://localhost:8000" 입력
```

### 5. Rate limit KV namespace 생성 (**필수** — v6.0)
```bash
wrangler kv namespace create RATE_LIMIT
```
출력되는 ID를 복사 → `wrangler.toml` 의 주석된 부분을 풀고 ID 붙여넣기 → `wrangler deploy` 다시 실행.

> v6.0부터 KV namespace가 없으면 worker는 503으로 응답합니다(서버 측 API 키 무방비 노출 방지).
> 본인 API 키 모드(`X-User-Api-Key` 헤더)는 KV 없이도 동작합니다.

### 6. (선택) 커스텀 도메인 `api.daibfy.com` 연결
- Cloudflare Dashboard → Workers & Pages → 본 worker → Settings → Triggers → Custom Domain
- `api.daibfy.com` 입력 (Cloudflare가 자동으로 DNS 설정. 단 도메인이 Cloudflare에 등록돼있어야 함 — 가비아라면 네임서버 변경 필요)
- 또는 그냥 기본 `*.workers.dev` URL 사용

### 7. 프론트엔드 (daibfy.com)에서 endpoint 등록
`app.js` 상단의 `WORKER_ENDPOINT` 값을 본인 worker URL로:
```javascript
const WORKER_ENDPOINT = "https://daibfy-ai-proxy.<username>.workers.dev/analyze";
// 또는 커스텀 도메인 연결했다면:
// const WORKER_ENDPOINT = "https://api.daibfy.com/analyze";
```

## 비용

- Cloudflare Workers 무료 한도: **일 100,000 요청** (개인용으론 무제한이나 다름없음)
- 사용자님이 부담하는 건 OpenAI/Anthropic 사용량만:
  - IP당 일 5회 × 사용자 N명 = 일 5N회 호출
  - 평균 분석 1회 = OpenAI gpt-4o-mini 약 $0.005 / Claude Sonnet 약 $0.02
  - 사용자 10명 × 일 5회 × $0.02 = 일 $1 (Claude 기준)

## 보안

- API 키는 Worker Secrets에만 (DB 저장 X, 로그 X)
- CORS는 명시된 도메인만 허용
- Rate limit으로 남용 차단
- Worker는 stateless — 분석 내용 저장 안 함

## 동작 확인

```bash
curl -X POST https://daibfy-ai-proxy.<username>.workers.dev/analyze \
  -H "Content-Type: application/json" \
  -d '{"backend": "openai", "prompt": "안녕? 한 줄로 답해줘."}'
```
