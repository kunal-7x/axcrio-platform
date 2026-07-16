"""ai_manager.config — package-wide env reads (dormant-until-key).

Spec: plans/aim-build/BUILD_SPEC.md §A + schema-and-config-contract.md §4 +
caller-consumer-contract.md §5 (env table).

PATTERN (mirrors droplet_work/provider_registry/config.py): every value is read
from os.environ at CALL TIME, never cached at import, so:
  * an empty environment imports cleanly and yields safe (dormant) defaults,
  * a key flip / `.env` append takes effect on the next process boot with NO
    restart of THIS module's import,
  * nothing here ever raises at import, does ZERO I/O, touches no network/DB/FS
    (the master design law: resting byte-identical, dormant-until-key).

Consumers (ground truth for the exact surface):
  * intent/driver.py     -> llm_provider()
  * state_machine.py     -> max_pin_attempts(), llm_provider()
  * endpoints.py         -> sessions_file()  (used as a pathlib.Path)
  * tools/catalog.py     -> asset_service_base()
  * transport.py / store / recorder / __init__.py -> the rest.

Secrets (AIM_SPACES_KEY/SECRET, *_API_KEY, *_SERVICE_TOKEN) are read but MUST NOT
be logged or echoed — snapshot() exposes booleans only.
"""
from __future__ import annotations

import os
import pathlib
from typing import Dict, List


# --------------------------------------------------------------------------- #
# truthy parse — lenient, matches how the rest of the box reads boolean flags
# --------------------------------------------------------------------------- #
_TRUTHY = {"1", "true", "yes", "on"}


def _truthy(val: str | None) -> bool:
    """Lenient truthy parse: {1,true,yes,on} case-insensitive. Unset/garbage -> False."""
    if val is None:
        return False
    return val.strip().lower() in _TRUTHY


def _str_env(key: str, default: str = "") -> str:
    """Read a string env var; unset -> default. Never raises."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw


def _int_env(key: str, default: int) -> int:
    """Read an int env var; fall back to default on unset/blank/garbage (never raises)."""
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
# LLM / NLU
# --------------------------------------------------------------------------- #
def llm_provider() -> str:
    """NLU provider id. `AIM_LLM_PROVIDER` default `"none"`; blank -> `"none"`.

    (driver + state_machine.) Lower-cased + stripped so callers can branch
    deterministically; the dormant stub fires whenever this is `"none"`.

    NOTE: the schema-and-config contract table lists a `"groq"` default, but the
    frozen BUILD_SPEC §A pins the default to `"none"` (dormant-by-default locally,
    so the deterministic NLU stub is the import-time behaviour). BUILD_SPEC wins.
    """
    val = os.environ.get("AIM_LLM_PROVIDER", "none").strip().lower()
    return val or "none"


def llm_model() -> str:
    """Groq model for intent parse. `AIM_GROQ_MODEL` default `llama-3.3-70b-versatile`."""
    val = _str_env("AIM_GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    return val or "llama-3.3-70b-versatile"


def llm_config() -> Dict[str, str]:
    """`{provider, model, api_key}`. api_key from GROQ_API_KEY (fallback AIM_GROQ_API_KEY).

    Secret is returned here for the live NLU client only — never logged/echoed in
    snapshot(). Empty when no key is set (dormant)."""
    api_key = os.environ.get("GROQ_API_KEY") or os.environ.get("AIM_GROQ_API_KEY") or ""
    return {
        "provider": llm_provider(),
        "model": llm_model(),
        "api_key": api_key,
    }


# --------------------------------------------------------------------------- #
# PIN / firewall
# --------------------------------------------------------------------------- #
def max_pin_attempts() -> int:
    """Failed-PIN lockout threshold. `AIM_PIN_MAX_ATTEMPTS` default 3. (state_machine.)"""
    return _int_env("AIM_PIN_MAX_ATTEMPTS", 3)


# --------------------------------------------------------------------------- #
# Sessions JSONL (control-plane fallback store used by endpoints)
# --------------------------------------------------------------------------- #
def sessions_file() -> pathlib.Path:
    """JSONL path for the control-plane session log. `AIM_SESSIONS_FILE` override,
    else `var/ai_manager_sessions.jsonl` under cwd. (endpoints.)

    Returns a pathlib.Path — endpoints does `.parent.mkdir(...)`, `.exists()`, and
    `open(f, ...)`. No directory is created here (import/read does ZERO I/O); the
    caller is responsible for mkdir at write time."""
    raw = os.environ.get("AIM_SESSIONS_FILE", "").strip()
    if raw:
        return pathlib.Path(raw)
    return pathlib.Path.cwd() / "var" / "ai_manager_sessions.jsonl"


# --------------------------------------------------------------------------- #
# Internal transport / loopback to caller.py /api + the asset service
# --------------------------------------------------------------------------- #
def asset_service_base() -> str:
    """Base URL of the Asset (creative) Service. `AIM_ASSET_SERVICE_BASE`
    default `http://127.0.0.1:8310`. (catalog -> transport.call_service.)"""
    val = _str_env("AIM_ASSET_SERVICE_BASE", "http://127.0.0.1:8310").strip()
    return val or "http://127.0.0.1:8310"


def loopback_base() -> str:
    """Loopback base for internal action calls into caller.py /api.
    `AIM_API_BASE` default `http://127.0.0.1:8209`. (transport.)"""
    val = _str_env("AIM_API_BASE", "http://127.0.0.1:8209").strip()
    return val or "http://127.0.0.1:8209"


def service_token() -> str:
    """Bearer for service-to-service calls. `AIM_SERVICE_TOKEN` default `""`
    (empty -> the token gate is closed; service-token endpoints stay 401)."""
    return _str_env("AIM_SERVICE_TOKEN", "")


def aiwf_service_token() -> str:
    """The transport dormancy gate. `AIWF_SERVICE_TOKEN` default `""`.
    Transport is dormant (no live loopback) until this is set. (transport / delegate.)"""
    return _str_env("AIWF_SERVICE_TOKEN", "")


def transport_configured() -> bool:
    """True iff the live loopback transport is armed (AIWF token present).
    delegate uses this to pick live vs stub tool registry."""
    return bool(aiwf_service_token().strip())


def x_auth_value() -> str:
    """The `X-Auth` header value the caller expects.
    `X_AUTH_VALUE` (legacy `FAMIT_X_AUTH`) default `"FamitCall2026"`. (transport.)"""
    raw = os.environ.get("X_AUTH_VALUE")
    if raw is None:
        raw = os.environ.get("FAMIT_X_AUTH")
    if raw is None or raw.strip() == "":
        return "FamitCall2026"
    return raw


def x_auth_set() -> bool:
    """True iff an explicit X-Auth value (not the baked default) was set in env."""
    raw = os.environ.get("X_AUTH_VALUE") or os.environ.get("FAMIT_X_AUTH") or ""
    return bool(raw.strip())


# --------------------------------------------------------------------------- #
# Postgres (the store rides shared db.engine; this gates the private DSN path)
# --------------------------------------------------------------------------- #
def pg_dsn() -> str:
    """Private Postgres DSN. `AIM_PG_DSN` default `""`.
    Empty -> ensure_schema() is a no-op + the store stays InMemory."""
    return _str_env("AIM_PG_DSN", "")


def pg_configured() -> bool:
    """True iff a private AIM Postgres DSN is set (the dormant-until-key pivot)."""
    return bool(pg_dsn().strip())


# --------------------------------------------------------------------------- #
# Recording / DO Spaces
# --------------------------------------------------------------------------- #
def _spaces_required_set() -> bool:
    """All four required AIM_SPACES_* present (region has a default, excluded)."""
    return all(
        bool(os.environ.get(k, "").strip())
        for k in ("AIM_SPACES_BUCKET", "AIM_SPACES_KEY", "AIM_SPACES_SECRET", "AIM_SPACES_ENDPOINT")
    )


def recording_active() -> bool:
    """Egress recorder on/off. `AIM_RECORDING_ENABLED` truthy AND all four
    AIM_SPACES_{BUCKET,KEY,SECRET,ENDPOINT} set. Off -> NullRecorder."""
    return _truthy(os.environ.get("AIM_RECORDING_ENABLED")) and _spaces_required_set()


def spaces_creds() -> Dict[str, str]:
    """`{bucket,region,endpoint,key,secret}` for the recorder/boto3 presign.
    region default `us-east-1`. Secrets returned for the boto3 client only —
    never logged/echoed in snapshot()."""
    return {
        "bucket": _str_env("AIM_SPACES_BUCKET", ""),
        "region": _str_env("AIM_SPACES_REGION", "").strip() or "us-east-1",
        "endpoint": _str_env("AIM_SPACES_ENDPOINT", ""),
        "key": _str_env("AIM_SPACES_KEY", ""),
        "secret": _str_env("AIM_SPACES_SECRET", ""),
    }


def has_spaces_creds() -> bool:
    """True iff the four required DO Spaces creds are present (no secret echoed)."""
    return _spaces_required_set()


# --------------------------------------------------------------------------- #
# Feature gates
# --------------------------------------------------------------------------- #
def feature_enabled() -> bool:
    """Master mount gate. `FEATURE_AI_MANAGER` (router included iff true)."""
    return _truthy(os.environ.get("FEATURE_AI_MANAGER"))


def is_enabled() -> bool:
    """Runtime enable. `FEATURE_AI_MANAGER` AND `AIM_ENABLED`
    (`AIM_ENABLED=0` = instant rollback / kill switch)."""
    return feature_enabled() and _truthy(os.environ.get("AIM_ENABLED"))


# --------------------------------------------------------------------------- #
# Status snapshot — BOOLEANS ONLY, never a secret (for /status)
# --------------------------------------------------------------------------- #
def snapshot() -> Dict[str, object]:
    """JSON-able config snapshot for /status. NO secrets — booleans + the
    llm_provider id only. Computed fresh from os.environ at call time."""
    return {
        "feature": feature_enabled(),
        "enabled": is_enabled(),
        "llm_provider": llm_provider(),
        "has_service_token": bool(service_token().strip()),
        "pg_configured": pg_configured(),
        "recording_active": recording_active(),
        "has_spaces_creds": has_spaces_creds(),
        "x_auth_set": x_auth_set(),
    }


__all__: List[str] = [
    "llm_provider",
    "llm_model",
    "llm_config",
    "max_pin_attempts",
    "sessions_file",
    "asset_service_base",
    "loopback_base",
    "service_token",
    "aiwf_service_token",
    "transport_configured",
    "x_auth_value",
    "x_auth_set",
    "pg_dsn",
    "pg_configured",
    "recording_active",
    "spaces_creds",
    "has_spaces_creds",
    "feature_enabled",
    "is_enabled",
    "snapshot",
]
