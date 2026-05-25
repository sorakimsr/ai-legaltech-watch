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
    stdin을 명시적으로 닫아서 stdin 대기 경고 방지."""
    try:
        r = subprocess.run(
            ["claude", "--print", "--output-format", "text", prompt],
            capture_output=True, text=True, timeout=120,
            stdin=subprocess.DEVNULL,
        )
        if r.returncode != 0:
            print(f"  [claude-cli] error: {r.stderr[:200]}", file=sys.stderr)
            return ""
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        print("  [claude-cli] timeout", file=sys.stderr)
        return ""
    except Exception as exc:
        print(f"  [claude-cli] exception: {exc}", file=sys.stderr)
        return ""


def call_anthropic_sdk(prompt: str, max_tokens: int = 800, temperature: float = 0.3) -> str:
    """Anthropic SDK 직접 호출"""
    try:
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        # content 는 블록 리스트
        if msg.content and len(msg.content) > 0:
            return msg.content[0].text.strip()
        return ""
    except Exception as exc:
        print(f"  [anthropic] exception: {exc}", file=sys.stderr)
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
    """가용한 백엔드 자동 감지. 한 번 정해지면 캐시."""
    global _BACKEND_CACHE
    if _BACKEND_CACHE:
        return _BACKEND_CACHE

    # 환경 변수로 강제 지정 가능
    forced = os.environ.get("LLM_BACKEND", "").lower()
    if forced in ("claude-cli", "anthropic", "openai"):
        _BACKEND_CACHE = forced
        return forced

    if has_claude_cli():
        _BACKEND_CACHE = "claude-cli"
    elif has_anthropic_sdk():
        _BACKEND_CACHE = "anthropic"
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

    print(f"  [llm-json] parse failed. raw[:300]: {response[:300]}", file=sys.stderr)
    return {}
