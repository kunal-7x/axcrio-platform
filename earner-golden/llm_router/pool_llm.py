"""llm_router/pool_llm.py — a LiveKit `llm.LLM` that rotates keys via a ProviderPool.

WHY this exists: `groq.LLM` (and `openai.LLM`) bind ONE api_key for the instance lifetime and retry
the SAME key on a 429 — they never re-pick. So a static single Groq member inside a FallbackAdapter
can't rotate; key#1 hits its daily wall while keys #4-9 idle. PoolLLM fixes that:

  - holds ONE underlying delegate LLM (built once),
  - on EVERY chat() it `pool.pick()`s the LEAST-USED, not-cooling key and swaps it onto the
    delegate's AsyncOpenAI client (`_client.api_key`),
  - wraps the resulting stream: if it raises a 429, it `mark_429`s that key (TTL from Retry-After)
    and INSTANTLY re-picks the next available key (NO linear walk of dead keys) — up to the number
    of available keys — then, if the whole pool is cooling, raises so the FallbackAdapter advances
    to the next PROVIDER (Groq -> SambaNova -> OpenRouter).

Import-guarded by the caller: if this module or its deps are absent, aim_voice_agent.py degrades to
the legacy single-key members. It NEVER touches agent.py / trunks / firewall / SIP.
"""
from __future__ import annotations

import logging
from typing import Optional

from livekit.agents import llm as _lk_llm
from livekit.agents.types import APIConnectOptions, DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, NotGivenOr

from .provider_pool import ProviderPool, is_429, parse_retry_after

logger = logging.getLogger("llm_router.pool_llm")


def _set_key(delegate, key: str) -> None:
    """Swap the api_key on the delegate's underlying AsyncOpenAI client (per-request rotation)."""
    try:
        client = getattr(delegate, "_client", None)
        if client is not None:
            client.api_key = key
    except Exception:  # noqa: BLE001
        pass


class _PoolLLMStream(_lk_llm.LLMStream):
    """Runs the delegate stream with a pool-picked key; on 429 re-picks instantly, no dead-key walk."""

    def __init__(self, pool_llm: "PoolLLM", *, chat_ctx, tools, conn_options, extra):
        super().__init__(pool_llm, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._pool_llm = pool_llm
        self._extra = extra

    async def _run(self) -> None:
        pool = self._pool_llm.pool
        delegate = self._pool_llm.delegate
        attempts = max(1, pool.available_count())
        last_exc: Optional[Exception] = None
        for _ in range(attempts):
            chosen = pool.pick()
            if chosen is None:
                break  # whole provider cooling -> let FallbackAdapter advance to the next provider
            _set_key(delegate, chosen["key"])
            try:
                # delegate.chat() returns its own stream; forward every chunk into ours.
                stream = delegate.chat(
                    chat_ctx=self._chat_ctx,
                    tools=self._tools or None,
                    conn_options=self._conn_options,
                    **self._extra,
                )
                async with stream:
                    async for chunk in stream:
                        self._event_ch.send_nowait(chunk)
                pool.mark_ok(chosen["key"])
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if is_429(exc):
                    ra = parse_retry_after(exc)
                    pool.mark_429(chosen["key"], ra)
                    logger.info("PoolLLM[%s] key=%s 429 -> cooling %ss; instant re-pick",
                                pool.provider, chosen.get("label", "?"),
                                round(ra, 1) if ra else "default")
                    continue  # re-pick the next AVAILABLE key (not a linear walk of the dead one)
                raise        # non-429 -> surface immediately
        # exhausted: all keys cooling or repeated 429 -> raise so FallbackAdapter advances providers
        if last_exc is not None:
            raise last_exc
        raise _lk_llm.LLMError(f"PoolLLM[{pool.provider}]: all keys cooling/disabled")


class PoolLLM(_lk_llm.LLM):
    """A FallbackAdapter-compatible LLM member backed by a ProviderPool (smart key rotation)."""

    def __init__(self, *, pool: ProviderPool, delegate: _lk_llm.LLM, label: str = ""):
        super().__init__()
        self.pool = pool
        self.delegate = delegate
        self._pool_label = label or f"pool:{pool.provider}"
        # mirror strict-off so neither path schema-rejects loose tool calls
        try:
            self._strict_tool_schema = False  # noqa: SLF001
            self.delegate._strict_tool_schema = False  # noqa: SLF001
        except Exception:  # noqa: BLE001
            pass

    @property
    def model(self) -> str:
        return getattr(self.delegate, "model", self._pool_label)

    def chat(self, *, chat_ctx, tools=None,
             conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
             parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
             tool_choice: NotGivenOr = NOT_GIVEN,
             extra_kwargs: NotGivenOr[dict] = NOT_GIVEN):
        # Forward the standard LLM.chat kwargs the delegate accepts (skip NOT_GIVEN so the
        # delegate's own defaults apply). Robust across the groq/openai plugin signatures.
        extra: dict = {}
        if not _is_not_given(parallel_tool_calls):
            extra["parallel_tool_calls"] = parallel_tool_calls
        if not _is_not_given(tool_choice):
            extra["tool_choice"] = tool_choice
        if not _is_not_given(extra_kwargs):
            extra["extra_kwargs"] = extra_kwargs
        return _PoolLLMStream(self, chat_ctx=chat_ctx, tools=tools,
                              conn_options=conn_options, extra=extra)


def _is_not_given(v) -> bool:
    return v is NOT_GIVEN or type(v).__name__ == "NotGiven"
