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

    // v2.7.2: 사용자 체감 속도 개선을 위해 시스템 프롬프트에 "분석 계획 먼저" 지시 추가
    const defaultSystem = "당신은 한국 전략·기획·AI 업무 담당자를 돕는 한국어 AI 어시스턴트입니다.\n\n응답 규칙(반드시 지킬 것):\n1. **항상 두 섹션으로 응답**: 먼저 `## 🧭 분석 계획` (2~3줄, 어떤 관점으로 어떤 흐름을 살필지) → 그 다음 `## 📊 분석 결과` (실제 분석).\n2. 핵심 키워드·회사명·금액·기법명은 `**굵게**` 마크다운으로 강조 (한 문장당 1~2개).\n3. 단정 어조 지양, 구체 근거(회사명·날짜·금액) 우선.";
    const system = body.system || defaultSystem;
    const maxTokens = Math.min(parseInt(body.max_tokens || 1500, 10), 4000);
    const wantStream = body.stream === true;

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
      // v2.7.2: 스트리밍 모드 — 첫 글자가 1~2초 안에 도착하도록 token-by-token SSE 전송
      if (wantStream) {
        if (backend === "claude") {
          return await streamClaude(apiKey, prompt, system, maxTokens, model, request, env, useUserKey);
        } else {
          return await streamOpenAI(apiKey, prompt, system, maxTokens, model, request, env, useUserKey);
        }
      }
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

// ============================================================================
// v2.7.2: 스트리밍 — Anthropic/OpenAI 응답을 token 단위로 클라이언트에 전달
// 정규화 SSE 포맷:
//   data: {"type":"delta","text":"..."}
//   data: {"type":"done","model":"...","usage":{...}}
//   data: {"type":"error","error":"..."}
// ============================================================================

async function streamClaude(apiKey, prompt, system, maxTokens, model, request, env, useUserKey) {
  model = model || DEFAULT_MODELS.claude;
  const upstream = await fetch("https://api.anthropic.com/v1/messages", {
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
      stream: true,
      messages: [{ role: "user", content: prompt }],
    }),
  });
  if (!upstream.ok) {
    const errBody = await upstream.text();
    throw new Error(`Claude API ${upstream.status}: ${errBody.slice(0, 300)}`);
  }
  return makeNormalizedStream(upstream, "claude", model, request, env, useUserKey);
}

async function streamOpenAI(apiKey, prompt, system, maxTokens, model, request, env, useUserKey) {
  model = model || DEFAULT_MODELS.openai;
  const upstream = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model,
      max_tokens: maxTokens,
      stream: true,
      stream_options: { include_usage: true },
      messages: [
        { role: "system", content: system },
        { role: "user", content: prompt },
      ],
    }),
  });
  if (!upstream.ok) {
    const errBody = await upstream.text();
    throw new Error(`OpenAI API ${upstream.status}: ${errBody.slice(0, 300)}`);
  }
  return makeNormalizedStream(upstream, "openai", model, request, env, useUserKey);
}

function makeNormalizedStream(upstream, backend, model, request, env, useUserKey) {
  const reader = upstream.body.getReader();
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  let usage = null;

  const stream = new ReadableStream({
    async start(controller) {
      const send = (obj) => controller.enqueue(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`));

      // 메타 (used_user_key 등) 즉시 송신
      send({ type: "meta", backend, model, used_user_key: !!useUserKey });

      let buffer = "";
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // SSE는 \n\n 으로 이벤트 구분
          const events = buffer.split("\n\n");
          buffer = events.pop() || "";

          for (const evt of events) {
            // 각 줄에서 "data: ..." 부분만 추출
            const lines = evt.split("\n").filter(l => l.startsWith("data:"));
            for (const line of lines) {
              const payload = line.slice(5).trim();
              if (!payload || payload === "[DONE]") continue;
              try {
                const parsed = JSON.parse(payload);
                if (backend === "claude") {
                  if (parsed.type === "content_block_delta" && parsed.delta && parsed.delta.text) {
                    send({ type: "delta", text: parsed.delta.text });
                  } else if (parsed.type === "message_delta" && parsed.usage) {
                    usage = parsed.usage;
                  } else if (parsed.type === "message_start" && parsed.message && parsed.message.usage) {
                    usage = { ...usage, ...parsed.message.usage };
                  }
                } else {
                  // OpenAI
                  const choice = (parsed.choices && parsed.choices[0]) || null;
                  if (choice && choice.delta && choice.delta.content) {
                    send({ type: "delta", text: choice.delta.content });
                  }
                  if (parsed.usage) {
                    usage = parsed.usage;
                  }
                }
              } catch (e) {
                // 파싱 실패는 무시 (불완전 chunk)
              }
            }
          }
        }
        send({ type: "done", model, usage: usage || {}, backend });
      } catch (e) {
        send({ type: "error", error: e.message || String(e) });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
      ...corsHeaders(request, env),
    },
  });
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
