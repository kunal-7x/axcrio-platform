# communication/ — READ-FIRST INDEX

> The omnichannel **Communication tab** for Famit/Axcrio: **Telegram + Email + SMS** (new section, alongside the live WhatsApp). Mirrors + exceeds WhatsApp: multi-step builder, send banner/video/PDF, after-a-call auto-summary to the contact, hot-lead auto-alert to the founder's Telegram, a multi-step LLM conversation brain — per-tenant, earner-safe, sellable.
>
> **A post-compaction session reads THIS file first, then `COMMUNICATION-MASTER-PLAN.md`, then resumes from the roadmap (§8 of the plan).**

## The two files that matter
1. **`COMMUNICATION-MASTER-PLAN.md`** — THE plan. Exec summary + full feature set (the named 1% + the 99%) + architecture/seams + data model + security + compliance + cost/scale + frontend + the **phased earner-safe build roadmap** (Wave 1-6, each: scope/files/flags/acceptance/rollback) + the **founder credential actions** + risks. **Build from §8.**
2. **`_RESEARCH-LOG.md`** — the full research substrate (320 KB). 6 architecture phases (channel-registry, telegram, email-sms, automation-engine, llm-brain, ui, data-security) + 7 red-teams (deliverability, security, cost-scale, earner-safety, compliance, over-engineering) + the completeness critic + the channel/cost/compliance facts. The master plan folds all fixes in; read the log for the *why* behind a decision.

## The 60-second orientation
- **The structural decision:** the channel registry IS the provider registry (LIVE on the box). A bot token / Resend key / MSG91 key = one `provider_credentials` row + one adapter. Zero new crypto. Adding a channel = 1 row + 1 file.
- **Earner-safety law (red-team-corrected):** `_finalize_call` is `await`ed INSIDE the live dial loop — so every send is `asyncio.create_task` + payload snapshot + per-channel timeout, NEVER `await`; `agent.py` never imported; flags default OFF → resting byte-identical; earner gate before+after under an induced channel outage.
- **MVP-first:** Wave 1 = **3 tables + Telegram-only + founder alert + post-call auto-summary + setup UI** (~2 wks). NOT the 10-table cathedral, NOT the cost-router, NOT Hatchet journeys, NOT the agentic tool-loop, NOT the inbox — those are earned Waves 3-6.
- **Telegram first** — the unblocked launch (a 2-min BotFather token, no Meta verification, free, real-reach-provable to the founder's phone). Then Email (W3), then SMS (W5, DLT-gated).

## Build status (live progress — newest detail in `_BUILD-LOG.md`)
- **W1-P0** ✅ DB (4 FORCE-RLS tables) + founder Telegram token in the LIVE vault.
- **W1-P1** ✅ Telegram adapter + channel-agnostic send engine (offline).
- **W1-P2** ✅ **LIVE** — inbound webhook (FAIL-CLOSED, S2) + comm API endpoints + caller.py mount
  (additive +43/−0; box golden `44b867ea`→`73d7be4f`). Flags `COMM_ENABLED=1`+`COMM_TELEGRAM_ENABLED=1`
  ON for the founder tenant. LIVE T-WEBHOOK 6/6 PASS; earner gate green under an induced Telegram
  outage (agent.py `9150fabe` unchanged, famit-agent PID not restarted, /health 200, 0 5xx).
- **W1-P3** ✅ **LIVE** — `founder_alert.py` + `post_call.py` + `consent.py` + the caller.py
  `_finalize_call` hook (additive +28/−0, box golden `73d7be4f`→`ccf9715b`). The post-call block
  takes a PURE-SYNC snapshot then `asyncio.create_task`s a DETACHED send (founder hot-lead alert +
  contact auto-summary), NEVER awaited on the dial loop; the engine owns the per-channel timeout.
  Flags `FEATURE_TELEGRAM_FOUNDER_ALERT=1`+`FEATURE_TELEGRAM_FOLLOWUP=1` ON for the founder tenant.
  EARNER GATE under an induced Telegram black-hole: snapshot 0.047ms + create_task 0.015ms (the only
  hot-path cost), detached run bounded 0.10s, agent.py `9150fabe` unchanged, famit-agent PID 2808658
  not restarted, /health 200, 0 5xx. **ONE founder action pending** (tap @mr_kunal_bot once to seed
  the live chat_id — getUpdates aged out; auto-persists after) → `communication/_HUMAN_TASKS.md`.
- **W2** ✅ BUILT (flag-gated) — the LLM conversation brain (reply-only) + the signed single-use
  `?start=` deep-link that seeds CONTACT chat_ids (activates the auto-summary's deliverable path).
- **SECURITY PROBES** ✅ IMPLEMENTED + PROVEN (offline, real code) — the 6 ship-blockers
  (`T-WEBHOOK · T-INJECT · T-LEAK · T-VAULT · T-DEEPLINK · T-GATE`) consolidated into one harness
  `comm/tests/test_security_probes.py` → **6/6 PASS, 53 sub-checks, 0 fail, exit 0** (no box /
  caller.py / agent.py touch; zero regression; gitleaks 0). T-LEAK proven on the real runtime
  memory path. ONE tracked residual surfaced honestly: S1 per-tenant HKDF DEK (the AAD binding
  already defeats cross-tenant paste; the DEK upgrade is a separate key-version-gated crypto wave so
  the LIVE founder token stays decryptable). Details: `_BUILD-LOG.md` (## SECURITY-PROBES).
- **FE (W1/W2)** ✅ BUILT (panel deploy DEFERRED) — the **Communication TAB** (`Engage > Communication`,
  `/communication`): one shell, four views (Channels setup + Builder + unified Inbox + Analytics) behind a
  SubNav + ChannelPicker. Telegram live; Email/SMS coming-soon; WhatsApp deep-links out. Dormant-safe,
  Core_2, zero raw hex. tsc 0 + build GREEN + eslint 0 + gitleaks 0, committed on `fe/unify-run-wavec`.
  Panel deploy deferred to the single final canonical deploy (no race). Details: `_BUILD-LOG.md` (FE section).
- **W3-COSTGUARDS** ✅ BUILT (flag-gated OFF, offline-green) — the **6 cost guards** of §6, all PROVEN
  PASS (unit + engine-integration). #1 per-message metering via the LIVE wallet `reserve→settle/release`
  (release-on-failure never bills; **no `wallet.debit`**) · #2 per-tenant daily budget ceiling (free TG
  flows, metered over-cap → `blocked_budget`) · #3 per-contact/day frequency cap · #4 spend-anomaly
  (today > 3× trailing-7d median → founder priority-alert) · #5 per-(identity,channel) deliverability
  (403 → `dead` → next send blocked) · #6 per-bot token-bucket (30/s global + 1/s per-chat, founder-alert
  **priority lane**). 3 NEW FORCE-RLS tables (`ddl_comm_cost.sql`, additive). All permissive-on-fault;
  resting byte-identical (flags OFF). NO caller.py edit (guards live in the mounted `comm.engine.send`).
  10/10 comm suites PASS, gitleaks 0. Details: `_BUILD-LOG.md` (W3-COSTGUARDS).
- **W2+W3 LIVE DEPLOY** ✅ **DEPLOYED + VERIFIED (2026-06-15)** — the W2 brain + the 6 W3 cost
  guards are LIVE on the box for tenant `admin` (BE only; panel deploy still deferred to the single
  final canonical deploy). 13 comm files deployed md5-verified; `ddl_comm_cost.sql` applied (3 NEW
  FORCE-RLS tables → 7 comm tables FORCE-RLS); flags `COMM_BRAIN_ENABLED · COMM_COST_GUARDS_ENABLED ·
  COMM_METERING_ENABLED · COMM_TOKEN_BUCKET_ENABLED` flipped ON; **famit-caller restarted ONLY** (no
  caller.py edit — already mounted; box golden `ccf9715b` unchanged; NO agent.py touch). **LIVE PROOF:**
  `GET /comm/channels` 200 `configured:true` all flags live; getMe `mr_kunal_bot`; webhook no-secret →
  403 fail-closed. **REAL-MESSAGE pipeline LIVE** — `engine.send` reaches api.telegram.org for real
  (`http_400 chat-not-found`); only the founder chat_id is missing (`getUpdates=0` — he hasn't tapped;
  sentinel correctly absent, never faked; alert no-ops `no_founder_chat_id`, never blocks the loop). The
  webhook is deliberately NOT set (caller firewalled to the panel box only → would deaf-bot; stays
  getUpdates mode). **BRAIN PROVEN LIVE** — a real inbound through `/comm/webhook/telegram/admin`
  (valid HMAC secret → 200 stored) → Groq grounded Hinglish reply (`action=replied`); cost-guard #5
  deliverability proven live (`blocked_dead`). **EARNER GATE under an induced Telegram black-hole:**
  hot-path 0.017 ms snapshot + 0.016 ms create_task; detached run bounded (fresh-dest 0.75 s ≪ 8 s cap);
  agent.py `9150fabe` UNCHANGED, famit-agent PID 2808658 NRestarts=0 NOT restarted, /health 200, 0 5xx,
  NO ring. Details: `_BUILD-LOG.md` (## W2+W3 LIVE DEPLOY).
- **NEXT (the ONE founder action)** — founder taps `@mr_kunal_bot` once → the system auto-captures +
  persists his chat_id forever → the next hot lead lands a real Telegram alert on his phone. The public
  inbound webhook (for two-way contact replies) is a later infra task (panel proxy → no public ingress
  to the caller today). The FE goes live with the single final canonical panel deploy.

## Build order (from the plan §8)
| Wave | What | Channel | ~Effort |
|---|---|---|---|
| **W1** | Founder hot-lead alert + post-call auto-summary + setup UI | Telegram | 1.5-2 wks |
| **W2** | The LLM conversation brain (reply-only) + inbound webhook (fail-CLOSED) | Telegram | 1.5 wks |
| **W3** | Email + SPF/DKIM wizard + the cost-router + all cost guards + template builder | +Email | 2 wks |
| **W4** | Unified inbox + book_slot tool + output-safety + DLQ | all | 2 wks |
| **W5** | SMS (DLT-gated) + automation/journey engine + war-room | +SMS | 2-3 wks |
| **W6+** | CAPI signal closure (the moat) + team inbox + public API + in-chat payments | all | — |

## Founder credential actions (give these → we test on real numbers)
- **Telegram (W1, do this first):** @BotFather → `/newbot` → copy token; tap Start on your bot once. **~2 min, no verification, free.**
- **Email (W3):** Resend API key (+ optional own-domain DNS records via our wizard; or use the shared low-volume domain day-one).
- **SMS (W5):** MSG91 account + **DLT registration** (PE ID + header + post-call template) — **5-10 days, external, the one hard gate.**

## Conventions any build agent MUST honor (gate at review)
- `tenant_id TEXT` everywhere (== `org_id`); **REJECT any `uuid`/`UUID` PK/FK** (breaks the RLS GUC string-compare → fails-open-shaped). PKs `TEXT "<prefix>_<uuid4hex>"`. Money `BIGINT` paise.
- RLS = the `ddl_ai_wa.sql:95-116` admin-GUC `DO $rls$` block verbatim; `famit_app` NOSUPERUSER/NOBYPASSRLS.
- NO new credential table (reuse `provider_credentials`); NO new money table (reuse `wallet.reserve/settle` — there is **no `wallet.debit()`**); meter **per-message** (`idem_key=comms:{message_id}`).
- Consent = **`(channel × purpose)`**; `consent_basis` derived from `lead_source` (purchased lists ≠ service-implicit); consent log append-only (REVOKE + trigger); erasure = pseudonymize-in-place, two retention clocks.
- Webhooks **fail-CLOSED**, secret bound to the PATH tenant, RLS GUC set only AFTER verify. Deep-links signed single-use. Compliance gates are **server-side** send-path blocks, not UI.
- 6 security probes gate ship: **T-WEBHOOK · T-INJECT · T-LEAK · T-VAULT · T-DEEPLINK · T-GATE.**
- 6 cost guards are acceptance gates, not "later": per-message metering · per-tenant daily budget · per-contact frequency cap · spend-anomaly alert · per-(identity,channel) deliverability state · per-bot token-bucket + segment-accurate SMS pricing.
- BE/Opus, FE/Sonnet + the `frontend-design` skill, **reuse Core_2 never from scratch**; deploy FE only when no other FE wave is mid-deploy.

## Related files (outside this folder)
- `caps/NEXT-BIG-BUILDS.md` — the product backlog (this is a top item).
- `caps/ORCHESTRATOR.md` — the wave ledger / compaction-proof brain.
- `caps/WORKFLOW_LEDGER.md` — one-line-per-wave history.
- `droplet_work/provider_registry/` — the LIVE registry/credential vault this clones.
- `droplet_work/whatsapp_builder/` — the WA builder pattern (`build_router`, `ddl_ai_wa.sql`) to mirror.
- `droplet_work/caller.py` — the live earner (the `_finalize_call` seam; pull box-fresh + md5 before any edit; claim `CALLER_EDIT_LOCK.md`).

*Index written 2026-06-15.*
