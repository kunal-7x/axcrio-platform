# W-SEC-keys — Key-Management SEAM (W23)

**Status:** TRACKED library shipped + green; live signers (`caller.py` / `auth.py` / `firewall.py`)
NOT edited — this DOC is the family-by-family flip the operator applies behind a flag.

**Library:** `voice_ops/security/keys/` (droplet-free, 48 tests green, 0 droplet/agent imports at load)

---

## 1. The finding (what W23 closes)

`design/control-security.md:327-329` + the W18 sweep: **ONE shared signing secret (`var/secret`) signs
FOUR distinct token families with the SAME key.** A leak/forgery in one family = a leak in all.

| Token family | Live signer (file:line) | Today's key |
|---|---|---|
| Legacy HMAC panel token | `caller.py:622-623` `_make_token()` | `var/secret` (raw) |
| JWT access (HS256) | `auth.py:104-115` `_make_access()` | `var/secret` (raw) |
| JWT refresh | `auth.py:118-126` `_make_refresh()` | opaque random id (not signed today) |
| Firewall step-up | `firewall.py:267-274` `mint_step_up()` | `var/secret` (raw) |
| Provider-reveal step-up | `firewall.py:419-434` `mint_reveal_step_up()` | `var/secret` (raw) |

All resolve `SECRET` loaded once at `caller.py:584`, handed identically to `auth.init(secret=SECRET)`
(`caller.py:1062`) and `firewall.init(secret=SECRET)` (`caller.py:1085`).

Separately: long-lived **OAuth/WABA refresh tokens** risk `var/*.json` plaintext — the crown jewels.

---

## 2. What the library gives you

```
voice_ops/security/keys/
  purpose.py         KeyPurpose enum (jwt-access / jwt-refresh / legacy-hmac / step-up /
                     reveal-step-up / service) + LIVE_SEAM (1:1 map to each signer) + COLLIDING_TODAY
  keyring.py         Keyring: derive a DISTINCT HMAC key per (purpose, version) from ONE master via
                     HKDF-SHA256 domain separation; sign()/verify() under a purpose. A MAC made under
                     purpose A FAILS verify under purpose B  ← the containment guarantee
  service_tokens.py  mint/verify short-lived (<=600s) audience+scope-bound inter-service tokens,
                     signed under the SERVICE key only
  oauth_vault.py     seal/open OAuth/WABA refresh tokens via the SAME AAD AES-256-GCM vault the
                     provider keys use (voice_ops.config.vault) — at-rest encrypted, NOT var/*.json
  runbook.py         per-purpose rotation (contained), master rotation (full logout), split-migration
```

**Containment property (proven, `test_keyring.py::test_jwt_key_cannot_forge_a_step_up_token`):**
a holder of the JWT-access key cannot mint or verify a step-up token, and vice-versa.

---

## 3. How the split works (no new secret to provision)

The box already distributes ONE master (`var/secret` / the keystore env). `Keyring` derives a
distinct 32-byte key per purpose via **HKDF-SHA256** with `info = "famit/security/keys/v1|<purpose>|v<version>"`.
Different purpose label ⇒ different bytes; HKDF is one-way ⇒ one purpose's key reveals nothing about
another's. Per-purpose rotation = bump that purpose's `version` (no other purpose changes).

`KEYRING_MASTER_SECRET` (or `FAMIT_SIGNING_MASTER` / the existing keystore envs) feeds the master. To
keep the migration drop-in, `Keyring.legacy_compat_key_fingerprint()` is the fingerprint of the RAW
master — proves "before flip all families share THIS fp; after flip each has its own."

---

## 4. The PATCH (apply family-by-family, non-privileged first)

> **Discipline:** one signer family at a time, each behind `KEYS_SPLIT_ENABLED` (default OFF), each
> with a transition window that still VERIFIES old tokens, each with the before/after fingerprint
> smoke. Never flip all five at once. caller.py md5 must be byte-identical until the flag is ON.

### 4a. Wire the keyring once (caller.py, near `caller.py:584` / `:1056`)

```python
# additive, after SECRET = _load_secret()
from voice_ops.security.keys import Keyring, KeyPurpose
KEYS_SPLIT_ENABLED = os.environ.get("KEYS_SPLIT_ENABLED", "0") == "1"
_KEYRING = Keyring(get_master=lambda: SECRET.encode("utf-8"))  # same master, derived per-purpose
```

### 4b. `auth.py` — access JWT (`_make_access` 104-115, `resolve_token` 153, `access_claims` 169)

Add an optional `keyring` to `auth.init(...)` (called at `caller.py:1062`). When set + flag ON, sign
with the derived key; verify accepts BOTH (derived, then raw) during the transition:

```python
# _make_access: sign under the JWT_ACCESS key when split is on
if _KEYRING is not None:
    return _sign_hs256_with(payload, _KEYRING_access_key())   # purpose=jwt-access
return _jwt.encode(payload, _SECRET, algorithm=ALGO)          # legacy raw (transition + OFF)

# resolve_token / access_claims: try derived key first, then fall back to _SECRET (transition window)
```

(PyJWT signs with raw bytes; to keep PyJWT, derive the per-purpose bytes via the keyring's internal
derivation exposed for this seam, OR move access-token signing to the keyring's `sign/verify` which is
the same HMAC-SHA256 primitive HS256 uses. Either is byte-shape-compatible.)

### 4c. `firewall.py` — step-up (`mint_step_up` 267, `verify_step_up_token` 284, `require_step_up`
329) and reveal (`mint_reveal_step_up` 419, verify 453)

Same shape: `firewall.init(...)` (`caller.py:1085`) gains an optional `keyring`; mint signs under
`KeyPurpose.STEP_UP` / `KeyPurpose.REVEAL_STEP_UP`; verify tries derived then raw during transition.
**This is the highest-value flip** — after it, a step-up-key compromise no longer forges an access JWT
(the exact `control-security.md:327-329` recommendation).

### 4d. `caller.py` — legacy HMAC (`_make_token` 622-623) **[W20-retired]**

This family is being retired by W20. If still present at flip time, sign it under
`KeyPurpose.LEGACY_HMAC` so it is isolated from the access key until W20 removes it entirely.

### 4e. Inter-service tokens (NEW — no live signer today)

Replace legacy-password / long-lived loopback auth on the AIM loopback, the retry/callback scheduler,
and the Hatchet worker→caller path with `mint_service_token(...)` / `verify_service_token(...)`:

```python
# minting side (e.g. the scheduler about to call caller.py /run)
tok = mint_service_token(_KEYRING, issuer="scheduler", audience="caller",
                         scope="dial", subject=tenant_id, ttl_seconds=120)
# receiving side (caller.py route)
claims = verify_service_token(_KEYRING, tok, expected_audience="caller", required_scope="dial")
if claims is None:  # fail-closed
    return forbidden()
```

Short-lived (≤600s), audience-bound, scope-bound, signed under the SERVICE key only.

### 4f. OAuth/WABA refresh tokens → vault (replace any `var/*.json` plaintext)

At store time: `seal_oauth_token(tenant_id, "whatsapp", refresh_token)` → persist `.to_record()` in
the FORCE-RLS `config_state` store (same pattern as `voice_ops.config.keys`). At use time:
`open_oauth_token(...)` / `open_record(...)`. Cross-tenant blobs fail closed (AAD InvalidTag).

---

## 5. Rotation runbook (per-purpose, contained)

```python
from voice_ops.security.keys import rotate_purpose, rotate_master, split_migration_plan
plan = rotate_purpose(_KEYRING, KeyPurpose.STEP_UP)   # bump step-up v1->v2; ONLY step-up tokens die
print(plan.as_text())                                 # operator steps; fingerprints only, no secret
```

- **rotate_purpose(p)** — bump one purpose's version. Contained: only that family logs out; all other
  families keep working. Smoke: a token at v1 must FAIL verify at v2 (other purposes' fingerprints
  unchanged across the bump).
- **rotate_master()** — replace the master (suspected master compromise). Re-derives ALL purposes =
  full platform logout. Reuses the W20 CSPRNG primitive (`rotate_hmac_signing_secret`) — the fresh
  master is revealed ONLY via `.reveal()` piped into the secret store, never logged.
- **split_migration_plan()** — the one-time flip plan (non-privileged purposes first, privileged
  last), each step naming its live seam.

**Secret hygiene:** no plan/handle/record/repr ever contains a secret or key byte — only fingerprints
+ masks. Verified by `test_runbook.py::test_no_plan_leaks_secret_bytes` and the no-leak tests across
every module.

---

## 6. Rollback

The library is additive + flag-gated (`KEYS_SPLIT_ENABLED` / `KEYS_SERVICE_TOKENS_ENABLED` default
OFF). With the flags OFF, every signer uses the raw master exactly as today → caller.py byte-identical
at rest. Rollback = set the flag OFF + restart; no data migration (derived keys are computed, not
stored). OAuth-vault rows are forward-only (encrypted) and decryptable as long as the keystore master
is unchanged.

---

## 7. Test evidence

`python -m pytest voice_ops/security/keys/tests/ -q` → **48 passed**. Covers: purpose separation
(JWT key can't forge step-up, every purpose a distinct key, version isolation), service tokens
(aud/scope binding, TTL ceiling + expiry, purpose isolation, tamper/replay fail-closed, cross-master
reject), OAuth vault (roundtrip, cross-tenant/cross-provider fail-closed, plaintext never in
record/repr, no filesystem write), runbook (contained rotation, master-invalidates-all, migration
ordering, no secret leak). Import isolation: 0 droplet/agent/cryptography/sqlalchemy at module load
(vault + rotation imported lazily).
