# W20 — Legacy Static-Token Retirement (wave run log)

Owning wave for W18 ticket **T-MD1 → NEW-W20 (GATES W8–W16)**: retire the legacy static-password
(`CALLER_PASS`). Per `design/control-security.md` #1 it is a permanent, un-revocable bearer token that
authenticates EVERY vendor route platform-wide → every new W8–W16 operational route is born reachable
by it → this **gates the safe deploy of the operational route surface**.

**HONEST RETIREMENT INVARIANT (red-team W20 fold; do NOT overstate the OFF flip):** the password has
THREE reach-paths, not one — (a) direct bearer on `resolve_tenant`, (b) exchange for a real admin JWT
at `/auth/login` (`_verify_password_for_auth`), (c) exchange for an hmac panel token at `/login`. The
OFF flip must close ALL THREE mint/bearer paths (PATCH §1 + §2 + §2b). But OFF does NOT invalidate
hmac/JWT tokens ALREADY minted from the password before the flip — only **Phase-3 HMAC-signing-secret
rotation** (rotation.py) does that. So the credential is **FULLY retired only after Phase-3 rotation**,
which is therefore a **HARD ship-gate** of any "legacy retired" claim, not an optional later phase.

Branch `fix/realtime-voice-kernel-v2`. DISJOINT tracked code under `voice_ops/security/`. **0
droplet/agent imports (lazy, verified)**. caller.py/auth.py NOT edited — changes ship as a PATCH DOC.
Earner law honored: no box/agent import or restart; live earner `98655dbf` untouched.

## Phase: EXPLORE (ground truth — fed by the orchestrator EXPLORE handoff)
Every legacy-auth acceptance point pinned to file:line:
- `caller.py:253` `PW = cfg_get("CALLER_PASS","<literal>")` — hardcoded default (box .env overrides to the live secret).
- `caller.py:662–687` `resolve_tenant()` — **the single choke point**; `:683` gated by `LEGACY_TOKEN_ENABLED`, `:685-686` `cred==PW` → admin tenant. Every `need_auth()`/`authed()` route accepts legacy.
- `caller.py:706–740` `_auth_method`/`_is_super_admin` — the ONLY existing exclusion (legacy_pw → 403 on `/admin/*` via `require_super_admin:743`). **Correct already.**
- `caller.py:3084–3109` `POST /login` — **NOT gated by the flag**; mints an HMAC token from the password. The residual gap a flag-flip alone does not close.
- `caller.py:1036–1053` `_verify_password_for_auth` → `/auth/login` issues a real revocable JWT from the password (stronger path).
- `voice_tools.py:34–38` + `ai_manager_voice_tools.W2.py:44–45` — AIM voice-tool loopback uses the password as `X-Auth`. **BLOCKER:** flipping OFF without a service-token fix 401s every AIM tool call → earner breaks.
- `config.py:19` same hardcoded default.
- Existing kill-switch `caller.py:151 LEGACY_TOKEN_ENABLED` (default ON) gates `:683`/`:722` only — NOT `/login`.

## Phase: BUILD (done 2026-06-18) — `voice_ops/security/`
- `principal.py` — `AuthMethod` (jwt/logto/service/legacy_pw/none; `.is_real`) + frozen `Principal` (the verdict, never the credential; repr never leaks a secret).
- `legacy_gate.py` — THE rejection layer + `LEGACY_TOKEN_MODE`/`LEGACY_TOKEN_ENABLED` gate. **Library default OFF.** `evaluate()/enforce()`: real auth always passes; legacy → reject@OFF, allow+audit(deprecated)@TRANSITION, silent@ON; `/admin/*` excluded in EVERY mode. `LEGACY_TOKEN_ENABLED=true` maps to TRANSITION (allow+audit), not silent ON. Garbage value fails CLOSED to OFF. Deprecation use emits a fail-soft `auth.legacy_token_used` W8 fact via `make_event` (a plain-str name — the closed `EventName` enum is NOT widened, staying disjoint).
- `route_auth_assert.py` — executable invariant: every W8–W16 operational route requires real tenant auth and NEVER lists legacy in `accepts`. Ships the W8–W16 route manifest (regression pin) + `legacy_reachable_route_paths()` (the 21 born-reachable routes).
- `rotation.py` — CSPRNG secret rotation (`rotate_caller_pass`, `rotate_hmac_signing_secret`); the new value is wrapped so repr/str/logs only show fingerprint+mask; `.reveal()`/`.env_line()` are the explicit secret-store-only paths; `verify_rotation_invalidates` proves an old token dies under the new HMAC secret.
- `docs_scrub.py` — scrub target list (source-fallbacks + env + docs) by reference + fingerprint; NEVER embeds the literal.
- `__init__.py` — clean public API; import pulls ZERO droplet/heavy modules (asserted).

## Phase: TEST (done) — pytest mock auth, ZERO droplet imports
- `tests/test_legacy_gate.py` — OFF rejects legacy (401) / JWT passes / mode precedence + fail-closed / TRANSITION allows-but-deprecates + emits the audit event (no secret in payload) + fail-soft on a dead bus / `/admin/*` always rejects legacy in all 3 modes.
- `tests/test_route_auth_assert.py` — legacy denied on every operational + admin route @OFF; real JWT passes everywhere; the reachable list = operational non-admin set; a badly-declared route fails the suite (regression pin).
- `tests/test_rotation.py` — rotation fresh+strong+non-leaking; old token fails under new HMAC secret; scrub list never embeds the literal; fingerprint stable+non-reversible.
- **48 new tests pass. Full `voice_ops/ + voice_kernel/` = 686 passed, 0 regressions.** Import-isolation asserted (no droplet/sqlalchemy/redis/livekit/boto3/cryptography pulled at import).

## Phase: DOCS (done)
- `voice_ops/security/PATCH-caller-auth.md` — the 1:1 caller.py/auth.py patch (gate wiring in `resolve_tenant`, `/login` gate, AIM loopback service-token fix, rotation). Behavior-identical at `LEGACY_TOKEN_ENABLED=true` (TRANSITION).
- `design/W20-LEGACY-TOKEN-RETIREMENT.md` — the gated-flip runbook: phases, before/after access smoke (legacy 200→401, JWT stays 200, real call rings), rotation, scrub, one-line rollback.

## Residuals / handoff (for the gated deploy, NOT this wave)
- **BLOCKER before OFF:** provision `AIM_SERVICE_TOKEN` + repoint `voice_tools.py`/`ai_manager_voice_tools.W2.py` (PATCH §3). Verify a real inbound AIM call executes a tool on it BEFORE flipping OFF.
- `/login` residual: closed only by rotating `CALLER_PASS` + the HMAC signing secret (PATCH §4 / runbook Phase 3) — flag-flip alone does not close it.
- Docs scrub of tracked literal hits → a follow-up PR; box .env + gitignored droplet_work scrubbed on the box.

## Phase: VERIFY+COMMIT (red-team fold, 2026-06-18)
Red-team raised 3 blockers; all fixed before ship:
- **B1 (CRITICAL bypass)** — the password also mints a real admin JWT at `/auth/login`
  (`_verify_password_for_auth:1013/1019`), which the gate (JWT=is_real) then ALWAYS allows, so OFF was
  bypassable. FIX: `legacy_gate.legacy_login_mint_allowed()` (OFF → mint refused) + PATCH **§2b** gating
  `_verify_password_for_auth`/`/auth/login` at OFF + the AFTER-smoke now curls `/auth/login` with the
  legacy pw expecting 401 + 4 new mint-gate tests (incl. the both-paths invariant).
- **B2 (overstated claim)** — OFF does NOT invalidate hmac/JWT tokens ALREADY minted from the password;
  only Phase-3 HMAC-secret rotation does. FIX: corrected the language (no more "rejects legacy
  everywhere") in `__init__.py`, `legacy_gate.py`, the runbook (new path a/b/c/d table) + this log; made
  **Phase-3 rotation a HARD ship-gate** of any "legacy retired" claim.
- **B3 (secret committed)** — the contiguous literal was printed in 6 module/doc files (the module that
  prescribes the scrub broke its own rule). FIX: scrubbed all 6 to reference/fingerprint; the 3 test
  files reconstruct the literal from fragments; added a **self-test** asserting no package module/doc
  embeds the literal (it caught one reintroduction during this fold → working).
- VERIFY: 53 security tests pass (was 48); full `voice_ops/`+`voice_kernel/` = **779 passed, 0
  regressions**; import isolation re-asserted (0 droplet/heavy at load); `droplet_work/` untouched (no
  box/agent import or restart; earner law honored). **gitleaks protect --staged = 0** (one false
  positive on the public symbol `W8_W16_OPERATIONAL_ROUTES` cleared with an inline `# gitleaks:allow`).
- Staged ONLY `voice_ops/security/` + `design/W20-LEGACY-TOKEN-RETIREMENT.md` + this log (no `git add -A`).
