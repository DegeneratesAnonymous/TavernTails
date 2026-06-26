"""
Thin LLM client for TavernTails.

Resolution order:
  1. STEWARD_HOST — call Steward's AI proxy at /api/games/taverntails/ai.
     Steward routes the request through its full LLM stack (model selection,
     node routing to heatherpc / colemanpc, fallback chain).
  2. OLLAMA_HOST — call an Ollama node directly at <host>/v1/chat/completions.
  3. OPENAI_API_KEY — call any OpenAI-compatible endpoint.

Environment variables:
  STEWARD_HOST        Base URL of the Steward dashboard (e.g. http://127.0.0.1:5555).
                      When set, all AI calls go through Steward's routing.
  STEWARD_TASK_SCOPE  task_scope passed to Steward's router (default: short_summary).
                      Use "creative_story" for higher-quality narrative when ColemanPC
                      is available; "short_summary" for fast, reliable heatherpc routing.
  OLLAMA_HOST         Base URL of an Ollama node (e.g. http://localhost:11434).
  OLLAMA_MODEL        Model to use when calling Ollama directly (default: qwen3:4b).
  OPENAI_API_KEY      Fallback OpenAI-compatible key.
  OPENAI_BASE_URL     Endpoint for OpenAI-compat calls (default: https://api.openai.com/v1).
  OPENAI_MODEL        Model name (default: gpt-4o).
  OPENAI_MAX_TOKENS   (default: 500)
  OPENAI_TEMPERATURE  (default: 0.7)
"""

from __future__ import annotations

import os

import httpx


def chat_complete(
    messages: list[dict],
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
    task_scope: str | None = None,
    timeout: float = 60.0,
) -> str | None:
    """
    Send a chat completion request and return the assistant message content,
    or None if the LLM is not configured or the call fails.
    """
    max_tokens = max_tokens or int(os.environ.get("OPENAI_MAX_TOKENS", "500"))
    temperature = temperature if temperature is not None else float(os.environ.get("OPENAI_TEMPERATURE", "0.7"))

    # ── 1. Steward AI proxy (preferred when configured) ────────────────────
    # When STEWARD_HOST is set, try Steward's model router first.
    # If Steward returns an error (500, timeout) we fall through to direct
    # Ollama so TavernTails can still generate content when Steward's
    # configured creative model isn't installed on the available nodes.
    steward_host = os.environ.get("STEWARD_HOST", "").rstrip("/")
    if steward_host:
        scope = task_scope or os.environ.get("STEWARD_TASK_SCOPE", "creative_story")
        # Cap Steward at 110s — routes to PC's qwen3:14b (warm ~40s, cold ~100s).
        # 110s covers cold-start (model load ~48s + generation ~50s = ~100s).
        # Falls through to direct PC Ollama only if Steward itself is unreachable.
        steward_attempt_timeout = min(float(timeout), 110.0)
        try:
            with httpx.Client(timeout=steward_attempt_timeout) as client:
                r = client.post(
                    f"{steward_host}/api/games/taverntails/ai",
                    json={"messages": messages, "task_scope": scope, "max_tokens": max_tokens, "timeout": int(min(timeout, 90))},
                )
                r.raise_for_status()
                data = r.json()
                choices = data.get("choices") or []
                if choices:
                    return (choices[0].get("message") or {}).get("content") or None
        except Exception:
            pass
        # Steward failed — fall through to direct Ollama as backup.

    # ── 2. Direct Ollama ────────────────────────────────────────────────────
    # Used both as a standalone provider (no STEWARD_HOST) and as the fallback
    # when Steward's model isn't available on the current nodes.
    # Cap at 40s so total (Steward attempt + Ollama) stays under the 150s proxy limit.
    ollama_host = os.environ.get("OLLAMA_HOST", "").rstrip("/")
    if ollama_host:
        model = os.environ.get("OLLAMA_MODEL", "qwen3:4b")
        # With Steward capped at 30s, allow up to 60s for direct Ollama (model may need loading).
        ollama_timeout = min(float(timeout), 60.0) if steward_host else float(timeout)
        result = _call_openai_compat(
            base_url=f"{ollama_host}/v1",
            api_key="ollama",
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=ollama_timeout,
        )
        if result is not None:
            return result

    # ── 3. OpenAI-compatible fallback ──────────────────────────────────────
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key and api_key != "ollama":
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o")
        return _call_openai_compat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )

    return None


def _call_openai_compat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    timeout: float,
) -> str | None:
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices") or []
            if choices:
                return (choices[0].get("message") or {}).get("content") or None
    except Exception:
        return None
    return None
