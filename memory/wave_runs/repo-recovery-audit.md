# repo-recovery-audit — wave log

> Append each phase's tight conclusion here as it completes.

---

## PHASE 1 — Earner Gate + Full Drift Map (2026-06-14)

### EARNER GATE: ✅ PASS
- **famit-agent PID 1477083**: active (sleeping), NOT restarted
- **agent.py md5**: `9150fabe4ff62b4b4470f9a87df346e5` — CONFIRMED UNCHANGED (matches every prior record)
- **famit-caller /health on :8208**: HTTP 200 `{"status":"ok","agent":"capsy","trunk":"ST_fmtVmNJmpzKa"}`
- **0 5xx** seen in recent journal (last 5min: only 200s and 304s)
- **NO ring triggered** (read-only audit, no call placed)

---

### A. MD5 DRIFT MAP: local droplet_work vs live box /opt/famit-agent

| File | Box md5 | Local droplet_work md5 | Status |
|---|---|---|---|
| `agent.py` | `9150fabe` | `1a154ea1` | 🔴 DIVERGE — local is stale (pre-voice-brain backups). Box = truth. NEVER overwrite from local. |
| `aim_voice_agent.py` | `018c20a7` | `a9eefa8c` | 🔴 DIVERGE — local is old (pre-W4-memory). Box = truth. |
| `aim_voice_agent.LIVEBOX.py` (local copy) | — | `f169d6e1` | 🔴 ALSO STALE vs box `018c20a7` — LIVEBOX golden was not re-pulled after latest deploy. |
| `prompt.py` | `fb87ea56` | `ec5fa971` | 🔴 DIVERGE — box has W1 vendor-script v2 renderer; local is stale pre-W1. |
| `caller.py` | `592e6b94` | `592e6b94` | ✅ MATCH |
| `context_store.py` | `245d864f` | `245d864f` | ✅ MATCH |
| `audit.py` | `190fa1b6` | `190fa1b6` | ✅ MATCH |
| `auth.py` | `a4397f78` | `a4397f78` | ✅ MATCH |
| `firewall.py` | `cd1ac5d1` | `cd1ac5d1` | ✅ MATCH |
| `wallet.py` | `1890d41f` | `1890d41f` | ✅ MATCH |
| `entitlements.py` | `9e483325` | `9e483325` | ✅ MATCH |
| `ratelimit.py` | `ac80252e` | `ac80252e` | ✅ MATCH |
| `obs.py` | `9fa824e4` | `9fa824e4` | ✅ MATCH |
| `bridge.py` | `b15a97b9` | `b15a97b9` | ✅ MATCH |
| `config.py` | `3e1a941f` | `3e1a941f` | ✅ MATCH |
| `store.py` | `2b2b0774` | `2b2b0774` | ✅ MATCH |
| `shadow_diff.py` | `679afb08` | `679afb08` | ✅ MATCH |
| `memory.py` | `cb70e1d7` | `cb70e1d7` | ✅ MATCH |
| `place_call.py` | `752cca73` | `752cca73` | ✅ MATCH |
| `backfill.py` | `cfd53d38` | `cfd53d38` | ✅ MATCH |
| `backfill_contacts.py` | `9e036175` | `9e036175` | ✅ MATCH |
| `langdetect.py` | `622b1807` | `622b1807` | ✅ MATCH |
| `lead_memory.py` | `0ab918f3` | `0ab918f3` | ✅ MATCH |
| `whatsapp.py` | `39006589` | `39006589` | ✅ MATCH (same hash) |
| `seed_kb_from_campaigns.py` | `7eb9caf5` | `7eb9caf5` | ✅ MATCH |
| `kb/__init__.py` | `f6ec3720` | (not in local) | ⚠️ BOX-ONLY (kb/ module exists on box, not tracked locally) |
| `kb/core.py` | `3922266f` | (not in local) | ⚠️ BOX-ONLY |

**`_inbound_ref/` stale reference files (local only, informational):**
| File | Local md5 | Notes |
|---|---|---|
| `_inbound_ref/aim_voice_agent.DEPLOYED.py` | `3152539f` | Stale pre-RAG reference — NOT current box. |
| `_inbound_ref/aim_voice_agent.LIVE.py` | `4bbd0956` | Another stale ref. |
| `_inbound_ref/aim_voice_agent.NEW.py` | `b44a7ae0` | — |
| `_inbound_ref/aim_voice_agent.VERIFY.py` | `a7d5e0ad` | — |
| `_inbound_ref/agent.REFERENCE.py` | `9150fabe` | ✅ Matches live box agent.py — this ref is current. |

---

### B. WHAT'S ON BOX BUT NOT IN LOCAL REPO

| Gap | Details |
|---|---|
| **RAG grounding (kb/ module)** | `kb/__init__.py` + `kb/core.py` + `kb/schema.sql` are DEPLOYED on box. Not tracked in git (droplet_work is gitignored). RAG is LIVE and UNGATED — 3 injection sites in aim_voice_agent.py (:504-516 kb_retrieve wrapper, :1695-1709 pick_campaign re-ground, :2520-2545 connect-prefetch). `kb_chunks` has 63 rows across 3 tenants. |
| **aim_voice_agent.py W4 memory + RAG** | Box `018c20a7` has W4b PG memory read (`LEAD_MEMORY_PG=1` live) + RAG grounding wired. Local `aim_voice_agent.py` is `a9eefa8c` (pre-W4). |
| **prompt.py W1 v2 renderer** | Box `fb87ea56` has `build_system_prompt_v2` (vendor-script adoption). Local `ec5fa971` is pre-W1. |
| **`_golden/` directory** | Box has `/opt/famit-agent/_golden/` with MANIFEST.md, 5 campaign JSON goldens, 5 prompt golden .txt files, and `verify_golden.py`. Not in local repo. |
| **`seed_kb_from_campaigns.py`** | Exists on box (`7eb9caf5`), also exists locally (same md5) — but box has it as part of the deployed stack. |
| **`aim_voice_agent.py` W3b extraction** | Box has PG-outbox memory extraction baked in (W3b wave). `LEAD_MEMORY_PG=1` in .env. |

---

### C. WHAT'S COMMITTED LOCALLY BUT NOT DEPLOYED ON BOX

| Gap | Details |
|---|---|
| **hrd9 isolation-reliability** | Commits `afa309c`, `c7ba982`, `8084e4a` on branch `hrd9-isolation-reliability` are NOT merged to `fe/unify-run-wavec` (the deployed branch). These add: Live Calls monitor, WhatsApp score-gate/brochure, handoff bridge fix, WA pipeline verify, inbound-customer-reframe fix. The hrd9 hardening `caller.py` changes (+68 lines) are committed but may or may not be deployed. **Caller.py local matches box (`592e6b94`) so hrd9 caller changes ARE deployed but the branch was never merged to unify.** |
| **feat/rag-grounding branch** | 2 commits ahead of `fe/unify-run-wavec`: `c9f0dca` (call logging + Egress recording + Call History #8) and `724e5e1` (RAG grounding code). The RAG grounding (aim_voice_agent.py changes) IS deployed on box (box `018c20a7`). The #8 caller.py changes — caller.py local = box (`592e6b94`) so those ARE deployed too. The branch is 2 commits ahead in git but the deployed files already match. |
| **fix/wafx-whatsapp-meta-error-surfacing** | 2 commits: `9b7591f` (Signal Aurora loader FE) and `17d1eb8` (WA real-error surface). These frontend changes not merged to unify-run-wavec. May or may not be on FORTRESS panel. |
| **fix/inbound-customer-reframe** | `5346a23` (inbound reframe) = same as on hrd9 branch. Plus 9 other commits including WhatsApp brochure, Live Calls monitor, handoff bridge, all absorbed into hrd9. |
| **backend/handoff-name-clean-line** (current) | 52 commits ahead of feat/premium-ui. This is the active backend branch. The 2 FE commits unique to fe/unify-run-wavec (fa99acb, 6a63f6e) are NOT on this branch. |
| **`droplet_work/caller.py` local** | Has `592e6b94` — matches box. So W4 memory-read caller changes (sessions API mounting) are deployed. |

---

### D. LIVE FLAG STATE ON BOX .env

| Flag | Value | Intended? | Risk |
|---|---|---|---|
| `LEAD_MEMORY_PG` | `1` (ON) | ✅ YES — W4b memory read is live | Low |
| `CONTROL_ENABLED` | `1` | ✅ YES | Low |
| `FIREWALL_ENABLED` | `true` | ✅ YES | Low |
| `AIM_ENABLED` | `1` | ✅ YES | Low |
| `AIM_RECORDING_ENABLED` | `1` | ✅ YES | Low |
| `FEATURE_*` (forms/support/workflows/booking/funnels/ai_manager/whatsapp/whatsapp_builder) | All `1` | ✅ YES | Low |
| `WORKFORCE_ENABLED` | `1` | ✅ YES | Low |
| `WA_AUTO_FOLLOWUP` | `0` (OFF) | ✅ YES — intentionally off | Low |
| `MEMORY_TENANT_SCOPED` | `1` | ✅ YES | Low |
| `STORE_MODES` | `dual` for all | ✅ YES — P1 PG strangler | Low |
| **`RAG_INJECT_ENABLED`** | **NOT SET (flag does not exist)** | 🔴 NO — RAG is LIVE+UNGATED right now | 🔴 HIGH — no kill switch |
| **`CTX_CACHE`** | **NOT SET** | ⚠️ UNKNOWN — W2 deployed but flag missing from .env | ⚠️ MEDIUM — context cache may be defaulting off |
| **`INBOUND_PROV_LOCK`** | **NOT SET** | ⚠️ UNKNOWN — Wave A committed a "flip INBOUND_PROV_LOCK=1" but it's absent from .env | ⚠️ MEDIUM — provider-lock feature may be defaulting off |
| `VENDOR_SCRIPT_INJECT` | NOT SET (code checks via feature flag indirectly) | ✅ Handled — code uses `build_system_prompt_v2` directly (no env gate needed) | Low |
| `AIM_KB_GROUNDING_CHARS` / `PREFETCH_K` / `LOOKUP_K` | NOT in .env (using code defaults: 1400/5/3) | ✅ OK — defaults are safe | Low |
| `EMBED_API_KEY` | NOT SET | ✅ GOOD — dense embedder off; FTS-only. C-3 constraint satisfied. | Low |

---

### E. RISKY/STALE COPIES — DANGER LIST

1. **`droplet_work/aim_voice_agent.py` (`a9eefa8c`)** — STALE. Any edit starting here and deploying to box would REVERT W4 PG-memory + RAG grounding. NEVER deploy from this. Pull `018c20a7` from box first.
2. **`droplet_work/aim_voice_agent.LIVEBOX.py` (`f169d6e1`)** — ALSO STALE (was pulled at an earlier point, not re-synced after latest deploys). Not a reliable golden.
3. **`droplet_work/prompt.py` (`ec5fa971`)** — STALE. Missing W1 `build_system_prompt_v2`. Deploying this would break vendor-script adoption.
4. **`droplet_work/agent.py` (`1a154ea1`)** — STALE earner. The box has `9150fabe`. Never deploy from local; the earner is the sacrosanct prod file.
5. **`_inbound_ref/aim_voice_agent.DEPLOYED.py` (`3152539f`)** — OBSOLETE reference, pre-RAG. Do not use as a base.
6. **`_inbound_ref/aim_voice_agent.LIVE.py` (`4bbd0956`)** — ALSO OBSOLETE. Do not use as a base.
7. **`caller.py.W4bak.20260614-091316` on box** (`e0b2cf68`) — Pre-W4-caller backup. Different from current box caller.py (`592e6b94`). Keep as rollback only.

---

### F. BRANCH SPRAWL MAP

| Branch | Ahead feat/premium-ui | Behind | Deployed? | Safe to merge to unify? |
|---|---|---|---|---|
| `fe/unify-run-wavec` | +54 | 0 | ✅ YES (FORTRESS panel, BUILD_ID TU16Mn1DcJVmxnxr2GVyL) | — already deployed |
| `backend/handoff-name-clean-line` | +52 | 0 | Partially (backend changes deployed; 2 FE commits from unify missing) | Merge fe/unify-run-wavec into this |
| `feat/rag-grounding` | +2 | 12 | Box files match | Stale — needs rebase onto unify |
| `hrd9-isolation-reliability` | +13 | 12 | Partially (hardening deployed; FE missing) | Needs merge of unify |
| `fix/wafx-whatsapp-meta-error-surfacing` | +2 | 11 | Partial (BE deployed; FE maybe) | Needs merge of unify |
| `fix/inbound-customer-reframe` | +10 | 12 | Partial | Superseded by hrd9 |
| `feat/eval-harness` | +6 | 49 | NO | Behind main — likely stale |
| `main` | 0 | 49 | NO | Behind feat/premium-ui by 49 commits |

---

### G. RECOVERY PLAN

**Priority order (earner-safe, no restarts):**

1. **W0 — RETRO-GATE (first move, before any RAG build):**
   - Pull live box `aim_voice_agent.py` (`018c20a7`) as a new `.LIVEBOX2.py` golden.
   - Add `RAG_INJECT_ENABLED` env-flag kill-switch to `aim_voice_agent.py` (wraps the 3 injection sites).
   - Prove `RAG_INJECT_ENABLED=0` → `grounding=""` → `_build_sales_instructions` byte-identical to no-grounding path.
   - Set `.env` `RAG_INJECT_ENABLED=1` (keeps current behavior on), then restart aim-voice-agent ONLY (not famit-agent earner).
   - Gate: aim-voice-agent health 200 + earner md5 unchanged.

2. **ENV GAPS to fix (safe, no restart for most):**
   - Confirm `CTX_CACHE=1` is in `.env` (W2 was deployed but flag not visible in current env scan — needs verification that the code defaulted it on via the env or it's missing).
   - Confirm `INBOUND_PROV_LOCK=1` is in `.env` (commit `c14d1fe` said "flip it" but it's absent from current live .env scan). If absent, re-add it.

3. **LOCAL REPO SYNC (git discipline):**
   - Pull box `aim_voice_agent.py` → `droplet_work/aim_voice_agent.LIVEBOX2.py` (new golden).
   - Pull box `prompt.py` (`fb87ea56`) → `droplet_work/prompt.LIVEBOX.py` (already exists as `a2c5b0539`? — needs re-check).
   - Update `_inbound_ref/aim_voice_agent.DEPLOYED.py` to point at the current box file OR delete the stale ref.
   - Merge `fe/unify-run-wavec` into `backend/handoff-name-clean-line` (the current active branch) so FE + BE are aligned.

4. **BRANCH CONSOLIDATION (no deploy needed, git only):**
   - `feat/rag-grounding`: rebase onto fe/unify-run-wavec or declare "deployed via box" and close.
   - `hrd9-isolation-reliability`: merge unify FE commits in or declare "partially deployed" and note the gap.
   - `fix/wafx-whatsapp-meta-error-surfacing`: assess if frontend `9b7591f` (Signal Aurora loader) is on FORTRESS already.

5. **WHAT NOT TO TOUCH:**
   - `agent.py` (earner) — NEVER.
   - `caller.py` — currently matching box; no edits until next wave.
   - Any box .env restart without an aim-voice-agent restart-only path.

---

### SUMMARY ONE-LINERS

- **Earner: HEALTHY** — PID 1477083, agent.py `9150fabe`, /health 200.
- **RAG: LIVE+UNGATED** — 3 sites in aim_voice_agent.py, 63 chunks, NO `RAG_INJECT_ENABLED` kill-switch. W0 must build this before any further RAG work.
- **3 critical stale local files**: `aim_voice_agent.py` (a9eefa8c≠018c20a7), `prompt.py` (ec5fa971≠fb87ea56), `agent.py` (1a154ea1≠9150fabe). Deploying any of these from local = regression.
- **Missing env flags**: `RAG_INJECT_ENABLED` (not built), `CTX_CACHE` (deployed but not in env?), `INBOUND_PROV_LOCK` (committed as 1 but absent from .env scan).
- **Branch sprawl**: 7 branches all ahead of feat/premium-ui; fe/unify-run-wavec is the deployed truth for FE; backend/handoff-name-clean-line is current active; merger needed.

---

## PHASE 2 — RECONCILE local↔box (pull box goldens into mirrors) (2026-06-14)

### EARNER GATE: PASS (before + after the pulls — all reads were SCP-down, no box write)
- agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED
- famit-agent MainPID `1477083` / ActiveEnter `2026-06-10 19:58:18` NOT restarted
- caller `/health` = 200 `{db:ok, redis:ok, livekit:ok}`
- 0 5xx (last 10 min); NO ring; NO flag flipped; NO famit-agent restart

### WHAT WAS RECONCILED (3 critical stale local files → box truth)
| File | Before (stale local) | After (= box) | Action |
|---|---|---|---|
| `droplet_work/aim_voice_agent.py` | `a9eefa8c` | `018c20a7` | SCP-pulled from box; committed |
| `droplet_work/aim_voice_agent.LIVEBOX.py` | `f169d6e1` | `018c20a7` | refreshed golden; committed |
| `droplet_work/prompt.py` | `ec5fa971` | `fb87ea56` | SCP-pulled from box; committed |
| `droplet_work/prompt.LIVEBOX.py` | `a2c5b053` | `fb87ea56` | refreshed golden; committed |
| `droplet_work/agent.py` (gitignored) | `1a154ea1` | `9150fabe` | on-disk refreshed for reference; NOT committed (earner stays out of git) |
| `_inbound_ref/aim_voice_agent.DEPLOYED.py` | `3152539f` (obsolete pre-RAG) | `018c20a7` | refreshed → name now truthful; committed |

### ALREADY-MATCHING (no action needed — Phase-1 audit was slightly off on kb/)
- `droplet_work/kb/{__init__.py,core.py,schema.sql}` (`f6ec3720`/`3922266f`/`fabd3803`) **ALREADY** match box exactly — the kb RAG module IS mirrored locally (Phase-1 listed it as box-only; corrected).
- `droplet_work/caller.py` (`592e6b94`) already matched box.

### CANONICAL-SOURCE MAP (the ONE copy per file, established)
Written to `_inbound_ref/README.CANONICAL.md` (committed): canonical = `droplet_work/<file>` + its `.LIVEBOX` golden, each reconciled to box; earner `agent.py` = gitignored on-disk scratch only; stale `_inbound_ref/aim_voice_agent.{LIVE,NEW,VERIFY}.py` marked OBSOLETE; `agent.REFERENCE.py` (`9150fabe`) confirmed accurate. RULE banked: re-pull `droplet_work/` from box after every box deploy or it silently goes stale (the branch-sprawl class of bug).

### SAFE GAP CLOSED?
NONE deployed. There was NO clearly-safe committed-but-undeployed earner gap to close: the 3 "stale local" files were stale in the LOCAL direction (box is ahead, not behind), so the safe move is to pull box→local (done), never push local→box. RAG-live-ungated retro-gate (`RAG_INJECT_ENABLED`, 0 hits in box code + .env) is the documented W0 wave — NOT closed here (it is box-mutating + flag-bearing, out of scope for this reconcile). The two env-flag uncertainties (`CTX_CACHE`, `INBOUND_PROV_LOCK` absent from `.env`) are NOTED for a famit-caller-only follow-up; not touched here (no restart in this wave).

### COMMIT
`70969dd` on `fe/unify-run-wavec` — "chore(repo-recovery): reconcile local mirrors to live BOX truth" (6 files, +744/-63). gitleaks staged = 0 (pre-commit hook re-confirmed).

### PHASE-2 ONE-LINERS
- Repo now MATCHES live box truth for every earner-path file → a future "deploy from local" can no longer silently revert the box.
- ONE canonical copy per file established + the stale `_inbound_ref` snapshots labeled obsolete (`README.CANONICAL.md`).
- Earner untouched (md5/PID/health all unchanged); no flag flip; W0 RAG retro-gate remains the separate next box-mutating wave.

---

## PHASE 3 — RECOVERY-STATE.md + bank rules + ORCHESTRATOR update (2026-06-14)

### EARNER GATE: PASS (all disk/git work, zero box write)
- agent.py md5 `9150fabe` UNCHANGED; famit-agent PID `1477083` NOT restarted; /health 200; 0 5xx; NO ring.

### DELIVERABLES WRITTEN
| File | Action | Purpose |
|---|---|---|
| `caps/design/RECOVERY-STATE.md` | CREATED | Authoritative canonical-source-per-file map + live flag state + 4 open follow-ups |
| `caps/PLAYBOOK.md` | APPENDED rules 16+17 | Bank "deploy from LIVEBOX golden" + "one auth copy per file" as permanent rules |
| `caps/AGENT_LEARNINGS.md` | PREPENDED new entry | Class-of-bug: branch-sprawl + stale local; RAG live+ungated; W0 first; `.LIVEBOX` golden rule |
| `caps/ORCHESTRATOR.md` | PREPENDED new wave entry | Ledger of this wave's plan + output + open follow-ups |

### RULES BANKED (PLAYBOOK §1)
- **Rule 16:** Every deployed-file edit MUST start from a box-pulled `.LIVEBOX` golden — never the repo or `_inbound_ref/*.py` scratch. SCP direction = box→local only.
- **Rule 17:** One authoritative copy per file. `droplet_work/<file>.LIVEBOX.py` = canonical local mirror. Update `RECOVERY-STATE.md` after every deploy.

### OPEN FOLLOW-UPS (from RECOVERY-STATE.md §3, priority order)
1. **P0 — W0:** Build `RAG_INJECT_ENABLED` kill-switch into `aim_voice_agent.py` (start from `018c20a7` LIVEBOX golden) — first move before any RAG wave.
2. **P1 — ENV verify:** Confirm `CTX_CACHE=1` + `INBOUND_PROV_LOCK=1` in box `.env` on next famit-caller-only restart.
3. **P2 — Branch merge:** Merge `fe/unify-run-wavec` into `backend/handoff-name-clean-line` to align the active branch with deployed FORTRESS FE.
4. **P3 — kb/ local tracking:** `scp -r box:/opt/famit-agent/kb/ droplet_work/kb/` — already matched, just needs tracking.

### PHASE-3 CONSISTENCY VERDICT
**LOCAL ↔ BOX = CONSISTENT** (for all earner-path files after P2 reconcile):
- `aim_voice_agent.py`: local = box = `018c20a7` ✅
- `prompt.py`: local = box = `fb87ea56` ✅
- `agent.py`: local on-disk = box = `9150fabe` (gitignored, box is truth) ✅
- All other `droplet_work/` files: matched in P1 audit (22 files) ✅
- Remaining divergence: **intentional** — `_inbound_ref/aim_voice_agent.{LIVE,NEW,VERIFY}.py` are OBSOLETE scratch, not deployed copies; they are labeled as such in `README.CANONICAL.md`.

**The branch-sprawl class of bug is CLOSED for these files** — a future "deploy from local" can no longer silently revert the box, because the local mirrors now match box truth. Earner untouched throughout the entire wave.
