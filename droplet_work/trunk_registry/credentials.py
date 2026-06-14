"""trunk_registry.credentials — SIP-password crypto, REUSING provider_registry.credentials.

Spec: design/TELEPHONY-INDEPENDENCE-PLAN.md §2.1 / §8 ("REUSE credentials.py [AAD AES-256-GCM]
... import/share, do not rewrite") + §2.2 table 2 (sip_trunk_credentials, AAD =
tenant_id||trunk_id||key_version).

DO NOT REWRITE THE CRYPTO. This module is a thin TRUNK-binding wrapper over the LIVE
provider_registry.credentials (the AAD AES-256-GCM primitive that W2 shipped + verified). It
imports that module and reuses its AESGCM encrypt/decrypt, its interim get_key seam (the SAME
PROVIDER_KEYSTORE_SECRET / FAMIT_KEYSTORE_SECRET), and its `mask` grammar — so:
  * there is ONE crypto implementation on the box (no duplicated, drift-prone AES code),
  * the SIP password is sealed under the trunk-bound AAD (tenant_id||trunk_id||version), so a
    ciphertext copied into another tenant's / another trunk's row decrypts under a DIFFERENT
    AAD -> InvalidTag -> no plaintext leaks (§2.2),
  * when Vault ships, flipping VAULT_BACKEND swaps the get_key seam in ONE place
    (provider_registry.credentials) and BOTH registries inherit it — the §6 seam promise.

The ONLY thing trunk creds change vs provider creds is the AAD field name (trunk_id, not
provider_def_id). We pass that through provider_registry.credentials' positional API (which is
field-name-agnostic — it just concatenates the 2nd id into the AAD), and we re-stamp the
returned dict's key_aad with the trunk-form so the SipTrunkCred binding reads cleanly.

import-safe: if provider_registry is somehow absent on a box, every call raises a clear
CredentialError (NEVER a silent plaintext fallback — that would be a leak). NEVER logs/echoes
a plaintext.
"""
from __future__ import annotations

from typing import Callable, Optional

from .schema import SipTrunkCred  # noqa: F401 (used by callers)


# Re-export the SHARED crypto exception so callers can `except CredentialError`.
try:  # pragma: no cover - the box always has provider_registry alongside this package.
    from provider_registry.credentials import (  # type: ignore
        CredentialError,
        DEFAULT_GET_KEY,
        mask,
    )
    from provider_registry import credentials as _pcred  # type: ignore
    _SHARED_OK = True
except Exception:  # noqa: BLE001
    _SHARED_OK = False

    class CredentialError(RuntimeError):  # type: ignore[no-redef]
        """Raised when the shared provider_registry crypto is unavailable. NEVER carries plaintext."""

    DEFAULT_GET_KEY = None  # type: ignore

    def mask(key: str) -> str:  # type: ignore[no-redef]
        k = (key or "").strip()
        if len(k) <= 10:
            return (k[:3] + "…") if k else ""
        return f"{k[:4]}…{k[-4:]}"


def _require_shared():
    if not _SHARED_OK:
        raise CredentialError(
            "provider_registry.credentials unavailable — cannot handle SIP credentials "
            "(the trunk registry REUSES the provider crypto by design; do not rewrite it)"
        )


# ---------------------------------------------------------------------------
# AAD — the single canonical formula for a TRUNK credential (delegated to schema so there is
# ONE source of truth). Mirrors provider_registry.compute_aad but over the trunk id.
# ---------------------------------------------------------------------------
def compute_aad(tenant_id: str, trunk_id: str, key_version: int) -> str:
    """The MANDATORY GCM AAD binding for a SIP password (§2.2). Delegates to
    SipTrunkCred.expected_aad so encrypt, decrypt, and the dataclass all agree."""
    return SipTrunkCred.expected_aad(tenant_id, trunk_id, key_version)


# ---------------------------------------------------------------------------
# encrypt / decrypt — thin wrappers over the SHARED provider_registry crypto.
# ---------------------------------------------------------------------------
def encrypt_credential(
    tenant_id: str,
    trunk_id: str,
    plaintext: str,
    key_version: int = 1,
    *,
    get_key: Optional[Callable[[str, str, int], bytes]] = None,
) -> dict:
    """Encrypt a SIP digest password for storage. Returns a dict ready to INSERT into
    sip_trunk_credentials: {ciphertext(bytes), key_aad(str), key_version(int)}.

    REUSES provider_registry.credentials.encrypt_credential — the AAD is built from
    (tenant_id, trunk_id, key_version), so the blob is non-portable (§2.2). The shared
    primitive's 2nd positional id is the trunk_id here (it just concatenates it into the AAD);
    we re-stamp key_aad to the trunk-form string for clarity. Raises CredentialError if crypto
    is unavailable (never returns plaintext on failure)."""
    _require_shared()
    enc = _pcred.encrypt_credential(tenant_id, trunk_id, plaintext, key_version, get_key=get_key)
    # Re-stamp the AAD field to the canonical trunk form (the value is identical by construction;
    # provider_registry's expected_aad uses the same tenant||id||version concatenation).
    enc["key_aad"] = compute_aad(tenant_id, trunk_id, key_version)
    return enc


def decrypt_credential(
    cred,
    *,
    get_key: Optional[Callable[[str, str, int], bytes]] = None,
) -> str:
    """Decrypt a stored SIP credential to plaintext. `cred` may be a SipTrunkCred dataclass or a
    dict/row with tenant_id / trunk_id / key_version / ciphertext.

    REUSES provider_registry.credentials.decrypt_credential, which recomputes the AAD from the
    cred's OWN identity fields. Because that primitive reads `provider_def_id` for the 2nd AAD
    component, we present the trunk row to it under a tiny adapter that maps trunk_id ->
    provider_def_id (the AAD STRING is identical: tenant||id||version). A ciphertext stolen from
    tenant/trunk A and pasted under tenant/trunk B decrypts under AAD(B) != AAD(A) -> InvalidTag
    (fail-closed, no plaintext). NEVER logs the plaintext."""
    _require_shared()
    return _pcred.decrypt_credential(_AadAdapter(cred), get_key=get_key)


class _AadAdapter:
    """Presents a trunk credential to provider_registry.credentials.decrypt under the field
    names it expects (it reads tenant_id / provider_def_id / key_version / ciphertext). We map
    trunk_id -> provider_def_id so the AAD string is byte-identical to what encrypt produced
    (tenant_id||trunk_id||key_version). Carries NO plaintext; read-through only."""

    __slots__ = ("_c",)

    def __init__(self, cred):
        self._c = cred

    def _get(self, name, default=None):
        c = self._c
        if isinstance(c, dict):
            return c.get(name, default)
        return getattr(c, name, default)

    # provider_registry.credentials._field reads these attrs / keys:
    @property
    def tenant_id(self):
        return self._get("tenant_id", "")

    @property
    def provider_def_id(self):
        # the 2nd AAD component — for a trunk cred this is the trunk_id.
        return self._get("trunk_id", "") or self._get("provider_def_id", "")

    @property
    def key_version(self):
        return self._get("key_version", 1)

    @property
    def ciphertext(self):
        return self._get("ciphertext")
