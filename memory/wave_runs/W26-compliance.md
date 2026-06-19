# W26 — Consent & Regulatory Engine (wave run log)

DOC-ONLY. No code, no box, agent.py untouched. Date 2026-06-18.
Deliverable: `design/W26-COMPLIANCE-CONSENT-ENGINE.md`.
Consumes: `design/W26-INDIA-AI-VOICE-DISCLOSURE-LAW.md` (legally-precise spine) +
`design/INDIA-TELECOM-AI-DISCLOSURE-LAW.md` (conservative checklist).
Feeds: W2 (disclosure-line + block-list), W12 (number/identity), W7/W9/W14 (DPDP), W17 (eval).

## Phase: DESIGN

Designed the Consent & Regulatory Engine = a server-side **dial-time preflight gate**
(`compliance.py`, in-process, fail-closed on Tier A), NOT a microservice. Rides EXISTING
live primitives instead of rebuilding: `_in_window` (caller.py:862, in run_job), the
suppression/DND store (`_suppressed_set` caller.py:1526), wallet ACID hold/charge, firewall
PIN step-up, immutable audit (JSONL + PG events mirror), and the FORCE-RLS admin-GUC DDL
pattern (db/ddl_wallet.sql / db/rls.sql).

### Engine
- 4 new FORCE-RLS tables (admin-GUC, mirrors ddl_wallet): `consent_ledger` (append-only,
  per-type/per-channel, expiry: explicit-txn +7d / inferred=contract; revocable), `dlt_registry`
  (PE/header/template/CLI-series/autodialer-notify + sender_of_record), `dnd_cache` (NCPR scrub,
  number-hash only, <=30d freshness), `compliance_audit` (append-only decision log, >=6mo).
- ONE call point: `compliance.preflight(tenant, lead, campaign)` in run_job BEFORE
  create_sip_participant (caller.py:2951) -> Decision{allow|block|soft, reasons, disclosure_ctx}.
  Gates A1 registration, A2 number-series (140/1600, reject 10-digit mobile), A3 NCPR+local DND
  scrub, A4 calling-window (legal floor 10:00-19:00, BFSI 08:00, recipient-local), A5 consent
  freshness at DIAL time. Tier B = recording-notice + retention/erasure.
- Flag-gated `COMPLIANCE_ENABLED` default OFF (enabling pre-DLT-registration would block ALL
  dials); when OFF preflight=allow + audit marker, resting build byte-identical. Fail-closed on
  Tier A, fail-soft on Tier B. <15ms budget (PK/indexed reads + in-proc cache).

### Obligations ranked
- TIER A NOW-MANDATORY (hard-block): DLT PE+header+template, 140/1600 number-series, NCPR scrub,
  10:00-19:00 window, autodialer pre-notify, use-and-purpose disclosure, 2x fresh consent.
- TIER B build-now (DPDP, ramps ~May-2027): recording consent, retention TTL, cascading
  right-to-erasure (recording+transcript+vector+lead-memory+WhatsApp), at-rest enc, >=6mo audit.
- TIER C track-only (DON'T gate): MeitY AI Guidelines (advisory), SGI/deepfake rules
  (intermediary-scoped, not a live call), TRAI AI-self-ID mandate (PROPOSED). Build Tier-2 flip only.

### LIVE GAPS FOUND (ground truth)
- Calling-window default 09:00-21:00 IST is ILLEGAL (legal = 10:00-19:00) — first dial-path fix.
- DND = tenant-local opt-out only; NO national NCPR scrub exists.
- The brain ALREADY has a disclosure knob (prompt.py:358 disclose_ai/ai_disclosure;
  agent.py:218 _llm_opener) but its DEFAULT phrase is `"{company} की एक AI assistant"` = the
  founder's BANNED wording, AND it's a SOFT prompt instruction not control-flow. W2 fixes default
  + enforcement; does NOT build the mechanism from scratch.

### Disclosure-line reconciliation (the product feature / W2 spec)
3 config-driven tiers, per-tenant/jurisdiction, env-gated, default-safe:
- Tier 0 (DEFAULT, founder-aligned, in-force-compliant): brand+purpose+record cue, NO banned phrase.
- Tier 1 (toggle, regulated verticals): "<Brand>'s digital assistant" safe-harbour cue.
- Tier 2 (DORMANT flip): explicit automated-voice line, enable when TRAI mandate lands (config not code).
Brain rules: opener emitted FIRST as control-flow; disclosure_ctx from preflight (no hardcoded
string); hard block-list ("I am an AI assistant / bot / virtual assistant / main ek AI hoon");
truthful-if-asked-human (warm + value-forward, never claim human); remove the AI-assistant default.

RECOMMENDED DEFAULT (Tier 0, Hinglish): "Namaste! Main Riya, {Brand} ki taraf se — aapne jo
{product} mein interest dikhaya tha usi ke baare mein baat karni thi. Ye call record ho sakti hai.
Bas do minute?"  EN: "Hi, this is Riya from {Brand} — I'm reaching out about the {product} you
looked at. Quick heads-up, this call may be recorded. Got a quick minute?"

(Sister doc INDIA-TELECOM-AI-DISCLOSURE-LAW.md bakes "AI/automated" into its DEFAULT; per the
legally-precise W26-INDIA-AI-VOICE doc that explicit-AI wording is NOT in-force-required, so we
make it Tier 2 dormant-available rather than default — conservative safety as a one-flip toggle.)

### Open (founder/counsel — recorded, not blocking)
Sender-of-record (Famit PE vs per-tenant PE; recommend per-tenant for liability isolation);
counsel sign-off on exact suspension clause ("15-day" UNVERIFIED); abandoned-call % cap;
register variable-slot template envelope; default tier per vertical.

_W26 DESIGN phase complete 2026-06-18._
