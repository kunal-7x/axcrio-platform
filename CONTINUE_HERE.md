# CONTINUE HERE — resume pointer (newest on top)

> Read this first, then `MASTER_BUILD_STATE.md` → `git log --oneline -15` → `AGENT_LEARNINGS.md`.

## 2026-06-13 — 🟢 REC WAVE FINAL VERIFY (handoff-name + recordings + retention + earner) = ALL PASS

Independent honest verification of the whole REC wave on the LIVE box. **4/4 acceptance items PASS** (item 3 retention was the only unbuilt piece — built + verified this pass).

- **(1) HANDOFF caller-line — PASS.** Deployed `aim_voice_agent.py:740` says exactly `Ek second, main aapko {_dial_who} se connect kar rahi hoon.` where `_dial_who` = dialed person's `name` → `role` → `apni team`. NAMES the person and NOTHING else (no number/reason/AI-disclosure). `name` round-trips end-to-end LIVE: POST `/brain/handoff/add {"name":"VerifyRajesh"}` → GET `/brain/handoff` returns `"name":"VerifyRajesh"` in its OWN field (role empty); test entry removed, founder's original 2-entry list restored. `session.aclose()` AI-exit + same-room `create_sip_participant` bridge + `participant_disconnected` hangup all intact (18 refs).
- **(2) RECORDINGS — PASS.** Outbound auto-egress (REC-B): fresh after-gate call `55181bfa77` → object `outbound-recordings/2026/06/13/55181bfa77.ogg` 57235 B landed + `recording_key`/`recording_status:recording` on its row. Inbound finalize-on-read (REC-A): session `vs_dee5eeef4141` → `uploaded`/`duration_s:117` + presigned. Unified API: `GET /calls/61a6bfeada/recording` → presigned (361ch) → full GET HTTP **200** audio/ogg 56916 B + range **206** 1024 B (play+seek); inbound presign → **200** 1.6MB + **206**. `GET /contacts/+918949906361/recordings` → 8 calls newest-first, `with_recording:1`, both directions unified. Tenant-scoped: `require_object(...not_found=True)`→404 (outbound BOLA) + RLS `_inbound_rec_items` (inbound). FE live on panel (BUILD_ID `4aXNPr1rvAfpK4ku5dNa7`): CRM Recordings card + `<audio>` player + Download, handoff name field.
- **(3) RETENTION — BUILT + PASS.** Was the ONE missing item (no lifecycle existed). Created 2 Spaces lifecycle rules on `capsy-recordings` (Status=Enabled): `outbound-recordings/`→expire 90d, `aim-recordings/`→expire 90d (read back confirmed). Bucket PRIVATE (unauth GET → 403 on both URL styles); access ONLY via presign-on-read. Spaces config only — NO code/earner touched.
- **(4) EARNER AFTER-GATE — PASS.** In-window outbound to `+917861019021` (job `cc09c4888b`, conc 1, now=1): livekit-sip INVITE via trunk `ST_fmtVmNJmpzKa`, `+918071583488`→`+917861019021`, sipCallID `XY5QFVaxg3O8G8CNaen0L9iqrcc`, returned **486 Busy Here / USER_REJECTED** = carrier RANG it (real ring). agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED; famit-agent MainPID `1477083` / ActiveEnter 2026-06-10 NEVER restarted; all 3 services active; `/health`=200; 0 5xx; 0 Traceback. Nothing restarted this pass.

**FOUNDER RECIPE:** see AGENT_LEARNINGS.md (REC-FINAL VERIFY entry) — add a handoff person WITH a name → AI says "connecting you to <Name>"; open a lead in CRM → Recordings → play+download any call.

**RESIDUAL:** caller-line + recordings proven over API/SIP/Spaces; the two-party AUDIBLE bridge + the spoken named line still need ONE real inbound call by the founder to fully accept (everything upstream proven). 90-day retention chosen as a sane default — change `Days` in the lifecycle rule if the founder wants a different window.

## 2026-06-13 — 🟢 HUMAN HANDOFF "says yes then silence" = FIXED + VERIFIED (earner intact)

**Symptom (founder, live):** on an inbound call the caller says "mujhe insaan se baat karni hai" → AI says "haan/yes" → COMPLETE SILENCE, no hold music, the human number never rings. **Three identical-looking root causes, ALL now closed:**
1. **Tool never fired (PROMPT bug — the real code fix).** On the HINDI phrasing the small Groq primary (llama-4-scout) ANNOUNCED ("kya main aapko transfer karoon?") and fired NO tool that turn — it asked permission / narrated instead of invoking `transfer_to_human`. Fix = made the handoff instruction IMPERATIVE same-turn in 5 places of `aim_voice_agent.py` (customer inbound_note, customer disambiguation note, customer + manager `transfer_to_human` docstrings, manager prompt bullet): "the MOMENT the caller asks for a person (ANY language) you MUST call `transfer_to_human(reason)` IMMEDIATELY as your VERY NEXT action — do NOT ask 'kya main transfer karoon' / do NOT just say you're connecting them and wait; calling the tool is the ONLY thing that connects them; talking ≠ doing." No logic change.
2. **Dial leg 402'd (Vobiz empty).** FIXED by founder recharge — Vobiz funded (~₹495); the exact trunk/target rings now (proven below).
3. **LLM turn 429'd (Groq daily TPD).** FIXED by the `FallbackAdapter[Groq pool → SambaNova → OpenRouter-free]` from the prior wave (independent quota pools).

**`_do_warm_transfer` itself was already robust** — `_say_filler` / `_start_hold_audio` / the dial are all try/except-guarded with a finally-stop on the hold music, so any audio/asyncio failure degrades to spoken-only + STILL dials, never aborting into silence. Kept the proven same-room DIRECT `create_sip_participant(room_name=<caller room>, trunk ST_fmtVmNJmpzKa)` bridge — did NOT reintroduce the beta side-room.

### VERIFICATION (this session — honest, all PASS except the one residual)
- **Tool FIRES now (was the bug):** 3/3 healthy-Groq integrated turn-loop smoke runs fire `transfer_to_human` on BOTH Hindi AND English handoff turns (was 0 on Hindi pre-fix). Force-fail run (bad Groq key) logs `groq failed → switching` then `openrouter failed → switching` and the tool STILL fires via SambaNova = fails over, fires regardless. ✅
- **Dial leg RINGS (live SIP proof):** the EXACT primitive `create_sip_participant(trunk ST_fmtVmNJmpzKa, +916375548830)` → livekit-sip callID `SCL_xi94NuKM2tAQ`: `inviteToRingingMs:1302` (180 RANG) + `inviteToAcceptMs:5047` (200 OK ANSWERED) + RTP + `result:success`. The opposite of the empty-Vobiz 402 era. ✅
- **Deployed on box:** `aim_voice_agent.py` md5 `61f2e0e642727eacfa54367e683048bc` (backup `*.HORTbak.20260613-093052`), py_compile OK on `/opt/capsy-agent/.venv`, worker re-registered clean `agent_name:manager` `AW_hGPByd3DAg74`, **0 ImportError/Traceback**, **0 5xx** since restart. ✅
- **EARNER GATE before+after PASS** — agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED; famit-agent MainPID 1477083 / ActiveEnter 2026-06-10 19:58 NEVER restarted; in-window REAL outbound to founder `+917861019021` (callID `SCL_BYbA8zxAK4Qr`, trunk `ST_fmtVmNJmpzKa`): `Outbound SIP call established` + `accepting RTP stream` + agent↔phone track + `inviteToRingingMs:1570`/`inviteToAcceptMs:12209` + ~70s live media + clean BYE = RANG + ANSWERED. Only famit-caller (09:37) + aim-voice-agent (09:38) restarted. ✅

**HONEST RESIDUAL:** no real INBOUND call was placed this pass (the inbound DID +918071583488 needs the FOUNDER to dial in). So the live hold-music PUBLISH + the actual two-party audible bridge on a real inbound handoff are the ONE thing still unproven end-to-end. Everything upstream is proven: tool fires reliably (small-model Hindi included), the chain fails over, the dial leg rings/answers on the exact trunk/target, the bridge code is the proven same-room path. The 30-second founder test below is the final proof.

### FOUNDER TEST RECIPE — "does human handoff work now?" (60 seconds)
1. From your phone, call **+918071583488**.
2. Riya greets you. Say (in Hindi or English): **"Mujhe kisi insaan se baat karni hai"** (or "I want to talk to a human / person / banda / aadmi").
3. ✅ EXPECT: she says she's connecting you, then you hear **hold music** (NOT silence).
4. ✅ Within a few seconds, **+916375548830 RINGS**. Answer it.
5. ✅ You (the human) hear a one-line whisper of context, then you and the original caller are on the **SAME call** — talk freely.
6. If the human number does NOT answer → Riya apologises, fires a **hot-lead WhatsApp** to the team, and logs a callback — you should NEVER get dead silence.
**If you EVER get "yes then silence" again:** check (a) Vobiz balance (must be funded — empty = no ring), and (b) whether every turn says "thoda sa system slow" = Groq daily quota exhausted (top up Groq, don't change code). The tool-firing prompt fix is permanent.

### Backups / rollback (box)
`aim_voice_agent.py.HORTbak.20260613-093052`. Rollback = restore it + `systemctl restart aim-voice-agent` (reverts to the announce-don't-act prompt → Hindi handoff may narrate instead of dialing; do NOT roll back unless directed). NEVER touch agent.py / trunk / firewall / SIP container.

---

## 2026-06-13 — 🟢 INBOUND AI MANAGER = RESTORED + VERIFIED WORKING (the production incident is CLOSED)

**Incident:** AIM greeted fine then repeated the filler "thoda sa system slow hua hai" on EVERY turn; inbound customer also dead. **Root cause (NOT a code regression):** Groq **daily-token (TPD) exhaustion** — all keys share ONE org's 500k/day pool, drained by a day of stacked AIM voice-wave testing → every real LLM turn 429'd → error handler spoke the filler. **Fix (already applied, entry below in AGENT_LEARNINGS):** wrapped AIM's LLM in `llm.FallbackAdapter([groq, openrouter-free])` — Groq stays primary (auto-heals when the bucket refills), fails over to a FREE OpenRouter model (`openai/gpt-oss-120b:free`, independent daily pool, $0). Only `/opt/famit-agent/aim_voice_agent.py` changed (backup `*.EMERGbak.20260612-182751`); NOT a revert.

### VERIFICATION (this session — integrated, honest, all PASS)
- **(1) Manager turn loop WORKS** — drove the real `_aim_llm` + 15 real tools inside `http_context` while Groq was STILL 429ing (so OpenRouter failover was actually exercised): greeting answered, **PIN 4827 → verified=true**, "kitne hot leads hain" → `check_leads` → **REAL DATA** "5 hot, 1 warm, 1 cold", "campaigns list karo" → **8 real campaigns**. NO filler. ✅
- **(2) Customer path responds reactively** — CustomerSalesAgent (same `_aim_llm`) answered an open question + a "3 BHK price?" via the `lookup` RAG tool with a **real ₹1.32cr price**. No silence/filler. ✅
- **(3) EARNER GATE before+after** — agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED; famit-agent active PID 1477083 NEVER restarted; a FRESH out-of-window outbound **RANG** (+917861019021, SIP room `famit-917861019021-3f2db7`, participant joined); core 401-alive, 0 5xx; only famit-caller+aim-voice-agent restarted. ✅

**HONEST RESIDUAL:** only a real founder phone call fully proves the audio leg end-to-end (STT→LLM→TTS over the live SIP room). The harness proves the LLM+tools+data leg (the part that was broken) conclusively. ⚠️ The earner's agent.py shares the SAME Groq org TPD pool — heavy AIM test-burn can still starve the live earner's LLM on a busy outbound day. **Founder action (not blocking):** give the earner its own fallback too OR add a second Groq org, and gate AIM test volume.

### FOUNDER TEST RECIPE — "is my AI Manager fixed?" (30 seconds)
1. Call **+918071583488** from your phone.
2. It greets you. When it asks, say your PIN: **"four eight two seven"** (4827).
3. Say: **"Kitne hot leads hain?"**
4. ✅ EXPECT: a real answer like *"Aapke paas 5 hot leads hain"* — **NOT** "thoda sa system slow hua hai".
5. (Optional) Say **"Mere campaigns list karo"** → it names your real campaigns.
If you EVER hear "thoda sa system slow" on every turn again → Groq's daily quota is exhausted again; the fix is to top up Groq capacity (Dev Tier / second org), not to change code.

### Backups / rollback (box)
`aim_voice_agent.py.EMERGbak.20260612-182751`. Rollback = restore it + `systemctl restart aim-voice-agent` (loses the FallbackAdapter → back to pure-Groq, which fillers again until the bucket refills — so do NOT roll back unless directed). NEVER touch agent.py / trunk / firewall / SIP.

---

## 2026-06-12 — PER-TENANT HUMAN HANDOFF BACKEND = DONE + VERIFIED (earner intact)

**Branch:** `feat/premium-ui` · **Commits:** `7934783` (CRUD config layer) + `36d1afa` (voice UX).
**Box:** `famit@168.144.153.145` `/opt/famit-agent` · **caller listens on :8209** (NOT 8000).

### Status — all 6 acceptance items PASS (independently re-verified live)
1. Per-tenant CRUD — tenant-isolated (token-scoped, body tenant_id/org_id stripped), +91-validated, idempotent. ✅
2. Hold-audio-while-ringing, NO side-room regression (direct same-room `create_sip_participant`). ✅
3. Whisper-on-answer then AI steps back. ✅
4. Fallback + gating (enabled flag + availability hours; all-fail → apology + hot-lead WhatsApp + callback). ✅
5. Live monitor shows the current number (`Dialing #N` → `Bridged`); each attempt logged to analytics JSONL. ✅
6. EARNER GATE after = +917861019021 RANG; agent.py md5 `9150fabe…` UNCHANGED; famit-agent never restarted; 0 5xx. ✅

### What's NEXT (not this wave)
- **FRONTEND handoff-list UI wave** (panel) — consume the API contract below. The panel is busy now; do this when no other wave is editing `famit-panel`.
- `hot_lead_alert` Meta template approval (cold team alert currently 404s gracefully; `post_call_followup` sends a real wamid).
- Optional: a true two-human end-to-end inbound bridge test (proven by parts today).

### Backups / rollback (box)
`*.HOTLbak.20260612-170656` + `*.HOFXUXbak.20260612-172359` (caller.py, ai_manager/voice_tools.py, aim_voice_agent.py). Rollback = restore backups + `systemctl restart famit-caller aim-voice-agent`. NEVER touch agent.py / agent / trunk / firewall / SIP.

---

## FOUNDER TEST RECIPE — "does my human-handoff work?" (dead simple)

**A) Manage my handoff team by voice (the AI does it for me)**
1. Call the AI Manager DID **+918071583488** from your phone.
2. When it asks, say your PIN: **4827**.
3. Say: **"List my handoff team."** → it reads back who's on it.
4. Say: **"Add Rajesh +91 63755 48830 to my handoff team."** → it confirms "added".
5. Say: **"List my handoff team"** again → Rajesh is now there.
6. Say: **"Remove +91 63755 48830 from my handoff team."** → it confirms "removed".
   (If you give a number that isn't a valid Indian mobile, it politely refuses — by design.)

**B) Watch a real transfer happen (hold music + whisper + bridge)**
1. Make sure at least one number on your handoff team is reachable (e.g. your second phone).
2. Call the AI Manager DID and, mid-conversation, say **"I want to talk to a human"** (or trigger a hot lead).
3. You (the caller) immediately hear a calm line + **hold music** while the human's phone rings — never silence.
4. When the human picks up, they hear a one-line context whisper, then you're **bridged two-way** and the hold music stops.
5. If the first number is busy / no-answer / outside its hours, it automatically tries the **next** number in your list.
6. If nobody answers at all, you hear a short apology, a **callback is logged**, and a **hot-lead WhatsApp** goes to your team — never a dead drop.

> Note: the AI must hear the PIN before it will read or change your team — this protects who real calls get transferred to.

---

## BACKEND API CONTRACT — for the FRONTEND handoff-list UI wave

Base: the caller service. Auth: tenant **from the token** (Bearer JWT or `X-Auth`), never from the body. All handoff routes are **write-role gated** except the GET. Tenant A can never see/touch tenant B's list.

### Data shape — one handoff team member
```json
{
  "phone":    "+916375548830",   // canonical +91XXXXXXXXXX (E.164 India). REQUIRED.
  "whatsapp": "+916375548830",   // defaults to phone if omitted
  "role":     "sales head",       // free text label (shown in UI), optional
  "hours":    "24x7",             // "24x7"/"" = always; or "HH:MM-HH:MM" IST window (handles midnight wrap)
  "priority": 1,                   // integer, 1 = dialed first; auto = max+1 on add
  "enabled":  true                 // false = paused (skipped on transfer), default true
}
```
The list is always returned **priority-sorted ascending**.

### Routes
| Method | Path | Body / Query | Returns |
|---|---|---|---|
| `GET`  | `/brain/handoff` | — | `{ "handoff": [ <member>, … ] }` |
| `POST` | `/brain/handoff/add` | JSON `{phone, whatsapp?, role?, hours?, priority?, enabled?}` | `{ "handoff": [...], "ok": true }` · **400** `{error, handoff}` on invalid phone (non-+91 / malformed). Idempotent: re-adding a number **updates** it. `priority<=0`/omitted → appended (max+1). |
| `DELETE` | `/brain/handoff/remove` | `?phone=<+91…>` (or JSON `{phone}`) | `{ "handoff": [...], "removed": bool, "ok": true }` · removing a missing number is a no-op (`removed:false`, not an error) |
| `PUT`  | `/brain/handoff` | JSON array `[<member>,…]` **or** `{"handoff":[…]}` | `{ "handoff": [...] }` — REPLACES the whole list (use for drag-reorder: send the full list in the new priority order) |
| `POST` | `/handoff/notify` | JSON `{name, phone, summary?, score?}` | hot-lead WhatsApp send report `{ok, sent, attempts, results[]}` (internal/fallback; UI usually won't call this) |

### Live monitor (for a "transfer in progress" widget)
`GET /ai-manager/live` → `{ "calls": [ { room, caller, mode, state, handoff, handoff_target, started, updated, tenant_id }, … ], "count": N }`
- `handoff` ∈ `none | Requested | Dialing #1 | Dialing #2 | … | Bridged | Failed`
- `handoff_target` = the +91 number currently being tried / bridged.
- Tenant-scoped from the token (admin sees all).

### Analytics (for a handoff report page — read the file or expose a route later)
Durable JSONL at `var/aim_handoff_attempts.jsonl`, one row per attempt:
`{ts, iso, tenant_id, room, number, attempt, outcome, wait_s, reason}` where `outcome` ∈ `answered | no_answer | busy | invalid | out_of_hours | error`.

### Validation the UI should mirror (so it fails fast client-side)
- Phone must canonicalise to `+91` + 10 national digits (13 chars). Reject foreign / malformed before POST.
- `hours`: accept `24x7`/blank or `HH:MM-HH:MM`; anything else is treated as always-on (fail-open) server-side.
- `priority`: integer ≥ 1; the UI's drag-reorder = `PUT` the full list in new order.
