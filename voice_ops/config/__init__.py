"""voice_ops.config — real-time Vendor Control Center + health-scored API-key pool/rotation (W13).

The founder's ask, in one disjoint, TRACKED, droplet-free package:

  1. REAL-TIME PROVIDER CONFIG + KEY ROTATION — add a Groq/Sarvam/ElevenLabs/WhatsApp/telephony key
     from the panel; it becomes active IMMEDIATELY (no .env edit, no restart, no redeploy). A
     HEALTH-SCORED key pool (capacity / rate-limit / latency / error-rate / reliability per key)
     routes to the HEALTHIEST key and fails over instantly + LOUDLY (never a silent default).
        keys.ProviderKeyStore  (encrypted CRUD)  ->  keyhealth.HealthScoredKeyPool (scoring)
        ->  router_bridge.KeyRouter / LiveProviderRouter / build_w5_router  (live resolve + failover)

  2. VENDOR CONTROL CENTER — one per-vendor config (handoff #, AI-Manager #, WhatsApp report #, plan,
     phone numbers, provider-cred refs, retention policies, compliance) editable from the panel and
     live across workers/schedulers/agents WITHOUT redeploy.
        profile.VendorProfile / VendorProfileStore

  3. FUTURE-READY WHATSAPP — blank-but-present fields that activate when creds are added later
     (profile.WhatsAppConfig.is_active).

  4. PER-TENANT RETENTION/STORAGE — independent recording vs transcript TTLs + storage quota + the
     archive/delete knobs the W9 (env-global) retention sweep reads (profile.RetentionPolicy).

REAL-TIME MECHANISM — store.ConfigStore: every config doc is VERSIONED + FORCE-RLS + tenant-scoped;
a write bumps the version (atomic UPSERT) and emits a W8 `config_changed` event. Readers self-
invalidate a stale cache on a cheap version poll (belt) and push-consumers refresh on the event
(suspenders). No redeploy, ever.

SECURITY: every secret is AAD-bound AES-256-GCM encrypted at rest (vault.py, self-contained re-impl
of the W4 provider_registry vault posture); plaintext never hits disk / a row / a log / an event.
Cross-tenant ciphertext fails closed (InvalidTag). FORCE-RLS on every table.

IMPORT ISOLATION: `import voice_ops.config` pulls ZERO droplet_work, ZERO agent.py/caller.py, ZERO
sqlalchemy/redis/cryptography at module load — every such import is LAZY (inside a function). Safe to
load on any host / in CI.
"""
from __future__ import annotations

from . import events, keyhealth, keys, profile, router_bridge, store, vault
from .events import set_event_bus
from .keyhealth import HealthScoredKeyPool, KeyHealth
from .keys import KNOWN_PROVIDERS, ProviderKeyStore
from .profile import (
    ComplianceSettings,
    RetentionPolicy,
    VendorProfile,
    VendorProfileStore,
    WhatsAppConfig,
)
from .router_bridge import KeyRouter, LiveProviderRouter, ResolvedKey, build_w5_router
from .store import ConfigSnapshot, ConfigStore, InMemoryBackend, set_backend_for_tests
from .vault import VaultError, decrypt_secret, encrypt_secret, fingerprint, mask

__all__ = [
    # sub-packages
    "vault", "keyhealth", "store", "keys", "profile", "events", "router_bridge",
    # vault
    "encrypt_secret", "decrypt_secret", "mask", "fingerprint", "VaultError",
    # health pool
    "HealthScoredKeyPool", "KeyHealth",
    # config store
    "ConfigStore", "ConfigSnapshot", "InMemoryBackend", "set_backend_for_tests",
    # keys
    "ProviderKeyStore", "KNOWN_PROVIDERS",
    # vendor control center
    "VendorProfile", "VendorProfileStore", "RetentionPolicy", "ComplianceSettings", "WhatsAppConfig",
    # router bridge
    "KeyRouter", "LiveProviderRouter", "ResolvedKey", "build_w5_router",
    # events
    "set_event_bus",
]
