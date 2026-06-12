# BUILD #4 — AI Manager conversational SLOT-FILLING (multi-turn ELICIT)

BOX famit@168.144.153.145 key do-blr-test/id_ed25519 ; venv /opt/capsy-agent/.venv ; PIN 4827 ; founder campaign c17e55e9f3
Chat path: POST /ai-manager/commands/test -> /commands/{id}/confirm|execute (port 8209 famit-caller)
Voice path: aim_voice_agent.py -> CommandMachine.run() (aim-voice-agent svc)

## BASELINE (before)
- agent.py md5 = 9150fabe4ff62b4b4470f9a87df346e5  (MUST be unchanged after)
- famit-agent active, famit-caller active, aim-voice-agent active
- core /health (8209) = 200 ; 5xx in caller log = 0
- EARNER regression: outbound call +917861019021 must RING  [run FIRST + LAST]

## THE GAP (confirmed in code)
- driver.py _map_to_intentmatch: when LLM emits missing_fields -> converts to {kind:clarify, intent:""} (LOSSY: drops intent+slots). lines ~508-515.
- state_machine.py command loop (201-325): kind=="clarify" branch (212-215) = dead-end "rephrase", discards intent.
- endpoints.py _aim_parse_card (303): kind=="clarify" (340) = dead-end "rephrase". No PendingCommand across HTTP turns.
- ToolSpec has no required_slots; nothing maps missing slot -> a question.

## DESIGN (additive; safety spine UNTOUCHED)
1. ToolSpec.required_slots (tools/__init__.py) + per-tool required_slots in catalog.py.
   - leads.enqueue_calls: [campaign, segment]  (segment enum hot|warm|all|cold|specific)
   - campaigns.create: [objective]
   - ads.set_budget: [budget_minor]  (+ campaign)
   - whatsapp.send: [segment]
   - workflow.activate/run_now: [workflow_id]   booking.create: [slot_start]
2. driver.py: add CLARIFY-WITH-INTENT. New helper required_slots_for(intent) reads the live registry.
   _map_to_intentmatch: when COMMAND intent present but missing required slots -> emit
   {kind:"command", intent, slots, missing_fields:[...], _summary} INSTEAD of lossy clarify.
   parse_intent merges a slot-extraction-only mode for ELICIT replies (parse_slot_value).
   Offline stub: fill missing_fields from required_slots table.
3. slot->question map (slot_question) + slot->validator/normalizer (coerce_slot) in driver.py.
4. state_machine.py NEW S4.5 ELICIT: after parse, before S5. Hold PendingCommand{intent,slots,outstanding}.
   While outstanding: ask slot_question(next), _hear, merge via parse_slot_value, re-check. MAX_CLARIFY=3.
   Then flows UNCHANGED into S5 permission -> S6 step-up -> S7 confirm -> S8 execute.
   clarify branch: only TRUE no-intent clarify rephrase; missing-slot now routes to ELICIT.
5. endpoints.py chat: _aim_parse_card returns status "eliciting" + prompt + command_id when missing slots;
   NEW route POST /commands/{id}/slot (or reuse /test with pending_id) merges the reply, re-checks,
   loops; when complete -> normal needs_confirmation/needs_pin card. _TEST_CMDS holds the PendingCommand.

## PROGRESS — ALL DONE
- [x] baseline regression (earner rings) — job 014b6f1bce, Riya opener spoke
- [x] ToolSpec.required_slots + catalog required_slots
- [x] driver.py clarify-with-intent + slot_question + coerce_slot + parse_slot_value + article-guard
- [x] state_machine.py S4.5 ELICIT (voice path inherits via CommandMachine)
- [x] endpoints.py chat ELICIT loop (POST /commands/{id}/slot + _finalize_command_card)
- [x] py_compile all (local + venv)
- [x] restart famit-caller + aim-voice-agent (NOT famit-agent)
- [x] SMOKE chat path: run a campaign->Which campaign?->Codename Joy->Which leads?->hot->needs_pin readback; read "how many leads in Codename Joy"=5
- [x] regression AFTER: earner rings (job 5df287309a) + md5 9150fabe...UNCHANGED + health 200 + 0 5xx post-restart
- [x] commit + append MASTER_BUILD_STATE.md
MID-BUILD BUG (fixed): _finalize_command_card used _identity (imported only inside _aim_parse_card)
 -> NameError 500 on /slot completion -> added `from . import identity as _identity` inside the helper.
