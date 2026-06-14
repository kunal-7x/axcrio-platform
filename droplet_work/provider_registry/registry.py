"""provider_registry.registry — the SINGLE resolution point: get_provider(tenant, capability) (W3).

Spec: design/PROVIDER-FRAMEWORK-PLAN.md §2c (capability-based consumer interface — consumers
declare a CAPABILITY, not a provider name) + §3 (the registry is the single resolution point;
strangler: a MISS -> the consumer falls back to its legacy env path) + §4 ("registry.py —
get_provider(tenant, capability, routing_hint) -> ProviderClient; resolve+route+meter") + §6
(the credential is fetched ONLY through the get_secret seam) + §2f (skip circuit-open providers,
fall back by priority).

THE CONSUMER CONTRACT (the whole "Video Studio is just the first consumer" promise):

    client = registry.get_provider(tenant_id, capability="video_gen", routing_hint=None)
    if client.ok:
        url, headers, body = client.build_request(envelope)   # via the 3-tier adapter
        ... consumer does the HTTP (SSRF-guarded) ...
        envelope_out = client.parse_response(raw)
    else:
        ... client.reason == "not_configured" | "registry_disabled" | "no_credential" ...
        ... consumer falls back to its LEGACY env path (the strangler) ...

RESOLUTION (never raises — a problem yields an ok=False ProviderClient, the consumer degrades):
  1. flag OFF (config.is_enabled() False) -> ok=False, reason="registry_disabled" (resting
     byte-identical; the consumer uses legacy).
  2. PG unavailable -> ok=False, reason="not_configured".
  3. list the tenant's ENABLED definitions for `capability` (RLS: own + `_global`), ordered by
     priority asc (the fallback chain). A `routing_hint` (a slug) pins a specific provider first.
  4. walk the chain; SKIP any provider whose circuit is OPEN (health.is_open). The FIRST provider
     that has an active credential (fetched via the get_secret seam) wins.
  5. no usable provider -> ok=False, reason="not_configured" | "no_credential".

EARNER-SAFE: this module imports store / credentials / adapter / health only — NEVER agent.py,
NEVER does network I/O itself (the consumer owns the HTTP). For the latency-sensitive LLM-router
consumer (W6) the resolution is wrapped in a warm in-memory cache there (§3) — registry.get_provider
itself is a cheap RLS read + an in-memory breaker check.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple

from . import adapter, config, credentials, health, store
from .schema import ProviderCred, ProviderDef

_log = logging.getLogger("provider_registry.registry")


@dataclass
class ProviderClient:
    """The ready-to-use handle the registry returns. `ok` is the ONLY thing a consumer branches on.
    On ok=False the consumer falls back to its legacy path (the strangler). Holds the resolved
    ProviderDef + the decrypted key (transiently, in-process); NEVER logged, NEVER persisted."""
    ok: bool
    reason: str = ""
    capability: str = ""
    tenant_id: str = ""
    definition: Optional[ProviderDef] = None
    _key: str = field(default="", repr=False)   # plaintext, in-process only; repr-suppressed
    tried: List[str] = field(default_factory=list)  # slugs walked (for the audit/diagnostic)

    def build_request(self, envelope: dict) -> Tuple[str, dict, dict]:
        """Build (url, headers, body) for this provider via the 3-tier adapter. The consumer does
        the actual (SSRF-guarded) HTTP. Returns ("",{},{}) if not ok."""
        if not self.ok or self.definition is None:
            return "", {}, {}
        return adapter.build_request(self.definition, self._key, envelope)

    def parse_response(self, raw: Any) -> dict:
        """Parse a raw provider response into the neutral envelope via the adapter."""
        if self.definition is None:
            out = adapter._empty_response_envelope()
            out["status"] = "failed"
            return out
        return adapter.parse_response(self.definition, raw)

    def __repr__(self) -> str:  # never leak the key in a repr/log
        return (f"ProviderClient(ok={self.ok}, reason={self.reason!r}, "
                f"slug={(self.definition.slug if self.definition else None)!r})")


def _not_configured(capability: str, tenant_id: str, reason: str, tried: List[str]) -> ProviderClient:
    return ProviderClient(ok=False, reason=reason, capability=capability, tenant_id=tenant_id,
                          tried=tried)


def get_provider(
    tenant_id: str,
    capability: str,
    routing_hint: Optional[str] = None,
    *,
    get_key: Optional[Callable[[str, str, int], bytes]] = None,
    now_fn: Optional[Callable[[], float]] = None,
) -> ProviderClient:
    """Resolve the enabled provider for (tenant_id, capability), honoring the priority fallback
    chain + the in-memory circuit breaker, and return a ready ProviderClient. NEVER raises.

      * tenant_id    : ALWAYS the token-derived tenant (the caller passes resolve_tenant(req); RLS
                       then returns the tenant's own + `_global` defs only — A never gets B's).
      * capability   : e.g. 'video_gen' | 'text_gen' | 'image_gen' (§2c).
      * routing_hint : optional provider SLUG to try first (a consumer's explicit pick / BYO).
      * get_key      : injectable key-deriver for the get_secret seam (test/Vault swap); default
                       = credentials.DEFAULT_GET_KEY (interim Fernet).

    Resolution order: routing_hint slug first (if enabled + not circuit-open + has a cred), then
    the priority chain. The FIRST provider with a usable credential wins."""
    tried: List[str] = []

    # 1) flag OFF -> dormant; the consumer uses its legacy env path (resting byte-identical).
    if not config.is_enabled():
        return _not_configured(capability, tenant_id, "registry_disabled", tried)

    # 2) PG down / store unavailable -> not_configured (the consumer falls back).
    if not store.available():
        return _not_configured(capability, tenant_id, "not_configured", tried)

    nowf = now_fn or __import__("time").time

    # 3) the candidate chain: enabled defs for this capability, RLS-scoped, priority asc.
    candidates: List[ProviderDef] = store.list_definitions(
        tenant_id, capability=capability, enabled_only=True)

    # a routing_hint slug is tried FIRST (a consumer's explicit pick / vendor BYO selection).
    if routing_hint:
        hinted = [d for d in candidates if d.slug == routing_hint]
        rest = [d for d in candidates if d.slug != routing_hint]
        candidates = hinted + rest

    if not candidates:
        return _not_configured(capability, tenant_id, "not_configured", tried)

    # 4) walk the chain; skip circuit-open; first with a usable credential wins.
    last_reason = "not_configured"
    for d in candidates:
        tried.append(d.slug)
        pdid = d.id or ""
        if pdid and health.is_open(tenant_id, pdid, now_fn=nowf):
            last_reason = "circuit_open"
            continue
        cred = store.get_active_credential(tenant_id, pdid)
        # A provider with NO auth (auth_scheme='none') is usable WITHOUT a credential.
        scheme = d.auth_scheme
        scheme = scheme.value if hasattr(scheme, "value") else str(scheme or "bearer")
        if cred is None:
            if scheme == "none":
                return ProviderClient(ok=True, reason="ok", capability=capability,
                                      tenant_id=tenant_id, definition=d, _key="", tried=tried)
            last_reason = "no_credential"
            continue
        # 5) fetch the plaintext ONLY through the seam (credentials.decrypt; AAD-bound).
        try:
            key = credentials.decrypt_credential(cred, get_key=get_key)
        except Exception as exc:  # noqa: BLE001 — a bad/cross-tenant cred is skipped, not fatal
            _log.warning("provider_registry resolve: credential decrypt failed for %s: %r",
                         d.slug, type(exc).__name__)
            last_reason = "no_credential"
            continue
        return ProviderClient(ok=True, reason="ok", capability=capability, tenant_id=tenant_id,
                              definition=d, _key=key, tried=tried)

    return _not_configured(capability, tenant_id, last_reason, tried)


def resolve_status(tenant_id: str, capability: str) -> dict:
    """A non-secret diagnostic for the UI/health: which providers serve `capability` for this
    tenant + each one's circuit state. Never reveals a credential."""
    out = {"enabled": config.is_enabled(), "capability": capability, "providers": []}
    if not config.is_enabled() or not store.available():
        return out
    for d in store.list_definitions(tenant_id, capability=capability):
        out["providers"].append({
            "slug": d.slug,
            "display_name": d.display_name,
            "priority": d.priority,
            "is_enabled": d.is_enabled,
            "circuit": health.circuit_state(tenant_id, d.id or ""),
        })
    return out
