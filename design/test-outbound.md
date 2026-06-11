# Outbound Run/Dial Path — Health + Founder Run-Campaign Steps

**Verified:** 2026-06-11 (read-only; NO test call placed yet).
**Box:** `famit@168.144.153.145` (hostname `famit-livekit`) — the voice/caller BACKEND.
The panel UI (`panel.famit.in`) lives on the separate FORTRESS box and proxies to
this backend over the VPC (seen reaching in from `10.122.0.2`).

---

## VERDICT: OUTBOUND IS READY ✅ — no break found.

Every link in the live earner chain is up and the dispatch code is intact. One
**naming gotcha** (not a break) for the AI Manager — see §3.

---

## 1. Service / infra health (all GREEN)

| Component | State | Evidence |
|---|---|---|
| `famit-caller` (:8209) | **active**, `/health` = `{"status":"ok"}` | uvicorn pid listening on `0.0.0.0:8209` |
| `famit-agent` (voice worker "Riya") | **active** | systemd active |
| `famit-bridge` (LiveKit-SIP) | **active** 1d+ | systemd active |
| LiveKit server | **Up 8 days** (Docker `livekit-server`) | `127.0.0.1:7880` |
| LiveKit SIP | **Up 8 days** (Docker `livekit-sip`) | `0.0.0.0:5060/udp` + RTP `10000-10200/udp` |
| LiveKit redis | **Up 8 days (healthy)** | Docker `livekit-redis` |
| Outbound SIP trunk | configured | `TRUNK = LIVEKIT_SIP_TRUNK_ID = ST_fmtVmNJmpzKa` (caller.py:147) |
| Admin PIN (firewall) | **enrolled** for tenant `admin` | `var/pins.json` has `admin` record; PIN 4827 will pass |

Telephony chain: Vobiz SIP trunk (`VOBIZ_CALLER_ID +918071583488`) → LiveKit SIP
(5060/udp) → LiveKit room → `famit-agent` Riya. `agent.py` (Groq/Sarvam round-robin)
NOT touched.

## 2. Exact dial path (panel "Run a Campaign" button)

1. Panel **Run** page (`app/run/page.tsx`) builds payload (`buildRunPayload`, line 306)
   and POSTs to **`/run`** (caller.py:3071) — NOT `/campaigns/{id}/run`.
2. `/run` validates tenant/role/caps/balance, resolves the audience, creates
   `JOBS[job_id]`, fires `asyncio.create_task(run_job(job_id))` (caller.py:3071-3162).
3. `run_job` (caller.py:1971) dial loop, per lead (caller.py:~2055):
   `lk.room.create_room` → `lk.agent_dispatch.create_dispatch(agent="capsy")`
   → `lk.sip.create_sip_participant(sip_trunk_id=ST_fmtVmNJmpzKa, sip_call_to=num,
   ringing_timeout=45s)`.
4. Vobiz dials the lead; on answer, `famit-agent` Riya speaks. Call recorded
   (`record_call`), wallet/billing metered.

## 3. AI Manager "run a campaign" — the ONE caveat (verified live)

The AI Manager has TWO different intents — and ONLY one actually DIALS:

- ❌ **"launch / create / start a campaign"** → intent `campaigns.create` →
  `POST /campaigns`. This creates a **DRAFT ONLY. It does NOT dial anyone.**
- ✅ **"call hot leads" / "call all leads" / "call everyone"** → intent
  `leads.enqueue_calls` → tool `_leads_enqueue_calls` → **`POST /run`** (the real
  dialer, with `run_token`). THIS is what places calls.

**Live read-only NLU probe (no execution) of `POST /ai-manager/commands/test`
with `"call hot leads"` returned:**
```
intent=leads.enqueue_calls  risk_level=3  requires_pin=true
status=needs_pin  safe_to_execute=true
```
So the AI-Manager→dialer route is WIRED and LIVE, gated by PIN. The founder must
say **"call hot leads"** (not "run campaign <name>") to trigger a real dial via
the AI Manager. Flags confirmed ON: `AIM_ENABLED=1`, `WORKFORCE_ENABLED=1`,
`FEATURE_AI_MANAGER=1`, `FIREWALL_ENABLED=true`.

## 4. Founder steps — run a 1-lead campaign to your OWN number

**Your test number:** `+91 78610 19021` (`7861019021`, TESTE_PHONE_NO — confirmed
in inbound-setup + ALL_CREDENTIALS). **AI Manager PIN: 4827.**

### Path A — Panel "Run a Campaign" (most reliable)
1. Open `panel.famit.in` → **Run a Campaign**.
2. **Select a campaign** (required — the script Riya speaks).
3. Audience source → **Upload / Manual**: add ONE lead = your number
   `7861019021` (name e.g. "Founder Test"). Pick exactly that one lead.
4. Concurrency `1`. (If a calling-window guard returns "queued out of window",
   the run still auto-resumes; use the **Force** option to dial immediately.)
5. **Start.** Within seconds your phone rings; answer → Riya speaks.
   → This is the 1 sanctioned real test call.

### Path B — AI Manager command (proves the brain dials)
1. Open `/ai-manager` (Try-It / command box).
2. Type/say exactly: **`call hot leads`** (or `call all leads`).
   → NLU shows `leads.enqueue_calls`, risk: bulk, **needs PIN**.
3. Enter PIN **4827** → confirm → it executes `POST /run` and dials.
   ⚠️ This dials whatever leads match "hot"/"all" for the admin tenant — for a
   pure 1-lead proof, prefer Path A. Use Path B only after ensuring the only
   eligible lead is your own number (or accept it dials the current segment).

## 5. Cost discipline
Place AT MOST 1 real call, to `7861019021` only. Prefer **Path A with a single
manually-selected lead = your own number** so exactly one call goes out.
