# W20 — Legacy Token Retirement (voice_ops/security/) — BUILD STATE

Branch: `fix/realtime-voice-kernel-v2`. DISJOINT tracked code. 0 droplet/agent imports (lazy).
NEVER edit live caller.py/auth.py — caller.py/auth.py changes ship as a PATCH DOC only.

## DELIVERABLES (founder ask)
1. Legacy-auth REJECTION layer + `LEGACY_TOKEN_ENABLED` gate (default toward OFF) — when off, legacy_pw
   rejected EVERYWHERE; forces proper JWT/Logto auth. — `legacy_gate.py`
2. Assertion that every NEW operational route (W8–W16) requires real tenant auth (`resolve_tenant`),
   NEVER the legacy token. — `route_auth_assert.py`
3. Secret-ROTATION helper + docs-scrub list (NEVER print the secret value). — `rotation.py`, `docs_scrub.py`
4. PATCH DOC for caller.py/auth.py (no live edit). — `design/W20-LEGACY-TOKEN-RETIREMENT.md` (runbook) +
   `voice_ops/security/PATCH-caller-auth.md`
5. pytest (mock auth): gate-off rejects legacy_pw (401) / JWT passes / new routes deny legacy;
   gate-on (transition) legacy works but logged deprecated; rotation invalidates old.

## PROGRESS — ALL DONE
- [x] explore conventions (config/vault/events/taxonomy)
- [x] security/__init__.py  (clean API; import pulls 0 droplet/heavy modules — asserted)
- [x] security/principal.py
- [x] security/legacy_gate.py  (default OFF; OFF/TRANSITION/ON; admin always excluded; fail-soft audit)
- [x] security/route_auth_assert.py  (W8–W16 manifest + 21 legacy-reachable routes)
- [x] security/rotation.py  (CSPRNG; never leaks plaintext; old-token-invalidation verify)
- [x] security/docs_scrub.py  (refs + fingerprint, never the literal)
- [x] security/tests/test_legacy_gate.py / test_route_auth_assert.py / test_rotation.py
- [x] security/PATCH-caller-auth.md
- [x] design/W20-LEGACY-TOKEN-RETIREMENT.md
- [x] memory/wave_runs/W20-legacy-token.md

## RED-TEAM FOLD (W20 VERIFY+COMMIT — 3 blockers fixed before ship)
- [x] BLOCKER 1 (CRITICAL bypass): the password also mints a real admin JWT at /auth/login
  (`_verify_password_for_auth`), which the gate then always allows. FIX: added
  `legacy_gate.legacy_login_mint_allowed()` (OFF -> mint refused) + PATCH §2b gating
  `_verify_password_for_auth`/`/auth/login` at OFF + 4 mint-gate tests incl. the both-paths invariant.
- [x] BLOCKER 2 (overstated claim): OFF does NOT invalidate hmac/JWT tokens ALREADY minted from the
  password — only Phase-3 HMAC-secret rotation does. FIX: corrected the language in __init__.py,
  legacy_gate.py, the runbook (new "what OFF retires" table, paths a/b/c/d) + wave-log; made Phase-3
  rotation a HARD ship-gate of the "retired" claim.
- [x] BLOCKER 3 (secret committed): scrubbed every contiguous legacy-password literal from the 6
  module/doc files (now by reference/fingerprint); test files reconstruct it from fragments; added a
  self-test asserting no package module/doc embeds the literal. gitleaks staged-scan = 0.
- [x] pytest: 53 security tests pass (was 48; +5); full voice_ops + voice_kernel = 779 passed, 0
  regressions. Import isolation re-asserted (0 droplet/heavy imports). droplet_work untouched.
