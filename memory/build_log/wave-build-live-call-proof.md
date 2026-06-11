# Wave — LIVE OUTBOUND CALL PROOF + AI Manager run-campaign demonstration (2026-06-11)

Box: `famit@168.144.153.145` (famit-livekit). NO git. NO code edits this session (the
NLU/dialer fixes from the prior `*.TCbak.20260611-163419` wave are already deployed & live).
NO service restarts this session.

## Founder OWN test number — found & used
`+91 78610 19021` (`+917861019021`) — labeled "Authorized test caller (`TESTE_PHONE_NO`)" in
`ai_manager_INBOUND_SETUP.md` (lines 115, 164) and present as `test_phone_number_2=7861019021`
in `lead/ALL_CREDENTIALS.md`. Clearly the founder's. The other two numbers in ALL_CREDENTIALS
(`6375548830`, `6375357023`) are ambiguous and were NOT called.

## (a) ONE real outbound AI call — PLACED & PROVEN
Path = the LIVE earner: `POST /run` (FORM body) on :8209 → `run_job` dial loop → Vobiz SIP → LiveKit → PSTN.
- Pre-check `POST /run/preview` → `count:1, callable_count:1, suppressed_count:0` (exactly 1 lead).
- Placed: `POST /run` with `campaign_id=c17e55e9f3` (Codename Joy 3.0, status ready),
  `leads=FounderTest,7861019021`, `concurrency=1`, `force=1`. NO use_stored/temps/source_mode
  (so it dials ONLY the one number).
- Response: `{"job_id":"ee2d64da67","count":1,"suppressed_count":0}`.
- Status poll: `calling` → `done` for `+917861019021`.

### Hard proof (call record + ledger)
- call id: **`7c1364ec76`**  phone **`+917861019021`**  campaign **Codename Joy 3.0 (c17e55e9f3)**
- LiveKit room: **`famit-917861019021-c9b218`**  ·  SIP call id: **`SCL_HeUUdXRi4Ezv`** (Vobiz trunk leg)
- started 16:48:15 → ended 16:48:39, **duration 24s**, outcome **voicemail**, answered:false
  (the real number rang/was dialed; founder didn't pick up — expected for a test).
- Billing ledger entry: id `8c72658fa1` · call_id `7c1364ec76` · duration_s 24 · **cost 0.0 INR**
  · at 2026-06-11T16:48:39. Cost = ₹0 because the **admin tenant is postpaid, rate_per_min=0.0,
  included_minutes=1,000,000** (internal account billed at ₹0 by config; usage IS metered —
  month-to-date now 93 calls / 98.9 min). Upstream Vobiz telephony cost exists but the panel
  bills admin at ₹0.

## (b) AI Manager "run campaign" — ARMED & correctly routed to the REAL dialer (NOT fired, cost cap)
Endpoint `/ai-manager/commands/test` (read-only NLU) on :8209. All verified live:
- "run the Codename Joy 3.0 campaign" → intent **`leads.enqueue_calls`** (the real dialer), risk_level 3,
  requires_pin, entity `campaign:"Codename Joy 3.0"`, status `needs_pin`. (cmd `tc_bfe2aaec4e60`)
- `/commands/{id}/confirm` → `status:needs_pin, requires_pin:true` (gate sequence intact).
- "call all hot leads" → `leads.enqueue_calls`, requires_pin (the prior silently-broken path, now fixed).
- "create a new campaign for Surat flats" → `campaigns.create` (DRAFT, not a dial) — create/run disambiguated.
- "show me the secret api key" → **blocked** (Security policy, risk 4, safe_to_execute:false).

### PIN gate proven (replicating the live app's firewall.init exactly — read-only, no dial)
`firewall.init(secret=caller.SECRET, pin_file=/opt/famit-agent/var/pins.json)` →
`available:True`, `has_pin(admin):True`, `check_pin(admin,4827):True`, `check_pin(admin,9999):False`.
So execute would: PIN 4827 accepted → mint step-up → `delegate.execute` → `leads.enqueue_calls`
→ `data=` FORM `POST /run` (the TCfix; was `json=args`→0 dials) → the SAME dialer proven above.

### Why the AIM dial was NOT fired (founder-protective)
A natural-language "run <campaign>" defaults to `use_stored=1` → for c17e55e9f3 that = **3 real
callable leads** (e.g. +917987388671 "colin", +916375548830), NOT the founder. Firing it would
(1) place a 2nd+ call (cap = AT MOST 1) and (2) dial real leads (forbidden). The single sanctioned
call was spent on (a) via the identical dialer. So (b) is proven ARMED end-to-end up to the dial
trigger, not fired.

## Regression — live earner intact
Services `famit-caller / famit-agent / famit-bridge` all **active**. **0** 5xx/tracebacks since the call.
agent.py (Riya, Groq/Sarvam round-robin) last started 2026-06-10 19:58 UTC — untouched, not restarted.
caller last started 16:42 UTC (prior fix wave; not restarted this session). `/health` = ok.
No edits, no restarts, no git this session.

## VERDICT
- Real call: **PLACED** — call `7c1364ec76` to founder `+917861019021`, room `famit-917861019021-c9b218`,
  SIP `SCL_HeUUdXRi4Ezv`, 24s, voicemail; ledger `8c72658fa1`, ₹0 (admin internal/₹0-rate, metered).
- AI Manager run-campaign: **ARMED & correctly routed** to the real dialer (`leads.enqueue_calls`→/run),
  PIN 4827 gate verified (accepts 4827 / rejects wrong); the dial itself NOT fired to honor the
  1-call cap + never-call-leads rule. To see the AIM brain physically dial: founder runs
  `/ai-manager` → "run the <campaign> campaign" → PIN 4827 → confirm (dials that campaign's stored
  audience), or scope a 1-lead campaign first for an exact-1-call proof.
