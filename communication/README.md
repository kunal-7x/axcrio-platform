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
- **NEXT (W1-P3)** — `founder_alert.py` + `post_call.py` + the caller.py `_finalize_call` insertions
  (founder hot-lead alert + post-call contact auto-summary; both `asyncio.create_task` + snapshot +
  per-channel timeout, NEVER awaited on the dial loop), then FE channel-setup + send-log view.

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
