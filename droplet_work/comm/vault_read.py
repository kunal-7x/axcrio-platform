"""comm.vault_read — read + decrypt a channel credential from the LIVE provider vault.

Spec: communication/COMMUNICATION-MASTER-PLAN.md §0/§3 ("the channel registry IS the
provider registry — a bot token is a provider_credentials row; ZERO new crypto, reuse the
AAD-bound AES-256-GCM store already LIVE on the box") + the W1-P0 build-log (the founder
Telegram token is already stored under tenant `admin`, provider_def
`95ed8978-8bfe-4de2-8506-52e989d09f0e`, scope `integration`).

WHAT THIS DOES (a thin bridge — it owns NO crypto of its own):
  * `get_channel_token(tenant_id, provider_def_id)` -> plaintext token str (or None) by:
      1. reading the active credential row via provider_registry.store.get_active_credential
         (RLS-scoped: STRICTLY the tenant's own row — tenant A can never read tenant B's),
      2. decrypting it via provider_registry.credentials.decrypt_credential behind the
         SAME get_secret() seam (AAD recomputed from the row's own identity -> a stolen
         ciphertext pasted under another tenant raises InvalidTag, no plaintext leaks).
  * `resolve_provider_def_id(tenant_id, named_provider, slug)` -> the provider_def id for a
    channel, so the engine resolves "the tenant's telegram channel" without a hardcoded id.

DEGRADE, NEVER RAISE INTO THE EARNER PATH: every public fn returns None on any failure
(PG down / no row / crypto unavailable / decrypt InvalidTag). The plaintext is returned
TRANSIENTLY to the immediate caller (the adapter) only — never logged, never persisted on
any object, never echoed. `available()` is False when the registry/db layer is absent (local
build box) so import + call are safe on an empty-env machine.
"""
from __future__ import annotations

import logging
from typing import Optional

_log = logging.getLogger("comm.vault_read")


# ---------------------------------------------------------------------------
# lazy imports of the LIVE provider_registry (never at module import -> empty-env safe).
# ---------------------------------------------------------------------------
def _store():
    try:
        from provider_registry import store  # type: ignore
        return store
    except Exception:  # noqa: BLE001
        return None


def _creds():
    try:
        from provider_registry import credentials  # type: ignore
        return credentials
    except Exception:  # noqa: BLE001
        return None


def available() -> bool:
    """True iff the provider-registry store + crypto are importable AND PG is reachable.
    With this False, every read degrades to None (the strangler/dormant guarantee)."""
    st = _store()
    cr = _creds()
    if st is None or cr is None:
        return False
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

    Prefers an explicit `slug` lookup (e.g. 'telegram-founder'); else falls back to the
    first definition whose `named_provider` matches (e.g. 'telegram'). Returns the id str
    or None. NEVER raises."""
    st = _store()
    if st is None or not available() or not tenant_id:
        return None
    try:
        if slug:
            d = st.get_definition_by_slug(tenant_id, slug)
            if d is not None and getattr(d, "id", None):
                return str(d.id)
        if named_provider:
            for d in st.list_definitions(tenant_id):
                if (getattr(d, "named_provider", "") or "") == named_provider:
                    return str(d.id) if getattr(d, "id", None) else None
    except Exception as exc:  # noqa: BLE001 — degrade to None (never raise into the earner path)
        _log.warning("comm.vault_read.resolve_provider_def_id failed: %r", type(exc).__name__)
    return None


def get_channel_token(tenant_id: str, provider_def_id: str) -> Optional[str]:
    """Read + decrypt the active credential (the channel token) for (tenant, provider_def).

    RLS guarantees the read is STRICTLY the tenant's own credential. The decrypt recomputes
    the AAD from the row's own (tenant_id, provider_def_id, key_version) — so a cross-tenant
    copy fails closed (InvalidTag -> None here). Returns the plaintext token transiently to
    the caller, or None on any failure. NEVER logs the plaintext, NEVER raises."""
    st = _store()
    cr = _creds()
    if st is None or cr is None or not available():
        return None
    if not tenant_id or not provider_def_id:
        return None
    try:
        row = st.get_active_credential(tenant_id, provider_def_id)
        if row is None:
            return None
        token = cr.decrypt_credential(row)
        if not token or not isinstance(token, str):
            return None
        return token
    except Exception as exc:  # noqa: BLE001 — InvalidTag / PG / crypto -> fail-closed to None
        # type-only log: NEVER the plaintext, NEVER the ciphertext.
        _log.warning("comm.vault_read.get_channel_token failed: %r", type(exc).__name__)
        return None
