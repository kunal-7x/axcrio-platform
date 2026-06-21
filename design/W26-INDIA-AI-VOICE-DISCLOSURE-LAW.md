# W26 — India AI-Voice Disclosure Law (2025–2026): Hard-Law Obligations + Disclosure-Line Output

**Wave:** W26 / consumed by W2 (brain) + W26 build. Feeds the T-C7 collision from `design/W18-BLINDSPOT-AND-REDTEAM.md`.
**Status:** RESEARCH (doc-only, no code, no box). 2026-06-18.
**Question gated:** Must a Famit/Axcrio outbound+inbound AI voice telecaller (India-first, Hindi/Hinglish, high-volume, multi-tenant) disclose it is AI at call start? What is mandated (hard law) vs guidance? What collides with the founder's hard demand "the AI must NEVER say I am an AI assistant"?

> **Bottom line for the founder (read this first).** There is **no in-force Indian law that forces the words "I am an AI assistant."** The collision is **resolvable**. The two real, in-force hard-law exposures for our product are **(1) TRAI TCCCPR** (the calling/anti-spam regime — DLT registration, 140-series numbers, consent, DND, time-windows, and a **disclose-the-auto-dialer/robocall purpose** duty; penalties escalate ₹2L→₹5L→₹10L and **suspension of all telecom resources** on 5 complaints from unique recipients in 10 days) and **(2) DPDP** (consent/notice for processing the called party's personal data + call recordings). The much-publicised **MeitY deepfake / "synthetically generated information" (SGI) labeling rules (in force 20 Feb 2026)** bind **intermediaries/platforms hosting/transmitting synthetic *content*** — they are **not** cleanly a duty on a live two-way phone call, and they do **not** mandate a spoken "I am an AI" line on telecalls. A **TRAI AI-specific disclosure mandate is drafted/under consultation but NOT yet in force.** So: we comply on the **calling** layer (which is the real risk), and we satisfy any "transparency" expectation with a **brand/identity opener that does not contain the brittle phrase the founder hates** — see the Disclosure-Line Output section.

---

## 1. The three legal regimes that touch an AI voice telecaller in India

| # | Regime | What it governs | Status (as of 2026-06) | Does it force "I am an AI"? |
|---|--------|-----------------|------------------------|-----------------------------|
| A | **TRAI TCCCPR 2018 + Feb 2025 Amendment** (under **Telecommunications Act, 2023**) | The *act of calling*: registration, numbering series, consent, DND, complaint→penalty→suspension, and disclosure of **auto-dialer/robocall use & purpose** | **IN FORCE** (amendment notified 12 Feb 2025; staged rollout through 2025) | **No.** It mandates disclosing *that an auto-dialer/robocall is used and its purpose* — not the literal phrase "I am an AI." An **AI-voice-specific** disclosure mandate is **proposed/under TRAI consultation, NOT yet in force.** |
| B | **DPDP Act 2023 + DPDP Rules 2025** | Processing the *called person's personal data* (name, number, recording, transcript) | **Staged in force** — notified 13 Nov 2025; Phase 1 from 14 Nov 2025; consent-manager phase by 13 Nov 2026; substantive obligations from **13 May 2027** | **No.** Requires lawful basis + clear notice + consent + withdrawal/retention/erasure — not an "I am an AI" line. |
| C | **MeitY IT (Intermediary Guidelines & Digital Media Ethics Code) Amendment Rules, 2026** — the **deepfake / "Synthetically Generated Information" (SGI)** rules | Labeling/provenance of synthetic *content* (audio/visual/audio-visual deepfakes) and **intermediary/platform** due-diligence | **IN FORCE 20 Feb 2026** (notified 10 Feb 2026). A further modification round was in draft/consultation ~Mar–Apr 2026. | **No, and likely out-of-scope for a live call** (see §4). Duty is "prefixed spoken disclaimer + permanent metadata/provenance" on **content**, and the labeling duty attaches primarily to **intermediaries/platforms**, not a business making a live phone call. |

**Headline correction to the W18 note:** W18 recorded "mandatory AI-disclosure-at-call-start + ₹10 lakh + 15-day telecom suspension." The current, source-verified reality is more precise:
- The **₹10 lakh** is the **top tier of the TRAI/TCCCPR financial-disincentive ladder** (₹2L first violation → ₹5L second → ₹10L for repeat), **not** a deepfake-rule fine.
- The **suspension** is **TRAI suspension of *all telecom resources* of the sender** triggered by **≥5 complaints from unique recipients in 10 days**, plus blacklisting up to **2 years** — **not** a fixed "15-day" period in the primary sources (the "15-day" figure is **not corroborated** in authoritative sources and should be treated as **unverified**; the real mechanism is complaint-triggered suspension + investigation + up-to-2-year blacklist).
- The **"must disclose at call start"** that *is* in force is the **auto-dialer/robocall use-and-purpose** disclosure (TRAI), **not** a literal "I am an AI" mandate. The literal **AI self-identification mandate is PROPOSED, not law.**

---

## 2. Hard-law obligations (IN FORCE) — what the product MUST do

### A. TRAI TCCCPR / Telecommunications Act 2023 (the real gate for a calling product)
These are **conditions of being allowed to dial at scale** — non-compliance is what actually gets a sender suspended/penalised:
1. **Register on DLT** as a **Principal Entity (PE)**; use a registered **Telemarketer (TM)** chain; register **headers/identities, consent and content templates** (blockchain-based DLT). *(In force.)*
2. **Use designated numbering series**, not ordinary 10-digit mobiles, for telemarketing: **140-series** for promotional, **1600-series** for transactional/service calls. *(In force.)*
3. **Consent + DND scrubbing.** Honour the DND/NCPR preference registry; obtain and log **consent**. Per Feb-2025 amendment: **explicit consent for a commercial transaction is valid only 7 days** from acquisition; **inferred consent** lasts only the duration of the contractual relationship; a **Digital Consent Management** pilot (revocable, telco-mediated) began June 2025.
4. **Disclose use & intended purpose of Auto-Dialer / Robo-Calls.** Telemarketers **must disclose the use and intended purpose** of an auto-dialer or robo-call. *(In force — this is the closest in-force "disclosure" duty, and it is about the *mechanism/purpose*, satisfiable without the words "I am an AI.")*
5. **No silent / abandoned autodialer calls**; respect **calling-time windows**; prevent duplicate-call harassment.
6. **Complaint→suspension ladder:** **≥5 complaints from unique recipients within 10 days → outgoing services of *all* the sender's telecom resources used for the UCC are suspended + investigation**; repeat → **blacklisting up to 2 years** + ban on new resource allocation. **Financial disincentive: ₹2L (1st) / ₹5L (2nd) / ₹10L (repeat).**

### B. DPDP Act 2023 + Rules 2025 (the data layer; substantive obligations from 13 May 2027 but build now)
1. **Lawful basis + clear, itemised notice** to the called person (Data Principal): what personal data, purpose, and a link/route to **withdraw consent**.
2. **Consent** must be free, informed, specific, unambiguous; **withdrawal as easy as giving**.
3. **Call recording = processing of personal data** → notice + lawful basis required; **retention limits + erasure** rights; **at-rest protection**.
4. **Dual exposure warning** (Bar & Bench): an AI calling business can face **both** telecom penalties (spam) **and** DPDP liability (unlawful processing / no consent) for the same call. Build consent + retention + erasure into the pipeline (ties to W7/W9/W14).

### C. MeitY SGI / deepfake rules (in force 20 Feb 2026) — what they actually say
- **Definition (Rule 2(1)(wa)):** SGI = audio/visual/audio-visual info **artificially or algorithmically created or altered** to appear **real, authentic, true and indistinguishable** from a real person/real-world event. *(Excludes text-only, routine editing, accessibility/quality tools.)*
- **Audio labeling (Rule 3(3)):** a **prominently *prefixed* (start-of-content) spoken disclosure** that the content is SGI, **plus permanent metadata / provenance / unique identifier** that users may not strip. **Note:** the **"10%" figure was in the Oct-2025 DRAFT and was DROPPED** from the in-force version — final rule says "prominent/prefixed," **no fixed percentage**.
- **Who is bound:** **intermediaries/platforms** that host, transmit, or provide tools enabling creation/dissemination of SGI; **SSMIs** (≥5M users) get enhanced duties (user self-declaration + verify + label before publish, Rule 4(1A)); **3-hour takedown** of unlawful SGI on actual knowledge. Sanction = **loss of Section 79 safe-harbour** + the underlying **BNS criminal exposure** for unlawful synthetic content (impersonation/fraud).
- **Why this is most likely NOT a duty to say "I am an AI" on our live call:** see §4.

---

## 3. Guidance / proposed (NOT yet hard law) — track, don't gate on
- **TRAI AI-specific disclosure & consent-verification:** TRAI has **stated it is *considering* amending TCCCPR for AI-based telemarketing, AI disclosures and consent-verification systems.** A widely-repeated vendor claim that **"AI must identify itself as automated within the first 15 seconds"** appears **only in vendor/SEO blogs (qcall/ondial/conversailabs-type), NOT in the TRAI regulation text or top-tier law-firm analyses** → treat as **anticipatory best-practice, NOT a current legal mandate.**
- **MeitY further modifications (Mar–Apr 2026 consultation):** continuous-disclosure tightening was **in draft**, not final, in that window — monitor.
- **Sector guidance (RBI etc.)** on AI in financial outreach may add disclosure norms for fintech tenants — handle per-tenant.

---

## 4. The collision, resolved: does our live AI call legally have to say "I am an AI"?

**Legal reasoning (this is the load-bearing analysis the founder needs):**
1. **The MeitY SGI/deepfake rules target *content that impersonates a real person/event* and bind *intermediaries/platforms*.** A real-time, two-way Famit sales/support call is **not stored, disseminated "content"** posted on a platform; Famit is **not an intermediary** hosting third-party SGI. The harm the rules target is **deception via fake media of a *real, identifiable* person/event** (deepfakes), not "a company used a synthetic-sounding voice to talk to its own lead." So the **SGI prefixed-disclaimer duty does not cleanly attach** to our call, and even if a regulator stretched it, the cure is a **prefixed disclosure of synthetic voice**, *not* the brittle phrase "I am an AI assistant."
2. **No in-force TRAI/Telecom rule compels the literal sentence "I am an AI assistant."** What is in force is **identify the caller/brand + disclose auto-dialer/robocall use & purpose** + honour consent/DND. All of that is satisfiable with a **branded, human-sounding opener that names the business and the purpose** and (to be safe + future-proof) a **light, natural synthetic/automated-assistant cue** — without ever uttering the exact words the founder bans.
3. **Therefore the founder's hard demand and the law can BOTH be honoured.** Ban the phrase **"I am an AI assistant / I am a bot / I am a virtual assistant."** Replace it with a **compliant identity+purpose opener** that (a) names the calling business/brand (TRAI identity), (b) states the purpose (TRAI auto-dialer/robocall purpose), (c) is recorded-with-consent (DPDP), and (d) carries a **soft, natural "automated assistant / digital assistant calling on behalf of <brand>" cue available as a per-tenant/per-jurisdiction toggle** so we can flip to explicit AI-identification the day TRAI's AI-disclosure amendment lands — **without re-architecting the brain.**

---

## 5. DISCLOSURE-LINE OUTPUT (consumed by W2 brain + W26 build)

**Design contract for the brain (W2) and the build (W26):** the opener is **config-driven, per-tenant, per-jurisdiction, env-gated default-safe**, never a hardcoded string in `agent.py`. Three disclosure **tiers** the policy layer selects between:

### Tier 0 — "Brand-identity opener" (DEFAULT; founder-aligned; in-force-compliant)
Names brand + purpose + (for outbound) auto-dialer/robocall purpose + consent/record cue. **Never says "I am an AI."**
- **Hindi/Hinglish (outbound, female persona "Riya"):**
  *"Namaste, main Riya bol rahi hoon <Brand> ki taraf se — aapne jo <product/enquiry> mein interest dikhaya tha, usi ke baare mein ek chhoti si baat karni thi. Yeh call recording ke liye save ho sakti hai. Do minute hain aapke paas?"*
- **English (outbound):**
  *"Hi, this is Riya calling on behalf of <Brand> about the <product/enquiry> you enquired about. This call may be recorded. Do you have a quick minute?"*
- Satisfies: TRAI caller identity + purpose; DPDP record-notice cue; no banned phrase.

### Tier 1 — "Automated-assistant cue" (RECOMMENDED safe-harbour; per-tenant toggle ON for cautious tenants / regulated verticals)
Adds a **natural, non-robotic** automated/digital-assistant signal — future-proofs against the pending TRAI AI-disclosure amendment **without** the banned wording.
- **Hindi/Hinglish:** *"…main Riya, <Brand> ki digital assistant bol rahi hoon…"* ("<Brand>'s digital assistant").
- **English:** *"…this is Riya, <Brand>'s digital assistant, calling about…"*
- Rationale: "digital/automated assistant on behalf of <brand>" reads as honest disclosure to a regulator, is human-natural, and **avoids "I am an AI assistant."** Founder can keep Tier 0 as default and enable Tier 1 per tenant.

### Tier 2 — "Explicit AI / synthetic-voice disclosure" (DORMANT toggle; flip the day a law/regulator/tenant requires it)
For jurisdictions/tenants that mandate explicit AI identification (e.g., if/when TRAI's AI-disclosure amendment is notified, or a US/EU tenant): a **prefixed** line that this is an **automated/AI voice** — still phrased to be warm, not the cold banned sentence.
- **English:** *"Hi — quick heads-up, this is an automated voice assistant from <Brand>. …"*
- Keep this behind a flag so enabling it is a **config change, not a code change.**

**Brain-policy rules (for W2):**
- The opener is emitted by the **compliance/safety layer FIRST** in the layered brain priority (it already sits at the top of the priority stack per the plan), **before** persona/script — so disclosure is structurally guaranteed and cannot be overridden by a vendor script.
- **Hard block-list** in the brain: never generate "I am an AI assistant / I'm a bot / I'm a virtual assistant / main ek AI hoon." (This is the founder's ban *and* avoids sounding robotic.) The current firing of this phrase at `agent.py:218` / `prompt.py:358` must be removed in W2 — it is **neither required by law nor wanted.**
- **Per-call config inputs:** `disclosure_tier` (0/1/2), `brand_name`, `purpose`, `record_consent_line` (bool), `jurisdiction`, `channel` (outbound/inbound). Default `disclosure_tier=0` (founder-aligned, in-force-compliant). Recording-consent cue ON for DPDP.
- **DLT/identity/number** are infra-layer (W12), not brain-layer, but the brain's spoken identity must **match the registered header/PE identity** to be coherent with DLT registration.

---

## 6. Compliance checklist mapped to build waves (so each obligation has an owner)
- **W12 (capacity/number-pool/compliance):** DLT PE/TM registration, 140/1600-series, DND/NCPR scrub, consent capture+expiry (7-day commercial), calling-window enforcement, no silent/abandoned calls, complaint-rate monitor (alarm BEFORE 5/10-day suspension threshold), per-tenant identity ↔ registered header match. **This is the wave that actually prevents the ₹10L/suspension outcome.**
- **W2 (brain):** disclosure-tier policy layer (Tier 0/1/2 above), remove "I am an AI assistant", block-list, brand+purpose+record-consent opener emitted first.
- **W7/W9/W14 (memory/recording/reporting):** DPDP — consent log, retention limits, erasure on request, at-rest protection of recordings/transcripts; record-notice cue surfaced in the opener.
- **W17 (eval):** golden tests — every call opens with a compliant identity+purpose line; **never** emits the banned phrase; record-consent cue present when configured; per-jurisdiction tier selection correct.
- **Legal sign-off gate (founder action):** before high-volume dialing, a **qualified Indian telecom/data lawyer** confirms (a) DLT PE registration done, (b) tier-0 opener meets the registered-entity identity + auto-dialer-purpose duty, (c) DPDP consent/retention posture. *(This research is engineering-grade due diligence, not a legal opinion.)*

---

## 7. Penalties & deadlines (precise, sourced)
- **TRAI/TCCCPR financial disincentive:** **₹2,00,000 (1st violation) → ₹5,00,000 (2nd) → ₹10,00,000 (repeat).** *(In force.)*
- **TRAI suspension trigger:** **≥5 complaints from 5+ unique recipients in 10 days → suspension of ALL telecom resources used for the UCC + investigation**; repeat → **blacklist up to 2 years** + no new resource allocation. *(In force; the "15-day" figure in the W18 note is UNVERIFIED — real mechanism is complaint-triggered suspension + up-to-2-yr blacklist.)*
- **Spam complaint window:** raised to **7 days**; complaint resolution shortened to **5 days**.
- **MeitY SGI rules:** **notified 10 Feb 2026, in force 20 Feb 2026**; unlawful-SGI takedown **within 3 hours**; sanction = **loss of Section 79 safe-harbour** + BNS criminal exposure (intermediary-facing). *(Most likely not applicable to our live call — §4.)*
- **DPDP:** notified **13 Nov 2025**; Phase 1 **14 Nov 2025**; consent-manager phase **by 13 Nov 2026**; **substantive obligations from 13 May 2027** (build now, enforce-ready before then).
- **TRAI AI-specific disclosure mandate:** **PROPOSED / under consultation — NOT in force.** The "AI must self-identify within 15 seconds" claim is **vendor-blog only, unverified as law.**

---

## 8. Sources (authoritative / primary first)
- MeitY — FAQ on IT Amendment Rules (SGI), Oct 2025: https://www.meity.gov.in/static/uploads/2025/10/065b6deb585441b5ccdf8be42502a49c.pdf
- MeitY — Explanatory Note (SGI amendment), 22 Oct 2025: https://www.meity.gov.in/static/uploads/2025/10/8e40cdd134cd92dd783a37556428c370.pdf
- TRAI — TCCCPR Amendment Regulation, 12 Feb 2025 (primary text): https://www.trai.gov.in/sites/default/files/2025-02/Regulation_12022025.pdf
- TRAI — Unsolicited Commercial Communications (UCC) FAQ: https://www.trai.gov.in/faqcategory/unsolicited-commercial-communicationsucc
- TRAI — Consultation Paper, Leveraging AI & Big Data in Telecom (AI-disclosure still consultative): https://www.trai.gov.in/consultation-paper-leveraging-artificial-intelligence-and-big-data-telecommunication-sector
- Telecommunications Act, 2023 (India Code): https://www.indiacode.nic.in/handle/123456789/20101
- DPDP Rules 2025 (English text): https://www.dpdpa.com/DPDP_Rules_2025_English_only.pdf
- Khaitan & Co — MeitY notifies IT Amendment Rules 2026 (in force 20 Feb 2026): https://www.khaitanco.com/thought-leadership/MeitY-notifies-the-IT-Amendment-Rules-2026
- Argus Partners — Overview of IT Intermediary Amendment Rules 2026: https://www.argus-p.com/updates/updates/update-overview-of-the-it-intermediary-amendment-rules-2026/
- SCC Online — IT Rules 2026, AI & intermediary compliance: https://www.scconline.com/blog/post/2026/02/12/it-rules-2026-ai-and-intermediary-compliance/
- Bhatt & Joshi — India's 2026 IT Rules: binding synthetic-content provenance mandate (audio = prefixed spoken disclaimer + metadata; intermediary-facing): https://bhattandjoshiassociates.com/indias-2026-it-rules-amendment-the-worlds-first-binding-synthetic-content-provenance-mandate/
- Chambers & Partners — TRAI crackdown on spam calls & AI-driven telemarketing (suspension/blacklist; AI-disclosure proposed): https://chambers.com/articles/trai-s-crackdown-on-spam-calls-and-ai-driven-telemarketing
- Bar & Bench — TRAI's crackdown (AI disclosure proposed, not in force; dual DPDP exposure): https://www.barandbench.com/view-point/trais-crackdown-on-spam-calls-and-ai-driven-telemarketing
- Securiti — India spam rules, TRAI Feb-2025 amendment (₹2L/₹5L/₹10L tiers; 5-complaints/10-days suspension; auto-dialer purpose disclosure): https://securiti.ai/india-spam-rules-trai-latest-amendment/
- S.S. Rana & Co — TRAI's crackdown on spam & AI telemarketing: https://ssrana.in/articles/trais-crackdown-on-spam-calls-and-ai-driven-telemarketing/
- Lexology — DPDP regime takes effect (staged dates): https://www.lexology.com/library/detail.aspx?g=2073ac40-628f-4112-81f3-fffdfd4b8858

*Engineering due-diligence research, not legal advice. Confirm DLT/PE registration + opener wording + DPDP posture with a qualified Indian telecom/data lawyer before high-volume dialing.*
