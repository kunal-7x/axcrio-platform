"""voice_ops.config.vault — AAD-bound AES-256-GCM secret vault (TRACKED, self-contained).

WHY SELF-CONTAINED: the platform's existing AAD vault lives in
`droplet_work/provider_registry/credentials.py`, which is GITIGNORED. Per the path rule a TRACKED
deliverable must NOT depend on gitignored code being importable. So this module re-implements the
exact same crypto posture (AES-256-GCM, 12-byte random nonce prepended, the AAD binding string fed
to GCM so a ciphertext is NON-PORTABLE across tenants) as a small, tracked, standalone module —
identical in shape to `voice_ops/gcal/vault.py`. It reuses the SAME master-secret envs the rest of
the platform uses (PROVIDER_REGISTRY_KEYSTORE_SECRET / PROVIDER_KEYSTORE_SECRET /
FAMIT_KEYSTORE_SECRET) — zero new env, zero new dependency (rides the `cryptography` package the box
already has). When the live `provider_registry` vault IS importable on the box, the SAME ciphertexts
decrypt because the key derivation + AAD are byte-identical — so this is a true reuse of the W4 vault,
not a fork.

EVERY provider API key / WhatsApp token / telephony secret stored by the config layer is encrypted
through THIS module. Plaintext NEVER touches disk, a DB row, a log line, or an event payload.

The AAD = tenant_id || provider || key_version makes a stolen-and-pasted ciphertext fail to decrypt
under another tenant (InvalidTag) — defence in depth on top of the FORCE-RLS table.

SECURITY: never logs/echoes plaintext. decrypt lets InvalidTag propagate (fail-closed, audit a
tamper). Refuses to encrypt an empty secret. Raises VaultError (never a silent plaintext fallback)
when crypto / the master secret is unavailable.
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import Callable, Optional

log = logging.getLogger("voice_ops.config.vault")

_NONCE_LEN = 12  # 96-bit GCM nonce (NIST SP 800-38D), random + prepended to ciphertext.
# Same precedence the gcal vault + provider_registry credentials use.
_SECRET_ENVS = (
    "PROVIDER_REGISTRY_KEYSTORE_SECRET",
    "PROVIDER_KEYSTORE_SECRET",
    "FAMIT_KEYSTORE_SECRET",
    "CONFIG_VAULT_SECRET",
)


class VaultError(RuntimeError):
    """Crypto/key unavailable, or a key cannot be resolved. NEVER carries plaintext."""


# --------------------------------------------------------------------------- #
# key derivation (the get_key seam — a real KMS/Vault can back this later,
# signature-compatible; exactly the provider_registry DEFAULT_GET_KEY seam).
# --------------------------------------------------------------------------- #
def _interim_get_key(tenant_id: str, provider: str, key_version: int) -> bytes:
    """Derive the 32-byte AES-256 key from the platform master secret. Deterministic so the same
    row decrypts across restarts; the AAD (passed to GCM, not here) makes the ciphertext
    tenant+provider-bound. Raises if no master secret is set (never a weak/empty key for a secret)."""
    secret = ""
    for env in _SECRET_ENVS:
        secret = (os.environ.get(env) or "").strip()
        if secret:
            break
    if not secret:
        raise VaultError(
            "no keystore secret set (PROVIDER_REGISTRY_KEYSTORE_SECRET / PROVIDER_KEYSTORE_SECRET / "
            "FAMIT_KEYSTORE_SECRET / CONFIG_VAULT_SECRET) — cannot derive the AES key for the config vault"
        )
    return hashlib.sha256(secret.encode("utf-8")).digest()


DEFAULT_GET_KEY: Callable[[str, str, int], bytes] = _interim_get_key


def compute_aad(tenant_id: str, provider: str, key_version: int) -> str:
    """The MANDATORY GCM AAD that binds a ciphertext to (tenant, provider, version)."""
    return f"{(tenant_id or '').strip()}|{(provider or '').strip()}|{int(key_version)}"


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM
    except Exception as exc:  # noqa: BLE001
        raise VaultError("cryptography (AESGCM) unavailable — cannot handle the config secret") from exc


# --------------------------------------------------------------------------- #
# encrypt / decrypt.
# --------------------------------------------------------------------------- #
def encrypt_secret(
    tenant_id: str,
    provider: str,
    secret: str,
    key_version: int = 1,
    *,
    get_key: Optional[Callable[[str, str, int], bytes]] = None,
) -> dict:
    """Encrypt a provider secret (API key / token) for at-rest storage. Returns
    {ciphertext(bytes), key_aad(str), key_version(int)} ready to UPSERT.

    Layout: ciphertext = nonce(12) || AESGCM(secret, aad). The AAD binds the blob to
    (tenant, provider, version) -> non-portable. Raises VaultError on empty secret /
    missing crypto/key (never returns plaintext on failure)."""
    if not isinstance(secret, str) or secret == "":
        raise VaultError("refusing to encrypt an empty secret")
    if not (tenant_id or "").strip():
        raise VaultError("refusing to encrypt without a tenant_id (fail-closed)")
    if not (provider or "").strip():
        raise VaultError("refusing to encrypt without a provider (fail-closed)")
    AESGCM = _aesgcm()
    keyfn = get_key or DEFAULT_GET_KEY
    key = keyfn(tenant_id, provider, key_version)
    if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
        raise VaultError("key must be 32 bytes (AES-256)")
    aad = compute_aad(tenant_id, provider, key_version).encode("utf-8")
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(bytes(key)).encrypt(nonce, secret.encode("utf-8"), aad)
    return {
        "ciphertext": nonce + ct,
        "key_aad": compute_aad(tenant_id, provider, key_version),
        "key_version": int(key_version),
    }


def decrypt_secret(
    tenant_id: str,
    provider: str,
    ciphertext: bytes,
    key_version: int = 1,
    *,
    get_key: Optional[Callable[[str, str, int], bytes]] = None,
) -> str:
    """Decrypt a stored secret. Recomputes the AAD from the row's OWN (tenant, provider, version) —
    a ciphertext stolen from tenant A and pasted under tenant B decrypts under AAD(B) != AAD(A)
    and raises InvalidTag (fail-closed, no plaintext). NEVER logs the plaintext."""
    AESGCM = _aesgcm()
    if not (tenant_id or "").strip():
        raise VaultError("decrypt requires a tenant_id (fail-closed)")
    if not (provider or "").strip():
        raise VaultError("decrypt requires a provider (fail-closed)")
    blob = bytes(ciphertext or b"")
    if len(blob) <= _NONCE_LEN:
        raise VaultError("ciphertext too short")
    keyfn = get_key or DEFAULT_GET_KEY
    key = keyfn(tenant_id, provider, int(key_version or 1))
    if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
        raise VaultError("key must be 32 bytes (AES-256)")
    aad = compute_aad(tenant_id, provider, int(key_version or 1)).encode("utf-8")
    nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
    pt = AESGCM(bytes(key)).decrypt(nonce, ct, aad)  # InvalidTag propagates (tamper/cross-tenant)
    return pt.decode("utf-8")


def mask(secret: str) -> str:
    """Masked form for UI/logs — never the full secret. 'gsk_…AB12'."""
    t = (secret or "").strip()
    if len(t) <= 10:
        return (t[:3] + "…") if t else ""
    return f"{t[:4]}…{t[-4:]}"


def fingerprint(secret: str) -> str:
    """A stable, NON-reversible 12-hex id for a secret — lets the UI/health pool refer to a key
    ('which key is unhealthy?') and dedupe duplicates WITHOUT ever holding the plaintext. SHA-256
    truncated; salted with the provider-agnostic domain tag so a fingerprint is not a rainbow target."""
    t = (secret or "").strip()
    if not t:
        return ""
    return hashlib.sha256(("famit-keyfp|" + t).encode("utf-8")).hexdigest()[:12]
