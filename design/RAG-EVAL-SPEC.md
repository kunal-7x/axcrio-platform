# ✅ RAG-EVAL-SPEC — The Gate Before Flipping `RAG_INJECT_ENABLED=1` (W4-RAG)

> **What this is:** the hard, measured acceptance gate that W4-RAG must pass BEFORE the grounding
> injection is turned on for the live inbound voice path. No green per-component report counts — this
> gate proves the integrated, earner-safe, low-latency, faithful, isolated behaviour on the real box.
> A fail leaves `RAG_INJECT_ENABLED=0` (corpus ingested + ready, zero live risk) until tuned.
>
> **Status:** READY (design only). Companion to `RAG-MASTER-PLAN.md` + `RAG-INGESTION-PLAN.md`.
> **Read order:** `RAG-MASTER-PLAN.md` §8 → this. 2026-06-14.

---

## 0. THE FIVE GATES (ALL must pass; any fail ⇒ flag stays OFF)

| Gate | Threshold | Instrument | Hot-fail? |
|---|---|---|---|
| **G1 Earner-safe** | md5/PID/health/golden unchanged, NO ring | md5 + systemctl + `_golden/verify_golden.py` | YES |
| **G2 Latency** | p95 `llm_ttft` regression OFF→ON **< 150ms**; p95 turn ≤ 1400ms; no `tts_ttfb`/EOU regression | **journal log-parse** (NOT `/metrics`) | YES |
| **G3 Faithfulness** | RAGAS faithfulness **≥ 0.85**; context recall **≥ 0.80**; 0 anti-invent guard violations | offline LLM-judge (Gemini-flash free) on golden set | YES |
| **G4 RLS isolation** | cross-tenant grounding bleed = **0**; `_global` write-lock holds | RLS probe over real GUC | YES |
| **G5 Byte-identical-off** | `_build_sales_instructions` flag-off == pre-change, even WITH collateral ingested | instruction-dump diff | YES |

---

## 1. G1 — EARNER-SAFE (the standing gate, run before + after every step)

Exactly the VOICE-BRAIN earner gate (`VOICE-BRAIN-MASTER-PLAN.md §7`):
- `agent.py` md5 == `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED (re-baseline from the box, never trust
  the constant — `AGENT_LEARNINGS` 2026-06-14).
- famit-agent MainPID `1477083` / ActiveEnter `2026-06-10 19:58:18` NOT restarted.
- `_golden/verify_golden.py` on the box → **5/5 byte-identical, exit 0** (proves the shared `prompt.py`
  render is unperturbed — the earner re-renders through `prompt.py` every dial, so md5 of `agent.py`
  alone is a FALSE signal; the golden byte-diff is the real gate).
- caller `/health` = 200 (find the real listen port via `ss -ltnp`, not a guessed one —
  VPC `10.122.0.4:8310` / loopback :8209 per `AGENT_LEARNINGS`).
- 0 new 5xx in caller logs (filter `--since` the service ActiveEnter, or stale pre-deploy noise counts).
- NO outbound dispatch / NO ring (DID resting — HARD RULE).

Only `aim-voice-agent` + `famit-caller` are restarted in W4; `famit-agent` (the earner) is NEVER
restarted in this wave.

---

## 2. G2 — LATENCY (the real cost is the +350-token grounding block → inbound TTFT)

### 2.1 The instrument (decision-critical — do NOT curl `/metrics`)
`obs.py` exposes only `famit_request_latency_seconds{method,route}` (HTTP latency on the CALLER, a
different process). `llm_ttft` is a **log line emitted by the `aim-voice-agent` worker** (LiveKit
`LLMMetrics` → `logger.info`), not a Prometheus histogram (`dynamic-context-rag.md F4`). So:

```
ssh famit@168.144.153.145 \
  "journalctl -u aim-voice-agent --since '<window>' | grep -oE 'llm_ttft[=: ]+[0-9.]+'"
  → collect → compute p95
```
Confirm the exact log key/format the inbound worker emits BEFORE the run (do NOT assume the key name —
inbound has no `_on_metrics` today per `VOICE-BRAIN-MASTER-PLAN.md §4`; if TTFT isn't logged inbound,
add a one-shot per-call `llm_ttft` log line to the inbound metrics hook as part of W5, or measure on the
existing per-call gen-time line). Re-baseline a SEPARATE inbound baseline — do NOT borrow the outbound
number.

### 2.2 The procedure
1. Flag OFF (`RAG_INJECT_ENABLED=0`): place/replay N≥10 inbound test turns over a fixed golden set
   (same campaign, realistic-length prompts incl. an 8K-token script + 10-turn history) → record p95
   `llm_ttft` = **OFF baseline**.
2. Flag ON (`RAG_INJECT_ENABLED=1`, corpus seeded): repeat the identical set → record p95 = ON.
3. **PASS iff:** `p95(ON) − p95(OFF) < 150ms` AND p95 turn latency ≤ 1400ms AND no `tts_ttfb`/EOU
   regression.
4. **Cache-hit proof (the latency moat):** the SECOND new-caller to the same campaign/stage must show a
   grounding-cache HIT in the log (0 `kb.retrieve` call) — proves the W2-substrate grounding cache
   collapses N callers to ~1 retrieval (`RAG-MASTER-PLAN §3`). A per-call retrieval on every new caller
   = the cache key is wrong → BLOCK + fix.
5. **Connect-window proof:** the connect-prefetch `kb.retrieve` (FTS-only) completes inside the 200-400ms
   connect window (cold miss 2-8ms; never blocks first-utterance).

### 2.3 Tuning ladder if G2 fails
`AIM_KB_PREFETCH_K` 5→3 → re-measure → `AIM_KB_GROUNDING_CHARS` 1400→900 → re-measure → if still failing,
leave `RAG_INJECT_ENABLED=0` (corpus ready, injection off, no live risk) and record the numbers in
`build_log/`. The `lookup` tool still covers deep facts mid-call with zero prompt-length cost.

---

## 3. G3 — FAITHFULNESS (voice-critical: a hallucinated price on a live sales call is the worst failure)

### 3.1 The golden set (20 inbound turns × 3 scenarios)
- **FAQ-heavy** (7 turns): caller asks pricing/specs/amenities/possession that ARE in the seeded
  collateral → the agent must answer FROM the chunks, with the right number.
- **Objection-heavy** (7 turns): caller raises price/trust/timing objections → the agent must use the
  `_global` rebuttal PATTERN + the tenant's actual value facts, never invent a discount/number.
- **Out-of-KB** (6 turns): caller asks something NOT in the corpus → the agent must use the escape hatch
  ("team will confirm on a callback / WhatsApp — do NOT make up a number", `DEPLOYED.py:1679`), NEVER
  fabricate. This is the most important scenario — it proves anti-hallucination.

Build the golden set from REAL inbound transcript shapes (the inbound eval bridge, `VOICE-BRAIN-MASTER-PLAN.md
§3E` / W5) — not synthetic. Store under `eval/golden/rag/`.

### 3.2 The metrics (offline, off the hot path)
- **RAGAS Faithfulness ≥ 0.85** — fraction of the agent's answer claims traceable to the retrieved
  chunks. Below 0.80 = hallucination risk. LLM-judge = Gemini-flash FREE tier (founder's no-paid-test
  rule; `MASTER_DNA §O`).
- **Context Recall ≥ 0.80** — did retrieval surface the chunk that contained the answer (catches poor
  FTS recall on Hinglish/Devanagari before flag-on).
- **Anti-invent guard = 0 violations** — a shape-check over the 6 out-of-KB turns: the agent must NOT
  assert a specific price/EMI/address/availability not in the chunks. Any such assertion = a hard fail
  (this is the live-call-safety gate).

### 3.3 Async weekly audit (off hot path, named-for-later)
A weekly Hatchet job (off-box) runs RAGAS faithfulness over a sample of real `kb_query_log` rows per
tenant → a drift report. Below 0.80 for a tenant = corpus quality alert → KB-UI "questions your AI
couldn't answer" + a re-curate prompt. Not in the W4 hot path; named so it's not forgotten.

---

## 4. G4 — RLS ISOLATION (multi-tenant; the `_global` corpus must not break it)

1. **Cross-tenant grounding bleed = 0.** Super-admin act-as Tenant A → the connect-prefetch grounding
   contains ONLY Tenant A's collateral chunks + `_global`. A raw
   `SELECT count(*) FROM kb_chunks WHERE tenant_id='<B>'` under A's GUC (`SET LOCAL app.tenant_id='A'`,
   `is_admin` OFF) returns **0**. Repeat the connect-prefetch concurrently for two different tenants and
   assert each call's grounding has only its own + `_global` (the conn-per-op + `SET LOCAL`-in-txn
   discipline, `kb/core.py:253,337`).
2. **`_global` read-allowed, write-locked.** Every tenant CAN read `_global` (the explicit
   `OR tenant_id='_global'` clause, named — never `%`). NO tenant request path can WRITE a `_global` row
   (the seed endpoint is `require_super_admin` + `is_admin=True`; tenant is resolved from the token, not
   the body). Probe: a forged `POST /brain/knowledge` with `tenant_id='_global'` in the body writes
   under the CALLER's real tenant, never `_global` → 0 `_global` rows attributable to a tenant.
3. **Admin escape-hatch NOT used on the voice read path.** The inbound `_kb_retrieve` calls
   `kb.retrieve(..., is_admin=False)` (verified `DEPLOYED.py:455` → `kb/core.py:301` default
   `is_admin=False`) — never `is_admin=1` (which makes admin see ALL rows, the `VOICE-BRAIN-MASTER-PLAN
   §3D` red-team finding). Assert the call site passes `is_admin=False`.

---

## 5. G5 — BYTE-IDENTICAL WHEN OFF (non-breaking by construction)

With `RAG_INJECT_ENABLED=0`, dump the assembled `_build_sales_instructions(fields, recap, ...)` for a
campaign that **HAS collateral ingested into the KB** (not just any campaign — `dynamic-context-rag.md
F7`: prove the prefix is byte-identical even when knowledge is present) → assert it is byte-identical to
the pre-W4 assembly (no `grounding_block` appended). Flip ON for a NON-PROD test campaign → confirm the
grounding block appears AFTER the KNOWLEDGE PACK / before the lang-lock, prefix unchanged, and a test
call completes with a transcript. This proves the off path is a true no-op and the on path only appends
a suffix (never mutates the cached body).

---

## 6. THE INTEGRATED TRUTH (the only gate that really counts — founder's #1 rule)

Per the OWNERSHIP rule: a green G1-G5 on isolated components is necessary but NOT sufficient. The final
proof is the founder's REAL inbound call to the DID:
- Call in, ask a pricing question that's in the seeded collateral → the AI answers with the RIGHT number
  (grounded), in the caller's language (lang-lock).
- Ask an objection → the AI uses a natural `_global` rebuttal pattern, not a robotic deflection.
- Ask something NOT in the corpus → the AI gracefully says "team will confirm" — does NOT invent.
- The call latency feels human (no added lag from the grounding block).

Only this real, integrated inbound call proves the product. G1-G5 gate the flag-on; the founder's call
confirms it. Record the real-call result in `build_log/` — and state honestly that only the founder's
own call can prove the live mic/voice/grounding adoption (the same residual W1 carried).

---

## 7. ACCEPTANCE CHECKLIST (the wave is DONE when all are ✅)

- [ ] G1 earner-safe before + after every step (md5/PID/golden/health/no-ring)
- [ ] G2 p95 `llm_ttft` regression < 150ms (log-parsed, inbound-baselined) + turn ≤ 1400ms + cache-hit
      collapses N callers to ~1 retrieval
- [ ] G3 RAGAS faithfulness ≥ 0.85 + recall ≥ 0.80 + 0 anti-invent violations on the 20×3 golden set
- [ ] G4 cross-tenant bleed = 0 + `_global` write-lock holds + `is_admin=False` on the voice read
- [ ] G5 byte-identical when off (on a collateral-bearing campaign)
- [ ] Integrated: founder's real inbound call answers grounded, in-language, never invents
- [ ] `RAG_INJECT_ENABLED=1` flipped ONLY after G1-G5 green; instant rollback path proven
- [ ] Numbers recorded in `build_log/wave-build-W4-rag.md`; `ORCHESTRATOR.md` + ledger pointers updated
