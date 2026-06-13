# NEXT-BIG-BUILDS — COMPLETE MASTER QUEUE (post-audit 2026-06-13)

> Single sequenced backlog of EVERYTHING planned-but-unbuilt across the whole project (reconciled vs the LIVE box by audit a7b7853). Build TOP-DOWN, one box-mutating wave at a time (shared caller.py + panel + FORTRESS deploy + the server rate-limits heavy parallel load). READ-ONLY research may parallelize; BUILDS are sequential. EVERY wave: explore→research→design→build (backend→frontend→DB→AI→security)→verify on the founder's REAL flow, **autonomously add the out-of-box / sellable / differentiating features he didn't name** (global-memory mandate), earner-gated (agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` untouched), append AGENT_LEARNINGS + update ORCHESTRATOR.

## P0 — NOW / NEXT (core, founder-reported, quick)
1. **Campaign-run fix** [agent a06ee231 RUNNING] — can't run campaigns; prime suspect = my recordings auto-egress blocking `run_job` dial (make recording best-effort, never block the call); + window/Vobiz/suppression. Proof = a real ring.
2. ~~**FIXES wave**~~ ✅ **DONE + VERIFIED LIVE 2026-06-13** — (a) image preview/asset-click-empty FIXED (asset-detail folds the current-version PRESIGNED url; live GET 200 image/jpeg ~50–63KB on founder+admin tenants); (b) CRM transcript chat-view SHIPPED (customer RIGHT / AI LEFT; `GET /calls/{room}/transcript` → 200/94 turns/roles {ai,customer}, tenant-scoped 404 cross-tenant). Deployed FORTRESS BUILD_ID `tuuIjqN7fCf_iEL-obLon`; commits `d9daa86`+`6940742`; earner untouched (agent.py md5 `9150fabe…` unchanged, famit-agent never restarted). 3/3 PASS.
3. **Multilingual adaptive voice + greeting glitch** — per-turn Sarvam language-detect + LLM mirrors the caller (Hindi↔English↔Hinglish); fix the "Hello/Haan" opening. INBOUND `aim_voice_agent.py` SAFE; OUTBOUND `agent.py` GATED.
4. **Two-party inbound handoff** — PROVEN by parts; needs ONE real founder inbound call to confirm (60-sec test).

## P1 — big builds (sequential, back-to-back)
5. **Model/Voice switcher Phase-1** [PAUSED, resume `wf_4d047a56-724`] — Lean/Standard/Premium slider + ₹/min cost-meter + free voice preview + custom-provider CRUD + recommender/health/favorites (Run-page; caller.py /voices,/voice-preview,/providers,/tiers; ~90% SAFE). **Founder is owed this — build next after P0.**
6. **AIM Access + PIN** (`.wf/aim-access-and-pin.js` STAGED) — repoint Setup tab → live `/ai-manager/numbers` CRUD + `POST /firewall/pin/change` (verify-old→new) + audit/grants/lockout/last-used.
7. **🔒 Funnels/Media MOUNT-BLOCKER security fix** — `funnel_wiring`/`media_gen` read tenant FROM BODY (cross-tenant hole) → build a token-deriving `build_router` BEFORE serving. Do this with/before the Workflow wave. (P1-SECURITY.)
8. **Workflow/Funnel execution** — human-language node labels (not raw JSON) + wire Trigger→pick leads→pick campaign→Run to `/run` + ≥1 working template that actually runs.
9. **VIDEO STUDIO** — sub-page prompt→video→preview→assets (provider abstraction, `media_gen/video/*`); "add your API key"; manual video upload; library **Images↔Videos toggle**; attach video+image/banner to WhatsApp + Ads. Dormant until a founder video key (→ Vault).
10. **VAULT** — PIN-gated per-vendor encrypted secret store (API/private keys, numbers); super-admin always-on, vendor HIDDEN-by-default + super-admin toggle; flexible for future self-hosted models; reuse control HIDE/LOCK + firewall PIN + key-store.
11. **🛡️ Earner own LLM fallback** [GATED-on-agent.py, founder sign-off] — the earner shares ONE Groq org TPD pool with AIM test-burn → can starve the LIVE earner (real risk, flagged in 3 ledgers, never built). Give agent.py its own FallbackAdapter or a 2nd Groq org + gate AIM test volume. **Highest-value forgotten SAFETY item.**
12. **RAG: populate + wire** — `kb/core.py` BUILT but corpus EMPTY + not wired into voice/WhatsApp; embedder dim already 1024 (the 1536 concern is RESOLVED). Configure self-hosted BGE-M3 + load campaign knowledge + wire grounding into the agents.
13. **Per-person memory inbound + WA-reply** [keystone gap] — memory is read for OUTBOUND recaps only; load `var/memory/<digits>.json` + call summary into the INBOUND agent + the WhatsApp reply-brain (deepen G5 context too).
14. **#9 Hardening PART 2** — onboarding flow, billing/metering at scale, reliability/monitoring → SELLABLE (pt1 RLS+watchdog DONE).
15. **ai_asset go-wide** — `/api/assets/raw` stream (`version.local_path` unset, one-line map) + per-tenant ON/OFF gate (flag is global) + write the cross-module PG `events` leg. (Plus FE nginx `/api/assets/` proxy → `10.122.0.4:8310` — needs FE-box `143.110.247.249` root access.)

## P2 — forgotten / spec'd, lower urgency
16. **6 un-built Creative Studio sub-products** (specs exist, only image-banner shipped): **Brochure/Catalog · Creative-Batch (all-sizes) · Ads-Engine · Landing-Page Builder · 3D-Model · A/B Testing-Lab** (`design/creative-*.md`).
17. **Control-Layer C10 — AI Copilot entitlement gate** (probe T18) — the one un-shipped control unit.
18. **AIM step-up → runner approval-row wiring** — spend commands (e.g. ads.set_budget) silently re-park; wire AIM step-up → workforce approval/resume.
19. **WhatsApp residuals** — reply-brain deep context (call summary + recap); `hot_lead_alert` cold-team template (Meta approval); banner-in-builder (image-header upload live).
20. **Switcher P2** — A/B voice-tier test, hard budget auto-pause, per-call ₹ in call log, spend sparkline.
21. **OB-PROV** (outbound provider honor) — agent.py reads `fields.{stt,llm,tts}_provider`/tier; GATED (default-identical + ring-gate + founder sign-off).
22. **growth-os** — flagship ads monorepo SCAFFOLD-ONLY; `@growth-os/events` codegen build FAILS (Payload-suffix/dup-type bug) — fix that first; 6-container stack never booted (infra).
23. **Logto OIDC** wired into caller.py (deployed on hatchet box, not wired); control C2 Phase-2 admin-org binding.
24. **AIM dedicated-service 39-unit items** (superseded by in-process; per-user Argon2id PIN, strict-JSON NLU, PolicyEngine, CostGuard, compliance window/DLT gate, + 8 dashboard pages) — extract only if DO droplet limit raised. **P3.**
25. **media_gen monolith retirement** (superseded by ai_asset) — P3 cleanup.

## ⏸️ ON-HOLD (build ONLY when founder specifically asks)
- **Credit / Billing / Plans** (balance icon→Credits page, spend breakdown, Razorpay-ready, PLANS tiers) — wallet.py exists; dropped from auto-sequence 2026-06-13.

## 🔴 FOUNDER ACTIONS (unblock whole pipelines)
- **BIND ModelScope↔Alibaba Cloud** → image gen (`FOUNDER-MODELSCOPE-BIND.md`). · **Fix Meta WhatsApp** payment+verify+webhook → delivery (`FOUNDER-META-WHATSAPP-FIX.md`). · Video-gen API key → Vault. · Razorpay (when Credits un-holds). · Ads OAuth (Meta/Google). · SambaNova Developer tier. · FE-box root for the nginx /api/assets proxy.
