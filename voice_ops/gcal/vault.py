"""voice_ops.gcal.vault — AAD-bound AES-256-GCM refresh-token vault (TRACKED, self-contained).

WHY SELF-CONTAINED: the platform's existing AAD vault lives in
`droplet_work/provider_registry/credentials.py`, which is GITIGNORED. Per the path rule the
tracked deliverable must NOT depend on gitignored code being importable. So this module
re-implements the exact same crypto posture (AES-256-GCM, 12-byte random nonce prepended, the AAD
binding string fed to GCM so a ciphertext is NON-PORTABLE across tenants) as a small, tracked,
standalone module. It reuses the SAME master secret env the rest of the platform uses
(FAMIT_KEYSTORE_SECRET / PROVIDER_KEYSTORE_SECRET) — zero new env, zero new dependency (rides the
`cryptography` package the box already has).

The refresh token (the long-lived Google credential) is the ONLY thing stored at rest, encrypted.
Access tokens are short-lived and re-minted from the refresh token on demand (oauth.refresh) — never
persisted. The encrypted blob lives in a FORCE-RLS table `gcal_credentials` (DDL below) so a tenant
can only ever read its own row (the same RLS rule the booking tables use). The AAD =
tenant_id||"google_calendar"||key_version makes a stolen-and-pasted ciphertext fail to decrypt
under another tenant (InvalidTag) — defence in depth on top of RLS.

SECURITY: never logs / echoes plaintext. decrypt lets InvalidTag propagate (fail-closed, audit a
tamper). Refuses to encrypt an empty token. Raises VaultError (never a silent plaintext fallback)
when crypto / the master secret is unavailable.
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Callable, Optional

log = logging.getLogger("voice_ops.gcal.vault")

_NONCE_LEN = 12  # 96-bit GCM nonce (NIST SP 800-38D), random + prepended to ciphertext.
_PROVIDER = "google_calendar"
_SECRET_ENVS = ("PROVIDER_REGISTRY_KEYSTORE_SECRET", "PROVIDER_KEYSTORE_SECRET",
                "FAMIT_KEYSTORE_SECRET", "GCAL_VAULT_SECRET")


class VaultError(RuntimeError):
    """Crypto/key unavailable, or a key cannot be resolved. NEVER carries plaintext."""


# --------------------------------------------------------------------------- #
# key derivation (the get_key seam — Vault can back this later, signature-compatible).
# --------------------------------------------------------------------------- #
def _interim_get_key(tenant_id: str, provider: str, key_version: int) -> bytes:
    """Derive the 32-byte AES-256 key from the platform master secret. Deterministic so the same
    row decrypts across restarts; the AAD (passed to GCM, not here) makes the ciphertext
    tenant-bound. Raises if no master secret is set (never a weak/empty key for a credential)."""
    secret = ""
    for env in _SECRET_ENVS:
        secret = (os.environ.get(env) or "").strip()
        if secret:
            break
    if not secret:
        raise VaultError(
            "no keystore secret set (FAMIT_KEYSTORE_SECRET / PROVIDER_KEYSTORE_SECRET / "
            "GCAL_VAULT_SECRET) — cannot derive the AES key for the gcal token vault"
        )
    return hashlib.sha256(secret.encode("utf-8")).digest()


DEFAULT_GET_KEY: Callable[[str, str, int], bytes] = _interim_get_key


def compute_aad(tenant_id: str, key_version: int) -> str:
    """The MANDATORY GCM AAD that binds a ciphertext to (tenant, provider, version)."""
    return f"{(tenant_id or '').strip()}|{_PROVIDER}|{int(key_version)}"


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM
    except Exception as exc:  # noqa: BLE001
        raise VaultError("cryptography (AESGCM) unavailable — cannot handle the gcal token") from exc


# --------------------------------------------------------------------------- #
# encrypt / decrypt.
# --------------------------------------------------------------------------- #
def encrypt_token(
    tenant_id: str,
    refresh_token: str,
    key_version: int = 1,
    *,
    get_key: Optional[Callable[[str, str, int], bytes]] = None,
) -> dict:
    """Encrypt a Google refresh token for at-rest storage. Returns
    {ciphertext(bytes), key_aad(str), key_version(int)} ready to UPSERT into gcal_credentials.

    Layout: ciphertext = nonce(12) || AESGCM(token, aad). The AAD binds the blob to
    (tenant, google_calendar, version) -> non-portable. Raises VaultError on empty token /
    missing crypto/key (never returns plaintext on failure)."""
    if not isinstance(refresh_token, str) or refresh_token == "":
        raise VaultError("refusing to encrypt an empty refresh token")
    if not (tenant_id or "").strip():
        raise VaultError("refusing to encrypt without a tenant_id (fail-closed)")
    AESGCM = _aesgcm()
    keyfn = get_key or DEFAULT_GET_KEY
    key = keyfn(tenant_id, _PROVIDER, key_version)
    if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
        raise VaultError("key must be 32 bytes (AES-256)")
    aad = compute_aad(tenant_id, key_version).encode("utf-8")
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(bytes(key)).encrypt(nonce, refresh_token.encode("utf-8"), aad)
    return {
        "ciphertext": nonce + ct,
        "key_aad": compute_aad(tenant_id, key_version),
        "key_version": int(key_version),
    }


def decrypt_token(
    tenant_id: str,
    ciphertext: bytes,
    key_version: int = 1,
    *,
    get_key: Optional[Callable[[str, str, int], bytes]] = None,
) -> str:
    """Decrypt a stored refresh token. Recomputes the AAD from the row's OWN (tenant, version) —
    a ciphertext stolen from tenant A and pasted under tenant B decrypts under AAD(B) != AAD(A)
    and raises InvalidTag (fail-closed, no plaintext). NEVER logs the plaintext."""
    AESGCM = _aesgcm()
    if not (tenant_id or "").strip():
        raise VaultError("decrypt requires a tenant_id (fail-closed)")
    blob = bytes(ciphertext or b"")
    if len(blob) <= _NONCE_LEN:
        raise VaultError("ciphertext too short")
    keyfn = get_key or DEFAULT_GET_KEY
    key = keyfn(tenant_id, _PROVIDER, int(key_version or 1))
    if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
        raise VaultError("key must be 32 bytes (AES-256)")
    aad = compute_aad(tenant_id, int(key_version or 1)).encode("utf-8")
    nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
    pt = AESGCM(bytes(key)).decrypt(nonce, ct, aad)  # InvalidTag propagates (tamper/cross-tenant)
    return pt.decode("utf-8")


def mask(token: str) -> str:
    """Masked form for UI/logs — never the full token. '1//0g…AB12'."""
    t = (token or "").strip()
    if len(t) <= 10:
        return (t[:3] + "…") if t else ""
    return f"{t[:4]}…{t[-4:]}"


# --------------------------------------------------------------------------- #
# Persistence: a FORCE-RLS table for the encrypted refresh tokens. DDL is the
# tracked source of truth (applied by the mount step alongside booking/rls.sql).
# The DB layer is lazy/import-guarded so importing this module pulls no sqlalchemy.
# --------------------------------------------------------------------------- #
RLS_DDL = """
-- voice_ops.gcal refresh-token vault. FORCE-RLS, tenant-isolated (mirrors booking/rls.sql).
CREATE TABLE IF NOT EXISTS gcal_credentials (
    org_id        text NOT NULL,
    provider      text NOT NULL DEFAULT 'google_calendar',
    ciphertext    bytea NOT NULL,
    key_aad       text  NOT NULL,
    key_version   integer NOT NULL DEFAULT 1,
    calendar_id   text  NOT NULL DEFAULT 'primary',
    account_email text  NOT NULL DEFAULT '',
    status        text  NOT NULL DEFAULT 'connected',  -- connected|revoked|error
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, provider)
);
ALTER TABLE gcal_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE gcal_credentials FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS gcal_credentials_rls ON gcal_credentials;
CREATE POLICY gcal_credentials_rls ON gcal_credentials
    USING (org_id = current_setting('app.tenant_id', true)
           OR current_setting('app.is_admin', true) = 'true')
    WITH CHECK (org_id = current_setting('app.tenant_id', true)
           OR current_setting('app.is_admin', true) = 'true');
""".strip()


_NOT_CONFIGURED = {"status": "not_configured", "reason": "postgres_unavailable"}


def _engine():
    """Lazy import-guarded db.engine (the P1 spine). None when absent (CI / no Postgres)."""
    try:
        from db import engine as eng  # type: ignore
        return eng if eng.available() else None
    except Exception:  # noqa: BLE001
        return None


def _text(sql: str):
    from sqlalchemy import text
    return text(sql)


# Injectable store for tests (a dict-backed fake) so we never need Postgres in CI.
_injected_store = None


def set_store_for_tests(s) -> None:
    """Inject a fake store with upsert_blob/read_blob/set_status(org_id,...). None to clear."""
    global _injected_store
    _injected_store = s


def upsert_blob(org_id: str, blob: dict, *, calendar_id: str = "primary",
                account_email: str = "", is_admin: bool = False) -> dict:
    """Persist an encrypted refresh-token blob for a tenant (UPSERT by org_id). Dormant-safe."""
    if _injected_store is not None:
        return _injected_store.upsert_blob(org_id, blob, calendar_id=calendar_id,
                                           account_email=account_email)
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    try:
        with eng.session(tenant_id=org_id, is_admin=is_admin) as s:
            s.execute(_text(
                "INSERT INTO gcal_credentials "
                "(org_id, provider, ciphertext, key_aad, key_version, calendar_id, account_email, "
                " status, created_at, updated_at) "
                "VALUES (:org,'google_calendar',:ct,:aad,:kv,:cal,:em,'connected',now(),now()) "
                "ON CONFLICT (org_id, provider) DO UPDATE SET "
                " ciphertext=:ct, key_aad=:aad, key_version=:kv, calendar_id=:cal, "
                " account_email=:em, status='connected', updated_at=now()"
            ), {"org": org_id, "ct": blob["ciphertext"], "aad": blob["key_aad"],
                "kv": int(blob["key_version"]), "cal": calendar_id or "primary",
                "em": account_email or ""})
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        log.info("gcal vault upsert failed: %r", exc)
        return {"status": "error", "reason": "db_error", "detail": repr(exc)[:160]}


def read_blob(org_id: str, *, is_admin: bool = False) -> Optional[dict]:
    """Read the encrypted blob row for a tenant. Returns the row dict or None. Dormant-safe."""
    if _injected_store is not None:
        return _injected_store.read_blob(org_id)
    eng = _engine()
    if eng is None:
        return None
    try:
        with eng.session(tenant_id=org_id, is_admin=is_admin) as s:
            row = s.execute(_text(
                "SELECT ciphertext, key_version, calendar_id, account_email, status "
                "FROM gcal_credentials WHERE org_id=:org AND provider='google_calendar'"
            ), {"org": org_id}).fetchone()
            if row is None:
                return None
            return {"ciphertext": bytes(row[0]), "key_version": int(row[1]),
                    "calendar_id": row[2], "account_email": row[3], "status": row[4]}
    except Exception as exc:  # noqa: BLE001
        log.info("gcal vault read failed: %r", exc)
        return None


def set_status(org_id: str, status: str, *, is_admin: bool = False) -> dict:
    """Flip the connection status (e.g. 'revoked' when refresh returns invalid_grant). Dormant-safe."""
    if _injected_store is not None:
        return _injected_store.set_status(org_id, status)
    eng = _engine()
    if eng is None:
        return dict(_NOT_CONFIGURED)
    try:
        with eng.session(tenant_id=org_id, is_admin=is_admin) as s:
            s.execute(_text(
                "UPDATE gcal_credentials SET status=:st, updated_at=now() "
                "WHERE org_id=:org AND provider='google_calendar'"
            ), {"org": org_id, "st": status or "error"})
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001
        log.info("gcal vault set_status failed: %r", exc)
        return {"status": "error", "reason": "db_error", "detail": repr(exc)[:160]}
