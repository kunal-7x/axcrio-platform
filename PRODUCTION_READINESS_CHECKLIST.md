# PRODUCTION READINESS CHECKLIST
## Definition of Done — nano-details the founder will NOT ask for

**How to use:** Gate every feature ship on this list. Any unchecked box = NOT DONE.
Grouped by layer. Items marked `[AUTO]` must be inferred and built without being asked.

---

## LAYER 0 — ROOT CAUSE GATE (run BEFORE any code change)

- [ ] Root cause is PROVEN by measurement (log diff / replay / controlled variable test), NOT a hypothesis
- [ ] Founder's debugging guess is logged as `HYPOTHESIS (unverified)` — it graduates to `CAUSE (proven)` only after measurement confirms it
- [ ] Single variable changed per test — not two things at once
- [ ] Stop-loss: if two consecutive speculative changes don't move the measured metric → HALT, re-measure from scratch
- [ ] Rollback path defined BEFORE the change is made (backup file + restart command documented)

---

## LAYER 1 — FRONTEND

### Lists / Tables / Feeds `[AUTO — no ask needed]`
- [ ] Pagination or infinite scroll (never load all rows)
- [ ] Virtualization for lists > 50 rows (react-window or equivalent)
- [ ] Skeleton / loading state while data fetches
- [ ] Empty state (message + CTA, not a blank white box)
- [ ] Error state (message + retry button)
- [ ] Optimistic UI for mutations (show result immediately, revert on failure)
- [ ] Debounce on search/filter inputs (300ms)
- [ ] URL state for pagination + filters (browser back works)

### Forms `[AUTO]`
- [ ] Client-side validation before submit (required, format, length limits)
- [ ] Disabled submit button while inflight (prevent double-submit)
- [ ] Server error displayed inline, not silently swallowed
- [ ] Success state / redirect after submit

### Navigation + Auth `[AUTO]`
- [ ] Route guards: unauthenticated → login, wrong role → 403 page
- [ ] Token expiry handled (auto-refresh or redirect to login, no silent 401 loops)
- [ ] Loading indicator for slow navigations (skeleton or spinner)

### Performance `[AUTO]`
- [ ] Images lazy-loaded (`loading="lazy"` or IntersectionObserver)
- [ ] No layout shift on image load (explicit width/height or aspect-ratio)
- [ ] Code-split heavy routes (dynamic import)
- [ ] No `console.error` / unhandled promise rejections in prod build

### Multi-tenant `[AUTO]`
- [ ] Every UI query scoped to current tenant (never show cross-tenant data)
- [ ] Tenant switcher clears all cached state

---

## LAYER 2 — BACKEND / API

### Every Endpoint `[AUTO]`
- [ ] Authentication required (JWT validated — not just present, but signature + expiry)
- [ ] Authorization checked (role / permission, not just authenticated)
- [ ] Input validated and sanitized (type, length, format, enum membership)
- [ ] 400 returned for bad input with a human-readable error (not a stack trace)
- [ ] 401 / 403 / 404 used correctly — never leak existence via 403 vs 404 ambiguity on sensitive resources
- [ ] Rate limited (per-tenant or per-IP depending on endpoint sensitivity)
- [ ] Request timeout set (no infinite hang)
- [ ] All error paths return JSON, not HTML or empty body

### Mutations (POST / PUT / PATCH / DELETE) `[AUTO]`
- [ ] Idempotency key checked (double-submit = same result, not double write)
- [ ] Atomic: DB write + side-effect (email / webhook / audit) in a single transaction or saga with compensate
- [ ] Audit record written (who, what, when, tenant) before the response is returned
- [ ] Response includes the created/updated resource (not just `{ok: true}`)

### Reads (GET / LIST) `[AUTO]`
- [ ] Pagination enforced server-side (max page size capped, never unbounded SELECT)
- [ ] Filters validated (SQL injection impossible — parameterized queries only)
- [ ] N+1 avoided: list endpoints use JOIN or `IN(...)` not per-row queries
- [ ] Index exists on every WHERE column and every FK used in a JOIN
- [ ] Response time < 200ms at p95 for list endpoints (verify with EXPLAIN ANALYZE)

### Background Jobs / Async `[AUTO]`
- [ ] Retry with exponential backoff + max attempts + dead-letter queue
- [ ] Idempotent: running the same job twice produces the same state
- [ ] Job failure does NOT silently drop the task — logged + alerted
- [ ] Timeout on external calls inside the job (not blocked indefinitely)

---

## LAYER 3 — DATA / DATABASE

- [ ] Migration is reversible (down migration written alongside up)
- [ ] FORCE RLS on every new table (no `%` admin bypass without explicit GUC)
- [ ] Foreign keys declared (no orphaned rows possible)
- [ ] Nullable vs NOT NULL deliberate (no accidental NULLs)
- [ ] UNIQUE constraint where business logic requires uniqueness (not just app-level check)
- [ ] `created_at` / `updated_at` columns on every entity table (DEFAULT now(), trigger for updated_at)
- [ ] Large text / JSONB columns have size bounds where applicable
- [ ] No SELECT * in application code — explicit column list
- [ ] EXPLAIN ANALYZE run on any query touching > 10k rows

---

## LAYER 4 — SECURITY

- [ ] Secrets only in `.env` / secret manager — never in code, never in logs
- [ ] `gitleaks protect --staged` = 0 before every commit
- [ ] CORS restricted to known origins (not `*` in production)
- [ ] Headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` set
- [ ] File uploads: type validated server-side (not just extension), stored outside webroot, scanned if possible
- [ ] SQL: parameterized queries only — no string interpolation into SQL
- [ ] Cross-tenant isolation: every DB query includes `tenant_id = :tid` (RLS + app-level double-guard)
- [ ] Sensitive fields (phone, email, PII) never logged in plaintext
- [ ] Admin endpoints behind `require_super_admin` (not just `is_admin`)
- [ ] The static password `FamitCall2026` never reaches `/admin/*` (existing known gap — enforced)

---

## LAYER 5 — OPS / OBSERVABILITY

- [ ] Structured log line on every request (method, path, tenant_id, duration_ms, status)
- [ ] Error logged with stack trace + request context (not just the message)
- [ ] Health endpoint (`/health`) returns 200 + service name + version (used by DO / LB)
- [ ] Restart-safe: service survives `systemctl restart` and comes back clean (py_compile passes, env vars present)
- [ ] Backup exists BEFORE any box-mutating change (file + md5 recorded in STATE.md)
- [ ] Rollback command is one line and documented before the change is deployed
- [ ] No deployment without a smoke test (minimum: the primary happy-path returns 200)
- [ ] Alerts on: 5xx spike, job failure, wallet balance low, service crash (Telegram hook or equivalent)
- [ ] Metrics: request count, error rate, p95 latency — at minimum as log aggregates

### Voice / LLM path specifically `[AUTO]`
- [ ] Prompt size tracked (char count logged on each call)
- [ ] Loop detector running in replay harness before any prompt.py change goes live
- [ ] High-N replay (N ≥ 40 per failing turn) before declaring a prompt fix works
- [ ] agent.py md5 logged on service start (locked file must never silently change)

---

## LAYER 6 — QUALITY

- [ ] Happy path test (the main flow works end-to-end)
- [ ] Unhappy path tests: bad input, missing auth, resource not found, duplicate submit
- [ ] Multi-tenant isolation test: tenant A cannot read/write tenant B's data
- [ ] Concurrent write test for any balance / counter (no double-spend, no race)
- [ ] Load test for any endpoint expected to receive > 10 req/s
- [ ] No test that only tests mocks — at least one test hits the real DB (local or staging)

---

## LAYER 7 — COST / SCALE

- [ ] LLM token budget set per call (max_tokens cap — never unbounded)
- [ ] Free / low-cost provider used for dev/test (Pollinations, Gemini-free, local) — never burn paid credits on testing
- [ ] External API calls cached where response is stable (TTL appropriate to staleness tolerance)
- [ ] Per-tenant usage metered and stored (so billing is always derivable from DB, not memory)
- [ ] Runaway job guard: max iteration count / max runtime on any loop

---

## "DONE" DEFINITION (reserved — requires evidence)

**"Done" is only valid when ALL of the following are true:**

1. Every checklist item above relevant to this feature is checked.
2. Integrated smoke of the REAL end-to-end flow passed — with evidence (log output, measurement, screenshot, replay result).
3. What only the founder's manual test can prove is stated explicitly with exact click-by-click steps.
4. Rollback path confirmed (backup md5 recorded, one-line restore command documented).
5. EARNER-LIVE-STATE.md updated with the new live state (md5s, PIDs, config).

**Saying "done" without this evidence block is a protocol violation.**

---

## AUTO-INFERENCE TRIGGERS (build these without being asked)

| Trigger | Auto-add |
|---|---|
| New list / table / feed | Pagination + virtualization + loading/empty/error states |
| New form | Client validation + double-submit guard + server error display |
| New API endpoint | Auth + authz + input validation + rate limit + idempotency |
| New DB table | RLS + FK + NOT NULL + indexes + created_at/updated_at |
| New background job | Retry + dead-letter + idempotency + timeout |
| New LLM call | max_tokens cap + prompt size log + loop replay gate |
| New file/secret | gitleaks check + .gitignore entry |
| Any box-mutating change | Backup + md5 recorded + rollback command + smoke test |
| Any balance / counter mutation | Concurrency test (no double-spend) |
| New backend feature | Matching frontend CRUD UI — never backend-only |
