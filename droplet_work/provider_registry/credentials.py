"""provider_registry.credentials — AAD-bound AES-256-GCM credential crypto (W2).

Spec: design/PROVIDER-FRAMEWORK-PLAN.md §6 (the encryption-at-rest + the get_secret seam) +
§5 table 2 (provider_credentials) + §2d (AAD = tenant_id||provider_def_id||version MANDATORY) +
§13 R5 (interim Fernet, Vault-shaped so the swap is a backend change).

WHAT THIS DOES:
  * `encrypt_credential(tenant_id, provider_def_id, plaintext, key_version, get_key=None)`
    -> ProviderCred-ready dict {ciphertext, key_aad, key_version, ...}. AES-256-GCM with a
    12-byte random nonce PREPENDED to the ciphertext; the AAD (the §2d binding string) is
    fed to GCM so the ciphertext is NON-PORTABLE: copying it into another tenant's row
    changes the AAD -> decrypt fails with InvalidTag (no plaintext ever leaks).
  * `decrypt_credential(cred, get_key=None)` -> plaintext str. Recomputes the AAD from the
    cred's OWN (tenant_id, provider_def_id, key_version) — so a row whose ciphertext was
    stolen from tenant A and pasted under tenant B will have AAD B != AAD A -> InvalidTag.
  * `mask(key)` -> 'gsk_…AB12' (reuses the live key_store mask grammar; never echoes full).

THE get_secret SEAM (§6, the clean Vault swap point): the 32-byte AES key is fetched through
an injectable `get_key()` callable. The DEFAULT seam derives the key from the SAME
PROVIDER_KEYSTORE_SECRET / FAMIT_KEYSTORE_SECRET that llm_router/key_store.py already uses
(sha256 -> 32 bytes), so on the box we reuse the existing master secret with ZERO new env and
ZERO new dependency. When Vault ships, the consumer flips VAULT_BACKEND and `get_key` routes
to Vault — credentials.py is unchanged (that is the §6 seam promise).

CRYPTO CHOICE: AES-256-GCM directly (via `cryptography.hazmat`) rather than Fernet, because
Fernet does NOT support Additional Authenticated Data, and the AAD binding is MANDATORY here
(§2d). We still ride the SAME `cryptography` package the box already has (key_store.py:48) —
no new dependency. If `cryptography` is somehow absent, encrypt/decrypt raise a clear
CredentialError (NEVER a silent plaintext fallback for a secret — that would be a leak).

NEVER logs/echoes a plaintext. NEVER persists plaintext on any object. Returns the plaintext
transiently to the immediate caller (registry) only.
"""
from __future__ import annotations

import hashlib
import os
from typing import Callable, Optional

from .schema import GLOBAL_TENANT, ProviderCred  # noqa: F401 (ProviderCred used by callers)

# 96-bit nonce per NIST SP 800-38D for GCM (random nonce, prepended to ciphertext).
_NONCE_LEN = 12
# The env secrets we derive the interim AES key from (reuse the box's existing master).
_SECRET_ENVS = ("PROVIDER_REGISTRY_KEYSTORE_SECRET", "PROVIDER_KEYSTORE_SECRET",
                "FAMIT_KEYSTORE_SECRET")


class CredentialError(RuntimeError):
    """Raised when crypto is unavailable or a key cannot be resolved. NEVER carries plaintext."""


# ---------------------------------------------------------------------------
# The interim get_key seam (Vault backs this later; §6).
# ---------------------------------------------------------------------------
def _interim_get_key(tenant_id: str, provider_def_id: str, key_version: int) -> bytes:
    """Derive the 32-byte AES-256 key for the interim (local-Fernet-era) backend.

    Reuses the box's existing master secret (the SAME one key_store.py uses). The key is
    derived deterministically so the same row decrypts across restarts; the AAD (passed to
    GCM, not here) is what makes the ciphertext tenant-bound. Raises if no secret is set
    (we never fall back to a weak/empty key for a credential)."""
    secret = ""
    for env in _SECRET_ENVS:
        secret = (os.environ.get(env) or "").strip()
        if secret:
            break
    if not secret:
        raise CredentialError(
            "no keystore secret set (PROVIDER_KEYSTORE_SECRET / FAMIT_KEYSTORE_SECRET) — "
            "cannot derive the interim AES key"
        )
    # sha256(secret) = a stable 32-byte key (same derivation family as key_store.py:52).
    return hashlib.sha256(secret.encode("utf-8")).digest()


# The default seam: a key-deriver matching the get_secret() signature shape. A test or the
# Vault migration injects a different callable.
DEFAULT_GET_KEY: Callable[[str, str, int], bytes] = _interim_get_key


# ---------------------------------------------------------------------------
# AAD — the single canonical formula (delegated to schema so there is ONE source of truth).
# ---------------------------------------------------------------------------
def compute_aad(tenant_id: str, provider_def_id: str, key_version: int) -> str:
    """The MANDATORY GCM AAD (§2d). Delegates to ProviderCred.expected_aad so encrypt,
    decrypt, and the dataclass all agree on the one formula."""
    return ProviderCred.expected_aad(tenant_id, provider_def_id, key_version)


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM
    except Exception as exc:  # noqa: BLE001
        raise CredentialError("cryptography (AESGCM) unavailable — cannot handle credentials") from exc


# ---------------------------------------------------------------------------
# encrypt / decrypt.
# ---------------------------------------------------------------------------
def encrypt_credential(
    tenant_id: str,
    provider_def_id: str,
    plaintext: str,
    key_version: int = 1,
    *,
    get_key: Optional[Callable[[str, str, int], bytes]] = None,
) -> dict:
    """Encrypt a provider API key for storage. Returns a dict ready to INSERT into
    provider_credentials: {ciphertext(bytes), key_aad(str), key_version(int)}.

    Layout: ciphertext = nonce(12) || AESGCM(plaintext, aad). The AAD binds the blob to
    (tenant_id, provider_def_id, key_version) — making it non-portable (§2d). Raises
    CredentialError if crypto/key is unavailable (never returns plaintext on failure)."""
    if not isinstance(plaintext, str) or plaintext == "":
        raise CredentialError("refusing to encrypt an empty credential")
    AESGCM = _aesgcm()
    keyfn = get_key or DEFAULT_GET_KEY
    key = keyfn(tenant_id, provider_def_id, key_version)
    if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
        raise CredentialError("interim key must be 32 bytes (AES-256)")
    aad = compute_aad(tenant_id, provider_def_id, key_version).encode("utf-8")
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(bytes(key)).encrypt(nonce, plaintext.encode("utf-8"), aad)
    return {
        "ciphertext": nonce + ct,
        "key_aad": compute_aad(tenant_id, provider_def_id, key_version),
        "key_version": int(key_version),
    }


def decrypt_credential(
    cred,
    *,
    get_key: Optional[Callable[[str, str, int], bytes]] = None,
) -> str:
    """Decrypt a stored credential to plaintext. `cred` may be a ProviderCred dataclass or
    a dict/row with tenant_id/provider_def_id/key_version/ciphertext.

    Recomputes the AAD from the cred's OWN identity fields — so a ciphertext stolen from
    tenant A and pasted into tenant B's row decrypts under AAD(B) != AAD(A) and raises
    InvalidTag (from `cryptography`). We deliberately let InvalidTag propagate so the caller
    audits a tamper attempt; NO plaintext is produced. NEVER logs the plaintext."""
    AESGCM = _aesgcm()
    tenant_id = _field(cred, "tenant_id")
    provider_def_id = _field(cred, "provider_def_id")
    key_version = _field(cred, "key_version", 1)
    blob = _field(cred, "ciphertext")
    if blob is None:
        raise CredentialError("credential has no ciphertext")
    blob = bytes(blob)
    if len(blob) <= _NONCE_LEN:
        raise CredentialError("ciphertext too short")
    keyfn = get_key or DEFAULT_GET_KEY
    key = keyfn(tenant_id, provider_def_id, int(key_version or 1))
    if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
        raise CredentialError("interim key must be 32 bytes (AES-256)")
    aad = compute_aad(tenant_id, provider_def_id, int(key_version or 1)).encode("utf-8")
    nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
    # InvalidTag (cross-tenant copy / tamper / wrong key) propagates — fail-closed, no plaintext.
    pt = AESGCM(bytes(key)).decrypt(nonce, ct, aad)
    return pt.decode("utf-8")


def _field(cred, name: str, default=None):
    """Read a field from either a dataclass/object or a mapping/row."""
    if isinstance(cred, dict):
        return cred.get(name, default)
    return getattr(cred, name, default)


# ---------------------------------------------------------------------------
# mask — never echo the full secret (reuses the live key_store grammar).
# ---------------------------------------------------------------------------
def mask(key: str) -> str:
    """'gsk_…AB12' — the masked form the UI/logs may see. Mirrors key_store.mask."""
    k = (key or "").strip()
    if len(k) <= 10:
        return (k[:3] + "…") if k else ""
    return f"{k[:4]}…{k[-4:]}"
