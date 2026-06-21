"""config.py — Famit P0 secret resolver (additive, backwards-compatible).

Single source of truth for reading secrets/config values. Behavior:

  * If DOPPLER_TOKEN is set in the environment, fetch the project's secrets from
    Doppler ONCE at import (via the Doppler API, no CLI needed) and merge them
    UNDER os.environ — i.e. a value already present in os.environ / the loaded
    .env always WINS, so nothing that works today can change. Doppler only fills
    values that are otherwise unset.
  * If DOPPLER_TOKEN is absent (today's situation), this module is a thin wrapper
    over os.environ and changes NOTHING. `get()` == `os.getenv()`.

Doppler is therefore strictly OPTIONAL. The live service must keep working with
just the existing /opt/famit-agent/.env. Setting up Doppler is a user follow-up
(see bottom of this file).

Usage in caller.py / agent.py:
    from config import get, require
    PW = get("CALLER_PASS", "Famit@2026")
    GROQ_KEY = require("GROQ_API_KEY")

Nothing here ever raises at import time (a Doppler fetch failure is swallowed and
logged to stderr); the process always falls back to os.environ.
"""
from __future__ import annotations

import os
import sys
from typing import Optional

# ---- optional .env load (mirror caller.py; harmless if python-dotenv absent) ----
try:  # pragma: no cover - trivial
    from dotenv import load_dotenv

    # Load the same env file caller.py uses, without overriding already-set vars.
    load_dotenv(os.getenv("FAMIT_ENV_FILE", "/opt/famit-agent/.env"), override=False)
except Exception:  # noqa: BLE001
    pass


_DOPPLER_LOADED = False
_DOPPLER_KEYS: set[str] = set()      # which keys Doppler provided (for diagnostics)
_DOPPLER_ERROR: Optional[str] = None


def _load_doppler_into_environ() -> None:
    """Fetch secrets from Doppler and place them in os.environ WITHOUT overriding
    anything already set. Best-effort: any failure is recorded and ignored so the
    process falls back to the existing .env / os.environ."""
    global _DOPPLER_LOADED, _DOPPLER_ERROR
    token = os.getenv("DOPPLER_TOKEN", "").strip()
    if not token:
        return  # Doppler disabled -> today's behavior, nothing to do.
    try:
        import httpx  # already a caller.py dependency

        # Doppler "download secrets" REST endpoint. A Service Token scopes the
        # request to a single config, so project/config params are optional.
        params = {"format": "json"}
        proj = os.getenv("DOPPLER_PROJECT", "").strip()
        cfg = os.getenv("DOPPLER_CONFIG", "").strip()
        if proj:
            params["project"] = proj
        if cfg:
            params["config"] = cfg
        r = httpx.get(
            "https://api.doppler.com/v3/configs/config/secrets/download",
            params=params,
            auth=(token, ""),
            timeout=float(os.getenv("DOPPLER_TIMEOUT", "8")),
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            raise ValueError("unexpected Doppler payload type")
        applied = 0
        for k, v in data.items():
            if k in ("DOPPLER_TOKEN",):
                continue
            if v is None:
                continue
            # Do not override values already present (env/.env wins).
            if os.environ.get(k) in (None, ""):
                os.environ[k] = str(v)
                _DOPPLER_KEYS.add(k)
                applied += 1
        _DOPPLER_LOADED = True
        print(f"[config] Doppler: loaded {applied} secret(s) (env/.env values kept)",
              file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        _DOPPLER_ERROR = repr(exc)[:200]
        print(f"[config] Doppler fetch failed, falling back to .env/os.environ: "
              f"{_DOPPLER_ERROR}", file=sys.stderr)


# Resolve Doppler exactly once, at import.
_load_doppler_into_environ()


def get(key: str, default: Optional[str] = None) -> Optional[str]:
    """Read a config/secret value. Identical to os.getenv() except that, when
    Doppler is enabled, any Doppler-provided keys have already been merged into
    os.environ (without overriding pre-existing values)."""
    return os.environ.get(key, default)


def require(key: str) -> str:
    """Like get() but raises KeyError if missing/empty — for values the service
    cannot run without (mirrors caller.py's existing os.environ[...] usages)."""
    v = os.environ.get(key)
    if v is None or v == "":
        raise KeyError(f"required config '{key}' is not set "
                       f"(checked os.environ/.env"
                       f"{' and Doppler' if os.getenv('DOPPLER_TOKEN') else ''})")
    return v


def source() -> dict:
    """Diagnostics for a /health-style probe. Never exposes secret VALUES."""
    return {
        "doppler_enabled": bool(os.getenv("DOPPLER_TOKEN")),
        "doppler_loaded": _DOPPLER_LOADED,
        "doppler_keys_count": len(_DOPPLER_KEYS),
        "doppler_error": _DOPPLER_ERROR,
    }


# ============================================================================
# USER FOLLOW-UP — enabling Doppler (optional; nothing breaks if you skip this)
# ----------------------------------------------------------------------------
# 1. Create a Doppler project + config; import the current /opt/famit-agent/.env
#    values into it.
# 2. Mint a Doppler SERVICE TOKEN (read-only) scoped to that config.
# 3. On the droplet, add to /opt/famit-agent/.env:
#        DOPPLER_TOKEN=dp.st.xxxxxxxx
#    (optionally DOPPLER_PROJECT / DOPPLER_CONFIG if the token isn't config-scoped)
# 4. `sudo systemctl restart famit-caller famit-agent`.
# Until DOPPLER_TOKEN is set, this module is a no-op pass-through to os.environ.
# ============================================================================
