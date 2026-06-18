# PATCH DOC — caller.py / auth.py legacy-token retirement (W20)

> **DO NOT EDIT THE LIVE FILES FROM THIS WAVE.** This is a documented patch the operator applies as a
> separate, gated deploy with a real access smoke before/after (see
> `design/W20-LEGACY-TOKEN-RETIREMENT.md`). The earner stays untouched until that gated flip.
>
> `droplet_work/` is gitignored — these edits are applied on the box / in a curated copy, not in this
> repo. The logic they call (`voice_ops.security`) IS tracked and unit-tested (686 green).

The patch swaps caller.py's inline legacy-password literals for the tracked, tested
`voice_ops.security` gate. It is **1:1 with the existing behavior when the gate is in TRANSITION mode**,
so applying the patch alone changes nothing observable until the operator flips `LEGACY_TOKEN_MODE`.

---

## 0. Wire the gate once (caller.py startup)

```python
# near the other startup wiring (after the EventBus is built, ~where W8 bus is set)
from voice_ops.security import legacy_gate
legacy_gate.set_event_bus(EVENT_BUS)   # the same RedisEventBus W8 uses; enables the deprecation audit
```

`import voice_ops.security` pulls zero heavy SDKs (verified), so this is safe at module load.

---

## 1. `resolve_tenant()` — the single choke point (caller.py ~:662–687)

**Today** (EXPLORE):
```python
def resolve_tenant(request):
    # ... JWT path first (:675–681) ...
    cred = _bearer_or_header(request)
    if not LEGACY_TOKEN_ENABLED:          # :683
        return None
    if cred == PW:                        # :685-686  <-- accepts the static password EVERYWHERE
        return _tenant_by_id(ADMIN_ID) or ADMIN_TENANT
    return None
```

**Patch** — keep JWT path unchanged; route the legacy branch through the gate so it rejects at mode
OFF, allows+audits at TRANSITION, and stays excluded from /admin/* automatically:
```python
from voice_ops.security import AuthMethod, Principal, legacy_gate
from voice_ops.security.legacy_gate import LegacyTokenRejected

def resolve_tenant(request):
    # ... JWT path first (UNCHANGED) ...
    cred = _bearer_or_header(request)
    if cred and cred == PW:
        principal = Principal(AuthMethod.LEGACY_PW, tenant_id=ADMIN_ID, role="admin", is_admin=True)
        try:
            # route_for_audit = request.url.path; is_admin_route handled by require_super_admin anyway
            legacy_gate.enforce(principal, route=request.url.path, is_admin_route=False)
        except LegacyTokenRejected:
            return None        # -> the route's need_auth() 401s, exactly as before for a bad cred
        return _tenant_by_id(ADMIN_ID) or ADMIN_TENANT
    return None
```
- Mode resolution reads `LEGACY_TOKEN_MODE` / the existing `LEGACY_TOKEN_ENABLED` from the env — no
  new wiring. `LEGACY_TOKEN_ENABLED=true` (today's live value) maps to **TRANSITION** (allow + audit),
  so the deploy is byte-behavior-identical except the deprecation event now fires.
- `_auth_method()` (caller.py :706) and `_is_super_admin()` (:733) are left AS-IS — the /admin/* plane
  is already legacy-excluded by `require_super_admin`; the gate's `is_admin_route` path is belt-and-
  suspenders and never regresses it.

## 2. `POST /login` — the residual gap (caller.py ~:3084–3109)

The flag does **not** gate `/login` today — anyone with the password can still mint an HMAC token.
Add the same gate so the panel login refuses the legacy password at mode OFF:
```python
from voice_ops.security import legacy_gate
from voice_ops.security.legacy_gate import LegacyMode, resolve_mode

@app.post("/login")
def login(...):
    if password == PW and not email:                 # :3093 legacy no-email form
        if resolve_mode() is LegacyMode.OFF:
            raise HTTPException(401, "legacy login retired; use SSO/JWT")
        # else (TRANSITION/ON) mint as before, but log deprecated:
        log.warning("DEPRECATED legacy /login by static password — migrate panel to /auth/login")
        ...
    if email == ADMIN_EMAIL and password == PW:      # :3106 admin-email + PW form
        if resolve_mode() is LegacyMode.OFF:
            raise HTTPException(401, "legacy login retired; use SSO/JWT")
        ...
```
Closing this fully requires **rotating** `CALLER_PASS` + the HMAC signing secret (see §4) — flipping
the flag alone leaves the password usable at `/login` until rotation.

## 2b. `_verify_password_for_auth()` / `POST /auth/login` — the JWT-MINTING bypass (CRITICAL — red-team W20)

> **This is the blocker the §1 choke-point alone does NOT close.** `resolve_tenant` (§1) only rejects
> the password as a *direct bearer*. But `POST /auth/login` → `_auth_mod.login()` →
> `_verify_password_for_auth` (caller.py ~:1004) accepts the bare legacy password (`password == PW`,
> ~:1013) and admin-email+PW (~:1019) and **issues a real, gate-passing admin JWT**. Because the gate
> classifies a JWT as `is_real → ALWAYS allowed (every mode incl. OFF)`, an attacker at
> `LEGACY_TOKEN_MODE=off` does `POST /auth/login` with the legacy password (no email) → mints an admin
> JWT → full operational access. **OFF is NOT achieved until this path is also gated.**

**Today** (EXPLORE, caller.py ~:1004–1019):
```python
def _verify_password_for_auth(email, password):
    if password == PW:                       # :1013  bare legacy password -> admin
        return ADMIN_TENANT, "admin", True
    if email == ADMIN_EMAIL and password == PW:   # :1019 admin-email + legacy password
        return ADMIN_TENANT, "admin", True
    # ... real per-user credential checks ...
```

**Patch** — gate the password→JWT mint at mode OFF exactly like the §2 `/login` path. At OFF the legacy
password can no longer be exchanged for a JWT; real per-user credentials are untouched:
```python
from voice_ops.security.legacy_gate import LegacyMode, resolve_mode

def _verify_password_for_auth(email, password):
    if password == PW and (not email or email == ADMIN_EMAIL):
        if resolve_mode() is LegacyMode.OFF:
            # legacy password is retired; it may no longer mint a JWT.
            raise HTTPException(401, "legacy password retired; use SSO/JWT credentials")
        log.warning("DEPRECATED legacy password used at /auth/login — migrate admin to a real credential")
        return ADMIN_TENANT, "admin", True
    # ... real per-user credential checks (UNCHANGED) ...
```
- At `LEGACY_TOKEN_ENABLED=true` (→ TRANSITION) this still mints the JWT (byte-behaviour-identical),
  just adds the deprecation log → safe to deploy ahead of the flip.
- A `route_auth`/login test (added to `tests/`) asserts: at mode OFF, the legacy password presented to
  the `/auth/login` verify path is REJECTED (no JWT minted); a real credential still mints normally.
- **Together, §1 + §2 + §2b are the full set of password reach-paths.** OFF must close all three to
  stop *new* privileged tokens; already-minted hmac/JWT tokens are killed only by §4 rotation (Phase 3).

## 3. `voice_tools.py` / `ai_manager_voice_tools.W2.py` — the AIM loopback (BLOCKER)

The AI-Manager voice tools call back into caller.py on loopback using the legacy password as `X-Auth`
(`voice_tools.py:34-38`). **If you flip the mode to OFF without fixing this, the AIM voice tools 401
on every loopback call and the earner breaks.** Provision a real service credential first:
```python
# voice_tools.py — replace the `or "<legacy-password-literal>"` fallback with a provisioned service token
_ADMIN_CRED = (os.getenv("AIM_SERVICE_TOKEN") or os.getenv("AIM_CALLER_ADMIN_CRED") or "").strip()
if not _ADMIN_CRED:
    raise RuntimeError("AIM_SERVICE_TOKEN not set — refusing to start without a real loopback credential")
_HEADERS = {"Authorization": f"Bearer {_ADMIN_CRED}"}   # a short-TTL JWT/service token, NOT the password
```
Mint `AIM_SERVICE_TOKEN` as a real JWT via `/auth/login` (or a Logto service credential) so the gate
classifies the loopback as `AuthMethod.SERVICE`/`JWT` (which always passes). This is **Phase-2
pre-cutover work** and is the hard prerequisite for the OFF flip.

## 4. Rotation (caller.py defaults + box .env)

- Remove the hardcoded literal default: `PW = cfg_get("CALLER_PASS")` with a **fail-closed** check
  (`if not PW: raise RuntimeError("CALLER_PASS unset")`) instead of `cfg_get("CALLER_PASS", "<literal>")`
  (caller.py :253, config.py :19).
- Generate the new secrets with `voice_ops.security.rotation` (never echo the value to a terminal/log):
  ```python
  from voice_ops.security.rotation import rotate_caller_pass, rotate_hmac_signing_secret
  cp = rotate_caller_pass()            # -> cp.env_line() piped straight into the secret store
  hs = rotate_hmac_signing_secret()    # rotating this logs everyone out (closes the /login residual)
  ```

---

## Scope of the OFF flip (honest — what §1+§2+§2b+§4 each close)
The legacy password has **three mint/bearer reach-paths plus already-minted tokens**:
- §1 closes (a) the password as a **direct bearer** on `resolve_tenant`.
- §2 closes (b) `/login` minting a new **hmac panel token** from the password.
- §2b closes (c) `/auth/login` (`_verify_password_for_auth`) minting a new **admin JWT** from the
  password — the CRITICAL path, because a JWT is `is_real` and the gate then always allows it.
- §4 (Phase-3 rotation) is the ONLY thing that kills (d) hmac/JWT tokens **already minted** from the
  password before the flip — OFF does not reach those. **The credential is fully retired only after §4.**

Do NOT describe OFF as "rejects legacy everywhere": it closes new mints/bearer; path (d) needs rotation.

## Equivalence guarantee
With `LEGACY_TOKEN_ENABLED=true` (today) → gate resolves **TRANSITION** → legacy still works at §1/§2/§2b
(plus a fire-and-forget `auth.legacy_token_used` audit on the bearer path and a deprecation log on the
mint paths). **No request that worked before fails after the patch.** The behavior change is opt-in via
`LEGACY_TOKEN_MODE=off`, gated by the runbook smoke (which now asserts §2b: the password can no longer
be exchanged for a JWT at OFF).
