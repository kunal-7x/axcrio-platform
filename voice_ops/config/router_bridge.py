"""voice_ops.config.router_bridge — live key → healthiest plaintext, fail-LOUD failover (W13).

This is the seam the realtime-voice-kernel-v2 consumer calls instead of agent.py's bare
`itertools.cycle(_GROQ_KEYS)`. It ties the three pieces together:

    ProviderKeyStore (encrypted, versioned, hot-reloading)
        -> HealthScoredKeyPool (capacity/ratelimit/latency/error/reliability score per key)
        -> resolve_key(tenant, provider) = (fingerprint, plaintext) of the HEALTHIEST key, or LOUD failure

A key added in the panel joins the rotation on the next `resolve_key` (the store is versioned and the
pool membership is reconciled from `key_store.fingerprints` every resolve — no restart). On a 429 /
5xx / transport error the consumer calls `report(tenant, provider, fingerprint, code)`; the pool
demotes/trips that key and the NEXT resolve returns a different healthy key — instant failover. When
ALL keys are unhealthy `resolve_key` returns a LOUD result (`ResolvedKey(found=False, reason=...)`)
and emits `key_pool_exhausted` on the W8 bus — NEVER a silent default.

It ALSO offers `build_w5_router(...)`: a `DefaultProviderRouter` (the FROZEN W5 ProviderRouter
Protocol) whose pools are seeded LIVE from this tenant's key store — so the existing kernel wiring
(`build_kernel(cfg, router=...)`) gets hot keys for free, and its fail-loud `on_error` rotation works
against the real, health-scored pool.

A `LiveProviderRouter` adapter also satisfies the W5 `resolve()/on_error()` contract directly while
materializing plaintext on demand — the path the new kernel uses end to end.

Importing this pulls ZERO droplet/agent code (the W5 router/keypool are voice_kernel, tracked).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from . import events as _events
from .keyhealth import HealthScoredKeyPool
from .keys import ProviderKeyStore

log = logging.getLogger("voice_ops.config.router_bridge")

# provider -> the capability it serves (matches provider_registry schema capabilities).
PROVIDER_CAPABILITY = {
    "groq": "text_gen",
    "sarvam": "stt",          # Sarvam serves STT + TTS; the consumer disambiguates by use site
    "elevenlabs": "tts",
    "whatsapp": "webhook",
    "telephony": "webhook",
}


@dataclass
class ResolvedKey:
    """The result of resolving the healthiest key. `found=False` is the LOUD signal (the consumer
    MUST surface/log it, never substitute a silent default). Plaintext is materialized only here,
    at call time, and is never logged."""

    found: bool
    provider: str
    fingerprint: str = ""
    plaintext: str = ""           # call-time only; never stored, never logged
    reason: str = ""

    def __repr__(self) -> str:  # never leak plaintext in a repr / log line
        return f"ResolvedKey(found={self.found}, provider={self.provider!r}, fingerprint={self.fingerprint!r}, reason={self.reason!r})"


class KeyRouter:
    """Per-tenant live key resolver with health-scored pools (one pool per provider, lazily built and
    reconciled from the versioned key store on every resolve so a new key joins immediately)."""

    def __init__(self, tenant_id: str, key_store: Optional[ProviderKeyStore] = None,
                 *, is_admin: bool = False) -> None:
        self.tenant_id = (tenant_id or "").strip()
        self.key_store = key_store or ProviderKeyStore()
        self.is_admin = is_admin
        self._pools: dict[str, HealthScoredKeyPool] = {}

    def _pool(self, provider: str) -> HealthScoredKeyPool:
        provider = provider.strip().lower()
        pool = self._pools.get(provider)
        if pool is None:
            pool = HealthScoredKeyPool(provider)
            self._pools[provider] = pool
        # hot-reload membership from the versioned store EVERY resolve: a panel-added key joins now,
        # a removed/disabled key drops now — no restart. Existing keys keep their health state.
        fps = self.key_store.fingerprints(self.tenant_id, provider, active_only=True, is_admin=self.is_admin)
        pool.set_keys(fps)
        return pool

    def resolve_key(self, provider: str) -> ResolvedKey:
        """Return the HEALTHIEST active key's (fingerprint, plaintext) for a provider, or a LOUD
        not-found result + a key_pool_exhausted event. Plaintext is decrypted on demand."""
        provider = (provider or "").strip().lower()
        if not provider:
            return ResolvedKey(found=False, provider=provider, reason="no provider given")
        pool = self._pool(provider)
        if len(pool) == 0:
            reason = f"no keys configured for provider '{provider}' (add one in the panel)"
            log.warning("KeyRouter[%s/%s]: %s", self.tenant_id, provider, reason)
            _events.emit_key_pool_exhausted(self.tenant_id, provider)
            return ResolvedKey(found=False, provider=provider, reason=reason)
        fp = pool.pick()
        if fp is None:
            reason = f"all '{provider}' keys unhealthy/cooling — pool EXHAUSTED (failover required)"
            log.warning("KeyRouter[%s/%s]: %s", self.tenant_id, provider, reason)
            _events.emit_key_pool_exhausted(self.tenant_id, provider)
            return ResolvedKey(found=False, provider=provider, reason=reason)
        plaintext = self.key_store.decrypt(self.tenant_id, provider, fp, is_admin=self.is_admin)
        if not plaintext:
            # the chosen key vanished/disabled between pick and decrypt — demote + one retry.
            pool.report_failure(fp, 401, detail="decrypt returned no plaintext")
            fp2 = pool.pick()
            if fp2 and fp2 != fp:
                plaintext = self.key_store.decrypt(self.tenant_id, provider, fp2, is_admin=self.is_admin)
                if plaintext:
                    return ResolvedKey(found=True, provider=provider, fingerprint=fp2,
                                       plaintext=plaintext, reason="failover after decrypt miss")
            reason = f"could not materialize a usable '{provider}' key"
            _events.emit_key_pool_exhausted(self.tenant_id, provider)
            return ResolvedKey(found=False, provider=provider, reason=reason)
        return ResolvedKey(found=True, provider=provider, fingerprint=fp, plaintext=plaintext,
                           reason="healthiest key")

    # ----------------------------------------------------------- feedback -- #
    def report_success(self, provider: str, fingerprint: str, *, latency_ms: float = 0.0) -> None:
        self._pool(provider).report_success(fingerprint, latency_ms=latency_ms)

    def report_failure(self, provider: str, fingerprint: str, code: int, *, detail: str = "") -> None:
        """Feed a failure — demotes/trips the key so the NEXT resolve fails over. LOUD: the trip is
        logged by the pool; we also log the failover intent here."""
        self._pool(provider).report_failure(fingerprint, code, detail=detail)
        log.info("KeyRouter[%s/%s]: reported %s on key %s -> next resolve will fail over if needed",
                 self.tenant_id, provider, code, fingerprint)

    def observe_latency(self, provider: str, fingerprint: str, latency_ms: float) -> None:
        self._pool(provider).observe_latency(fingerprint, latency_ms)

    def set_capacity(self, provider: str, fingerprint: str, remaining: int, limit: int) -> None:
        self._pool(provider).set_capacity(fingerprint, remaining, limit)

    def health(self, provider: Optional[str] = None) -> dict:
        """Health snapshot (NO secrets) for the panel badge. One or all providers."""
        provs = [provider.strip().lower()] if provider else list(self._pools.keys())
        return {p: self._pool(p).snapshot() for p in provs}


# --------------------------------------------------------------------------- #
# W5 ProviderRouter adapters (so the existing kernel wiring gets live, health-scored keys).
# --------------------------------------------------------------------------- #
def build_w5_router(tenant_id: str, key_store: Optional[ProviderKeyStore] = None,
                    *, is_admin: bool = False):
    """Build a W5 `DefaultProviderRouter` whose KeyPools are seeded LIVE from this tenant's key store
    (fingerprints as the pool 'keys' — the W5 KeyPool only needs opaque identifiers for its
    rotation, and the bridge maps fingerprint->plaintext at call time). The kernel's authoritative
    selection + fail-loud on_error then operate against the real, health-aware pools."""
    from voice_kernel.providers.router import DefaultProviderRouter
    from voice_kernel.providers.keypool import KeyPool

    ks = key_store or ProviderKeyStore()
    pools: dict[str, KeyPool] = {}
    for provider in ("sarvam", "elevenlabs", "groq"):
        fps = ks.fingerprints(tenant_id, provider, active_only=True, is_admin=is_admin)
        if fps:
            pools[provider] = KeyPool(provider, fps)
    return DefaultProviderRouter(pools=pools)


class LiveProviderRouter:
    """A W5 `ProviderRouter`-shaped adapter backed by the health-scored KeyRouter. `resolve()` keeps
    the authoritative triple from the campaign fields (delegating to DefaultProviderRouter) while the
    actual KEY behind each provider is the healthiest live one; `on_error()` reports the failing key
    and re-resolves — fail-loud, never silent."""

    def __init__(self, tenant_id: str, key_store: Optional[ProviderKeyStore] = None,
                 *, is_admin: bool = False) -> None:
        from voice_kernel.providers.router import DefaultProviderRouter
        self.tenant_id = tenant_id
        self.key_router = KeyRouter(tenant_id, key_store, is_admin=is_admin)
        self._w5 = DefaultProviderRouter(pools={})
        self._last_fp: dict[str, str] = {}

    def resolve(self, ctx):
        return self._w5.resolve(ctx)

    def on_error(self, provider: str, code: int):
        fp = self._last_fp.get((provider or "").strip().lower(), "")
        if fp:
            self.key_router.report_failure(provider, fp, code, detail="on_error")
        return self._w5.on_error(provider, code)

    def key_for(self, provider: str) -> ResolvedKey:
        rk = self.key_router.resolve_key(provider)
        if rk.found:
            self._last_fp[provider.strip().lower()] = rk.fingerprint
        return rk
