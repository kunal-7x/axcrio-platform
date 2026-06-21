# EXPLORE-3 — Campaign Context + Inbound Disambiguation (READ-ONLY plan)

_Authored 2026-06-12 from live box famit@168.144.153.145 (read-only) + local design docs. Evidence-grounded, file:line cited._

> **#1 CONSTRAINT — NEVER BREAK OUTBOUND.** The outbound earner (`agent.py`, `agent_name="capsy"`, `famit-agent.service`, :8090) and its trunks/dispatch are byte-frozen here. Everything below is **additive + isolated**: a NEW inbound sales worker (`agent_name="sales-in"`, its own port/unit) and **read-only reuse** of caller.py's existing campaign/lead/call/transcript stores and prompt.py's `build_system_prompt`. No edits to the outbound dial path, no shared-infra changes that touch it.

---

## SCOPE OF THIS DOC
Two questions for **CUSTOMER inbound** (mode A): (1) how does an OUTBOUND call get its campaign context today, and (2) for a NEW inbound caller, how do we (a) **detect which campaign** and (b) **load that context** so the inbound sales convo runs exactly like outbound. (Mode B, the MANAGER inbound brain, is `aim_voice_agent.py` + `design/inbound-gap-analysis.md` — out of scope here except where it shares the DID-routing seam.)

---

## 12-LINE MAP — how OUTBOUND gets campaign context (the reference to mirror)

1. **Campaign record** = a JSON file `var/campaigns/{cid}.json`, written by `caller.py:1153 save_campaign(fields, tenant_id)`. Shape: `{id, tenant_id, name, company, product, status:"ready", created_at, fields{…}, system_prompt}`.
2. **`fields{}`** is the brain payload (`prompt.py` keys): `company_name, agent_name, product_name, product_summary, location, price_offer, qualifying_questions[], objections[], negotiation_ladder[], objection_bank[], primary_language, voice_id, disclose_ai, landmark`. This is the entire persona + sales knowledge.
3. **Prompt render** = `prompt.py:254 build_system_prompt(fields)` → the full ~6k-char Hinglish sales system prompt (flow, objection bank, negotiation ladder, gender-correct body, TRAI AI-disclosure). One function, deterministic, pure.
4. **Run trigger** = `caller.py:3072 /run` (campaign_id + leads) → `caller.py:1971 run_job()` loops the lead queue.
5. **Per-lead room** = `room = f"famit-{num[1:]}-{uuid6}"` (`caller.py:2042`). The lead's **phone is encoded in the room name** (load-bearing — see #9).
6. **Dispatch metadata** = `md_obj = {"campaign_id": cid, "lead_name": name [, variant_id, fields_override]}` → `json.dumps` → `create_dispatch(room, agent_name="capsy", metadata=md)` (`caller.py:2044-2058`). **This is the ONLY channel that carries campaign identity into the voice job.**
7. **SIP leg** = `create_sip_participant(trunk, sip_call_to=num, room, …)` dials the lead into that room (`caller.py:2059`). Then a `call` record is written: `{id, tenant_id, name, phone, campaign_id, campaign_name, status, room, sip_call_id, …}` (`caller.py:2069 record_call`).
8. **Agent reads metadata** = `agent.py:346 entrypoint` → `ctx.job.metadata` → `json.loads` → `meta{campaign_id, lead_name, …}` (`agent.py:351-358`).
9. **Context load** = `agent.py:361 _load_campaign(meta["campaign_id"])` reads `var/campaigns/{cid}.json` → `system_prompt = build_system_prompt(fields)` (re-rendered fresh at call time, not the baked copy) (`agent.py:142, 361-372`).
10. **Cross-call memory** = `memory.py:34 parse_phone(room_name)` pulls the longest 6+ digit run from the room → `load_memory(phone)` → `build_recap()` returns the **prior call's summary + last turns** (`agent.py:391-395`). Keyed by **phone**, not room → survives across calls. Saved at hangup via `save_memory(phone, history, summary)` after `_summarize()` (`agent.py:461-477`, `caller.py:155 _summarize`).
11. **Instructions assembly** = `base = system_prompt + (lead_name greet line) + ("=== PICHHLI BAAT ===" recap if returning)` (`agent.py:380-389`). The opener greets by name and references the prior conversation.
12. **A/B + language** = optional `fields_override`/`variant_id` merge over fields then re-render (`agent.py:374-388`); default TTS language from `_campaign_default_lang(fields)` (`agent.py:404`), then mirror per-turn. Net: **campaign identity travels ONLY via dispatch metadata; phone-keyed memory + the campaign JSON do the rest.**

---

## WHAT EXISTS vs WHAT IS MISSING (the gap)

### EXISTS (reusable read-only — strong foundation)
- **Campaign store + render** — `get_campaign(cid)` / `list_campaigns(tenant)` / `build_system_prompt(fields)` are pure read/render. An inbound sales worker can call the SAME `_load_campaign` + `build_system_prompt` → **identical brain to outbound, zero divergence.**
- **Phone-keyed cross-call memory** — `memory.py` `parse_phone`/`load_memory`/`build_recap` already give "you spoke with us about X, you said call back…" **for free** — IF the inbound room name embeds the caller's phone digits (we control the inbound room name, so we make it `famit-{caller_digits}-{uuid6}`, mirroring outbound → recap recovers automatically).
- **Inbound→tenant/campaign linker** — `caller.py:1466 _link_inbound(phone)` ALREADY exists (built for WhatsApp): scans `CALLS` for the most-recent call to this number → returns `{tenant_id, name, campaign_id, campaign_name}`, falling back to a stored lead, then to `ADMIN_ID`. **This is exactly the "returning lead → which campaign" resolver** and it's live + tenant-safe.
- **Caller-ID extraction** — `aim_voice_agent.py:397-413` reads `sip.phoneNumber`/`sip.from` off the SIP participant attributes and canonicalizes it. The inbound sales worker reuses this pattern verbatim.
- **Per-call transcript persistence** — `TRANSCRIPT_DIR/{room}.json` + the `_summarize` → call-record outcome/interest pipeline already capture history for the panel and for the next recap.

### MISSING (the build — all additive, all isolated from outbound)
- **G1 — No inbound SALES worker.** `aim_voice_agent.py` is MANAGER-only (no campaign loading, no `build_system_prompt`; it drives the PIN/command state machine). **Mode A needs a NEW worker** (`agent_name="sales-in"`, own systemd unit + port) that, on inbound, runs the *outbound* `AgentSession` pipeline (copy `agent.py`'s session kwargs for the latency moat) with a **campaign system prompt** instead of the command machine. (Don't bolt sales onto the manager worker — different brain, different gating.)
- **G2 — No DID→campaign mapping table.** The only inbound DID concept is the single hardcoded AI-Manager DID → `agent_name="manager"`. There is **no record that says "banner number +91XXXX = campaign cid".** Need a tiny additive store `var/inbound_dids.json` (or PG `inbound_dids`): `{did, tenant_id, campaign_id, agent_name, lang, label}`. A campaign-specific banner number resolves campaign with **zero asking** (the strongest UX). The dispatch rule routes each DID's room to `agent_name="sales-in"` and stamps the DID into room metadata.
- **G3 — No "active campaigns" list for disambiguation.** `list_campaigns` returns ALL `status:"ready"` campaigns; there is **no notion of "currently active / running" per tenant** to offer a NEW caller a short menu ("are you calling about Godrej Park or Lodha Estate?"). Need an `active` flag (or derive "active" = campaigns with a running/recent `/run` job, or an explicit toggle) so the disambiguation menu is short and correct, not a dump of every campaign ever created.
- **G4 — No inbound disambiguation flow.** For a NEW caller on a SHARED/unknown DID, nothing asks "which campaign/property?". Need a deterministic mini state-machine: greet → if `_link_inbound` hits a prior campaign, **confirm-or-switch** ("you spoke with us about X — still about that?"); else read active campaigns → ask → NLU-match the spoken product name to a `cid` (reuse the Mode-B `intent/driver` closed-enum matcher, enum = active campaign names) → on match load that campaign; on miss re-ask once then fall back to a generic "let me take your details" capture.
- **G5 — Inbound room-name convention not set.** Outbound encodes phone in the room name so memory works; inbound rooms are created by the SIP dispatch rule. Must pin the inbound room name to `famit-{caller_digits}-{uuid6}` (or pass caller phone explicitly in metadata) so `memory.parse_phone` + `_link_inbound` both resolve the returning lead. **Without this, the "continue the prior conversation" promise silently fails.**
- **G6 — No inbound concurrency / tenant gate / suppression-on-inbound.** Outbound has `ACTIVE_CALLS` caps, DND suppression, wallet holds. Inbound sales calls also cost vendor money (STT/LLM/TTS) and must be tenant-attributed + metered + wallet-gated, but inbound has **no equivalent gate**. Additive: attribute the inbound call to the resolved `tenant_id` (from DID or `_link_inbound`), apply the same wallet/entitlement check before answering, and record the call exactly like outbound (so it appears in the panel + feeds the next recap).

---

## RECOMMENDED RESOLUTION ORDER (for the inbound campaign-context piece)

1. **DID-first (best, zero-ask):** banner/brochure prints a **campaign-specific DID** → `inbound_dids.json` maps DID→`{tenant_id, campaign_id}` → dispatch routes to `sales-in` with that `campaign_id` in metadata → worker loads it via the existing `_load_campaign` + `build_system_prompt`. Runs **exactly like outbound**, no menu.
2. **Returning-lead (recover context):** caller-ID hits `_link_inbound` → prior `campaign_id` → load it; room name carries phone digits → `memory.build_recap` supplies "you spoke with us about X, you said call back…". Confirm-or-switch before diving in.
3. **Shared DID, new caller (ask):** read the tenant's **active** campaigns (G3) → offer a 1–3 item spoken menu → NLU-match (G4) → load. Cap the menu; if >N active, ask "are you calling about a property, a loan, or something else?" first to bucket.
4. **Fallback:** no match → capture name + interest as a fresh lead (tenant from DID), promise a callback, log it. Never dead-air; never the wrong script.

**Net dependency:** the campaign **brain** is 100% reusable read-only (`_load_campaign` + `build_system_prompt` + `memory` + `_link_inbound` all exist). The gap is purely the **inbound front-door**: a new isolated sales worker (G1), a DID→campaign map (G2), an active-campaign notion (G3), a disambiguation flow (G4), the room-name/phone convention (G5), and the inbound tenant/wallet/record gate (G6) — all additive, none touching the frozen outbound path.

---

## EVIDENCE INDEX (file:line, live box)
- `agent.py:142` `_load_campaign`; `:254`→ wrong, `prompt.py:254` `build_system_prompt`; `agent.py:346-395` entrypoint metadata→prompt→recap; `:404` default lang; `:461-477` transcript+memory save.
- `caller.py:1153` `save_campaign`; `:1173` `get_campaign`; `:1188` `list_campaigns`; `:1466` `_link_inbound`; `:1971` `run_job`; `:2042` room name; `:2044-2069` dispatch metadata + sip + record_call; `:3072` `/run`; `:155` `_summarize`.
- `memory.py:34` `parse_phone`; `:53` `load_memory`; `:67` `build_recap`; `:96` `save_memory`.
- `aim_voice_agent.py:397-413` caller-ID off `sip.phoneNumber`; `:712` `agent_name="manager"` dispatch routing (the DID-routing seam to extend for `sales-in`).
- No matches anywhere for an inbound DID→campaign table or an "active campaign" flag → confirmed MISSING (G2/G3).
