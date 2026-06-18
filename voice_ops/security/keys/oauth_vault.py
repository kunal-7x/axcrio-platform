"""voice_ops.security.keys.oauth_vault — VAULTED OAuth / WABA refresh tokens (W23, TRACKED).

THE GAP THIS CLOSES: long-lived OAuth refresh tokens (Google Calendar, Meta/WhatsApp WABA, ad
platforms) are the crown jewels — a refresh token mints access tokens indefinitely. Today such
tokens risk landing in `var/*.json` plaintext on the box. W23 mandates they live ENCRYPTED, AAD-bound
to (tenant, provider), exactly like the provider-registry API keys — NEVER as a plaintext file.

REUSE, NOT FORK: this module is a thin domain wrapper over the SAME AAD AES-256-GCM vault the config
layer already ships (`voice_ops.config.vault`), which itself mirrors the live
`droplet_work/provider_registry/credentials.py` posture byte-for-byte. So a token vaulted here is
encrypted with the identical crypto + AAD the platform already trusts — a true reuse of the W4 vault.
The vault import is LAZY (inside the call) so `import voice_ops.security.keys.oauth_vault` stays
crypto/droplet-free; the cryptography dep is only touched when you actually seal/open a token.

AAD BINDING: the ciphertext is bound to (tenant_id, "oauth:<provider>", version). A refresh-token
blob stolen from tenant A and pasted under tenant B fails to decrypt (InvalidTag) — the same
cross-tenant non-portability the provider keys get, on top of FORCE-RLS at the row.

WHAT THIS MODULE DOES vs DOESN'T:
  * DOES: seal a refresh token -> an at-rest record {fingerprint, ciphertext, key_aad, version,
    provider, label, sealed_at}; open it back at use-time; mask/fingerprint for UI/audit.
  * DOESN'T: choose WHERE the record persists. That is the caller's FORCE-RLS store (the same
    `config_state` / vault row pattern `voice_ops.config.keys` uses). This module is the seal/open +
    record-shape contract, so it has ZERO DB/droplet import and is fully unit-testable with a mock
    master secret.

SECURITY: refusing to seal an empty token; plaintext NEVER in the record, a log, a repr, or an event;
open() lets InvalidTag propagate (fail-closed tamper/cross-tenant). The record is SAFE to log.

IMPORT ISOLATION: stdlib + a LAZY `voice_ops.config.vault` (which itself is stdlib + cryptography).
ZERO droplet/caller/auth import.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

log = logging.getLogger("voice_ops.security.keys.oauth_vault")

# the at-rest record's provider key is namespaced so an OAuth token can't be confused with (or
# decrypt under the AAD of) a provider API key for the same provider string.
_PROVIDER_NS = "oauth"


class OAuthVaultError(RuntimeError):
    """Seal/open failed (empty token, missing tenant/provider, crypto/master unavailable). NEVER
    carries the token plaintext."""


def _provider_aad_name(provider: str) -> str:
    """The vault `provider` field for an OAuth token — namespaced so it never collides with the API-key
    AAD for the same provider (so an API-key ciphertext can't be opened as a refresh token)."""
    return f"{_PROVIDER_NS}:{(provider or '').strip()}"


@dataclass(frozen=True)
class VaultedToken:
    """The at-rest record for a sealed OAuth/WABA refresh token. SAFE to persist + log: holds ONLY
    ciphertext + fingerprint + AAD + metadata, NEVER the plaintext. `ciphertext` is bytes ready to
    store in a bytea/base64 column."""

    provider: str
    fingerprint: str
    ciphertext: bytes = field(repr=False)   # nonce||AESGCM(token, aad) — opaque, off repr
    key_aad: str = ""
    key_version: int = 1
    masked: str = ""
    label: str = ""
    sealed_at: int = 0

    def __repr__(self) -> str:  # safe-to-log: no ciphertext, no plaintext
        return (
            f"VaultedToken(provider={self.provider!r}, fp={self.fingerprint}, "
            f"masked={self.masked!r}, v={self.key_version}, aad={self.key_aad!r})"
        )

    def to_record(self) -> dict:
        """The dict to UPSERT into the caller's FORCE-RLS store. ciphertext is hex so it survives a
        JSON/text column; NEVER includes the plaintext."""
        return {
            "provider": self.provider,
            "fingerprint": self.fingerprint,
            "ciphertext_hex": self.ciphertext.hex(),
            "key_aad": self.key_aad,
            "key_version": self.key_version,
            "masked": self.masked,
            "label": self.label,
            "sealed_at": self.sealed_at,
        }


def seal_oauth_token(
    tenant_id: str,
    provider: str,
    refresh_token: str,
    *,
    label: str = "",
    key_version: int = 1,
    get_key: Optional[Callable[[str, str, int], bytes]] = None,
) -> VaultedToken:
    """Encrypt an OAuth/WABA refresh token for at-rest storage, AAD-bound to (tenant, oauth:provider,
    version). Returns a VaultedToken record. Raises OAuthVaultError on empty token / missing crypto or
    master secret — NEVER returns plaintext on failure, NEVER writes a plaintext file."""
    if not isinstance(refresh_token, str) or refresh_token == "":
        raise OAuthVaultError("refusing to seal an empty OAuth token")
    if not (tenant_id or "").strip():
        raise OAuthVaultError("refusing to seal without a tenant_id (fail-closed)")
    if not (provider or "").strip():
        raise OAuthVaultError("refusing to seal without a provider (fail-closed)")
    try:
        from voice_ops.config import vault  # LAZY — keeps this module crypto/import-light
    except Exception as exc:  # noqa: BLE001
        raise OAuthVaultError("config vault unavailable — cannot seal OAuth token") from exc
    pname = _provider_aad_name(provider)
    try:
        blob = vault.encrypt_secret(tenant_id, pname, refresh_token, key_version, get_key=get_key)
    except vault.VaultError as exc:
        raise OAuthVaultError(str(exc)) from exc
    return VaultedToken(
        provider=(provider or "").strip(),
        fingerprint=vault.fingerprint(refresh_token),
        ciphertext=blob["ciphertext"],
        key_aad=blob["key_aad"],
        key_version=int(blob["key_version"]),
        masked=vault.mask(refresh_token),
        label=(label or "").strip(),
        sealed_at=int(time.time()),
    )


def open_oauth_token(
    tenant_id: str,
    provider: str,
    ciphertext: bytes,
    *,
    key_version: int = 1,
    get_key: Optional[Callable[[str, str, int], bytes]] = None,
) -> str:
    """Decrypt a sealed OAuth/WABA refresh token at use-time. Recomputes the AAD from (tenant,
    oauth:provider, version) — a blob from another tenant raises (InvalidTag -> OAuthVaultError),
    fail-closed. This is the ONLY place the plaintext is ever materialised; NEVER log the result."""
    if not (tenant_id or "").strip():
        raise OAuthVaultError("open requires a tenant_id (fail-closed)")
    if not (provider or "").strip():
        raise OAuthVaultError("open requires a provider (fail-closed)")
    try:
        from voice_ops.config import vault  # LAZY
    except Exception as exc:  # noqa: BLE001
        raise OAuthVaultError("config vault unavailable — cannot open OAuth token") from exc
    pname = _provider_aad_name(provider)
    try:
        return vault.decrypt_secret(tenant_id, pname, ciphertext, int(key_version or 1), get_key=get_key)
    except vault.VaultError as exc:
        raise OAuthVaultError(str(exc)) from exc
    except Exception as exc:  # InvalidTag (tamper / cross-tenant) — fail closed, never plaintext
        raise OAuthVaultError("OAuth token failed to decrypt (tamper or cross-tenant AAD mismatch)") from exc


def open_record(
    tenant_id: str,
    record: dict,
    *,
    get_key: Optional[Callable[[str, str, int], bytes]] = None,
) -> str:
    """Convenience: open from a stored `to_record()` dict (hex ciphertext)."""
    try:
        ct = bytes.fromhex(record["ciphertext_hex"])
    except Exception as exc:  # noqa: BLE001
        raise OAuthVaultError("record missing/invalid ciphertext_hex") from exc
    return open_oauth_token(
        tenant_id,
        record.get("provider", ""),
        ct,
        key_version=int(record.get("key_version", 1) or 1),
        get_key=get_key,
    )
