# MASTER BUILD STATE — read this FIRST after any compaction

> **Resume protocol:** read THIS → `design/PRODUCTION-ROADMAP.md` → `git log --oneline -20` → `WORKLOG.md` → the memory index. Update this after EVERY wave (durable brain; survives compaction).

## WHO / GOAL
Famit/Axcrio = ONE connected lifecycle: **outbound AI call → per-person memory → WhatsApp follow-up (template→LLM convo) → inbound callback with FULL history → hot-lead → warm-transfer to human + hot-lead-to-team WhatsApp.** Goal = finish it, make it **production-grade + SELLABLE**. Founder non-technical, wants full autonomy + fast, but **every step secure**. "LLM everywhere."

## 🟥 #1 RULE (learned hard 2026-06-12)
NEVER edit shared outbound infra (agent.py, outbound trunks `ST_fmtVmNJmpzKa`/`ST_LH8ighJJtHSi`, firewall `livekit-vobiz-fw.sh`, SIP container) for inbound — I broke the live earner that way (firewall dropped 219 outbound INVITEs). New capability = **additive + isolated** (own worker/port/service/trunk). **Regression-gate EVERY box change:** `famit-agent` active + a REAL outbound test call RINGS, before AND after. Commit to git + update this file each wave. Run ONE box-mutating wave at a time (sequential = secure).

## CURRENT STATE (2026-06-12)
- **Outbound calling = RESTORED + ringing** (firewall fixed: outbound allows to 10 Vobiz IPs by dest + SIP DNS pinned 13.203.7.132).
- **WhatsApp post_call_followup template TEST = SENT + accepted** to +917861019021 (wamid returned) — founder received it. WhatsApp NOT cred-blocked (Meta creds on box).
- Connected pipeline ≈ **70-80% built as components, not wired into one loop**.

## KEY CONCRETE FACTS (from audits — saves rediscovery)
- **WhatsApp template builder**: "create→thinking→try again" = **DEAD Groq key on box** (403 err1010) + no OpenRouter fallback. Real Meta TEXT-template submission ALREADY WORKS (proven). **Image-banner header missing** (no resumable upload → interim host on DO Spaces + submit `example.header_url`).
- **WhatsApp post-call automation** ~80% built: send/template/webhook/multi-turn-reply-brain all WORK. GAPS: G1 post-call auto-send uses free-form (Meta rejects cold) not the approved template; G2 template name unwired; G3 gate `fields.wa_followup=False` on ALL campaigns; G4 language `en` not `en_US` (404s); G5 reply brain context THIN (doesn't load call summary + `memory.build_recap`).
- **Inbound voice** P0 BROKEN: Sarvam STT `max_retry=0` → one blip kills session before greet → silence. Fix = FallbackAdapter + APIConnectOptions(max_retry) + greet-first (HUMAN-LIKE, not "I am an AI assistant") + never-silent + registry-seed founder numbers (06375548830 + 917861019021). SIP inbound trunk/dispatch EMPTY (Phase-1 = RISKY shared-infra, additive TCP-5060).
- **RAG/pgvector** BUILT (`kb/core.py`) but corpus EMPTY + embedder dormant → populate + configure.
- **Per-person memory** EXISTS (`var/memory/<digits>.json`); outbound recaps; **inbound + WhatsApp-reply do NOT read it yet** (keystone gap).
- **Warm transfer**: chosen = dial-human-into-room conference (carrier-agnostic). **Handoff list** → vendor Business Brain (`var/brain/<tenant>.json`) + Settings→Human-Handoff card. Hot-lead scorer exists (interest≥70). Image gen = Pollinations free default.

## 🔨 BUILD MODE — LOCKED (execute this queue SEQUENTIALLY + AUTONOMOUSLY; do NOT re-plan, do NOT ask)
Plans ARE DONE (INBOUND-PIPELINE-MASTER-PLAN v1/v2 + PRODUCTION-ROADMAP + design/*.md). **Founder standing order (2026-06-12, verbatim intent): STOP planning — BUILD everything, wave after wave, ONE secure box-mutating wave at a time (SEQUENTIAL, never parallel on the box — sequential = no break), each additive + backup-first + regression-gated (real outbound call to +917861019021 RINGS before+after) + committed to git + this ledger updated. When a wave finishes, IMMEDIATELY launch the NEXT in the queue. Each wave = its own ultracode with RICH context. Only pause to report a win or a genuine founder-blocker (cred / Meta-template-approval). NEVER ask "should I build" again — the founder said he will not repeat it.**

### BUILD QUEUE (in order — mark DONE as completed):
1. [RUNNING wfa4phnkp] **WhatsApp P0/P1** — template-builder Groq-key fix + post-call approved-template auto-send + deepen reply context (call summary + memory).
2. **Inbound voice Phase-0** — STT FallbackAdapter + APIConnectOptions(max_retry) + greet-FIRST + HUMAN-LIKE greeting (not "I am an AI assistant") + never-silent guard + registry-seed founder numbers (06375548830 + 917861019021). aim_voice_agent.py ONLY (isolated; restart aim-voice-agent only).
3. **Inbound SIP wiring Phase-1** — additive TCP-5060 trunk+dispatch+allowlist (⚠ touches SIP container + firewall = the thing that broke the earner → EXTREME care, additive only, earner regression-gate before+after, rollback ready).
4. **Inbound MANAGER mode** — conversational command slot-filling (which campaign/leads/how-many → confirm → execute via workforce; PIN/step-up).
5. **Inbound CUSTOMER mode** — returning-caller loads memory+WA-thread+RAG & continues; new-caller campaign-ask; runs sales like outbound; creates the lead.
6. **Human HANDOFF** — dial-human-into-room conference + per-vendor handoff list (Business Brain + Settings→Human-Handoff card) + hot-lead→team-WhatsApp.
7. **RAG** — configure embedder + populate KB (campaign knowledge) + wire grounding into voice + WhatsApp.
8. **Logging/recording/session-history** + panel surfaces (call history, WA-thread viewer, handoff card, DID admin).
9. **Production hardening** — reliability/monitoring, onboarding, billing/metering, multi-vendor RLS isolation, scale → SELLABLE.
Each item: verify (real test) + commit + update this ledger BEFORE launching the next.

## RUN LEDGER (newest first; append after each)
- wfa4phnkp (U1) — WhatsApp template-builder BACKEND fix — DONE (2026-06-12). FINDING: the "DEAD GROQ_API_KEY / 403 err1010" premise was WRONG — err1010 is a Cloudflare block on the LOCAL dev IP; FROM THE BOX the live GROQ_API_KEY returns 200 and the generate route already works (status:accepted, real AI templates, model groq:llama-4-scout). Root cause of any "create→thinking→try again" is NOT the backend LLM (healthy) — likely the FORTRESS panel/proxy or FE path (open item to chase). STILL SHIPPED (all additive, backup-first, regression-gated): (1) added the missing OpenRouter fallback to /opt/famit-agent/.env (OPNEROUTER_API_KEY + OPENROUTER_API_KEY + WAB_OPENROUTER_MODEL) so a Groq outage no longer blanks the builder; (2) added SPACES_* (mapped from DO_SPACES_*) + installed boto3 in the capsy venv so the shared media_gen.spaces client is LIVE on the box; (3) IMAGE-BANNER header fix — meta_submit resolves banner bytes → DO Spaces (provenance) → Meta **Resumable Upload API** → example.header_handle (header_url 500s on message_templates create — handle is the supported path; app_id 2741460946218468 derived from token, persisted as META_WA_APP_ID). SMOKE PROOF on box: TEXT submit→200 PENDING (deleted), IMAGE-header submit→200 PENDING (deleted). REGRESSION: real outbound to +917861019021 RANG before+after (agent room+Hinglish opener+tts_ttfb~0.35s); core /me /campaigns /leads 200; zero 5xx; famit-agent untouched. Backups: .env.WAPbak.20260611-232133, whatsapp_builder/{meta_submit,__init__,config}.py.WAPbak2.20260611-233410 (+ meta_submit/__init__ .WAPbak.20260611-232307). Files mirrored to droplet_work/whatsapp_builder/ (force-tracked). NOT YET DONE (this wave's other items): post-call approved-template auto-send (caller.py _wa_ai_followup sends free-form→Meta rejects cold; should send the APPROVED post_call_followup template) + deepen reply context (call summary + memory.build_recap).
- (prev) WhatsApp build wave — template-builder fix + post-call automation wiring + deepen reply context.
- wqost7wmt — WhatsApp automation explore/test — DONE (template SENT ok; gaps G1-G5 found).
- w83r2d6w2 — production-readiness audit → roadmap — DONE.
- wm86wda65 / whfbhmhxw — inbound plan V2 / V1 — DONE.
- Earlier: outbound-earner restore; image-render+ModelsLab+Pollinations; AIM run-campaign fix; control/workflow/whatsapp fixes; sales proposal + investor deck; architecture docs; growth-os phase0; secure git push → repo github.com/kunal-7x/axcrio-platform private @ 2bd0343.

## BOX / CREDS
Backend `famit@168.144.153.145` (priv 10.122.0.4), key `C:\Users\kunal\.ssh\do-blr-test\id_ed25519`, app `/opt/famit-agent/`, X-Auth `FamitCall2026`, capsy venv `/opt/capsy-agent/.venv`. Frontend `root@143.110.247.249` `/opt/famit-panel` (FORTRESS deploy backup-first). Creds `.env.local` + `lead/ALL_CREDENTIALS.md` (gitignored). Inbound DID +918071583488; founder test phone +917861019021; PIN 4827.
