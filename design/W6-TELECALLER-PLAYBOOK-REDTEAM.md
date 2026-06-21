# W6 Telecaller Playbook — ETHICS + COMPLIANCE RED-TEAM

**Status:** RED-TEAM review (DOC-ONLY; no code, no box mutation). Reviewer: Opus adversarial pass.
**Date:** 2026-06-18.
**Target:** `design/W6-TELECALLER-PLAYBOOK.md` + its 5 most ethics-load-bearing referenced packs
(`brain-ethical-urgency-scarcity.md`, `voice-brain-push-without-pushy.md`,
`voice-brain-identity-confirm-reason-permission.md`, `brain-objection-not-interested-callme-later.md`).
**Verdict:** **DO NOT SHIP AS-IS.** The persuasion content is largely ethical and well-built, but **one
foundational law (AI non-disclosure) is squarely illegal under current Indian law** and must be reframed
before this becomes brain-pack behavior. 1 BLOCKER, 4 MAJOR, 3 MINOR. Fixes below are concrete and keep
the founder's "real human telecaller" intent intact within the law.

---

## REGULATORY GROUND TRUTH (verified 2026-06-18, not from memory)

- **TRAI TCCCPR Second Amendment, 12 Feb 2025:** AI/automated commercial calls must **disclose their
  automated nature UP FRONT** (industry guidance: within the **first ~15 seconds**), run on **140-series**
  (promotional) / **160-series** (transactional, regulated entities only) numbers, honor **10 AM–7 PM**
  promotional calling hours, scrub **DND**, offer an **opt-out within the first ~30s** ("press 9 to stop"),
  process opt-outs in **24–48h**. Penalties: 15-day outgoing suspension (first offense) → 1-year
  disconnection + blacklist (repeat); per-violation fines ₹1,000–₹1,50,000; **3 complaints → number
  disconnected.**
- **DPDP Act 2023:** outbound marketing/collection needs **prior consent**; a **recording + data-processing
  notice** at call start; purpose limitation; erasure rights. Penalties up to ₹250 crore.
- **TRAI AI/synthetic-voice consultation (in progress):** trending toward an explicit **mandatory
  AI-disclosure at the start of every commercial call** — i.e. the direction of law is the *opposite* of
  Law 1 as written.
- Sector overlays where the campaign is BFSI/insurance/lending: **RBI Fair Practices Code, IRDAI** norms add
  their own scripted disclosures.

Sources: TRAI Regulation 12-02-2025 (gazette PDF) · TRAI PR No.11/2025 · Securiti TCCCPR summary ·
qcall.ai / caller.digital / autointerviewai / ondial.ai 2026 compliance guides (URLs at end).

---

## BLOCKER — B1. Law 1 "never self-label as AI; disclose only on direct ask" is ILLEGAL in India

**Where:** Playbook §0 Law 1; §A6 ("Disclose AI only on direct ask"); §B branch "is this AI?";
`identity-confirm` pack §1.10 + §3 ("NEVER say 'I'm an AI assistant' unprompted") + §5 (lists unprompted
AI disclosure as a ❌ "what not to do"); echoed in `push-without-pushy` and `not-interested` packs
("Never identify as 'an AI assistant'").

**The problem:** The playbook's hardest, most-repeated rule is "introduce as a named human, NEVER volunteer
that you're AI, answer truthfully only if *directly asked*." Under the **Feb 2025 TCCCPR amendment + DPDP**,
an automated/AI commercial call must **affirmatively disclose its automated nature up front**, on every call,
*without* waiting to be asked. "Trying to pass AI off as a live agent" is explicitly called out as a
**deceptive trade practice**. So Law 1 doesn't just risk a fine — it is the exact behavior the regulator
names as the violation, and it's baked in as a guardrail "a campaign cannot accidentally flip on." This also
exposes the founder personally (number disconnection, blacklist) and torches the product's defensibility.

It is *also* an ethics problem independent of law: impersonating a human ("Main Riya, Shapoorji se" with the
identity guardrail forcing the human frame) is identity misrepresentation. Persuasion built on a false
premise about *who is speaking* taints every downstream technique, however clean those techniques are.

**The fix (reframe, don't delete — keeps the founder's intent legal):**
1. **Replace "never self-label / disclose only on ask" with "disclose the assisted/automated nature up
   front, briefly, in ONE warm line, then move to the reason."** This is fully compatible with sounding
   human and warm — the win is the disclosure being *graceful and brief*, not *absent*. A named persona is
   fine; **claiming to be a human telecaller is not.** e.g. "Hi, I'm Riya, the virtual assistant for
   Shapoorji — calling about your Hadapsar enquiry." One line, downward inflection, then straight to value.
   It costs ~1.5 seconds and removes the entire legal/ethical fault.
2. **Make disclosure a hard, campaign-uncloseable guardrail** — but in the *opposite direction* to the
   current one. The thing a campaign must not be able to flip off is the **disclosure**, not the human-frame.
3. **Keep the "answer truthfully if asked" branch** — but it's now a backstop, not the primary policy.
4. **Founder framing for the doc:** keep "behave like the best human telecaller" as the *quality/behavior*
   bar (warmth, listening, pacing, objection skill) — that is 100% legal and is the actual moat. Decouple it
   from "pretend to BE a human," which is the illegal part. The product is "an AI as good as your best
   telecaller," not "an AI pretending to be a telecaller." That reframe loses nothing the founder wants.
5. **Add the adjacent mandated disclosures** the playbook omits (see B2/B3) so the opener is compliant as a
   unit.

> NOTE for the founder (he is non-technical, will not know this): this is the single change that can save
> the whole product from being shut off at the carrier level. It is not optional and not a "nice to have."
> The behavior he loves (human-quality conversation) survives intact; only the *lie about being human* is
> removed.

---

## MAJOR ISSUES

### M1. No call-recording / data-processing notice in the opener (DPDP)
**Where:** Playbook §B opener; §A6 mentions "disclose AI only on direct ask" but no recording notice;
`identity-confirm` §1.11 treats the recorded-line disclosure as **conditional** ("if the campaign flags
it", "regulated sectors"). DPDP makes the recording + data-processing notice **baseline for outbound
marketing/collection**, not a sector-only add-on.
**Fix:** Add a standing universal behavior: **one short recording/data notice near the top of every call**
("this call is recorded; your details are handled per our privacy policy"), folded into the opener so it
doesn't eat the warmth. Make it default-ON, campaign-suppressible only where a lawful basis genuinely
removes it (rare). Pair with B1's AI disclosure as a single 2-line compliant opener.

### M2. No opt-out / DND mechanics in the persuasion flow
**Where:** Playbook §A6 ("DND/opt-out → immediate polite acknowledgment ... log and stop") is the *only*
mention; the opener framework (§B) and the persuasion packs never surface a **proactive opt-out path**.
TRAI requires a clear opt-out offered **within the first ~30s** of a promotional call ("press 9 to stop"),
processed in 24–48h, and synced to DND.
**Fix:** (a) Brain behavior: when the lead signals "stop / don't call / DND" → acknowledge once, stop
instantly, **no objection-handling, no callback-scheduling, no graceful-exit micro-ask** (the
`not-interested` pack's "ask permission to send ONE WhatsApp" graceful-exit must be **suppressed** on a true
opt-out — see M3). (b) Platform behavior (flag for build wave, not brain text): proactive opt-out offer +
24–48h suppression sync + DND scrub before dial + 140-series + 10 AM–7 PM window for promotional. Note these
in the W2 handoff as *infra preconditions* so brain behavior isn't asked to carry what telephony must.

### M3. Graceful-exit "one more WhatsApp" micro-ask can override a refusal/opt-out
**Where:** `not-interested` pack §4: "A graceful exit is also a *micro-commitment opportunity*: ask for
permission to send ONE WhatsApp" — applied *after* "'No' twice = stop." Also §2.F turns "send me info" into
"send it AND anchor a step / book a callback."
**The problem:** After a genuine refusal — and *especially* after a DND/opt-out — squeezing one more
consent-seeking ask is exactly the "dark pattern / persistence → complaint" behavior TRAI penalizes
(3 complaints = disconnection). It also undermines the pack's own good "No twice = stop" rule.
**Fix:** Hard-gate the graceful-exit micro-ask: it is allowed ONLY on a *soft* brush-off where the lead has
**not** expressed an unwillingness to be contacted, and **never** after (a) an explicit "don't contact me",
(b) a DND/opt-out invocation, or (c) a second hard no. On those, the only legal move is clean stop +
suppression. Make this an explicit branch in the brain, not a footnote.

### M4. "Confidence without disclosure" + persona names compound the impersonation risk
**Where:** `push-without-pushy` §0 "calm certainty," the persona "Riya/Karan/Neha from {company}," and the
returning-lead **pattern-interrupt** opener ("Hey Rajesh, how've you been?") which manufactures a *prior
human relationship* the AI never had.
**The problem:** A warm human persona + "how've you been?" + no AI disclosure = a deliberately constructed
false impression that a *person* who *knows you* is calling. Each technique is individually fine; stacked
without disclosure they cross from persuasion into deception.
**Fix:** With B1's up-front disclosure in place, these become legal *and* still warm. Keep the persona and
the pattern-interrupt — but they now sit *after* a one-line "virtual assistant for {company}" disclosure, so
"how've you been?" reads as a friendly assistant continuing a known thread (true — there *is* call history),
not a human faking intimacy. Add a brain rule: pattern-interrupt is allowed only on a genuinely *returning*
lead with real prior contact (the pack already says this for the "fake familiarity" reason — extend it to
the legal reason too).

---

## MINOR / TIGHTENING

### N1. Urgency/scarcity pack is clean — keep it, and cite its honesty gate from the playbook
The `brain-ethical-urgency-scarcity.md` pack is genuinely well-built: a 5-check honesty gate, explicit
"never fabricate a count/date," cooldown, "no urgency on a cold lead," and an India/DPDP/DND awareness
section. **No false-scarcity, no fake-discount, no fabricated-demand behavior is endorsed anywhere** — the
anti-patterns list forbids exactly those. **Fix (tightening only):** the *playbook* §A6/§D reference urgency
loosely ("ethical urgency only"); promote the pack's **5-check honesty gate** into the playbook §0 laws (or
§A6) so the gate is impossible to miss when W2 compiles behavior, rather than living only in a sub-pack.

### N2. "Defer discounts/concessions to the human" is good — make it a hard never, not a soft default
**Where:** Playbook §A6, §D.4 ("defer concessions to the human"). It's currently phrased as a default.
**Fix:** State it as an absolute: the AI must **never invent, imply, or promise** a discount, price,
waiver, freebie, rate, possession date, legal/RERA/policy assurance, or guarantee not present in campaign
data — those are deferred to a human, full stop. (Prevents both an ethics problem *and* a mis-selling/legal
problem in BFSI/RERA contexts.) The packs already lean this way; make it a named law.

### N3. "Pressuring vulnerable people" is unaddressed — add a vulnerability guardrail
**Where:** Nothing in the playbook or packs addresses a distressed/elderly/confused/financially-vulnerable
contact, or a clearly-pressured "yes." The push-intensity calibration scales on lead temperature, not on
vulnerability.
**Fix:** Add a universal behavior: if the contact signals confusion, distress, age/comprehension difficulty,
or financial vulnerability (esp. collections/renewal/insurance) → **drop all push, slow down, do not close,
offer a human callback.** No urgency, no assumptive close, no micro-commitment ladder on a vulnerable
contact. Cheap to add, removes the worst-case ethical headline.

---

## WHAT IS ALREADY CLEAN (do not "fix")

- **No false scarcity / fake discounts / fabricated demand** — explicitly forbidden across the urgency pack
  and push pack (hard "never" lists). 
- **Push intensity is capped** ("No twice = stop," "never a third ask," ladder-down) — this is *more*
  conservative than typical telecaller behavior. Good.
- **Honest cadence / anti-spam** (2–3 voice retries, WhatsApp carries light touches, India 4–5 PM default) —
  consistent with TRAI's anti-spam intent.
- **Language/naturalness rules** (casual Hinglish, no truncation) — quality, not ethics; fine.
- **DND "acknowledge and stop, never argue"** is present (just needs the M2/M3 hardening so nothing
  *else* in the flow can override it).

---

## SHIP DECISION

**NOT SHIP as written.** Ship-able after: **B1 reframed (mandatory up-front AI disclosure, kill the
human-impersonation guardrail), M1–M4 added/hardened.** N1–N3 are strongly recommended and cheap. None of
these weaken the founder's "human-quality telecaller" goal — they relocate the product from "AI pretending to
be human" (illegal, deceptive) to "disclosed AI that talks as well as your best human telecaller" (legal, and
the actual moat). Hand the M1/M2 *infra* items (140-series, hours, DND scrub, opt-out sync) to the build wave
as preconditions; the rest are brain-behavior edits to this doc before W2 compiles it.

---

## SOURCES (verified 2026-06-18)
- TRAI TCCCPR amendment regulation, 12 Feb 2025 (gazette): https://www.trai.gov.in/sites/default/files/2025-02/Regulation_12022025.pdf
- TRAI Press Release No. 11/2025: https://trai.gov.in/sites/default/files/2025-02/PR_No.11of2025.pdf
- Securiti — India spam rules / TCCCPR amendment takeaways: https://securiti.ai/india-spam-rules-trai-latest-amendment/
- qcall.ai — TRAI 2026 AI-calling compliance (15s disclosure, 140/160, opt-out): https://qcall.ai/trai-updates-for-ai-calling
- caller.digital — Voice AI India regulatory map 2026 (DPDP/TRAI/RBI/IRDAI/RERA): https://www.caller.digital/blog/voice-ai-india-regulatory-map-2026
- autointerviewai — AI calling DPDP/TRAI/DLT compliance 2026 (deceptive-practice if AI not disclosed): https://www.autointerviewai.com/blog/ai-calling-india-dpdp-trai-dlt-compliance-complete-guide-2026
- ondial.ai — AI calling legality / TRAI rules & consent: https://www.ondial.ai/blog/ai-calling-legal-india-trai-rules-consent
