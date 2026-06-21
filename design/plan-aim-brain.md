# PLAN — AI Manager BRAIN (conversational command execution)

> READ-ONLY exploration (EXPLORE-4). Maps the AI Manager command brain as BUILT on the box
> `famit@168.144.153.145` (`/opt/famit-agent/ai_manager/`, `/opt/famit-agent/workforce/`) and the gap
> for a natural "run a campaign by phone, asking me what I want" flow. No code, no deploy, no git.
> #1 constraint stands: the AI Manager is a co-located DEDICATED service that calls the monolith `/api`
> over the network — it touches NOTHING on the outbound `agent.py` path; this plan is purely additive.

---

## 12-LINE MAP (the brain, as actually built)

1. **Entry / spine** = `ai_manager/state_machine.py` `CommandMachine.run()` — a 10-state machine
   `S0 CONNECT→S1 VERIFY→S2 AUTH(PIN/OTP)→S3 CONTEXT→S4 CAPTURE INTENT→S5 PERMISSION→S6 STEP-UP→S7 CONFIRM
   →S8 DELEGATE+EXECUTE→S9 REPORT`. Channel-agnostic: drives an injected `transport` (speak/listen/
   collect_secret) — voice + chat + scripted-test are thin wrappers over the SAME machine (`:138`).
2. **NLU** = `ai_manager/intent/driver.py` `parse_intent(utterance, ctx)` → `IntentMatch`
   `{kind∈[query|command|clarify|goodbye], intent∈CLOSED_ENUM, slots:{}, confidence, reason}`. Groq
   JSON-mode when keyed; deterministic keyword/regex matcher offline; off-enum / low-conf / error → `clarify`,
   never guesses (`:141 _coerce`, `:186 offline matcher`).
3. **Slot extraction** is single-shot inside `parse_intent`: regex pulls `budget_minor`, `campaign`,
   `channel`, `count`, `segment`, `objective` from ONE utterance into `slots` (`:254`, `:283`, `:307`).
4. **Command catalog** = `workforce/tools/catalog.py` — `ToolSpec(name, desc, scopes, fn, side_effecting,
   money, risk_class, schema)` registered into a `ToolRegistry`. ~28 tools: reads (`leads.read`,
   `analytics.read`, `wallet.read`, `billing.read`, `booking.read`, `brain.retrieve`), writes
   (`contacts.write`, `suppression.add`), outreach (`whatsapp.send`, `leads.enqueue_calls`), spend
   (`ads.set_budget`, `ads.pause`, `ads.create_campaign`), campaigns/workflows/bookings/creatives (PARKED
   behind `FEATURE_MEDIA`).
5. **Intent→action map** = `ai_manager/delegate.py` `map_intent_to_action(match)` →
   `{tool, args=slots, risk, scope}` where `risk`/`scope` are the DETERMINISTIC `identity.classify_risk` /
   `stepup_scope` — the model's risk label is discarded (`:67`).
6. **Permission (S5)** = `identity.permits(role, grants, tool)` — role-family + per-user grant, default-DENY;
   a deny persists `status="denied"` + audit + speaks "you're not permitted" and `continue`s the loop (`:225`).
7. **Risk gate (S6)** = `identity.is_risky(tool)` → if risky, `_step_up()` mints a FRESH, scoped, 300 s
   step-up via `firewall_bridge` AFTER a per-action PIN (`:373`); PIN audio suppressed via `recorder.pause()`,
   digits stored `"****"`, never persisted.
8. **Confirm (S7)** = `_confirm_text(action)` read-back + `_hear()` + `_is_yes()`; "no" → `status="cancelled"`,
   `continue` (`:271`).
9. **Execute (S8)** = `delegate.execute()` → `workforce/runner.py` (`run_agent`) which RE-ENFORCES caps /
   idempotency / kill-switch independently (defense in depth); only a runner `"done"` counts as executed.
10. **Persistence** = `ai_manager/store.py` over PG `ai_manager_*` (FORCE-RLS): `commands`, `action_runs`,
    `sessions`, `authorized_users`, `profiles`, `audit_logs`; `(vendor_id, idempotency_key)` UNIQUE makes a
    retried turn resolve to the same row (no double-execute). All store calls best-effort (PG-down still runs).
11. **The loop** = `while True:` at `state_machine.py:201`: hear → `parse_intent` → branch by `kind`. After a
    command completes (or cancels/denies), it loops back to "What else?" — so it IS multi-COMMAND across turns.
12. **PIN/risk gating is solid and deterministic** (Argon2id designed in `aim-nlu-policy-security.md §4`,
    salted-sha256 today in `firewall.py`); the always-block list (secrets/compliance-bypass/account-delete)
    and the L0–L4 risk table are the authoritative spine. **Reads are answered inline** (`kind="query"` →
    `_answer_query`) with no gate.

---

## THE GAP — conversational slot-filling (the core of the founder's vision)

**Verdict: the brain understands ONE complete utterance and executes it; it CANNOT hold a half-specified
command and ASK for the missing pieces over multiple turns.** It expects everything in one breath.

### What's missing (precisely)
- **No `missing_fields` in the BUILT code.** The design doc `aim-nlu-policy-security.md §1.2` *specifies* a
  `missing_fields[]` + `assumptions[]` + `user_facing_summary` NLU schema — but the actual `parse_intent`
  driver never emits `missing_fields`, and the state machine never reads it. `map_intent_to_action` passes
  whatever `slots` arrived, even if empty/partial. Design says one thing; code does the single-shot thing.
- **`clarify` is a dead-end, not a slot question.** `state_machine.py:212` handles `kind=="clarify"` with a
  GENERIC `"I didn't quite get that — could you rephrase?"` and `continue` — it **discards the partial slots
  and the detected intent**. So "run a campaign" (no campaign named, no segment, no count) is treated as
  unintelligible noise, not as "I know you want to run a campaign — which one?".
- **No partial-command / dialogue state.** The `while True` loop has NO carried `pending_command` object
  across turns. Each `parse_intent` is stateless w.r.t. the previous turn's intent+slots. There is no
  accumulator that says "intent=campaign.run, have segment=hot, STILL NEED count + which-campaign".
- **No required-slot metadata to DRIVE the questions.** `ToolSpec` has an advisory `schema` (JSON-schema for
  args) but no enforced `required_slots`, and nothing maps a missing required slot → a natural question
  ("Which leads — hot, warm, or all?"). `resolve_campaign` ambiguity (design §3.4) is also unbuilt — an
  ambiguous campaign_ref today just rides through as a raw string slot.
- **Reads aren't conversational either.** `kind="query"` answers immediately; it can't ask "for which
  campaign?" before reading.

### What this blocks (the founder's two flows)
- **MANAGER INBOUND** — "I want to run a campaign" → today: clarify→"rephrase"→stall. NEEDED: detect
  `campaign.run`, then ASK in sequence — *new or existing? which campaign? which leads (hot/warm/all)? how
  many?* — accumulate slots, read-back, PIN, execute.
- **CUSTOMER INBOUND** (separate `aim_voice_agent.py` sales path, not this command machine) similarly needs
  disambiguation ("which campaign/property?") — same slot-filling primitive.

### The fix shape (one additive wave, no outbound-path touch)
1. **NLU emits `missing_fields[]` + `assumptions[]`** (already in the schema spec §1.2 — wire it in
   `intent/driver.py`; offline matcher fills it from a required-slot table).
2. **`ToolSpec.required_slots`** (declarative): e.g. `campaign.run → [campaign_ref, lead_segment, count]`;
   `ads.set_budget → [campaign_ref, amount_minor]`. Plus a **slot→question** map ("lead_segment" → "Which
   leads — hot, warm, or all?") and a **slot→validator** (count is int, amount is paise, segment ∈ enum).
3. **A `PendingCommand` dialogue state** carried across the `while True` loop: holds `intent`, accumulated
   `slots`, and `outstanding = required − filled`. New state **S4.5 ELICIT** between CAPTURE and PERMISSION:
   while `outstanding` non-empty → ask the next slot's question, merge the answer (re-parse JUST that slot,
   not the whole command), re-check; bounded by `MAX_CLARIFY` (e.g. 3) → then graceful give-up. Confidence
   `< CONF_MIN` → also routes here, not to "rephrase".
4. **Deterministic resolvers** (`resolve_campaign` §3.4): `ambiguous` → ask "Urban Nest ya Satellite?";
   `not_found` → ask/offer-create — both are ELICIT questions, NOT blocks.
5. **Unchanged downstream:** once `outstanding` is empty the command flows into the EXISTING
   S5→S6→S7→S8 spine (permission, PIN, confirm, execute) — all the safety machinery is already built and
   correct; we are only adding the *gather-missing-slots* front half.

**Net:** the safety spine, catalog, PIN/risk gating, audit, RLS, and multi-COMMAND looping are DONE and
sound. The single missing capability is **multi-TURN slot-filling** (carry a partial command, ask targeted
clarifying questions, accumulate, then execute) — it is purely additive to `intent/driver.py` +
`state_machine.py` (new S4.5) + `ToolSpec.required_slots`, and never touches the monolith outbound path.
