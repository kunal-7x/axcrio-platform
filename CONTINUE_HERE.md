# CONTINUE HERE — resume pointer (newest on top)

> Read this first, then `MASTER_BUILD_STATE.md` → `git log --oneline -15` → `AGENT_LEARNINGS.md`.

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
