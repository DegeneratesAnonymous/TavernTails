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

import logging
import os
import re
import time
from threading import BoundedSemaphore, Lock

import httpx

logger = logging.getLogger(__name__)

_CLIENTS: dict[str, httpx.Client] = {}
_CLIENT_LOCK = Lock()
_INFERENCE_GATES: dict[int, BoundedSemaphore] = {}


def chat_complete(
    messages: list[dict], *, max_tokens: int | None = None,
    temperature: float | None = None, task_scope: str | None = None,
    timeout: float = 60.0,
) -> str | None:
    """Queue local inference before starting its provider timeout.

    One local GPU defaults to one in-flight completion per server process.
    Set TAVERNTAILS_LLM_MAX_CONCURRENCY for multi-node Steward installations;
    zero disables the gate. No prompt, endpoint or credential is logged.
    """
    local = bool(os.environ.get("STEWARD_HOST") or os.environ.get("OLLAMA_HOST"))
    limit = int(os.environ.get("TAVERNTAILS_LLM_MAX_CONCURRENCY", "1" if local else "0"))
    if limit <= 0:
        return _chat_complete(messages, max_tokens=max_tokens, temperature=temperature, task_scope=task_scope, timeout=timeout)
    with _CLIENT_LOCK:
        gate = _INFERENCE_GATES.setdefault(limit, BoundedSemaphore(limit))
    started = time.perf_counter()
    acquired = gate.acquire(timeout=float(os.environ.get("TAVERNTAILS_LLM_QUEUE_TIMEOUT", "300")))
    queued_ms = round((time.perf_counter() - started) * 1000)
    logger.info("llm_queue task_scope=%s queue_ms=%s acquired=%s concurrency=%s",
                task_scope or "default", queued_ms, acquired, limit)
    if not acquired:
        return None
    try:
        return _chat_complete(messages, max_tokens=max_tokens, temperature=temperature, task_scope=task_scope, timeout=timeout)
    finally:
        gate.release()


def _client_for(base_url: str) -> httpx.Client:
    """Return a pooled HTTP client for a provider base URL.

    Agent calls are frequent and short-lived; reusing clients keeps TCP
    connections warm and avoids rebuilding connection pools for every request.
    """
    with _CLIENT_LOCK:
        client = _CLIENTS.get(base_url)
        if client is None:
            client = httpx.Client(timeout=None)
            _CLIENTS[base_url] = client
        return client


def _scope_key(task_scope: str | None) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", (task_scope or "default").upper()).strip("_") or "DEFAULT"


def _env_for_scope(prefix: str, task_scope: str | None, fallback: str) -> str:
    """Resolve per-task settings before falling back to the global default.

    Example: OLLAMA_MODEL_TAVERNTAILS_ANALYSIS=qwen3:1.7b lets scene analysis
    use a faster model while narrative generation can keep a stronger default.
    """
    scoped = os.environ.get(f"{prefix}_{_scope_key(task_scope)}")
    return scoped or os.environ.get(prefix, fallback)


def _log_attempt(
    *,
    provider: str,
    task_scope: str | None,
    elapsed: float,
    ok: bool,
    detail: str = "",
) -> None:
    message = (
        f"llm_attempt provider={provider} task_scope={task_scope or 'default'} ok={ok} "
        f"elapsed_ms={int(elapsed * 1000)}{f' detail={detail}' if detail else ''}"
    )
    if ok:
        if elapsed >= float(os.environ.get("TAVERNTAILS_LLM_SLOW_LOG_SECONDS", "2.0")):
            logger.info(message)
        else:
            logger.debug(message)
    else:
        logger.warning(message)


def _steward_payload(messages, scope, max_tokens, temperature, timeout) -> dict:
    """Everything TavernTails configured is forwarded unchanged; Steward adds nothing."""
    payload = {
        "messages": messages,
        "task_scope": scope,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "timeout": int(min(timeout, 90)),
    }
    model = os.environ.get(f"OLLAMA_MODEL_{_scope_key(scope)}")  # per-scope override only
    if model:
        payload["model"] = model
    return payload


def _chat_complete(
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
        started = time.perf_counter()
        try:
            client = _client_for(steward_host)
            r = client.post(
                f"{steward_host}/api/games/taverntails/ai",
                json=_steward_payload(messages, scope, max_tokens, temperature, timeout),
                timeout=steward_attempt_timeout,
            )
            r.raise_for_status()
            data = r.json()
            choices = data.get("choices") or []
            if choices:
                _log_attempt(
                    provider="steward",
                    task_scope=scope,
                    elapsed=time.perf_counter() - started,
                    ok=True,
                    detail=_steward_queue_detail(data),
                )
                return (choices[0].get("message") or {}).get("content") or None
            _log_attempt(
                provider="steward",
                task_scope=scope,
                elapsed=time.perf_counter() - started,
                ok=False,
                detail="empty_choices",
            )
        except Exception as exc:
            _log_attempt(
                provider="steward",
                task_scope=scope,
                elapsed=time.perf_counter() - started,
                ok=False,
                detail=type(exc).__name__,
            )
        # Steward failed — fall through to direct Ollama as backup.

    # ── 2. Direct Ollama ────────────────────────────────────────────────────
    # Used both as a standalone provider (no STEWARD_HOST) and as the fallback
    # when Steward's model isn't available on the current nodes.
    # Cap at 40s so total (Steward attempt + Ollama) stays under the 150s proxy limit.
    ollama_host = os.environ.get("OLLAMA_HOST", "").rstrip("/")
    if ollama_host:
        model = _env_for_scope("OLLAMA_MODEL", task_scope, "qwen3:4b")
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
            task_scope=task_scope,
            provider="ollama",
        )
        if result is not None:
            return result

    # ── 3. OpenAI-compatible fallback ──────────────────────────────────────
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if api_key and api_key != "ollama":
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o")
        model = _env_for_scope("OPENAI_MODEL", task_scope, model)
        return _call_openai_compat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            task_scope=task_scope,
            provider="openai_compat",
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
    task_scope: str | None = None,
    provider: str = "openai_compat",
) -> str | None:
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    started = time.perf_counter()
    try:
        client = _client_for(base_url)
        r = client.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        choices = data.get("choices") or []
        if choices:
            _log_attempt(
                provider=provider,
                task_scope=task_scope,
                elapsed=time.perf_counter() - started,
                ok=True,
                detail=f"model={model}",
            )
            return (choices[0].get("message") or {}).get("content") or None
        _log_attempt(
            provider=provider,
            task_scope=task_scope,
            elapsed=time.perf_counter() - started,
            ok=False,
            detail="empty_choices",
        )
    except Exception as exc:
        _log_attempt(
            provider=provider,
            task_scope=task_scope,
            elapsed=time.perf_counter() - started,
            ok=False,
            detail=type(exc).__name__,
        )
        return None
    return None


def _steward_queue_detail(data: dict) -> str:
    for key in ("queue_position", "queued", "worker", "model"):
        if key in data:
            return f"{key}={data[key]}"
    meta = data.get("metadata") or data.get("meta") or {}
    if isinstance(meta, dict):
        parts = [f"{key}={meta[key]}" for key in ("queue_position", "queued", "worker", "model") if key in meta]
        if parts:
            return ",".join(parts)
    return ""
