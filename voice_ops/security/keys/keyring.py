"""voice_ops.security.keys.keyring — PURPOSE-SEPARATED signing keys (W23, TRACKED, droplet-free).

THE CORE W23 GUARANTEE: from the SAME master secret, derive a DISTINCT key per `KeyPurpose` via
HKDF-SHA256 with the purpose label as the domain-separation `info`. Because the labels differ, the
derived bytes differ; because HKDF is one-way, holding the access-key bytes reveals NOTHING about the
step-up-key bytes. A token signed under `JWT_ACCESS` therefore CANNOT be verified under `STEP_UP` —
which is exactly the containment the founder asked for ("a JWT key can't forge a step-up token").

WHY DERIVE RATHER THAN STORE 6 SECRETS: the box already has ONE master secret distribution channel
(`var/secret` / the keystore env). Forcing the operator to provision and rotate six independent
files would be operationally fragile and is unnecessary — HKDF domain separation gives independent
keys from one root, and per-purpose rotation is achieved by bumping a per-purpose `version` (folded
into `info`) WITHOUT touching the other purposes. The master can later be split further or backed by
a real KMS at the `get_master` seam (signature-compatible, exactly the vault DEFAULT_GET_KEY pattern).

MIGRATION (the honest two-leg, mirrors auth.py / firewall.py today):
  * Today every family uses the raw master directly (`_SECRET`). This module's
    `legacy_compat_key(JWT_ACCESS)` returns the RAW master so a drop-in swap verifies EXISTING tokens
    during transition. The patch DOC flips each signer to `signing_key(purpose)` one family at a time.
  * Once flipped, each family is on its own derived key; a step-up-key leak no longer forges access.

SECURITY POSTURE:
  * derived key bytes NEVER logged / repr'd / returned in the clear except via the explicit signer API
    (`sign`/`verify` take the purpose, not raw bytes — callers never handle key material).
  * `sign`/`verify` are HMAC-SHA256 (the same primitive auth.py/firewall.py HS256 + the legacy panel
    token already use) so the migration is byte-shape-compatible.
  * verify is constant-time (`hmac.compare_digest`); a wrong-purpose or tampered MAC fails closed.
  * no master secret -> KeyError-free `KeyManagerError` (never a weak/empty fallback key).

IMPORT ISOLATION: stdlib only (hashlib, hmac, os, base64). ZERO droplet/caller/auth/firewall import.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from dataclasses import dataclass
from typing import Callable, Optional

from .purpose import KeyPurpose

log = logging.getLogger("voice_ops.security.keys.keyring")

# Same master-secret env precedence the rest of voice_ops uses, plus the platform's `var/secret`
# loader env. The first non-empty wins. NEVER hard-codes a default key.
_MASTER_ENVS = (
    "KEYRING_MASTER_SECRET",
    "FAMIT_SIGNING_MASTER",
    "PROVIDER_REGISTRY_KEYSTORE_SECRET",
    "FAMIT_KEYSTORE_SECRET",
)

# Domain tag so a derived key is not confusable with any other HKDF use of the same master elsewhere
# (e.g. the config vault's AES key derivation). Splits the *namespace* before we split by purpose.
_DERIVE_DOMAIN = b"famit/security/keys/v1"


class KeyManagerError(RuntimeError):
    """Master secret missing / crypto unavailable. NEVER carries key or secret material."""


# --------------------------------------------------------------------------- #
# master-secret resolution (the get_master seam — KMS-swappable, same shape as vault DEFAULT_GET_KEY)
# --------------------------------------------------------------------------- #
def _default_get_master() -> bytes:
    secret = ""
    for env in _MASTER_ENVS:
        secret = (os.environ.get(env) or "").strip()
        if secret:
            break
    if not secret:
        raise KeyManagerError(
            "no master signing secret set (KEYRING_MASTER_SECRET / FAMIT_SIGNING_MASTER / "
            "PROVIDER_REGISTRY_KEYSTORE_SECRET / FAMIT_KEYSTORE_SECRET) — cannot derive purpose keys"
        )
    return secret.encode("utf-8")


DEFAULT_GET_MASTER: Callable[[], bytes] = _default_get_master


# --------------------------------------------------------------------------- #
# HKDF-SHA256 (RFC 5869) — stdlib hmac only, no external dep.
# --------------------------------------------------------------------------- #
def _hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    return hmac.new(salt or b"\x00" * 32, ikm, hashlib.sha256).digest()


def _hkdf_expand(prk: bytes, info: bytes, length: int = 32) -> bytes:
    out, t, counter = b"", b"", 1
    while len(out) < length:
        t = hmac.new(prk, t + info + bytes([counter]), hashlib.sha256).digest()
        out += t
        counter += 1
    return out[:length]


def _purpose_info(purpose: KeyPurpose, version: int) -> bytes:
    """The HKDF `info` that makes two purposes (or two versions of one purpose) derive different
    bytes. version is folded in so per-purpose rotation = bump version, NO other purpose changes."""
    return _DERIVE_DOMAIN + b"|" + purpose.label.encode("utf-8") + b"|v" + str(int(version)).encode("ascii")


@dataclass(frozen=True)
class KeyHandle:
    """A reference to a derived key — carries the purpose + version + a NON-reversible fingerprint, so
    health/audit/UI can name 'which key' WITHOUT ever holding the bytes. The bytes are reachable ONLY
    via the keyring's sign/verify, never off this object."""

    purpose: KeyPurpose
    version: int
    fingerprint: str

    def __repr__(self) -> str:  # safe-to-log
        return f"KeyHandle(purpose={self.purpose.value}, v={self.version}, fp={self.fingerprint})"


def _fingerprint(key: bytes) -> str:
    """12-hex non-reversible id of a derived key (domain-salted SHA-256). Lets the runbook/health pool
    refer to a key without the plaintext."""
    return hashlib.sha256(b"famit-keyhandle|" + key).hexdigest()[:12]


class Keyring:
    """Resolves a distinct HMAC key per (purpose, version) from one master, and signs/verifies under
    it. The ONLY object that ever materialises derived key bytes; it never returns them."""

    def __init__(self, *, get_master: Optional[Callable[[], bytes]] = None, default_version: int = 1):
        self._get_master = get_master or DEFAULT_GET_MASTER
        self._default_version = int(default_version)

    # --- derivation (private — bytes never leave this class) ----------------- #
    def _derive(self, purpose: KeyPurpose, version: int) -> bytes:
        master = self._get_master()
        if not isinstance(master, (bytes, bytearray)) or not master:
            raise KeyManagerError("master secret resolved empty — refusing to derive a key")
        prk = _hkdf_extract(_DERIVE_DOMAIN, bytes(master))
        return _hkdf_expand(prk, _purpose_info(purpose, version), 32)

    # --- public, secret-free surface ----------------------------------------- #
    def handle(self, purpose: KeyPurpose, *, version: Optional[int] = None) -> KeyHandle:
        """A safe-to-log reference to the key for (purpose, version) — fingerprint only."""
        v = self._default_version if version is None else int(version)
        return KeyHandle(purpose=purpose, version=v, fingerprint=_fingerprint(self._derive(purpose, v)))

    def fingerprint(self, purpose: KeyPurpose, *, version: Optional[int] = None) -> str:
        return self.handle(purpose, version=version).fingerprint

    def sign(self, purpose: KeyPurpose, payload: bytes | str, *, version: Optional[int] = None) -> str:
        """HMAC-SHA256 sign `payload` under the PURPOSE-derived key. Returns a urlsafe-b64 MAC.
        Signing under one purpose produces a MAC that verify() rejects under any other purpose."""
        v = self._default_version if version is None else int(version)
        data = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
        mac = hmac.new(self._derive(purpose, v), data, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac).decode("ascii").rstrip("=")

    def verify(self, purpose: KeyPurpose, payload: bytes | str, mac: str, *, version: Optional[int] = None) -> bool:
        """Constant-time verify `mac` over `payload` under the PURPOSE-derived key. A MAC made for a
        DIFFERENT purpose (or version, or tampered payload) returns False — fail-closed."""
        if not mac:
            return False
        expected = self.sign(purpose, payload, version=version)
        return hmac.compare_digest(expected, mac)

    def legacy_compat_key_fingerprint(self) -> str:
        """During migration the live signers still use the RAW master. This is the fingerprint of the
        raw master (NOT a derived key) so the runbook can prove 'before flip, all families share THIS
        fp; after flip, each family has its own'. Returns fp only — never the master bytes."""
        return _fingerprint(self._get_master())
