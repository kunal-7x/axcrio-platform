"""voice_ops.gcal.config — GCalConfig: Google Calendar OAuth + sync knobs.

Default OFF / dormant everywhere. The whole gcal package is inert until the founder sets the
Google OAuth client id/secret AND flips BOOKING_CALENDAR_SYNC=1. Until then OAuth URL minting,
token exchange, and event sync all degrade to a benign "not_configured" — bookings still persist
in Postgres regardless (the calendar is an ENRICHMENT, never a dependency).

ENV (box .env):
  BOOKING_CALENDAR_SYNC        "1" to arm Google Calendar sync          (default OFF)
  GOOGLE_CALENDAR_CLIENT_ID    OAuth 2.0 client id     (founder provides at go-live)
  GOOGLE_CALENDAR_CLIENT_SECRET OAuth 2.0 client secret (founder provides at go-live)
  GOOGLE_CALENDAR_REDIRECT_URI server-side callback URL (default https://panel.famit.in/api/gcal/callback)
  GOOGLE_CALENDAR_SCOPE        OAuth scope             (default calendar)
  GCAL_TOKEN_KEY_VERSION       AES key version for the refresh-token vault (default 1)

The refresh-token vault key is derived from the SAME master secret the rest of the platform uses
(FAMIT_KEYSTORE_SECRET / PROVIDER_KEYSTORE_SECRET) — zero new env, zero new dependency. See vault.py.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

_TRUE = ("1", "true", "True", "yes", "on")

_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_CAL_API = "https://www.googleapis.com/calendar/v3"
_DEFAULT_SCOPE = "https://www.googleapis.com/auth/calendar"
_DEFAULT_REDIRECT = "https://panel.famit.in/api/gcal/callback"


def _flag(name: str, default: str = "0") -> bool:
    return (os.getenv(name, default) or "").strip() in _TRUE


@dataclass(frozen=True)
class GCalConfig:
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = _DEFAULT_REDIRECT
    scope: str = _DEFAULT_SCOPE
    key_version: int = 1
    auth_endpoint: str = _AUTH_ENDPOINT
    token_endpoint: str = _TOKEN_ENDPOINT
    api_base: str = _CAL_API

    @classmethod
    def from_env(cls) -> "GCalConfig":
        return cls(
            enabled=_flag("BOOKING_CALENDAR_SYNC"),
            client_id=(os.getenv("GOOGLE_CALENDAR_CLIENT_ID") or "").strip(),
            client_secret=(os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET") or "").strip(),
            redirect_uri=(os.getenv("GOOGLE_CALENDAR_REDIRECT_URI") or _DEFAULT_REDIRECT).strip(),
            scope=(os.getenv("GOOGLE_CALENDAR_SCOPE") or _DEFAULT_SCOPE).strip(),
            key_version=int(os.getenv("GCAL_TOKEN_KEY_VERSION", "1") or "1"),
        )

    @property
    def client_ready(self) -> bool:
        """True when the OAuth app credentials are present (needed to mint URLs / exchange code)."""
        return bool(self.client_id and self.client_secret)

    @property
    def configured(self) -> bool:
        """True only when sync is enabled AND the OAuth client is wired."""
        return bool(self.enabled and self.client_ready)

    def status(self) -> dict:
        """Redacted snapshot — booleans only. Safe to return from an API / log."""
        return {
            "calendar_sync_enabled": self.enabled,
            "google_client_present": self.client_ready,
            "configured": self.configured,
            "redirect_uri": self.redirect_uri,
            "scope": self.scope,
        }
