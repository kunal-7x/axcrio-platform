"""ads_engine.vault_adapter — the ONLY door to ad-platform secrets.

REDTEAM secrets-vault: ad/whatsapp/telephony creds are read ONLY through the injected
provider_registry seam — NEVER os.environ / .env / a `*_key` constant, never logged in
plaintext. This module owns NO crypto; provider_registry does the AES-256-GCM decrypt under
Postgres FORCE-RLS with AAD `tenant_id||def_id||key_version` (a cross-tenant ciphertext copy
fails closed via InvalidTag).

GET_SECRET SEAM (redteam mustFix C2 — ONE signature, pinned):
  * get_secret(tenant_id, provider_def_id)      -> str | None   (the whole credential blob)
  * get_secret_json(tenant_id, provider_def_id) -> dict | None  (json.loads of the blob)
  There is NO 3-arg per-field get_secret. A 3-arg call is a hard TypeError (a stub
  `_forbid_3arg` makes the mistake loud, not silent). Per-field reads go through
  get_secret_json(t, def)["field"] with the None-guarded accessors below — fixing the
  field-name drift the redteam flagged (oauth_refresh_token -> refresh_token; nested
  app_secret inside the meta-marketing blob).

The store + decrypt seam is reached via the injected `registry` module (the provider_registry
package), mirroring comm/vault_read.py:107-110 verbatim in spirit:
  registry.store.get_active_credential(tenant, def)  ->  registry.credentials.decrypt_credential(row)

Degrade-never-raise: PG down / no row / disabled registry / InvalidTag -> None / not_configured
(the route renders dormant), never an exception into the live spine. Type-only logging; the
plaintext blob is returned TRANSIENTLY to the immediate caller, never logged / never persisted.

`list_status` is PROVEN secret/id-free (redteam M4): it returns ONLY {channel, state} — never an
ad_account_id / phone_number_id / waba_id / token prefix.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from . import seams

_log = logging.getLogger("ads_engine.vault_adapter")

# capability strings the connectors request (provider_registry Capability values).
CAP_META = "ad_platform"
CAP_GOOGLE = "ad_platform"
CAP_WHATSAPP = "messaging"

# channel -> the capability used to resolve the def in the vault.
_CHANNEL_CAP = {
    "meta": "ad_platform",
    "google": "ad_platform",
    "whatsapp": "messaging",
    "telephony": "webhook",
    # V2-W4: the vault-configurable REASONING-MODEL connection (litellm gateway). Its own def
    # family so a tenant's OpenRouter/Groq/Anthropic/OpenAI/Sarvam key is resolved distinctly.
    "reasoning": "reasoning",
}

# channel -> named_provider on the provider_def (resolve_provider_def_id lookup).
_CHANNEL_NAMED = {
    "meta": "meta",
    "google": "google",
    "whatsapp": "whatsapp",
    "telephony": "livekit_sip",
    "reasoning": "reasoning_model",
}


@dataclass
class ConnectorCreds:
    """In-process value object — NEVER persisted. repr suppresses the secret blob."""
    ok: bool
    channel: str
    tenant_id: str
    provider_def_id: str = ""
    secret_json: dict = field(default_factory=dict, repr=False)
    reason: str = "ok"  # ok | not_configured | no_credential | bad_shape | registry_disabled


# ---------------------------------------------------------------------------
# Registry seam plumbing — the store + credentials modules, reached ONLY via the
# injected registry module (never an os-level import of secrets). Lazy + crash-proof.
# ---------------------------------------------------------------------------
def _registry():
    """The injected provider_registry module (or None)."""
    return getattr(seams(), "registry", None)


def _store():
    reg = _registry()
    return getattr(reg, "store", None) if reg is not None else None


def _creds():
    reg = _registry()
    return getattr(reg, "credentials", None) if reg is not None else None


def _get_provider():
    """The injected provider_registry get_provider seam (or None if registry absent)."""
    s = seams()
    fn = getattr(s, "get_provider", None)
    if fn is not None:
        return fn
    reg = _registry()
    return getattr(reg, "get_provider", None) if reg is not None else None


def available() -> bool:
    """True iff the provider-registry store + crypto are reachable (engine usable).

    Mirrors comm/vault_read.available(): both store + credentials importable AND store.available()
    (PG up). With this False every read degrades to None (the dormant guarantee)."""
    st = _store()
    cr = _creds()
    if st is None or cr is None:
        # Fall back to the get_provider seam presence (resolve-only path still works for status).
        return _get_provider() is not None
    try:
        return bool(st.available())
    except Exception:  # noqa: BLE001
        return False


def resolve_provider_def_id(
    tenant_id: str,
    *,
    named_provider: str = "",
    slug: str = "",
) -> Optional[str]:
    """Resolve the provider_definitions.id for a channel (RLS-scoped to this tenant).

    Prefers an explicit `slug`; else the first def whose `named_provider` matches. Returns the
    id str or None. NEVER raises. (mirror comm/vault_read.resolve_provider_def_id:65)"""
    st = _store()
    if st is None or not tenant_id:
        return None
    try:
        if slug and hasattr(st, "get_definition_by_slug"):
            d = st.get_definition_by_slug(tenant_id, slug)
            if d is not None and getattr(d, "id", None):
                return str(d.id)
        if named_provider and hasattr(st, "list_definitions"):
            for d in st.list_definitions(tenant_id):
                if (getattr(d, "named_provider", "") or "") == named_provider:
                    return str(d.id) if getattr(d, "id", None) else None
    except Exception as exc:  # noqa: BLE001 — degrade to None (never raise into the earner path)
        _log.warning("ads_engine.vault_adapter.resolve_provider_def_id failed: %r",
                     type(exc).__name__)
    return None


# ---------------------------------------------------------------------------
# THE GET_SECRET SEAM (2-arg ONLY). redteam C2.
# ---------------------------------------------------------------------------
def get_secret(tenant_id: str, provider_def_id: str, *_forbidden_extra: Any) -> Optional[str]:
    """Read + decrypt the active credential BLOB for (tenant, provider_def). 2-ARG ONLY.

    Returns the whole credential plaintext (a JSON string for ad/messaging connectors) transiently
    to the caller, or None on any failure. The RLS read is STRICTLY the tenant's own row; the
    decrypt recomputes the AAD from the row's own (tenant, def, key_version) so a cross-tenant copy
    fails closed (InvalidTag -> None). NEVER logs the plaintext, NEVER raises.

    A 3-arg per-field call (the leads/feedback drift the redteam flagged) is a HARD error: there is
    no `field` parameter. Callers MUST use get_secret_json(t, def)["field"]. We raise loudly rather
    than silently bind a field to nothing — surfacing the mistake at the call site, not in prod.
    """
    if _forbidden_extra:
        raise TypeError(
            "get_secret(tenant_id, provider_def_id) takes 2 args ONLY — no per-field form. "
            "Use get_secret_json(tenant_id, provider_def_id)['field'] instead (redteam C2)."
        )
    st = _store()
    cr = _creds()
    if st is None or cr is None or not tenant_id or not provider_def_id:
        return None
    if not available():
        return None
    try:
        row = st.get_active_credential(tenant_id, provider_def_id)
        if row is None:
            return None
        blob = cr.decrypt_credential(row)
        if not blob or not isinstance(blob, str):
            return None
        return blob
    except Exception as exc:  # noqa: BLE001 — InvalidTag / PG / crypto -> fail-closed to None
        # type-only log: NEVER the plaintext, NEVER the ciphertext.
        _log.warning("ads_engine.vault_adapter.get_secret failed: %r", type(exc).__name__)
        return None


def get_secret_json(tenant_id: str, provider_def_id: str, *_forbidden_extra: Any) -> Optional[dict]:
    """get_secret + json.loads — the multi-field OAuth blob as a dict. 2-ARG ONLY.

    Returns the decrypted blob parsed to a dict, or None on any failure (incl. non-JSON / non-object
    plaintext). NEVER raises, NEVER logs the blob. This is the door every per-field connector read
    goes through: get_secret_json(t, def)["system_user_token"] etc.
    """
    if _forbidden_extra:
        raise TypeError(
            "get_secret_json(tenant_id, provider_def_id) takes 2 args ONLY (redteam C2)."
        )
    blob = get_secret(tenant_id, provider_def_id)
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except Exception:  # noqa: BLE001 — malformed JSON -> None (never raise, never log the blob)
        _log.warning("ads_engine.vault_adapter.get_secret_json: blob not valid JSON")
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# NONE-GUARDED FIELD ACCESSORS — the canonical key names (redteam C2 field-drift fix).
# Every accessor takes the already-decrypted blob dict and returns str|None (never raises on a
# missing/None field). Field names are the CANONICAL vault-blob shapes (vault-connectors.md
# §1.3), NOT the leads/feedback drift names:
#   * refresh_token          (NOT oauth_refresh_token)
#   * app_secret             (nested inside the meta-marketing blob — read it from the SAME blob)
# ---------------------------------------------------------------------------
def get_field(blob: Optional[dict], key: str, default: Optional[str] = None) -> Optional[str]:
    """None-guarded blob field read. Returns blob[key] as a non-empty str, else `default`.

    Named `get_field` (NOT `field`) so it never shadows `dataclasses.field` imported above.
    Tolerates blob=None, missing key, and a None/empty/non-str value — never raises, never logs."""
    if not isinstance(blob, dict):
        return default
    v = blob.get(key)
    if v is None:
        return default
    if not isinstance(v, str):
        v = str(v)
    return v if v else default


# Canonical-name aliasing: accept the historical drift names on READ but normalize to canonical,
# so a stored blob written with either spelling resolves. NEVER write the drift names.
_FIELD_ALIASES = {
    "refresh_token": ("refresh_token", "oauth_refresh_token"),
    "app_secret": ("app_secret",),
    "system_user_token": ("system_user_token", "access_token"),
    "api_key": ("api_key",),
}


def field_aliased(blob: Optional[dict], canonical: str,
                  default: Optional[str] = None) -> Optional[str]:
    """Read a canonical field, tolerating known historical aliases (read-side drift repair)."""
    for name in _FIELD_ALIASES.get(canonical, (canonical,)):
        v = get_field(blob, name)
        if v is not None:
            return v
    return default


# ---------------------------------------------------------------------------
# Per-channel resolve helpers (used by get_connector_creds + connectors).
# ---------------------------------------------------------------------------
def _resolve_client(tenant_id: str, channel: str):
    """Resolve a ready ProviderClient for (tenant, channel) via the registry seam. None on any
    error. Used ONLY for the existence/status check — the secret itself comes via get_secret."""
    fn = _get_provider()
    if fn is None:
        return None
    cap = _CHANNEL_CAP.get(channel, "ad_platform")
    try:
        return fn(tenant_id, cap)
    except Exception:  # noqa: BLE001 — degrade-never-raise
        return None


def _def_id_for(tenant_id: str, channel: str) -> Optional[str]:
    """The provider_def_id for (tenant, channel).

    CHANNEL-ACCURATE (BLINDSPOTS B2): resolve by `named_provider` FIRST. Meta AND Google both carry
    capability `ad_platform`, so a capability-only resolve (get_provider) cannot tell them apart and
    would map both channels to the SAME def — making is_configured("meta") and is_configured("google")
    indistinguishable. The named_provider lookup ("meta" vs "google" vs "whatsapp") is the only
    channel-accurate key, so it wins. Only when no named def exists do we fall back to the
    capability-resolved client's definition id (covers a legacy def created without named_provider).
    None-safe; never raises."""
    pdid = resolve_provider_def_id(tenant_id, named_provider=_CHANNEL_NAMED.get(channel, channel))
    if pdid:
        return pdid
    client = _resolve_client(tenant_id, channel)
    d = getattr(client, "definition", None) if client is not None else None
    cid = getattr(d, "id", None) if d is not None else None
    return str(cid) if cid else None


def _has_credential(tenant_id: str, provider_def_id: str) -> bool:
    """Does an ACTIVE credential row EXIST for (tenant, def)? Existence-only — NEVER decrypts to
    plaintext (the row is ciphertext). RLS keeps it strictly the tenant's own row. Default-safe False.
    This is the 'a key has actually been saved' check that closes the paste-key -> connected loop."""
    st = _store()
    if st is None or not tenant_id or not provider_def_id:
        return False
    try:
        return st.get_active_credential(tenant_id, provider_def_id) is not None
    except Exception:  # noqa: BLE001 — PG down / RLS -> fail-closed to False
        return False


def is_configured(tenant_id: str, channel: str) -> bool:
    """Is this (tenant, channel) CONNECTED — i.e. a provider def is resolvable for the channel AND an
    active credential row exists for it? (BLINDSPOTS B2/B15.)

    Channel-accurate via _def_id_for (named_provider), then proves a key was actually saved via the
    existence-only _has_credential (no decrypt). This is what flips /ads/health.providers.<channel>
    from not_configured -> configured the instant a vendor pastes + saves a key. Default-safe False."""
    try:
        pdid = _def_id_for(tenant_id, channel)
        if not pdid:
            return False
        return _has_credential(tenant_id, pdid)
    except Exception:  # noqa: BLE001
        return False


def list_status(tenant_id: str) -> dict:
    """Non-secret provider status for /ads/health.providers — SECRET/ID-FREE (redteam M4).

    Returns ONLY { "<channel>": "configured" | "not_configured" }. No ids, no token prefixes,
    no ad_account_id / phone_number_id / waba_id. (asserted secret-free by the offline smoke)."""
    out: dict = {}
    for ch in ("meta", "google", "whatsapp"):
        try:
            out[ch] = "configured" if is_configured(tenant_id, ch) else "not_configured"
        except Exception:  # noqa: BLE001
            out[ch] = "not_configured"
    return out


def provider_status_for_health(tenant_id: str) -> dict:
    """The {meta, google, whatsapp} block config.health_block expects. Subset of list_status."""
    s = list_status(tenant_id)
    return {
        "meta": s.get("meta", "not_configured"),
        "google": s.get("google", "not_configured"),
        "whatsapp": s.get("whatsapp", "not_configured"),
    }


# ---------------------------------------------------------------------------
# TEST CONNECTION (BLINDSPOTS B15) — a round-trip that proves the ad engine can actually READ a
# usable credential blob for a channel. Structural (no network): resolve the def -> decrypt the blob
# -> assert the connector's REQUIRED fields are present. Secret-free result (field NAMES only, never
# values). This closes the "key in -> status shows connected" loop the founder named: the UI calls it
# right after a paste-key save and shows Connected ✓ / what's still missing.
# ---------------------------------------------------------------------------
# The minimum fields each connector needs to operate (canonical vault-blob names; connectors/*.py).
_REQUIRED_FIELDS = {
    "meta": ("system_user_token", "ad_account_id"),
    "google": ("refresh_token", "developer_token", "client_id", "client_secret"),
    # whatsapp: phone_number_id + at least one auth (360dialog api_key OR cloud access_token).
    "whatsapp": ("phone_number_id",),
}
# at least one of these must be present (channel -> tuple of acceptable alternatives).
_REQUIRED_ANY = {
    "whatsapp": ("api_key", "access_token"),
}


def test_connection(tenant_id: str, channel: str) -> dict:
    """Round-trip a (tenant, channel): resolve the def, decrypt the blob, assert the connector's
    required fields are present. Returns a SECRET-FREE dict:
        { ok, channel, reason, missing: [field,...], present: [field,...] }
    reason ∈ ok | registry_disabled | not_configured | no_credential | missing_fields. NEVER raises,
    NEVER returns a secret VALUE (only field names). Structural by design (no live Meta/Google call)
    so it is earner-safe + offline-testable; a live ping is a separate, flag-gated step (B15)."""
    ch = (channel or "").strip().lower()
    if not available():
        return {"ok": False, "channel": ch, "reason": "registry_disabled", "missing": [], "present": []}
    pdid = _def_id_for(tenant_id, ch)
    if not pdid:
        return {"ok": False, "channel": ch, "reason": "not_configured", "missing": [], "present": []}
    blob = get_secret_json(tenant_id, pdid)
    if blob is None:
        return {"ok": False, "channel": ch, "reason": "no_credential", "missing": [], "present": []}
    required = _REQUIRED_FIELDS.get(ch, ())
    present = [k for k in required if field_aliased(blob, k)]
    missing = [k for k in required if not field_aliased(blob, k)]
    # "at least one of" group (e.g. whatsapp api_key | access_token).
    any_group = _REQUIRED_ANY.get(ch)
    if any_group:
        if any(field_aliased(blob, k) for k in any_group):
            present.append("|".join(any_group))
        else:
            missing.append("|".join(any_group))
    ok = not missing
    return {
        "ok": ok,
        "channel": ch,
        "reason": "ok" if ok else "missing_fields",
        "missing": missing,
        "present": present,
    }


# ---------------------------------------------------------------------------
# THE WRITE SEAM (BLINDSPOTS B4) — land an OAuth-minted token into the channel's vault blob.
# ---------------------------------------------------------------------------
def write_channel_blob(tenant_id: str, channel: str, updates: dict) -> dict:
    """MERGE `updates` (e.g. {"system_user_token": ...} / {"refresh_token": ...}) into the existing
    credential blob for (tenant, channel) and re-encrypt+upsert it. Used by the OAuth callback to
    persist a freshly-minted token WITHOUT the vendor pasting it.

    Contract (SECRET-FREE return): { ok, channel, reason, fields_written: [names...] }
      reason ∈ ok | registry_disabled | not_configured | no_updates | encrypt_unavailable | write_failed
    `not_configured` => the vendor has not yet created a Meta/Google provider def (the preset wizard,
    B3, owns def creation); the OAuth flow only LANDS the token into an existing def — it never mints
    a def, never echoes a secret. NEVER raises.
    """
    ch = (channel or "").strip().lower()
    if not isinstance(updates, dict) or not updates:
        return {"ok": False, "channel": ch, "reason": "no_updates", "fields_written": []}
    st = _store()
    cr = _creds()
    if st is None or cr is None or not available():
        return {"ok": False, "channel": ch, "reason": "registry_disabled", "fields_written": []}
    pdid = _def_id_for(tenant_id, ch)
    if not pdid:
        return {"ok": False, "channel": ch, "reason": "not_configured", "fields_written": []}
    # Merge onto the current blob (preserve sibling fields like ad_account_id/page_id the vendor set).
    current = get_secret_json(tenant_id, pdid) or {}
    if not isinstance(current, dict):
        current = {}
    merged = dict(current)
    written = []
    for k, v in updates.items():
        if v is None or v == "":
            continue
        merged[str(k)] = v
        written.append(str(k))
    if not written:
        return {"ok": False, "channel": ch, "reason": "no_updates", "fields_written": []}
    try:
        enc = cr.encrypt_credential(tenant_id, str(pdid), merged)
    except Exception as exc:  # noqa: BLE001 — crypto/key unavailable -> degrade, never raise
        _log.warning("ads_engine.vault_adapter.write_channel_blob encrypt failed: %r",
                     type(exc).__name__)
        return {"ok": False, "channel": ch, "reason": "encrypt_unavailable", "fields_written": []}
    try:
        st.upsert_credential(tenant_id, str(pdid), enc, scope="integration")
    except Exception as exc:  # noqa: BLE001 — DB write failure -> degrade, never raise
        _log.warning("ads_engine.vault_adapter.write_channel_blob upsert failed: %r",
                     type(exc).__name__)
        return {"ok": False, "channel": ch, "reason": "write_failed", "fields_written": []}
    return {"ok": True, "channel": ch, "reason": "ok", "fields_written": written}


def get_connector_creds(tenant_id: str, channel: str) -> ConnectorCreds:
    """High-level door the connectors call: resolve the def, pull + parse the secret blob, return a
    typed ConnectorCreds. On any miss -> not_configured (the connector surfaces it, the route renders
    dormant). The decrypted blob lives ONLY on the repr-suppressed secret_json; never logged.
    """
    if not available():
        return ConnectorCreds(ok=False, channel=channel, tenant_id=tenant_id,
                              reason="registry_disabled")
    pdid = _def_id_for(tenant_id, channel)
    if not pdid:
        return ConnectorCreds(ok=False, channel=channel, tenant_id=tenant_id,
                              reason="not_configured")
    blob = get_secret_json(tenant_id, pdid)
    if blob is None:
        # def exists but no usable/parseable credential row.
        return ConnectorCreds(ok=False, channel=channel, tenant_id=tenant_id,
                              provider_def_id=pdid, reason="no_credential")
    return ConnectorCreds(ok=True, channel=channel, tenant_id=tenant_id,
                          provider_def_id=pdid, secret_json=blob, reason="ok")
