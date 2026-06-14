"""provider_registry.named_transforms — the Tier-2 named-provider registry (W2).

Spec: design/PROVIDER-FRAMEWORK-PLAN.md §7 (Tier 2) + §4 ("named_transforms.py — REGISTERS
the existing video builders ... reused, not rewritten") + §14 W2 (named-`fal` must byte-match
the live `providers.py` golden).

THE DESIGN LAW HERE — REUSE, NEVER REWRITE: the existing
`media_gen/video/providers.build_submit / parse_submit_resp / build_status / parse_result`
ARE the named transforms. This module does NOT re-implement them — it IMPORTS them verbatim
and adapts the registry's provider-neutral envelope <-> the existing `VideoBrief` shape. A
test asserts the wire bytes a `fal` named-transform emits are IDENTICAL to calling
`media_gen.video.providers._fal_submit` directly (the golden), proving zero drift.

A named transform is a small object with two callables the adapter dispatches to:
    build(def_, cred_plaintext, envelope) -> (url, headers, body)
    parse(def_, raw_response)            -> response_envelope (the §7 internal shape)

ADDING A NEW NAMED FORMAT = one entry in NAMED + one test + one SSH push (§7 Tier-2 cost).

IMPORT SAFETY: the media_gen import is guarded — if the media_gen package isn't importable
in some context (it never is on the empty-env box at W2, since we don't mount), NAMED is
still constructed (the video entries are simply absent) and the module imports cleanly.
text-only named providers (anthropic/gemini) are pure-local and always present.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from .schema import Capability, ProviderDef

# Reuse the EXISTING video builders verbatim (do not rewrite). Guarded so an empty-env
# import never fails (the W1/W2 resting-byte-identical guarantee).
try:  # pragma: no cover - exercised when media_gen is on the path
    from media_gen.video import providers as _video_providers  # noqa: F401
    from media_gen.video.schema import VideoBrief as _VideoBrief
    _HAVE_VIDEO = True
except Exception:  # noqa: BLE001
    _video_providers = None  # type: ignore
    _VideoBrief = None  # type: ignore
    _HAVE_VIDEO = False


# ---------------------------------------------------------------------------
# The internal response envelope (§7) — every parse() returns this exact shape.
# ---------------------------------------------------------------------------
def _empty_response_envelope() -> dict:
    return {
        "text": "",
        "image_url": "",
        "video_url": "",
        "embedding": [],
        "external_id": "",
        "status": "submitted",
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "cost_micros": 0,
        "latency_ms": 0,
        "raw": {},
    }


@dataclass
class NamedTransform:
    """One Tier-2 named provider. `build`/`parse` bridge the neutral envelope <-> the
    provider's exact wire shape (reusing the existing builder where one exists)."""
    name: str
    build: Callable[[ProviderDef, str, dict], Tuple[str, dict, dict]]
    parse: Callable[[ProviderDef, Any], dict]


# ---------------------------------------------------------------------------
# VIDEO named providers — bridge to the EXISTING media_gen builders (REUSE).
# ---------------------------------------------------------------------------
def _envelope_to_video_brief(def_: ProviderDef, envelope: dict):
    """Map the registry's neutral request envelope onto the existing VideoBrief, so the
    EXISTING `providers.build_submit` produces byte-identical wire output. No rewrite."""
    params = dict(envelope.get("params") or {})
    # VideoBrief.from_any tolerates partials + fills safe defaults (never raises).
    brief_dict = {
        "tenant_id": envelope.get("tenant_id", "") or "",
        "prompt": envelope.get("prompt", "") or "",
        "image_url": envelope.get("image_url", "") or params.get("image_url", "") or "",
        "duration_s": params.get("duration_s", params.get("duration", 6)),
        "aspect_ratio": params.get("aspect_ratio", "9:16"),
        "resolution": params.get("resolution", "720p"),
        "model": envelope.get("model", "") or "",
        # `webhook_url` is passed to build_submit as its explicit 5th arg (and appended to the URL
        # by the existing builder) — it must NOT also land in brief.extra or it leaks into the body
        # (via _common_input's `d.update(brief.extra)`), drifting from the golden bytes.
        "extra": {k: v for k, v in params.items()
                  if k not in ("duration_s", "duration", "aspect_ratio", "resolution",
                               "image_url", "max_tokens", "temperature", "webhook_url")},
    }
    return _VideoBrief.from_any(brief_dict)


def _make_video_named(provider_name: str) -> NamedTransform:
    """Construct a NamedTransform that delegates to the existing video providers switch."""

    def _build(def_: ProviderDef, key: str, envelope: dict):
        brief = _envelope_to_video_brief(def_, envelope)
        model = (def_.model_default or envelope.get("model") or "") or ""
        webhook_url = str((envelope.get("params") or {}).get("webhook_url", "") or "")
        # EXACT existing builder — the golden test asserts these bytes match.
        return _video_providers.build_submit(provider_name, brief, model, key, webhook_url)

    def _parse(def_: ProviderDef, raw: Any) -> dict:
        out = _empty_response_envelope()
        # Reuse BOTH existing parsers: submit-resp (external_id) + result (status/url).
        submit = _video_providers.parse_submit_resp(provider_name, raw)
        result = _video_providers.parse_result(provider_name, raw)
        out["external_id"] = submit.get("external_id", "") or ""
        out["video_url"] = result.get("artifact_url", "") or ""
        # Map the video JobStatus vocabulary onto the envelope's status vocabulary.
        st = str(result.get("status", "") or "")
        out["status"] = _VIDEO_STATUS_MAP.get(st, "running")
        cost = result.get("cost_usd")
        if cost not in (None, ""):
            try:
                out["cost_micros"] = int(round(float(cost) * 1_000_000))
            except (TypeError, ValueError):
                out["cost_micros"] = 0
        out["raw"] = raw if isinstance(raw, dict) else {}
        return out

    return NamedTransform(name=provider_name, build=_build, parse=_parse)


# JobStatus (media_gen) strings -> the §7 envelope status vocabulary.
_VIDEO_STATUS_MAP = {
    "queued": "submitted",
    "submitted": "submitted",
    "running": "running",
    "succeeded": "succeeded",
    "failed": "failed",
    "cancelled": "failed",
    "not_configured": "failed",
}


# ---------------------------------------------------------------------------
# TEXT named providers (anthropic / gemini) — pure-local (no media_gen dep).
# These cover the §7 Tier-2 non-OAI text formats. Minimal, deterministic, offline.
# ---------------------------------------------------------------------------
def _anthropic_build(def_: ProviderDef, key: str, envelope: dict):
    base = (def_.base_url or "https://api.anthropic.com").rstrip("/")
    url = f"{base}/v1/messages"
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    params = dict(envelope.get("params") or {})
    body = {
        "model": def_.model_default or envelope.get("model") or "",
        "max_tokens": int(params.get("max_tokens", 1024) or 1024),
        "messages": [{"role": "user", "content": envelope.get("prompt", "") or ""}],
    }
    if "temperature" in params:
        body["temperature"] = params["temperature"]
    if envelope.get("system"):
        body["system"] = envelope["system"]
    return url, headers, body


def _anthropic_parse(def_: ProviderDef, raw: Any) -> dict:
    out = _empty_response_envelope()
    if isinstance(raw, dict):
        content = raw.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                out["text"] = str(first.get("text", "") or "")
        usage = raw.get("usage") or {}
        if isinstance(usage, dict):
            out["usage"] = {
                "input_tokens": int(usage.get("input_tokens", 0) or 0),
                "output_tokens": int(usage.get("output_tokens", 0) or 0),
            }
        out["status"] = "succeeded" if out["text"] else "failed"
        out["raw"] = raw
    return out


def _gemini_build(def_: ProviderDef, key: str, envelope: dict):
    base = (def_.base_url or "https://generativelanguage.googleapis.com").rstrip("/")
    model = def_.model_default or envelope.get("model") or "gemini-1.5-flash"
    # Gemini puts the key in the query string (api_key_query analogue).
    url = f"{base}/v1beta/models/{model}:generateContent?key={key}"
    headers = {"Content-Type": "application/json"}
    body = {
        "contents": [{"role": "user", "parts": [{"text": envelope.get("prompt", "") or ""}]}],
    }
    params = dict(envelope.get("params") or {})
    gen_cfg = {}
    if "max_tokens" in params:
        gen_cfg["maxOutputTokens"] = int(params["max_tokens"])
    if "temperature" in params:
        gen_cfg["temperature"] = params["temperature"]
    if gen_cfg:
        body["generationConfig"] = gen_cfg
    return url, headers, body


def _gemini_parse(def_: ProviderDef, raw: Any) -> dict:
    out = _empty_response_envelope()
    if isinstance(raw, dict):
        cands = raw.get("candidates")
        if isinstance(cands, list) and cands:
            parts = (((cands[0] or {}).get("content") or {}).get("parts")) or []
            if isinstance(parts, list) and parts and isinstance(parts[0], dict):
                out["text"] = str(parts[0].get("text", "") or "")
        usage = raw.get("usageMetadata") or {}
        if isinstance(usage, dict):
            out["usage"] = {
                "input_tokens": int(usage.get("promptTokenCount", 0) or 0),
                "output_tokens": int(usage.get("candidatesTokenCount", 0) or 0),
            }
        out["status"] = "succeeded" if out["text"] else "failed"
        out["raw"] = raw
    return out


# ---------------------------------------------------------------------------
# THE REGISTRY. video entries present only when media_gen is importable.
# ---------------------------------------------------------------------------
NAMED: Dict[str, NamedTransform] = {
    "anthropic": NamedTransform("anthropic", _anthropic_build, _anthropic_parse),
    "gemini": NamedTransform("gemini", _gemini_build, _gemini_parse),
}

# Video providers that map onto the EXISTING media_gen switch (§7: fal/replicate/luma/
# higgsfield/selfhost/generic). Registered by reference — never re-implemented here.
_VIDEO_NAMES = ("fal", "replicate", "luma", "higgsfield", "selfhost", "generic")
if _HAVE_VIDEO:
    for _vn in _VIDEO_NAMES:
        NAMED[_vn] = _make_video_named(_vn)


def get_named_transform(name: str) -> Optional[NamedTransform]:
    """Look up a Tier-2 named transform by `named_provider`. None if unregistered (the
    adapter then yields a `not_configured`-shaped failure, never raises)."""
    return NAMED.get((name or "").strip().lower())


def available_named() -> Dict[str, bool]:
    """Diagnostic: which named providers are registered in THIS process (video entries
    depend on media_gen being importable). Never echoes anything secret."""
    base = {k: True for k in NAMED}
    for vn in _VIDEO_NAMES:
        base.setdefault(vn, False)
    return base
