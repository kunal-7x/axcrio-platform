"""voice_ops.config.keys — real-time, encrypted provider-key store + rotation feed (W13).

The founder's #1 ask: "add a Groq/Sarvam/ElevenLabs/WhatsApp/telephony key from the frontend → it
becomes active IMMEDIATELY, no .env edits, no restart, no redeploy; route to the healthiest key with
instant failover; fail LOUD."

This module is the CRUD + storage half (the health/scoring half is keyhealth.py; the live router
half is router_bridge.py). It:

  - stores each key ENCRYPTED through `voice_ops.config.vault` (AAD-bound AES-256-GCM) — plaintext
    NEVER hits disk / a row / a log / an event. The persisted doc holds {fingerprint, ciphertext_b64,
    key_aad, key_version, label, status, added_by, added_at} — secrets at rest only.
  - persists the doc in the versioned, FORCE-RLS `config_state` store under the `provider_keys`
    namespace — so a write bumps the version and (via events.py) emits a config_changed +
    provider_key_added event; any reader picks it up on the next poll WITHOUT a restart.
  - exposes `fingerprints(provider)` (for the health pool membership) and
    `decrypt(provider, fingerprint)` (the ONLY place plaintext is ever materialized, at call time).

PROVIDERS supported (the founder's list): groq, sarvam, elevenlabs, whatsapp, telephony — plus any
future provider string (the store is provider-agnostic; capability mapping lives in router_bridge).

Importing this pulls ZERO droplet/agent code. DB + crypto are reached only through the store + vault.
"""
from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Optional

from . import events as _events
from . import vault as _vault
from .store import ConfigStore

log = logging.getLogger("voice_ops.config.keys")

NAMESPACE = "provider_keys"

# The founder's provider set. Extra strings are allowed (provider-agnostic), these are just the
# known ones the panel surfaces by default + their human capability hint.
KNOWN_PROVIDERS = ("groq", "sarvam", "elevenlabs", "whatsapp", "telephony")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ProviderKeyStore:
    """Tenant-scoped encrypted key CRUD on top of the versioned config store.

    The doc shape persisted under `provider_keys`:
        { "<provider>": [ {fingerprint, ciphertext_b64, key_aad, key_version, label,
                           status: active|disabled, added_by, added_at}, ... ], ... }
    Plaintext is supplied to `add_key` and immediately encrypted; it is NEVER stored or returned by
    any list/get method — only `decrypt(...)` (call-time) materializes it."""

    def __init__(self, store: Optional[ConfigStore] = None) -> None:
        self.store = store or ConfigStore()

    # ----------------------------------------------------------- internal -- #
    def _load(self, tenant_id: str, *, is_admin: bool = False) -> tuple[dict, int]:
        snap = self.store.get(tenant_id, NAMESPACE, is_admin=is_admin)
        if snap is None:
            return {}, 0
        return dict(snap.doc or {}), snap.version

    def _save(self, tenant_id: str, doc: dict, *, updated_by: str, is_admin: bool = False) -> int:
        snap = self.store.put(tenant_id, NAMESPACE, doc, updated_by=updated_by, is_admin=is_admin)
        # push: config_changed (whole namespace) — the per-key event is emitted by the caller method
        # so the payload can carry the specific provider/fingerprint.
        _events.emit_config_changed(tenant_id, NAMESPACE, snap.version, updated_by)
        return snap.version

    # --------------------------------------------------------------- CRUD -- #
    def add_key(self, tenant_id: str, provider: str, secret: str, *, label: str = "",
                added_by: str = "", is_admin: bool = False) -> dict:
        """Encrypt + persist a new key for a provider. Returns the public (NO-plaintext) record. The
        key joins the rotation pool LIVE on the next reader poll / immediately for push consumers.
        Idempotent on fingerprint: re-adding the SAME secret reactivates it rather than duplicating."""
        provider = (provider or "").strip().lower()
        if not provider:
            raise ValueError("add_key requires a provider")
        if not (secret or "").strip():
            raise ValueError("add_key requires a non-empty secret")
        fp = _vault.fingerprint(secret)
        blob = _vault.encrypt_secret(tenant_id, provider, secret)  # raises VaultError if no master secret
        rec = {
            "fingerprint": fp,
            "ciphertext_b64": base64.b64encode(blob["ciphertext"]).decode("ascii"),
            "key_aad": blob["key_aad"],
            "key_version": blob["key_version"],
            "label": (label or "")[:80],
            "status": "active",
            "added_by": added_by or "",
            "added_at": _now_iso(),
        }
        doc, _ = self._load(tenant_id, is_admin=is_admin)
        lst = list(doc.get(provider) or [])
        # de-dup / reactivate by fingerprint.
        lst = [r for r in lst if r.get("fingerprint") != fp]
        lst.append(rec)
        doc[provider] = lst
        version = self._save(tenant_id, doc, updated_by=added_by, is_admin=is_admin)
        _events.emit_provider_key_added(tenant_id, provider, fp)
        log.info("provider key added tenant=%s provider=%s fp=%s v=%s (LIVE, no restart)",
                 tenant_id, provider, fp, version)
        return {**{k: v for k, v in rec.items() if k != "ciphertext_b64"}, "version": version}

    def disable_key(self, tenant_id: str, provider: str, fingerprint: str, *, actor: str = "",
                    is_admin: bool = False) -> dict:
        return self._set_status(tenant_id, provider, fingerprint, "disabled", actor=actor, is_admin=is_admin)

    def enable_key(self, tenant_id: str, provider: str, fingerprint: str, *, actor: str = "",
                   is_admin: bool = False) -> dict:
        return self._set_status(tenant_id, provider, fingerprint, "active", actor=actor, is_admin=is_admin)

    def remove_key(self, tenant_id: str, provider: str, fingerprint: str, *, actor: str = "",
                   is_admin: bool = False) -> dict:
        provider = (provider or "").strip().lower()
        doc, _ = self._load(tenant_id, is_admin=is_admin)
        lst = [r for r in (doc.get(provider) or []) if r.get("fingerprint") != fingerprint]
        doc[provider] = lst
        version = self._save(tenant_id, doc, updated_by=actor, is_admin=is_admin)
        _events.emit_provider_key_revoked(tenant_id, provider, fingerprint)
        log.info("provider key removed tenant=%s provider=%s fp=%s v=%s", tenant_id, provider, fingerprint, version)
        return {"status": "ok", "version": version}

    def _set_status(self, tenant_id: str, provider: str, fingerprint: str, status: str, *,
                    actor: str, is_admin: bool) -> dict:
        provider = (provider or "").strip().lower()
        doc, _ = self._load(tenant_id, is_admin=is_admin)
        found = False
        for r in (doc.get(provider) or []):
            if r.get("fingerprint") == fingerprint:
                r["status"] = status
                found = True
        if not found:
            return {"status": "not_found"}
        version = self._save(tenant_id, doc, updated_by=actor, is_admin=is_admin)
        if status == "disabled":
            _events.emit_provider_key_revoked(tenant_id, provider, fingerprint)
        return {"status": "ok", "new_status": status, "version": version}

    # --------------------------------------------------------------- read -- #
    def list_keys(self, tenant_id: str, provider: Optional[str] = None, *, is_admin: bool = False) -> dict:
        """Return the PUBLIC, masked view (fingerprint + label + status + meta — NEVER ciphertext or
        plaintext). The shape the panel renders + the health pool seeds membership from."""
        doc, version = self._load(tenant_id, is_admin=is_admin)
        out: dict = {"version": version, "providers": {}}
        provs = [provider.strip().lower()] if provider else list(doc.keys())
        for p in provs:
            recs = doc.get(p) or []
            out["providers"][p] = [
                {"fingerprint": r["fingerprint"], "label": r.get("label", ""),
                 "status": r.get("status", "active"), "added_by": r.get("added_by", ""),
                 "added_at": r.get("added_at", ""), "key_version": r.get("key_version", 1)}
                for r in recs
            ]
        return out

    def fingerprints(self, tenant_id: str, provider: str, *, active_only: bool = True,
                     is_admin: bool = False) -> tuple[str, ...]:
        """The ACTIVE key fingerprints for a provider — exactly what HealthScoredKeyPool.set_keys
        wants. Hot-reloaded: a freshly added key shows up on the next call (the store is versioned)."""
        provider = (provider or "").strip().lower()
        doc, _ = self._load(tenant_id, is_admin=is_admin)
        recs = doc.get(provider) or []
        return tuple(r["fingerprint"] for r in recs
                     if r.get("fingerprint") and (not active_only or r.get("status", "active") == "active"))

    def decrypt(self, tenant_id: str, provider: str, fingerprint: str, *, is_admin: bool = False) -> Optional[str]:
        """The ONLY place a plaintext secret is materialized — at CALL TIME, for the chosen key. The
        router asks the health pool for the healthiest fingerprint, then asks here for its plaintext.

        Returns None — never raises — when the key is unknown/disabled OR when its ciphertext cannot
        be decrypted (cross-tenant paste, on-disk tamper, a ROTATED/changed master keystore secret, or
        a missing master secret in this worker's env). A crypto failure is fail-CLOSED *and* fail-SOFT:
        it never yields plaintext, never crashes the live voice path, and is logged LOUD (fingerprint
        only, NEVER the secret) so the router turns the None into a logged failover / pool-exhausted
        alarm. (Before this guard a master-secret rotation or a corrupt row raised InvalidTag/VaultError
        straight through resolve_key and crashed every call instead of failing over.)"""
        provider = (provider or "").strip().lower()
        doc, _ = self._load(tenant_id, is_admin=is_admin)
        for r in (doc.get(provider) or []):
            if r.get("fingerprint") == fingerprint and r.get("status", "active") == "active":
                try:
                    ct = base64.b64decode(r["ciphertext_b64"])
                    return _vault.decrypt_secret(tenant_id, provider, ct, int(r.get("key_version", 1)))
                except Exception as exc:  # noqa: BLE001  — InvalidTag / VaultError / bad b64 / bad row
                    # LOUD but secret-safe: fingerprint + error TYPE only, never the ciphertext/plaintext.
                    log.warning(
                        "decrypt FAILED tenant=%s provider=%s fp=%s err=%s — key unusable, "
                        "failing CLOSED (check master keystore secret / rotation / row integrity)",
                        tenant_id, provider, fingerprint, type(exc).__name__,
                    )
                    return None
        return None
