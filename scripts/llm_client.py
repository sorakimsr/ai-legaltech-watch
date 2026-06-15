"""
LLM 클라이언트 — 다중 백엔드 지원

우선순위:
1. Claude Code CLI (`claude --print`)  — GitHub Actions에서 가장 안정적
2. anthropic Python SDK                 — ANTHROPIC_API_KEY 있을 때
3. openai Python SDK                    — OPENAI_API_KEY 있을 때 (폴백)

사용:
    from llm_client import call_llm
    response = call_llm(prompt, max_tokens=800, temperature=0.3)
"""

import json
import os
import subprocess
import sys


# ---- 백엔드 가용성 체크 ----

def has_claude_cli():
    try:
        r = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=5
        )
        return r.returncode == 0
    except Exception:
        return False


def has_anthropic_sdk():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa
        return True
    except ImportError:
        return False


def has_openai_sdk():
    if not os.environ.get("OPENAI_API_KEY"):
        return False
    try:
        import openai  # noqa
        return True
    except ImportError:
        return False


# ---- 백엔드 호출 ----

def call_claude_cli(prompt: str, max_tokens: int = 800) -> str:
    """Claude Code CLI 호출. --print 모드로 일회성 응답.
    v2.7: timeout 120 → 300, 모델 명시 (Sonnet 4.6).
    """
    # 환경변수로 override 가능, 기본 sonnet 4.6
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    try:
        r = subprocess.run(
            ["claude", "--print", "--model", model, "--output-format", "text", prompt],
            capture_output=True, text=True, timeout=300,
            stdin=subprocess.DEVNULL,
        )
        if r.returncode != 0:
            print(f"  [claude-cli] error: {r.stderr[:200]}", file=sys.stderr)
            return ""
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        print("  [claude-cli] timeout (300s)", file=sys.stderr)
        return ""
    except Exception as exc:
        print(f"  [claude-cli] exception: {exc}", file=sys.stderr)
        return ""


def call_anthropic_sdk(prompt: str, max_tokens: int = 800, temperature: float = 0.3) -> str:
    """Anthropic SDK 직접 호출 (스트리밍 + 재시도·백오프).

    v6.15.49 (2026-06-02): 비스트리밍 messages.create()는 max_tokens가 커서
    요청이 10분을 넘길 수 있으면 "Streaming is required for operations that may take
    longer than 10 minutes" 예외를 던진다(#90 daily 전략 실패의 진짜 원인 — v6.15.47에서
    max_tokens 12000→24000으로 올리며 이 임계선을 넘김). 스트리밍으로 토큰을 누적 수신하면
    10분 제한이 사라져 큰 max_tokens도 안전하고, 응답 잘림도 발생하지 않는다.

    v6.15.57 (2026-06-15): 재시도·백오프 추가 — 구조적 결함 해소.
      배경: 스트리밍이 일시적 장애(overloaded 529·rate-limit 429·timeout·네트워크 블립)로
      중간에 끊기면 빈 문자열을 반환했고, 호출자(generate_cards)는 재시도 없이 곧장
      '임시 카드' fallback으로 빠졌다. 첫 빌드엔 self-heal도 없어 단 1회의 일시 실패가
      그날 daily 시사점 전체를 임시카드로 고착시켰다(v6.15.47/.49/.50에 이은 같은 영역 반복).
      → LLM 호출 계층에서 최대 3회 재시도(5s·20s 지수 백오프)하여 일시 장애가
      비상 경로로 cascade되지 않도록 한다. 빈 응답도 재시도 대상. 에러 유형을 구분 로깅.
    """
    import time
    try:
        import anthropic
        client = anthropic.Anthropic()
    except Exception as exc:
        # 비-일시적 설정 오류(모듈 없음·키 없음) → 재시도 무의미, 즉시 실패
        print(f"  [anthropic] setup error (재시도 안 함): {type(exc).__name__}: {str(exc)[:120]}",
              file=sys.stderr)
        return ""
    last_err = None
    for attempt in range(1, 4):  # 최대 3회 (일시적 장애만)
        try:
            parts = []
            with client.messages.stream(
                model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                for text in stream.text_stream:
                    parts.append(text)
            out = "".join(parts).strip()
            if out:
                if attempt > 1:
                    print(f"  [anthropic] 재시도 {attempt}회차에 성공", file=sys.stderr)
                return out
            last_err = "empty response (스트림은 정상 종료했으나 본문 0자)"
            print(f"  [anthropic] 빈 응답 (attempt {attempt}/3)", file=sys.stderr)
        except Exception as exc:
            last_err = exc
            print(f"  [anthropic] {type(exc).__name__}: {str(exc)[:160]} (attempt {attempt}/3)",
                  file=sys.stderr)
        if attempt < 3:
            time.sleep(5 * (attempt ** 2))  # 5s, 20s 지수 백오프
    print(f"  [anthropic] 3회 모두 실패 → 빈 결과 반환 (마지막 원인: {str(last_err)[:120]})",
          file=sys.stderr)
    return ""


def call_openai_sdk(prompt: str, max_tokens: int = 800, temperature: float = 0.3) -> str:
    """OpenAI SDK 호출 (폴백)"""
    try:
        from openai import OpenAI
        client = OpenAI()
        r = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return (r.choices[0].message.content or "").strip()
    except Exception as exc:
        print(f"  [openai] exception: {exc}", file=sys.stderr)
        return ""


# ---- 메인 인터페이스 ----

_BACKEND_CACHE = None


def detect_backend() -> str:
    """가용한 백엔드 자동 감지. 한 번 정해지면 캐시.

    v2.7: 우선순위 변경 — Anthropic SDK 우선 (CLI는 stdin/timeout 제어 어려움, SDK가 더 안정적).
    """
    global _BACKEND_CACHE
    if _BACKEND_CACHE:
        return _BACKEND_CACHE

    # 환경 변수로 강제 지정 가능
    forced = os.environ.get("LLM_BACKEND", "").lower()
    if forced in ("claude-cli", "anthropic", "openai"):
        _BACKEND_CACHE = forced
        print(f"  [llm] backend: {_BACKEND_CACHE} (forced)", flush=True)
        return forced

    # SDK 우선 (ANTHROPIC_API_KEY 있으면) → CLI fallback → OpenAI fallback
    if has_anthropic_sdk():
        _BACKEND_CACHE = "anthropic"
    elif has_claude_cli():
        _BACKEND_CACHE = "claude-cli"
    elif has_openai_sdk():
        _BACKEND_CACHE = "openai"
    else:
        _BACKEND_CACHE = "none"

    print(f"  [llm] backend: {_BACKEND_CACHE}", flush=True)
    return _BACKEND_CACHE


def call_llm(prompt: str, max_tokens: int = 800, temperature: float = 0.3) -> str:
    """단일 LLM 호출 — 가용한 백엔드를 알아서 선택"""
    backend = detect_backend()
    if backend == "claude-cli":
        result = call_claude_cli(prompt, max_tokens)
        # CLI 실패 시 SDK 폴백
        if not result and has_anthropic_sdk():
            result = call_anthropic_sdk(prompt, max_tokens, temperature)
        if not result and has_openai_sdk():
            result = call_openai_sdk(prompt, max_tokens, temperature)
        return result
    elif backend == "anthropic":
        result = call_anthropic_sdk(prompt, max_tokens, temperature)
        if not result and has_openai_sdk():
            result = call_openai_sdk(prompt, max_tokens, temperature)
        return result
    elif backend == "openai":
        return call_openai_sdk(prompt, max_tokens, temperature)
    else:
        return ""


def _salvage_truncated(text: str):
    """잘린(truncated) JSON 회복 — bracket-stack 기반 일반 복구.

    v6.15.47 (2026-06-02): daily 전략 응답이 토큰 한도에서 잘려 파싱 실패 →
    카드 0건 → 임시 카드 fallback이 반복된 문제의 구조적 방어.

    동작:
      1) 첫 '{' 또는 '[' 이전의 잡음(예: 닫히지 않은 ```json 펜스)을 버린다.
      2) 문자열·이스케이프 상태를 추적하며 열린 컨테이너 스택을 유지.
      3) depth>=1에서 (a) 하위 element가 완전히 닫힌 직후(`}`/`]`), 또는
         (b) element 구분 콤마 위치를 'safe cut point'로 기록.
      4) 마지막 safe point까지 자르고 열린 컨테이너를 역순으로 닫아 파싱.

    효과: cards-first 응답이 summary 도중 또는 카드 배열 중간에 잘려도
    이미 완성된 카드들을 회복(0건+임시카드 대신 'N건' graceful degrade).
    회복 실패 시 None.
    """
    if not text:
        return None
    starts = [p for p in (text.find("{"), text.find("[")) if p != -1]
    if not starts:
        return None
    text = text[min(starts):]

    stack = []          # 열린 컨테이너: '{' 또는 '['
    in_string = False
    escape = False
    safe_len = -1       # 이 길이까지 보존하면 닫아서 유효
    safe_stack = None   # 그 시점의 열린 컨테이너 스냅샷

    for i, c in enumerate(text):
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if in_string:
            if c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
            continue
        if c in "{[":
            stack.append(c)
        elif c in "}]":
            if stack:
                stack.pop()
            if stack:  # 아직 상위 컨테이너 안 — element 하나 완성된 직후
                safe_len = i + 1
                safe_stack = list(stack)
        elif c == "," and stack:
            # element 구분 콤마 — 콤마 직전까지 보존하면 유효
            safe_len = i
            safe_stack = list(stack)

    if safe_len <= 0 or not safe_stack:
        return None
    prefix = text[:safe_len].rstrip().rstrip(",")
    closers = "".join("]" if b == "[" else "}" for b in reversed(safe_stack))
    try:
        return json.loads(prefix + closers)
    except json.JSONDecodeError:
        return None


def call_llm_json(prompt: str, max_tokens: int = 800, temperature: float = 0.2):
    """LLM 응답을 JSON(dict or list)으로 파싱.

    버그 fix: 기존 regex `(\\{.*?\\}|\\[.*?\\])` 가 배열 응답에서 첫 번째 object만
    캡처해 dict 반환 → 호출자의 isinstance(result, list) 체크 실패 → 빈 결과.
    """
    response = call_llm(prompt, max_tokens, temperature)
    if not response:
        return {}

    import re

    # 1) ```json ... ``` 또는 ``` ... ``` 코드블록 안의 모든 내용 추출
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", response, re.DOTALL)
    candidate = m.group(1).strip() if m else response.strip()

    # 2) 1차 시도 — 코드블록/원본 그대로 파싱
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # 3) 2차 시도 — 가장 바깥쪽 배열([) 또는 객체({) 추출
    #    배열이 먼저 등장하면 배열을, 아니면 객체를 시도
    first_arr = candidate.find("[")
    first_obj = candidate.find("{")

    spans = []
    if first_arr != -1 and (first_obj == -1 or first_arr <= first_obj):
        last_arr = candidate.rfind("]")
        if last_arr > first_arr:
            spans.append(candidate[first_arr:last_arr + 1])
    if first_obj != -1:
        last_obj = candidate.rfind("}")
        if last_obj > first_obj:
            spans.append(candidate[first_obj:last_obj + 1])

    for span in spans:
        try:
            return json.loads(span)
        except json.JSONDecodeError:
            continue

    # 4) max_tokens 한도로 잘린 JSON array 복구 시도
    #    (`[ {...}, {...}, {... 까지만 와서 닫힘 `]` 가 없는 경우)
    if first_arr != -1:
        depth = 0
        in_string = False
        escape = False
        last_complete_obj_end = -1
        for i in range(first_arr, len(candidate)):
            c = candidate[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                # array 안에서 object 하나가 완전히 닫힘
                if depth == 0:
                    last_complete_obj_end = i
        if last_complete_obj_end > first_arr:
            # `[ ... <마지막 완전한 object>` 까지만 잘라서 `]` 닫음
            salvaged = candidate[first_arr:last_complete_obj_end + 1].rstrip().rstrip(",") + "]"
            try:
                result = json.loads(salvaged)
                print(f"  [llm-json] truncated array salvaged ({len(result)} items)", file=sys.stderr)
                return result
            except json.JSONDecodeError:
                pass

    # 5) v6.15.25 (2026-05-28): max_tokens 한도로 잘린 JSON object 복구
    #    enrich 응답은 대부분 object {"summary_ko": ..., "entities": [...]} 형태.
    #    entities/relations 리스트 중간에 잘리면 마지막 `}` 없어 파싱 실패.
    #    → top-level에서 마지막 완전한 key-value pair까지 잘라 `}`로 닫음.
    #    효과: summary_ko·insight_ko 등 이미 받은 필드는 살림 (entities 일부 잘려도 OK).
    if first_obj != -1:
        depth = 0
        in_string = False
        escape = False
        last_top_level_comma = -1
        last_value_end = -1  # 마지막으로 top-level value가 완전히 끝난 위치
        for i in range(first_obj, len(candidate)):
            c = candidate[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                # top-level에서 문자열이 닫혔으면 value 끝일 수도 (보수적)
                if not in_string and depth == 1:
                    last_value_end = i
                continue
            if in_string:
                continue
            if c == "{" or c == "[":
                depth += 1
            elif c == "}" or c == "]":
                depth -= 1
                if depth == 1:
                    last_value_end = i  # top-level value (array/object) 완료
            elif c == "," and depth == 1:
                last_top_level_comma = i

        # last_top_level_comma까지 잘라서 닫기 시도
        # (마지막 완전한 필드까지 살리고 그 뒤 잘린 부분 버림)
        if last_top_level_comma > first_obj:
            salvaged = candidate[first_obj:last_top_level_comma] + "\n}"
            try:
                result = json.loads(salvaged)
                fields = list(result.keys()) if isinstance(result, dict) else []
                print(f"  [llm-json] truncated object salvaged (fields: {fields})", file=sys.stderr)
                return result
            except json.JSONDecodeError:
                pass

    # 6) v6.15.47: 일반 bracket-stack 기반 truncation 회복 (마지막 방어선)
    #    cards-first 응답이 summary 도중/카드 배열 중간에 잘린 경우 완성 카드 회복.
    salvaged = _salvage_truncated(candidate)
    if salvaged is not None:
        if isinstance(salvaged, dict) and isinstance(salvaged.get("cards"), list):
            n = len(salvaged["cards"])
        elif isinstance(salvaged, list):
            n = len(salvaged)
        else:
            n = len(salvaged) if hasattr(salvaged, "__len__") else 1
        print(f"  [llm-json] bracket-repair salvaged ({n} items)", file=sys.stderr)
        return salvaged

    print(f"  [llm-json] parse failed. raw[:300]: {response[:300]}", file=sys.stderr)
    return {}
