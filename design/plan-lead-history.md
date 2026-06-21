# Plan — Lead + Call History + Memory (inbound "continue the conversation")

_EXPLORE-2. Authored 2026-06-12 from live box `famit@168.144.153.145` (READ-ONLY) + local design docs. Evidence-grounded, file:line cited._

**Goal of this sub-problem:** when an inbound call lands, the AI must — in real time, keyed by the caller's phone number — pull that person's prior call HISTORY / transcript / where-they-left-off and CONTINUE the sales conversation ("aapne humse X ke baare mein baat ki thi, aapne kaha tha call back…"). For a NEW caller (banner/brochure number) with no history, it must disambiguate which active campaign they're calling about and run the sales script for that campaign exactly like outbound.

> ⚠️ #1 CONSTRAINT — **NEVER BREAK OUTBOUND.** `agent.py` / `memory.py` / `caller.py` are the live earner. This plan is **additive + isolated**: it READS the existing per-phone memory + leads + calls + campaigns that the outbound path already writes, and adds an inbound lookup. It must NOT change the memory schema, the `norm()` function, the room-naming, or any write that the outbound path depends on. New code lives in the inbound service (`aim_voice_agent.py`) and reuses the SAME `memory.py` / `caller.py` helpers read-only.

---

## THE 12-LINE MAP (where each thing lives today, on the live box)

1. **Lead record** → `var/leads.json` (JSON list). Per-lead: `{id, name, phone:"+916375548830", status, score, hot, last_outcome, last_call_at, tenant_id, added_at}`. Phone stored **E.164 with `+`**. (caller.py:159 `LEADS_FILE`.)
2. **Call history (every call)** → `var/calls.json` (JSON list, **116 rows live**). Per-call: `{id, name, phone:"+91…", campaign_id, campaign_name, status, outcome, answered, interest, room, sip_call_id, duration_s, started_at, ended_at, tenant_id}`. NO transcript inline; the `room` field is the join key to the transcript.
3. **Per-call transcript** → `var/transcripts/{room}.json`, keyed by **LiveKit room name** (e.g. `famit-910000000066-050387`). Holds `{room, phone, lead_name, campaign_id, turns:[], summary, outcome, interest, next_action, opt_out, callback_at, callback_raw}`. This is the per-call "where they left off" (next_action / callback_at / opt_out).
4. **⭐ Per-PERSON cross-call MEMORY** → `var/memory/{digits}.json`, keyed by **digits-only phone, no `+`** (e.g. `916375548830.json`). Holds `{phone, last_call_at, summary, history:[{role,content}…]}` — the running multi-call dialog. **THIS is the "continue the conversation" store** and it is REAL/populated (live file shows a full Riya↔Kunal Hindi dialog ending in "site visit kal 2 baje book kar do").
5. **The outbound recap mechanism (the reference)** → `agent.py:391-393`: `phone = mem.parse_phone(room_name)` → `recap = mem.build_recap(mem.load_memory(phone))` → injected at `agent.py:413` as `"=== PICHHLI BAAT (returning lead) ===" + recap` into the system prompt. **This is exactly the behaviour the founder wants** — it already works for outbound; inbound just never invokes it.
6. **memory.py module** (caps the surface): `load_memory(phone)`, `build_recap(mem)` (prefers `summary`, else stitches last 8 turns, prefixes `(pichhli call: <when>)`, ≤600 chars), `save_memory(phone, history, summary)`, `parse_phone(room_name)` (longest digit-run ≥6 out of room name). `_path_for()` strips to digits-only → so it reconciles `+91…` and `91…` to the same file.
7. **Campaign = the sales knowledge** → `var/campaigns/{id}.json` (8 campaigns, ≥6 `status="ready"`): `{id, tenant_id, name, company, product, status, system_prompt, fields:{company_name, agent_name, product_name, product_summary, location, price_offer, usps, talking_points, objections, qualifying_questions, language, voice_id, variants…}}`. This is what an inbound sales call needs to run a campaign "exactly like outbound."
8. **Phone normalizer (canonical)** → `caller.py:649 norm(n)`: strips non-digits, drops a leading `0`, prepends `91` if 10 digits, returns `"+"+digits` (E.164). This is the system's one true normalizer for leads/calls.
9. **Inbound caller-ID is ALREADY read** → `aim_voice_agent.py:398-413`: reads SIP attribute `sip.phoneNumber` (fallback `sip.from`) off the participant, then `_canon()` (line 141, `'+'+digits`). So the inbound number IS available in real time at call start.
10. **Inbound multi-form matcher ALREADY exists** → `aim_voice_agent.py:151 _match_forms(phone)`: expands a number to every digit-rep (bare-10, `+91…`, leading-`0`, strip-`91`). Built to match a `+91…` record against an inbound CLI like `06375548830`. Currently used ONLY for the AIM caller-ID allowlist — NOT to load customer memory.
11. **Inbound→lead/campaign resolver ALREADY exists** → `caller.py:1465 _resolve_contact_by_phone(phone)`: `norm()`s the number, finds the most-recent `calls.json` row → returns `{tenant_id, name, campaign_id, campaign_name}`, falls back to a `leads.json` match. Built for inbound WhatsApp; **directly reusable** to tell an inbound voice call "we last called this person about campaign X."
12. **The unified PG CRM tables exist but are EMPTY/unused by the live path** → `contacts` (`phone_key`, `phone_display`, `stage`, `last_outcome`), `contact_identity` (kind/value→contact_id), `contact_timeline` (every interaction). **0 rows** — the live earner writes the JSON files in (1)-(4), not PG. So inbound lookup must read the JSON files (or whatever the eventual store is), NOT these empty tables.

---

## THE EXACT GAP — inbound caller-history lookup

**Everything needed exists, but no wire connects inbound caller-ID → per-person memory → recap injection.** Concretely:

**GAP A — inbound never loads the memory.** `aim_voice_agent.py` reads the caller-ID (step 9) but never calls `mem.load_memory()` / `mem.build_recap()`. The whole `aim_voice_agent.py` is the *Manager* (command) brain; there is **no customer-sales inbound mode** that injects "PICHHLI BAAT". The outbound recap (`agent.py:391`) keys off `parse_phone(room_name)`, but an **inbound room is NOT named `famit-<phone>-…`** (LiveKit dispatches the inbound call into a SIP room whose name does not embed the customer's digits) — so `parse_phone(room_name)` returns "" inbound and the memory is never found even if the code path were copied. **The inbound key MUST come from the SIP caller-ID, not the room name.**

**GAP B — normalization mismatch across the three stores (the founder's `06375548830` vs `+91…` problem).** Three live key formats for the same person:
   - lead / call: `+916375548830` (E.164, via `caller.py:norm`)
   - memory file: `916375548830.json` (digits-only, no `+`, via `memory._path_for`)
   - inbound CLI (per task): `06375548830` (national, leading `0`, **no country code**)

   `norm("06375548830")` → strips `0` → 10 digits `6375548830` → prepends `91` → `+916375548830` ✅ (resolves lead/call). And `memory.load_memory("+916375548830")` → `_path_for` strips to `916375548830.json` ✅ (resolves memory). **So the chain DOES reconcile IF and ONLY IF inbound passes the raw CLI through `caller.norm()` first and then to `load_memory()`.** The gap is that nothing does this today — and a naive `load_memory(raw_cli)` (e.g. `load_memory("06375548830")`) would look for `06375548830.json` and **MISS** the `916375548830.json` file. **Fix = always `norm()` the inbound CLI before any lookup; never key memory off the raw CLI.** Edge cases still to handle: CLI arriving as bare-10 with no `0`/`+`, CLI with a different country code, CLI withheld/"anonymous" (→ treat as brand-new caller), and the historical write inconsistency where some memory files are digits-only-without-`91` — use `_match_forms()` (step 10) to try every digit-rep against the memory dir, not a single key.

**GAP C — no "returning vs new" branch + no campaign disambiguation for inbound.** When history IS found, inbound must greet-with-context and continue the **specific** campaign's script (load `var/campaigns/{campaign_id}.json` via the `campaign_id` from `_resolve_contact_by_phone`). When history is NOT found (banner/brochure caller), inbound has no signal for which of the ≥6 active campaigns they want — **campaigns carry NO inbound-DID field today**, so campaign-by-DID inference is impossible until a `did`/`inbound_number` field is added to the campaign record (or a DID→campaign map file is introduced). Until then the only path is to **ASK** ("aap kis project ke baare mein jaan-na chahte hain?") and match the answer to a campaign name/product, then run that campaign's `system_prompt` exactly like outbound.

**GAP D — recap is read-only one-way; inbound calls must also WRITE back.** The outbound path saves memory on shutdown (`agent.py:423 _persist_memory → mem.save_memory(phone, turns)`). An inbound sales call that continues the conversation must **append** its turns to the SAME `memory/{digits}.json` so the next call (in or out) sees this call too. Because `save_memory` overwrites with the **last 16 turns**, inbound must merge prior history + this call's turns before saving, or successive calls will truncate the thread. (Outbound has the same 16-turn cap but is acceptable today; for true multi-call continuity, raise the cap or keep a rolling summary — noted as a follow-up, not a regression risk.)

---

## MINIMUM ADDITIVE FIX (isolated, outbound untouched) — for the architecture wave

A new inbound **customer-sales** entrypoint (separate from the Manager brain) that, on join:
1. `cli = read SIP sip.phoneNumber` → `key = caller.norm(cli)` (reuse, don't reinvent).
2. `ctx = caller._resolve_contact_by_phone(cli)` → `{tenant_id, name, campaign_id, campaign_name}` (reuse).
3. `recap = mem.build_recap(mem.load_memory(key))`; if empty, retry across `_match_forms(cli)` digit-reps.
4. **Returning** (recap or campaign_id found) → load `campaigns/{campaign_id}.json`, build the SAME system prompt the outbound agent builds, inject `"=== PICHHLI BAAT ===" + recap` + lead name → continue.
5. **New** (nothing found) → greet generically, ASK which campaign/product, match answer → load that campaign → run sales script.
6. On hangup → merge-and-`save_memory(key, prior+turns)` so the thread grows (GAP D).

This reuses `memory.py`, `caller.norm`, `caller._resolve_contact_by_phone`, `campaigns/*.json`, and `agent.py`'s prompt-build pattern **without editing any of them**. The only NEW persistent need is GAP C's campaign-DID map (add a `did` field to campaign records OR a small `var/did_campaign_map.json`) so multi-campaign banners can route by number instead of always asking.
