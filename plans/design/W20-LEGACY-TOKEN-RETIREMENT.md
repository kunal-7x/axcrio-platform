# W20 — Legacy Static-Token Retirement (gated-flip runbook)

**Status:** code + tests built (`voice_ops/security/`, 48 tests, full suite 686 green). The live flip
is a **gated deploy** — NOT done by this wave. caller.py/auth.py changes ship as a PATCH DOC
(`voice_ops/security/PATCH-caller-auth.md`), never edited from this branch.

## The finding (W18 MD1 / NEW-W20, per `design/control-security.md` #1)
The legacy static password (`CALLER_PASS`) is a **permanent, un-revocable bearer token**. It
authenticates **every** vendor route platform-wide because `resolve_tenant` accepts it, so **every new
W8–W16 operational route is born reachable by it.** This **gates the safe deploy of the operational
route surface.** It must be retired: gate OFF → reject legacy_pw everywhere → rotate the secret →
scrub the docs. Flag-gated + reversible; the flip is a gated deploy with a real access smoke
before/after.

## Routes that were legacy-reachable (the surface this unblocks)
From `voice_ops.security.route_auth_assert.legacy_reachable_route_paths()` (21 operational, non-admin):
`/callbacks`, `/usage`, `/usage/all`, `/ads/campaigns`, `/ads/insights`, `/aim/sessions`,
`/aim/command`, `/providers/custom`, `/media/generate`, `/media/assets`, `/booking/appointments`,
`/funnels`, `/forms`, `/whatsapp/send`, `/comm/messages`, `/inbound/sessions`, `/billing/vendors`,
`/billing/explorer`, `/leads/hot`, `/contacts`, `/tenants/{tid}/limits`.
The `/admin/*` plane was **already** legacy-excluded (`require_super_admin`) — the gate keeps it
excluded in every mode.

## What "OFF" actually retires (honest invariant — red-team W20 fold)

The legacy password has **three** reach-paths, not one. `LEGACY_TOKEN_MODE=off` closes the first three
*mint/bearer* paths; it does **NOT** retroactively kill tokens already issued from the password.

| reach-path | closed by | PATCH |
|---|---|---|
| (a) direct bearer on `resolve_tenant` | gate OFF | §1 |
| (b) `/login` → mint an **hmac panel token** | gate OFF (new mints) | §2 |
| (c) `/auth/login` → mint a **real admin JWT** (`_verify_password_for_auth`) | gate OFF (new mints) | §2b |
| (d) hmac/JWT tokens **already minted** from the password before the flip | **only Phase-3 HMAC-secret rotation** | §4 |

So the precise claim is: **OFF retires the password as a direct bearer + closes all new privileged-token
mints from it; the credential is FULLY retired only after Phase-3 HMAC `SECRET` rotation (which
invalidates every already-minted hmac/panel token).** Do NOT describe OFF as "rejects legacy
everywhere" — path (d) survives OFF until rotation. **Phase 3 rotation is therefore a HARD ship-gate of
the "legacy retired" claim, not an optional later phase.**

## The three modes (`LEGACY_TOKEN_MODE`)
| mode | legacy_pw bearer (resolve_tenant) | password→JWT/`/login` mint | /admin/* | use |
|---|---|---|---|---|
| `off` | **rejected (401)** | **rejected (no new mint)** | rejected | **target end-state** (path (d) needs Phase 3) |
| `transition` | allowed + audited (`auth.legacy_token_used`, deprecated) | allowed + deprecation-logged | rejected | migration window |
| `on` | allowed silently | allowed silently | rejected | pre-W20 status quo (do not ship) |

Back-compat: the existing `LEGACY_TOKEN_ENABLED=true` maps to **TRANSITION** (allow + audit), not
silent ON — so even before any env change, applying the patch produces the deprecation trail.

---

## PHASE 1 — pre-cutover (no behavior change yet)
1. Apply `PATCH-caller-auth.md` §0–§1 (wire the gate into `resolve_tenant`). With
   `LEGACY_TOKEN_ENABLED=true` the gate resolves TRANSITION → **byte-behavior-identical** plus the
   audit event. Deploy. Smoke (below) should be unchanged.
2. **Fix the AIM loopback (BLOCKER, §3):** provision `AIM_SERVICE_TOKEN` (a real JWT / Logto service
   credential) and point `voice_tools.py` + `ai_manager_voice_tools.W2.py` at it. Without this, an OFF
   flip 401s every AIM voice-tool call → **earner breaks.** Verify an inbound AIM call still executes a
   tool after this change.
3. Migrate the panel frontend to `/auth/login` (JWT) so active sessions carry a real revocable token
   before the flip. Apply patch §2 (gate `/login`) **and §2b (gate the password→JWT mint in
   `_verify_password_for_auth` / `/auth/login`)** — §2b is the CRITICAL path: without it, OFF still
   lets the legacy password be exchanged for a real admin JWT, which the gate then always allows.

## PHASE 2 — the gated flip (one box-mutating change + revert path)

**ACCESS SMOKE — BEFORE (record outputs):**
```bash
# legacy bearer still works in TRANSITION (expect 200)
curl -s -o /dev/null -w '%{http_code}\n' -H "X-Auth: $LEGACY_PW" https://<box>/api/usage          # 200
# a real JWT works (expect 200) — the earner path
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $REAL_JWT" https://<box>/api/usage  # 200
# an operational route reachable by legacy today (expect 200 in TRANSITION)
curl -s -o /dev/null -w '%{http_code}\n' -H "X-Auth: $LEGACY_PW" https://<box>/api/callbacks      # 200
# place ONE real outbound/inbound call -> rings + AIM tool executes (earner alive)
```

**FLIP** (on the box `/opt/famit-agent/.env`):
```
LEGACY_TOKEN_MODE=off
```
Restart the service.

**ACCESS SMOKE — AFTER (the proof):**
```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "X-Auth: $LEGACY_PW"  https://<box>/api/usage     # 401  (dead)
curl -s -o /dev/null -w '%{http_code}\n' -H "X-Auth: $LEGACY_PW"  https://<box>/api/callbacks # 401  (dead)
# CRITICAL (§2b): the legacy password can no longer be EXCHANGED for a JWT (expect 401, NOT a token)
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://<box>/api/auth/login -d "password=$LEGACY_PW"  # 401
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://<box>/api/login      -d "password=$LEGACY_PW"  # 401
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $REAL_JWT" https://<box>/api/usage  # 200 (alive)
# place ONE real call -> still rings + AIM tool executes (earner alive on JWT/service auth)
```
If `/auth/login` with the legacy password returns a token instead of 401, §2b was not applied — the
OFF flip is INCOMPLETE (the password can still mint an admin JWT). Note: a token minted BEFORE the flip
still validates until Phase 3 rotation — that is path (d), closed by Phase 3, not Phase 2.
If the earner call FAILS → **revert immediately** (below). The AIM loopback fix (Phase 1.2) is what
keeps the call working at OFF; if it regresses, Phase 1.2 wasn't complete.

## PHASE 3 — rotation (HARD SHIP-GATE of the "retired" claim — close the already-minted-token residual)
**This phase is mandatory, not optional.** OFF (Phase 2) closes new mints (paths a/b/c) but every
hmac/JWT token ALREADY minted from the password (path (d)) keeps validating until the HMAC signing
`SECRET` is rotated. **Do NOT claim the legacy credential is "retired" until Phase 3 is done.** Rotate
(never echo values):
```python
from voice_ops.security.rotation import rotate_caller_pass, rotate_hmac_signing_secret
cp = rotate_caller_pass()           # cp.env_line() -> piped into the secret store, NOT a terminal/log
hs = rotate_hmac_signing_secret()   # invalidates ALL existing HMAC/panel tokens (full logout)
```
- Set the new `CALLER_PASS` + HMAC signing secret in the secret store; restart.
- Rotating the HMAC secret logs everyone out — **expected**; they re-login via SSO/JWT.
- After-smoke: `voice_ops.security.rotation.verify_rotation_invalidates(payload, old, new)` must be
  `True` — an old token no longer validates.

## PHASE 4 — docs scrub
Run `voice_ops.security.docs_scrub.scrub_list()` + `grep_hints()`. Replace every printed literal with a
reference (never the value); fix the source-fallback defaults via the PATCH (caller.py :253,
config.py :19, voice_tools.py, ai_manager_voice_tools.W2.py). Tracked-file hits → a follow-up PR;
gitignored droplet_work + box .env → scrubbed on the box.

---

## ROLLBACK (always one step)
```
# .env on the box:
LEGACY_TOKEN_MODE=transition      # (or remove it; LEGACY_TOKEN_ENABLED=true => TRANSITION)
```
Restart. Legacy bearer works again immediately. (If secrets were already rotated in Phase 3, the OLD
password is gone for good — rollback restores legacy_pw *acceptance*, but the rotated value is the new
secret; keep Phase 2 and Phase 3 as separate gated deploys so each has an independent revert.)

## Earner-safety summary
- `resolve_tenant` JWT path is **never** touched — real auth is unchanged.
- The patch at `LEGACY_TOKEN_ENABLED=true` is behavior-identical (TRANSITION) → safe to deploy ahead
  of the flip.
- The flip is **one** env change with an immediate one-line revert and a real before/after call smoke.
- The AIM loopback service-token (Phase 1.2) is the hard prerequisite — do the OFF flip only after a
  real inbound AIM call executes a tool on the service token.
