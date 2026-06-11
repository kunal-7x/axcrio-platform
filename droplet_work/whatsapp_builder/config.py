"""whatsapp_builder.config — environment + feature gating (dormant-safe).

NO secrets are printed anywhere. Reads the live env the box already holds.
Everything degrades gracefully: missing LLM key -> templated fallback; missing
Meta token -> submit is a no-op; missing DB -> JSONL fallback.
"""
from __future__ import annotations
import os


def _get(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _flag(name: str, default: str = "0") -> bool:
    return _get(name, default).lower() in ("1", "true", "yes", "on")


# ── Feature gate ───────────────────────────────────────────────────────────────
def feature_enabled() -> bool:
    """The mount gate. Default OFF -> live path byte-identical."""
    return _flag("FEATURE_WHATSAPP_BUILDER", "0")


# ── LLM seam (reuse the live Groq -> OpenRouter pool) ──────────────────────────
def groq_keys() -> list[str]:
    """The live round-robin Groq pool (GROQ_API_KEY + _2.._20). Same as agent.py."""
    keys: list[str] = []
    for nm in ["GROQ_API_KEY"] + [f"GROQ_API_KEY_{i}" for i in range(2, 21)]:
        v = _get(nm)
        if v and v not in keys:
            keys.append(v)
    return keys


def groq_model() -> str:
    return _get("GROQ_LLM_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")


def openrouter_key() -> str:
    """⚠ founder typo: OPNEROUTER_API_KEY is the real var; OPENROUTER_API_KEY is the fallback."""
    return _get("OPNEROUTER_API_KEY") or _get("OPENROUTER_API_KEY")


def openrouter_model() -> str:
    return _get("WAB_OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")


def llm_ready() -> bool:
    return bool(groq_keys() or openrouter_key())


def llm_timeout_s() -> float:
    try:
        return float(_get("WAB_LLM_TIMEOUT_S", "20") or 20)
    except Exception:
        return 20.0


# ── Meta WhatsApp Cloud API (submit seam — dormant until creds) ────────────────
def meta_token() -> str:
    return _get("META_WA_TOKEN")


def meta_waba_id() -> str:
    return _get("META_WA_BUSINESS_ACCOUNT_ID")


def meta_ready() -> bool:
    return bool(meta_token() and meta_waba_id())


def graph_base() -> str:
    return _get("META_GRAPH_BASE", "https://graph.facebook.com/v21.0")


def meta_app_id() -> str:
    """The Meta App ID — required for the Resumable Upload API (media headers).
    Derivable from the access token via /debug_token; persisted as META_WA_APP_ID."""
    return _get("META_WA_APP_ID") or _get("META_APP_ID")


# ── Credit (generation) ────────────────────────────────────────────────────────
def gen_credit_minor(n_templates: int) -> int:
    """Estimate the LLM credits (INR paise) for an n-template bundle.
    Small fixed estimate ~ a few credits; settled to actual after the call."""
    try:
        per = int(_get("WAB_GEN_CREDIT_PER_TEMPLATE_MINOR", "100") or 100)  # ₹1 / template
    except Exception:
        per = 100
    base = int(_get("WAB_GEN_CREDIT_BASE_MINOR", "100") or 100)
    n = max(1, min(int(n_templates or 1), 25))
    return base + per * n


# ── Storage ────────────────────────────────────────────────────────────────────
def jsonl_dir() -> str:
    return _get("WAB_JSONL_DIR", os.path.join("var", "whatsapp_builder"))


def require_approval() -> bool:
    """Default biases SAFE: human approval required before submit/attach/send."""
    return _flag("WAB_REQUIRE_APPROVAL", "1")
