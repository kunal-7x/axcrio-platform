"""ads_engine.llm_gateway — the VAULT-CONFIGURABLE, REAL-TIME reasoning-model gateway.

Founder decision #2 (V2_DECISIONS.md): the LLM layer is NOT hardcoded to Claude/Sarvam.
A tenant pastes ONE key into the per-tenant vault under the "reasoning_model" connection and
SELECTS a model from the UI; this module reads that per-tenant config at RUNTIME and routes
every reasoning / copy / brief LLM call through it — in real time, NO REDEPLOY (the same
"paste-key -> it works" law as the ad-platform connections).

  * OpenRouter (recommended): one key -> ANY model (deepseek / groq / claude / llama / ...).
  * OR a direct provider key: groq | anthropic | openai | sarvam + a selected model.

THE LAW (binding — every invariant the master plan pins):
  * PROPOSAL-ONLY. This gateway returns TEXT proposals (ad copy / brief drafts / narration).
    It has ZERO spend authority — it never calls campaign.approve / optimization mutations /
    a connector. "LLM never on the spend path" is structural here: there is no spend door.
  * EARNER-SAFE. The Devanagari VOICE brain (agent.py) NEVER touches this module. No
    `from caller import ...`. Keys come ONLY through the injected vault seam (vault_adapter),
    never os.environ / a *_key constant, and are returned TRANSIENTLY — never logged/persisted.
  * FAIL-CLOSED + DEGRADE-NEVER-RAISE. No vault config -> {ok:False, reason:"not_configured"}.
    litellm/langfuse absent -> {ok:False, reason:"gateway_unavailable"} (the route renders
    dormant). A provider/network error -> {ok:False, reason:"provider_error"}. NEVER raises
    into the request thread or the live spine.
  * PER-TENANT COST CAP. An optional `monthly_cap_minor` in the blob hard-stops calls once the
    tenant's month-to-date LLM spend (paise) would exceed it (fail-closed -> "cap_exceeded").

litellm + langfuse are LAZY/optional: imported inside the call path, swallowed if missing, so
the package import stays cheap + crash-proof (the mount guard is never tripped). Tests inject a
mock `complete_impl` so the whole path is offline-verifiable with no key and no network.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import store, vault_adapter

_log = logging.getLogger("ads_engine.llm_gateway")

# The vault connection key: a provider_def with named_provider "reasoning_model" holds the blob.
NAMED_PROVIDER = "reasoning_model"
# Capability the def advertises (reasoning/copy/tool-call text generation).
CAPABILITY = "reasoning"

# USD -> paise conversion for cost metering (1 USD ~= Rs.86 ~= 8600 paise). Configurable via
# env ADS_LLM_USD_TO_MINOR; a rough peg is fine (cost is informational + cap-guarding, not billed).
_DEFAULT_USD_TO_MINOR = 8600

# Collection (tenant-scoped) where month-to-date LLM spend is metered (paise, append-only-ish).
_USAGE_COLLECTION = "llm_usage"


# ---------------------------------------------------------------------------
# PROVIDER MAP — provider slug -> how to address it through litellm.
#   prefix    : the litellm model-string prefix ("<prefix><model>")
#   base_url  : default api base (overridable by the blob's base_url)
# OpenRouter is the recommended one-key-any-model door; the rest are direct.
# ---------------------------------------------------------------------------
PROVIDER_MAP: dict = {
    "openrouter": {"prefix": "openrouter/", "base_url": "https://openrouter.ai/api/v1"},
    "groq":       {"prefix": "groq/",       "base_url": ""},
    "anthropic":  {"prefix": "anthropic/",  "base_url": ""},
    "openai":     {"prefix": "openai/",     "base_url": ""},
    # Sarvam is OpenAI-compatible -> route via the openai prefix + Sarvam's base_url.
    "sarvam":     {"prefix": "openai/",     "base_url": "https://api.sarvam.ai/v1"},
}

# Recommended catalog surfaced in the UI (provider -> [model ids]). Claude (reasoning/English) +
# Sarvam (Hinglish) are the defaults the founder named; the tenant has full flexibility.
RECOMMENDED: dict = {
    "openrouter": [
        "anthropic/claude-3.5-sonnet", "deepseek/deepseek-chat",
        "meta-llama/llama-3.3-70b-instruct", "google/gemini-2.0-flash-001",
        "groq/llama-3.3-70b-versatile",
    ],
    "groq":      ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    "anthropic": ["claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"],
    "openai":    ["gpt-4o", "gpt-4o-mini"],
    "sarvam":    ["sarvam-m"],
}
DEFAULT_PROVIDER = "openrouter"
DEFAULT_MODEL = "anthropic/claude-3.5-sonnet"


# ---------------------------------------------------------------------------
# Resolved per-tenant config (in-process value object — NEVER persisted/logged).
# repr suppresses the api_key.
# ---------------------------------------------------------------------------
@dataclass
class ResolvedModel:
    ok: bool
    tenant_id: str
    provider: str = ""
    model: str = ""
    api_key: str = field(default="", repr=False)
    base_url: str = ""
    litellm_model: str = ""          # the fully-prefixed model string litellm expects
    monthly_cap_minor: int = 0       # 0 => no cap
    temperature: float = 0.7
    provider_def_id: str = ""
    reason: str = "ok"               # ok | not_configured | no_credential | bad_shape


# ---------------------------------------------------------------------------
# Config resolution — RUNTIME read of the per-tenant vault blob (no redeploy).
# ---------------------------------------------------------------------------
def _def_id(tenant_id: str) -> str:
    """Resolve the reasoning_model provider_def id for this tenant (named_provider lookup)."""
    try:
        return vault_adapter.resolve_provider_def_id(
            tenant_id, named_provider=NAMED_PROVIDER) or ""
    except Exception:  # noqa: BLE001 — degrade to "" (renders not_configured)
        return ""


def _normalize(provider: str, model: str, blob: dict, tenant_id: str,
               def_id: str) -> ResolvedModel:
    provider = (provider or "").strip().lower()
    spec = PROVIDER_MAP.get(provider)
    if spec is None:
        return ResolvedModel(ok=False, tenant_id=tenant_id, provider=provider,
                             provider_def_id=def_id, reason="bad_shape")
    api_key = vault_adapter.get_field(blob, "api_key") or vault_adapter.get_field(blob, "key") or ""
    if not api_key:
        return ResolvedModel(ok=False, tenant_id=tenant_id, provider=provider,
                             provider_def_id=def_id, reason="no_credential")
    model = (model or "").strip() or DEFAULT_MODEL
    base_url = vault_adapter.get_field(blob, "base_url") or spec["base_url"] or ""
    # litellm model string: prefix unless the tenant already typed a fully-qualified id.
    prefix = spec["prefix"]
    litellm_model = model if model.startswith(prefix) else f"{prefix}{model}"
    cap = 0
    try:
        cap = int(blob.get("monthly_cap_minor") or 0)
    except Exception:  # noqa: BLE001
        cap = 0
    temp = 0.7
    try:
        if blob.get("temperature") is not None:
            temp = float(blob.get("temperature"))
    except Exception:  # noqa: BLE001
        temp = 0.7
    return ResolvedModel(
        ok=True, tenant_id=tenant_id, provider=provider, model=model, api_key=api_key,
        base_url=base_url, litellm_model=litellm_model, monthly_cap_minor=max(0, cap),
        temperature=temp, provider_def_id=def_id, reason="ok")


def resolve(tenant_id: str) -> ResolvedModel:
    """Read + parse the per-tenant reasoning-model config from the vault, RIGHT NOW.

    Returns a ResolvedModel; .ok is False with a reason on any miss (not_configured /
    no_credential / bad_shape). NEVER raises, NEVER logs the key. This is the real-time,
    no-redeploy door: a key/model the tenant saved a second ago is picked up on the next call.
    """
    if not tenant_id:
        return ResolvedModel(ok=False, tenant_id="", reason="not_configured")
    def_id = _def_id(tenant_id)
    if not def_id:
        return ResolvedModel(ok=False, tenant_id=tenant_id, reason="not_configured")
    try:
        blob = vault_adapter.get_secret_json(tenant_id, def_id)
    except Exception:  # noqa: BLE001
        blob = None
    if not isinstance(blob, dict):
        return ResolvedModel(ok=False, tenant_id=tenant_id, provider_def_id=def_id,
                             reason="no_credential")
    provider = (vault_adapter.get_field(blob, "provider") or DEFAULT_PROVIDER)
    model = (vault_adapter.get_field(blob, "model") or "")
    return _normalize(provider, model, blob, tenant_id, def_id)


def save_selection(tenant_id: str, *, provider: str = "", model: str = "",
                   api_key: str = "", monthly_cap_minor: Optional[int] = None,
                   base_url: str = "", temperature: Optional[float] = None) -> dict:
    """Persist a tenant's reasoning-model SELECTION into the vault (real-time, no redeploy).

    Merges {provider, model, api_key?, monthly_cap_minor?, base_url?, temperature?} into the
    existing `reasoning_model` credential blob via the registry's AES-256-GCM encrypt + RLS upsert
    (vault_adapter.write_channel_blob). The provider DEF must already exist (seeded `_global` or
    created in the vault UI) — `reason:"not_configured"` if it does not. SECRET-FREE return:
      { ok, reason, fields_written: [names...] }   (never echoes the api_key)

    The instant this returns ok, the NEXT gateway call picks up the new model/key — same
    "paste-key -> it works" law as the ad-platform connections. Validates the provider slug
    against PROVIDER_MAP (an unknown provider is rejected, not stored)."""
    updates: dict = {}
    p = (provider or "").strip().lower()
    if p:
        if p not in PROVIDER_MAP:
            return {"ok": False, "reason": "bad_provider", "fields_written": []}
        updates["provider"] = p
    if model:
        updates["model"] = str(model).strip()
    if api_key:
        updates["api_key"] = str(api_key)
    if base_url:
        updates["base_url"] = str(base_url).strip()
    if monthly_cap_minor is not None:
        try:
            updates["monthly_cap_minor"] = max(0, int(monthly_cap_minor))
        except Exception:  # noqa: BLE001
            pass
    if temperature is not None:
        try:
            updates["temperature"] = float(temperature)
        except Exception:  # noqa: BLE001
            pass
    if not updates:
        return {"ok": False, "reason": "no_updates", "fields_written": []}
    try:
        res = vault_adapter.write_channel_blob(tenant_id, "reasoning", updates)
    except Exception:  # noqa: BLE001 — degrade-never-raise
        return {"ok": False, "reason": "write_error", "fields_written": []}
    # never leak the api_key name's VALUE; field names are safe.
    return {"ok": bool(res.get("ok")), "reason": res.get("reason", ""),
            "fields_written": res.get("fields_written", [])}


def status(tenant_id: str) -> dict:
    """SECRET-FREE config status for the Connections UI (no key, no key-prefix).

    Returns { configured, provider, model, has_key, monthly_cap_minor, month_spend_minor,
    gateway_available, reason }. Safe to log / render. Never raises."""
    r = resolve(tenant_id)
    return {
        "configured": bool(r.ok),
        "provider": r.provider,
        "model": r.model,
        "has_key": bool(r.ok),
        "monthly_cap_minor": int(r.monthly_cap_minor or 0),
        "month_spend_minor": _month_spend_minor(tenant_id),
        "gateway_available": gateway_available(),
        "reason": r.reason,
    }


# ---------------------------------------------------------------------------
# Cost metering + per-tenant monthly cap (paise).
# ---------------------------------------------------------------------------
def _month_key(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m", time.gmtime(ts if ts is not None else time.time()))


def _month_spend_minor(tenant_id: str) -> int:
    """Month-to-date LLM spend (paise) for this tenant, from the metering collection. 0 on miss."""
    mk = _month_key()
    try:
        row = store.get_row(tenant_id, _USAGE_COLLECTION, mk)
    except Exception:  # noqa: BLE001
        row = None
    if not isinstance(row, dict):
        return 0
    try:
        return int(row.get("spend_minor") or 0)
    except Exception:  # noqa: BLE001
        return 0


def _record_spend(tenant_id: str, cost_minor: int, model: str) -> None:
    """Append-add `cost_minor` to the tenant's month-to-date LLM spend (best-effort, never raises)."""
    if cost_minor <= 0:
        return
    mk = _month_key()
    try:
        row = store.get_row(tenant_id, _USAGE_COLLECTION, mk) or {}
        if not isinstance(row, dict):
            row = {}
        row["spend_minor"] = int(row.get("spend_minor") or 0) + int(cost_minor)
        row["calls"] = int(row.get("calls") or 0) + 1
        row["last_model"] = model
        row["month"] = mk
        store.put_row(tenant_id, _USAGE_COLLECTION, mk, row)
    except Exception:  # noqa: BLE001 — metering must never break a proposal
        pass


def _usd_to_minor(usd: float) -> int:
    try:
        from . import config as _cfg
        rate = int(_cfg.cfg("ADS_LLM_USD_TO_MINOR", str(_DEFAULT_USD_TO_MINOR)))
    except Exception:  # noqa: BLE001
        rate = _DEFAULT_USD_TO_MINOR
    try:
        return max(0, int(round(float(usd) * rate)))
    except Exception:  # noqa: BLE001
        return 0


# ---------------------------------------------------------------------------
# THE GATEWAY CALL — litellm (lazy) + langfuse (lazy) + injectable mock impl.
# ---------------------------------------------------------------------------
def gateway_available() -> bool:
    """True iff litellm is importable (the gateway can actually route a call). Cheap probe."""
    try:
        import litellm  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _default_complete_impl(rm: ResolvedModel, messages: list, opts: dict) -> dict:
    """The real litellm call. Returns {text, cost_minor, usage, model}. Raises on provider error
    (the caller wraps it into reason="provider_error"). Langfuse tracing is best-effort."""
    import litellm  # lazy — only imported when an actual call is made

    params: dict = {
        "model": rm.litellm_model,
        "messages": messages,
        "api_key": rm.api_key,
        "temperature": float(opts.get("temperature", rm.temperature)),
        "max_tokens": int(opts.get("max_tokens", 1024)),
    }
    if rm.base_url:
        params["api_base"] = rm.base_url
    rf = opts.get("response_format")
    if rf:
        params["response_format"] = rf

    # Langfuse trace (best-effort): litellm has a native callback integration; if langfuse is
    # installed we register it so per-tenant cost/trace lands without coupling the call path.
    try:
        import langfuse  # noqa: F401
        cb = list(getattr(litellm, "success_callback", []) or [])
        if "langfuse" not in cb:
            litellm.success_callback = cb + ["langfuse"]
        params["metadata"] = {
            "trace_name": str(opts.get("trace_name") or "ads.reasoning"),
            "tenant_id": rm.tenant_id, "session_id": str(opts.get("session_id") or ""),
            "tags": ["ads_engine", "proposal_only"],
        }
    except Exception:  # noqa: BLE001 — langfuse absent/misconfigured => trace skipped, call proceeds
        pass

    resp = litellm.completion(**params)
    text = ""
    try:
        text = resp.choices[0].message.content or ""
    except Exception:  # noqa: BLE001
        text = ""
    usage = {}
    try:
        u = getattr(resp, "usage", None)
        if u is not None:
            usage = {"prompt_tokens": getattr(u, "prompt_tokens", 0),
                     "completion_tokens": getattr(u, "completion_tokens", 0),
                     "total_tokens": getattr(u, "total_tokens", 0)}
    except Exception:  # noqa: BLE001
        usage = {}
    cost_minor = 0
    try:
        usd = float(litellm.completion_cost(completion_response=resp) or 0.0)
        cost_minor = _usd_to_minor(usd)
    except Exception:  # noqa: BLE001
        cost_minor = 0
    return {"text": text, "cost_minor": cost_minor, "usage": usage, "model": rm.litellm_model}


def complete(tenant_id: str, messages: list, *,
             complete_impl: Optional[Callable[[ResolvedModel, list, dict], dict]] = None,
             **opts: Any) -> dict:
    """Route ONE chat completion through the tenant's vault-selected model. PROPOSAL-ONLY.

    Returns a SECRET-FREE dict:
      { ok, text, provider, model, cost_minor, usage, month_spend_minor, reason, trace_id }
      reason ∈ ok | not_configured | no_credential | gateway_unavailable | cap_exceeded |
               provider_error | bad_request

    `complete_impl` is the injection seam tests use to supply a mock provider (so the entire
    resolve -> cap -> route -> meter path is verifiable offline with NO key and NO network).
    NEVER raises; NEVER logs the key or the prompt content at INFO.
    """
    if not isinstance(messages, list) or not messages:
        return _fail("bad_request", tenant_id)

    rm = resolve(tenant_id)
    if not rm.ok:
        # not_configured / no_credential / bad_shape -> fail-closed, render dormant.
        return _fail(rm.reason if rm.reason != "ok" else "not_configured", tenant_id,
                     provider=rm.provider, model=rm.model)

    impl = complete_impl or _default_complete_impl
    if complete_impl is None and not gateway_available():
        return _fail("gateway_unavailable", tenant_id, provider=rm.provider, model=rm.model)

    # PER-TENANT MONTHLY CAP (fail-closed): block BEFORE spending if MTD already >= cap.
    if rm.monthly_cap_minor > 0:
        spent = _month_spend_minor(tenant_id)
        if spent >= rm.monthly_cap_minor:
            out = _fail("cap_exceeded", tenant_id, provider=rm.provider, model=rm.model)
            out["month_spend_minor"] = spent
            out["monthly_cap_minor"] = rm.monthly_cap_minor
            return out

    try:
        res = impl(rm, messages, dict(opts))
    except Exception as exc:  # noqa: BLE001 — provider/network error => fail-closed, never raise
        _log.warning("ads_engine.llm_gateway.complete provider error: %r", type(exc).__name__)
        return _fail("provider_error", tenant_id, provider=rm.provider, model=rm.model)

    cost_minor = int((res or {}).get("cost_minor") or 0)
    _record_spend(tenant_id, cost_minor, rm.model)
    return {
        "ok": True,
        "text": str((res or {}).get("text") or ""),
        "provider": rm.provider,
        "model": rm.model,
        "cost_minor": cost_minor,
        "usage": (res or {}).get("usage") or {},
        "month_spend_minor": _month_spend_minor(tenant_id),
        "reason": "ok",
        "trace_id": str((res or {}).get("trace_id") or ""),
    }


def complete_json(tenant_id: str, messages: list, **opts: Any) -> dict:
    """`complete` + best-effort JSON parse of the model's text. Returns the same dict plus
    `data` (the parsed object) when the text is valid JSON, else `data=None`. Asks the provider
    for a json object via response_format when not overridden."""
    opts.setdefault("response_format", {"type": "json_object"})
    out = complete(tenant_id, messages, **{k: v for k, v in opts.items()
                                           if k != "complete_impl"},
                   complete_impl=opts.get("complete_impl"))
    out["data"] = None
    if out.get("ok") and out.get("text"):
        out["data"] = _safe_json(out["text"])
    return out


def _safe_json(text: str):
    """Parse a JSON object out of model text (tolerates ```json fences). None on failure."""
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s[:4].lower() == "json":
            s = s[4:]
        s = s.strip()
    try:
        data = json.loads(s)
        return data
    except Exception:  # noqa: BLE001
        # last resort: grab the outermost {...}
        try:
            i, j = s.find("{"), s.rfind("}")
            if 0 <= i < j:
                return json.loads(s[i:j + 1])
        except Exception:  # noqa: BLE001
            return None
    return None


def _fail(reason: str, tenant_id: str, *, provider: str = "", model: str = "") -> dict:
    return {
        "ok": False, "text": "", "provider": provider, "model": model,
        "cost_minor": 0, "usage": {}, "month_spend_minor": _month_spend_minor(tenant_id),
        "reason": reason, "trace_id": "",
    }


__all__ = [
    "NAMED_PROVIDER", "CAPABILITY", "PROVIDER_MAP", "RECOMMENDED",
    "DEFAULT_PROVIDER", "DEFAULT_MODEL", "ResolvedModel",
    "resolve", "status", "complete", "complete_json", "gateway_available",
]
