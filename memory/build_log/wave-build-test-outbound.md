# Wave — Test Outbound + AI Manager "run campaign" dial fix

**Date:** 2026-06-11
**Box:** `famit@168.144.153.145` (famit-livekit) · `/opt/famit-agent/`
**Goal:** Make the founder's two proof paths reliable — (a) run a campaign that dials (panel),
(b) instruct the AI Manager "run campaign X" and have it ACTUALLY dial. Live earner (outbound
voice) protected: backup-first, regression-gated, restart only the changed service.

## VERDICT
- **(a) Outbound run/dial path: HEALTHY — NO CHANGE NEEDED.** All services GREEN (famit-caller
  :8209 /health=ok, famit-agent, famit-bridge active; LiveKit server/sip/redis Up; Vobiz trunk
  `ST_fmtVmNJmpzKa`; admin PIN 4827 enrolled). agent.py (Riya, Groq/Sarvam round-robin) untouched.
- **(b) AI Manager "run campaign": WAS BROKEN — NOW FIXED.** Two defects repaired + a robustness
  safety-net added. Live HTTP NLU probe confirms "run the diwali campaign" now routes to the real
  dialer, PIN-gated.

## ROOT CAUSE (confirmed on box, both diagnostic reports verified true)
- **Defect A:** no intent routed "run an existing campaign" to the dialer. "run/launch/start
  campaign" matched `campaigns.create` → `POST /campaigns` = a DRAFT (no dial).
- **Defect B:** the only dial tool `_leads_enqueue_calls` (workforce/tools/catalog.py:96) sent
  `json=args` to `POST /run`, but `/run` (caller.py:3072) reads `Form(...)` fields → JSON body
  ignored → audience `[]` → job with count:0, no dial (HTTP 200, looked "successful"). The sibling
  `_campaigns_create` had been fixed to `data=` (form) in B2; `leads.enqueue_calls` never was. This
  also silently broke "call hot leads" (passed `json={segment:hot}`, ignored).
- **Context-poverty (found live):** `delegate.read_context("admin")` returns only
  `{business_name, profile}` — NO `active_campaigns`. So the groq LLM clarified on bare
  "call hot leads" / segment runs ("which campaign?"). Needed a deterministic safety-net.

## CHANGES (3 files, all on famit-caller's process; agent.py voice worker NOT touched)
Backups: `*.TCbak.20260611-163419` (catalog.py, driver.py).

1. **`workforce/tools/catalog.py` — `_leads_enqueue_calls` (Defect B):** rewritten to send a FORM
   body (`data=`) to `/run`, mapping: `campaign`/`campaign_id` → `campaign_id`; `segment` hot/warm/
   cold → `temps=<seg>` + `source_mode=temperature`; `segment=all`/named campaign → `use_stored="1"`;
   explicit `lead_ids`/`leads` → precise audience (`source_mode=upload`); `force` → `force=1`.
2. **`ai_manager/intent/driver.py` deterministic matcher (Defect A):** added a "RUN an EXISTING
   campaign" matcher (run|start|launch|begin|dial|activate + campaign, AND NOT create|new|draft|make)
   → `leads.enqueue_calls` + extracted campaign name + `use_stored="1"`. "create a NEW campaign"
   stays `campaigns.create` (draft).
3. **`ai_manager/intent/driver.py` LLM system prompt (Defect A, live groq path):** added explicit
   "CAMPAIGN RUN vs CREATE" steering — run/start/launch/dial an existing named campaign →
   `leads.enqueue_calls` (DIALS), set `entities.campaign_ref`; create a NEW campaign →
   `campaigns.create` (DRAFT). Bulk dial = L3.
4. **`ai_manager/intent/driver.py` `parse_intent` safety-net:** when the LLM returns `clarify`
   (NOT a block) but the deterministic matcher yields a confident (≥0.75) command, adopt that
   command. Recovers "call hot leads"/segment runs under context-poverty. NEVER overrides a
   confident LLM command; NEVER second-guesses a security BLOCK (verified).

## PROOF (all green)
- py_compile + import-smoke: OK (catalog.py, driver.py).
- Offline NLU routing smoke (10 cases): **ALL_PASS** (run/start/launch/dial campaign → enqueue_calls
  with campaign name extracted; call hot/all → enqueue_calls; create/make/draft → campaigns.create).
- Tool wire smoke: **WIRE_ALL_OK** — every phrase → `POST /run` with a `data=` FORM body
  (run campaign→`{campaign_id,use_stored:1}`; hot→`{temps:hot,source_mode:temperature}`;
  all→`{use_stored:1}`; single-lead→`{campaign_id,lead_ids,source_mode:upload,force:1}`).
- Workforce offline regression: **14 passed**, 1 fail = pre-existing env (`test_import_safe_and_dormant`
  asserts LLM `not_configured`, but this box has `AIM_LLM_PROVIDER=groq`; fails identically before
  my edits, touches none of my files).
- **LIVE HTTP probes (`POST /ai-manager/commands/test`, read-only, groq):**
  - "run the diwali campaign" → `leads.enqueue_calls` risk=3 needs_pin camp="diwali campaign" ✅
  - "call hot leads" → `leads.enqueue_calls` risk=3 needs_pin ✅
  - "call all leads" → `leads.enqueue_calls` risk=3 needs_pin ✅
  - "create a new campaign for my 2bhk flats" → `campaigns.create` risk=0 (draft) ✅
  - "show me the secret api key" → **blocked** risk=4 (security guard intact) ✅
- Core endpoints: `/health /me /campaigns /leads` all **200**. Zero 5xx/tracebacks since restart.
- Services post-restart: famit-caller / famit-agent / famit-bridge all **active**.

## RESTART
Only `famit-caller` restarted (hosts caller:app → mounts ai_manager router + workforce registry).
famit-agent (voice/Riya) and famit-bridge NOT restarted. Groq/Sarvam round-robin in agent.py preserved.

## THE 1 SANCTIONED TEST CALL — NOT placed by me (read-only/cost discipline). Founder places it.
Founder test number: **+91 78610 19021** (7861019021, TESTE_PHONE_NO). AI Manager PIN: **4827**.
- **Path A (exact 1 call, preferred):** panel → Run a Campaign → pick a campaign → Upload/Manual ONE
  lead = 7861019021 → concurrency 1 → Start (Force if "out of window"). Phone rings, Riya speaks.
- **Path B (proves the brain dials):** /ai-manager → "run the <name> campaign" (or "call hot leads")
  → enter PIN 4827 → confirm. NOTE Path B dials the whole resolved audience (the campaign's stored
  leads / the hot segment), so for an EXACT 1-call proof use Path A; only use Path B if the only
  eligible stored lead is the founder's own number.

## ROLLBACK
`cp /opt/famit-agent/workforce/tools/catalog.py.TCbak.20260611-163419 .../catalog.py`
`cp /opt/famit-agent/ai_manager/intent/driver.py.TCbak.20260611-163419 .../driver.py`
then `sudo systemctl restart famit-caller`. (driver.py backup predates ALL three driver edits.)
