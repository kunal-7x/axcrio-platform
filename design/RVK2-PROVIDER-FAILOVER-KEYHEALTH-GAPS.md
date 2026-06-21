# RVK2 — PROVIDER FAILOVER + KEY HEALTH + BILLING ATTRIBUTION — GAP ANALYSIS

> READ-ONLY design artifact (no code/box mutation). Dimension: **provider failover, key rotation,
> health scoring, fail-loud-not-silent, billing attribution to the provider actually used.**
> Grounded in the LIVE tree (file:line verified 2026-06-18) + 2026 web research. Maps each gap to the
> owning wave (W1..W17) or flags a NET-NEW wave. Companion to `RVK2-BLINDSPOT-OBSERVABILITY.md`
> (which owns the observability/trace G2 finding — this doc owns the failover/key/billing mechanics).

## GROUND TRUTH (what is actually on the box today)

- **LIVE OUTBOUND `agent.py` (the earner) uses a DUMB blind round-robin.** `_collect_groq_keys()` /
  `_collect_sarvam_keys()` build `itertools.cycle(...)` lists (`agent.py:77-125`); `_next_groq_key()`
  / `_next_sarvam_key()` just return the next key in the cycle with **zero** health, cooldown, or 429
  awareness. The smart `llm_router/provider_pool.py` (cooldown-aware, least-used, 429-marking,
  Retry-After parsing) **exists but is used ONLY by the INBOUND `aim_voice_agent.py` + the caller.py
  status route** — the live outbound earner never imports it.
- **Key is PINNED per-call at session start, no mid-call failover.** `_call_groq_key = _next_groq_key()`
  (`agent.py:588`) → `groq.LLM(api_key=_call_groq_key, ...)` (`agent.py:604`). STT key picked once
  (`agent.py:593`). **ElevenLabs is a single hardcoded `os.environ["ELEVENLABS_API_KEY"]`**
  (`agent.py:564`) — NO pool, NO rotation, NO second key at all. If any of these 429s / 401s / stalls
  mid-call, the call breaks; there is no swap to another key or another provider.
- **Billing attribution records the VENDOR class, never the KEY/account actually used, and is
  `estimated`.** The per-call usage flush (`agent.py:499-532`) emits `{"vendor":"groq"}` /
  `{"vendor":"elevenlabs"}` / `{"vendor":"sarvam"}` with `"actual_or_estimated":"estimated"` and NO
  `key_id` / `account` / `provider_def_id`. Spend cannot be attributed to the specific key/account that
  was actually billed.
- **A registry framework already exists** (`PROVIDER-FRAMEWORK-PLAN.md`, W1-W5 live): a PG+FORCE-RLS
  provider registry with health-log table + in-memory circuit breaker + Fernet key store. BUT it is a
  **CRUD/registry for HOSTED providers (video/image/LLM-router)** — it does NOT govern the voice hot
  path's STT/TTS/LLM key selection, and `provider_health_log` is written by a 60s background probe, not
  by real call outcomes. The runtime voice-path failover is a separate, unbuilt concern.

## RESEARCH ANCHORS (2026, sourced below)

- **Groq rate limits are PER-ORGANIZATION, not per-key.** Multiple keys under one Groq org share the
  SAME RPM/TPM/RPD/TPD bucket → adding `GROQ_API_KEY_2.._20` from one account gives **ZERO extra
  headroom**. "Rate-limit headroom comes from independent quota pools (separate providers, projects, or
  accounts), not extra keys under one org."
- **Groq returns rich headers** (`retry-after`, `x-ratelimit-remaining-{requests,tokens}`,
  `x-ratelimit-reset-{requests,tokens}`) — but `retry-after` is set ONLY on the 429. Proactive systems
  read `remaining` BEFORE hitting the wall.
- **For voice/realtime the real ceiling is CONCURRENCY, not character/token quota.** ElevenLabs
  concurrency: Free 2 / Starter 3 / Creator 5 / Pro 10 / Scale-Business 15 → `too_many_concurrent_requests`
  429. 500 concurrent telecaller seats vs a 15-slot EL plan is an unbridgeable gap with one account.
- **Circuit breaker (CLOSED→OPEN→HALF-OPEN) cuts failover from 10s to ms;** latency-based health
  (P95 > 2× baseline → deprioritize) catches partial brown-outs that error-based breakers miss.
- **"Rotating a key on a quota-429 hides the real owner and breaks incident review."** Distinguish
  credential failure (401/invalid → rotate/disable) from quota-429 (cool down, don't disable) from
  concurrency-429 (queue/shed, don't cool the key).

---

## THE GAPS

### G-PF1 — The EARNER hot path uses a blind round-robin with NO health/429/failover; the smart pool it needs already exists but is wired only to inbound  [CRITICAL · W5]
The live outbound `agent.py` rotates keys with `itertools.cycle` (`:85-125`) — it cannot skip a cooling
key, cannot react to a 429, cannot fail over. The cooldown-aware `provider_pool.py` (least-used + 429
mark + Retry-After) is already built and proven on inbound but the earner never uses it. **Fix:** W5's
provider router must make the OUTBOUND hot path resolve STT/LLM keys through `provider_pool.pick()`
(+ `mark_429`/`mark_ok` on every call result), with an in-memory circuit breaker per (provider,key).
This is a key-selection swap, not a rewrite — earner-gated, flag-OFF, inbound-proven first.

### G-PF2 — Key is pinned for the whole call; a mid-call 429/401/stall = a dead call, no swap  [CRITICAL · W5]
`groq.LLM(api_key=_call_groq_key)` is constructed once and lives the whole call (`:602-618`). LiveKit's
`AgentSession` holds that one client; if it 429s on turn 4 there is no swap to another key/provider —
the turn fails. **Fix:** W5 wraps the LLM/STT plugin in a **failover adapter** that, on a 429/5xx/timeout
for a turn, re-picks the next available key (or the fallback provider) and retries THAT turn once before
falling back to the canned line. Bound the retry to a tight budget (~1 extra TTFT) so latency stays sane.

### G-PF3 — Multi-key strategy is FUTILE under one org: Groq quota is per-org, so `_2.._20` give zero headroom  [CRITICAL · W5 + W13 + NEW]
The founder's whole mental model ("add more keys to spread load") is defeated by Groq's per-ORG limit —
keys from one account share one bucket. The pool will round-robin keys that all 429 together. **Fix:**
(a) W13's provider-config UI must capture, per key, the **account/org it belongs to** and group health
at the ORG level, not the key level; (b) the pool must treat same-org keys as ONE quota pool (don't
falsely believe 20 keys = 20× headroom); (c) the product guidance + UI must tell the founder the only
real headroom is **separate accounts/projects** or **a second provider** (SambaNova/Cerebras/OpenRouter
fallback). Without this the pool is theater. Flag as needing a small NET-NEW "org/account grouping"
model in the key store.

### G-PF4 — ElevenLabs has NO pool at all (single env key) AND its real ceiling is CONCURRENCY, which round-robin cannot solve  [CRITICAL · W5 + W13]
`agent.py:564` is a single `os.environ["ELEVENLABS_API_KEY"]`. There is no EL rotation, no EL fallback,
and — critically — for voice the binding constraint is the **concurrency slot count** (2-15 by plan),
not character quota. At 500 seats you will saturate EL concurrency regardless of keys. **Fix:** W5 adds
an EL key pool with concurrency-aware admission (track in-flight EL streams per key/account; when all
accounts are at their concurrency cap, fail over to **Sarvam Bulbul** TTS rather than queueing a live
caller). W13 surfaces per-account EL plan/concurrency so capacity is visible. This couples to W12
(capacity planner): TTS concurrency is a first-class capacity dimension, not just SIP channels.

### G-PF5 — No distinction between 401-credential-dead, quota-429, and concurrency-429 → wrong remediation, key churn, hidden incidents  [HIGH · W5 + W13]
`is_429()` in `provider_pool.py:234` lumps all rate-limit text together; nothing classifies a 401
(dead/rotated key → must DISABLE, not cool) vs a TPM-429 (cool by Retry-After) vs a
concurrency-429 (`too_many_concurrent_requests` → shed/queue, do NOT cool the key — it's healthy).
Research warns rotating on a quota-429 "hides the real owner." **Fix:** W5 classifies each failure into
{auth_dead, quota_exhausted, concurrency, server_5xx, timeout} and applies the right action (disable /
cooldown-by-retry-after / shed / circuit-open / retry-once). W13 shows the classification per key so the
founder sees "this key is INVALID" vs "this key is just busy."

### G-PF6 — Cooldown is reactive-only; no PROACTIVE header-based pre-emption → keys 429 mid-call instead of being skipped before  [HIGH · W5]
The pool only reacts AFTER a 429 (`mark_429`). Groq returns `x-ratelimit-remaining-tokens/requests`
on EVERY 200 — a pool that reads them can deprioritize a key at ~10% remaining BEFORE it walls, so a
live caller never eats the 429. Research: "alert/act when X-RateLimit-Remaining drops below ~20%."
**Fix:** W5's adapter parses ratelimit headers on every success and feeds a "near-exhaustion" soft-cool
into the pool (deprioritize, not fully cool). Latency-based health too: if a key's P95 TTFT > 2×
baseline over a 5-min window, deprioritize (catches brown-outs no 429 reports).

### G-PF7 — "Provider selected ≠ provider used" has no durable record for the OUTBOUND path; a silent-Sarvam-class bug stays invisible  [CRITICAL · W5 + W17]
(Cross-ref `RVK2-BLINDSPOT-OBSERVABILITY.md` G2 — this doc owns the failover-specific facet.) When the
pool fails over Groq→Sarvam or key A→key B, or when EL falls back to Sarvam TTS, **nothing durable
records which key/provider actually served each turn.** The Sarvam-silence bug (selected-but-no-audio)
is exactly this class. **Fix:** W5 emits a per-turn `provider_decision` event carrying
{modality, requested_provider, requested_key_id, resolved_provider, resolved_key_id, produced_output:bool,
fallback_reason}; W17 surfaces it and a fleet counter `famit_provider_mismatch_total`. Fail LOUD: a
fallback or a produced_output=false must raise a visible signal, never pass silently.

### G-PF8 — Billing is attributed to the vendor CLASS, never the KEY/account billed, and is `estimated` not reconciled → cost-per-appointment is unknowable and free-tier overspend invisible  [HIGH · W13 + W17]
`agent.py:509-527` emits `vendor:"groq"` with no `key_id`/`account` and `actual_or_estimated:"estimated"`.
You cannot answer "which account got billed for this call," cannot reconcile against the provider invoice,
and cannot detect a key silently dropping off free tier into paid. The W17 north-star metric is
**cost-per-appointment**, which requires cost attributed per call AND per the key/account that actually
served it. **Fix:** the usage event must carry `key_id` + `account_id` + `provider_def_id` (joinable to
the W13 registry) and the resolved provider from G-PF7; add a **reconciliation job** that pulls each
provider's real usage/billing (Groq has no billing API → use header token counts as the authoritative
meter; EL workspace analytics IS authoritative; Sarvam by audio-seconds) and flags drift between our
estimate and the vendor's number per account.

### G-PF9 — Telephony (SIP/Vobiz) failover is designed for trunk health but NOT for credential/account health or per-trunk billing attribution  [HIGH · W12 + W13]
`telephony-independence-megaplan.md` covers trunk channel-counting + health (healthy/degraded/dead) +
rotation, but treats a trunk as one credential; it does not model **provider-account auth failure**
(Vobiz token expired/revoked = ALL trunks on that account dead at once — the same failure mode that
already broke warm-transfer once via a stale-SIP-trunk env captured at import), nor **per-trunk/per-call
cost attribution** (which account/rate-card billed this minute). **Fix:** W12 adds account-level
auth-health (one probe per account, not per trunk) and W13 captures per-trunk rate-card + account so
call-minute cost attributes to the actual trunk used — feeding the same cost-per-appointment join as
G-PF8. Telephony is a "provider" in the failover/key-health model, not a special case.

### G-PF10 — No fleet-wide health dashboard / alerting; the founder learns a key/provider is dead only from a dead call  [HIGH · NEW (small) + W13]
There is a `/admin/provider-keys/status` snapshot route but no **alerting** and no live fleet board.
Research: "monitoring is reactive; alerting is proactive." With 500 seats, a key going invalid or an
org hitting its TPD must page the founder (Telegram/PushNotification) BEFORE it tanks call quality.
**Fix:** a small NET-NEW "provider health alerter" (rides caller.py / a cron, NOT agent.py): thresholds
at 70/80/90% quota-remaining + any key auth_dead + any provider circuit-OPEN → push alert; W13's UI
shows the live board (per key: available/cooling/dead, quota remaining, last error class, account).

### G-PF11 — Circuit breaker / failover state is per-process in-memory only; with multiple agent workers each re-learns "key is dead" independently  [MEDIUM · W5 + W8]
`provider_pool` state is process-local (`ProviderPool._keys` in memory). The outbound agent runs as
worker processes; each must independently 429 and cool the same key, and a key cooled on worker A is
still "fresh" to worker B → repeated 429s, slower convergence, wasted live calls. **Fix:** share
cooldown/circuit state via Redis (the event bus W8 already introduces Redis) — a key 429'd anywhere is
cooled fleet-wide for the Retry-After window. Keep the in-memory pick fast-path (read Redis async,
never block the turn) — Redis is the shared truth, memory is the hot cache.

### G-PF12 — No fallback PROVIDER chain, only a key chain; if Groq (the whole vendor) browns out, there is no second LLM vendor on the hot path  [HIGH · W5]
The pool fails over between Groq KEYS but there is no second LLM VENDOR wired into the live session
(the plan names "Groq primary + one fallback" and "OpenRouter = fallback router" but the live agent has
only Groq). A Groq-wide incident (region outage, model deprecation, org-wide TPD wall) kills every call.
**Fix:** W5 wires an ordered fallback CHAIN by capability — Groq(llama) → SambaNova/Cerebras (fast OAI-
compat) → OpenRouter (last, +latency) — selectable per turn when the primary vendor's whole pool is
unavailable. Reuse the registry's capability resolution (`PROVIDER-FRAMEWORK-PLAN` §2c) so the chain is
config-driven, not hardcoded. Validate each fallback meets the TTFA<1s budget before it's allowed live.

### G-PF13 — A failed FALLBACK (the canned line) is itself a key-dependent network call with no offline floor  [MEDIUM · W5]
The opener/close fallbacks still call Groq (`agent.py:172,246,374` use `_next_groq_key()`); the "safety"
path shares the same failure mode as the thing it's protecting. If the org is fully 429'd, even the
fallback line generation fails. **Fix:** the absolute floor must be a **pre-rendered, key-free** TTS or
text line per language (cached audio / templated string) so a fully-down provider fleet still yields a
graceful human-sounding line instead of dead air — and that floor event is logged as a hard failure
(fail loud).

### G-PF14 — No per-tenant / per-campaign key isolation or BYO-key spend control on the voice path → one tenant's burst 429s every other tenant's calls  [HIGH · W5 + W13]
The voice pools are PLATFORM-global (`provider_pool` singletons). A single high-volume tenant can exhaust
the shared org's TPD and **429 every other tenant's live calls** — a multi-tenant fairness/cost-leak
hole. The registry already supports per-tenant BYO credentials (`provider_credentials.scope='integration'`),
but the voice hot path doesn't consult them. **Fix:** W5 resolves the voice key by tenant FIRST (BYO key
if present → that tenant's own quota/bill), platform pool only as shared fallback; W13 lets a tenant bring
their own Groq/EL/Sarvam key so heavy tenants run on their own quota and bill. Add per-tenant rate
fairness (token-bucket) so no tenant can monopolize the shared pool.

---

## SEVERITY SUMMARY → OWNING WAVE

| ID | Gap | Severity | Owning wave |
|----|-----|----------|-------------|
| G-PF1 | Earner uses blind round-robin; smart pool wired only to inbound | CRITICAL | W5 |
| G-PF2 | Key pinned per call; mid-call 429/401/stall = dead call, no swap | CRITICAL | W5 |
| G-PF3 | Multi-key futile under one Groq org (per-org quota) | CRITICAL | W5 + W13 + NEW (org grouping) |
| G-PF4 | EL has no pool + real ceiling is concurrency, not quota | CRITICAL | W5 + W13 |
| G-PF7 | Provider-selected ≠ used has no durable record (outbound) | CRITICAL | W5 + W17 |
| G-PF5 | 401 vs quota-429 vs concurrency-429 not classified | HIGH | W5 + W13 |
| G-PF6 | No proactive header/latency-based pre-emption | HIGH | W5 |
| G-PF8 | Billing attributed to vendor class not key/account; estimated only | HIGH | W13 + W17 |
| G-PF9 | Telephony failover ignores account-auth-health + per-trunk billing | HIGH | W12 + W13 |
| G-PF10 | No fleet health dashboard / proactive alerting | HIGH | NEW (alerter) + W13 |
| G-PF12 | No fallback PROVIDER chain, only key chain | HIGH | W5 |
| G-PF14 | No per-tenant key isolation → cross-tenant 429 contagion | HIGH | W5 + W13 |
| G-PF11 | Circuit/cooldown state per-process, not fleet-shared | MEDIUM | W5 + W8 |
| G-PF13 | Fallback line is itself a key-dependent call, no offline floor | MEDIUM | W5 |

## THE NET-NEW WORK THE 18-WAVE PLAN MISSES
1. **Org/account grouping in the key store** (G-PF3) — the pool must model that N keys can share ONE
   quota bucket; without it the whole multi-key strategy is theater. (Small model + UI change; W13-adjacent.)
2. **Provider health alerter** (G-PF10) — proactive paging at 70/80/90% quota + auth-dead + circuit-OPEN.
   (Small service riding caller.py/cron, never agent.py.)
3. **Reconciliation job** (G-PF8) — pull each vendor's real usage and flag drift vs our estimate per
   account; the only way cost-per-appointment is trustworthy.

## THE ONE-LINE THESIS
The platform has a SMART provider pool and a registry framework already built — but the LIVE EARNER runs
on a DUMB blind round-robin, ElevenLabs has no pool at all, the multi-key plan is defeated by Groq's
per-ORG quota, failover is reactive-only and key-only (no provider chain, no concurrency awareness), and
spend is attributed to a vendor CLASS not the key/account actually billed. W5 (provider router) must
inherit the inbound pool, add classification + proactive header/latency health + a provider fallback
chain + per-tenant BYO isolation + fleet-shared Redis circuit state, fail LOUD on every fallback, and
attribute every unit of spend to the resolved key/account — feeding W13 (config/health UI + alerter) and
W17 (cost-per-appointment + reconciliation).

## SOURCES
- Groq Rate Limits (per-ORG, headers): https://console.groq.com/docs/rate-limits
- LiteLLM Router / weighted failover: https://docs.litellm.ai/docs/routing
- Retries, Fallbacks, Circuit Breakers (production): https://www.getmaxim.ai/articles/retries-fallbacks-and-circuit-breakers-in-llm-apps-a-production-guide/
- LLM Failover & Load Balancing: https://www.truefoundry.com/blog/llm-failover-load-balancing-provider-outages
- ElevenLabs 429 / concurrency limits: https://help.elevenlabs.io/hc/en-us/articles/19571824571921-API-Error-Code-429
- ElevenLabs error messages / quota: https://elevenlabs.io/docs/developers/resources/error-messages
- Proactive quota monitoring / thresholds: https://oneuptime.com/blog/post/2026-02-17-how-to-monitor-api-usage-and-set-up-alerts-for-quota-thresholds-in-gcp/view
- Rotate-on-credential-not-quota guidance: https://blog.laozhang.ai/en/posts/openclaw-rate-limit-exceeded-429
