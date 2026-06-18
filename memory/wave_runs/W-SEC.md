# W-SEC — Voice-kernel security hardening (W19 / W21 / W22 / W23) + red-team fold

**Branch:** `fix/realtime-voice-kernel-v2`
**Date:** 2026-06-18
**Discipline:** DISJOINT tracked code only. NO live box / agent.py / caller.py / auth.py / W20 legacy_gate
mutation. Pure additive library + flag-gated SEAMs. Earner law honored (OUTBOUND live=76a93f0a).

---

## What shipped

Four security axes, mapped to the actual tracked layout on this branch (NOT the literal
`{egress,firewall,routes_ci,keys}/` subdir shape the prompt assumed):

| Axis | Wave | Real path(s) | State |
|---|---|---|---|
| EGRESS (toll-fraud / denial-of-wallet cap) | W19 | `voice_ops/concurrency/{budget,slots,admission}.py` | tracked (prior wave) |
| FIREWALL (privileged-action step-up + legacy gate) | W21 | `voice_ops/security/{legacy_gate,principal}.py` | tracked (W20/W21) |
| ROUTES_CI (tenant-unsafe route gate) | W22 | `voice_ops/security/route_auth_assert.py` | tracked (prior wave) |
| KEYS (purpose-key split / vault) | W23 | `voice_ops/security/keys/` (purpose, keyring, service_tokens, oauth_vault, runbook) | **NEW — landed this commit** |

The only NEW tracked code in this commit is `voice_ops/security/keys/` (the W23 key-management
library, 48 tests) + its SEAM doc `design/W-SEC-keys-SEAM.md`. The other three axes were already
tracked; this wave is their adversarial red-team FOLD + the keys landing.

---

## Red-team verdict: SHIP. No blockers.

153/153 security+concurrency tests green via direct adversarial probing (attack, not just read).
No live box, agent.py, caller.py, or W20 legacy_gate touched. Full `voice_ops/` = 509 passed;
`voice_kernel/` = 367 passed.

### EGRESS — `concurrency/{budget,slots,admission}.py`
- Hard cap refuses past capacity (T,T,T,F,F). `give_back` clamps to capacity → a spam-refund loop
  cannot mint free budget. `take(-n)` / `take(0)` are no-ops (no negative-credit escape). Capacity-0
  pool/bucket always refuses.
- Wallet integrity: a refused admit fully rolls back the LLM token (no leak); a successful admit
  DEPLETES it; `release()` frees slots but does NOT refund the spent token → a `reserve→release` loop
  cannot mint unlimited free calls. Rollback on first-refusal is exact (no slot/token leak).
- Admission E2E: distinct 2nd call hits the global cap (QUEUE); per-tenant LLM burst exhaustion →
  PACE/`llm_tenant`. Cap not bypassable by lease-id collision (identical call_id self-DoSes to one
  slot; distinct calls get distinct slots).
- DESIGN NOTE (not a blocker): `CONCURRENCY_ENABLED` defaults OFF; `AdmissionController.reserve()` is
  pure and enforces regardless of the flag. The cap only protects the wallet once the dial-loop SEAM
  actually calls it — until that seam lands, the live loop is uncapped. The module has no bypass; the
  gap is the seam. → ACTION in the seam wave.

### FIREWALL — `security/{legacy_gate,principal}.py`
- `legacy_pw` on `/admin/*` rejected in EVERY mode (off/transition/on) — privileged plane never
  regresses. Unknown/garbage mode fails CLOSED to OFF. `LEGACY_TOKEN_ENABLED=true` → TRANSITION
  (allow+audit), not silent ON. No-env default = OFF.
- Both retirement legs closed: direct bearer (`enforce`→401) AND the password→token mint
  (`legacy_login_mint_allowed`=False at OFF). Real JWT/Logto/service always pass (earner not
  over-blocked). No bypass found.

### ROUTES_CI — `security/route_auth_assert.py`
- NEGATIVE CONTROLS PASS: a route declaring `accepts=LEGACY_PW` is CAUGHT (`RouteAuthViolation`);
  `requires_tenant_auth=False` is CAUGHT. Real W8–W16 surface: 21/21 legacy-denied at mode OFF,
  21/21 JWT-allowed. The gate catches the unsafe case, not just the safe one.

### KEYS — `security/keys/{keyring,purpose,service_tokens,oauth_vault}.py`
- One purpose-key CANNOT forge another: a `JWT_ACCESS` MAC fails under `STEP_UP`/`SERVICE`;
  version-confusion (v1 MAC under v2) fails; HKDF domain-separation holds. Header-swap / alg-confusion
  (`alg=none`, `kid` rewrite) rejected (verify uses the fixed SERVICE key, ignores attacker header);
  payload `purpose` downgrade rejected. Empty master → `KeyManagerError`, never a weak fallback key.
- No plaintext secret anywhere: master never in any repr/handle/fingerprint; service-token string
  carries no master; `VaultedToken` repr / `to_record()` carry no plaintext. oauth_vault crypto
  verified with real `cryptography`: cross-tenant AND cross-provider ciphertext is non-portable
  (InvalidTag→`OAuthVaultError`); the `oauth:` namespace stops an OAuth blob being opened as a provider
  API key. 200 minted tokens → 200 distinct jti.

---

## ONE RESIDUAL TO TRACK (documented, not a flaw)

Service tokens are stateless-replayable within their ≤600s TTL — `verify_service_token` accepts the
same token twice. The module documents jti as "OPTIONALLY" receiver-deduped. **The patch DOC wiring
receivers (caller / hatchet) MUST mandate jti-dedup within the TTL window**, or a captured short-lived
service token can be replayed until expiry. Containment is already strong (≤120s default TTL, aud+scope
bound), so the window is hard. → ops/seam action.

---

## Verification evidence

- `python -m pytest voice_ops/security/ voice_ops/concurrency/ -q` → **153 passed** (3.0s)
- `python -m pytest voice_ops/ -q` → **509 passed** (8.2s)
- `python -m pytest voice_kernel/ -q` → **367 passed** (3.5s)
- Local `droplet_work/agent.py` snapshot md5 `6c577b9b688169419895909052c08365` — UNCHANGED.
- caller.py / auth.py — no working-tree changes (only untracked scratch copies under `.boxwork/` etc.).
- gitleaks: 0 (no secrets committed; keys/ heuristic scan clean — no key bytes, no plaintext).
- Staged ONLY: `voice_ops/security/keys/` + `design/W-SEC-keys-SEAM.md` + `memory/wave_runs/W-SEC.md`
  + the `WORKFLOW_LEDGER.md` append. Never `git add -A`. ORCHESTRATOR.md NOT touched.

---

## FOUNDER / OPS ACTIONS (gated — apply behind flags, family-by-family)

1. **Apply the W23 key-split SEAM** (`design/W-SEC-keys-SEAM.md`) family-by-family behind
   `KEYS_SPLIT_ENABLED` (default OFF). Order: non-privileged first, **firewall step-up last/highest-value**.
   caller.py must stay byte-identical until the flag is ON. Each flip: before/after fingerprint smoke.
2. **Mandate jti-dedup at the service-token receivers** (caller `/run`, hatchet worker→caller) within
   the TTL window — closes the only residual (short-lived replay).
3. **Land the dial-loop admission SEAM** so the W19 cap actually protects the live wallet (today the
   controller is correct but uncalled when `CONCURRENCY_ENABLED=0`). Until then the live loop is uncapped.
4. **Migrate OAuth/WABA refresh tokens** out of any `var/*.json` plaintext into `seal_oauth_token(...)`
   (AAD AES-GCM vault), persisted in the FORCE-RLS config store.
5. **Rotation runbook is ready** (`runbook.py`): per-purpose rotation is contained (only that family
   logs out); master rotation = full platform logout (suspected master compromise only). All
   secret-free (fingerprints only).
