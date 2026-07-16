# EXECUTION PLAN — Famit/Axcrio AI Revenue OS (STRANGLE & EVOLVE)

> **Chief-Architect assembly of the 9 verified subsystem specs** (`design/*.md`) into one
> ordered, unit-level, crash-safe build sequence with a worktree/agent delegation map, the
> exact Phase-0 first actions, and the cross-cutting gates.
>
> **VERDICT (settled, red-team confirmed):** STRANGLE & EVOLVE. Modular monolith. Every change
> additive, behind a feature flag, non-breaking; the live site (`panel.famit.in`) keeps earning
> throughout. Do NOT rebuild. (Master plan: `.claude/plans/you-have-digitalocean-api-imperative-mist.md`.)
>
> **Operating doctrine for every unit:** `AUTONOMY_OS.md` §3 per-unit loop (mark IN PROGRESS →
> backup local+box → small Edit → INSTANTIATE-test → deploy → REGRESSION GATE 200 → verify →
> build_log → commit → flip DONE) and §3.2 reconcile-first resume. One agent per file, ever.

---

## 0. THE SPINE (read this first — it dictates the whole sequence)

Five facts drive ordering. They override any per-spec optimism:

1. **P1-Postgres is the keystone and it is NOT done.** `store.py` does **not exist** on disk
   (verified: `droplet_work/` has no `store.py`, no `db/`); `P1_FOUNDATION_STATE.md` shows
   **U1 IN PROGRESS** (provision only). The strangler seam (U3) that everything else needs is
   unbuilt. **Four subsystems hard-gate on Postgres reaching U2-U9:** credit-ledger-firewall
   (needs PG schema + RLS), dynamic-context-rag (needs pgvector + RLS), orchestration UNITs 5/7
   (need the full finalize write-set migrated), auth-logto JIT-provision (needs the `_STORE_LOCK`
   seam). **P1 is the dominant blocker of the entire roadmap.**

2. **`caller.py` is the single serialization bottleneck.** It is one ~3,422-line / ~138KB file
   touched by: P0-curation, P1-U3, credit STEP 2-5, orchestration UNIT 3/5/6/7, auth STEP 0,
   obs V1, dynamic-rag finalize-hook. **All of these run SEQUENTIALLY in main, one unit at a
   time** (opus for the hard units). Two agents on `caller.py` = lost writes (brain/mistakes.md).

3. **The deployed box is AHEAD of the local tree on `agent.py` AND maybe `caller.py`.** The
   2026-06-08 FORTRESS pass added Groq(6)/Sarvam(5) key round-robin **on the box** (`agent.py`);
   local `droplet_work/agent.py` has only the older 3-key `_next_groq_key`. P1-U1-in-progress
   may have moved box `caller.py` past the U0 baseline md5. **Any scp deploy that overwrites the
   box without first reconciling local↔box regresses live production.** This is a hard pre-DEPLOY
   gate on BOTH the voice track and the caller.py spine (see §6 SECRETS/REGRESSION/DRIFT gates).
   *(obs-sec-cost RTF-4 flagged this for `agent.py`; voice-quickwins was anchored on the local
   tree and did NOT — this plan propagates it to the voice track.)*

4. **Phase 0 splits into "unblocked NOW" vs "P1-coordinated".** The secrets-gate, git, CI,
   terraform-import, and the voice quick-wins need **no new credentials and touch no product
   code** (new files only, or read-only-on-box) — they start instantly. The P0 "curate
   `caller.py`/siblings into `backend/`" sub-unit is gated on P1 coordination (md5-as-record,
   route `store.py`/`db/` through P1's PR — p0-foundation BLOCKER-3).

5. **Phases 0-3 need ZERO founder credentials.** Founder blockers (Meta WA, Razorpay, Google
   OAuth, paid Groq, re-scoped Cloudflare token) gate only later/optional flips, never the
   build start. They are gathered in parallel (§7).

**Conventions in this doc:** `[NOW]` = unblocked, can start in Phase 0. `[SPINE]` = edits
`caller.py`, runs sequentially in main. `[WT:x]` = runs in worktree `x` (parallel). Each unit
cites its **owning spec** and its **acceptance gate, taken verbatim from that spec** (this plan
invents no new gates; it sequences the specs' own gates).

---

## 1. ORDERED, UNIT-LEVEL BUILD SEQUENCE

### PHASE 0 — FOUNDATION + SECRETS GATE + VOICE QUICK-WINS  *(no new creds; live site untouched)*

P0 runs as **three parallel tracks** the moment the session starts. Track A (infra) and Track C
(voice pre-flight) are fully independent; Track B (voice ship) depends on C's pre-flight + the
drift reconcile.

#### TRACK A — Secrets gate → monorepo → CI → IaC  ·  spec: `p0-foundation.md`  ·  **sonnet** (+ one-time **opus** secret review)  ·  `[NOW]` `[WT:infra]`

| # | Unit | Owning spec | Acceptance gate (from spec) |
|---|------|-------------|------------------------------|
| A0 | **Secrets gate** — author `caps/.gitignore` (`.env*`, `*.pem/*.key`, `id_ed25519*`, `**/ALL_CREDENTIALS.md`, `**/secret`, `**/var/`, `*.bak.*`, `fortress/*`, `node_modules`, `.next`, `__pycache__`) **then run `gitleaks detect` / `git ls-files`-dry-run against the actual tree BEFORE `git init`** | p0-foundation §secrets-gate / master-plan §68-73 | gitleaks **clean** on staged tree before the FIRST commit; no `.env`/key/`ALL_CREDENTIALS.md`/`fortress/*` tracked |
| A1 | **git init + first commit** — `git init`; add+commit `.gitignore` ALONE; then `git add .` (safe now) + snapshot commit | p0-foundation; AUTONOMY_OS §4.1 | clean tree; `git log` shows gitignore-first then snapshot; `git ls-files` shows zero secrets |
| A2 | **Monorepo skeleton** — `/backend` (uv) `/frontend` (pnpm) `/infra` (terraform) layout + committed lockfiles **in the same unit** (`uv.lock`, `pnpm-lock.yaml`) | p0-foundation §4.1/§5.1 | `uv sync --frozen` + `pnpm i --frozen-lockfile` resolve from committed lockfiles |
| A3 | **CI: backend.yml** — ruff + pytest + gitleaks; pin **py3.12** (box reality, NOT 3.14); **`conftest.py` must `os.environ.setdefault` the 3 throwaway keys** (`LIVEKIT_API_KEY/_SECRET/_URL`) before importing `caller` | p0-foundation BLOCKER-1 + §6.1 + §4.4 | CI green: `import caller` + pytest collection do NOT `KeyError` on GitHub Actions/Windows |
| A4 | **CI curation gate: test_imports.py** — import each sibling (`whatsapp`, `vendors/*`, `config`, `auth`, `audit`, `ratelimit`, `obs`) **directly** + assert `caller._auth_mod/_audit_mod/_rl_mod/_obs_mod/wa_mod/v_vobiz` are wired (not `None`) | p0-foundation BLOCKER-2 | all 14 siblings import-clean under bare env; wiring assertions pass |
| A5 | **CI: frontend.yml** — pnpm build + Playwright smoke (`--legacy-peer-deps` reality lives in panel; mirror) | p0-foundation §6 | build exit 0; smoke green |
| A6 | **Terraform import (DO + Cloudflare), no-diff loop** — import existing droplets/firewalls/DNS; **`apply` FORBIDDEN**; CF zone-id **API-discovered** (not in `fortress/STATE.md`); iterate to no-diff | p0-foundation §7.x | `terraform plan` shows **no-diff** (iterative; never first-try — judgment-gated, not a one-shot) |

> **A0 is the irreversible one.** The hand-written `.gitignore` is *intent*; **gitleaks is the
> net**. This box was compromised once; a wrong ignore commits live creds permanently. Scan,
> then commit. The opus secret-review runs once over A0-A1 before any push.

#### TRACK B — Voice quick-wins (semantic turn-detector + barge-in)  ·  spec: `voice-quickwins.md`  ·  **opus**  ·  `[WT:voice]`

| # | Unit | Owning spec | Acceptance gate (from spec) |
|---|------|-------------|------------------------------|
| **B-DRIFT** | **🔴 PRE-DEPLOY DRIFT RECONCILE (gate, do FIRST):** md5/diff **local `droplet_work/agent.py` vs box `/opt/famit-agent/agent.py`** (CRLF-normalized). The box has FORTRESS Groq(6)/Sarvam(5) rotation local lacks. **Pull box → reconcile → make local a superset BEFORE any scp.** | this plan (propagates obs RTF-4 to voice) | local `agent.py` contains the box's 6/5-key rotation; a deploy will NOT regress live key-rotation. **Blocks B2/B3, not B1.** |
| B1 | **STEP 1 pre-flight** (read-only on box, NO restart): confirm `livekit-agents ≥1.5` (build log records **1.5.17** → almost certainly satisfied), CPU/RAM headroom, dump `SESSION_KNOBS`, confirm `MultilingualModel()`+`vad=` API, verify `min_interruption_words`/`resume_false_interruption` exist on 1.5.17, **run HF model-download as user `famit`** | voice-quickwins STEP 1 + RTF-F | model loads on box as `famit`; knob presence recorded; **no behavior change** |
| B2 | **STEP 2 semantic swap behind flag** (`TURN_DETECTION`, DEFAULT stays `vad`): resolve detector **ONCE** into `_td`; derive `_semantic_on = not isinstance(_td, str)` from the **resolved** detector (RTF-A — kills the VAD+1.8s dead-air fallback bug) | voice-quickwins STEP 2 + RTF-A/C | flag OFF = byte-identical current behavior; flag ON loads semantic; introspect assertion confirms built session carries intended kwargs |
| B3 | **STEP 3 adaptive barge-in** (separate deploy from B2 — RTF-C): `MIN_INT_DUR` 0.45, `min_interruption_words=2`, `resume_false_interruption=on`; **decide ship-gated-on-env vs ship-default** (RTF-B); introspect-assert kwargs survive | voice-quickwins STEP 3 + RTF-B/C | introspect assertion green pre-call; barge-in defaults flip via env |
| B4 | **STEP 4 real bidirectional call** (the only proof) — a human answers, speaks, interrupts | voice-quickwins STEP 4 | lower eou + **no mid-sentence cuts** + **no latency regression**; instant `vad` rollback verified available |

> RTF-E: **drop `backchannel.py` entirely** if B1 confirms native `min_interruption_words` (expected on this box).
> RTF-D: ship the missing `prewarm`/`WorkerOptions(prewarm_fnc=)` diff with B2 so "prewarm" isn't improvised live.
> Do-not-touch `famit-caller` from this track (P1 strangler mid-flight).

---

### PHASE 1 — COMPLETE POSTGRES MIGRATION  *(the one risky migration; the keystone)*  ·  spec: `p1-postgres.md`  ·  **opus**  ·  `[SPINE]` (U3+ edit `caller.py`)

**Canonical unit list = `droplet_work/P1_FOUNDATION_STATE.md` U0-U9** (the P1 owner executes
against the STATE U-list, not the design doc's by-risk sections — cite STATE). **U0 DONE, U1 IN
PROGRESS.** Folded blockers B1-B4 are **mandatory** and already in the spec.

| # | Unit (STATE U-list) | Acceptance gate (from spec + STATE regression gate) |
|---|----------------------|------------------------------------------------------|
| U1 | PROVISION: `apt postgresql`, db `famit`, restricted role `famit_app` (NOSUPERUSER, FORCE RLS), venv deps, `PG_DSN` (async+sync). **PgBouncer `scram-sha-256` not md5** (B3 — bare apt gives PG14/16 SCRAM) | both drivers connect; on FAIL → all stores forced `json` (live site never breaks) |
| U1 (+) | **`CREATE EXTENSION vector` belongs in U1/PROVISION, run as the `postgres` superuser** (rag-F1) — NOT in U2's Alembic migration, which runs as `famit_app` (NOSUPERUSER) and would fail. Fold the EXTENSION into the U1 provision step | extension present before any app DDL |
| U2 | `db/models.py` (SQLAlchemy 2.0, 15 tables + RLS DDL) + Alembic init + first migration. **App-owned tables/indexes only** (the vector-typed tables/indexes succeed as `famit_app` because the EXTENSION already exists from U1) | DDL-only, no behavior change |
| U3 | **`store.py` + seam rewire** (`_read`/`_write`/`_awrite` route via `Store`; DEFAULT `json`). **Declare `_store=None` at module scope, guard `is not None`, assign only after `init()`** (B4). **RISKIEST UNIT** `[SPINE]` | REGRESSION GATE: byte-identical writes (indent=2, ensure_ascii=False), all 200s, md5 stable |
| U4 | flip leads `json→dual`; **single per-store coalescing worker, depth-1 replace-on-full queue, last-snapshot-wins, O(1) non-blocking enqueue** (B1 — the headline fix; the hot leads writers fire `_write` inside `_STORE_LOCK`). **Empty-snapshot guard** on reconcile (B2 — `<> ALL(empty)` wipes the table) | create lead via API → row in BOTH PG + JSON → `shadow_diff==0` after burst-write→quiesce |
| U5 | `backfill.py` (idempotent JSON→PG, dedupe by id) | counts match; spot-check 10 leads |
| U6 | flip leads `→pg` → restart → leads still served → set back to `dual` (safe steady state) | leads served from PG; `dual` is the legitimate P1 end state (do NOT flip campaigns/transcripts to `pg` — agent-read stores) |
| U7 | orgs/users/memberships backfill (each tenant→1 org+admin). **org_id == tenant_id; do NOT rewire `resolve_tenant`; tenants.json authoritative** | legacy `/login` + X-Auth + JWT unchanged |
| U8 | `GET /admin/store-status` (admin) — per-store MODE + last shadow-diff | endpoint 200; reflects modes |
| U9 | RLS proof — restricted role + `SET LOCAL app.tenant_id` → cross-tenant raw SQL **blocked**; `shadow_diff.py` drift report | cross-tenant read blocked; drift report clean |

**P1 unblocks the gated four.** `shadow_diff==0` (U4/U9) is the cutover invariant — a build agent
must NOT declare a store cutover-ready on a silently-diverged mirror (that is exactly what B1/B2
prevent).

---

### PHASE 2 — DYNAMIC VOICE CONTEXT + RAG  *(gated on P1 U2)*  ·  spec: `dynamic-context-rag.md`  ·  **opus** + sonnet review

Hard prereq: **P1 U2** provisions `CREATE EXTENSION vector` + RLS scaffolding. Step 1 (embedder)
can author before that, but schema needs U2.

| # | Unit | Acceptance gate (from spec) |
|---|------|------------------------------|
| RAG-1 | Embedder service **OFF the voice box** (F5 — torch beside `famit-agent` risks call latency) + `rag.py` **connection-per-op + `SET LOCAL` inside explicit txn** (F3 — shared conn across coroutines = wrong-tenant reads) `[WT:voice or separate]` | two-tenant no-bleed check passes |
| RAG-2 | `ensure_schema()` tables/indexes **app-owned** (EXTENSION already done in U2 per F1); all three RLS policies get explicit **`WITH CHECK`** (F2 — `OR tenant_id=''` let any tenant insert a global visible to all) | own-only writes; globals seeded out-of-band |
| RAG-3 | Caller-side delivery: `var/rag_context/<room>.json` written before dispatch (room minted `caller.py:1642` — race-free) `[SPINE]`; `kb_version` in cache key (F6 — else stale ≤24h) | byte-identical when `RAG_INJECT_ENABLED=0`, **with `knowledge` field present** (prefix-purity F7) |
| RAG-4 | Agent-side inject at recap seam (`agent.py:372-378`) `[WT:voice]` | **gate = agent-log TTFT parse** (F4 — `/metrics` exposes no `llm_ttft`); flip `RAG_INJECT_ENABLED=1` only when p95 holds |

*(Master-plan Phase 2 also lists HA/no-SPOF ×2 + DO LB + warm-pool — infra, sequence after RAG
or in parallel on `[WT:infra]`; not owned by a design spec in this batch.)*

---

### PHASE 3 — ASYNC SPINE (Hatchet) + EVAL HARNESS

#### Eval harness  ·  spec: `eval-harness.md`  ·  **opus**/sonnet  ·  `[WT:eval]` — FULLY INDEPENDENT, can start as early as Phase 0

Offline, reads `var/` only, structurally call-free, zero v1 hot-path edits. **No file collision
with anything** → its own worktree, parallel from day one.

| # | Unit | Acceptance gate (from spec) |
|---|------|------------------------------|
| E1 | UNIT 1 corpus audit (decides center of gravity). **All on-box cmds prefixed `cd /opt/famit-agent &&`** (B1 — venv at `/opt/capsy-agent`, code at `/opt/famit-agent`) | commands actually run (not ModuleNotFoundError) |
| E2 | UNIT 2 golden scenarios + deterministic scorers + unit tests | scorers pass on seeded fixtures |
| E3 | UNIT 3 Groq client + turn-level replay driver. **`max_tokens` not `max_completion_tokens`** on raw endpoint (B4); **faithfulness 3b is a hard VALIDITY gate** (B2 — fail ⇒ `invalid`, never pass/fail) | replay reconstructs context; 3b green or run invalid |
| E4 | UNIT 4 pinned LLM judge (soft qualities) | rubric scores stable |
| E5 | UNIT 5 gate + baseline freeze + CLI (token cap **140** per S1) | baseline frozen |
| E6 | UNIT 6 **MARQUEE** deliberately-bad self-test | a worse model **FAILS** the harness (proves teeth) |
| E7 | UNIT 7 (OPTIONAL, flag-gated) richer live-agent capture `[SPINE]` if it touches caller/agent | flag OFF = no-op |

#### Orchestration (Hatchet)  ·  spec: `orchestration-hatchet.md`  ·  sonnet/opus

**Split: infra+read-path (GO now) vs call-placing/finalize (BLOCKED on P1).**

| # | Unit | Status / gate (from spec RTFs) |
|---|------|--------------------------------|
| H0 | UNIT 0 baseline + pin `[NOW]` | md5 `a60b8a9e…` recorded |
| H1 | UNIT 1 deploy Hatchet engine (docker, resource-limited). **RTF-3: RAM pre-flight; DEFAULT = separate $6/mo droplet, NOT the voice box.** **RTF-2: all ports 127.0.0.1-bound** (PG 5432/RabbitMQ 5672/mgmt 15672), not just 8888/7077 `[WT:hatchet or separate box]` | `ss`/`iptables` shows loopback-only; RAM headroom proven |
| H2 | UNIT 2 worker scaffold + client + flags + smoke (RTF-7: worker import-safe, `WorkingDirectory=/opt/famit-agent`) | smoke passes; no workflow live |
| H3 | UNIT 3 **`vendor-sync` cutover** — route `POST /billing/sync` through Hatchet when flagged (RTF-4: it writes the same ledgers the cron owns → corruption otherwise) + frontend-contract guard `{ok,synced_at,vendors}` `[SPINE]` | WAVE-A "Refresh now" shape preserved; no double-write |
| H6 | UNIT 6 extract `dial_one_lead()` (pure refactor; mutates 6 loop-locals — NOT byte-for-byte, RTF-6) `[SPINE]` | behavior identical; cross-process record-visibility test |
| H4 | UNIT 4 `wa-cadence` — **DEFER** (net-new Phase-7 feature, not on cutover path) | — |
| H5 | UNIT 5 `retry-callback` cutover — **🔴 BLOCKED on P1 full finalize write-set** (RTF-1: finalize writes billing/ledger/wa_log/wa_threads/webhook_log too). RTF-5 webhook exactly-once marker BEFORE emit. RTF-11 atomic `O_CREAT\|O_EXCL` dial-claim BEFORE `create_room` `[SPINE]` | webhook-fires-exactly-once test; CONCURRENT double-fire test |
| H7 | UNIT 7 `campaign-run` cutover (LAST; call-placing write path) — **🔴 BLOCKED on P1 + H5** `[SPINE]` | restart mid-campaign → no lost/double calls |
| H8 | UNIT 8 decommission-in-place guards + docs | old polling paths inert |

---

### PHASE 4 — AUTH (Logto) + ACTION FIREWALL + AUDIT + WALLET LEDGER

#### Auth (Logto)  ·  spec: `auth-logto.md`  ·  opus security review mandatory

| # | Unit | Gate (from spec) |
|---|------|-------------------|
| AU0 | STEP 0-5 + flag-OFF no-op deploy: `resolve_token` Logto branch, `init`, `_provision`, `_extract_roles`, `health`. **`iss != _ISSUER` pre-filter BEFORE any JWKS network call** (FIX#1 — pre-auth DoS/latency) + `LOGTO_JWKS_URI` localhost (FIX#2 hairpin) `[SPINE]` (one boolean short-circuit in `resolve_tenant:366`) | flag OFF = byte-for-byte current behavior |
| AU1 | STEP 6 flag flip — **NO-GO until FIX#1+#2 + tests (a)no-refetch (b)JWKS-down-isolation (c)alg-confusion green** | flip safe only with `iss` pre-filter present |
| AU2 | STEP 7 frontend (after AU1 green) `[WT:frontend]` | login via Logto; legacy path intact |
| — | JIT-provision (write to tenants.json) — **gated on `_STORE_LOCK` seam (P1)**; OFF by default | non-blocking now |

#### Credit/wallet ledger + Action Firewall  ·  spec: `credit-ledger-firewall.md`  ·  opus  ·  **the BUILD-don't-compose exception**

**G0 hard gate: Step-0 Postgres must pass — else STOP after a schema-design commit, do NOT ship a
JSON wallet.** (Depends on P1 U1/U2.)

| # | Unit | Gate (from spec) |
|---|------|-------------------|
| W0 | STEP 0 Postgres gate (G0) + STEP 1 schema (DDL + migration, flag OFF). `ALTER DEFAULT PRIVILEGES … SEQUENCES` (F7) | G0 green or stop |
| W1 | STEP 2 `wallet.py` transactional core + **OVERSELL TEST** + **T-A concurrent double-settle via `asyncio.gather`** (the hard unit) | no oversell; idempotency `result` populated UPDATE-before-COMMIT |
| W2 | STEP 3 wire hold/settle/release/sweep behind `WALLET_ENABLED`, ON for ONE test tenant. **F1: hoist `call_id` beside `room` (caller.py:1642), reserve before `create_room`, release off local var in `except`** (else every call double-holds, never settles) `[SPINE]` + **T-B release-on-dial-failure** | reserve/settle use the SAME uuid; dial-failure releases |
| W3 | STEP 4 Action Firewall (`firewall.py`) behind `FIREWALL_ENABLED`, OFF. **F3: `require_step_up` asserts `sub == resolve_tenant(request)`** (leaked token replay) | cross-tenant step-up token rejected |
| W4 | STEP 5 AI-decision audit (`aidecision.py` + agent.py drop + drain). **F2: money-mutating audit = PG row INSIDE the wallet txn** (JSONL can't be atomic with COMMIT) `[SPINE]` | money audit atomic with the wallet txn |
| W5 | STEP 6 frontend `[WT:frontend]` — **deploy target `143.110.247.249:/opt/famit-panel`** (F4 — old `168.144.125.155` deleted) | 402 "top up" handled, no crash |

---

### PHASE 5+ — OBSERVABILITY / SECURITY / COST  ·  spec: `obs-sec-cost.md`  ·  opus(voice)/sonnet

Mostly independent of the spine; the voice-metric + cost units touch `agent.py`/`caller.py`.

| # | Unit | Track / gate (from spec RTFs) |
|---|------|-------------------------------|
| OBS-V0 | UNIT V0 pre-flight (read-only) `[WT:voice]` | knobs/firewall recorded |
| OBS-V1 | UNIT V1 persist per-stage voice latency → **separate `voice_lat_raw/<room>.json`** (RTF-1/2: `usage` dict is NOT serialized by `_write_usage_raw`; appending to `events` corrupts the cost ledger) `[SPINE]`+`[WT:voice]` | `voice_lat_raw` file shows arrays; cost ledger untouched |
| OBS-V2 | UNIT V2 `obs.py` voice histograms + fold-loop emission at **`_drain_usage_raw()` caller.py:1415** (RTF-3, NOT scheduler_loop:3303) `[SPINE]` | voice SLIs populate; flag `OBS_VOICE_ENABLED` |
| OBS-O1/O2/O3 | Prometheus + Grafana (+ OTel) **on the PANEL box** `143.110.247.249` (firewall `10.122.0.2→:8209` precondition) `[WT:obs-infra]` | dashboards live; voice box load unchanged |
| OBS-C1 | UNIT C1 cost dashboards + cost/min SLI (Grafana over existing meter) `[WT:obs-infra]` | sum == grand_total |
| OBS-C2 | UNIT C2 TTS A/B EL-vs-Sarvam provider factory. **RTF-4: pull live box `agent.py` + diff FIRST, use box key-resolution** (else bypasses on-box rotation — same drift as B-DRIFT). **RTF-5: ONE cost provider, single ledger read** `[SPINE]`+`[WT:voice]` | A/B panel; no rotation regression |
| OBS-S1..S5 | Infisical branch / encryption posture / OWASP-BOLA proof harness / prompt-injection guard (S4 standalone, opus) / DPDP-TRAI posture `[WT:infra]` mostly | each unit's own gate; S3 BOLA proof green |

---

## 2. WORKTREE + AGENT DELEGATION MAP

**The rule (AUTONOMY_OS §2.3): one agent per file, ever. Shared big files serialize in MAIN.**

### The ONE sequential spine (main thread, opus for hard units)
Every unit that edits **`caller.py`** runs here, one at a time, JSON-authoritative until
`shadow_diff==0`: **P0-curation → P1 U3-U9 → RAG-3 → H3 → H6 → H5 → H7 → AU0 → W2 → W4 →
OBS-V1 → OBS-V2 → OBS-C2.** New-file authoring (`store.py`, `db/models.py`, `wallet.py`,
`firewall.py`, `aidecision.py`, `rag.py`) happens in worktrees, but **each WIRE-IN to `caller.py`
rejoins this spine.**

### Parallel tracks (each its own worktree, non-conflicting files)

| Worktree / branch | Owns (files) | Agent model | Units | Independent of spine? |
|---|---|---|---|---|
| **`[WT:infra]`** `feat/foundation` | `caps/.gitignore`, `/infra/*`, CI `.yml`, `config.py` (S1) | sonnet (+opus secret review) | A0-A6, OBS-S* | **Yes** (new files) |
| **`[WT:voice]`** `feat/voice` | `agent.py`, `prompt.py`, `langdetect.py` | **opus** | B1-B4, RAG-1/RAG-4, OBS-V0/V1(agent-half)/C2(agent-half) | **Yes** — but **gated on B-DRIFT reconcile**; internally serial (one `agent.py`) |
| **`[WT:frontend]`** `feat/frontend` | `caps/famit-panel/**` (panel box `143.110.247.249`) | sonnet | all WAVE-B/3 + credit W5 + auth AU2 frontend TODOs | **Yes** (separate dir + box) |
| **`[WT:eval]`** `feat/eval` | `eval/**` (reads `var/` only) | opus/sonnet | E1-E6 (E7 only if it touches agent → spine) | **Yes, fully** — can start Phase 0 |
| **`[WT:obs-infra]`** `feat/obs` | Prometheus/Grafana/OTel configs on **panel box** | sonnet | OBS-O1/O2/O3, OBS-C1 | **Yes** (separate box) |
| **`[WT:hatchet]`** `feat/hatchet` (or separate $6 droplet) | docker-compose, worker scaffold (new files) | sonnet | H1, H2 | **Yes** (new files/box); H3/H5/H6/H7 cutovers rejoin spine |
| **new-file authoring** (any worktree) | `store.py`/`db/`, `wallet.py`, `firewall.py`, `rag.py`, `aidecision.py` | opus | P1/credit/rag pre-wire | **Yes to author**; wire-in → spine |

**`.worktreeinclude`** must list `.env`/`.env.local`/keys so each fresh worktree checkout can
deploy (AUTONOMY_OS §4.3). Add `.claude/worktrees/` to `.gitignore` (done in A0).

### One-paragraph parallel-vs-sequential summary
**Sequential (main, opus):** everything that mutates `caller.py` — P0-curation, all of P1 U3-U9,
then the RAG caller-delivery, the three Hatchet cutovers, the auth `resolve_tenant` edit, the two
wallet wire-ins, and the obs voice-fold edits — runs **one unit at a time** because they share the
single 3,422-line file and the JSON→PG mirror must stay diff-clean. **Parallel (worktrees,
sonnet/opus):** the secrets-gate+CI+terraform infra track, the voice track (`agent.py`/`prompt.py`,
internally serial, gated on the local↔box drift reconcile), the frontend track (`famit-panel` on
the panel box), the eval harness (offline, `var/`-read-only — startable on day one), the
observability infra (Prometheus/Grafana on the panel box), and the Hatchet engine deploy (docker,
ideally its own droplet) all run **concurrently and independently**, with the discipline that any
unit which finally *wires a new module into `caller.py`* drops back onto the sequential spine.

---

## 3. EXACT PHASE-0 FIRST ACTIONS (first 5 commands/edits — start instantly)

Run from `C:\Users\kunal\Desktop\caps`. **A0/A1 are irreversible — gitleaks is the net.**

```
1. WRITE  caps\.gitignore   (Edit/Write the block in §1-A0: .env*, *.pem, *.key,
   id_ed25519*, **/ALL_CREDENTIALS.md, **/secret, **/var/, *.bak.*, fortress/*,
   node_modules/, .next/, __pycache__/, .claude/worktrees/)

2. SCAN   (the NET — before any git init/add):
   gitleaks detect --no-git --source . --redact      # or, if gitleaks absent:
   git init && git add --dry-run . | findstr /I ".env id_ed25519 ALL_CREDENTIALS secret fortress"
   # MUST come back clean. If ANY secret would be staged, fix .gitignore and re-scan. Do NOT proceed dirty.

3. git init   &&   git add .gitignore   &&   git commit -m "chore: add .gitignore before tracking (keep secrets out)"

4. git add .   &&   git commit -m "chore: initial crash-safe snapshot"
   (safe ONLY because step 2 proved no secret is staged)   →  then: git ls-files | findstr /I ".env secret id_ed25519"  ==  empty

5. PARALLEL, read-only, blocks nothing — kick off voice STEP-1 pre-flight (B1) in [WT:voice]:
   ssh -i C:\Users\kunal\.ssh\do-blr-test\id_ed25519 famit@168.144.153.145 ^
     "cd /opt/famit-agent && /opt/capsy-agent/.venv/bin/python -c 'import livekit.agents as a; print(a.__version__)' ; nproc ; free -m"
   # AND begin B-DRIFT: md5 local droplet_work\agent.py vs box /opt/famit-agent/agent.py (CRLF-normalized)
```

After step 4, the §3.1 per-unit loop is live (commit-per-unit real). Steps 1-4 are Track A; step 5
starts Track C in parallel. The opus one-time secret review runs over the step-1-4 diff before any
`git push`/remote.

---

## 4. CROSS-CUTTING GATES (every unit, every track)

1. **SECRETS-GATE (once, before first commit; re-checked in CI forever).** `.gitignore` is intent;
   **gitleaks is the net.** No `.env*`/`*.key`/`id_ed25519*`/`ALL_CREDENTIALS.md`/`fortress/*`/
   `*.bak.*` ever tracked. CI `backend.yml`/`frontend.yml` run gitleaks on every push (A3/A5). This
   box was compromised once — treat a committed secret as an irreversible production incident.

2. **DRIFT-GATE (before EVERY box deploy — the new cross-cutting gate this synthesis adds).** The
   box is ahead of local on `agent.py` (FORTRESS 6/5-key rotation) and possibly `caller.py` (P1
   mid-flight). **`md5sum`/diff local-vs-box for the exact file you are about to scp (CRLF-
   normalized); if the box is ahead, PULL → reconcile → make local a superset BEFORE deploying.**
   Skipping this regresses live production silently. Applies to B2/B3/OBS-C2 (`agent.py`) and the
   entire `caller.py` spine.

3. **REGRESSION-GATE (every unit, do FIRST after deploy — AUTONOMY_OS §3.1.5).**
   `curl -s -o NUL -w "%{http_code}" -H "X-Auth: FamitCall2026" https://panel.famit.in/api/<known>`
   != 200 → **RESTORE on-box `.bak.<ts>` + restart famit-caller, re-run gate to known-good, THEN
   diagnose.** Full gate (P1 STATE): legacy X-Auth→200 on `/campaigns`; `/auth/login` issues
   tokens; `/leads`,`/run`,`/billing/overview`,`/me` all 200; `/run` dispatches; **famit-caller +
   famit-agent active**; md5 local==deployed. **No paid call to verify blind.**

4. **INSTANTIATE-GATE (before deploy — brain/mistakes.md).** Don't trust `ast.parse`; actually
   instantiate the real plugins/clients with exact kwargs (the silent-call bug was a constructor
   `TypeError` ast missed). Voice deploys: run the `/tmp/insttest.py` pattern.

5. **FLAG-OFF-IS-BYTE-IDENTICAL (every strangler unit).** Each new capability ships behind a flag
   defaulting OFF/`json`/`vad`; with the flag off, behavior is provably byte-for-byte current. This
   is the non-breaking guarantee and the rollback path. Flip ON only after that unit's own
   acceptance gate (cited per-unit above) is green in prod.

6. **CRASH-SAFE PER-UNIT (every unit — AUTONOMY_OS §3).** mark IN PROGRESS (STATE/TASKS line) →
   backup local + on-box `.bak.<ts>` BEFORE scp → small Edit → instantiate-test → deploy →
   regression-gate → verify-new → **build_log + brain (win→playbooks, trap→mistakes,
   choice→decisions)** → commit (one unit = one commit) → flip DONE. Never batch-then-verify. A
   kill costs ≤1 unit. WORKLOG.md auto-writes via the PostToolUse hook; the STATE line is what
   tells a resume whether the last unit actually passed.

7. **BRAIN / BUILD_LOG (load-before, append-after).** Before a domain, read HANDOFF + the relevant
   `brain/*.md` + `build_log/wave-*.md`. After each unit, APPEND (never overwrite) a per-wave
   build_log report and the win/trap/choice. The brain is how the org stops re-learning.

8. **OPUS SECURITY REVIEW** on any auth/tenant/billing/money diff before flip (auth AU1, wallet
   W1-W4, BOLA S3). For auth it must additionally assert FIX#1's `iss` pre-filter is present and
   `algorithms=` allow-lists are pinned in both `caller.py` and the auth module.

---

## 5. CRITICAL PATH & BLOCKERS (summary)

- **Critical path:** P0-A (secrets/git/CI) → **P1 U1→U9** (the keystone; `store.py` must be built
  and `shadow_diff==0` reached) → unblocks {credit-ledger, dynamic-rag schema, orchestration
  cutovers H5/H7, auth-JIT}. **P1 IS the dominant blocker** — it is only at U1-IN-PROGRESS;
  `store.py` does not yet exist.
- **Startable in parallel on day one (no P1 dependency):** the entire infra track (A0-A6), the
  voice quick-wins (after B-DRIFT reconcile), the eval harness (fully offline), the Hatchet engine
  deploy + obs infra (separate boxes).
- **BLOCKED-until-P1:** credit STEP 2-5, dynamic-rag schema (needs U2 EXTENSION/RLS),
  orchestration UNIT 5 + UNIT 7, auth-logto JIT-provision.
- **Founder-credential blockers (gate flips only, NOT the build — gather in parallel):** Meta WA
  (4 values + template), Razorpay/Stripe keys (wallet topup OTP/payment — wallet core works
  without), Google OAuth (Logto social — email/pw works without), paid Groq/Cerebras key (latency
  polish — 6-key rotation is the interim), re-scoped Cloudflare token (panel.famit.in go-live +
  DNS automation — backend already serves over VPC).
- **Coordination blocker the orchestrator must resolve:** serialize **P0-curation vs P1-U3** on
  `caller.py` (p0-foundation BLOCKER-3) — either P0 curates the post-P1 tree, or md5 becomes a
  record-not-gate and `store.py`/`db/` route through P1's PR. Do NOT run a P0 curation agent and a
  P1 store agent on `caller.py` at the same time.

---

*Assembled by the Chief Architect from the 9 verified subsystem specs in `design/*.md`, grounded
against `droplet_work/` live source, `P1_FOUNDATION_STATE.md`, HANDOFF, build_log, brain, and the
master plan. Every unit's acceptance gate is taken from its owning spec; this plan sequences and
de-conflicts, it does not re-design.*
