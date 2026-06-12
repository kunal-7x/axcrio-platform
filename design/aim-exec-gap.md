# AIM Voice — Execution Gap (run_campaign says "dialing" but nothing dials)

DIAGNOSE-2. Box famit@168.144.153.145, /opt/famit-agent. Evidence from
`journalctl -u aim-voice-agent` (founder's real calls, 2026-06-12).

## ROOT CAUSE (12 lines)
1. The data + dial path is FINE: admin X-Auth sees all 8 campaigns (Codename Joy 3.0 = `c17e55e9f3`),
   5 leads (all score>=80 = hot), window 00:00-23:59 => in-window. `/run` with `lead_ids` DOES create a
   job and `run_job` DOES dispatch SIP. So the audience/segment/window are NOT the blocker.
2. THE BLOCKER is the LLM tool call NEVER EXECUTES. `aim_voice_agent.py:377` types the action params
   strictly: `count: int, confirmed: bool`. The realtime LLM emits them as STRINGS (`confirmed="true"`,
   `count="5"`).
3. The OpenAI/LiveKit inference layer HARD-REJECTS the tool call against its JSON schema:
   `tool call validation failed: parameters for tool run_campaign did not match schema:
    [/confirmed: expected boolean, but got string, /count: expected integer, but got string]`.
4. This raises `APIError -> APIConnectionError` INSIDE `_llm_inference_task`. The `run_campaign` body
   (and its `AIM run_campaign CONFIRMED` log) NEVER runs => NO job, NO `/run` POST, NO SIP dial.
5. Count over 3 days: **`run_campaign CONFIRMED` = 0 times**; **schema-mismatch rejections = 28** (24+4).
   Every single "run it / yes" the founder gave was silently dropped at the validator.
6. Meanwhile the agent had already SPOKEN "I'm dialing" (narration precedes the failed tool call), so the
   founder hears "dialing" but the phone never rings. Exactly the reported symptom.
7. SAME class of bug breaks reads: `check_leads(campaign: str)` is REQUIRED-typed. When the founder asks
   "how many campaigns/leads" WITHOUT naming one, the model omits `campaign` and the call is rejected:
   `check_leads did not match schema: [missing properties: 'campaign']` (16 rejections). The agent then
   has no tool result and HALLUCINATES — the founder's "can't find my campaigns / wrong info" complaint.
8. "all corporates"/"hot"/arbitrary words are NOT the cause: `run_campaign` maps unknown segment->"all"
   and resolve_audience("all") returns all 5 leads. The audience would have resolved fine IF the tool ran.
9. Net: the gate is purely the strict typed/required tool schema vs. a realtime LLM that emits stringy,
   sometimes-partial args. Strict validation = fail-CLOSED on the action that matters most.
10. (Secondary, latent) `force=1` is sent to `/run` but `run_job` re-checks `_in_window` itself and is
    NOT passed force; a campaign with a narrow window would park at sleep(60). Codename Joy is 24h so not
    hit now, but it WILL bite other campaigns — fix alongside.
11. (Secondary) voice tool authenticates as `admin` (FamitCall2026), so it acts on the admin lead pool,
    not a per-founder tenant. Works today because the founder's data lives under admin; note for later.
12. No 5xx, no SIP errors in the dial path itself — the failure is 100% upstream at tool-arg validation.

## THE FIX (so run actually dials, reliably, for arbitrary words)
Edit ONLY `aim_voice_agent.py` (+ `ai_manager/voice_tools.py`). Make every @function_tool arg
LLM-tolerant (loose types + server-side coercion) so the validator can't reject a valid call:

A. `run_campaign(...)` signature -> accept strings, coerce in-body:
   - `count: int` -> `count: str = "0"`  then `n = _to_int(count, 0)`.
   - `confirmed: bool` -> `confirmed: str = "false"` then
     `is_confirmed = str(confirmed).strip().lower() in ("true","1","yes","y","ok","confirm","confirmed")`.
   - `segment: str = "all"`, `campaign: str = ""` (defaulted, never required).
   Behaviour unchanged downstream; only the wire types loosen. This alone makes the founder's
   "run it, yes" actually fire the CONFIRMED branch -> `_vt.run_campaign` -> POST /run -> SIP dial.

B. `check_leads(campaign: str)` -> `campaign: str = ""` (optional). It already treats "" as the whole
   tenant pool, so "how many leads/campaigns" with no name now SUCCEEDS instead of being rejected.
   Audit every other tool the same way: no required non-string params; default everything.

C. Belt-and-braces on the LLM: in `_build_instructions`, add an explicit rule —
   "When calling any tool, pass arguments as the asked types but it is SAFE to pass numbers/booleans as
    plain strings (e.g. confirmed=\"true\", count=\"5\"); always include every argument."
   And keep the readback->confirm flow.

D. Make execution observable + honest: log the raw tool args on entry to `run_campaign`, log the `/run`
   HTTP status + job_id (already partly there), and have the tool RETURN the real result string only
   AFTER /run responds 200/202 with a job_id — never let the model say "dialing" before the tool returns.
   (Instruction: "Do not tell the caller you are dialing until run_campaign returns a job id.")

E. Secondary hardening (optional, same isolation): pass `force` through to run_job OR have voice_tools
   only call /run when in-window; and plan a per-founder tenant credential instead of admin X-Auth.

## VERIFY AFTER FIX
- Repro: call run_campaign tool path with confirmed="true", count="0", segment="corporates" for
  c17e55e9f3 -> expect `AIM run_campaign CONFIRMED` log + `run.dispatch` audit + livekit
  "Creating SIP participant" + founder phone +917861019021 RINGS.
- Grep journal: `run_campaign CONFIRMED` > 0 and ZERO `did not match schema`.
- REGRESSION GATE (unchanged): agent.py md5 = 9150fabe4ff62b4b4470f9a87df346e5, famit-agent active,
  a real outbound call still rings, zero 5xx. Restart ONLY aim-voice-agent.
