"""voice_ops.gcal — Google Calendar OAuth + async event sync (TRACKED, W11 founder bug 3).

The vendor connects their Google Calendar ONCE from the panel; thereafter AI/manual bookings
create REAL calendar events (lead name/phone/campaign/notes/status), and reschedule/cancel
update/delete them — all ASYNC so the call is NEVER blocked.

Modules:
  - config   GCalConfig — flags + OAuth client + endpoints (default OFF / dormant).
  - vault    AAD-bound AES-256-GCM refresh-token vault (self-contained, tracked; does NOT depend
             on the gitignored provider_registry) + the FORCE-RLS gcal_credentials table DDL.
  - oauth    GoogleOAuth — server-side flow: authorization_url -> exchange_code (store encrypted
             refresh token) -> refresh (mint access token; flip to 'revoked' on invalid_grant =
             reconnect-on-expiry).
  - sync     CalendarSync — on_booked / on_rescheduled / on_cancelled async hooks the
             BookingService fires fire-and-forget.

IMPORT ISOLATION: `import voice_ops.gcal` pulls ZERO droplet_work, ZERO google SDK, ZERO redis,
ZERO sqlalchemy at module load. Crypto rides the `cryptography` package already on the box; HTTP
is stdlib urllib. Inert until BOOKING_CALENDAR_SYNC=1 + the OAuth client id/secret are set.
"""
from __future__ import annotations

from . import oauth, sync, vault
from .config import GCalConfig
from .oauth import GoogleOAuth
from .sync import CalendarSync
from .vault import VaultError, decrypt_token, encrypt_token, mask

__all__ = [
    "GCalConfig",
    "GoogleOAuth",
    "CalendarSync",
    "oauth",
    "sync",
    "vault",
    "encrypt_token",
    "decrypt_token",
    "mask",
    "VaultError",
]
