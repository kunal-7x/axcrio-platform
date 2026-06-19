# W6 RED-TEAM — Cross-Vertical Correctness (sales-bias contamination sweep)

**Date:** 2026-06-18 · DOC-ONLY (read files + write this ledger; no code, no box).
**Target:** `design/W6-TELECALLER-PLAYBOOK.md` + the 12 per-mode source-of-record packs it points to.
**Question:** Do support / after-sales / reminder / feedback / complaint / renewal / inbound modes inherit
sales-push behavior? Do real-estate specifics leak into other verticals?

**Verdict: NOT clean — SHIP-AFTER-FIXES.** The per-mode deep packs are excellent and well-firewalled.
The contamination risk lives in the *unifying* W6 playbook, which is structured sales-first and lets
sales behavior + real-estate specifics bleed downward by default. 6 concrete issues, all doc-level, all fixable.

---

## What is CLEAN (verified, no change needed)
- `brainpack-customer-support-mode.md` — §9 explicit no-sales-push firewall + §12 SALES-vs-SUPPORT contrast table. Clean.
- `brain-aftersales-feedback-nps.md` — §9 promotion firewall + TRAI service-call protection + review-gating compliance. Clean.
- `voice-mode-reminder-renewal-payment.md` — §0 "NO PITCH unless configured" hard boundary + RBI payment guardrails. Clean.
- `inbound-receptionist-brain-pack.md` — §0 "serve first, qualify second, sell last", aggression-repels-inbound. Clean.
- `brainpack-discovery-qualification.md` — explicitly cross-vertical (§ top + §8); RE examples flagged India/illustrative. Clean.
- These packs each have their own sentiment-fork / no-push / cross-vertical-adaptation section. The DEEP layer is correct.

## ISSUES (in the W6 playbook — the layer that unifies and feeds W2)

### ISSUE 1 (HIGH) — §B sales framework is the "default", inheritable by non-sales modes
§B "DEFAULT OUTBOUND-SALES CONVERSATION FRAMEWORK" (GREET→...→PITCH→OBJECTIONS→CLOSE) is positioned as
*the* fallback skeleton "when no vendor script is supplied." Non-sales modes (support/complaint/feedback)
must NOT fall back to a PITCH/OBJECTIONS/CLOSE arc. The §C blocks override per-mode, but §B's framing
("fallback skeleton when no vendor script exists") does not say "SALES mode only". A brain pack built
literally from §B as the default risks a support call inheriting pitch/close stages.
**FIX:** Rename §B to "DEFAULT **SALES** FRAMEWORK" and add one line: "This default applies ONLY when the
campaign mode is SALES (or unset+buying-intent). Support/complaint/feedback/reminder/after-sales modes use
their own §C spine and NEVER this PITCH→OBJECTIONS→CLOSE arc — there is no pitch/close to fall back to."

### ISSUE 2 (HIGH) — no top-level mode-router / mode-lock rule in the playbook
The playbook lists 9 modes but never states HOW the brain picks one, or that once locked, a mode's
guardrails (esp. no-push) cannot be overridden by sales universals. Support-mode pack has this internally
(§0 mode-detection); the unifying playbook does not. Without it, W2 may build the always-on layer (§0+§A)
as globally sales-leaning and let it bleed into every mode.
**FIX:** Add a "§0.5 MODE ROUTER + MODE-LOCK" section: detect mode from campaign objective + caller state
+ intent (not keywords); on lock, the mode's posture (push ON for sales; push OFF for support/complaint/
feedback/reminder/after-sales) is authoritative and a sales universal can never re-enable push in a no-push mode.

### ISSUE 3 (MED) — §A universals are written sales-tilted, presented as "apply in EVERY mode"
§A ("apply in EVERY mode") includes A2 "Brevity & altitude / earn the next 20 seconds", A3 "Discovery is
questions not pitches", and the §B-adjacent "push hard but never pushy" framing. These are SALES instincts.
A3's "don't dump the brochure" / "lead toward the close" energy is wrong for a complaint call (where the
posture is OWN, not advance). §A says it is universal — that is the contamination vector.
**FIX:** Split §A into A-TRULY-UNIVERSAL (tone/warmth A1, listen>talk A3-listening-half, language-mirror A4,
prosody A5, honesty A6, memory A7) vs A-SALES-ONLY (the "earn the next step / advance / momentum" instinct).
State that the sales-advance instinct is OFF in support/complaint/feedback/reminder/after-sales.

### ISSUE 4 (MED) — §D objection-handling "per-mode tilt" is one buried line; under-weighted
§D is framed as the universal objection stance, with only one closing line ("support/complaint 'objections'
are de-escalation, not rebuttal"). The whole §D scaffold (acknowledge→isolate→REFRAME→RE-CLOSE SOFTLY) is a
sales rebuttal loop. "Re-close softly" (§D step 5) is actively wrong in support/complaint/feedback — there
is nothing to re-close. A W2 build that lifts §D as the universal objection behavior contaminates non-sales modes.
**FIX:** Make §D explicitly SALES-scoped for the reframe/re-close loop. Add a parallel one-liner: "In support/
complaint/feedback/reminder, there are no objections to reframe — there are CONCERNS to OWN. Validate, capture,
route. Never counter, never re-close." (Mirror the support pack §12 row: "you *own*, not *counter*.")

### ISSUE 5 (MED) — real-estate specifics baked into the playbook beyond "illustrative"
Grep confirms RE specifics in W6 that are NOT clearly fenced as illustrative:
- L31: "premium **real-estate** persona = composed... festive-offer = brighter" — the two *named persona archetypes*
  are RE/retail; fine as examples but stated as the persona model. Add "(examples; persona comes from campaign)".
- L100 / L105 / L108-110 (C1 SALES): "site-visit", "Shapoorji Properties", "Hadapsar project", "Godrej",
  "Whitefield" — these are in C1-SALES (acceptable, flagged illustrative) BUT C1's Data-to-collect and
  Success-criteria lean RE ("site-visit/demo", "config/area/feature"). For a non-RE sales campaign (insurance,
  edtech, auto) "site-visit" is wrong vocabulary. Generalize C1 to "next concrete step (demo/visit/trial/quote)".
- L243 (§D price hook): "per-unit / EMI / **appreciation** / cost-of-inaction" — *appreciation* is a real-estate/
  investment-asset frame; meaningless for SaaS/edtech/insurance. Mark it [RE-example] not a universal price move.
- L247 / L270 (§D, §E): "price/**sq ft**, **possession date**", "**pachaasi lakh**", "**do BHK**" — RE-specific
  number examples presented inside otherwise-universal sections. Fence as [RE illustrative].
- L262 (§E): the "don't translate EMI/site visit/brochure/loan" list is RE/finance-tilted — fine as Hinglish
  guidance but note the un-translate principle is general; the *word list* is example-specific.
**FIX:** Every RE noun in a section labeled universal gets an explicit `[RE example — campaign fills the vertical]`
tag, and C1's collect/success fields get generalized vocabulary so a non-RE sales campaign reads correctly.

### ISSUE 6 (LOW) — §C5 REMINDER example reuses "site visit"; minor RE bleed into a cross-vertical mode
L165-166: the C5 REMINDER illustrative lines use "your site visit is tomorrow" — REMINDER is explicitly
cross-vertical (appt/payment/event) per the deep pack, so the sole example being a RE site-visit subtly
re-anchors it to RE. **FIX:** vary the C5 examples across verticals (a clinic appt, a payment due, a demo)
so the mode doesn't read as RE-default. (The deep reminder pack already does this; the playbook should mirror it.)

---

## NET
- Deep per-mode packs: PASS (firewalls present, cross-vertical sections present).
- Unifying W6 playbook: FAIL on structural sales-default inheritance (Issues 1-4) + RE-in-universal-sections
  leakage (Issues 5-6). All are doc-edits to the playbook; no deep pack needs rewriting.
- The risk is real because W2 builds brain packs FROM this playbook: if §B/§A/§D are lifted as the "default/
  universal" layer, every non-sales mode inherits pitch/advance/reframe/re-close + RE vocabulary by default.
