"""pmodel.vision_providers — env-gated provider switch for floor-plan vision.

The default provider is **openrouter** (the existing, working path). GLM (Zhipu)
and MiniMax are alternates: both expose an OpenAI-compatible `/chat/completions`
that accepts an image content-block and returns JSON in
`choices[0].message.content` — the exact shape `analyzer._chat` already parses, so
this is a *provider switch*, not a rewrite.

Returns None when the selected provider has no key (dormant → the router maps it to
a 503 `vision_not_configured`, never a crash). The working OpenRouter path is
untouched when `PMODEL_VISION_PROVIDER` is unset.

Notes from research (2025/2026):
- There is NO `glm-5.2` *vision* model — glm-5 / 4.7 / 4.6 are text-only; vision is
  `glm-4.6v` / `glm-4.5v`. Set `thinking.type=disabled` for fast, clean JSON.
- MiniMax's OpenAI-compatible path needs **no GroupId** (that's only for the legacy
  native endpoint). Its `response_format` JSON-mode is unreliable, so we DON'T send
  it and rely on the prompt + `_extract_json`.
"""
from __future__ import annotations

import os


def _g(name: str) -> str:
    return (os.getenv(name) or "").strip()


def select() -> str:
    return (_g("PMODEL_VISION_PROVIDER") or "openrouter").lower()


def resolve():
    """-> (url, model, headers, extra_body, send_json_mode) for the active alternate
    provider, or None when the provider is openrouter/unknown or has no key.
    `extra_body` is merged into the payload; `send_json_mode` says whether to add
    response_format={"type":"json_object"}."""
    p = select()
    if p == "glm":
        key = _g("ZAI_API_KEY") or _g("GLM_API_KEY")
        if not key:
            return None
        return (
            _g("PMODEL_GLM_BASE") or "https://api.z.ai/api/paas/v4/chat/completions",
            _g("PMODEL_GLM_MODEL") or "glm-4.6v",
            {"Authorization": "Bearer " + key, "content-type": "application/json"},
            {"thinking": {"type": "disabled"}},
            True,
        )
    if p == "minimax":
        key = _g("MINIMAX_API_KEY")
        if not key:
            return None
        return (
            _g("PMODEL_MINIMAX_BASE") or "https://api.minimax.io/v1/chat/completions",
            _g("PMODEL_MINIMAX_MODEL") or "MiniMax-M3",
            {"Authorization": "Bearer " + key, "content-type": "application/json"},
            {},
            False,  # MiniMax: don't send response_format; rely on prompt + _extract_json
        )
    return None  # openrouter (or unknown) -> caller uses the existing path


def configured() -> bool:
    """True if the *active* vision provider has a key (incl. default OpenRouter)."""
    if select() in ("glm", "minimax"):
        return resolve() is not None
    return bool(_g("OPENROUTER_API_KEY"))


def label() -> str:
    p = select()
    if p in ("glm", "minimax"):
        return p
    return "openrouter"
