# Telephony Independence Megaplan — Research Log

## Phase: RESEARCH [multitrunk-concurrency-arch]
**Date:** 2026-06-14
**Scope:** Production architecture for a MULTI-TRUNK, multi-number dialer with real concurrency on LiveKit-SIP OSS. Hard constraints surfaced honestly. Sourced.

---

## PART 1 — LiveKit-SIP: What It Actually Does and Does NOT Do

### How SIP trunks work in LiveKit-SIP OSS

LiveKit-SIP (`github.com/livekit/sip`) is a standalone SIP-to-WebRTC bridge that connects to a LiveKit server. It exposes two objects via the LiveKit API: **SIPInboundTrunk** and **SIPOutboundTrunk**.

**Trunk configuration (each trunk is an API object):**
- `address`: SIP provider endpoint (e.g. `sip.telnyx.com`)
- `numbers`: array of DIDs associated with this trunk (can be `["*"]` for wildcard)
- `auth_username` / `auth_password`: authentication
- `destination_country`: region pinning
- No documented hard cap on number of trunks registered

**Inbound Dispatch Rules (the routing layer):**
- Each dispatch rule has a `trunk_ids` field — if set, the rule fires only when a call arrives on those specific trunks. If empty, it matches all trunks.
- Three routing strategies: Individual (unique room per caller), Direct (all to one room), Callee (room assigned by called number)
- `attributes` and `metadata` on the rule carry tenant context downstream to agents
- DID-to-tenant routing: configure one dispatch rule per tenant DID set, filter by `trunk_ids` — this is the correct isolation mechanism

**Outbound call mechanics (per-call):**
- `CreateSIPParticipant` API takes `sip_trunk_id` explicitly per call
- Also accepts `sip_number` to specify which originating DID from the trunk to use
- NO automatic trunk pool selection, NO built-in round-robin, NO automatic failover
- Selection logic MUST live in the application layer (the dialer / caller.py)

**State and scaling:**
- SIP service + LiveKit server communicate over Redis; Redis holds SIP session state
- The SIP bridge is horizontally scalable: multiple instances behind a load balancer
- RTP port range defaults to 10000-20000 (~10,000 media flows per instance); configurable
- No documented hard cap on concurrent calls per deployment; practical limit is box resources

**What LiveKit-SIP does NOT provide out-of-the-box:**
- No trunk pool manager
- No weighted / round-robin outbound trunk selection
- No per-trunk channel-limit enforcement
- No automatic failover from trunk to trunk
- No number rotation or spam-protection logic
- No concurrent call counter per trunk

**Conclusion:** LiveKit-SIP provides primitives (trunk objects + dispatch rules + per-call trunk_id). All POOL LOGIC — channel counting, rotation, least-cost routing, failover — must be built in the application layer.

---

## PART 2 — SIP Trunk Channel Limits: The Hard Math

### What a "channel" is
One channel = one concurrent call, regardless of direction. A 10-channel trunk = max 10 simultaneous calls (in + out combined, unless provider separates them).

### Provider channel models
- Standard fixed SIP trunks: 20-100 concurrent channels per trunk (negotiated at provisioning)
- Elastic/cloud SIP (Twilio Elastic SIP, Telnyx, Bandwidth): unlimited concurrent channels; no seat licenses; pay-per-minute; capacity auto-scales
- Twilio Elastic SIP: 1 CPS (calls per second) default per trunk per region; self-service to 30 CPS; enterprise higher
- Most Indian SIP providers (Airtel Business, Tata Tele, Knowlarity): fixed channel count on standard trunks; elastic options available at enterprise tier

### Channel headroom rule
Plan for 20-30% headroom above expected peak. When all channels are busy, new calls receive SIP 486 Busy Here, queue at provider, or overflow to secondary trunk.

### Concurrent call math
```
Required channels = peak_concurrent_calls x 1.25 (25% headroom)
Bandwidth per call (G.711 ulaw) = ~80 kbps
Total bandwidth = required_channels x 80 kbps
```
Example: 50 concurrent calls = 63 channels provisioned, 4 Mbps bandwidth minimum.

### Multi-trunk pooling to beat single-trunk channel limits
If one trunk caps at 30 concurrent and you need 150: provision 5 trunks, register all in LiveKit, build a channel counter in the application layer. Before each outbound call: query which trunk has free capacity, pass that `sip_trunk_id`. This is the standard pattern.

---

## PART 3 — How Vapi / Bland / Retell / Twilio Handle Multi-Trunk + Concurrency

### Vapi
- Default: 10 concurrent call slots account-wide (soft limit, purchasable via Dashboard -> Settings -> Billing)
- BYO SIP trunk: one credential per trunk, DIDs linked to it
- Outbound number rotation: Vapi CLI has rotation flag to cycle a number pool
- Vapi's soft concurrency limit AND the SIP trunk's channel limit are both active ceilings; both must be satisfied
- No native trunk pool manager; application code handles multi-trunk selection
- Inbound: calls forward to `{did}@{credential_id}.sip.vapi.ai`

### Bland.ai
- Outbound-first; Pathways node-graph architecture claims 1,000+ concurrent calls
- BYO SIP: "custom SIP endpoint" — same one-credential model
- No published native trunk pool API; high concurrency is internal infrastructure

### Retell AI
- Managed architecture; concurrency handled internally
- BYO SIP trunk for enterprise; no published per-trunk pool management

### Twilio (the reference model)
- Elastic SIP Trunking: unlimited concurrent channels, no seat licenses, pay-per-minute
- 1 CPS default per trunk/region; adjustable to 30 CPS self-service, enterprise higher
- Per-call caller ID assignment in API
- Spam protection: SHAKEN/STIR via TrustHub, CNAM registration, Free Caller Registry
- Monitor `QueueTime` in API responses; exponential backoff on 429s

### The common pattern across all platforms
None expose a native trunk pool UI. High-concurrency dialers BUILD a pool manager in their application layer:
1. Register N trunks (or one elastic trunk)
2. Maintain Redis counter: {trunk_id: active_calls}
3. Pre-call: select trunk with lowest utilization / round-robin; verify active_calls < channel_limit
4. Increment on call start, decrement on call end (via webhook/event)
5. On channel-full: queue or select next trunk
6. On trunk failure (SIP 5xx / timeout): mark unhealthy, route to next

---

## PART 4 — GSM Gateway Hard Constraints (GoIP / Yeastar)

### Hardware concurrency (physical ceiling)
| Device | SIMs / concurrent calls |
|--------|------------------------|
| GoIP-1 | 1 |
| GoIP-4 | 4 |
| GoIP-8 | 8 |
| GoIP-16 | 16 |
| GoIP-32 | 32 |
| Yeastar TG series | 1-32 per unit |

Multiple units chain via SIM banks, but each SIM still = 1 call. 100 concurrent calls = 100 SIMs across multiple hardware units. Cost, power, space scale linearly.

### The SIM blacklisting problem (HARD, not a risk to manage)
Indian carriers (Airtel, Jio, Vi) actively detect and block SIM cards used for bulk calling via partnerships with anti-fraud vendors (GoAntiFraud, etc.). Detection signals:
- High call velocity per SIM
- Low answer rates
- Consecutive failed call bursts
- Abnormal accumulated call duration vs. normal subscriber behavior

GoIP devices include SIM protection features (duration limits, cool-down timers) to slow detection. In practice, SIM blocks happen quickly at any meaningful call volume. A personal SIM used for bulk auto-dialing WILL be banned — this is not a risk to mitigate; it is an inevitability at scale.

### Regulatory illegality (not just a risk — it is illegal)
- Using a personal 10-digit mobile SIM for telemarketing is ILLEGAL under TRAI TCCCPR 2018
- Only 140-series numbers are permitted for promotional calls; 160-series for transactional
- A GSM gateway with a consumer SIM cannot produce a 140-series Caller ID
- Even if it could, DLT registration, script registration, and AI disclosure requirements apply
- Carriers are mandated to disconnect numbers at first complaint; 2-year blacklist follows

**Verdict on GSM gateways for Famit India telemarketing:** NOT viable. Works for GSM termination arbitrage (international VoIP traffic, different legal context) or internal PBX. Cannot be used for TRAI-compliant outbound marketing at any scale.

---

## PART 5 — TRAI / DND Compliance for Auto-Dialers in India (2025)

### Mandatory number series (hard requirement)
- Promotional calls: 140-series (e.g. 1400XXXXXXX)
- Transactional / service calls: 160-series
- Any 10-digit mobile number used for telemarketing: carrier disconnects on first complaint, 2-year blacklist

### How to obtain 140-series SIP trunks
1. Register as Principal Entity (PE) on TRAI DLT platform via telecom provider
2. Register as Telemarketer (obtain Telemarketer ID)
3. Register all call scripts / voice templates on DLT BEFORE campaign launch
4. 140-series DIDs provisioned by the telecom provider
5. SIP-compatible vendors offering 140-series trunks: C-Zentrix, Knowlarity, Airtel Business, Tata Tele Business Services
6. These are standard SIP trunks; LiveKit-SIP connects to them identically to any other SIP provider

### DND scrubbing (mandatory, ongoing)
- Download / query NCPR (National Customer Preference Register) before every campaign batch
- Must scrub on rolling basis (minimum weekly; NCPR updates continuously)
- Calling a DND-registered number: Rs 2 lakh fine first offense, Rs 10 lakh repeat

### Call timing
- No promotional calls between 9 PM and 9 AM IST, even to non-DND numbers

### Auto-dialer / AI disclosure (February 2025 amendment, TCCCPR)
- Must disclose use of auto-dialer / robocall at the start of every call
- Must notify origin access provider of auto-dialer use in advance
- Pre-recorded messages: require prior consent from called party (effectively prohibits cold robo-calls)
- Live AI agent calls (real-time LLM): not yet explicitly regulated as robocalls; TRAI is "considering amendments for AI-driven telemarketing" — still under development as of mid-2026
- Safest interpretation: the AI agent should identify itself as automated at the call start

### Enforcement tightening (February 2025)
- Action timeframe: 30 days reduced to 5 days after complaint
- Complaint threshold: 10 complaints/7 days reduced to 5 complaints/10 days
- Fines on telecom operators (cascade to the sender): Rs 2L / Rs 5L / Rs 10L
- Unregistered telemarketing: carrier blocks ALL outgoing traffic immediately; no grace

### Practical registration path for Famit
1. Register PE + Telemarketer on DLT (via Airtel Business or Tata Tele)
2. Provision 140-series SIP trunk from that provider
3. Register each campaign's call script variant on DLT
4. Build NCPR scrub step into campaign launch flow (UI: block campaign start without scrub confirmation)
5. Enforce 9AM-9PM window in dialer
6. Agent opening line must identify as automated / AI call

---

## PART 6 — Target Production Architecture for Famit Trunk Registry

### System design (what needs to be built)

```
DB table: sip_trunks (per-tenant)
  trunk_id | provider | sip_address | auth_user | auth_pass
  numbers[] | channel_limit | weight | priority | region
  tenant_id | health_status | last_health_check

Redis keys:
  trunk:{trunk_id}:active_calls  (integer, atomic incr/decr)
  trunk:{trunk_id}:health        (healthy/degraded/dead, TTL 60s)

Pool Manager (application layer, caller.py):
  select_trunk(tenant_id, region) -> trunk_id, sip_number
    - filter by tenant + region
    - skip health=dead trunks
    - apply round-robin or weighted selection
    - verify active_calls < channel_limit
    - return trunk_id + next DID from numbers[] pool (rotated by index)

  on_call_start(trunk_id): INCR trunk:{trunk_id}:active_calls
  on_call_end(trunk_id): DECR trunk:{trunk_id}:active_calls (via webhook)

  health_check() [background task, every 30s]:
    - SIP OPTIONS ping to each trunk sip_address
    - mark healthy/degraded/dead

Failover:
  on SIP 5xx or timeout from CreateSIPParticipant:
    - mark trunk degraded in Redis (TTL 120s)
    - retry with next trunk from select_trunk()
    - if all trunks exhausted: queue call for retry (Hatchet)

Inbound DID-to-tenant routing (LiveKit dispatch rules):
  For each tenant DID set:
    SIPInboundTrunk {numbers: tenant_dids}
    SIPDispatchRule {trunk_ids: [trunk.id], metadata: {tenant_id: X, ...}}
  Agent reads metadata.tenant_id from job context -> all data scoped to tenant
```

### Number rotation strategy (anti-complaint distribution)
- Store numbers[] per trunk as an ordered array in DB
- Maintain Redis key `trunk:{trunk_id}:number_index` (atomic INCR % len(numbers))
- Each outbound call picks `numbers[index % len]` as sip_number
- This distributes call velocity per DID; reduces per-number complaint accumulation
- Does NOT bypass TRAI DND — NCPR scrub is mandatory regardless

### Concurrency example
- Need: 50 concurrent outbound calls for Famit (current scale)
- One Telnyx elastic trunk: unlimited concurrent, request 10 CPS (sufficient for campaigns)
- One 140-series Airtel trunk (for India compliance): negotiate 60 channels
- Register both in LiveKit as separate SIPOutboundTrunk objects
- Pool manager: prefer 140-series for India DIDs, fall back to Telnyx for international
- Redis counters track each trunk independently

### UI requirements (per founder's standing rule: every backend feature needs a frontend)
- Trunk registry page: list all trunks (status, active_calls, health, provider)
- Add/edit/delete trunk (sip_address, credentials, numbers[], channel_limit, weight)
- Per-tenant trunk assignment
- Number pool management: add/remove DIDs per trunk
- Health dashboard: real-time active_calls counter, health status per trunk
- Test call button: place a test call via selected trunk

---

## ADVERSARIAL VERIFY (3-vote spot check on key claims)

| Claim | V1 | V2 | V3 | Verdict |
|-------|----|----|----|----|
| LiveKit has no native trunk pool manager | docs.livekit.io (no pool API) | livekit/sip GitHub (no pool code) | CLI docs (only explicit trunk_id per call) | CONFIRMED |
| GoIP 32 = 32 concurrent calls | goantifraud.com product page | Wikipedia GoIP | Yeastar TG32 spec | CONFIRMED |
| TRAI requires 140-series for telemarketing | trai.gov.in + TCCCPR 2018 | Feb 2025 TCCCPR amendment | DoT PIB press release | CONFIRMED |
| Vapi default concurrency = 10 slots | docs.vapi.ai/calls/call-concurrency | Vapi community posts | Retell blog comparison | CONFIRMED |
| GSM SIM cards get banned for bulk dialing in India | carrier anti-fraud partnerships | TRAI ban on 10-digit marketing | VoIP-GSM termination industry guides | CONFIRMED |
| Twilio Elastic SIP = unlimited concurrent | Twilio docs/elastic-sip | Twilio blog launch post | Third-party guides (Callin.io) | CONFIRMED |
| 140-series SIP trunks are standard SIP compatible | C-Zentrix guide (explicit) | Knowlarity product listing | Airtel Business offering | CONFIRMED |

All 7 key claims: 3/3 confirmed. No claims killed.

---

## Phase: RESEARCH — BYO-Number / SIP+CPaaS Providers (Telnyx / Plivo / Twilio / Exotel / Knowlarity / Vobiz / DIDlogic / Bandwidth)

**Date:** 2026-06-14
**Scope:** Which providers let Famit own/port Indian numbers and use them as outbound caller ID on LiveKit, at what cost and with what hard constraints. Deep-sourced.

### Provider-by-Provider Findings

#### VOBIZ (current + primary)
- India local DID: YES — specializes in India; instant provisioning; 130+ countries
- DID cost: ~₹250–500/number/month (not officially published; standard India rate)
- Outbound per-min: **₹0.45/min** (standard voice); **₹0.65/min** (streaming/AI)
- BYO number porting IN: Not documented — likely no self-serve; they sell own DID inventory
- Concurrency: Elastic — no stated hard cap for outbound
- Multi-number: YES — `numbers[]` array in LiveKit trunk; app-level rotation needed
- LiveKit config: SIP domain `<unique>.sip.vobiz.ai`, credential auth (username+password), TCP transport required
- India compliance: TRAI-aware, INR billing, GST invoices; 1600-series available for transactional
- Verdict: **PRIMARY — keep as-is. Add more DIDs to pool. Build rotation in caller.py.**
- Sources: docs.vobiz.ai/integrations/livekit, vobiz.ai, indiahood.com/vobiz-secures-1-million

#### PLIVO (best documented alternative)
- India local DID: YES — local numbers across all Indian states
- DID cost: **₹250/month** per local number
- Outbound per-min (SIP trunk): **₹0.60/min** (local/mobile)
- Outbound per-min (Voice API/SIP SDK): ₹0.34/min (lower — different product)
- BYO number porting IN: **NO** — porting only for US & Canada; Indian numbers CANNOT be ported to Plivo
- Concurrency: **Unlimited** — no per-channel fee for SIP trunking, elastic
- India entity requirement: **HARD BLOCKER** — only India-registered businesses can rent Indian numbers. Certificate of Incorporation + GST certificate required. KYC 1 hour to 1 business day.
- LiveKit config: officially listed in LiveKit's provider docs; standard credential auth
- STIR/SHAKEN: Full A attestation
- Verdict: **Viable as second trunk IF Famit has India-registered entity (likely yes given GST).** No BYO porting.
- Sources: plivo.com/sip-trunking/pricing/in/, plivo.com/virtual-phone-numbers/pricing/in/, plivo.com/docs/numbers/number-porting

#### EXOTEL (India-native, currently Alpha vSIP)
- India local DID: YES — Exophone numbers, all India mobile/landline coverage
- Outbound per-min: ~**₹0.40/min** (PAYG click-to-call); plans from ₹9,999/month
- BYO number porting IN: **YES** — number porting supported for existing Indian numbers (unique among this list)
- Concurrency: 200 CPM default per trunk; higher on request
- India entity: YES, INR plans
- LiveKit compatibility: **ALPHA — unverified.** vSIP docs exist but community GitHub issues (#278, #425, #428) are open/unresolved. IP whitelist-only auth (NO SIP REGISTER) — LiveKit must connect from a static IP whitelisted by Exotel. SIP host: `pstn.in2.exotel.com:5070`. Media IPs: `182.76.143.61`, `122.15.8.184`.
- SLA: None — Alpha, not production-safe
- Verdict: **Future option — BYO porting is the key differentiator.** Wait for GA. Test when they announce production status.
- Sources: support.exotel.com vSIP guide, github.com/livekit/sip/issues/425, /428

#### TWILIO
- India local DID: **NO** — Indian local phone numbers not available on Twilio
- Outbound to India per-min: **$0.0456–$0.0659/min (~₹3.8–5.5/min)** — 5-8x more expensive than Vobiz
- Caller ID: Must use non-India number (foreign CLI) — reduces Indian answer rates significantly
- BYO porting: Indian numbers not ported; Verified Caller ID (own number as CLI) possible but not porting
- Concurrency: Unlimited elastic, 1 CPS default per trunk/region
- LiveKit config: officially documented; credential auth
- STIR/SHAKEN: Full A
- Verdict: **NOT recommended for India primary.** No Indian DID, expensive, foreign CLI hurts answer rates. Emergency international fallback only.
- Sources: twilio.com/en-us/sip-trunking/pricing/in, help.twilio.com (India numbers not available)

#### TELNYX
- India local DID: **NOT AVAILABLE** — India explicitly absent from Telnyx's global coverage for local numbers and local calling
- Outbound to India per-min: **$0.0497–$0.0666/min (~₹4.1–5.5/min)** — expensive; increased from $0.0473/$0.0632 in Sept 2025
- BYO porting: Number porting product exists but India not documented; contact numbering@telnyx.com
- Outbound guarantee for India: **"Outbound local calling NOT guaranteed for countries not on supported list"** — India is not on list
- Concurrency: Unlimited elastic
- LiveKit config: officially documented; SIP host `sip.telnyx.com`; credential + `X-Telnyx-Username` header required
- STIR/SHAKEN: Full A (owned carrier)
- Verdict: **NOT recommended for India.** No Indian DID, India not on supported list, expensive per-minute. Excellent for US/Europe outbound.
- Sources: support.telnyx.com/articles/6622229-pstn-local-calling (India absent), telnyx.com/pricing/elastic-sip, developers.telnyx.com LiveKit guide

#### KNOWLARITY
- India local DID: YES — India-native CPaaS
- Outbound per-min: ₹0.40/min (click-to-call on Unlimited Inbound plan)
- Plans: from ₹1,499/agent/month; annual contracts, quarterly advance — no monthly option
- BYO porting: Not documented for SIP trunk mode
- LiveKit compatibility: NO — closed proprietary API; no SIP trunk self-serve; not a developer CPaaS
- Verdict: **SKIP** — closed ecosystem, annual lock-in, no LiveKit SIP path.
- Sources: prospeo.io/s/knowlarity-pricing-reviews-pros-and-cons

#### BANDWIDTH.COM
- India coverage: **NOT AVAILABLE** — no India SIP trunking documented; US-first carrier
- Verdict: **SKIP** — not relevant for India.

#### DIDLOGIC (niche, AI-voice-native)
- India DID: Claims 130+ countries — India status unconfirmed; must contact sales
- Per-min: Not published for India; pay-per-DID + per-minute; no per-channel fee
- BYO porting: "Paperless LNP in 8 countries; manual porting in most others" — India manual porting possible but unconfirmed
- Concurrency: No per-channel fee — elastic
- LiveKit compatibility: Dedicated LiveKit integration page; sub-20ms added media latency claim; TCP/UDP/TLS supported; G.711 + G.722 codecs
- Verdict: **Investigate** — designed for AI voice stacks; no per-channel pricing matches Famit's model. Verify India DID availability before committing.
- Sources: didlogic.com/ai-voice/livekit/

### Provider Summary Table

| Provider | India DID | Outbound ₹/min | BYO Port IN | Concurrency | LiveKit | India Entity | Verdict |
|----------|-----------|---------------|-------------|-------------|---------|-------------|---------|
| **Vobiz** | YES | ₹0.45 | NO (prob) | Elastic | Native | NO (INR) | PRIMARY — working |
| **Plivo** | YES | ₹0.60 | NO (US/CA only) | Unlimited | Official | YES (COI+GST) | Best alt trunk |
| **Exotel** | YES | ~₹0.40 | YES (India) | 200 CPM | Alpha | YES | Future — wait GA |
| **Telnyx** | NO | ₹4.1–5.5 | Unknown | Unlimited | Official | NO | Skip for India |
| **Twilio** | NO | ₹3.8–5.5 | NO | Unlimited | Official | NO | Emergency fallback |
| **Knowlarity** | YES | ₹0.40 | Unknown | Enterprise | NO | YES | Skip |
| **Bandwidth** | NO | — | — | — | — | — | Skip |
| **DIDlogic** | Unconfirmed | Unknown | Manual/possible | Unlimited | Native | — | Investigate |

### Key Findings — Honest Constraints

1. **No CPaaS (Telnyx / Twilio) provides Indian local DIDs directly.** The India market has regulatory requirements (OSP/ILDO licensing) that exclude most US-headquartered carriers from selling Indian local DIDs self-serve. Vobiz and Plivo (via India entity + KYC) are the realistic paths.
2. **BYO porting of Indian numbers to a CPaaS is nearly impossible today.** Plivo: US/CA only. Telnyx: not documented. Exotel: YES — but Alpha, no SLA. There is no easy "port your Airtel business number to a cloud SIP trunk" path currently in India.
3. **Twilio/Telnyx are 5-8x more expensive to India** than Vobiz/Plivo, and deliver a foreign CLI that hurts answer rates.
4. **Plivo requires India-registered entity + GST + COI.** If Famit/Axcrio has this (likely yes), Plivo is a clean second trunk at ₹250/DID/month + ₹0.60/min.
5. **Exotel vSIP is the only India-native provider with BYO porting AND a SIP trunk API.** It is currently Alpha (no SLA, IP-whitelist-only auth complicates LiveKit integration). Check quarterly for GA status.
6. **Number rotation is app-level.** LiveKit picks the number you pass; build a round-robin pool in caller.py over `numbers[]` on the trunk.

### Recommended Phased Path

- **Now:** Add 2–3 more Vobiz DIDs to the pool. Build round-robin selection in caller.py. Zero new infra.
- **4 weeks:** Onboard Plivo as second trunk (KYC + COI + GST). Register via plivo.com/sip-trunking. Add to LiveKit as second `SIPOutboundTrunk`. Build pool manager (Redis counters) to route between trunks.
- **When Exotel vSIP exits Alpha:** Onboard as third trunk. This enables true BYO porting of existing business numbers.
- **Ongoing:** DLT registration + 140-series numbers for TRAI compliance on commercial campaigns. Every campaign must scrub NCPR before launch.

---

## SOURCES

1. https://docs.livekit.io/telephony/
2. https://docs.livekit.io/sip/dispatch-rule/
3. https://docs.livekit.io/telephony/making-calls/outbound-trunk/
4. https://github.com/livekit/sip
5. https://deepwiki.com/livekit/livekit-cli/9-sip-integration
6. https://docs.vapi.ai/calls/call-concurrency
7. https://docs.vapi.ai/advanced/sip/sip-trunk
8. https://www.retellai.com/blog/vapi-vs-bland
9. https://sipsymposium.com/guides/sip-trunking-for-ai-agents
10. https://flowroute.com/blog/how-many-calls-can-a-sip-trunk-handle-a-comprehensive-guide/
11. https://www.ipcomms.net/blog/sip-trunk-failover/
12. https://www.twilio.com/en-us/blog/high-volume-voice-considerations
13. https://goantifraud.com/goip-equipment/7-goip32
14. https://en.wikipedia.org/wiki/GoIP
15. https://talk-q.com/outbound-call-regulations-in-india
16. https://ssrana.in/articles/trais-crackdown-on-spam-calls-and-ai-driven-telemarketing/
17. https://securiti.ai/india-spam-rules-trai-latest-amendment/
18. https://www.c-zentrix.com/blog/140-number-series-guide-india
19. https://varindia.com/news/no-more-spam-calls-as-trai-bans-10-digit-numbers-for-telemarketing
20. https://www.trai.gov.in/faqcategory/unsolicited-commercial-communicationsucc
21. https://didlogic.com/ai-voice/livekit/
22. https://didlogic.com/ai-voice/bring-your-own-carrier/

---

## Phase: RESEARCH [sim-to-sip-options] — Personal SIM via GSM Gateway / Android / eSIM

> Appended 2026-06-14. READ-ONLY research. No box mutation, no code edit.
> Sources: bekiot.com GoIP docs, goantifraud.com, Yeastar TG datasheets, TRAI talk-q.com,
> ictinnovations.com Android gateway verdict, LiveKit docs, subex.com SIM-box detection,
> mobileidworld.com DoT AI crackdown, didlogic India SIP trunk pricing.

---

### HEADLINE

The founder's goal (own numbers, flexibility, multi-number, multi-concurrency, add-via-UI)
is RIGHT and buildable. The personal SIM path — route a real mobile SIM as a SIP trunk via
GSM gateway hardware — is technically real but carries HARD legal, operational, and scaling
constraints that cannot be engineered away. Stated plainly below.

---

### A. GSM GATEWAY HARDWARE (GoIP / Yeastar TG) — how a SIM becomes a SIP trunk

#### What it does

A GSM gateway holds real SIM cards in hardware slots. Each slot connects to a cellular radio
module. The device runs a SIP stack, registers to a SIP server (LiveKit-SIP, Asterisk,
FreeSWITCH), and acts as a standard SIP trunk peer. When LiveKit issues a SIP INVITE, the
gateway dials via the SIM's cellular radio, bridges audio (cellular RTP ↔ SIP RTP), and
returns the call to the IP side. To LiveKit-SIP it is indistinguishable from any CPaaS trunk.

#### Integration contract with LiveKit

```python
# Register the gateway as an SIPOutboundTrunk
POST /sip/trunk/outbound {
  "name": "GoIP-8-SIM-pool",
  "address": "192.168.1.100",         # LAN IP of the gateway
  "numbers": ["+919876543210", ...],  # the SIM numbers in the device
  "auth_username": "goip_user",
  "auth_password": "goip_pass"
}
# Returns: sip_trunk_id = "ST_goip_xxxxxx"

# Per-call selection
CreateSIPParticipant(
  sip_trunk_id="ST_goip_xxxxxx",
  sip_call_to="+91target",
  sip_number="+919876543210",  # which SIM presents as caller ID
)
```

Multiple gateways = multiple trunks; per-call trunk_id selects which one. ListSIPOutboundTrunk
enumerates all. Same trunk registry pattern as the provider registry.

#### THE 1-SIM = 1-CONCURRENT-CALL HARD LIMIT (cellular physics, no workaround)

GSM/WCDMA/LTE voice is circuit-switched (including VoLTE at the IMS level). ONE SIM =
ONE active voice path at any moment. This is enforced by the carrier's MSC/IMS:
- GoIP-1: EXACTLY 1 concurrent call. GoIP-8: EXACTLY 8. GoIP-32: EXACTLY 32.
- Source: goantifraud.com GoIP-1 listing — "cannot handle more than one active call at a
  time and that limitation is intentional, not a flaw."
- N concurrent calls = N physical SIM cards. Cost, power, space scale linearly.
- NO software config, NO firmware, NO gateway model eliminates this constraint.

#### Multi-SIM hardware models

| Device | SIM slots | Max concurrent | Approx India cost |
|---|---|---|---|
| GoIP-1 | 1 | 1 | ~₹2,500–4,000 |
| GoIP-4 | 4 | 4 | ~₹8,000–12,000 |
| GoIP-8 | 8 | 8 | ~₹12,000–20,000 |
| GoIP-16 | 16 | 16 | ~₹25,000–40,000 |
| GoIP-32 | 32 | 32 | ~₹50,000–80,000 |
| Yeastar TG200 | 2 | 2 | ~₹15,000–22,000 (enterprise) |
| Yeastar TG800 | 8 | 8 | ~₹38,000–55,000 (enterprise, ~€650 EU) |
| Yeastar TG1600 | 16 | 16 | ~₹75,000–1,10,000 |
| SIM bank + head-end | 32–128+ | 32–128+ | ₹1,50,000+ |

Sources: goantifraud.com; vdsae.com Yeastar India; voipsupply.com TG800; ipphone-warehouse.com.
Yeastar = enterprise firmware (OpenVPN, VLAN, failover, TCP SIP — matches Famit's Vobiz TCP
requirement). GoIP = prosumer (no enterprise support, patchy firmware).

#### Reliability

Depends on signal strength at the gateway location, carrier quality, antenna quality.
Yeastar enterprise firmware significantly more reliable. Both work with LiveKit-SIP via
standard SIP/UDP or SIP/TCP peer mode.

---

### B. ANDROID PHONE AS SIP/GSM GATEWAY — hard verdict: NOT viable

An Android phone CANNOT bridge a real cellular call to SIP on stock hardware.
Three architectural barriers (sourced: ictinnovations.com, confirmed 2026):

1. **No in-call audio API**: Android's media layer does not expose the active cellular
   call's audio stream to third-party apps. Audio output is hardware-locked to the speaker
   or Bluetooth — cannot be piped into a parallel SIP RTP stream.

2. **Locked Radio Interface Layer (RIL)**: The bridge between Android's telephony framework
   and the baseband modem is proprietary. Root access does not fix this — the vendor RIL
   binary still gates all modem access.

3. **Closed-source vendor RIL binaries**: Qualcomm, MediaTek, Samsung keep these closed.
   Custom ROMs (LineageOS, GrapheneOS) still rely on the same proprietary blobs.

What Android CAN do (different thing — not a personal SIM path):
- Act as a SIP softphone (Linphone, Zoiper) over Wi-Fi/4G — the call goes over the internet;
  the device's SIM number is NOT the caller ID. This is just a SIP endpoint, not a GSM bridge.

Commercial products claiming "Android as GSM gateway" (Pure-VoIP, A2VoIP, Kolmisoft Android
termination): require custom-built Android app + modified/rooted device + vendor cooperation,
OR they are SIP softphones in disguise. NOT viable for production outbound using real mobile
SIM numbers without hardware-vendor-level modifications.

Recommendation: do not pursue. Use dedicated hardware (GoIP/Yeastar) if personal SIM numbers
are genuinely required for specific use cases.

---

### C. eSIM / VoLTE SIP OPTIONS — no shortcut

#### eSIM

eSIM is a profile delivery mechanism, NOT a SIP interface. eSIM credentials still connect
to the carrier via the device's cellular radio over the standard circuit-switched (or VoLTE)
path. To use an eSIM number as a SIP trunk:
- (a) Hardware gateway with eSIM support (some newer Yeastar/SIM-bank units) — 1-SIM=1-call
      constraint fully applies.
- (b) Port the number to a CPaaS provider who presents it as a SIP DID (number porting,
      not an eSIM feature — eSIM is just credential delivery).

#### VoLTE ≠ internet SIP

VoLTE uses the carrier's IMS core. Consumer VoLTE calls cannot be injected from a third-party
SIP stack. B2B VoLTE SIP trunking in India (Airtel/Jio enterprise) exists but is a
negotiated contract, not a consumer feature. Not accessible for a startup without a large
minimum commitment.

#### The real path: CPaaS DID on SIP trunk

Buying a DID number from a CPaaS provider (Plivo, Telnyx, Vobiz, Airtel Business SIP):
- The provider ports the DID to their SIP platform.
- They hand you a SIP trunk (host:port + credentials + the DID).
- You register this as another LiveKit SIPOutboundTrunk.
- To add a new number: buy a new DID, register a new trunk — zero hardware, zero lead time.
- This achieves everything the founder wants: own numbers, add-via-UI, multi-number,
  multi-concurrency (each trunk can have elastic channels), rotation, carrier-compliant.

---

### D. HARD CONSTRAINTS — stated plainly (founder mandate: surface reality)

#### D1. 1-SIM = 1-concurrent-call (carrier physics, unbreakable)

Each SIM = 1 voice channel. 100 concurrent calls via personal SIMs = 100 physical SIM
cards in hardware. Cost: ₹50,000–80,000+ in hardware + ₹100–200/SIM/month carrier plans
+ space + power + failure risk. Elastic CPaaS SIP trunks cost ₹0.40–0.60/min with
effectively unlimited concurrency. At any meaningful scale, hardware SIM pools are
economically uncompetitive vs. CPaaS.

#### D2. Carrier spam detection: automated dialing from personal SIMs WILL trigger a ban

Indian carriers (Jio, Airtel, Vi) deploy AI-powered CDR analysis:
- Graph ML: 85% detection rate on fraud rings, <5% false-positive rate (subex.com).
- Detection signals: high call velocity per MSISDN; short duration + high frequency
  (predictive dialer CDR signature); voice-only with minimal data (SIM-box fingerprint);
  batch SIM activation patterns.
- DoT deactivated ~4 million fraudulent SIMs in 2025 via AI (mobileidworld.com).
- TRAI blacklisted 21 lakh numbers + 1 lakh entities (2025, domain-b.com).

Detection timeline: deliberately not published by carriers. Industry consensus: high-volume
burst patterns flagged within 24–72 hours; subtler patterns caught within 2–4 weeks by
batch graph analysis. At scale this is not a risk to manage — it is an inevitability.

Consequence: permanent carrier blacklist (2-year minimum TRAI). The number is irrecoverable.
The gateway's pattern can flag all other SIMs on the same device.

#### D3. TRAI 140-series mandate — using a personal SIM for commercial calling is ILLEGAL

TRAI TCCCPR 2018 + August 2024 + February 2025 amendments (sourced: talk-q.com citing
official TRAI orders; trai.gov.in UCC FAQ):

"Promotional voice calls MUST originate from 140-series numbers. TRAI's rules explicitly
forbid any subscriber (individual or business) from engaging in telemarketing via a regular
[10-digit mobile] number; telemarketing must be done through registered routes only."

"Using ordinary 10-digit numbers for marketing calls is prohibited — telecom providers will
disconnect those numbers on the first complaint and blacklist the caller for two years."
(talk-q.com, citing August 2024 TRAI directive)

Famit's AI outbound calls (pitching products, booking appointments) are PROMOTIONAL calls
by TRAI definition. Using a personal SIM via GoIP gateway for these campaigns is a legal
violation — not just a carrier-policy risk. It cannot be mitigated by technical means.
The only compliant path is 140-series numbers from a DLT-registered licensed telemarketer.

#### D4. A consumer SIM cannot present a 140-series Caller ID

140-series numbers are TRAI-allocated only to registered telemarketers. A consumer SIM has
a +91-XXXXXXXXXX MSISDN — there is no mechanism to present a 140-series CLI from a
consumer SIM or GoIP gateway using consumer SIMs. Therefore even if you used a GoIP gateway,
the CLI would still be a 10-digit mobile number (prohibited for commercial calls), not a
compliant 140-series number.

#### D5. Multi-concurrency from one personal MSISDN impossible at carrier level

One MSISDN = one active call. This is enforced at the carrier's MSC/IMS, not in the handset.
Enterprise multi-MSISDN SIMs (MLSIM) exist but require B2B carrier contracts, are not
consumer products, and still carry DLT requirements.

---

### E. RECOMMENDED ARCHITECTURE

**Primary (build this): CPaaS BYO SIP trunk registry, UI-driven**

Add Plivo / Telnyx / Exotel as second+ trunks alongside Vobiz. For TRAI-compliant mass
campaigns: Airtel Business SIP or Tata Tele SIP with 140-series DID + DLT registration.
All map to the same `sip_trunks` PG table and LiveKit trunk registry pattern from the prior
research phase. Adding a number = one UI form, one DB row, one LiveKit API call.

**Secondary / niche: GSM gateway for specific personal number (limited, non-automated)**

If founder wants his own personal mobile number to appear as caller ID on a specific
manual recall to a high-value lead (not a campaign): a Yeastar TG200 (2-SIM, ~₹18,000)
registered as a single LiveKit trunk handles this. HARD RULE: manual trigger only, NOT
in the automated campaign dialer pool — TRAI violation + rapid carrier ban otherwise.

**Do not build:**
- Android-as-gateway (architecturally blocked at hardware/RIL level).
- eSIM as direct SIP trunk (requires the same gateway hardware as a physical SIM).

---

### F. SOURCES (this phase)

- GoIP architecture: https://bekiot.com/encyclopedia/what-is-goip-gateway-definition-how-it-works-features-and-applications
- GoIP 1/4/8/32 specs: https://goantifraud.com/en/goip-equipment
- GoIP Wikipedia: https://en.wikipedia.org/wiki/GoIP
- SK GoIP manual: https://sksmsgateway.com/wp-content/uploads/2022/08/SKYLINE-SK-Gateway-User-Manual.pdf
- Yeastar TG800 India: https://www.vdsae.com/ippbxindia/price/yeastar-tg800-india/
- Yeastar TG800 product: https://www.ipphone-warehouse.com/Yeastar-TG800-Gateway-p/tg800.htm
- Yeastar TG user guide (PDF): https://help.yeastar.com/download/docs/tg200-tg400-tg800-tg1600-user-guide-en.pdf
- Android NOT viable: https://ictinnovations.com/using-android-phone-as-gsm-gateway/
- Android VoIP termination (Kolmisoft): https://blog.kolmisoft.com/android-powered-voip-termination-no-sim-boxes-no-headaches/
- Android SIP calling (softphone, not GSM bridge): https://www.videosdk.live/developer-hub/sip/what-is-sip-calling-in-android
- TRAI 140/160 outbound regulations: https://talk-q.com/outbound-call-regulations-in-india
- TRAI UCC / DND FAQ: https://www.trai.gov.in/faqcategory/unsolicited-commercial-communicationsucc
- TRAI 140/160 Exotel explainer: https://exotel.com/blog/decoding-new-calling-regulations-of-140-160-calling/
- India outbound call compliance: https://www.cleartouch.in/blog/trai-guidelines-for-outbound-calling-timings-in-india/
- TRAI crackdown 21 lakh numbers: https://www.domain-b.com/technology/information-technology/trai-cracks-down-on-spam-over-21-lakh-fraud-numbers-disconnected-new-advisory-issued
- DoT 4M SIM AI deactivation: https://mobileidworld.com/india-deactivates-4-million-fraudulent-sim-cards-using-ai-detection-system/
- India SIM verification 2024: https://mobileidworld.com/india-implements-strict-sim-card-security-measures-to-combat-telecom-fraud-in-2024/
- TRAI AI framework 2026: https://patnapress.com/trai-ai-rules-sim-disconnection-spam-india/
- SIM-box fraud detection (85% graph ML): https://www.subex.com/blog/simbox-fraud-challenges-and-ai-powered-solutions-for-telecom-operators/
- SIM-box fraud explained: https://theredteamlabs.com/sim-box-fraud/
- Interconnect bypass + SIM-box fraud: https://abhandshake.com/community/regional-fraud-interconnect-bypass/
- SIM-box telecom fast-mode: https://www.thefastmode.com/expert-opinion/45880-inside-sim-box-fraud-how-telcos-are-sparring-with-the-industry-s-next-big-challenge
- LiveKit outbound trunk: https://docs.livekit.io/telephony/making-calls/outbound-trunk/
- LiveKit SIP trunk setup: https://docs.livekit.io/telephony/start/sip-trunk-setup/
- LiveKit dispatch rules: https://docs.livekit.io/sip/dispatch-rule/
- LiveKit making calls: https://docs.livekit.io/agents/quickstarts/outbound-calls/
- India SIP trunk pricing: https://didlogic.com/blog/best-sip-trunk-provider-india/
- Plivo India SIP: https://www.plivo.com/sip-trunking/coverage/in/
- Exotel LiveKit SIP issue: https://github.com/livekit/sip/issues/278
- GSM-SIP connect guide: https://telxi.com/blog/connect-gsm-and-sip/

---
---

# Phase: DESIGN [telephony-trunk-registry] — THE 100% ARCHITECTURE (opus)
**Date:** 2026-06-14
**Mode:** READ-ONLY DESIGN. No box mutation, no caller.py/agent.py edit by this pass. The ONLY writes are this file + the ledger pointer. The live Vobiz/SIP trunk config is LEFT AS-IS; we build OUR OWN ALONGSIDE (additive). agent.py is NEVER touched — the registry feeds the SAME LiveKit-SIP the agent already dials through.
**Grounds:** the prior EXPLORE phases (current-sip-path, livekit-sip-native, existing-registry-analog) + the four RESEARCH phases (sim-to-sip-options, byo-number-sip-providers, spam-flag-and-compliance, multitrunk-concurrency-arch) in this same file, plus `design/PROVIDER-FRAMEWORK-PLAN.md` (the structural twin) and `droplet_work/db/ddl_provider_registry.sql` (the column-for-column source pattern).

---

## 0. HEADLINE — what we are building, and what is ALREADY proven on the box

The founder wants **telephony independence**: his own numbers, flexible, multi-number, multi-concurrency, add-a-trunk-entirely-from-the-UI, with spam-protection and number rotation — without ever touching the live earner (`agent.py`) or erasing the working Vobiz trunk.

The good news, proven in the EXPLORE phases: **LiveKit-SIP already supports unlimited trunks natively** (two outbound trunks are live on the box RIGHT NOW with zero conflict — `ST_fmtVmNJmpzKa` TCP + `ST_LH8ighJJtHSi` UDP). And the **provider_registry** (PG FORCE-RLS, AAD-bound AES-256-GCM credentials, in-memory circuit breaker, SSRF guard, strangler cut-over, super-admin + BYO UI) is **already built and LIVE** (W1-W5).

So this is NOT a from-scratch build. It is **ONE new layer cloned from a proven twin**: a `trunk_registry` PG table + Python package that is the column-for-column analog of `provider_registry`, resolving which `ST_<id>` (and which DID within it) `caller.py` passes to `CreateSIPParticipantRequest` per dial — instead of the hardcoded `TRUNK = cfg_get("LIVEKIT_SIP_TRUNK_ID", "ST_fmtVmNJmpzKa")` at `caller.py:184`.

**Design law (non-negotiable):** additive · flag-gated (`TRUNK_REGISTRY_ENABLED` default OFF -> resting byte-identical) · earner-safe (registry rides `caller.py`, NEVER imports `agent.py`) · multi-tenant FORCE-RLS · one box-mutating wave at a time · the existing Vobiz trunk is imported as ONE registry row so the live path is unchanged when the flag flips on · NEVER raises (any miss -> legacy `LIVEKIT_SIP_TRUNK_ID` fallback, the strangler guarantee).

**The single most important honest truth (founder mandate, stated up-front and repeated):** the *registry is buildable and correct*, but **independence at scale in India is gated by REGULATION, not by our code.** A consumer SIM cannot be a SIP trunk without a GSM gateway; 1 SIM = 1 concurrent call; auto-dialing from any 10-digit number (Vobiz DID or personal SIM) is **TRAI-non-compliant** — promotional calls legally MUST originate from a **140-series DID** provisioned through a **DLT-registered Principal Entity + Telemarketer**, NCPR-scrubbed, 9am-9pm only. The registry is designed to *enforce* this compliance (140-DID + DLT-status are required fields), not to bypass it. We build the perfect machine; the founder must buy the legal fuel (140-series trunk + DLT registration). Both are covered in §8 (founder-buy list).

---

## 1. THE PRODUCT — one paragraph (the 100% the founder didn't fully sketch)

A super-admin (or a vendor, scoped) opens **Settings > Telephony / Numbers**. They see a registry of every trunk the platform can dial through, each with a live health dot, a concurrency gauge (e.g. `3 / 20 channels in use`), its DID pool, and a per-DID daily-call budget bar. They click **Add trunk**, pick a **type** — *BYO SIP provider* (Vobiz / Plivo / Exotel / Telnyx — paste host + SIP username/password + the DID/caller-ID) · *GSM gateway* (a GoIP/Yeastar LAN endpoint — honestly flagged "1 SIM = 1 call, manual-trigger only, not for campaigns") · *Direct SIP* (a raw SIP URI + creds) — fill a short form (friendly name, SIP host:port, transport TCP/UDP/TLS, auth, DID pool, max-concurrency, 140-series + DLT-status fields), and the credentials are **encrypted at rest the instant they leave the form** (AAD-bound AES-256-GCM, only a masked `cap•••ject` shown after). They click **Test trunk** — which places **ONE controlled test call the FOUNDER places himself to a number he types** (NEVER an auto-dial; this is the only call this system ever originates outside a campaign), and watches it ring/answer/hang-up with a live SIP trace. The trunk is now **live, registered in LiveKit-SIP, with NO code deploy**. Campaigns then **rotate across the tenant's trunks** (round-robin or least-cost), **rotate the DID within each trunk** to spread call-velocity, **enforce per-trunk concurrency** (never exceed the channel cap), and **auto-rest any DID/trunk that starts returning 486/603** (the spam-reputation guard) — quarantining it and failing over to a healthy one. Every consumer asks `trunk_registry.get_trunk(tenant, direction='outbound')` instead of reading an env var; with no trunks configured the system is dormant and falls back to the single legacy Vobiz env trunk — byte-identical resting.

---

## 2. ARCHITECTURE — the layers (mirrors provider_registry exactly)

```
                            +------------------------------------------+
   FE: Settings>Telephony   |  famit-panel/app/telephony/page.tsx      |
   (the "crazy" Numbers page)|  + components/telephony/* (Core_2 kit)   |
                            +---------------+--------------------------+
                                            | lib/api.ts  (Bearer JWT)
                            +---------------v--------------------------+
   caller.py guarded mount  |  /trunk-registry/*   (super-admin)       |
   (additive, flag-gated)   |  /trunks/byo/*       (vendor, scoped)    |
                            +---------------+--------------------------+
                                            |
        +-----------------------------------+------------------------------------+
        v                                   v                                    v
  trunk_registry/                     trunk_registry/                     trunk_registry/
   store.py (RLS reads/writes)         credentials.py (AAD AES-GCM,        livekit_sync.py
   admin_store.py (is_admin)            REUSES provider_registry seam)      (the NEW glue:
   schema.py (dataclasses)             ssrf_guard.py (REUSE)                lk sip outbound/inbound/
   health.py (circuit breaker)         registry.py  get_trunk(...)         dispatch create/list/delete)
   rotation.py (NEW: DID round-robin                                       -> LiveKit Server API
              + spam-rest quarantine)                                         on 127.0.0.1:7880
        |                                                                          |
        v                                                                          v
   PG: 3 tables (FORCE-RLS)                                              LiveKit-SIP (Docker, box
   sip_trunks / sip_trunk_credentials / sip_trunk_health_log            168.144.153.145) — UNCHANGED
        |                                                                  binary; we only add/remove
        v                                                                  trunk + dispatch OBJECTS via API
   caller.py run_job dial loop  -- resolves ST_<id> + DID via get_trunk() --> CreateSIPParticipantRequest
   (the ONE hot-path consumer)                                                (sip_trunk_id=<resolved>,
                                                                              sip_number=<rotated DID>)
```

**Key architectural decision — REUSE, don't re-build.** `credentials.py`, `ssrf_guard.py`, `health.py`'s circuit-breaker primitive, the `get_secret()`/Fernet seam, the `require_super_admin` mount pattern, and the `build_router(...)` guarded-mount are **imported from / copied verbatim from `provider_registry`**. The ONLY genuinely new code is: (a) the 3 trunk-shaped PG tables, (b) `livekit_sync.py` (the LiveKit Server API glue that creates/lists/deletes outbound trunks, inbound trunks, and dispatch rules), and (c) `rotation.py` (DID round-robin + the spam-reputation rest/quarantine logic). Everything else is a structural clone.

---

## 3. SCHEMA — `db/ddl_trunk_registry.sql` (3 tables, FORCE-RLS, INTEGER paise)

Same posture as `ddl_provider_registry.sql`: standalone psql apply (NOT an Alembic revision), `IF NOT EXISTS`/`DROP-then-CREATE-POLICY` idempotent, `famit_app` is NOBYPASSRLS so FORCE-RLS binds the owner, money in **INTEGER PAISE** (no floats — founder law), `_global` read-share + write-lock for platform-shared trunks.

### Table 1 — `sip_trunks` (the reusable trunk spec; analog of `provider_definitions`)

```sql
CREATE TABLE IF NOT EXISTS sip_trunks (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            text NOT NULL,                 -- '_global' = platform-shared (e.g. the Vobiz import), else tenant
    slug                 text NOT NULL,                 -- 'vobiz-tcp', 'plivo-in', 'goip-desk'
    display_name         text NOT NULL,
    trunk_type           text NOT NULL,                 -- 'sip_provider'|'gsm_gateway'|'direct_sip'
    provider_vendor      text,                          -- 'vobiz'|'plivo'|'exotel'|'telnyx'|'twilio'|'goip'|'yeastar'|'generic'
    direction            text NOT NULL DEFAULT 'both',  -- 'outbound'|'inbound'|'both'
    -- SIP endpoint (reassembled server-side; SSRF-guarded for gsm_gateway/direct_sip LAN/host) --
    sip_host             text NOT NULL,                 -- '2c24f731.sip.vobiz.ai' | '10.0.0.5' (GoIP LAN)
    sip_port             int  NOT NULL DEFAULT 5060,
    transport            text NOT NULL DEFAULT 'TCP',   -- 'UDP'|'TCP'|'TLS'
    encryption           text NOT NULL DEFAULT 'DISABLE', -- 'DISABLE'|'SRTP'|'REQUIRE'
    auth_username        text,                          -- SIP digest user (outbound) ; NULL for IP-auth inbound
    -- inbound matching --
    allowed_addresses    jsonb DEFAULT '[]'::jsonb,     -- inbound IP allowlist (Vobiz IPs etc.)
    -- DID / caller-ID pool --
    did_pool             jsonb NOT NULL DEFAULT '[]'::jsonb, -- ['+918071583488', ...] rotated outbound caller-IDs
    -- concurrency + cost --
    max_concurrency      int  NOT NULL DEFAULT 1,        -- channel cap; GSM = #SIMs (HARD 1/SIM); SIP = licensed channels
    cost_per_minute_paise int,                           -- INTEGER paise/min ; e.g. 45 = Rs0.45 (Vobiz), 60 = Plivo
    -- COMPLIANCE (India TRAI — REQUIRED for promotional outbound) --
    is_140_series        boolean NOT NULL DEFAULT false, -- DID is a 140-series promotional number
    dlt_entity_id        text,                          -- DLT Principal-Entity id (NULL = unregistered)
    dlt_status           text NOT NULL DEFAULT 'unregistered', -- 'unregistered'|'pending'|'registered'
    per_did_daily_cap    int  NOT NULL DEFAULT 75,       -- stay <100/day/DID (spam-reputation guard)
    -- routing + health --
    priority             int  NOT NULL DEFAULT 100,      -- lower = preferred in outbound chain
    rotation_strategy    text NOT NULL DEFAULT 'round_robin', -- 'round_robin'|'least_cost'|'least_used'
    health_check_path    text DEFAULT 'OPTIONS',         -- SIP OPTIONS ping
    health_interval_s    int  DEFAULT 60,
    is_enabled           boolean NOT NULL DEFAULT true,
    is_test_verified     boolean NOT NULL DEFAULT false, -- flipped true ONLY after a founder test call succeeds
    quarantined_until    timestamptz,                    -- set by the spam-rest guard on 486/603 burst
    created_by           text,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    livekit_trunk_id     text,                           -- the ST_<id> returned by lk sip outbound/inbound create
    UNIQUE (tenant_id, slug)
);
CREATE INDEX IF NOT EXISTS siptrunk_tenant_idx ON sip_trunks (tenant_id, is_enabled, direction);
CREATE INDEX IF NOT EXISTS siptrunk_lk_idx     ON sip_trunks (livekit_trunk_id);
-- FORCE-RLS: READ own OR '_global' OR admin-GUC ; WRITE own (<>'_global') OR admin-GUC. (verbatim provider_definitions shape)
```

### Table 2 — `sip_trunk_credentials` (the SIP password; analog of `provider_credentials`)

Reuses the **identical** encrypt/decrypt/scope/AAD pattern from `provider_registry/credentials.py`. The SIP digest password is the secret. AAD = `tenant_id||trunk_id||key_version` (cross-tenant ciphertext copy -> `InvalidTag`). `scope='integration'` (vendor's own trunk -> revealable under PIN step-up) vs `'platform'` (the shared Vobiz trunk -> masked-only). UNIQUE `(tenant_id, trunk_id, key_version)`. FORCE-RLS strictly own-tenant (no `_global` cred read-share).

```sql
CREATE TABLE IF NOT EXISTS sip_trunk_credentials (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     text NOT NULL,
    trunk_id      uuid NOT NULL REFERENCES sip_trunks(id) ON DELETE CASCADE,
    ciphertext    bytea NOT NULL,                 -- AES-256-GCM: nonce(12)||ct  (the SIP password)
    wrapped_dek   bytea,                          -- NULL on interim Fernet path (Vault seam later)
    key_aad       text NOT NULL,                  -- 'tenant_id||trunk_id||version'
    key_version   int  NOT NULL DEFAULT 1,
    scope         text NOT NULL DEFAULT 'integration', -- 'integration' (revealable) | 'platform' (masked-only)
    is_active     boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, trunk_id, key_version)
);
-- FORCE-RLS: strictly own tenant.
```

### Table 3 — `sip_trunk_health_log` (append-only; analog of `provider_health_log`)

```sql
CREATE TABLE IF NOT EXISTS sip_trunk_health_log (
    id            bigserial PRIMARY KEY,
    tenant_id     text NOT NULL,
    trunk_id      uuid NOT NULL,
    did           text,                            -- which DID, for per-DID reputation tracking
    checked_at    timestamptz NOT NULL DEFAULT now(),
    is_healthy    boolean NOT NULL,
    event         text,                            -- 'options_ok'|'sip_486'|'sip_480'|'sip_603'|'answered'|'timeout'
    sip_code      int,                             -- 486/480/603/200
    latency_ms    int
);
-- REVOKE UPDATE, DELETE ON sip_trunk_health_log FROM famit_app;  -- append-only enforced
-- FORCE-RLS: own tenant.
```

**Column-for-column mapping (proves it is a clone, not invention):**

| provider_registry field | trunk_registry field |
|---|---|
| `provider_type` (hosted/self) | `trunk_type` (sip_provider/gsm_gateway/direct_sip) |
| `capabilities[]` | `direction` (outbound/inbound/both) |
| `base_url` (SSRF-validated) | `sip_host`+`sip_port`+`transport` (reassembled, SSRF-guarded for LAN/direct) |
| `auth_scheme`+`auth_header`+`auth_tmpl` | `auth_username` + encrypted password row |
| `named_provider` | `provider_vendor` |
| `model_default` | `did_pool[]` (the caller-ID set) |
| `cost_per_unit_micros`+`cost_unit` | `cost_per_minute_paise` (INTEGER, per_minute) |
| `rate_limit_rpm` | `max_concurrency` (1 per SIM — hard reality) + `per_did_daily_cap` |
| `priority` | `priority` + `rotation_strategy` |
| `is_enabled` | `is_enabled` + `is_test_verified` + `quarantined_until` |
| `health_check_path`+`health_interval_s` | `health_check_path`(OPTIONS)+`health_interval_s` |
| `tenant_id` + FORCE-RLS | identical |
| (NEW for trunks) | `is_140_series`, `dlt_entity_id`, `dlt_status` (TRAI compliance gates), `livekit_trunk_id` (the ST_ binding) |

---

## 4. PYTHON PACKAGE — `droplet_work/trunk_registry/` (clone of `provider_registry/`)

| File | Source | Role / what is NEW |
|---|---|---|
| `config.py` | clone | `FLAG_ENV="TRUNK_REGISTRY_ENABLED"`, `is_enabled()` call-time, default OFF |
| `schema.py` | clone | `TrunkType`, `Direction`, `Transport`, `DltStatus`, `RotationStrategy` enums + `SipTrunk`/`TrunkCred` dataclasses with `from_any(row)` + `expected_aad()` |
| `store.py` | clone | RLS reads (`list_trunks(tenant, direction, enabled_only)` ORDER BY priority) + writes; `get_active_credential(tenant, trunk_id)` |
| `admin_store.py` | clone | `is_admin=True` variant, mounted ONLY under `require_super_admin` (writes `_global` Vobiz row) |
| `credentials.py` | **REUSE** provider_registry's verbatim | AAD AES-256-GCM, the `get_secret()` seam; SIP password is the plaintext |
| `ssrf_guard.py` | **REUSE** verbatim | gates `sip_host` for `gsm_gateway`(LAN allowed-but-logged) + `direct_sip` (RFC1918/metadata denylist, DNS-resolve-all) |
| `health.py` | clone | in-memory 3-fail circuit breaker (FAIL_THRESHOLD=3, backoff 60->120->...3600) keyed `(tenant, trunk_id)`; `run_probe` does a SIP OPTIONS ping via livekit_sync |
| **`livekit_sync.py`** | **NEW** | the LiveKit Server API glue — `create_outbound_trunk(spec)->ST_id`, `create_inbound_trunk(spec)->ST_id`, `create_dispatch_rule(trunk_id, agent_name, tenant_id)`, `list/delete`. Wraps `livekit.api` (already imported by caller.py at `:184`/`place_call.py`). Stores returned `ST_<id>` into `sip_trunks.livekit_trunk_id`. NO container restart — pure API. |
| **`rotation.py`** | **NEW** | `pick_did(trunk)` -> Redis `INCR trunk:{id}:did_index` % len(did_pool); `note_result(trunk, did, sip_code)` -> on 486/480/603 burst (>=N in window) flip `quarantined_until = now()+rest` + write health row + emit audit; `daily_budget_ok(trunk, did)` -> enforce `per_did_daily_cap` |
| `registry.py` | clone | **THE resolution point:** `get_trunk(tenant, direction='outbound', did_hint=None) -> TrunkClient(ok, livekit_trunk_id, did, reason)`. Flag check -> `store.available()` -> `list_trunks` RLS by priority -> skip `health.is_open` + skip `quarantined_until>now` + skip `concurrency>=max` -> `pick_did` (skip DIDs over daily cap) -> return first usable. NEVER raises. |
| `concurrency.py` | **NEW (thin)** | `acquire(trunk_id)`/`release(trunk_id)` -> Redis `trunk:{id}:active_calls` INCR/DECR with the `max_concurrency` ceiling check; reuses the box Redis the SIP service already runs on |
| `endpoints.py` | clone | two surfaces: `/trunk-registry/*` (super-admin, `require_super_admin`) + `/trunks/byo/*` (tenant, `integration` scope, NO gsm_gateway/direct_sip self-registration — super-admin-only, SSRF-probed). Routes in §6. |

---

## 5. LIVEKIT WIRING — how the registry drives the SAME LiveKit-SIP the agent uses

**5a. Adding a trunk (UI -> DB -> LiveKit, no restart).** `POST /trunk-registry/trunks` -> SSRF-guard `sip_host` (for gsm/direct) -> encrypt password into `sip_trunk_credentials` -> insert `sip_trunks` row -> `livekit_sync.create_outbound_trunk({name, address:sip_host, transport, numbers:did_pool, auth_username, auth_password:<decrypted-in-memory>})` -> LiveKit returns `ST_<id>` -> store in `livekit_trunk_id`. For inbound trunks also `create_inbound_trunk({numbers:did_pool, allowed_addresses})` + `create_dispatch_rule({trunk_ids:[ST_id], rule:dispatchRuleIndividual(roomPrefix), room_config.agents:[{agent_name}], metadata:{tenant_id}})`. **This is the native multi-trunk path proven in EXPLORE [livekit-sip-native] 2a-2c — two trunks already coexist live.**

**5b. Outbound selection at dial time (the ONE hot-path change in caller.py — strangler).** Today `caller.py:184` hardcodes `TRUNK`; the dial is `caller.py:2913` `create_sip_participant(sip_trunk_id=TRUNK, sip_call_to=num, ...)`. The strangler cut:
```python
# caller.py run_job, just before create_sip_participant (additive, flag-gated):
if trunk_config.registry_enabled():
    tc = trunk_registry.get_trunk(tenant_id, direction="outbound")   # never raises
    if tc.ok:
        sip_trunk_id = tc.livekit_trunk_id
        sip_number   = tc.did            # rotated DID as caller-ID
        trunk_registry.concurrency.acquire(tc.trunk_id)
    else:
        sip_trunk_id = TRUNK             # legacy fallback (the Vobiz env trunk)
        sip_number   = None
else:
    sip_trunk_id = TRUNK                 # flag OFF -> byte-identical to today
    sip_number   = None
await lk.sip.create_sip_participant(CreateSIPParticipantRequest(
    sip_trunk_id=sip_trunk_id, sip_number=sip_number, sip_call_to=num, room_name=room, ...))
# on call finalize (caller.py:2844 region): trunk_registry.concurrency.release(tc.trunk_id)
#                                            + rotation.note_result(tc.trunk_id, tc.did, sip_code)
```
`sip_number` is the native LiveKit per-call caller-ID selector within the trunk's `numbers[]` (EXPLORE 2d) — this is how DID rotation is realized with ZERO LiveKit config change.

**5c. Inbound DID->tenant->agent (multi-tenant routing).** Each tenant DID gets its own inbound trunk + dispatch rule with `metadata:{tenant_id}`; the agent reads `sip.trunkPhoneNumber` (which DID was dialed) + `metadata.tenant_id` from job context (EXPLORE 2f) -> scopes all data to that tenant. The existing AIM inbound (`ST_K785ASpNh5ow` -> agent `manager`) is imported as ONE inbound registry row, unchanged.

**5d. Per-trunk concurrency enforcement.** LiveKit has NO native per-trunk cap (EXPLORE 2b) — enforced in `concurrency.py` via Redis `trunk:{id}:active_calls` vs `max_concurrency`. The total box ceiling is the RTP port range (`10000-10200` = ~100 calls); raise the range in `sip.runtime.yaml` (a container recreate, scheduled separately, NOT in this wave) when scaling past ~100.

**5e. Spam-reputation guard (number rotation + auto-rest).** `rotation.note_result` watches SIP codes per DID: a burst of 486/480/603 (the carrier-block fingerprint — exactly the `MASTER_DNA_PLAN.md:57-60` symptom on `+918071583488` today) -> set `quarantined_until = now()+rest_window`, write a health row, emit audit, and `registry.get_trunk` skips quarantined DIDs/trunks -> automatic failover to a healthy one. `per_did_daily_cap` (default 75, <100 hard) caps velocity per DID to stay under the carrier suspicion threshold (RESEARCH spam-flag 3). **Honest caveat:** rotation distributes velocity and survives a single-DID flag, but it does NOT defeat carrier *entity*-level behavioral scoring or substitute for DLT registration (RESEARCH spam-flag 3) — it is a mitigation, not a bypass.

**5f. Importing the live Vobiz trunk (zero-disruption).** A one-time seed inserts the existing `ST_fmtVmNJmpzKa` as a `_global` `sip_trunks` row (`trunk_type=sip_provider`, `provider_vendor=vobiz`, `livekit_trunk_id=ST_fmtVmNJmpzKa`, `did_pool=['+918071583488']`, `scope=platform` cred) — so when `TRUNK_REGISTRY_ENABLED=1`, `get_trunk` returns the SAME trunk the agent dials today. The live path is unchanged; we just route the selection through the registry. The Vobiz config files (`sip-inbound/outbound_trunks.json`) are LEFT AS-IS, untouched (founder mandate).

---

## 6. API SURFACE (caller.py guarded mount, additive, flag-gated)

Mounted ONLY when `TRUNK_REGISTRY_ENABLED=1`, via the same `build_router(resolve_tenant, can, need_auth, _forbidden, firewall=...)` pattern as provider_registry (`caller.py:7309` analog). Prefix `/trunk-registry` (super-admin) + `/trunks/byo` (tenant).

**Super-admin (`require_super_admin`):**
- `GET  /trunk-registry/trunks` — list all trunks + live health/concurrency/quarantine
- `POST /trunk-registry/trunks` — add trunk (SSRF-guard host, encrypt pw, insert row, `livekit_sync.create_*`)
- `PATCH /trunk-registry/trunks/{id}` — edit (priority, did_pool, max_concurrency, enable/disable, compliance fields)
- `DELETE /trunk-registry/trunks/{id}` — remove (also `livekit_sync.delete` the ST_ object)
- `POST /trunk-registry/trunks/{id}/test-call` — **THE founder test:** body `{to_number}` (a number the founder types) -> places ONE `CreateSIPParticipant` through this trunk into a throwaway room with a "test, please hang up" TTS agent -> returns live SIP trace (trying/ringing/answered + code). On 200/answered -> flip `is_test_verified=true`. **NEVER auto-dials; only this explicit founder action ever originates a non-campaign call.**
- `POST /trunk-registry/trunks/{id}/reveal-init` + `/reveal` — PIN step-up to reveal an `integration`-scope SIP password (platform scope = masked-only)
- `GET  /trunk-registry/trunks/{id}/health` — health history + per-DID reputation
- `POST /trunk-registry/dispatch` — create/list/delete inbound dispatch rules (DID->agent->tenant)

**Vendor (`/trunks/byo`, tenant-scoped, `integration` scope only):**
- `GET  /trunks/byo` — list own trunks
- `POST /trunks/byo` — add own **SIP-provider** trunk (BYO creds) — **NO** gsm_gateway/direct_sip (super-admin-only, SSRF-probed)
- `PATCH/DELETE /trunks/byo/{id}` — manage own
- `POST /trunks/byo/{id}/test-call` — own controlled founder/vendor test call

---

## 7. THE FRONTEND — Settings > Telephony / Numbers (Core_2 kit, never from scratch)

Lives at `famit-panel/app/telephony/page.tsx` + `components/telephony/*`, ported from the Core_2 Capsy dashboard kit (founder's #1 UI rule — REUSE, never invent). Talks via `lib/api.ts`.

**Layout (the "crazy best-of-best" Numbers page):**
- **Header:** "Telephony" title (no PageHeader/subtitle per the UI-overhaul rule) + primary **Add trunk** button.
- **Trunk cards grid** (Core_2 stat-card port): one card per trunk — friendly name, vendor badge, **live health dot** (green/amber/red from `health_log`), **concurrency gauge** (`3 / 20`), **DID pool chips** with a per-DID daily-budget bar (e.g. `52 / 75`), a **compliance badge** (140-series + DLT-registered OK / unregistered -> blocked from campaigns), a **quarantine banner** if rested, and per-card actions: Test · Edit · Reveal · Disable.
- **Add-trunk modal** (3-step wizard, Core_2 form kit): Step 1 pick **type** (SIP provider · GSM gateway · Direct SIP) — each with an honest inline note (GSM: "1 SIM = 1 concurrent call; manual-trigger only; not TRAI-compliant for campaigns"). Step 2 the form (host:port, transport, auth user+password, DID pool, max-concurrency, 140-series + DLT fields — **DLT fields REQUIRED to enable for outbound campaigns**, with a "What's DLT?" helper linking the founder-buy guide). Step 3 **Test trunk** — founder types a destination number -> one live test call with a ringing animation + SIP trace -> "Connected" flips `is_test_verified` and unlocks "Save & enable".
- **Inbound routing panel:** a table of DID -> agent (`capsy`/`manager`) -> tenant dispatch rules, add/edit/delete.
- **Spam-reputation panel:** per-DID 486/603 history sparkline + quarantine status + a manual "rest this number" / "release" toggle.

Every backend capability has its FE control here (founder's standing rule — full CRUD + configure + the founder-placed TEST, real-time).

---

## 8. THE HONEST FOUNDER-BUY LIST (what code cannot give him)

Stated plainly (founder mandate — surface reality):

1. **A 140-series DID on a DLT-registered SIP trunk — THE non-negotiable for legal India campaigns.** Code cannot mint this. The founder must register **Famit/Axcrio Pvt Ltd** as a **Principal Entity + Telemarketer** on a DLT portal (Airtel/Jio/Vi/Tanla — they mirror), register call headers (the 140-number) + conversation templates, and provision the 140-series SIP trunk from a licensed VNO (**Airtel Business / Tata Tele / C-Zentrix / Knowlarity** — all are standard SIP trunks LiveKit connects to identically). Cost: registration is cheap; the 140-trunk is per-channel + per-minute. **Lead time ~1-2 weeks. Until this exists, every "campaign" from any 10-digit DID (including the current Vobiz number) is technically non-compliant and spam-flag-prone — which is exactly why `+918071583488` is carrier-blocked today.**
2. **A second BYO SIP trunk for provider-independence + failover — recommended: Plivo** (Rs250/DID/mo, Rs0.60/min, unlimited concurrency, official LiveKit docs, requires India entity COI+GST — Famit likely has these). One UI form -> one registry row -> instant second trunk. **Exotel** is the only provider that supports **BYO porting of an existing Indian number**, but its LiveKit vSIP is still **Alpha/IP-whitelist-auth** — wait for GA. **Telnyx/Twilio have NO India local DID** (Rs4-5.5/min, foreign caller-ID kills answer rates) — emergency international only, skip for India.
3. **(Optional, niche) A GSM gateway for ONE personal number as caller-ID on a manual high-trust recall — Yeastar TG200** (~Rs18,000, 2-SIM, proper TCP SIP stack). Registers as one more outbound trunk. **HARD RULE baked into the design: `gsm_gateway` trunks are manual-trigger only, NEVER in the automated campaign pool** — because 1 SIM = 1 call, the SIM WILL get carrier-banned at campaign volume, and consumer-SIM telemarketing is illegal under TRAI. Do NOT buy this for scale; only for a single personal-number recall use-case. **Recommendation: skip unless that exact use-case is needed.**
4. **NCPR/DND scrub access** (bundled with the DLT/VNO trunk) — mandatory pre-campaign scrub.
5. **Raise the LiveKit RTP port range** (a future container-recreate wave, not a buy) when scaling past ~100 concurrent.

**The one-line truth for the founder:** the registry gives you *technical* independence (own creds, add any trunk from the UI, multi-number, multi-concurrency, rotation, failover, spam-rest) TODAY; *legal* independence at India scale requires the 140-series + DLT registration (a purchase + a 1-2 week paperwork step), which the registry is built to enforce, not bypass.

---

## 9. RISKS + MITIGATIONS

| Risk | Mitigation (baked into the design) |
|---|---|
| Touching the live earner | Flag OFF = byte-identical; agent.py never imported; Vobiz trunk imported as a row so the dial is unchanged; one box-mutating wave; immediate env-flag revert |
| The `scheduler_loop` retry bug re-firing dead numbers (kept the carrier block alive) | MUST be fixed BEFORE enabling outbound rotation (it is QUEUED in WORKFLOW_LEDGER) — else rotation just spreads the bug across more DIDs |
| SSRF via a user `sip_host` (GSM LAN / direct SIP) | REUSE provider_registry `ssrf_guard.py` verbatim; gsm/direct trunks are super-admin-only |
| Cross-tenant credential theft | AAD-bound AES-256-GCM (copy -> InvalidTag); FORCE-RLS own-tenant creds; PIN step-up reveal; platform scope masked-only |
| Auto-dialing a personal SIM -> permanent ban + illegal | `gsm_gateway` HARD-flagged manual-only + excluded from the campaign pool in code; honest UI note; founder-buy list states it plainly |
| Promotional calls from non-140 DID -> TRAI disconnect + 2yr blacklist | `is_140_series`+`dlt_status` are REQUIRED to enable a trunk for outbound campaigns; UI blocks unregistered trunks from the campaign pool |
| Concurrency oversell beyond channel cap -> SIP 486 storm | `concurrency.py` Redis counter vs `max_concurrency`; per-trunk hard ceiling before dial |
| LiveKit container restart needed | NONE for trunk/dispatch CRUD (pure API); only RTP-range scaling needs a recreate (separate wave) |
| A test call auto-firing | The ONLY non-campaign originate is the explicit founder-typed `test-call` route; never automatic |

---

## 10. BUILD SEQUENCE (earner-safe, one box-mutating wave at a time)

- **T0 (prereq, separate):** deploy the queued `scheduler_loop` retry-bug fix (else rotation amplifies it).
- **T1 (DB-only, no box risk):** apply `db/ddl_trunk_registry.sql` (3 tables, FORCE-RLS) standalone via psql; seed the `_global` Vobiz row + cred.
- **T2 (code, flag OFF):** ship `droplet_work/trunk_registry/*` (clone provider_registry; REUSE credentials/ssrf/health; NEW livekit_sync/rotation/concurrency). Resting byte-identical.
- **T3 (mount, flag OFF):** additive `/trunk-registry` + `/trunks/byo` guarded mount in caller.py. No behavior change.
- **T4 (FE):** Settings>Telephony page (Core_2 port) + the founder test-call flow. Deploy to FORTRESS panel.
- **T5 (strangler, flag ON in staging->prod):** the `caller.py` dial-loop cut-over (5b) behind `TRUNK_REGISTRY_ENABLED`. Integrated smoke: a real outbound call rings via the registry-resolved Vobiz row (= the current trunk) BEFORE and AFTER — proving zero regression — then enable rotation across a second (Plivo/140) trunk once the founder buys it.

---

**Files this design names (to be created in the BUILD waves):**
- `droplet_work/db/ddl_trunk_registry.sql` (NEW — 3 tables)
- `droplet_work/trunk_registry/` (NEW package: config/schema/store/admin_store/credentials[reuse]/ssrf_guard[reuse]/health/livekit_sync[NEW]/rotation[NEW]/concurrency[NEW]/registry/endpoints)
- `caller.py` (additive: guarded mount + the 5b strangler dial-loop cut, flag-gated)
- `famit-panel/app/telephony/page.tsx` + `famit-panel/components/telephony/*` (NEW — Core_2 port)
- `famit-panel/lib/api.ts` (additive trunk-registry client methods)

**Flags:** `TRUNK_REGISTRY_ENABLED` (master, default OFF), reuses `FIREWALL_ENABLED` for the PIN step-up reveal.
**END Phase: DESIGN [telephony-trunk-registry]**

---
---

# Phase: RED-TEAM [sim-concurrency-legal] — adversarial review of the trunk-registry DESIGN (opus)
**Date:** 2026-06-14
**Mode:** READ-ONLY. No box/`caller.py`/`agent.py` edit. The only write is this append. Skeptical-by-default: I am NOT here to agree with the design — I am here to find the concrete failures it has not closed, on the two axes the founder named: (A) the 1-SIM=1-call ceiling vs the multiple-concurrency wish, and (B) the TRAI/DND/DLT + carrier-ToS legality of mass outbound from a personal SIM. Each finding states the failure concretely and the exact fix it demands.

---

## VERDICT FIRST (the one line)

The DESIGN is **honest and architecturally sound** on both axes — it does NOT hide the 1-SIM=1-call physics, it does NOT pretend a personal SIM is legal, and it bakes the right enforcement gates (`is_140_series` / `dlt_status` required, `gsm_gateway` manual-only). That is rare and correct. **But it is enforcement-by-good-intention, not enforcement-by-construction.** Five concrete gaps let a non-compliant or over-concurrent call slip through *despite* the design's stated rules, because the rules live in prose and in nullable/default-true columns rather than in hard DB constraints + a single choke-point check. Below are the failures and the fix each demands. None invalidate the build; all must land before `TRUNK_REGISTRY_ENABLED=1` in prod.

---

## AXIS A — 1 SIM = 1 CALL vs the founder's "multiple concurrency" wish

### Does the design make the limit CLEAR? — YES.
§0, §8.3, the schema comment on `max_concurrency` ("GSM = #SIMs (HARD 1/SIM)"), the UI Step-1 note ("1 SIM = 1 concurrent call"), and the RESEARCH D1/D5 phases all state it plainly and repeatedly. The founder cannot read this design and believe one SIM gives him concurrency. **PASS on clarity.**

### Does the design SOLVE concurrency? — YES, the right way, but with three concrete holes.
The solve is correct in shape: concurrency is **not** bought from one SIM — it is bought from **multiple channels** = (a) elastic CPaaS trunks (Vobiz/Plivo, effectively unlimited channels, the real answer), (b) multiple SIP-provider trunks pooled, or (c) at the GSM edge, N physical SIMs in N gateway slots (1 each). `concurrency.py` (Redis `trunk:{id}:active_calls` vs `max_concurrency`) + multi-trunk failover is the standard, proven pattern (RESEARCH multitrunk PART 3). The wish is satisfied by **summing channels across trunks**, never by a single SIM. Good. The holes:

**A1 — FAILURE: the Redis concurrency counter leaks and will eventually deadlock a trunk at "full" with zero real calls.**
The design acquires in the dial path (5b) and releases "on call finalize (caller.py:2844 region)". Concrete failure: any path that does NOT reach the finalize region — `CreateSIPParticipant` raises after `acquire()`, the box OOM-kills the worker mid-call, the LiveKit egress/agent crashes, a `SIGKILL` on deploy — leaves `active_calls` permanently incremented. After enough crashes, `active_calls >= max_concurrency` forever and `get_trunk` skips a perfectly healthy trunk; with one trunk, the dialer silently stops dialing and looks "dead" with no error. This is the single most common production failure of exactly this Redis-counter pattern.
**FIX (required):** (1) wrap acquire/release in try/finally so a raise after acquire always releases; (2) make the counter self-healing — store per-call membership in a Redis **sorted set** keyed by call start-time (`ZADD trunk:{id}:calls <now> <call_id>`) and count via `ZCOUNT` after `ZREMRANGEBYSCORE` evicts entries older than max-call-duration (e.g. 1h). A leaked entry then auto-expires instead of poisoning the trunk forever. A bare `INCR/DECR` integer (as written in §4 `concurrency.py` and RESEARCH PART 6) is NOT crash-safe and must not ship as-is.

**A2 — FAILURE: acquire/check/dial is a race (TOCTOU) — the counter oversells under burst.**
`get_trunk` checks `concurrency >= max` (registry.py) and `acquire()` increments — but these are two separate Redis round-trips. Under a campaign burst (the whole point of concurrency), two workers both read `active_calls = 19` (cap 20), both pass the check, both `INCR` to 20/21 → 21 concurrent dials on a 20-channel trunk → the provider returns SIP 486 on the 21st, and worse, on a real licensed-channel trunk this can trip the provider's anti-abuse and flag the DID. The check and the claim must be ONE atomic operation.
**FIX (required):** make acquisition atomic — a tiny Lua script (or `INCR` then compare-and-`DECR`-on-overflow): `INCR active_calls; if result > max then DECR and return DENY`. The ceiling is then enforced by the increment itself, not by a prior read. This is a 6-line Lua script; the design must name it, not leave acquire/check as two steps.

**A3 — GAP: per-SIM concurrency is modelled at the trunk grain, not the SIM/DID grain — a GSM gateway can oversell a single SIM.**
`max_concurrency` is per-**trunk**. A GoIP-8 registered as ONE trunk with `max_concurrency=8` correctly caps the trunk at 8 — BUT if two of those 8 calls are both told to use the SAME `sip_number` (same SIM) via DID rotation collision, that single SIM is asked for 2 simultaneous calls, which the cellular radio physically cannot do → the second fails mid-setup with a confusing gateway error, not a clean 486. The 1-SIM=1-call limit is physical per-SIM, but the counter is per-trunk. (For elastic CPaaS this is a non-issue — a DID there is not a physical radio — so this only bites the `gsm_gateway` type.)
**FIX (required, but cheap because GSM is manual-only):** for `trunk_type='gsm_gateway'`, the DID-rotation index and the concurrency counter must be the SAME object — one in-flight call per `sip_number`. Simplest: enforce that a `gsm_gateway` trunk's `did_pool` length == `max_concurrency` == #SIMs, and rotation hands out a DID only if THAT DID's per-DID active count is 0. Since the design already hard-restricts `gsm_gateway` to manual single calls (never the campaign pool), this is a small guard, but it must exist or a 2-SIM Yeastar will misbehave the first time two manual recalls overlap.

**A4 — HONEST CEILING the design under-states: the real concurrency wall is the LiveKit RTP port range, not the trunk.**
§5d and §8.5 mention raising the RTP range "past ~100" as a *future* wave. But the founder's "multi-concurrency" wish, if he buys an elastic Plivo trunk and runs a real campaign, hits the **box's** `10000-10200` RTP ceiling (~100 media flows) LONG before any trunk channel limit. The design correctly defers the recreate, but it does NOT flag that **until that recreate happens, `max_concurrency` on any trunk is a lie above ~100 box-wide** — the registry will happily hand out trunk #101 and the call fails at media setup. So concurrency is *summed across trunks* but *capped by the box*, and that cap is lower than the trunk caps the UI will show.
**FIX (required, cheap):** add a **box-global concurrency ceiling** check in `concurrency.py` (`trunk:_box:active_calls < BOX_MAX_CONCURRENT`, default ~90 to stay under the 100 RTP flows) that gates EVERY acquire regardless of trunk. The per-trunk cap and the box cap are both active ceilings (exactly as RESEARCH PART 3 says Vapi's slot-limit AND the trunk-limit are both active). Without this, the UI gauge promises concurrency the box can't deliver.

### Axis A summary
Clarity: **PASS.** Solve: **CORRECT IN SHAPE** (concurrency = sum of channels across trunks, never one SIM) but ships with a **leaky, racy, trunk-grain, box-unaware counter**. Fixes A1-A4 are all small and local to `concurrency.py`/`rotation.py` — but A1 (leak) and A2 (race) are not optional: a bare INCR/DECR counter WILL strand a trunk and WILL oversell under exactly the burst load concurrency exists for.

---

## AXIS B — TRAI / DND / DLT + carrier-ToS legality of mass outbound from a personal SIM

### Does the design FLAG the exposure? — YES, thoroughly and honestly.
§0, §8.1, §8.3, the §9 risk table (two dedicated rows), the UI Step-1 honest note, and RESEARCH phases D2/D3/D4 + PART 4/5 state without hedging: a personal SIM via GSM gateway for campaigns is **illegal under TCCCPR 2018 (+Aug-2024/Feb-2025 amendments)**, **WILL be carrier-banned** (DoT 4M SIMs deactivated 2025, graph-ML 85% within 24-72h to 4 weeks), **cannot present a 140-series CLI**, and is exactly why `+918071583488` is blocked today. It names the compliant path (140-series DID on a DLT-registered PE+Telemarketer trunk, NCPR scrub, 9am-9pm, AI self-disclosure). **PASS on flagging.** This is the strongest part of the design.

### What a registered telemarketing trunk REQUIRES — the design names it but the ENFORCEMENT has holes.
The compliant requirements (correct, per RESEARCH PART 5): (1) PE registration on DLT, (2) Telemarketer ID, (3) call-header (140-number) + conversation-template registration on DLT *before* launch, (4) 140-series DID provisioned by a licensed VNO (Airtel Business/Tata Tele/C-Zentrix), (5) NCPR/DND scrub on a rolling (≥weekly) basis, (6) 9am-9pm IST window, (7) AI/auto-dialer self-disclosure at call start, (8) origin-access-provider notified of auto-dialer use. The design lists 1-7 in prose. The holes are that the design's *enforcement* of these is softer than its prose:

**B1 — FAILURE: the compliance gate is `DEFAULT true` / nullable — a non-compliant trunk can be enabled by omission.**
`is_140_series boolean NOT NULL DEFAULT false` is fine, but `dlt_status text NOT NULL DEFAULT 'unregistered'` plus `is_enabled boolean NOT NULL DEFAULT true` means: insert a row with NO compliance fields set → it is `is_enabled=true`, `dlt_status='unregistered'` → and NOTHING in the schema stops `get_trunk` from returning it for an outbound campaign. The design SAYS (§7, §9) "DLT fields REQUIRED to enable for outbound campaigns" and "UI blocks unregistered trunks from the campaign pool" — but that block lives in the **UI and in prose**, not in `registry.get_trunk` or a DB constraint. A vendor hitting `POST /trunks/byo` directly (bypassing the UI), or a future code path that forgets the check, dials a real campaign from an unregistered 10-digit DID → the exact TRAI violation the design exists to prevent, with a 2-lakh fine and 2-year blacklist.
**FIX (required — this is the most important finding):** move the gate from prose into the **single choke-point** + a **DB CHECK**. (1) In `registry.get_trunk(..., direction='outbound', purpose='campaign')`, after health/concurrency/quarantine skips, add: `if purpose=='campaign' and not (trunk.is_140_series and trunk.dlt_status=='registered'): skip this trunk`. This is the ONE place every campaign dial resolves a trunk — enforce it there and the UI/API can never route around it. (2) Add a partial DB constraint or a `is_campaign_eligible` GENERATED column = `(is_140_series AND dlt_status='registered' AND quarantined_until IS NULL)` so eligibility is computed, not asserted. The founder's own manual test-call and a `gsm_gateway` recall pass a different `purpose` and are allowed; only `purpose='campaign'` demands the 140+DLT gate. Right now a campaign and a test share the same `get_trunk` and the same default-true row — that is the gap.

**B2 — FAILURE: NCPR/DND scrub and the 9am-9pm window and AI-disclosure are NAMED but have NO enforcement point in this design at all.**
The design lists NCPR scrub (#4/§8.4), the 9-9 window, and AI self-disclosure as founder-buy / prose items — but unlike the 140/DLT gate (which at least has nullable columns), there is **zero hook** in the trunk registry for them. The trunk registry resolves *which trunk*; it never checks *whether THIS destination number is DND-scrubbed*, *whether it is 9am-9pm right now*, or *whether the agent's opening line discloses AI*. Those are per-**call** / per-**campaign** gates, and the design correctly notes they belong to the campaign-launch flow — but it does not say WHERE, so they will fall through the cracks between "trunk registry" and "campaign", which is exactly how compliance gaps happen ("I thought the other system did it").
**FIX (required, scoped correctly):** explicitly state these are NOT the trunk registry's job and name their owner: (1) **NCPR scrub** → a pre-flight gate in the campaign-launch path (block launch without a scrub-confirmation timestamp ≤7 days old) — add a TODO/handoff line so it is not orphaned. (2) **9am-9pm IST window** → enforced in the `scheduler_loop` dial path (the same loop with the retry bug), a single `if not (9 <= now_ist.hour < 21): defer` guard — cheap, and it belongs next to the dialer, not the registry. (3) **AI self-disclosure** → the agent's system prompt / opening line (agent.py territory — NOT touched by this wave, but must be flagged as a compliance dependency so it is not forgotten). The registry design must at minimum carry a one-line "compliance is enforced at these THREE other choke-points, not here" note so the gap is visible, not silent.

**B3 — GAP: the spam-rotation guard can *mask* a compliance problem and delay the founder learning he's non-compliant.**
§5e auto-quarantines a DID on a 486/480/603 burst and fails over to a healthy DID. Honest failure mode: if the founder runs a campaign from an unregistered 10-digit DID (B1 not yet fixed), the carrier starts blocking → 486 burst → the rotation guard dutifully quarantines that DID and **rotates to the next 10-digit DID in the pool**, which then also gets flagged, and so on. The guard is designed for *reputation distribution*, but with a non-compliant trunk it becomes a machine for **burning through the founder's whole DID pool one number at a time** while hiding the root cause (non-compliance) behind "it auto-failed-over, looks handled". This is precisely the dynamic that got `+918071583488` blocked, now automated across N numbers. The design's own §5e caveat ("does NOT defeat entity-level scoring / substitute for DLT") is correct but understated — rotation on a non-compliant trunk is actively *harmful*, not neutral.
**FIX (required):** the rotation guard must **escalate, not just rotate**, on a sustained pattern: if ≥K DIDs on the SAME trunk quarantine within a window, do NOT keep rotating — **disable the whole trunk** and raise a loud compliance alert ("this trunk's numbers are being carrier-blocked en masse — likely a DLT/140 compliance problem, not a per-number reputation issue"). Tie this to B1: a trunk that is `is_140_series=false` should never have reached campaign dialing, but if one does, the guard must fail LOUD and STOP, not silently chew the pool.

**B4 — GAP (legal precision): "live AI agent" is NOT a settled exemption — the design leans on a soft reading.**
RESEARCH PART 5 and D3 correctly note that pre-recorded robocalls require prior consent (effectively banned) while *live real-time LLM* calls are "not yet explicitly regulated as robocalls" and TRAI is "considering amendments". The design's §8/UI implicitly treats the live-AI path as the compliant one. Honest skeptic's flag: that is a **regulatory grey area in active motion (mid-2026)**, not a green light. If TRAI's pending AI-telemarketing amendment lands (it is explicitly "under development"), a live-AI outbound call pitching a product may be reclassified, and the whole compliant path may require *additional* consent/disclosure. The design should not present live-AI as a durable legal moat.
**FIX (advisory, not blocking):** add a one-line standing note that AI-telemarketing regulation is in flux and the compliant posture (140+DLT+NCPR+9-9+disclosure) is the floor, not a ceiling — and that the AI self-disclosure opening line should be treated as MANDATORY now (the safest reading), not optional, to stay ahead of the amendment.

### Axis B summary
Flagging: **PASS — best part of the design, fully honest.** Enforcement: **PARTIAL.** The 140/DLT gate lives in prose + default-true columns, not in the `get_trunk` choke-point or a DB constraint (B1 — the critical fix). NCPR/9-9/disclosure have NO enforcement hook and risk falling between systems (B2). The rotation guard can automate non-compliance across the pool instead of stopping it (B3). And the "live AI is fine" reading is a moving grey area (B4). The design knows the law; it must now make the law **unbypassable by construction**, not merely documented.

---

## THE 5 FIXES, RANKED (gate `TRUNK_REGISTRY_ENABLED=1` in prod)

| # | Severity | Failure | Fix | Where |
|---|---|---|---|---|
| B1 | 🟥 CRITICAL | Non-compliant trunk (unregistered 10-digit) can be returned for a campaign — UI/prose block is bypassable via direct API | Gate in `registry.get_trunk(purpose='campaign')` + `is_campaign_eligible` GENERATED column / DB CHECK | `registry.py`, DDL |
| A1 | 🟥 CRITICAL | Redis `active_calls` leaks on crash/raise → trunk stuck "full" → dialer silently stops | try/finally release + self-healing sorted-set counter with TTL eviction | `concurrency.py` |
| A2 | 🟧 HIGH | Check-then-acquire TOCTOU oversells the channel cap under burst → 486 storm / DID flag | Atomic INCR-and-compare (Lua), enforce ceiling in the increment | `concurrency.py` |
| B3 | 🟧 HIGH | Rotation guard auto-rotates through the whole DID pool on a non-compliant trunk → burns every number, hides root cause | Escalate: ≥K quarantines on one trunk → disable trunk + loud compliance alert, don't keep rotating | `rotation.py` |
| A4 | 🟨 MED | `max_concurrency` lies above the box RTP ceiling (~100) until the recreate wave | Box-global concurrency cap in every acquire (`BOX_MAX_CONCURRENT ~90`) | `concurrency.py` |
| B2 | 🟨 MED | NCPR scrub / 9-9 window / AI-disclosure named but un-enforced, orphaned between registry and campaign | Name the 3 choke-points explicitly (campaign-launch / scheduler_loop / agent prompt) so none is silent | handoff note + scheduler_loop |
| A3 | 🟦 LOW | GSM trunk can ask one SIM for 2 calls via DID-rotation collision | For `gsm_gateway`: did_pool len == max_concurrency == #SIMs; per-DID in-flight==0 guard | `rotation.py` |
| B4 | 🟦 LOW (advisory) | "Live AI is unregulated" is a moving grey area | Standing note: 140+DLT+NCPR+9-9+disclosure is the FLOOR; disclosure mandatory now | design note |

**Net:** the DESIGN is honest and the architecture is right — the founder's goal is buildable and the design does not lie to him about SIMs or the law. But "the registry enforces compliance" (its own claim, §0/§9) is currently **true in prose and false in code**: the gates are default-permissive columns and UI checks, not choke-point + DB constraints. Land B1 + A1 + A2 (the three non-negotiables) and the design's promises become real; B3/A4/B2/A3/B4 close the rest. NONE require touching `agent.py` or the Vobiz config; all live in `concurrency.py` / `rotation.py` / `registry.py` / the DDL — fully consistent with the additive, earner-safe, flag-OFF-resting design law.

**END Phase: RED-TEAM [sim-concurrency-legal]**

---
---

# Phase: RED-TEAM [spam-reality] — does a personal SIM / new number ESCAPE the 486 carrier block? (opus)
**Date:** 2026-06-14
**Mode:** READ-ONLY. Adversarial pass on the DESIGN. No box/caller.py/agent.py edit. The only writes are this append + the ledger pointer.
**Grounds:** this file's RESEARCH phases (sim-to-sip, byo-providers, spam-flag, multitrunk) + DESIGN [telephony-trunk-registry] section 5e/8/9 + `MASTER_DNA_PLAN.md:57-60` (the live 2026-06-13 carrier-block on `+918071583488`).

## THE QUESTION (founder mandate — answer it plainly, no soft-pedalling)
Does the founder's personal SIM, OR a fresh new number, actually ESCAPE the 486/480/603 carrier spam-block that `+918071583488` hits today — or will mass auto-dialing simply RE-FLAG the new number (and, for a personal SIM, risk a permanent ban)? And if it does NOT escape: say so, and demand rotation + reputation-protection + volume-throttling as REQUIRED, not optional.

## THE HONEST ANSWER — NO. A new number does NOT escape it. A personal SIM is WORSE.

**Plainly: swapping the DID does not fix the problem. It RESETS A CLOCK.** The 486/480/603 block on `+918071583488` was not a fluke of that one number — it was *caused by the calling BEHAVIOUR* (per-wave automated burst test calls: high velocity, near-zero answer rate, repeated failed-call bursts, all from one un-DLT-registered 10-digit MSISDN — the exact predictive-dialer fingerprint Indian carrier anti-fraud graph-ML scores on; RESEARCH spam-flag D2 + MASTER_DNA_PLAN.md:57-60). A new number that repeats the SAME behaviour gets the SAME score and the SAME block. The carrier flags the *pattern*, then attaches the verdict to the *number* (and, increasingly, to the *entity* behind it). New number, same pattern then re-flagged. This is not a maybe; it is how the detection works.

### Five concrete failure modes, each with the fix it forces

**FM-1 — "Just use a fresh DID" then re-flagged within 24-72h.**
A new 10-digit DID starts with a *neutral* reputation, not a good one. The first burst of high-velocity, low-answer, failed-call traffic re-creates the predictive-dialer CDR signature. Industry consensus (RESEARCH spam-flag D2, subex.com graph-ML, 85% detection / under-5% FP): burst patterns flagged in **24-72 hours**; subtler ones caught by batch graph analysis within **2-4 weeks**. So a fresh DID buys *days*, not immunity. **FIX FORCED:** number rotation across a POOL is REQUIRED so no single DID accumulates the burst signature — but rotation alone only spreads the *velocity*; it does not change the *pattern class*. Rotation is necessary, NOT sufficient.

**FM-2 — Personal SIM is strictly WORSE than a CPaaS DID, on three axes.**
(a) **Ban, not block.** A CPaaS DID that gets flagged is *suspended/quarantined* — you stop using it, reputation is the provider's problem, you rotate to another. A personal-SIM ban is *permanent* (TRAI 2-year blacklist minimum, RESEARCH sim-to-sip D2) AND the gateway's behavioural pattern can flag *every other SIM on the same device* (D2). You don't lose a number; you lose the hardware's whole SIM bank. (b) **1 SIM = 1 call** (cellular physics, D1) — no concurrency, so to push *any* campaign volume you'd dial that one SIM relentlessly = the fastest possible path to the ban. (c) **It's illegal anyway** — a consumer SIM cannot present a 140-series CLI; promotional calls from a 10-digit MSISDN violate TRAI TCCCPR (RESEARCH sim-to-sip D3/D4). **FIX FORCED:** the design's HARD RULE — `gsm_gateway` trunks are manual-trigger-only, NEVER in the campaign pool (DESIGN 8.3, 9) — is CORRECT and must stay non-negotiable. A personal SIM is for ONE manual high-trust recall, never a dialer.

**FM-3 — Carrier scoring is moving to ENTITY level, so rotation has a ceiling.**
DoT/TRAI 2025 enforcement (RESEARCH sim-to-sip D2: 4M SIMs deactivated, 21 lakh numbers + 1 lakh *entities* blacklisted) increasingly scores the *entity/route*, not just the MSISDN. Graph ML links numbers that share calling patterns, destination lists, and origin routes. Once the *entity* (the SIP route / the business behind the DIDs) is scored bad, rotating DIDs underneath it is rearranging deck chairs — the new DIDs inherit the route's bad reputation faster. **FIX FORCED:** the ONLY durable escape is to change the *legal class of the traffic* — i.e. DLT-registered 140-series origination (DESIGN 8.1). Rotation + reputation-protection keep you alive *underneath* a compliant route; they cannot substitute for one. The DESIGN already says this (5e "mitigation, not a bypass"; 8 one-line truth) — RED-TEAM CONFIRMS it and sharpens it: **without the 140/DLT route, every mitigation only delays the inevitable re-flag.**

**FM-4 — The `scheduler_loop` retry bug would AMPLIFY the flag across the whole pool.**
This is the single most dangerous interaction and the DESIGN flags it (9, 10 T0) but RED-TEAM elevates it to a BLOCKER. The live retry bug re-fires dead/486 numbers. Turn on rotation *with that bug still present* and you don't fix anything — you take the burst-of-failed-calls signature (the exact thing that flagged `+918071583488`) and *multiply it across every DID in the pool simultaneously*, getting the entire pool flagged in one campaign instead of one number. **FIX FORCED (hard gate):** T0 `scheduler_loop` retry-bug fix is a PREREQUISITE, not a nicety — `TRUNK_REGISTRY_ENABLED` outbound rotation MUST NOT be enabled until it ships and is verified. Add to the design's enable-checklist: *"rotation stays OFF until the retry bug is proven fixed (no re-dial of a 486/480/603 number)."*

**FM-5 — Low answer rate is itself a flag input, and a flagged route makes it worse (death spiral).**
Answer rate is a primary carrier suspicion signal (RESEARCH spam-flag D2). A flagged number rings as "Spam Likely" / gets silently throttled then answer rate drops further then score worsens then more DIDs in the pool pick up the pattern. Rotation that only round-robins *blindly* feeds healthy DIDs into a bad-pattern campaign and burns them too. **FIX FORCED:** rotation must be *reputation-AWARE* (skip quarantined DIDs — DESIGN 5e already does this) AND velocity must be *throttled* (per-DID daily cap under 100, plus a per-DID inter-call spacing / calls-per-hour ceiling — see "what's MISSING" below). Volume-throttling is REQUIRED, not optional.

## VERDICT ON THE THREE MITIGATIONS — all three are REQUIRED, not optional
The founder mandate asked: if a new number does not escape the block, demand these as required. RED-TEAM does exactly that:

1. **NUMBER ROTATION — REQUIRED.** Without it, one DID accumulates the burst signature and dies (FM-1). The design's `did_pool[]` + Redis round-robin (`rotation.pick_did`) is correct. *Sharpening:* rotation must be reputation-aware (skip `quarantined_until` DIDs) and must NOT blindly feed fresh DIDs into a known-bad campaign (FM-5).
2. **REPUTATION-PROTECTION (auto-rest / quarantine) — REQUIRED.** Without it, a flagged DID keeps dialing, deepens its own block, and drags the pool down (FM-5). The design's `rotation.note_result` then 486/480/603 burst then `quarantined_until` + failover is correct. *Sharpening:* quarantine should trigger on a *low* threshold (a handful of consecutive 486/480/603, not dozens) because the carrier scores fast; and quarantine should be PER-DID *and* escalate to PER-TRUNK/route if multiple DIDs on one trunk flag together (entity-level signal, FM-3).
3. **VOLUME-THROTTLING — REQUIRED.** Without it, even a rotating, reputation-aware pool dials fast enough to paint the dialer signature (FM-1, FM-5). The design's `per_did_daily_cap` (default 75, under 100) is a start. *Sharpening — what's MISSING in the design and must be added:* a **calls-per-hour / inter-call-spacing throttle per DID** (a daily cap of 75 dialed in 10 minutes still looks exactly like a predictive dialer). Daily cap limits *total* volume; it does NOT limit *velocity*. Velocity is the stronger flag signal. **ADD to `rotation.py`/`concurrency.py`:** a per-DID minimum inter-call gap + a per-DID calls-per-hour ceiling, so the traffic shape resembles human telecalling, not a burst.

## THE ONE TRUTH FOR THE FOUNDER (say it plainly)
**A new number does not escape the 486 block, and a personal SIM is the worst possible choice — it gets permanently banned and it's illegal for campaigns. The block follows your calling BEHAVIOUR, not the digits. The registry's rotation + auto-rest + throttling keep you ALIVE and BUY TIME, but they are survival gear UNDERNEATH a compliant route — they are not a way around the rules. The only real, durable escape from the spam-block is to send your promotional traffic the legal way: a 140-series DID on a DLT-registered route (the 8.1 founder-buy). Build the rotation/reputation/throttle machine (it's required either way), but understand it is the seatbelt, not the engine. The engine is the 140/DLT registration.**

## CONCRETE ADDITIONS THIS RED-TEAM FORCES INTO THE BUILD
- **HARD GATE:** `TRUNK_REGISTRY_ENABLED` outbound rotation stays OFF until the T0 `scheduler_loop` retry bug is shipped AND verified (no re-dial of a 486/480/603 number). Bake this into the T5 enable-checklist (FM-4).
- **NEW throttle layer (missing from the design):** per-DID inter-call spacing + calls-per-hour ceiling in `rotation.py`, on top of `per_did_daily_cap`. Velocity, not just volume (FM-5).
- **Quarantine on a LOW threshold** (few consecutive 486/480/603, not many) + **escalate per-DID to per-trunk/route** when multiple DIDs flag together (FM-3, FM-5).
- **Reputation-aware rotation:** never feed a fresh DID into a campaign that is already throwing 486s on its other DIDs (FM-5).
- **UI honesty (already in 7):** keep the explicit "this rotates/rests but does NOT make non-140 traffic compliant" note on the campaign-enable path; block un-DLT trunks from the campaign pool (DESIGN 8.2 / 9 row).
- **No new auto-originate:** the ONLY non-campaign call this system places remains the explicit founder-typed test-call (DESIGN 6) — RED-TEAM confirms nothing here should auto-dial to "warm up" a number; warming a non-compliant number is just flagging it slower.

## BOTTOM LINE
The DESIGN is sound and HONEST about this already (5e, 8, 9). RED-TEAM does not overturn it — it CONFIRMS the uncomfortable truth and makes three things non-negotiable that were arguably presented as features: rotation, reputation-protection, and volume-throttling are REQUIRED survival infrastructure, not optional polish; the scheduler retry-bug fix is a hard prerequisite gate; and a velocity (calls/hour + inter-call spacing) throttle must be ADDED — `per_did_daily_cap` alone is insufficient. None of these escape the block. Only DLT-registered 140-series origination does. Build the machine; the founder must buy the fuel.
**END Phase: RED-TEAM [spam-reality]**

---
---

# Phase: RED-TEAM [earner-safety-reliability] — adversarial review of the DESIGN (opus, READ-ONLY)
**Date:** 2026-06-14
**Mode:** READ-ONLY. No box/caller.py/agent.py edit; Vobiz config untouched. The ONLY writes are this section + the ledger pointer.
**Method:** every claim re-checked against the LIVE code on disk (`droplet_work/caller.py` 7919 lines, `droplet_work/provider_registry/health.py`, `droplet_work/ratelimit.py`), not against the design's self-description. Skeptical by mandate: surface concrete failure modes + the exact fix each demands.

## VERDICT (one line)
The CORE architecture is SOUND and genuinely additive — but the design has **three real, code-grounded defects** (a phantom SIP-code the spam-guard depends on, a Redis dependency that contradicts the live fail-open posture, and a misread of the live single-worker concurrency model) plus **two safety gaps in the rollout** (no per-DID kill switch independent of the master flag, and `livekit_sync` create/delete mutating the SAME LiveKit the live earner dials through is NOT as risk-free as "no container restart" implies). None are fatal; each is fixable before BUILD. Fix them or the spam-rest guard is theater and T5 can wobble the live trunk.

## A. WHAT THE DESIGN GOT RIGHT (verified against code — keep)
- **Additive + flag-gated is REAL.** `caller.py:184 TRUNK = cfg_get("LIVEKIT_SIP_TRUNK_ID","ST_fmtVmNJmpzKa")` and the dial at `:2913 create_sip_participant(sip_trunk_id=TRUNK, ...)` are exactly where the strangler cuts; flag-OFF leaves `TRUNK` untouched = byte-identical. CONFIRMED.
- **agent.py never imported.** The registry rides caller.py only; the earner's voice loop is untouched. CONFIRMED (the founder's #1 infra lesson honored).
- **Vobiz imported as one `_global` row -> flip-on = same dial.** Correct strangler discipline; the live `ST_fmtVmNJmpzKa` is reused, not replaced.
- **The honest compliance truth is correct and load-bearing.** 1-SIM=1-call, 140-series+DLT mandatory, gsm_gateway manual-only, the founder-buy list — all accurate and properly surfaced. This is the most valuable part of the design and must NOT be softened.
- **The credentials/ssrf/health REUSE is legitimate** — `provider_registry/` exists with exactly those files; cloning the AAD-AES-GCM + FORCE-RLS + circuit-breaker pattern is proven, not invented.

## B. DEFECT 1 (BLOCKER for the spam-guard) — the `sip_code` the rotation guard fires on DOES NOT EXIST on the hot path
**Ground truth:** the dial loop calls `create_sip_participant(..., wait_until_answered=False, ringing_timeout=45)` (`caller.py:2916`) and **returns immediately** — it only reads back `sip_call_id` (`:2917`). The call OUTCOME is learned LATER, and NOT from a SIP code: `_classify_outcome` (`:1551`) infers `no_answer`/`voicemail`/`answered` from **call duration + transcript** (`dur < 8 -> no_answer`), never from SIP 486/480/603. There is **no 486/603/480 captured anywhere** in caller.py (grep: zero hits outside HTTP status strings).
**Why it breaks the design:** Sec 5e's entire spam-reputation guard is `rotation.note_result(trunk, did, sip_code)` reacting to "a burst of 486/480/603 (the carrier-block fingerprint)". That `sip_code` is a **phantom** — the code path that would supply it does not exist. As written, the quarantine guard would NEVER fire, because nothing ever passes it a 486/603. The spam-rest feature is non-functional on the real call path.
**The fix BUILD must include (not optional):** to get SIP disconnect codes you must EITHER (a) register a **LiveKit SIP webhook / participant-disconnected event** and map `DisconnectReason`/SIP status into `note_result` — this is NEW plumbing the design omits — OR (b) derive a *proxy* signal from the existing duration/answered classification (e.g. a burst of `no_answer` with `dur==0` ring-outs per DID approximates a carrier block) and quarantine on THAT. Option (b) is cheaper and uses signals that already exist (`_classify_outcome` + `_finalize_call` at `:2705`), but it is a DIFFERENT, weaker signal than the design claims. The design must be corrected to say "quarantine on a burst of zero-duration ring-outs per DID" — NOT on SIP 486/603 it cannot see. **Do not ship the guard described; ship the guard the data supports.**

## C. DEFECT 2 (architecture mismatch) — Redis concurrency/rotation contradicts the LIVE fail-open posture AND the twin it claims to clone
**Ground truth (three facts):**
1. The live box runs **uvicorn `--workers 1`** (`ratelimit.py:13` "the live config: --workers 1"). So today's in-proc `ACTIVE_CALLS` dict (`caller.py:535`, "Source of truth for active SIP calls") is CORRECT precisely because there is one process. There is no multi-worker race to solve yet.
2. The Redis at `:6380` is the **rate-limiter Redis**, and the codebase treats it as **FAIL-OPEN / best-effort / per-worker** by explicit design ("this must NEVER block real traffic", returns `redis_error_failopen` on any Redis fault — `ratelimit.py:3-13,133`). `_hc_redis` marks it a **soft/degraded** dependency, never fatal (`caller.py:2972,3005`).
3. The **twin the design claims to clone does NOT use Redis at all.** `provider_registry/health.py:1` is an **in-memory circuit breaker** — a process-local `_CircuitState` map + lock (`:49`), "ZERO network I/O ... never a PG hit on the hot path." grep for redis in `provider_registry/` = **zero hits**.
**Why it is a defect:** Sec 4/Sec 5d put the per-trunk concurrency counter AND the DID round-robin index on that fail-open Redis. But concurrency enforcement that "never blocks on a Redis problem" = a concurrency cap that **silently disappears** when Redis hiccups -> the design's headline "never exceed the channel cap" becomes "exceed the cap whenever Redis is degraded" -> SIP 486 storm + carrier-reputation damage — the exact failure the guard exists to prevent. Calling `concurrency.py` a clone of the twin is also FALSE: the twin is in-memory; this is net-new Redis infra.
**The fix:** (1) Keep concurrency in the SAME place the live system already does — the **in-process counter** (extend the proven `ACTIVE_CALLS` pattern to a per-trunk dict). It is correct under `--workers 1` and needs ZERO new dependency. Only move to Redis IF/when the box goes multi-worker — and then it must be **fail-CLOSED** for the concurrency CAP (degraded Redis -> fall back to a conservative in-proc cap, never "unlimited"). (2) Same for the DID rotation index: an in-proc round-robin counter is fine under one worker; Redis is premature. (3) Correct the design text: `concurrency.py`/`rotation.py` are **NEW** modules, NOT clones of the in-memory twin — and concurrency must be fail-closed, opposite to the rate-limiter's fail-open.

## D. DEFECT 3 (live-trunk risk understated) — `livekit_sync` create/delete mutates the SAME LiveKit the earner dials through
**Ground truth:** the design repeatedly reassures "NO container restart — pure API" (Sec 4 livekit_sync, Sec 5a, Sec 9). True — but "no restart" does NOT equal "no risk." `livekit_sync.delete` removes an `ST_<id>` **object** from the running LiveKit-SIP, and the live earner's outbound trunk (`ST_fmtVmNJmpzKa`) lives in that SAME LiveKit instance. A bug, a wrong id, a super-admin misclick, or a DELETE on the imported `_global` Vobiz row would **delete the live earner's trunk out from under in-flight and future campaigns** — no restart needed to break it.
**The fix BUILD must include:** (1) **Protect the imported Vobiz/`_global` rows from DELETE** — `livekit_sync.delete` must refuse to delete any `livekit_trunk_id` that equals the env `LIVEKIT_SIP_TRUNK_ID` (and any `tenant_id='_global'` trunk), returning a hard error. (2) Inbound: the existing AIM inbound (`ST_K785ASpNh5ow` -> agent `manager`) and the live dispatch rules are equally deletable — same protection. (3) The DELETE path should **soft-disable** (`is_enabled=false` + LiveKit trunk left in place) by default, with hard-delete a separate, audited, PIN-gated super-admin action. "Pure API" is the reassurance; "can't touch the earner's objects" is the guarantee that's missing.

## E. SAFETY GAP 1 — no per-DID / per-trunk KILL SWITCH independent of the master flag
**Issue:** the only OFF switch in the design is the master `TRUNK_REGISTRY_ENABLED` (all-or-nothing) plus per-trunk `is_enabled`. If, AFTER T5 flag-ON, one rotated DID starts getting the campaign flagged in real time, the founder's only fast lever is to flip the master flag OFF (drops the whole registry back to legacy) or edit a DB row. There is no "rest this number NOW" that takes effect on the **next dial** without a deploy.
**The fix:** the design DOES mention a manual "rest this number / release" toggle in the FE spam panel (Sec 7) — make it a FIRST-CLASS, real-time backend control: a `POST /trunk-registry/trunks/{id}/quarantine-did {did}` that sets `quarantined_until` and is read by `get_trunk` on the very next selection (already the design's read path) — and verify the FE wires it. Plus a documented one-flag instant revert (`TRUNK_REGISTRY_ENABLED=0` -> legacy Vobiz, byte-identical) as the big red button. Make both explicit in the BUILD acceptance, not just a UI bullet.

## F. SAFETY GAP 2 — the founder test-call is the right idea, but its blast radius needs nailing down
**Issue:** Sec 6's `/test-call` is correctly the ONLY non-campaign originate (good — auto-test-dials are exactly what spam-flagged the DID). But: it dials whatever number the founder types THROUGH a possibly-unverified, possibly-non-140 trunk. A test call from a non-compliant 10-digit DID still hits the carrier and still accrues reputation against that DID. One test is fine; the risk is a founder hammering "Test" 20 times while debugging.
**The fix:** rate-limit `/test-call` HARD (e.g. <=3/hour/trunk, server-side, reusing the existing `ratelimit.py` seam), require the destination to be a number the founder controls (a confirmed-own list), and count test calls against `per_did_daily_cap` like any other call. State this in the design so BUILD enforces it.

## G. THINGS THE DESIGN UNDER-SPECIFIED (fix in BUILD, not blockers)
- **`_finalize_call`/`concurrency.release` placement:** the design says "release at caller.py:2844". `:2844` is the `ACTIVE_CALLS ... -1` decrement INSIDE `_finalize_call`'s caller (`:2845`). Correct region, but the design must release in the SAME finally/decrement touch-point as `ACTIVE_CALLS`, or a crashed call leaks a held channel forever (the classic counter-leak). Pair acquire/release with the EXISTING ACTIVE_CALLS lifecycle, do not add a parallel one.
- **Multi-tenant inbound DID collision:** two tenants cannot own the same DID; the design's dispatch-rule-per-DID is right, but BUILD needs a UNIQUE guard on `did_pool` membership across tenants (a DID can live in exactly one tenant's inbound trunk) or inbound routing is ambiguous.
- **Cost truth:** `cost_per_minute_paise` is stored but nothing in the design DEBITS the wallet per trunk-minute. If trunks have different per-minute costs (Vobiz 45p vs Plivo 60p vs 140-series higher), the existing billing meter must read the SELECTED trunk's rate, else metering is wrong the moment a 2nd trunk goes live. Wire trunk-cost -> the wallet/usage meter in the same BUILD wave that enables rotation.

## H. THE SAFE ROLLOUT I DEMAND (replaces/sharpens Sec 10)
- **T0** (unchanged, mandatory): fix the queued `scheduler_loop` retry bug FIRST — else rotation amplifies dead-number redials across more DIDs (design already flags this in Sec 9; agreed, it is a hard prerequisite).
- **T1 DDL + seed** Vobiz `_global` row — DB-only, zero box risk. ADD: a CHECK/trigger or app-guard so the `_global` Vobiz `livekit_trunk_id` can never be hard-deleted (Defect D).
- **T2 package, flag OFF** — ship; concurrency/rotation as **in-process** counters (Defect C), spam-guard keyed on **zero-duration ring-out bursts** not phantom SIP codes (Defect B). Resting byte-identical.
- **T3 mount, flag OFF** — additive guarded mount; `/test-call` rate-limited (Gap F); DELETE soft-disables + protects `_global`/env trunk (Defect D).
- **T4 FE** to FORTRESS — including the real-time per-DID quarantine button (Gap E).
- **T5 strangler flag-ON, staged:** (1) integrated smoke — a REAL outbound call rings via the registry-resolved Vobiz row (= today's trunk) BEFORE and AFTER the flag flip, proving zero regression, agent.py md5 unchanged, famit-agent PID NOT restarted, /health 200, 0 5xx; (2) ONLY THEN enable DID rotation within the single Vobiz trunk; (3) ONLY AFTER the founder buys a compliant 140/Plivo trunk, enable cross-trunk routing. One box-mutating step at a time; the master flag is the instant revert at every step.

## I. RED-TEAM BOTTOM LINE
The design is **buildable and earner-safe in skeleton** — additive, flag-gated, agent.py-free, Vobiz-preserving. But three claims are **not true against the live code**: (1) the spam-rest guard fires on a SIP code the hot path never captures; (2) the Redis concurrency/rotation is net-new fail-open infra mislabeled as a clone of an in-memory twin, and fail-open is WRONG for a hard cap; (3) "pure API, no restart" understates that `livekit_sync` can delete the live earner's own trunk object. Fix B/C/D before BUILD, add the per-DID kill switch + test-call rate-limit, wire trunk-cost to the meter, and the rollout in Sec H is safe. Approve to BUILD **conditional on those corrections** — do NOT build the guard/concurrency exactly as the DESIGN text describes them.
**END Phase: RED-TEAM [earner-safety-reliability]**

---
---

# Phase: SYNTHESIZE [telephony-independence-master-plan] (opus)
**Date:** 2026-06-14
**Mode:** READ-ONLY synthesis. The ONLY writes are the master plan + pointers. No box / caller.py / agent.py mutation; Vobiz config left as-is.

Folded the DESIGN [telephony-trunk-registry] + the 4 RED-TEAMs (spam-reality, sim-concurrency-legal, earner-safety-reliability) into the decision-ready master plan: **`design/TELEPHONY-INDEPENDENCE-PLAN.md`**.

## What the master plan contains
- **§0 Honest reality** (4 facts: SIM-to-SIP needs a gateway-or-BYO-provider; 1-SIM=1-call; a fresh DID does NOT escape the spam-flag — it resets a clock, the block follows the BEHAVIOUR not the digits; a personal SIM is worse + illegal). The one-line truth: code = technical independence today; legal India-scale independence = a 140/DLT regulation purchase the registry ENFORCES not bypasses.
- **§1 Exec summary** (~25 lines).
- **§2 Architecture** — trunk_registry = column-for-column clone of the LIVE provider_registry; 3 FORCE-RLS tables; pkg with REUSED credentials/ssrf/health + NEW livekit_sync/rotation/IN-PROCESS concurrency; strangler at caller.py:184/:2913; Vobiz `_global` un-deletable row.
- **§3 RED-TEAM FIXES table** — every defect→fix, gating `TRUNK_REGISTRY_ENABLED=1`:
  - **B1 (BLOCKER):** `is_campaign_eligible` GENERATED column + `get_trunk(purpose='campaign')` gate (unbypassable; was prose-only).
  - **B-rel (BLOCKER):** the spam-rest guard fired on a 486/480/603 caller.py NEVER captures (`wait_until_answered=False` :2916, outcome inferred from duration+transcript :1551) → quarantine on **zero-duration ring-out bursts** (signal exists) OR add NEW LiveKit SIP-webhook plumbing. Do NOT ship the guard as the original text described.
  - **C-rel (BLOCKER):** concurrency must be **IN-PROCESS** (box is uvicorn `--workers 1`, in-proc ACTIVE_CALLS :535 is already correct) — the proposed `:6380` Redis is the rate-limiter's FAIL-OPEN redis so a hard cap on it silently vanishes → 486 storm. This also dissolves A1 (leak) + A2 (TOCTOU) — an in-proc counter under one worker has neither. Pair acquire/release with the existing ACTIVE_CALLS finalize touch-point (:2844) in try/finally.
  - **D (HIGH):** `livekit_sync.delete` hits the SAME LiveKit the earner dials → refuse DELETE of env `LIVEKIT_SIP_TRUNK_ID` + any `_global`/AIM-inbound trunk, default soft-disable, hard-delete PIN-gated+audited.
  - **HARD-GATE:** rotation OFF until the live `scheduler_loop` retry bug is fixed+verified (else it multiplies the failed-call signature across the whole pool) — this is **T0** of the roadmap.
  - **NEW velocity throttle** (per-DID inter-call spacing + calls/hour ceiling — `per_did_daily_cap` limits volume not velocity, and velocity is the stronger flag signal).
  - **B3:** ≥K quarantines on one trunk → DISABLE the trunk + loud alert, stop rotating (don't auto-burn the whole DID pool one number at a time).
  - **E/F/A3/A4/B2/B4:** per-DID kill switch `POST /quarantine-did`; `/test-call` rate-limit ≤3/hr/trunk founder-dest; gsm did_pool==max_concurrency==#SIMs guard; box-global ~90 cap; name the NCPR/9-9/AI-disclosure choke-points; AI self-disclosure mandatory now.
- **§4 FE** (Core_2 telephony page). **§5 Phased roadmap** (T0→T5, each scope/files/flag/acceptance/rollback; T5 acceptance = a real founder outbound ring via the registry-resolved Vobiz row before+after). **§6 Risks. §7 Founder actions** (fastest-path table BYO-SIP > GSM + the buy list: 140/DLT non-negotiable, Plivo 2nd trunk, GSM niche-only). **§8 Files + flags.**

## Earner-safety VERIFIED (re-checked vs live code, not self-description)
Flag-OFF byte-identical (caller.py:184 TRUNK / dial :2913); agent.py 9150fabe never imported; Vobiz `_global` row reused not replaced. Vobiz config files untouched.

## Pointers appended
`NEXT-BIG-BUILDS.md` #9c · `ORCHESTRATOR.md` (newest-on-top) · `WORKFLOW_LEDGER.md` (one line) · this file.

**NEXT BUILD when queued:** T0 (scheduler retry-bug fix) → T1 (DDL + Vobiz `_global` seed). One box-mutating wave at a time; serialize caller.py vs RAG/Vault/Registry/Video.
**END Phase: SYNTHESIZE [telephony-independence-master-plan]**
