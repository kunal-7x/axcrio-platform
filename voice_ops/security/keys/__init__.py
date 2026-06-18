"""voice_ops.security.keys — W23 KEY-MANAGEMENT: split the single shared signing secret by PURPOSE.

THE W18/W23 FINDING (design/control-security.md:327-329): ONE secret (`var/secret`) signs FOUR token
families — legacy HMAC panel token, JWT access, firewall step-up, provider-reveal step-up — all with
the SAME key. A leak/forgery in one family is a leak in ALL. W23 splits the key by PURPOSE so a JWT
key can't forge a step-up token, adds short-lived SCOPED inter-service tokens, and VAULTS OAuth/WABA
refresh tokens (AAD AES-GCM) instead of leaving them in `var/*.json`.

  purpose.py         The closed KeyPurpose enum (jwt-access / jwt-refresh / legacy-hmac / step-up /
                     reveal-step-up / service) + the 1:1 map to each live signer (LIVE_SEAM) + which
                     purposes collide on the shared secret today (COLLIDING_TODAY).

  keyring.py         Derives a DISTINCT HMAC key per purpose+version from one master via HKDF-SHA256
                     domain separation, and signs/verifies under it. A MAC made under one purpose
                     fails verify under any other — the containment guarantee. Key bytes never leave.

  service_tokens.py  Short-lived (<=600s), audience-bound, scope-bound inter-service tokens signed
                     under the SERVICE purpose key only. Replaces long-lived/legacy-password loopback
                     auth (AIM, retry/callback scheduler, Hatchet).

  oauth_vault.py     Seals OAuth/WABA refresh tokens through the SAME AAD AES-256-GCM vault the
                     provider keys use (voice_ops.config.vault) — at-rest encrypted, tenant-bound,
                     NEVER var/*.json plaintext. Lazy vault import.

  runbook.py         Per-purpose rotation (bump one version, contained), master rotation (full
                     logout), and the one-time split migration plan — all secret-free (fingerprints
                     only), reusing the W20 CSPRNG rotation primitive.

caller.py / auth.py / firewall.py are NOT edited here — the family-by-family flip ships as the patch
DOC design/W-SEC-keys-SEAM.md.

IMPORT ISOLATION: `import voice_ops.security.keys` pulls pure stdlib. The config vault (cryptography)
is imported LAZILY only when an OAuth token is actually sealed/opened; the W20 rotation primitive only
inside master rotation. ZERO droplet/caller/auth/firewall at module load. Safe on any host / in CI.
"""
from __future__ import annotations

from . import keyring, oauth_vault, purpose, runbook, service_tokens
from .keyring import (
    DEFAULT_GET_MASTER,
    KeyHandle,
    KeyManagerError,
    Keyring,
)
from .oauth_vault import (
    OAuthVaultError,
    VaultedToken,
    open_oauth_token,
    open_record,
    seal_oauth_token,
)
from .purpose import (
    COLLIDING_TODAY,
    LIVE_SEAM,
    KeyPurpose,
    all_purposes,
)
from .runbook import (
    RotationPlan,
    RotationStep,
    rotate_master,
    rotate_purpose,
    split_migration_plan,
)
from .service_tokens import (
    DEFAULT_TTL_SECONDS,
    MAX_TTL_SECONDS,
    ServiceClaims,
    ServiceTokenError,
    mint_service_token,
    verify_service_token,
)

__all__ = [
    # sub-modules
    "purpose", "keyring", "service_tokens", "oauth_vault", "runbook",
    # purpose
    "KeyPurpose", "LIVE_SEAM", "COLLIDING_TODAY", "all_purposes",
    # keyring
    "Keyring", "KeyHandle", "KeyManagerError", "DEFAULT_GET_MASTER",
    # service tokens
    "mint_service_token", "verify_service_token", "ServiceClaims", "ServiceTokenError",
    "DEFAULT_TTL_SECONDS", "MAX_TTL_SECONDS",
    # oauth vault
    "seal_oauth_token", "open_oauth_token", "open_record", "VaultedToken", "OAuthVaultError",
    # runbook
    "rotate_purpose", "rotate_master", "split_migration_plan", "RotationPlan", "RotationStep",
]
