"""comm.deeplink — the SIGNED, SINGLE-USE Telegram `?start=` consent deep-link (Wave 2).

Spec: communication/COMMUNICATION-MASTER-PLAN.md §4 S5 ("`?start=base64(tenant‖token)` with no
MAC is forgeable. FIX: `base64url(tenant‖nonce‖hmac(SECRET, tenant‖nonce‖phone))`, minted
server-side, single-use (reuse the firewall jti store), short TTL") + WAVE 2 (the deep-link
seeds a CONTACT chat_id and binds it to a tenant+phone, writing a real consent row on /start).

WHAT A DEEP-LINK IS FOR:
  A tenant shares a link `https://t.me/<bot>?start=<payload>`. When the contact taps it, Telegram
  delivers a `/start <payload>` message to the bot's webhook. The webhook calls verify() here:
    * the HMAC proves the tenant + phone were minted by US (not forged by an attacker),
    * the nonce makes it SINGLE-USE (a replay is refused — consume_nonce returns False the 2nd time),
    * the timestamp makes it EXPIRE (a stale link is refused),
  and on success the webhook binds (chat_id <-> tenant, phone) + writes a `telegram_start` consent
  row. This is what makes the post-call CONTACT auto-summary deliverable + legal (the W1 hook
  no-ops `no_destination` until a chat_id is bound — this is how it gets bound).

THE TOKEN (S5):
  payload = base64url( tenant_id || "." || phone || "." || nonce || "." || iat || "." || mac )
  mac     = HMAC-SHA256(signing_secret, tenant_id || phone || nonce || iat) hex (truncated)
  * server-mints only; the contact cannot forge a payload for another tenant/phone (no secret),
  * Telegram constrains the /start payload to <=64 chars of [A-Za-z0-9_-]; base64url(no '=') fits
    that charset, and we keep the phone short (digits) + a short nonce + truncated mac so the
    whole base64url stays within the budget,
  * SINGLE-USE: the nonce is recorded in a small on-disk store on first successful verify; a second
    verify of the same nonce -> reused -> refused (mirrors firewall.py's consumed-jti store).

EARNER / SAFETY LAW: imports NO agent.py / caller.py, ZERO I/O at import, NEVER raises out of
mint()/verify(). The signing secret is the SAME one comm.webhook uses (so there is no new secret).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Optional, Tuple

_log = logging.getLogger("comm.deeplink")

_LABEL = "telegram-start"           # HMAC domain separation (distinct from the webhook label)
_MAC_LEN = 16                       # truncated hex mac (64 bits — single-use+TTL bound it further)
_DEFAULT_TTL_S = 7 * 24 * 3600      # a /start link is valid for 7 days by default

# Telegram constrains the deep-link `/start` payload to 1-64 chars of [A-Za-z0-9_-]. We emit a
# COMPACT positional string `tenant_phone_nonce_iat36_mac` (separator '_', which is in that
# alphabet) — NOT JSON+base64 (too long). Each field is restricted to the safe alphabet so the
# whole payload is a valid Telegram start_parameter without any further encoding.
_SEP = "_"
_MAX_PAYLOAD = 64
_TENANT_RE_SAFE = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _ttl_s() -> int:
    raw = os.environ.get("COMM_DEEPLINK_TTL_S", "")
    try:
        return int(raw) if raw.strip() else _DEFAULT_TTL_S
    except Exception:  # noqa: BLE001
        return _DEFAULT_TTL_S


# ---------------------------------------------------------------------------
# signing secret — the SAME secret comm.webhook derives from (no new secret).
# ---------------------------------------------------------------------------
def _signing_secret() -> str:
    """Resolve the deep-link signing secret. Reuses comm.webhook._signing_secret so the mint
    (panel) and the verify (webhook) always agree. '' when no secret -> mint/verify fail-closed."""
    try:
        from .webhook import _signing_secret as _ws
        s = (_ws() or "").strip()
        if s:
            return s
    except Exception:  # noqa: BLE001
        pass
    return (os.environ.get("COMM_WEBHOOK_SIGNING_SECRET") or "").strip()


def _tenant_token(tenant_id: str) -> str:
    """A Telegram-safe, separator-free token for the tenant inside the compact payload.

    A short tenant id made only of [A-Za-z0-9] is used verbatim (so the link is human-legible
    for the common case, e.g. 'admin'). Anything longer than 12 chars or containing the '_'
    separator / any non-alphanumeric char is replaced by a deterministic 12-hex-char hash of the
    id — the verify side recomputes the SAME token from the PATH tenant, so the binding still
    holds (and a payload minted for tenant B never matches tenant A's recomputed token)."""
    t = str(tenant_id or "")
    if 0 < len(t) <= 12 and all(c in _TENANT_RE_SAFE for c in t):
        return t
    return hashlib.sha256(("tenant||" + t).encode("utf-8")).hexdigest()[:12]


def _mac(tenant_token: str, phone: str, nonce: str, iat: str, secret: str) -> str:
    msg = f"{_LABEL}||{tenant_token}||{phone}||{nonce}||{iat}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:_MAC_LEN]


def _b36(n: int) -> str:
    """Base-36 encode a non-negative int (compact iat). Only [0-9a-z] — Telegram-safe."""
    if n <= 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = []
    while n:
        n, r = divmod(n, 36)
        out.append(digits[r])
    return "".join(reversed(out))


def _unb36(s: str) -> int:
    return int(s, 36)


# ---------------------------------------------------------------------------
# mint — server-side only (the panel "Get my link" button calls this).
# ---------------------------------------------------------------------------
def mint(tenant_id: str, phone: str, *, signing_secret: str = "") -> str:
    """Mint a single-use, signed `?start=` payload binding (tenant_id, phone). Returns the compact
    Telegram-safe payload string (<= 64 chars of [A-Za-z0-9_-], to append after `?start=`), or ""
    on failure. NEVER raises.

    Format: `<tenant_token>_<phone_digits>_<nonce8>_<iat_b36>_<mac16>` (separator '_'). The phone
    is normalised to digits; iat is base-36 (compact); the mac is a 64-bit truncated HMAC. The
    tenant_token is the tenant id (short/alnum) or its 12-hex-char hash — recomputed identically
    on verify from the PATH tenant, so the binding holds without a long id in the link."""
    sec = (signing_secret or _signing_secret()).strip()
    if not sec or not tenant_id:
        return ""
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())[:15]
    nonce = secrets.token_hex(4)        # 8 hex chars (32 bits — one-shot, store-deduped)
    iat = _b36(int(time.time()))
    try:
        ttok = _tenant_token(tenant_id)
        mac = _mac(ttok, digits, nonce, iat, sec)
        payload = _SEP.join((ttok, digits, nonce, iat, mac))
        if len(payload) > _MAX_PAYLOAD:
            # extremely defensive — with a hashed tenant token this is always <= ~ 12+15+8+8+16+4 = 63.
            _log.warning("comm.deeplink.mint payload over budget (%d)", len(payload))
            return ""
        return payload
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.deeplink.mint failed: %r", type(exc).__name__)
        return ""


def link_for(bot_username: str, tenant_id: str, phone: str, *, signing_secret: str = "") -> str:
    """Convenience: the full https://t.me/<bot>?start=<payload> URL. "" when mint fails."""
    payload = mint(tenant_id, phone, signing_secret=signing_secret)
    bot = (bot_username or "").lstrip("@").strip()
    if not payload or not bot:
        return ""
    return f"https://t.me/{bot}?start={payload}"


# ---------------------------------------------------------------------------
# the single-use nonce store — mirrors firewall.py's consumed-jti file (offline-safe).
# ---------------------------------------------------------------------------
def _store_file() -> Optional[Path]:
    """The on-disk consumed-nonce store. Honours COMM_DEEPLINK_STORE (tests point it at a temp
    dir); else the box var dir; else None (in-memory only -> single-use within the process)."""
    p = (os.environ.get("COMM_DEEPLINK_STORE") or "").strip()
    if p:
        return Path(p)
    for cand in ("/opt/famit-agent/var/comm_used_deeplink.json",):
        try:
            d = Path(cand).parent
            if d.exists():
                return Path(cand)
        except Exception:  # noqa: BLE001
            continue
    return None


_MEM_USED: dict = {}                 # in-process fallback when no store file is available


def _read_used() -> dict:
    f = _store_file()
    if f is None:
        return dict(_MEM_USED)
    try:
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}
    return {}


def _write_used(data: dict) -> None:
    f = _store_file()
    if f is None:
        _MEM_USED.clear()
        _MEM_USED.update(data)
        return
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(f)
    except Exception as exc:  # noqa: BLE001
        _log.warning("comm.deeplink._write_used failed: %r", type(exc).__name__)


def _prune(store: dict, now: int) -> dict:
    """Drop consumed nonces older than 2x the TTL (a consumed nonce only needs to outlive its
    own link's expiry to block replay)."""
    horizon = now - 2 * _ttl_s()
    return {k: v for k, v in store.items() if isinstance(v, (int, float)) and v >= horizon}


def _consume_nonce(nonce: str) -> bool:
    """Record `nonce` as consumed. Returns True if THIS call consumed it (first use), False if it
    was ALREADY consumed (a replay). Fail-closed: an empty nonce -> False (refuse)."""
    if not nonce:
        return False
    now = int(time.time())
    store = _prune(_read_used(), now)
    if nonce in store:
        return False
    store[nonce] = now
    _write_used(store)
    return True


# ---------------------------------------------------------------------------
# verify — the webhook calls this on an inbound `/start <payload>`.
# ---------------------------------------------------------------------------
def verify(tenant_id: str, payload: str, *, signing_secret: str = "",
          consume: bool = True) -> Tuple[bool, str, str]:
    """Verify a `?start=` payload against the PATH tenant. Returns (ok, phone, error). NEVER raises.

    Checks, in order (fail-closed at each):
      1. a signing secret exists (else -> ('', 'no_secret')),
      2. the payload decodes to the expected shape,
      3. the embedded tenant matches the PATH tenant (a payload minted for tenant B presented on
         tenant A's webhook -> refused),
      4. the HMAC matches (constant-time) -> proves WE minted it for this (tenant, phone),
      5. it has not expired (iat + ttl >= now),
      6. SINGLE-USE: the nonce has not been consumed (a replay -> refused). When consume=True a
         successful verify consumes the nonce (so the NEXT verify of the same link fails)."""
    sec = (signing_secret or _signing_secret()).strip()
    if not sec or not tenant_id or not payload:
        return False, "", "no_secret" if not sec else "bad_input"
    if len(payload) > _MAX_PAYLOAD:
        return False, "", "bad_payload"
    parts = str(payload).split(_SEP)
    if len(parts) != 5:
        return False, "", "bad_payload"
    ttok, phone, nonce, iat, mac = parts
    if not (ttok and nonce and iat and mac):
        return False, "", "incomplete"
    # (3) tenant binding — the embedded tenant token MUST equal the token recomputed from the
    # PATH tenant (a payload minted for tenant B presented on tenant A's webhook -> mismatch).
    if ttok != _tenant_token(tenant_id):
        return False, "", "tenant_mismatch"
    # (4) HMAC — constant-time.
    try:
        expected = _mac(ttok, phone, nonce, iat, sec)
        if not hmac.compare_digest(mac, expected):
            return False, "", "bad_mac"
    except Exception:  # noqa: BLE001
        return False, "", "mac_error"
    # (5) expiry.
    try:
        if _unb36(iat) + _ttl_s() < int(time.time()):
            return False, "", "expired"
    except Exception:  # noqa: BLE001
        return False, "", "bad_iat"
    # (6) single-use — consume the nonce (replay -> refused).
    if consume:
        if not _consume_nonce(nonce):
            return False, "", "replayed"
    return True, phone, ""
