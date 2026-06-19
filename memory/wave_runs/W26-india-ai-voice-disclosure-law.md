# W26 — India AI-Voice Disclosure Law (RESEARCH, doc-only) — 2026-06-18

Deliverable: design/W26-INDIA-AI-VOICE-DISCLOSURE-LAW.md
Feeds: W2 (brain disclosure-line) + W26 build. Resolves T-C7 collision from W18.

## Phase: WEB RESEARCH + ADVERSARIAL VERIFY (done)
Verdict: NO in-force Indian law forces the literal phrase "I am an AI assistant".
Founder ban and the law are BOTH satisfiable. Three regimes:
- TRAI TCCCPR (Telecom Act 2023): the REAL gate for a calling product. IN FORCE.
  DLT/PE reg, 140/1600 series, consent (7-day commercial), DND, time-windows,
  disclose auto-dialer/robocall USE+PURPOSE (not "I am an AI"). Penalty ladder
  Rs2L->Rs5L->Rs10L; suspension of ALL telecom resources on >=5 complaints from
  unique recipients in 10 days + blacklist up to 2 yrs. AI-specific disclosure =
  PROPOSED (TRAI consultation), NOT in force. "15-sec AI ID" = vendor-blog only,
  UNVERIFIED as law.
- DPDP Act 2023 + Rules 2025: consent+notice+retention+erasure for called-party
  data + recordings. Staged; substantive obligations from 13 May 2027.
- MeitY SGI/deepfake rules (IT Amend Rules 2026): IN FORCE 20 Feb 2026. Audio =
  prefixed spoken disclaimer + permanent metadata/provenance (10% draft figure
  DROPPED). Binds INTERMEDIARIES/PLATFORMS hosting synthetic CONTENT, not a live
  2-way phone call -> most likely NOT a duty on our call; even if stretched, cure
  is "synthetic-voice prefix", NOT the banned phrase.

W18-note corrections: Rs10L = TRAI penalty top tier (not deepfake fine); "15-day
suspension" UNVERIFIED (real = complaint-triggered suspension + up-to-2yr blacklist);
"AI-disclosure-at-call-start" in force = auto-dialer PURPOSE disclosure, not "I am AI".

## DISCLOSURE-LINE OUTPUT (for W2)
3 config-driven tiers, per-tenant/jurisdiction, env-gated, default-safe; opener
emitted by compliance layer FIRST; hard block-list on "I am an AI assistant".
- Tier 0 (DEFAULT, founder-aligned): brand+purpose+record-consent opener
  ("Namaste, main Riya bol rahi hoon <Brand> ki taraf se..."). No "I am AI".
- Tier 1 (safe-harbour toggle): "<Brand> ki digital assistant" cue.
- Tier 2 (dormant toggle): explicit "automated voice assistant" line, flip when
  TRAI AI-disclosure amendment lands. Config change, not code change.
Remove the phrase firing at agent.py:218 / prompt.py:358 in W2.

Owners: W12=DLT/number/DND/consent/window/complaint-monitor (prevents Rs10L+
suspension); W2=disclosure tiers+block-list; W7/W9/W14=DPDP consent/retention/
erasure; W17=golden tests; founder=lawyer sign-off before high-volume.
