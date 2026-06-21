# W2 — RED-TEAM: Disclosure Line vs Rapport (RAPPORT vs DISCLOSURE attack)

> READ-ONLY red-team. Attacks the proposed disclosure openers in
> `design/W2-DISCLOSURE-COMPLIANCE-RESEARCH.md`, `design/W26-INDIA-AI-VOICE-DISCLOSURE-LAW.md`,
> `design/INDIA-TELECOM-AI-DISCLOSURE-LAW.md` against BOTH tests: (a) does it satisfy India's
> in-force law, (b) does it keep the human-sounding sales goal / would a real prospect hang up.
> Per-mode (sales / support / inbound) + vendor-script-compatibility checked. Date 2026-06-18.
> Verdict: **SHIP the resolution, with 5 required fixes below.** Consumed by W2 (brain) + W26 (build).

---

## VERDICT (one line)

The **core legal reasoning is correct and ships**: no in-force Indian statute compels the literal
phrase "I am an AI assistant," so the founder's ban and the law are reconcilable. BUT the three source
docs **disagree with each other on the actual wording**, and two of the proposed lines are **either
illegal-risky or rapport-killing**. Pick ONE canonical opener (below), kill the contradictions, fix the
recording-consent phrasing, and make opt-out + "are you AI?" structural. Then SHIP.

---

## ISSUE 1 (BLOCKER) — the three docs propose CONTRADICTORY disclosure tokens; one set VIOLATES the founder's hard rule

The wave cannot ship three different "canonical" openers. They disagree on the single most load-bearing word:

| Doc | Proposed token | Founder-rule safe? | Legal posture |
|---|---|---|---|
| `W2-DISCLOSURE-COMPLIANCE-RESEARCH.md` | **"automated call"** (no "AI") | ✅ safe | over-states MeitY as near-binding but lands on a safe word |
| `W26-INDIA-AI-VOICE-DISCLOSURE-LAW.md` | Tier 0 = **brand+purpose, no "automated" even**; Tier 1 = "digital assistant"; Tier 2 = explicit "AI" (dormant) | ✅ safe | most legally accurate (AI-mandate = proposed, not in force) |
| `INDIA-TELECOM-AI-DISCLOSURE-LAW.md` §5 | **"an AI voice assistant"**, **"automated AI call"**, **"digital (AI) assistant"** | ❌ **VIOLATES** — literally says "AI" in the default opener | over-states: treats MeitY advisory as "effectively mandatory," proposes the banned word as DEFAULT |

**Why this is a blocker, not a nit:** `INDIA-TELECOM-AI-DISCLOSURE-LAW.md`'s recommended-default line
*"Hi, this is Riya, an AI voice assistant…"* is **functionally identical to the phrase the founder
banned.** "I am an AI assistant" vs "this is Riya, an AI voice assistant" is a distinction without a
difference to a prospect — both announce "you are talking to a robot" in the first second. If W26 build
or W2 picks that doc's wording, the whole product thesis breaks AND it's not even legally required.

**GROUND TRUTH (web-verified 2026-06-18, Bar & Bench):** the AI-specific verbal-self-ID mandate is
*"TRAI is further **considering** an amendment … for AI-based telemarketing, AI disclosures and consent
verification"* — **PROPOSED, NOT IN FORCE.** The "AI must identify within 15/30 seconds" line is
**vendor-blog only** (qcall / ondial / autointerviewai / caller.digital), not black-letter TRAI. MeitY
SGI rules (in force 20 Feb 2026) bind **intermediaries hosting synthetic CONTENT**, not a live 1:1 call.
So saying the word "AI" today buys **zero** legal protection over "automated" — it only pays the rapport
tax for nothing.

**FIX (required):** Promote `W26-INDIA-AI-VOICE-DISCLOSURE-LAW.md`'s **tiered model** to canonical and
mark the other two docs' wording as superseded. **`INDIA-TELECOM-AI-DISCLOSURE-LAW.md` §5 must NOT be
the wording W26 build pulls** — its "AI voice assistant" default is wrong on both axes. One source of
truth for the string.

---

## ISSUE 2 (HIGH) — "automated call" in the W2 doc's default is a measurable rapport / hang-up risk

`W2-DISCLOSURE-COMPLIANCE-RESEARCH.md`'s default —
*"…ek **automated call** kar rahi hoon — aur yeh call quality ke liye **record** hoti hai. Aapke paas 2
minute hain?"* — front-loads **TWO friction words ("automated call" + "record")** in the first breath,
**before any reason or value.** This is exactly the cadence the W6 telecaller playbook and the
identity-confirm pack flag as a hang-up trigger:

- Gong (90,380 calls): naming nothing of value up front and leading with a process-disclaimer cadence
  reads as "spam telemarketer" → prospect screens out. Reason-first openers perform ~2× better.
- The identity-confirm pack (`voice-brain-identity-confirm-reason-permission.md` §1.2, §5) is explicit:
  **cramming identity+disclosure+ask into one breathless robotic line increases mistrust ("scam call"
  cadence)** and ❌-lists it. The W2-doc default does exactly that.
- "yeh call … **record** hoti hai" as the SECOND clause, before the reason, makes an Indian consumer
  think "legal/recovery/scam call" and bail. Recording disclosure is needed, but **placement** matters.

**FIX (required):** Adopt the W26 doc's **sequencing**, not the W2 doc's cram. Order = **brand +
warm reason FIRST → micro-permission → THEN the recording cue woven in** (not leading). Keep "automated"
out of the very first clause; if used at all, it follows the reason as a soft aside. The legal duty is
"disclose up front," not "disclose as literally the first three words" — anywhere in the opening
exchange before the substantive pitch satisfies it.

---

## ISSUE 3 (HIGH) — the recording-consent line is mis-modeled as passive when DPDP wants it actionable

All three docs treat recording as a one-way *announcement* ("yeh call record hoti hai" / "may be
recorded"). DPDP "informed consent" + revocability (in force for substance 13 May 2027, build now)
wants the recipient to be able to **act** on it, and India's one-party-consent posture makes a passive
announcement *legally workable* but **evidentiarily weak** for a regulated tenant.

Three concrete gaps:
1. **"record **hoti hai**" (present-continuous, "it gets recorded") sounds more surveillance-y than
   "iss call ko **quality ke liye save** kar rahe hain" (purpose-bound).** The purpose ("quality") must
   ride WITH the recording word every time, never bare "recorded."
2. **No consent-refusal branch in the opener spec.** If the prospect says "don't record me," the W2 doc
   only handles full opt-out, not record-refusal. Per-tenant policy needed: (a) regulated vertical →
   can't proceed without recording → graceful close; (b) default consumer → offer to continue, log the
   refusal, suppress storage. This is a **brain branch**, currently unspecified.
3. **Opt-out is described but not made STRUCTURAL.** "turn-loop must honor opt-out" is a soft sentence.
   Like the AI-token, opt-out detection ("number band karo / call mat karo / remove me") must be a
   **control-flow intent the caller cannot talk past**, with immediate stop + suppression-list write +
   timestamped log — not a prompt-hope. (Mirrors the H8/H12 structural-guarantee pattern in W18.)

**FIX (required):** (a) recording word always purpose-bound; (b) add the record-refusal brain branch
(per-tenant: hard-stop for regulated, log-and-continue for default); (c) opt-out = structural intent +
real-time suppression write, specified as control-flow not instruction.

---

## ISSUE 4 (MEDIUM) — per-mode correctness: SALES ok, SUPPORT/INBOUND over-disclose and break their own posture

The disclosure docs are written outbound-sales-first. Applied verbatim per-mode they misfire:

- **INBOUND (caller rings US):** `inbound-receptionist-brain-pack.md` §0/§3 correctly says inbound starts
  **WARM-to-HOT** and the brain must **serve first**. Front-loading "this is an automated call, recorded…"
  on someone who *chose to call you* is **hostile and unnecessary** — there is **no auto-dialer/robocall**
  on inbound (the TRAI auto-dialer-disclosure duty **does not even apply** — we didn't dial them). The
  disclosure docs don't carve this out. **Inbound needs only: brand identity + (if recording on)
  purpose-bound recording cue, woven after "how can I help."** No "automated call" announcement at all —
  it's a front desk answering, not a robocall.
- **SUPPORT / after-sales (outbound service call on 1600-series):** this is **transactional/service**,
  not promotional. The heavy promo-grade disclosure cadence is mismatched; a service call ("calling about
  your AC service booking") needs identity + purpose + recording cue, but the auto-dialer-promo framing is
  wrong register. Lighter touch, warmer, because there's an existing relationship (inferred consent valid
  for contract duration).
- **SALES outbound (140-series, cold/warm promo):** this is the **only** mode that needs the full
  promo disclosure (auto-dialer purpose + recording + identity). The docs' default is correct *here only*.

**FIX (required):** The disclosure spec must be **per-mode (channel-aware)**, keyed off the
`channel`/`vertical` config the W26 doc already defines (`disclosure_tier`, `channel`). Specify three
opener profiles:
- **outbound-sales** → full (identity + soft automated/purpose + recording cue) — current default.
- **outbound-service/support** → identity + purpose + recording cue, warmer, no promo-disclaimer cadence.
- **inbound** → identity + (recording cue if on); NO automated/robocall announcement (duty inapplicable).

This already aligns with the inbound pack's "vendor inbound script overrides" and "serve before sell" —
just make it explicit in the disclosure contract so W26 doesn't bolt the outbound line onto inbound.

---

## ISSUE 5 (MEDIUM) — "compliance layer overrides vendor script" is asserted but the precedence is ambiguous & vendor-script-compat is only half-checked

Both the W26 doc (§5 "emitted by the compliance/safety layer FIRST … cannot be overridden by a vendor
script") and the inbound pack (§3 "vendor inbound script overrides this opener verbatim-ish") are true
but **in tension**, and the resolution isn't stated:

- A DLT-registered vendor template **is itself the legal frame** — the regulated open lives *inside* the
  registered template (W2 doc §B.3, W26 doc §2.A.1). So "vendor script overrides the opener" and
  "compliance emits first" are only compatible if: **the disclosure tokens are a MANDATORY MERGE into the
  vendor script's opener, not a pre-pended separate line that the vendor script then overrides away.**
- Risk if unresolved: a vendor uploads a script whose opener says *"Hi, I'm Riya calling personally
  from {Brand}…"* (claims a human, no automated/recording cue). If "vendor script overrides," the brain
  emits an **illegal + false-human** opener. The W18 doc already flags vendor-script as the one
  injection-fenced source — but injection-fencing ≠ compliance-merge.

**FIX (required):** State the precedence explicitly: **disclosure tokens (identity + automated-cue-if-
required + recording-cue) are NON-NEGOTIABLE and MERGED into whatever opener fires — vendor script can
control tone/wording/order but CANNOT remove a required token or assert a human identity.** The
compliance layer **post-validates** the composed opener (vendor-script-or-default) and injects any
missing required token before TTS. That is the only way "vendor script wins on style" and "law wins on
substance" coexist. Add to W17 eval: a vendor script that claims-human / omits-recording must be
auto-corrected, not emitted.

**Vendor-script compatibility verdict:** ✅ compatible *once the merge-not-override rule above is
stated.* The tokens are short and tone-neutral enough to fold into any registered template's opener
(the W26 tiered tokens are designed as slot-ins). Without the rule, ❌ — a vendor script can produce an
illegal opener.

---

## THE CANONICAL OPENER (red-teamed, ship this — supersedes the three docs' separate versions)

**Default = founder-aligned, in-force-compliant, rapport-first. Token = soft "automated" only where the
mode requires it; NEVER the word "AI" in default tiers; recording always purpose-bound; reason before
process.**

### Outbound SALES (140-series, promo) — Tier 0 default
- **Hinglish:** *"Namaste {name} ji — main Riya, {Brand} se. Aapne jo {project/enquiry} mein interest
  dikhaya tha, usi ke baare mein ek minute baat karni thi. Call quality ke liye save kar rahe hain —
  do minute hain aapke paas?"*
  - Reason FIRST → identity → recording cue woven as purpose-bound aside → micro-yes. No "AI." No bare
    "record." "Automated" available as a per-tenant Tier-1 add if a cautious tenant wants belt-and-suspenders.
- **EN:** *"Hi {name}, this is Riya from {Brand} — about the {enquiry} you'd asked about. We save calls
  for quality. Do you have a quick minute?"*

### Outbound SUPPORT / service (1600-series) — warmer, relationship exists
- *"Hi {name}, Riya here from {Brand} — calling about your {service/order}. Quick check-in, and we keep
  these recorded for quality. That okay?"* — identity + purpose + purpose-bound recording, no promo cadence.

### INBOUND (they called us) — serve first, NO robocall announcement
- *"Thanks for calling {Brand} — how can I help you today?"* → after intent is known, if recording is on:
  *"…and just so you know, we keep calls recorded for quality."* — woven mid-call, never as a gate.
  No "automated" announcement (auto-dialer duty inapplicable; we didn't dial).

### "Are you AI / a robot / recording?" — truthful, brief, redirect (all modes)
- *"I'm {Brand}'s automated assistant — I can actually help you with {X} right now, shall I go ahead?"*
  - Honest ("automated assistant"), never the cold "I am an AI assistant," never a denial, pivots to value.
  - This is the ONE place the automated-cue is unavoidable, and it's reactive (only if asked) so it costs
    no rapport on the 95% of calls where it's never raised. Matches the identity-confirm pack §3.

### Tier 2 (DORMANT, per-tenant/jurisdiction toggle) — explicit "AI", flip-on-the-day-it's-law
- Keep `W26-INDIA-AI-VOICE-DISCLOSURE-LAW.md` Tier 2 as the config-flag escape hatch for when TRAI's
  proposed AI-mandate is notified, or for a US/EU tenant. **Config change, not code change.** Default OFF.

---

## STRUCTURAL HARD-RULES FOR W2 (not prompt-hope — control-flow, like H8/H12)

1. **Block-list (hard):** never generate "I am an AI assistant / main ek AI hoon / I'm a bot / virtual
   assistant" in any default tier. Remove the current firing at `agent.py:218` / `prompt.py:358` — it is
   neither required by in-force law nor wanted.
2. **Required-token merge:** identity always present; recording-cue present (purpose-bound) when recording
   on; automated-cue present only where mode+tier require. Composed opener (vendor-script-or-default) is
   **post-validated**; missing required token is injected before TTS; a human-claiming opener is corrected.
3. **Opt-out = structural intent** ("don't call / number band karo / remove me") → immediate stop +
   suppression write + timestamped log. Cannot be talked past.
4. **Record-refusal branch:** per-tenant — regulated vertical = graceful close; default = log refusal +
   continue + suppress storage.
5. **Mode/channel-aware:** outbound-sales / outbound-service / inbound select different opener profiles
   off the existing `channel`/`vertical`/`disclosure_tier` config; never bolt the outbound promo line
   onto inbound.
6. **Language-mirrored** (Hinglish default, casual — "important hai" not "mahatvapurn"); never truncate
   the disclosure/recording clause (the half-word bug must not eat a legally-required token).

---

## WHAT W17 EVAL MUST ADD (golden + red-team sets)

- Every outbound-promo open contains identity + recording-cue (purpose-bound); never the banned phrase.
- Inbound open does NOT announce "automated call" / does serve-first.
- A vendor script that (a) claims human or (b) omits recording → auto-corrected, not emitted.
- "Are you AI?" → "automated assistant" answer, never "I am an AI assistant," never a denial.
- Opt-out intent → stop + suppression + log, mid-sentence, within one turn.
- Record-refusal → correct per-tenant branch.
- Tier selection correct per channel/vertical/jurisdiction; Tier 2 only when toggled.

---

## RESIDUAL / FOUNDER-COUNSEL (record, don't block design)

1. **Sender-of-record** (Famit PE vs per-tenant PE) — unchanged open question from both docs; decides who
   eats ₹10L/suspension. Recommend per-tenant PE.
2. **Counsel sign-off** on the exact suspension clause AND on whether "automated/save-for-quality" without
   "AI" is acceptable to the registered-entity identity + auto-dialer-purpose duty before high-volume.
   (The "15-day" figure is **unverified** in primary sources per W26 doc §7 — real mechanism is
   complaint-triggered suspension on ≥5 unique complaints/10 days + up-to-2-yr blacklist. Don't cite "15
   days" to a regulator.)
3. **The day TRAI's AI-disclosure amendment is notified** → flip Tier 2 on by config; no rebuild. Monitor.

---

## SHIP DECISION

**SHIP** the resolution **with Issues 1–5 fixed**: one canonical tiered opener (W26 doc's model wins),
`INDIA-TELECOM-AI-DISCLOSURE-LAW.md` §5 wording superseded (its "AI voice assistant" default is
wrong on both axes), reason-before-process sequencing, purpose-bound + branchable recording consent,
per-mode opener profiles, and the merge-not-override vendor-script precedence — all as structural
control-flow, not prompt instructions. The legal core (no in-force "must say AI") is sound and
web-re-verified. A real prospect would NOT hang up on the canonical openers above; they WOULD on the
W2-doc's process-first cram and on the §5 "AI voice assistant" line.
