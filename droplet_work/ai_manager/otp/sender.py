"""ai_manager.otp.sender — ownership-OTP send hop for number registration (spec §L).

DORMANT-BY-DEFAULT: there is NO OTP provider wired on this box, so `send()` always returns
`{"status":"not_configured","sent":False}`. It NEVER sends an OTP blind and NEVER raises — the
registration flow (endpoints.register_number) assigns the return straight to `res["otp"]`, and a
freshly registered number simply stays `verified=False` until /verify. When a provider IS later
configured (an `AIM_OTP_PROVIDER` env + the matching transport), this is the single seam to light
up; the gate is read at CALL TIME (import does ZERO I/O, reads no env, NEVER raises).

NO raw OTP code is ever stored, logged, echoed, or returned by this module.
"""
from __future__ import annotations

import os
from typing import Optional


def _provider() -> str:
    """The configured OTP provider name (call-time env read). Blank/absent => dormant.

    No provider is wired on this box, so this resolves to "" and `send()` stays dormant. NEVER raises.
    """
    try:
        return (os.environ.get("AIM_OTP_PROVIDER", "") or "").strip().lower()
    except Exception:  # noqa: BLE001
        return ""


def is_configured() -> bool:
    """True only when an OTP provider env is set. Dormant (False) on this box. NEVER raises."""
    return bool(_provider())


def send(phone: str, *, code: Optional[str] = None) -> dict:
    """Send an ownership OTP to `phone`. DORMANT on this box -> `{"status":"not_configured","sent":False}`.

    NEVER sends blind (no provider => no-op), NEVER raises, NEVER logs/echoes/returns the raw `code`.
    Fail-closed on a blank phone. The return is assigned to `res["otp"]` by endpoints.register_number.
    """
    try:
        if not (phone or "").strip():
            return {"status": "invalid_phone", "sent": False}
        provider = _provider()
        if not provider:
            # No OTP provider configured -> dormant. The number stays verified=False until /verify.
            return {"status": "not_configured", "sent": False}
        # A provider name is set but no live transport is wired on this box yet -> still a no-op,
        # never a blind send. (This is the seam a future provider integration lights up.)
        return {"status": "not_configured", "sent": False, "provider": provider}
    except Exception:  # noqa: BLE001
        return {"status": "not_configured", "sent": False}
