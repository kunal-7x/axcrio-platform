# READINESS.md — auto-applied production checklist (Gate 1)

> The nano-details a real shipping team adds WITHOUT being asked. Run the relevant rows
> against EVERY build before claiming done. A row that doesn't apply is skipped; a row that
> applies is either DONE or written into `MISSING_LAYERS.md` (never silently dropped).
> Trigger phrasing: "I created a ___" → the matching block is mandatory.

## I created a LIST / FEED / TABLE / grid
- [ ] Pagination or infinite scroll (never load-all)
- [ ] Virtualization for long lists
- [ ] Loading state, empty state, error state (all three)
- [ ] Lazy-load images/heavy cells
- [ ] Stable sort + a sensible default order

## I created an API ENDPOINT / route
- [ ] AuthZ (who can call it) + tenant scoping / RLS
- [ ] Input validation + sane error shape (not a 500 stack)
- [ ] Rate-limit / abuse guard
- [ ] Idempotency for anything that writes money/state
- [ ] Timeout + retry/fallback for downstream calls

## I touched a DB / migration / schema
- [ ] Forward migration + a tested rollback
- [ ] Index for every new query path (no full scans, no N+1)
- [ ] FORCE-RLS on new multi-tenant tables (zero `%` DDL)
- [ ] No-double-spend / idempotency on money paths

## I built a BACKEND feature
- [ ] The matching FRONTEND control UI: full CRUD + configure + TEST/preview, real-time
- [ ] Reuse the existing UI kit (Core_2) — never invent components from scratch
- [ ] Wired into nav + api.ts; the founder can do it from his screen without asking

## I changed the VOICE EARNER (highest law)
- [ ] agent.py voice/TTS span + `.env` (EL_STABILITY, voice_id) BYTE-IDENTICAL — brain work in prompt.py only
- [ ] One box-mutating change only; one-command revert path named first
- [ ] Empirical replay gate BEFORE deploy (e.g. 0-loop high-N live-Groq replay)
- [ ] Prompt SIZE checked (size is a small-model degeneration lever)
- [ ] Founder real-PSTN-call is the only final truth — say so

## I changed anything PERF-sensitive
- [ ] Measured the number first (don't pre-optimize on a guess)
- [ ] Caching where the same work repeats; payload trimmed
- [ ] Latency budget stated + checked on the real path

## EVERY build (cross-cutting)
- [ ] Failure modes enumerated + handled (the resilience lens)
- [ ] Observability: logs/metrics so the next failure is diagnosable fast
- [ ] An empirical verification command exists and was RUN (Gate 3)
- [ ] Secrets never committed (`gitleaks` clean)
- [ ] Deferred items written to `MISSING_LAYERS.md`, not dropped
