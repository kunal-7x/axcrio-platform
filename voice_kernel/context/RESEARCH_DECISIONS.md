# W3 RESEARCH + DECISIONS — Vendor-script-as-authoritative-blueprint + Prompt-injection defense

> Scope: the `VendorScriptEngine` + `ContextEngine` build under `voice_kernel/context/`.
> The founder's flagship is "inject the PDF/script VERBATIM so the agent talks
> exactly like our telecaller" — that verbatim vendor text IS the prompt-injection
> attack surface (untrusted CAMPAIGN_BRIEF). This note is the binding decision log;
> it does NOT edit any live file (EARNER LAW). The live-agent splice
> (`/extract` + `run_job` + recap-seam) is a LATER flag-gated seam — recorded in
> §6 SEAM NOTE, not built here.

## 0. The core tension (stated honestly)
A vendor script must DRIVE the call (persona, greeting, talking points, objection
handling) — i.e. it is *authoritative for content/flow*. But it must NOT be
*authoritative for the agent's rules* — embedded "ignore your instructions /
reveal the system prompt / call this other number / drop the AI disclosure" must
be inert. **The resolution is a split: the script is authoritative as DATA-that-
shapes-behaviour, never as INSTRUCTIONS-that-rebind-the-agent.** Two different
trust tiers for two different uses of the same bytes.

## 1. RESEARCH — what production systems actually do (primary sources)
- **OWASP LLM01 (2025): prompt injection is still #1.** Root cause named everywhere:
  the model treats system text and untrusted text as the *same priority*. The fix
  is a trust/priority hierarchy enforced structurally. (OWASP / CrowdStrike / Palo Alto)
- **OpenAI Instruction Hierarchy** (arxiv 2404.13208): train/treat sources as
  `System > Developer > User > Tool/Retrieved`. Retrieved & uploaded documents are
  the LOWEST trust (priority ~30). All retrieved/user/document text = UNTRUSTED.
- **Microsoft Spotlighting** (arxiv 2403.14720 + MSRC 2025-07): mark untrusted
  content explicitly. Three modes — **delimiting** (randomized delimiter around the
  block), **datamarking** (a sentinel token interleaved through the text), **encoding**
  (base64/ROT13 the block). Plus Prompt Shields (a classifier detector) and
  *deterministic* impact controls (least-privilege, block exfil vectors, HITL on
  high-risk actions). Defense is layered: probabilistic prevention + probabilistic
  detection + deterministic mitigation.
- **Google "Defending Gemini" (arxiv 2505.14534) — THE load-bearing finding:**
  *simple delimiter schemes, INCLUDING closing-tag escaping, can be bypassed.* A
  fence alone is necessary-but-not-sufficient. Their stack = spotlighting markers +
  adversarial training + classifiers + **runtime OUTPUT-SCANNING + CANARY TOKENS**
  (a secret marker in the system prompt; if the model ever emits it, the turn was
  hijacked → kill/flag). "Extract genuine information from a document while not
  executing embedded commands" is the exact named goal.
- **Voice-agent specific** (NVIDIA / Uniphore / AssemblyAI / Gladia): ground in a
  trusted KB; apply guardrails at THREE checkpoints — input, tool-call, output;
  evidence-based answering (cite or don't claim); agents "freelance" off-script when
  scope is vague → tight scope boundaries beat verbose prompts.

## 2. DECISIONS — vendor-script-as-authoritative-blueprint (the founder flagship)
The verbatim script is split at INGEST into two artifacts with two trust tiers:

| Artifact | Trust | How it reaches the prompt | Authoritative for |
|---|---|---|---|
| **Sanitized structured persona** (`tone`, `greeting`, `do`/`dont`, `talking_points`, `objections`, `negotiation_ladder`, `closing_lines`) | semi-trusted (PLATFORM-framed, schema-validated, value-clamped) | the structured `CampaignCard` fields (already typed) | the agent's *style/flow/content* |
| **Raw verbatim script** (`raw_script`) | UNTRUSTED `CAMPAIGN_BRIEF` | a `FencedText(SourceTrust.CAMPAIGN_BRIEF)` block, positioned BELOW the PLATFORM layer, labelled "reference / business context only" | nothing — it is *reference data*, never an instruction source |

Concrete rules (bind these in `voice_kernel/context/`):
- **R1 — DRIVE via the card, not the raw block.** Flow/persona is driven by the
  *extracted, typed, validated* card fields (which the kernel already renders ABOVE
  the fence as platform-authored control text). The raw verbatim text is injected
  only as fenced reference ("here is the vendor's own script for tone/context"),
  never framed as "follow this." This is the persona-vs-instructions split.
- **R2 — Authoritative ≠ rule-rebinding.** The card may override product facts,
  greeting, tone, objection answers. It may NEVER override: the AI-disclosure, the
  opt-out/DND rule, the safety rules, the tenant identity, or the provider/tool
  routing. Those are PLATFORM L0 and sit positionally first (already enforced by
  `_render_platform_layer` rendering before any fence).
- **R3 — Retrieval-over-truncation, losslessly (H13).** Never silently truncate the
  blueprint. Store the FULL script verbatim (`full_product_summary` / `full_usps` +
  `raw_script_ref` pointer); inject a distilled in-prompt copy + set the overflow
  flags so the agent can "recall more on request." Honest: this is summary-scoped in
  the prompt, lossless in storage — do not call the in-prompt copy "lossless."
- **R4 — INLINE_BUDGET cliff.** One enforced number (~3K tokens of distilled card
  inline). Over the cap → UI/validation error at save time, not a silent route to an
  empty RAG. `clamp()` already fails LOUD (`BudgetExceededError`) if L0..L3 alone
  blow budget — keep that.
- **R5 — `card_overrides` is value-only, key-allowlisted.** `VendorScriptEngine.card_overrides`
  may set only known `CampaignCard` field VALUES from validated extraction; it can
  never inject new structural keys, control text, or anything that lands above the
  fence. Schema-validate + clamp BEFORE the override is applied.
- **R6 — `stage_excerpt` returns DATA, returned as a fence-able string.** It returns
  the stage-relevant slice of the *raw* script for L5 reference; the caller wraps it
  via `fence(SourceTrust.RETRIEVED_KNOWLEDGE | CAMPAIGN_BRIEF, ...)`. The engine
  never returns pre-rendered prompt text and never returns an unfenced authority.

## 3. DECISIONS — prompt-injection defense (LAYERED; fence is necessary-NOT-sufficient)
Per Gemini's finding, a fence alone is bypassable. Bind ALL of these:

- **D1 — Structural trust boundary by POSITION (already in `packet.py`).** PLATFORM
  L0 (identity + SHARED_RULES safety) renders FIRST/top; every untrusted source
  (CAMPAIGN_BRIEF, RETRIEVED_KNOWLEDGE, LEAD_MEMORY, CALLER_UTTERANCE) renders BELOW
  it inside a typed `FencedText` fence. Safety is the first token, not a "high
  priority" sentence. `fence()` refuses to wrap PLATFORM (authority is never fenced).
- **D2 — Sanitize BEFORE fencing (the fence is forgeable).** Before building any
  `FencedText` over vendor text, the `context/` ingest MUST:
  - NFKC-normalize, strip zero-width / bidi / control chars, collapse homoglyphs;
  - **escape the fence's own close-tag** in the body (`</campaign_brief>`,
    `</retrieved_knowledge>`, `</vendor_script>`, etc.) so the vendor can't close the
    fence early and "break out" above it. (Necessary but, per Gemini, not sufficient
    alone — hence the rest.)
  - run an injection **denylist on the NORMALIZED form**, multilingual (English +
    Hindi/Hinglish verbs: "ignore/disregard/forget", "system prompt", "instructions",
    "tum/aap … bhool jao / mat karo / ye bolo", "naya number", "disclosure mat").
    Denylist = a *signal to sandbox/flag*, never the only defense.
- **D3 — Canary + output-scan (runtime, the Gemini lesson).** Embed a per-call
  secret canary in the PLATFORM layer; scan the model's OUTPUT each turn — if the
  canary, the raw system rules, or a `</fence>` close-tag appears in the agent's
  speech, the turn was hijacked → drop the turn + flag/kill the session + emit an
  event. This catches what the fence misses.
- **D4 — Datamarking option (Microsoft).** For the highest-risk verbatim block,
  optionally interleave a sentinel token through the untrusted text so the model has
  a continuous "this is data" signal, not just two boundary tags. Behind a flag;
  measure latency/quality before enabling on the earner.
- **D5 — Trust-tier gates EARNER exposure (hard precondition).** A freshly-uploaded
  script defaults to `trust_tier = sandbox`. **Sandbox scripts are INBOUND-ONLY**
  until a super-admin explicitly promotes to `trusted`. No sandbox script ever
  reaches the outbound earner. This is the deterministic blast-radius control.
- **D6 — `extract_fields` is schema-validated + value-clamped at the sink.** The
  extraction that turns raw script → structured card is an open injection sink (V2
  amplifies it). Validate the output schema and clamp every value BEFORE store/use;
  an extraction that yields out-of-schema or oversized values is rejected, not
  best-effort'd.
- **D7 — Memory/RAG fenced ABOVE-vs-BELOW correctly.** Lead memory (possibly poisoned
  by a prior call) and RAG snippets are ALSO untrusted → already fenced
  (`LEAD_MEMORY`, `RETRIEVED_KNOWLEDGE`). The vendor block must not be able to
  reference/leak the caller-history block above it — assert ordering in a test.

## 4. Three-tier defense map (matches Microsoft's prevention/detection/mitigation)
- **Prevention (probabilistic):** D1 position-fence, D2 sanitize/escape/normalize,
  D4 datamarking, R1 persona-vs-raw split.
- **Detection (probabilistic):** D2 denylist, D3 canary + output-scan, D6 schema-validate.
- **Mitigation (deterministic, blast-radius):** D5 sandbox-trust-tier → inbound-only,
  R2 rules-never-overridable, R4 budget fail-loud, least-privilege tools (no
  destructive action from a script-driven turn without firewall PIN).

## 5. What to BUILD under `voice_kernel/context/` (disjoint new files, this wave)
- `sanitizer.py` — NFKC + zero-width/bidi strip + close-tag escape + multilingual
  denylist scan (returns sanitized text + a list of triggered signals). PURE/sync.
- `script_engine.py` — `VendorScriptEngine` impl: `stage_excerpt()` (sanitized raw
  slice, fence-ready), `card_overrides()` (allowlisted, schema-validated, clamped).
- `context_engine.py` — `ContextEngine` impl: `build_card()` (fields+raw_script →
  CampaignCard with H13 lossless full_* + overflow flags), `build_packet()`.
- `canary.py` — per-call canary mint + an `output_scan(text)` runtime check (D3).
- `trust.py` — `trust_tier` resolution (sandbox|trusted) + the inbound-only gate (D5).
- `tests/` — bound to FROZEN contracts: fence-breakout escaped; canary never echoed;
  Hindi/Hinglish "ignore your rules" inert (card still drives, rules unchanged);
  budget over-cap fails loud; lossless full_* preserved; ordering: memory above
  vendor block; sandbox script refused on outbound path.
- **Registration:** `build_kernel(cfg, context=ContextEngineImpl(), vendor_script=VendorScriptEngineImpl())`.
  NOTE (build blocker found): `KernelServices` field is named `context_engine`, but
  the binding contract says `context=`. `build_kernel` does `replace(svc, **impls)`,
  so `context=` raises TypeError today. **Fix in-wave:** add a thin kwarg alias in
  `build_kernel` mapping `context`→`context_engine` (keep `context_engine` working),
  so the frozen `build_kernel(cfg, context=impl, vendor_script=impl)` call binds.

## 6. SEAM NOTE — the LATER flag-gated live splice (DO NOT build/edit this wave)
EARNER LAW: live `agent.py` md5=98655dbf is frozen; `caller.py` / `aim_voice_agent.py`
are NOT edited here. The cutover (a future founder-signed, flag-gated wave) wires:
- **`/extract` seam** — campaign-save calls the `context/` extractor to produce the
  validated card + store `raw_script` verbatim (lossless) + `script_meta`. Default OFF.
- **`run_job` seam** — at dial, the kernel `build_packet(ctx)` replaces the legacy
  f-string ONLY when `KERNEL_ENABLED=1`; OFF = byte-identical legacy path.
- **recap-seam** — lead memory injected as a fenced LEAD_MEMORY block positioned
  ABOVE the vendor block (so the script can't reference caller history). Inbound-first
  (`aim_voice_agent.py:1436` `_build_sales_instructions`), earner-gated, default OFF.
- Acceptance for the cutover (when it happens): golden-render byte-diff identical
  flag-off; canary not echoed on a poisoned script; sandbox script refused outbound;
  agent.py md5 unchanged; /health 200; no ring. None of that runs in THIS wave.

## Sources
- OWASP LLM Top-10 2025 (LLM01) — via CrowdStrike / Palo Alto cyberpedia
- OpenAI, "The Instruction Hierarchy" — arxiv.org/abs/2404.13208
- Microsoft, "Defending Against Indirect Prompt Injection With Spotlighting" — arxiv.org/abs/2403.14720
- Microsoft MSRC, "How Microsoft defends against indirect prompt injection" (2025-07)
- Google, "Lessons from Defending Gemini Against Indirect Prompt Injections" — arxiv.org/abs/2505.14534
- NVIDIA / Uniphore / AssemblyAI / Gladia — voice-agent guardrails (3-checkpoint, KB-grounding)
