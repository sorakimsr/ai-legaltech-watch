// AI & Legaltech Watch — AI Analysis Proxy (Cloudflare Worker)
//
// Endpoint: POST /analyze
// Body: { backend: "claude" | "openai", prompt: string, system?: string, max_tokens?: number }
// Response: { result: string, backend: string, model: string }
//
// Secrets (Wrangler / Cloudflare Dashboard에서 설정):
//   ANTHROPIC_API_KEY — sk-ant-...
//   OPENAI_API_KEY    — sk-...
//   ALLOWED_ORIGINS   — "https://daibfy.com,https://sorakimsr.github.io" (선택)
//
// Rate limit: IP당 일 5회 (KV namespace 사용)
//   KV namespace 이름: RATE_LIMIT
//
// 사용자가 본인 API 키를 헤더 X-User-Api-Key + X-User-Backend 로 보내면
//   rate limit 우회 (본인 비용 부담)

const DEFAULT_MODELS = {
  claude: "claude-sonnet-4-6",
  openai: "gpt-4o-mini",
};

// 화이트리스트 (백엔드별 허용 모델). client가 임의 모델 호출 못하게.
const ALLOWED_MODELS = {
  claude: [
    "claude-opus-4-6",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "claude-3-7-sonnet-latest",
    "claude-3-5-haiku-latest",
  ],
  openai: [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "o1",
    "o1-mini",
  ],
};

const DAILY_FREE_LIMIT = 5;

export default {
  async fetch(request, env, ctx) {
    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(request, env) });
    }

    const url = new URL(request.url);

    if (url.pathname === "/health") {
      // v2.7.1: 콜로 정보 노출 → 지역 차단 진단
      return jsonResponse({
        status: "ok",
        colo: (request.cf && request.cf.colo) || "?",
        country: (request.cf && request.cf.country) || "?",
        timezone: (request.cf && request.cf.timezone) || "?",
      }, request, env);
    }

    if (url.pathname !== "/analyze") {
      return jsonResponse({ error: "Not found" }, request, env, 404);
    }

    if (request.method !== "POST") {
      return jsonResponse({ error: "Method not allowed" }, request, env, 405);
    }

    let body;
    try {
      body = await request.json();
    } catch (e) {
      return jsonResponse({ error: "Invalid JSON" }, request, env, 400);
    }

    const backend = (body.backend || "openai").toLowerCase();
    if (!["claude", "openai"].includes(backend)) {
      return jsonResponse({ error: "Invalid backend (claude|openai)" }, request, env, 400);
    }

    const prompt = (body.prompt || "").trim();
    if (!prompt) {
      return jsonResponse({ error: "Empty prompt" }, request, env, 400);
    }
    if (prompt.length > 50000) {
      return jsonResponse({ error: "Prompt too long (max 50000 chars)" }, request, env, 400);
    }

    const system = body.system || "당신은 전략·기획·AI 업무 분석을 돕는 한국어 AI 어시스턴트입니다.";
    const maxTokens = Math.min(parseInt(body.max_tokens || 1500, 10), 4000);

    // 모델 선택 — 화이트리스트 검증
    let model = body.model || DEFAULT_MODELS[backend];
    if (!ALLOWED_MODELS[backend].includes(model)) {
      model = DEFAULT_MODELS[backend];
    }

    // 사용자 본인 키 우선
    const userApiKey = request.headers.get("X-User-Api-Key");
    const userBackend = (request.headers.get("X-User-Backend") || "").toLowerCase();

    let apiKey, useUserKey = false;
    if (userApiKey && (userBackend === backend || !userBackend)) {
      apiKey = userApiKey;
      useUserKey = true;
    } else {
      // 서버 키 사용 + Rate limit
      apiKey = backend === "claude" ? env.ANTHROPIC_API_KEY : env.OPENAI_API_KEY;
      if (!apiKey) {
        return jsonResponse({ error: `${backend} API key not configured` }, request, env, 500);
      }
      // Rate limit (IP당 일 5회)
      if (env.RATE_LIMIT) {
        const ip = request.headers.get("CF-Connecting-IP") || "unknown";
        const today = new Date().toISOString().slice(0, 10);
        const key = `${ip}:${today}`;
        const count = parseInt((await env.RATE_LIMIT.get(key)) || "0", 10);
        if (count >= DAILY_FREE_LIMIT) {
          return jsonResponse({
            error: `오늘 무료 분석 한도(${DAILY_FREE_LIMIT}회)에 도달했습니다. 본인 API 키를 입력하시면 무제한 사용 가능합니다.`,
            limit_reached: true,
            free_limit: DAILY_FREE_LIMIT,
          }, request, env, 429);
        }
        ctx.waitUntil(env.RATE_LIMIT.put(key, String(count + 1), { expirationTtl: 86400 }));
      }
    }

    try {
      let result;
      if (backend === "claude") {
        result = await callClaude(apiKey, prompt, system, maxTokens, model);
      } else {
        result = await callOpenAI(apiKey, prompt, system, maxTokens, model);
      }
      return jsonResponse({
        result: result.text,
        backend,
        model: result.model,
        usage: result.usage,
        used_user_key: useUserKey,
      }, request, env);
    } catch (e) {
      // v2.7.1: 진단용 콜로(colo) 정보를 에러 응답에 첨부 → 지역 차단 진단 용이
      const colo = (request.cf && request.cf.colo) || "?";
      const country = (request.cf && request.cf.country) || "?";
      const rawMsg = e.message || String(e);
      let errorMsg = rawMsg;
      // Anthropic 지역 차단(403 forbidden) → 사용자에게 친절한 안내
      if (/403/.test(rawMsg) && /forbidden|not allowed/i.test(rawMsg)) {
        errorMsg = `${rawMsg}\n\n[진단] Worker colo=${colo}, country=${country}.\n해당 데이터센터에서 ${backend} API가 차단되었습니다. wrangler.toml의 Smart Placement를 비활성화 후 재배포(wrangler deploy)하면 사용자 edge(ICN)에서 실행되어 해결됩니다.`;
      }
      return jsonResponse({
        error: errorMsg,
        debug: { colo, country, backend, model },
      }, request, env, 502);
    }
  },
};

async function callClaude(apiKey, prompt, system, maxTokens, model) {
  model = model || DEFAULT_MODELS.claude;
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model,
      max_tokens: maxTokens,
      system,
      messages: [{ role: "user", content: prompt }],
    }),
  });
  if (!r.ok) {
    const errBody = await r.text();
    throw new Error(`Claude API ${r.status}: ${errBody.slice(0, 300)}`);
  }
  const data = await r.json();
  const text = (data.content && data.content[0] && data.content[0].text) || "";
  return { text, model, usage: data.usage };
}

async function callOpenAI(apiKey, prompt, system, maxTokens, model) {
  model = model || DEFAULT_MODELS.openai;
  const r = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model,
      max_tokens: maxTokens,
      messages: [
        { role: "system", content: system },
        { role: "user", content: prompt },
      ],
    }),
  });
  if (!r.ok) {
    const errBody = await r.text();
    throw new Error(`OpenAI API ${r.status}: ${errBody.slice(0, 300)}`);
  }
  const data = await r.json();
  const text = (data.choices && data.choices[0] && data.choices[0].message && data.choices[0].message.content) || "";
  return { text, model, usage: data.usage };
}

function corsHeaders(request, env) {
  // 기본은 daibfy.com만 허용, 환경변수 ALLOWED_ORIGINS로 확장 가능
  const origin = request.headers.get("Origin") || "";
  const allowed = (env.ALLOWED_ORIGINS || "https://daibfy.com,https://sorakimsr.github.io,http://localhost:8000")
    .split(",")
    .map(s => s.trim());
  const allowOrigin = allowed.includes(origin) ? origin : allowed[0];
  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-User-Api-Key, X-User-Backend",
    "Access-Control-Max-Age": "86400",
  };
}

function jsonResponse(obj, request, env, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...corsHeaders(request, env),
    },
  });
}
