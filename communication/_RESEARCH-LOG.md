# COMMUNICATION OMNICHANNEL — EXPLORATION RESEARCH LOG

**Date:** 2026-06-14  
**Task:** Explore media-handling patterns to ground Communication Omnichannel (Telegram + Email + SMS) design.  
**Status:** READ-ONLY exploration complete. HAVE vs GAP summary follows.

---

## LIVE MEDIA PATTERNS (WhatsApp + AI Asset Service)

### 1. WhatsApp Banner Upload: DO Spaces → Meta Resumable Upload → header_handle
**File:Line:** droplet_work/whatsapp_builder/meta_submit.py:142-174

- **Step 1:** Banner bytes → DO Spaces boto3 put_object (provenance, line 76-98)
- **Step 2:** Bytes → Meta Resumable Upload API → extract header_handle (line 101-139)
- **Step 3:** header_handle → template submission JSON → POST /{WABA_ID}/message_templates (line 176-193)
- **Dormancy:** All layers return graceful {ok:False, status:"not_configured"} when creds absent
- **Key fact:** Meta accepts header_handle (NOT raw URL) for template headers

### 2. Post-Call Auto-Send Hook + Template Delivery
**File:Line:** caller.py:1873 _finalize_call() → line 1932 _wa_ai_followup()

- **Gate:** per-campaign ields.wa_followup (default False, so dormant today)
- **Template:** Approved "post_call_followup" with 2 vars (name, product)
- **Send:** via send_whatsapp_async(to, template_name, [var1, var2])
- **Missing:** PDF brochure field (schema supports IMAGE/VIDEO/DOCUMENT headers, not yet wired)

### 3. AI Asset Presigned URL Pattern
**File:Line:** media_gen/spaces.py:126-139 signed_url(key, expires_s=3600)

- Image/video → stored to Spaces (i_asset_* table tracks spaces_key)
- Panel reads asset → presigns GET for 1 hour
- Attach presigned URL to message (WhatsApp, Email, SMS, Telegram)

### 4. Inbound Recording Egress → Presigned Read
**File:Line:** droplet_work/aim_p1/ai_manager/recorder.py:95-200

- LiveKit Egress → direct S3 upload to DO Spaces (no local disk)
- Session stores bucket/key
- Panel presigns GET for 1-hour URL retrieval

### 5. Provider Registry Foundation (DESIGN DONE, NOT IMPLEMENTED)
**File:Line:** design/PROVIDER-FRAMEWORK-PLAN.md (entire file is the spec)

- Capability-based resolution: egistry.get_provider(tenant_id, capability='sms'|'email'|'tg')
- Per-tenant encrypted credentials (FORCE-RLS, AAD-bound AES-256-GCM)
- 3-tier adapter: openai_compat / named_provider / custom_field_map (JSONPath)
- **THE FOUNDATION for "add Telegram token / SendGrid key / Twilio auth per tenant via UI"**

---

## HAVE — Reusable Components

| Component | Status | Reuse for Telegram/Email/SMS |
|---|---|---|
| Presigned URL gen | ✅ Complete | Attach banner/brochure to any channel |
| Template generation (LLM) | ✅ Complete | Email subject+body, SMS body, Telegram caption |
| Post-call hook | ✅ Wired | Route to each channel's send function |
| Reply brain (Groq) | ✅ Complete | Email/SMS/Telegram inbound parser + conversation |
| Provider abstraction | ✅ Pattern exists | Model Telegram/Email/SMS as Provider subclasses |
| Wallet + audit | ✅ Complete | Meter Email/SMS cost, Telegram free |
| RLS + per-tenant isolation | ✅ Complete | Extend to communication_* tables |

---

## GAP — What's Missing

| Gap | Notes |
|---|---|
| **Telegram bot framework** | Token mgmt, HTTP POST adapter, message delivery, inline buttons, inbound webhook |
| **Email service adapter** | SendGrid/SES request/response, MIME multipart, reply-to parsing |
| **SMS service adapter** | Twilio/Exotel, GSM7 encoding, URL shortening, DLT template ID gate |
| **Unified inbound router** | Parse Telegram/Email/SMS webhook formats → route to per-channel reply |
| **Founder hot-lead alert (CRITICAL)** | INSTANT Telegram notification when interest ≥70 (NOT deferred) |
| **Per-channel consent model** | Lead opts in to WA but not SMS; track separately |
| **PDF brochure deployment** | WeasyPrint exists in design, not deployed; per-channel attachment/inline/link |
| **Communication schema** | communication_templates, communication_send_log, communication_sessions (FORCE-RLS) |

---

## KEY INSIGHT: The Founder's 99%

The founder asked: "After-a-call AUTO-message the contact with their summary, HOT-LEAD auto-alert (phone + summary) to the founder Telegram."

**What this means:**
1. Contact receives: approved template with call recap + next steps (via WA/Email/SMS)
2. Founder receives: INSTANT Telegram notification (not email, not SMS — Telegram because it's the unblocked path, no Meta verification needed)

**This is TWO different communication streams:**
- **Downstream:** Contact-facing (delayed, batched, auto-followup templates)
- **Upstream:** Founder-facing (instant, real-time alert, "interrupt me if a hot lead calls")

**Current code has (1) wired but dormant (gate=False on all campaigns); (2) is missing entirely.**

---

## FILE:LINE INDEX (REUSE PATTERNS)

- media_gen/spaces.py:26-28 — is_configured() dormancy pattern
- media_gen/spaces.py:76-97 — put_bytes() (for brochure storage)
- media_gen/spaces.py:126-139 — signed_url() presigned GET
- whatsapp_builder/meta_submit.py:76-98 — _spaces_put_bytes() (banner to Spaces)
- whatsapp_builder/meta_submit.py:101-139 — _resumable_upload_handle() (Meta file upload)
- whatsapp_builder/__init__.py:155 — attach_banner() (asset → template header)
- caller.py:1873 — _finalize_call() (post-call hook, fires on every call end)
- caller.py:1932 — calls _wa_ai_followup() (auto-send trigger)
- caller.py:1518 — _wa_reply_text() (inbound reply brain: Groq + history)
- im_p1/ai_manager/recorder.py:95-200 — LiveKit Egress → DO Spaces pattern
- design/PROVIDER-FRAMEWORK-PLAN.md — entire file (provider registry spec)

---

## PHASE: MEDIA-DELIVERY-CHANNELS — Telegram / Email / SMS
**Date:** 2026-06-14  
**Scope:** Sending banner image + video + PDF brochure across all three channels. Exact limits, supported types, best practices. Sourced from official docs + 2026 industry references.

---

### 1. TELEGRAM — Native Media Delivery (sendPhoto / sendVideo / sendDocument)

**Verdict: Telegram is the richest, cheapest, most reliable channel for rich media. Zero cost, no carrier gatekeeping, no DLT, no delivery variability.**

#### File upload methods (three paths, different limits)
| Path | Photos | All other files |
|---|---|---|
| Direct upload (multipart/form-data) | 10 MB max | 50 MB max |
| HTTP URL (Telegram pulls it) | 5 MB max | 20 MB max |
| file_id (already on TG servers) | Unlimited | Unlimited |
| Local Bot API server (self-hosted) | 2 GB | 2 GB |

**Our path:** Store asset in DO Spaces → generate presigned URL → pass URL to Bot API. This hits the HTTP URL path: **5 MB for photos, 20 MB for documents/video**. For banners (typically <500 KB) and PDF brochures (typically <5 MB), the presigned URL path is sufficient. For large promotional videos (>20 MB), upload via multipart/form-data directly (stream bytes from Spaces to Telegram).

#### Per-method breakdown
| Method | Use case | Key constraint |
|---|---|---|
| `sendPhoto` | Banner image (JPEG/PNG) | 10 MB upload / 5 MB via URL; width+height ≤ 10,000 total |
| `sendVideo` | Promotional video (MP4 only) | 50 MB upload / 20 MB via URL; MP4 required (other formats → sendDocument) |
| `sendDocument` | PDF brochure, any file type | 50 MB upload / 20 MB via URL; no format restriction |
| `sendAnimation` | GIF / H.264 no-audio loop | 50 MB upload |
| `sendMediaGroup` | Bundle up to 10 media items | Same per-item limits; one caption per group |
| `sendAudio` | Audio message | OGG/OPUS, MP3, or M4A |

#### Caption limits
- **1,024 characters** for all media captions (sendPhoto, sendVideo, sendDocument, sendAnimation).
- **4,096 characters** for plain text messages (`sendMessage`).
- **Strategy:** For post-call summaries (longer text), send a plain `sendMessage` first, then a separate `sendDocument` with the PDF brochure attached. Do NOT try to fit a long summary into a media caption.

#### Inline buttons (critical UX feature)
- `InlineKeyboardMarkup` attaches clickable buttons below any message.
- Use for: "Book a Call", "View Brochure", "Talk to AI", "Confirm Interest".
- Callback_data max: 64 bytes per button.
- Buttons trigger webhook callbacks → route to the LLM conversation brain.

#### Telegram hot-lead alert pattern (founder-facing)
- Bot sends to the **founder's personal chat_id** (stored per-tenant as `founder_telegram_chat_id`).
- Message: call summary + lead score + inline "Call Now" button (tel: link).
- No approval, no Meta verification, instant delivery. This is THE unblocked path.
- **Source:** [core.telegram.org/bots/api](https://core.telegram.org/bots/api)

---

### 2. EMAIL — MIME Multipart, Attachments, Inline Images

**Verdict: Email is the highest-trust channel for brochures and formal follow-ups. Use hosted CDN images (not CID/Base64 embed). Attach PDF only for transactional 1:1 messages; use a link for marketing blasts.**

#### Provider size limits
| Provider | Total message size limit | Notes |
|---|---|---|
| SendGrid | 20–30 MB total (incl. all attachments + body + headers) | 30 MB on paid plans via smtp.sendgrid.net |
| AWS SES v2 | **40 MB** total | Best-in-class; SES v1 was 10 MB |
| Gmail (recipient) | 25 MB received | Sender-agnostic; applies regardless of ESP |
| Outlook (recipient) | 20–25 MB received | Varies by tenant policy |

**Critical:** Base64 MIME encoding inflates file size by **33–40%**. A 15 MB PDF becomes ~21 MB on the wire. Design rule: **keep total email (body + all attachments) under 10 MB**; above that, send a hosted link.

#### Banner image in email — three methods ranked
| Method | Compatibility | Deliverability | Recommended |
|---|---|---|---|
| **Hosted CDN URL** (`<img src="https://...">`) | Gmail, Outlook, Apple Mail, all webmail | Best — small email size | **YES — default** |
| CID embed (Content-ID multipart/related) | Good in desktop clients (Outlook), poor in webmail | Raises spam flags on some filters | Only for Outlook-heavy B2B |
| Base64 inline | Works everywhere technically | Blocked by Outlook entirely; inflates size; flags spam | **NEVER** |

**Implementation:** Banner → DO Spaces → generate a **permanent public URL** (not presigned, which expires) for email embeds. Or generate a long-lived (30-day) presigned URL and regenerate before send. MIME structure for inline image: `multipart/related` (NOT `multipart/mixed` — AWS SES docs note `multipart/mixed` is technically incorrect for CID-referenced inline images).

#### PDF brochure in email
- **Transactional / 1:1 follow-up** (e.g., post-call to a hot lead): **Attach directly** if <5 MB. Spam risk low because it's a triggered, 1:1 email with high engagement signals.
- **Marketing blast / template** (e.g., campaign drip): **Host and link** — attach nothing. "Sending PDF files attached to marketing emails harms deliverability." One operator saw 40% deliverability improvement after switching to hosted link.
- **Our post-call auto-message** = transactional (1:1, triggered), so attachment is acceptable for <5 MB brochures; use link for larger.

#### SPF/DKIM/DMARC (compliance — non-negotiable)
- Must configure SPF record + DKIM signing on the sending domain (`mail.famit.in` or subdomain).
- SendGrid and SES both provide DKIM signing; requires DNS record setup per tenant's verified sender domain.
- **Per-tenant verified sender domain** required for multi-tenant (each tenant sends from their own domain, not famit.in).

- **Sources:** [smtp2go.com attachment size guide](https://www.smtp2go.com/blog/the-goldilocks-theory-of-email-file-sizes/), [fileza.io limits guide](https://fileza.io/articles/email-attachment-size-limits-guide), [AWS SES 40MB announcement](https://aws.amazon.com/about-aws/whats-new/2022/04/amazon-ses-v2-supports-email-size-40mb-inbound-outbound-emails-default), [Twilio/SendGrid CID guide](https://www.twilio.com/en-us/blog/insights/embedding-images-emails-facts), [mailmodo embed guide](https://www.mailmodo.com/guides/embed-image-in-email/), [mailpool cold email 2026](https://www.mailpool.ai/blog/cold-email-attachments-vs-links-whats-safe-in-2026-and-whats-not)

---

### 3. SMS / MMS — Media Delivery

**Verdict: SMS is the most constrained channel. MMS image support is reliable; video and PDF support is carrier-gated and unreliable. The universal pattern for rich media over SMS = send a hosted link (branded short URL).**

#### MMS limits (Twilio — the de facto standard)
| Media type | Max size | Carrier compatibility | Notes |
|---|---|---|---|
| JPEG / PNG / GIF | 600 KB recommended (5 MB hard limit) | All major carriers | Twilio auto-resizes PNG/GIF/JPEG |
| MP4 video | 5 MB total MMS limit | Limited — many carriers transcode or reject | Send as link instead |
| PDF | 5 MB total MMS limit | **AT&T, Rogers, Fido, Telus = DOES NOT DELIVER** | Never attach PDF as MMS |
| Audio | 5 MB total MMS limit | Variable | Rarely used |
| Total MMS payload | **5 MB** (body text + all attachments) | — | Up to 10 attachments per message |
| Safe practice size | **500 KB** per attachment | Ensures delivery across all carriers | |

#### Banner image via MMS
- JPEG/PNG banner at ≤600 KB is safe for all carriers (Twilio auto-resizes supported formats).
- Keep banner dimensions reasonable (≤1200px wide) to stay under 600 KB post-compress.
- DO Spaces → generate presigned URL → pass as `mediaUrl` param to Twilio `messages.create()`.

#### Video and PDF over SMS — the correct pattern
**Never attach.** Instead:
1. Store asset in DO Spaces (already done by AI Asset Service).
2. Generate a presigned URL OR a permanent public URL.
3. **Shorten with a branded short domain** (e.g., `go.famit.in/xyz`) — NOT `bit.ly` or `tinyurl` (US carriers filter shared public shorteners as spam).
4. Append shortened URL to SMS text body: `"Hi {name}, your brochure: go.famit.in/abc"`
5. Destination page = mobile-optimized landing page showing the PDF inline (or PDF viewer).

#### DLT compliance (India — mandatory for commercial SMS)
- All **promotional and transactional SMS** to Indian numbers require DLT (Distributed Ledger Technology) registration via TRAI.
- **Entities must register:** sender ID (header), message templates (exact text), purpose (promotional/transactional/service).
- Template text must be pre-approved; variable content only in designated `{#var#}` fields.
- **Principal Entity (PE) ID + Template ID** must be passed in each API call (Twilio → `StatusCallback` headers or provider-specific params for Indian carriers).
- **This is a hard compliance gate** — sending unregistered templates = carrier block + regulatory risk.
- DLT registration is per-tenant (each business registers their own templates under their own PE ID).

#### India carrier: Exotel vs Twilio
- **Exotel** (India-native): natively DLT-integrated, simpler for Indian numbers, cheaper per-SMS, supports Hindi/regional language SMS.
- **Twilio**: global, more dev-friendly API, DLT support via Indian carrier partner — requires additional configuration.
- **Recommendation:** Exotel as primary SMS provider for Indian tenants; Twilio as international fallback. Both modeled as Provider subclasses in the channel registry.

- **Sources:** [Twilio MMS file types](https://support.twilio.com/hc/en-us/articles/360018832773), [Twilio PDF carrier note](https://support.twilio.com/hc/en-us/articles/360056727314-Carrier-support-for-PDF-files-sent-using-Twilio-MMS), [Twilio image resize](https://support.twilio.com/hc/en-us/articles/223133547), [MessageFlow URL shortener guide](https://messageflow.com/blog/short-links-in-sms/), [Twilio URL shortening](https://help.twilio.com/articles/1260804572090-How-can-I-send-shortened-URLs-links-in-my-messages-)

---

### 4. CROSS-CHANNEL MEDIA DELIVERY — Decision Matrix

| Asset | Telegram | Email (transactional) | Email (marketing) | SMS/MMS |
|---|---|---|---|---|
| Banner image (JPEG/PNG <600 KB) | `sendPhoto` (direct / URL) | Hosted CDN `<img>` in HTML | Hosted CDN `<img>` in HTML | MMS `mediaUrl` |
| Banner image (1–10 MB) | `sendPhoto` (direct upload) | Hosted CDN `<img>` | Hosted CDN `<img>` | Compress to <600 KB or link |
| Promo video MP4 (<20 MB) | `sendVideo` (URL if <20 MB, else upload) | Hosted link (never attach video) | Hosted link | Branded short link |
| Promo video MP4 (>20 MB) | `sendVideo` (direct multipart upload) | Hosted link | Hosted link | Branded short link |
| PDF brochure (<5 MB) | `sendDocument` (URL if <20 MB) | Attach directly (1:1 transactional) | Hosted link | Branded short link (**never MMS PDF**) |
| PDF brochure (>5 MB) | `sendDocument` (direct upload) | Hosted link | Hosted link | Branded short link |
| Call summary (long text) | `sendMessage` (4096 char) + separate `sendDocument` | Email body (HTML) | Email body (HTML) | SMS text (160/GSM7) + link |

---

### 5. KEY ARCHITECTURAL DECISIONS FOR THE BUILD

1. **Telegram is the default + unblocked channel.** Ship it first. BotFather token → per-tenant vault → `httpx.AsyncClient` POST to `api.telegram.org`. No approval, no DLT, instant rich media.

2. **Media storage pattern is already done.** DO Spaces + presigned URL (from `media_gen/spaces.py:126-139`) is reused verbatim. The only new logic is: which URL type per channel (presigned for transactional, permanent-public for email HTML embeds).

3. **SMS PDF = never attach.** Always link. The branded short-link service (`go.famit.in`) is a 2-line nginx redirect + a DB table (`short_links`). Worth building as infra because it's also needed for email tracking click-through and SMS compliance.

4. **Email banner = hosted CDN URL, not CID.** Use permanent public DO Spaces URL or a long-lived presigned URL (regenerated at send time). `multipart/related` MIME structure only if Outlook CID compatibility is needed.

5. **SES v2 (40 MB limit) > SendGrid (30 MB)** for our use case. But SendGrid has better deliverability reputation + easier per-tenant sender domain management. Default: **SendGrid** for deliverability; **SES v2** as fallback / high-volume tier.

6. **DLT is a hard India gate for SMS.** Multi-tenant = each tenant registers their own PE ID + template IDs. Store `dlt_pe_id` + `dlt_template_id` per communication template in the DB. Gate sends: if `dlt_template_id` is null, block with a clear UI error ("Register DLT template to enable SMS").

7. **Caption vs body split for post-call summaries:**
   - Telegram: `sendMessage` (full summary, 4096 chars) → follow with `sendDocument` (brochure, separate message).
   - Email: summary in HTML body; brochure attached or linked.
   - SMS: 160-char GSM7 teaser + branded short link to a full summary landing page.

---

**END MEDIA-DELIVERY-CHANNELS RESEARCH**

---

## PHASE: EMAIL-PROVIDERS — Transactional Email Provider Selection
**Date:** 2026-06-14
**Scope:** Amazon SES, Resend, Postmark, SendGrid, Brevo — cost, India deliverability, templates, PDF/banner attachments, SPF/DKIM/DMARC setup, multi-tenant architecture. Sourced.

---

### PROVIDER SNAPSHOT (2026 — verified)

#### 1. Amazon SES v2
| Dimension | Detail |
|---|---|
| **Price** | $0.10 / 1,000 emails. No monthly minimum. $0.12/GB for attachments over wire. |
| **Free tier** | 3,000 emails/mo for 12 months (new accounts pre-Jul 2025); new accounts get $200 AWS credit. |
| **At 10K emails/mo** | ~$1 |
| **At 100K emails/mo** | ~$10 |
| **At 1M emails/mo** | ~$100 |
| **Dedicated IP** | $24.95/month per IP (min volume requirement applies) |
| **Attachment limit** | **40 MB total** (SES v2 — best in class; SES v1 was 10 MB) |
| **Deliverability** | Strong infrastructure (Amazon.com's own mail stack). Shared IPs carry reputation risk unless on dedicated IP. Internet.nl score: 60/100. **ap-south-1 (Mumbai) has known issues sending to Outlook.com / live.in** — verified AWS re:Post report. |
| **India region** | ap-south-1 available; uniform pricing across regions. Outlook/Hotmail delivery from Mumbai region is unreliable — workaround: send from us-east-1 or eu-west-1. |
| **SPF/DKIM/DMARC** | Full support; domain verification via CNAME/TXT DNS records. DKIM auto-configured on domain verification. DMARC monitoring add-on: $0.07/1K emails. |
| **Setup friction** | **HIGH.** Sandbox → production approval (24-48h AWS review). IAM credentials, SNS topics for bounce/complaint webhooks, CloudWatch alarms — all manual. Estimated 4–8 hours. Auto-suspend on >10% bounce or >0.5% complaint with NO warning. |
| **Multi-tenant domains** | Supported via separate verified sending identities per tenant domain. No per-tenant API key isolation (single AWS account). |
| **Templates** | SES v2 template API (simple variable substitution). No visual builder. Must build template management yourself. |
| **SDK** | boto3 (Python), AWS SDK v3 (JS). SMTP relay also available. |
| **Verdict** | Cheapest at scale (4x cheaper than Resend at volume). Best for >200K emails/month. NOT recommended for early stage — setup is heavy, auto-suspend is brutal, Outlook from ap-south-1 is broken. |

---

#### 2. Resend
| Dimension | Detail |
|---|---|
| **Price — Free** | 3,000 emails/mo, 100/day hard cap. 1 domain. |
| **Price — Pro** | $20/mo (50K emails) or $35/mo (100K emails). Overage: $0.90/1K. 10 domains. |
| **Price — Scale** | $90/mo (100K) → $1,150/mo (2.5M). Overage: $0.46–$0.90/1K. 1,000 domains. Dedicated IPs: +$30/mo. |
| **Per-email rate (Pro)** | $0.40/1K (vs SES $0.10) — 4x more expensive at volume. |
| **Attachment limit** | **40 MB** (matches SES v2). Base64 or remote URL supported. PDF inline: CID referencing via content-id. |
| **Deliverability** | Internet.nl score: 72/100 (vs SES 60/100). Modern shared IP pool; no long track record but real-world production-grade. Sufficient for most SaaS at <500K/mo. |
| **India deliverability** | No India-specific data available; no ap-south-1 region (routes via global CDN). No known Outlook/Hotmail routing issues. |
| **SPF/DKIM/DMARC** | Fully managed — domain verification via CNAME, DKIM auto-configured. DMARC in UI. No manual DNS complexity. |
| **Setup friction** | **LOW.** API key → send in minutes. React Email (JSX templates) = best DX for Next.js stack. |
| **Multi-tenant domains** | Pro: 10 domains. Scale: 1,000 domains. Each domain = isolated sending identity. Per-organization domain recommended; architect `sender_domain` field in `communication_tenants` table early. |
| **Templates** | React Email (JSX → HTML) — first-class. Also supports plain HTML string. No visual drag-drop builder (need to build or use React Email components). |
| **SDK** | Official Python SDK (`resend`), TypeScript SDK. SMTP relay. |
| **SMTP relay** | Yes — drop-in for legacy code. |
| **Webhooks** | Delivered, bounced, complained, clicked, opened — all events via webhook. |
| **Sandbox** | No sandbox gate — send immediately in production (to any address). |
| **Verdict** | **RECOMMENDED for Famit/Axcrio at launch.** Lowest friction, no sandbox approval, managed deliverability, 40 MB attachment, multi-domain support, Python SDK, webhook events. Free tier sufficient for initial tenants. Migrate to SES when volume >200K/mo/tenant and cost matters. |

---

#### 3. Postmark
| Dimension | Detail |
|---|---|
| **Price — Free** | 100 emails/month only (effectively useless for production). |
| **Price — Basic** | $15/mo for 10K emails. Overage: $1.80/1K (most expensive overage of any provider). |
| **Price — Pro** | $16.50/mo for 10K emails. Overage: $1.30/1K. |
| **Price — Platform** | $18/mo for 10K emails. Unlimited domains, unlimited Message Streams, custom retention. |
| **Dedicated IP** | $50/month per IP. Minimum volume: 300,000 emails/month. |
| **Attachment limit** | Not explicitly published; standard MIME, effectively 10–25 MB. |
| **Deliverability** | **Best in class.** 98.7% inbox placement. 16-year track record. Strict sender vetting (rejects risky senders proactively). 99%+ to primary inbox within seconds. Achieves 93.8% average in 2026 benchmarks with 3/4 test rounds at 95-97%. |
| **India deliverability** | No India-specific published data. Global reputation likely gives better cross-carrier delivery than SES shared IPs. |
| **Message Streams** | Isolate transactional vs marketing sends per stream — spam from one stream cannot affect the other. Critical for SaaS with mixed traffic. |
| **SPF/DKIM/DMARC** | Auto-configured on domain verification. DMARC monitoring: +$14/mo per domain. |
| **Setup friction** | Medium. New account approval process tightened (post-ActiveCampaign acquisition in 2024). Reports of accounts suspended without notice for new users. |
| **Multi-tenant** | Requires separate "Server" per sending domain. Platform plan = unlimited servers = viable for multi-tenant. |
| **Templates** | Template API (Mustache/Handlebars syntax). No visual builder. |
| **SDK** | `postmarker` (Python). REST API. SMTP. |
| **Verdict** | Best deliverability, highest cost per 1K emails, and post-acquisition account approval issues. Recommended only if inbox placement is the #1 constraint (e.g., regulated industry, password-reset emails at scale). NOT cost-optimal for Famit's use case at launch. |

---

#### 4. SendGrid (Twilio)
| Dimension | Detail |
|---|---|
| **Free tier** | **REMOVED May 2025.** 60-day trial at 100/day only. After 60 days: must pay. |
| **Price — Essentials** | $19.95/mo for 50K emails/mo. $0.40/1K overage (scales down). |
| **Price — Pro** | $89.95/mo for up to 2.5M emails. Dedicated IP included. |
| **Attachment limit** | 30 MB total (25 MB via API; 30 MB via SMTP). |
| **Deliverability** | 95.3% inbox placement (vs Postmark 98.7%). Large IP pool, well-established. |
| **India deliverability** | Global shared IP pool; no known India-specific issues. |
| **SPF/DKIM/DMARC** | Fully supported; domain authentication wizard in dashboard. |
| **Setup friction** | Medium. Domain authentication required. API key management straightforward. |
| **Multi-tenant** | Subuser API for per-tenant isolation. Each subuser = separate reputation + stats. Only provider with native multi-tenant isolation built in. |
| **Templates** | Drag-and-drop visual builder + Dynamic Templates (Handlebars). Most full-featured builder of any provider. |
| **SDK** | `sendgrid-python` (official). |
| **Verdict** | Was the standard; free tier removal killed the value proposition for startups. Essentials plan = same cost as Resend Pro but worse DX. Only advantage: visual template builder + native multi-tenant Subuser API. Consider if the tenant count grows large (>100 tenants) and per-tenant reputation isolation is needed without custom code. |

---

#### 5. Brevo (ex-Sendinblue)
| Dimension | Detail |
|---|---|
| **Free tier** | 300 emails/day (9,000/month) — permanent, no credit card. Full API access. |
| **Paid — Starter** | ~$9/mo for 20K emails (~$0.45/1K overage). |
| **Paid — Business** | ~$18/mo for 20K emails; includes marketing automation, A/B test. |
| **Dedicated IP** | Enterprise only or ~$251/year add-on (~$20.90/mo) on Professional plan. |
| **Attachment limit** | Supported: base64 content or absolute URL; PDF is a supported extension. Size limit not explicitly published (standard ~10-25 MB). |
| **Deliverability** | 99% claimed. Shared infrastructure with marketing emails can degrade transactional deliverability. Dedicated IP not on lower tiers — shared IP = reputation variance. |
| **India deliverability** | Good for bulk sends to Indian mailboxes (Gmail.com, Yahoo.in) with DKIM configured. No India-specific delivery problems reported. |
| **SPF/DKIM/DMARC** | Managed via domain authentication in dashboard. Standard CNAME-based DKIM setup. |
| **Setup friction** | **Very low.** No sandbox gate. Free tier to production in minutes. |
| **Multi-tenant** | No native subuser/tenant isolation. All sends under single account. Insufficient for strict per-tenant reputation isolation. |
| **Templates** | Drag-and-drop builder + transactional template API. |
| **SDK** | `sib-api-v3-sdk` (Python). REST API. SMTP. |
| **Verdict** | Best free tier (300/day is actually usable for early tenants). But: no multi-tenant isolation, shared IP on lower plans, no dedicated IP under ~$21/mo extra. Suitable as a budget fallback or for very early stage. NOT the primary choice for a multi-tenant SaaS — reputation bleeding between tenants is unacceptable. |

---

### COST COMPARISON TABLE

| Provider | 1K emails/mo | 10K/mo | 50K/mo | 100K/mo | 1M/mo | Free tier |
|---|---|---|---|---|---|---|
| **Amazon SES** | $0.10 | $1 | $5 | $10 | $100 | 3K/mo (12mo) |
| **Resend** | Free (3K) | ~$5 est. | $20 | $20 | ~$460 | 3K/mo (perm) |
| **Postmark** | Free (100/mo) | $15 | $15+$72=$87 | $15+$162=$177 | ~$1,800 | 100/mo only |
| **SendGrid** | Trial only | Trial only | $19.95 | $19.95+$180=$200 | ~$400 | None (trial only) |
| **Brevo** | Free (9K/mo) | Free | ~$9 | ~$18+ | ~$200+ | 9K/mo (perm) |

---

### DELIVERABILITY RANKING (2026)

1. Postmark — 98.7% inbox. Best for mission-critical (password reset, billing alerts).
2. Resend — 72/100 Internet.nl. Sufficient for SaaS transactional at growth stage.
3. SendGrid — 95.3% inbox. Large legacy pool, no longer cost-competitive.
4. Brevo — 99% claimed but on shared marketing/transactional pool. India: good.
5. Amazon SES — Cheapest but shared IPs hurt reputation. ap-south-1 Outlook delivery broken.

---

### SPF / DKIM / DMARC SETUP COMPLEXITY

| Provider | SPF | DKIM | DMARC | Setup time |
|---|---|---|---|---|
| Resend | Auto (CNAME) | Auto on domain verify | UI-guided | ~15 min |
| Brevo | Auto | Auto | UI-guided | ~15 min |
| SendGrid | Auto (wizard) | Auto | UI-guided | ~20 min |
| Postmark | Auto | Auto | Add-on $14/mo/domain | ~20 min |
| Amazon SES | Manual (TXT + CNAME) | Auto on domain verify | Manual (TXT record) | 1–2 hours + 24-48h sandbox approval |

**2026 requirement:** Google, Yahoo, Microsoft all enforce SPF + DKIM + DMARC for senders at meaningful volume. DMARC enforcement (`p=reject` or `p=quarantine`) is mandatory for >5K/day senders. All five providers above support this; SES requires the most manual DNS work.

---

### MULTI-TENANT ARCHITECTURE — EMAIL

**Key insight:** For Famit (multi-tenant SaaS), each tenant ideally sends from their own domain (e.g., `noreply@acmecorp.com`) rather than `noreply@famit.in`. This requires:

1. **Per-tenant verified sender domain** stored in `communication_tenants.sender_domain`.
2. **Per-tenant DKIM/SPF DNS records** — provisioned when tenant onboards.
3. **Provider support for many domains:**
   - Resend Scale: up to 1,000 domains ✅
   - SendGrid Subusers: per-tenant IP/reputation isolation ✅
   - SES: unlimited verified identities (but single AWS account) ✅
   - Postmark Platform: unlimited servers ✅
   - Brevo: single account, no tenant isolation ❌

**Practical approach at Famit launch:** Resend Pro (10 domains = ~10 tenants) → upgrade to Scale (1,000 domains) as tenant count grows. Fallback sender domain `noreply@mail.famit.in` while tenant's own domain is being verified.

---

### RECOMMENDATION

**Primary: Resend**
- Reason: lowest setup friction (no sandbox gate, no 24h AWS approval), managed DKIM/DMARC, 40 MB attachment limit, 3,000/mo free tier covers initial tenants, Python SDK, webhook events for bounce/complaint tracking, 1,000 domains on Scale, best DX for the Next.js + Python stack already in use.
- Cost at 50K emails/mo across all tenants: $20/mo. Negligible.
- Migration path: when any single tenant exceeds ~200K emails/month, carve them onto SES for cost ($10 vs $35).

**Fallback / High-volume: Amazon SES**
- Reason: $0.10/1K is unbeatable. At 1M emails/mo, SES = $100 vs Resend = $460.
- Gate: only migrate when monthly email volume justifies the 4–8h setup cost and ongoing ops burden.
- CRITICAL: do NOT use ap-south-1 for Outlook delivery. Use us-east-1 as the SES region even for Indian tenants.

**Never use (for this project):**
- SendGrid: free tier gone, same price as Resend Pro but worse DX.
- Postmark: 16x more expensive overage rate ($1.80/1K vs $0.10/1K SES); post-acquisition account approval risk.
- Brevo: no multi-tenant reputation isolation — a single bad-actor tenant poisons the shared IP pool for all tenants.

---

### INTEGRATION SKETCH (Resend + Python)

```
# Install: pip install resend
import resend
resend.api_key = vault.get_secret(tenant_id, "resend_api_key")

params = resend.Emails.SendParams(
    from_="Acme Corp <noreply@acmecorp.com>",   # per-tenant verified domain
    to=["lead@example.com"],
    subject="Your call summary — {campaign_name}",
    html="<p>Hi {name}, here is your summary...</p><img src='{banner_url}'>",
    attachments=[{
        "filename": "brochure.pdf",
        "path": presigned_url,                  # DO Spaces presigned URL
    }]
)
resend.Emails.send(params)
```

Bounce/complaint webhooks → `POST /comm/webhook/resend` → update `communication_send_log.status` → trigger retry or suppress logic.

---

**Sources:**
- [Resend Pricing](https://resend.com/pricing)
- [Resend Attachments docs](https://resend.com/docs/dashboard/emails/attachments)
- [AWS SES Review 2026 — Mailflow Authority](https://mailflowauthority.com/esp-reviews/aws-ses-review)
- [Resend vs SES vs Postmark 2026](https://www.buildmvpfast.com/blog/resend-vs-ses-vs-postmark-transactional-email-deliverability-saas-2026)
- [SendGrid free tier removal](https://dreamlit.ai/blog/best-sendgrid-alternatives)
- [Postmark pricing](https://postmarkapp.com/pricing)
- [Brevo transactional email](https://www.brevo.com/products/transactional-email/)
- [India 70% deliverability baseline](https://www.smtp2go.com/blog/best-transactional-email-services/)
- [AWS SES ap-south-1 Outlook issue](https://repost.aws/questions/QUA1-_IV15T9Oi64jdh8yHXw)
- [Multi-tenant email architecture — MailerSend](https://www.mailersend.com/blog/multi-tenant-email-sending)
- [Resend vs SES — b2bsaastools](https://www.b2bsaastools.com/compare/resend-vs-ses/)
- [Email API Pricing June 2026](https://www.buildmvpfast.com/api-costs/email)

---

**END EMAIL-PROVIDERS RESEARCH**

---

## PHASE: sms-providers-india — SMS Providers, DLT Compliance, Pricing (2026-06-14)

### TRAI / DLT Compliance Framework

**Regulation:** TCCCPR 2018. Enforced via DLT (blockchain) platforms operated by telcos since 2020–2021. Mandatory for any entity sending commercial SMS on Indian domestic networks.

**Approved DLT portals (register on ONE — all are interoperable):**
- Jio TrueConnect — largest subscriber base, recommended
- Airtel Smartping / i.airtel.in
- Vi DLT / VILPOWER (Vodafone Idea)
- BSNL Sancharnet DLT (cheapest PE fee: ₹3,300 vs ₹5,900 elsewhere)
- Tata Communications / Videocon (niche)

**Registration — 5 steps (must complete all before first API send):**
1. **PE Registration** — KYC: PAN, GST certificate, business registration, authorised signatory ID. Fee: ₹5,900 incl. GST (BSNL: ₹3,300). Timeline: 24–72 hrs. Yields a 19-digit PE-ID required in every API payload.
2. **Header/Sender ID Registration** — 6-char uppercase alphanumeric (e.g. FAMITX). Fee: ₹590/year per header. Timeline: 1–3 working days. From May 2025: operator auto-appends suffix — -T (transactional), -S (service), -P (promotional), -G (government).
3. **Content Template Registration** — Pre-approve every message body with `{#var#}` placeholders (max 5–6 vars, tagged by type: OTP / amount / name / date). Free. 1–3 days. Every API send must pass an approved template ID.
4. **CTA URL Whitelisting** — All URLs in templates pre-approved separately (mandatory since Oct 2024). Free. 1–3 days.
5. **PE-TM Binding** — Link the PE to your SMS provider's Telemarketer entity on the portal. Without this, messages are blocked even if templates are approved.

**Total timeline:** 5–10 business days clean; 2–4 weeks first-time with rejections.

**Message categories — consent rules:**
- **Transactional:** OTP, banking alerts. No consent needed. DND does NOT block. Use -T header.
- **Service (Implicit):** Existing customer/lead relationship (post-call summary, booking update). Inferred consent. No time restriction. No DND block. **This is Famit's category.**
- **Service (Explicit):** Requires documented consent before first send.
- **Promotional:** Marketing/offers. Explicit opt-in required OR DND-clean. Time-window: 10:00 AM – 9:00 PM IST only (outside = DROPPED, not queued). Must include STOP instruction.

**DCA (Digital Consent Acquisition):** Only needed for promotional messages to DND numbers. Not applicable to Famit's service-implicit post-call flow.

**DPDP Act 2023 overlay:** Consent timestamp + wording must be stored per-lead per-tenant. Store in `communication_consents` (FORCE-RLS, indexed by tenant_id + phone + channel).

**Penalties:**
- 1st violation: Warning
- 2nd: Capped at 20 msgs/day for 6 months
- 3rd: Full telecom resource disconnection
- DPDP: ₹50 crore per instance (no consent), ₹250 crore (data breach)

---

### Provider Pricing Comparison (India, 2026)

| Provider | Service/Transactional | OTP | Enterprise floor | Billing | DLT support |
|---|---|---|---|---|---|
| **MSG91** | ₹0.18 (30k) → ₹0.16 (962k) | ₹0.15 | ₹0.13 negotiate | INR | Fully managed |
| **Gupshup** | ~₹0.17 flat | ~₹0.17 | Custom >1L/mo | INR or USD | Assisted |
| **Kaleyra** | ₹0.18–₹0.22 | ₹0.18 | Custom enterprise | USD (forex risk) | Assisted |
| **Twilio** | ~₹0.45 effective INR | ~₹0.45 | No India discount | USD (heavy forex) | Self-serve |
| **Plivo** | ~₹0.50 PAYG | Same | Volume commit plans | USD (forex risk) | Docs + assisted |
| **2Factor.in** | ~₹0.18 | <4 sec, ₹0.13 vol | ₹0.13 | INR | Managed |
| **Fast2SMS** | ₹0.11–0.18 | ₹0.11 (slow) | Lowest market | INR | Self-serve |

All prices EXCLUDE 18% GST. DLT setup = ₹5,900 PE (one-time) + ₹590/header/year is additional and mandatory.

**Twilio/Plivo forex cost analysis:** Plivo list $0.0058/SMS at current ₹84/USD = ₹0.49 + 2.5% forex card surcharge = ~₹0.50/SMS effective. Twilio similar or higher. That is 3× MSG91's ₹0.16–0.18. USD billing also adds accounting complexity for INR-billed tenants.

**MSG91 pricing tiers (from official pricing page):**
- 5,000 SMS: ₹0.25/SMS
- 16,500 SMS: ₹0.20/SMS
- 30,000 SMS: ₹0.18/SMS (₹5,400 pack)
- 60,000–450,000 SMS: ₹0.17/SMS
- 962,500 SMS: ₹0.16/SMS
- Enterprise negotiate: ₹0.13/SMS

---

### Provider Verdicts

**MSG91 — RECOMMENDED for Famit**
- INR billing, no forex risk, no bank FX markup
- Fully managed DLT onboarding — acts as Telemarketer entity, handles PE-TM binding
- Multi-tenant sub-accounts for per-tenant isolation and billing
- REST API: `POST /v5/flow/?flow_id=&sender=FAMITX&mobiles={phone}&VAR1={name}&VAR2={summary}&template_id={dlt_id}`
- Delivery receipt webhooks → `POST /comm/webhook/msg91` → update `communication_send_log`
- Same platform as WhatsApp (potential API consolidation — reduces vendors)
- Channels: SMS, WhatsApp, Email, Voice, RCS from one account

**Gupshup — Strong #2 (if consolidating WhatsApp + SMS on one vendor)**
- ₹0.17 flat; strong conversational/AI messaging focus
- But: Famit already has direct Meta WhatsApp — Gupshup adds less marginal value here

**Kaleyra — Enterprise-only, later phase**
- 99.99% uptime SLA, ISO 27001/SOC2; overkill for current scale
- Now part of Telnyx; integration future uncertain
- Revisit when Famit has enterprise contracts requiring SLA papers

**Twilio — NOT recommended for India SMS**
- 3× cost vs MSG91, USD billing, no India-local support, self-serve DLT
- Justified only if already deep in Twilio globally for other markets

**Plivo — Fallback for multi-country expansion**
- Good docs and India coverage; pricing is USD so works for international tenants
- When Famit adds non-Indian tenants, evaluate Plivo or Twilio for unified global routing

**2Factor.in — OTP specialist (future)**
- Sub-4-second OTP delivery; best speed benchmark in India
- No promotional, no WhatsApp, SMS only
- Add as specialist OTP provider when Famit ships SMS OTP login

**Fast2SMS — Avoid for production**
- Cheapest (₹0.08–0.11) but 5–15 sec OTP delivery, smaller telco network
- Reliability risk on automated flows; not suitable for after-call hooks

---

### Compliance + Integration Path for Famit

**Step 1 — Register on DLT (do this BEFORE any code):**
- Portal: Jio TrueConnect (recommended) or Airtel Smartping
- Fee: ₹5,900 one-time (founder action; requires GSTIN + PAN)
- Register header: FAMITS (6 chars, -S suffix for service)
- Register two templates:
  - "famit_post_call_summary": "Hi {#var#}, your call with {#var#} is complete. Summary: {#var#}. View full transcript: {#var#}" (whitelist the transcript URL)
  - "famit_hot_lead_alert": "HOT LEAD: {#var#} called re {#var#}. Score: {#var#}/100. View: {#var#}"
- Bind PE to MSG91 as Telemarketer

**Step 2 — MSG91 account:**
- Create sub-account per tenant (maps to tenant_id)
- Store sub-account API key in provider_credentials (AES-256-GCM, FORCE-RLS)
- Set webhook URL to `/comm/webhook/msg91/delivery`

**Step 3 — API send from caller.py post-call hook:**
```python
# After _finalize_call(), if sms_followup enabled:
import httpx
payload = {
    "flow_id": tenant.sms_flow_id,          # MSG91 flow with approved template
    "sender": "FAMITS",
    "mobiles": lead.phone,
    "VAR1": lead.name,
    "VAR2": truncate(call_summary, 80),      # SMS: keep short, link to full
    "VAR3": short_url(transcript_url),       # pre-whitelisted URL
    "template_id": tenant.sms_template_id,  # DLT template ID
}
await httpx.AsyncClient().post("https://api.msg91.com/api/v5/flow/", json=payload,
    headers={"authkey": tenant.msg91_key})
```

**Step 4 — Consent storage (DPDP 2023):**
```sql
-- In communication_consents (FORCE-RLS):
INSERT INTO communication_consents
  (tenant_id, lead_phone, channel, consent_basis, captured_at, wording)
VALUES
  ($1, $2, 'sms', 'service_implicit', NOW(),
   'Lead participated in inbound/outbound call via Famit platform');
```

### Cost Model for Famit (Tenant Billing)

At 1,000 SMS/day across all tenants:
- MSG91 cost at ₹0.17: ₹170/day + 18% GST = ₹200/day (~₹6,000/month)
- Bill tenants at ₹0.22–0.25/SMS (30–47% markup)
- Monthly gross margin at 1k/day: ~₹1,500–2,250
- Metered via existing `wallet_transactions` (channel='sms', amount_minor in paise)

---

**Sources:**
- [MessageCentral India SMS Guide 2026](https://www.messagecentral.com/sms-guideline/india)
- [MSG91 SMS Pricing India](https://msg91.com/in/pricing/sms)
- [Plivo DLT Compliance Blog](https://www.plivo.com/blog/trai-dlt-regulations-for-sms/)
- [Plivo DLT Support Docs](https://support.plivo.com/hc/en-us/articles/360046769131-DLT-Registration-Process-for-Sending-SMS-to-India)
- [MessageCentral OTP Pricing 2026](https://www.messagecentral.com/blog/sms-otp-pricing-india)
- [TechToNetworks SMS API India](https://www.techtonetworks.com/post/best-sms-api-providers-india)
- [Webxion DLT Registration 2026](https://www.webxion.com/dlt-registration-in-india-trai-rules-registration-process/)
- [TRAI DLT Registration 2Factor.in](https://2factor.in/v3/dlt/trai-mandatory-dlt-registration/)
- [India SMS Messaging Regulations TALK-Q](https://talk-q.com/sms-messaging-regulation-in-india)
- [Kaleyra DLT Registration](https://messaging.kaleyra.com/support/solutions/articles/3000100889-dlt-registration-india)

---

**END sms-providers-india RESEARCH**

---

## PHASE: TEMPLATE-BUILDERS — Cross-Channel Research

**Date:** 2026-06-14
**Sources:** Infobip docs, AiSensy/Interakt/Wati tutorials, Telegram Bot API (core.telegram.org), Resend docs, SendGrid/Twilio docs, MSG91/WebEngage DLT guides, Bird omnichannel docs, Zixflow comparison

---

### A. WhatsApp Business API — Canonical Template Structure (Ground Truth)

The WA template is the gold standard all other channels are mapped against.

**Component model:**

| Component | Required | Limits | Variables |
|---|---|---|---|
| Header | No | 60 chars text / 5 MB image / 16 MB video / 100 MB doc / location | 1 placeholder max (text header only) |
| Body | YES | 1,024 chars | Unlimited `{{1}}` `{{2}}` positional |
| Footer | No | 60 chars, plain text only | None (auth expiry only) |
| Buttons | No | Up to 10 total | — |

**Button types (full Meta spec):**

| Type | Limit | Notes |
|---|---|---|
| Quick Reply | 25 chars each, up to 10 | AiSensy imposes stricter 3-button/20-char limit — Meta allows more |
| CTA URL | Up to 2 per template, 2,000 char URL | Dynamic URL suffix: `{{1}}` allowed |
| Phone | 1 per template, international format | |
| Copy Code | 15 chars | Coupon codes |
| Flow Trigger | — | Launches WhatsApp native Flow |
| One-Tap Autofill | — | Android OTP auto-copy |

**Template categories (drives conversation cost):**
- Marketing: promos, retargeting — ~97 paise/conversation (Interakt benchmark)
- Utility: confirmations, alerts, OTPs — ~16 paise/conversation
- Authentication: OTP-only, restricted format

**Variable syntax:** `{{1}}`, `{{2}}` positional (sequential, mandatory). Sample values MANDATORY at submission or Meta rejects. Template name: lowercase + numbers + underscores only.

**Advanced template types:** Carousel (up to 10 cards each with header+body+buttons), Limited-Time Offer (countdown), Coupon Code (copy button), Flow (native WA form).

**Approval flow:** Submit → PENDING → APPROVED/REJECTED (minutes to 24h). Edited templates re-enter review. Deleted templates locked 30 days. Max 250 approved templates per WABA account. Rate limits tier-unlocked by usage: 250 → 1k → 10k → 100k conversations/day.

---

### B. BSP Platform UX — AiSensy, Wati, Interakt Compared

All three expose the identical Meta WA template data model (constrained by Meta). Differentiation is in UX add-ons only.

**AiSensy (~₹899–2,159/mo):**
- UI flow: Manage → Template Message → "+New" → Category → Name → Header (TEXT/IMAGE/VIDEO/FILE) → Body with `{{1}}` `{{2}}` → Footer → Buttons
- Quick Replies: up to 3 (platform-imposed limit, stricter than Meta's 10), max 20 chars
- CTA: URL + phone, max 1 of each
- Media: sample upload required at creation; text is mandatory (media alone is rejected by Meta)
- Pre-built template library: 100+ industry templates
- Analytics: click tracking per template
- Cheapest BSP for small teams

**Wati (~₹2,499–16,999/mo for 5 users):**
- Structured form builder; select pre-built or custom
- Dynamic variables with names/dates; quick-reply buttons
- Best for team inbox workflows (shared inbox, assignment, SLA)
- Most expensive of the three

**Interakt (Starter plan, pay-per-conversation):**
- Category → 70+ language support → Header/Body/Footer/Buttons builder
- AI Copilot: specify Goal + Audience + Tone (Professional/Witty/Friendly/Urgent) → LLM drafts template
- Utility Compliance button: when Meta recategorizes a marketing template, auto-rewrites for utility compliance
- Unique: 70+ languages; AI-draft built-in; recategorization compliance assistant

**Strategic conclusion for Famit:** All three BSPs are UI wrappers over Meta Cloud API. Famit owning the template registry in our DB removes BSP dependency, enables cross-channel templates (one template → WA + Email + Telegram), and eliminates ₹2,500–17,000/mo BSP fees. Build to Meta Cloud API directly.

---

### C. Telegram Bot API — Template Model (No Pre-Approval)

**Cost:** FREE for standard use. Paid Broadcasts (>30 msg/s) = 0.1 Telegram Stars/message. Famit use case (1 msg per call event) = ZERO cost.

**Setup:** @BotFather → /newbot → HTTP Bearer token. Per-tenant vault (AES-256-GCM encrypted, per provider registry pattern already designed). Username must end in "bot".

**No pre-approval needed.** Templates stored in Famit DB as free-form strings with `{variable}` placeholders, rendered via f-string interpolation at send time. No DLT, no Meta review, no scrubbing.

**Message types relevant to Famit:**

| Method | Use Case | Key Limit |
|---|---|---|
| `sendMessage` | Call summary, hot-lead alert text | 4,096 chars; HTML or MarkdownV2 |
| `sendPhoto` | Banner image (JPEG/PNG) | 10 MB direct / 5 MB via URL |
| `sendDocument` | PDF brochure, any file type | 50 MB direct / 20 MB via URL |
| `sendVideo` | Promo video (MP4) | 50 MB direct / 20 MB via URL |
| `sendMediaGroup` | Album: banner + brochure together | 2–10 items; per-item limits; 1 caption |

**Keyboard patterns:**
- `InlineKeyboardMarkup`: buttons inside message — `callback_data` (64 bytes max), `url`, `switch_inline_query`
- `ReplyKeyboardMarkup`: buttons replace device keyboard
- Use for: "Book a Call" / "View Brochure" / "Talk to AI" / "Confirm Interest" / "Not Interested"
- Callback fires webhook → LLM conversation brain

**ParseMode:** HTML or MarkdownV2. Supports bold, italic, code, pre, links, underline, strikethrough, custom emoji.

**file_id reuse:** Upload a file once → receive file_id → reuse across sends without re-uploading. Critical for brochure delivery at scale: upload the PDF once, cache the file_id, reuse for all sends of that template.

**Rate limits:** 30 msg/s to different users; 1 msg/s to same chat; no daily cap. Famit is well within limits.

---

### D. Email Template Builders — Resend vs SendGrid vs Postmark

**Resend (recommended for Famit — developer-first):**
- Free: 100 emails/day; Paid: $20/mo for 50,000/mo
- Template: ID + `variables` object → Resend renders and delivers
- Variable syntax in HTML: `{{{VARIABLE_NAME}}}` (triple braces = raw HTML, unescaped)
- Up to 20 variables per template; type string/number; fallback values supported
- Reserved names: `FIRST_NAME`, `LAST_NAME`, `EMAIL`, `RESEND_UNSUBSCRIBE_URL`
- API call: `POST /emails` → `{ from, to, template: { id, variables: { KEY: "value" } } }`
- Versioning: draft → published (edits stay draft until explicitly published)
- Native React Email support: JSX components, no separate render step needed

**SendGrid (Twilio — enterprise):**
- Dynamic Templates using Handlebars: `{{variable_name}}`
- Conditional logic: `{{#if cond}}...{{/if}}`; loops: `{{#each arr}}...{{/each}}`
- Drag-and-drop Design Library + code editor
- API: `POST /v3/mail/send` → `{ template_id, dynamic_template_data: { key: val } }`
- Serves both transactional and marketing

**Postmark:** Mustache `{{var}}`; transactional-only; fastest median delivery (2–3 sec); draft/live versioning.

**Variable syntax comparison:**

| Provider | Syntax | Conditionals | Max Vars | Best For |
|---|---|---|---|---|
| Resend | `{{{VAR}}}` | Basic | 20 | Transactional, dev-first, cheapest |
| SendGrid | `{{var}}` (Handlebars) | Full (loops, if/else) | Unlimited | Enterprise, marketing+transactional |
| Postmark | `{{var}}` (Mustache) | Basic | Unlimited | Transactional, speed |

**For Famit:** Resend (developer-first, generous free tier, React Email native, $20/mo). Template variables: `{{{contact_name}}}`, `{{{call_summary}}}`, `{{{next_step}}}`, `{{{brochure_url}}}`, `{{{RESEND_UNSUBSCRIBE_URL}}}`.

---

### E. SMS DLT — India Compliance (Hard Gate, Already Researched in Prior Phase)

Key template-builder-specific constraints for Famit UI design:

1. **Variable format on DLT portal:** `{#var#}` (during registration). On MSG91 API: `##variable_name##`. Max 5–6 variables, each value max 30 chars.
2. **Template builder must auto-generate the DLT-format version** (`{#var#}` syntax) alongside the Famit-internal version, so the tenant can copy-paste into DLT portal.
3. **Gate: if `sms_dlt_template_id` is null → block SMS send with UI error.** No silent failures.
4. **PE ID is per-business** (per prior phase research). Multi-tenant = each tenant registers. Panel guides them; stores PE ID + DLT Template ID encrypted per tenant.

---

### F. Bird (MessageBird) — Omnichannel Template Registry Pattern (Best-in-Class Reference)

Bird supports: WhatsApp, FB Messenger, WeChat, Telegram, SMS, Twitter, Slack — in one unified template system.

**Template creation flow:**
1. Select channel(s) — can choose "omnichannel" to span multiple at once
2. Set message type (marketing/utility/authentication)
3. Set default language
4. Build content — shared variable schema + channel-specific content blocks
5. Preview by clicking each channel tab in the Preview panel
6. Publish → immediately available in Inbox, Flows, and Campaigns (centralized registry)

**Key design lesson:** One template entity in DB; channel-specific content blocks per entry; shared variable schema. Preview renders each channel's actual format (WA, SMS, email, Telegram). This is exactly what Famit should build.

**Brevo:** Templates are per-channel (NOT shared objects). Syntax: `{{contact.FIRSTNAME}}`. Less relevant for Famit.

**Chatwoot:** Canned responses (simple snippets, no variable system). Not a template builder. Famit is building something more powerful.

---

### G. Unified Template Registry — Data Schema for Famit

Synthesized from Bird's model + Meta WA constraints + Telegram/Email/SMS requirements:

```sql
-- FORCE-RLS on all tables (tenant_id on every row)

communication_templates:
  id UUID PK
  tenant_id UUID FK (FORCE-RLS)
  name TEXT          -- slug: lowercase, underscores, numbers only
  display_name TEXT
  category TEXT      -- marketing | utility | authentication | alert
  variable_schema JSONB  -- [{name, type, description, sample, fallback}]
  channels TEXT[]    -- ['whatsapp','telegram','email','sms']
  created_at TIMESTAMPTZ
  updated_at TIMESTAMPTZ

communication_template_content:
  id UUID PK
  template_id UUID FK
  channel TEXT       -- whatsapp | telegram | email | sms
  subject TEXT NULL  -- email subject line
  header_type TEXT NULL   -- whatsapp: text|image|video|document|location
  header_spaces_key TEXT NULL  -- DO Spaces key for media
  body TEXT NOT NULL          -- Famit universal: {variable_name} syntax
  footer TEXT NULL
  buttons JSONB NULL  -- [{type:'quick_reply'|'url'|'phone', text, value}]
  -- WhatsApp approval tracking
  wa_template_name TEXT NULL  -- Meta template name
  wa_template_id TEXT NULL    -- Meta's returned template ID
  wa_status TEXT NULL         -- pending | approved | rejected
  -- SMS DLT tracking
  sms_dlt_body TEXT NULL      -- {#var#} syntax version for tenant to paste on DLT portal
  sms_dlt_template_id TEXT NULL
  sms_sender_id TEXT NULL
  sms_category TEXT NULL      -- service_implicit | promotional | etc.
  -- Email-specific
  email_from_name TEXT NULL
  email_reply_to TEXT NULL
  -- Approval tracking
  approved_at TIMESTAMPTZ NULL
  updated_at TIMESTAMPTZ
```

**Universal variable interpolation: Famit uses `{variable_name}` internally; each channel adapter converts at send time:**

| Channel | Famit → Channel Conversion |
|---|---|
| WhatsApp | `{name}` → positional `{{1}}`, `{{2}}`; params array built from variable_schema order |
| Telegram | `{name}` → Python `.format(**vars)` direct interpolation |
| Email (Resend) | `{name}` → `{{{name}}}` passed in variables object |
| Email (SendGrid) | `{name}` → `{{name}}` in dynamic_template_data |
| SMS (MSG91) | `{name}` → `##name##` at API call; DLT portal submission uses `{#var#}` |

**Template preview in panel UI:** Render each channel's format side-by-side with sample values filled. Show character count warnings (body > 1,024 WA; caption > 1,024 Telegram; SMS > 160 GSM7 characters).

---

### H. Adversarial Fact Checks

**CLAIM:** "AiSensy limits quick replies to 3 buttons at 20 chars"
Meta's actual API: up to 10 quick-reply buttons at 25 chars each.
VERDICT: AiSensy imposes a stricter platform limit. Famit implements full Meta limits (10 buttons, 25 chars).

**CLAIM:** "DLT variables limited to 5–6 per template, max 30 chars per value"
CROSS-CHECK: WebEngage DLT guide + MSG91 DLT FAQ both corroborate.
VERDICT: CONFIRMED. Hard carrier infrastructure limit. Template builder must warn at creation time.

**CLAIM:** "Telegram is free for Famit's use case (1 alert per call)"
DETAIL: Paid Broadcasts (>30 msg/s) = 0.1 Stars/msg. Famit sends 1 msg per call event.
VERDICT: CONFIRMED zero cost.

**CLAIM:** "Interakt utility = 16 paise, marketing = 97 paise"
CONTEXT: These are Meta WA Cloud API conversation rates for India (BSPs pass through Meta pricing).
VERDICT: Accurate benchmark for Meta conversation cost in India.

**CLAIM:** "Resend free tier = 100 emails/day, $20/mo for 50,000/mo"
SOURCE: Resend pricing page (resend.com/pricing).
VERDICT: CONFIRMED.

**CLAIM:** "PE ID is per-business, cannot be centralized across tenants"
SOURCE: TRAI/WebEngage DLT guide + MSG91 DLT step-by-step.
VERDICT: CONFIRMED. Each tenant must register independently. Famit guides and stores per-tenant.

**CLAIM:** "Telegram bot cannot cold-message users who never initiated contact"
SOURCE: Telegram Bot API docs (core.telegram.org/bots/api).
VERDICT: CONFIRMED for contact-facing bots. EXCEPTION: founder hot-lead alerts (founder initiated the bot conversation, so receives freely).

---

### I. Opt-In / Consent Model Summary

**WhatsApp:** Explicit opt-in before any template message. Meta audits opt-in quality. Opt-out = user blocks bot or sends STOP (must be honored).

**SMS India:** Explicit for Promotional + Service-Explicit. Implicit for Service-Implicit (existing transaction relationship). DND auto-checked by carrier. Promotional blocked 9 PM–10 AM automatically.

**Email:** Double opt-in best practice. `RESEND_UNSUBSCRIBE_URL` must appear in marketing emails. Physical address required (CAN-SPAM) for US recipients.

**Telegram:** User must send first message to bot. Exception: founder alert stream (founder is admin, pre-consented by setup).

**Famit schema for consent:** `communication_consents (contact_id, channel, tenant_id, opted_in BOOL, opted_in_at TIMESTAMPTZ, source TEXT, wording TEXT)`. Gate every contact-facing send through consent check. Founder alerts bypass (admin stream).

---

### J. Cost Summary (Template-Builder Phase)

| Channel | Provider | India Cost/Unit | Approval Wait | Rate Limit |
|---|---|---|---|---|
| Telegram | Bot API | FREE | None | 30 msg/s |
| Email | Resend | $0/100/day; $20/mo 50k | None | No hard limit |
| Email | SendGrid | $0/100/day; $19.95/mo 50k | None | 600/min (free) |
| WhatsApp marketing | Meta Cloud API | ~₹97/conversation | 1–24h Meta review | Tier-based |
| WhatsApp utility | Meta Cloud API | ~₹16/conversation | 1–24h Meta review | Tier-based |
| SMS promotional | MSG91 | ₹0.17–0.25/SMS | DLT 2–4 days | Carrier-limited |
| SMS service | MSG91 | ₹0.16–0.18/SMS | DLT 2–4 days | No DND block |

**Strategic order:** Telegram first (free, instant, rich, zero approval). Email second (near-zero cost, all features, no approval). WhatsApp third (existing Meta infra, per-conversation cost). SMS last (India-only gate, DLT friction, per-SMS cost).

---

**END TEMPLATE-BUILDERS RESEARCH**

---

## PHASE: telegram-bot-api — Telegram Bot API In Depth (2026-06-14)

**Scope:** BotFather token creation (no business verification), all send methods + media limits, webhooks vs long-poll, conversation state, deep-link onboarding, groups/channels, rate limits, Mini-Apps, 2026 new features (Managed Bots, Bot-to-Bot, streaming), integration contract for Famit. Sourced.

---

### 1. CREATING A BOT — BotFather (Zero Verification Required)

**The single most important fact:** There is NO business verification, NO Meta-style review, NO carrier DLT registration. Any developer with a Telegram account can create a fully functional bot in under 2 minutes.

**Step-by-step (complete):**

1. Open Telegram → search `@BotFather` → tap START
2. Send `/newbot`
3. BotFather asks for a **display name** (any string, e.g. "Famit AI")
4. BotFather asks for a **username** — MUST end in `bot` (e.g. `famit_notify_bot`). Must be 5–32 characters, a-z, 0-9, underscore only.
5. BotFather returns: `Done! Congratulations on your new bot. You will find it at t.me/<username>. You can now add a description...` and then the **HTTP API token**: `7123456789:AAH...` (format: `<bot_id>:<random_string>`)
6. Token is the permanent credential. Regenerate via `/revoke` if leaked. **Never commit to git.**

**Key BotFather commands for configuration:**
| Command | Effect |
|---|---|
| `/setdescription` | Text shown in bot's chat info (up to 512 chars) |
| `/setabouttext` | Short about text in bot profile (up to 120 chars) |
| `/setuserpic` | Bot's profile photo |
| `/setcommands` | Register slash commands shown in the UI menu |
| `/setprivacy` | ENABLED (default) = bot sees only mentions + replies in groups; DISABLED = sees all messages |
| `/setjoingroups` | Whether the bot can be added to groups |
| `/setinline` | Enable inline query mode (bot usable from any chat via @botname) |
| `/mybots` | Manage all your bots |
| `/revoke` | Invalidate + regenerate token |

**Per-tenant vault pattern for Famit:**
- Each tenant creates their OWN bot via BotFather (tenant is the bot owner)
- OR Famit provisions bots via **Managed Bots API** (Bot API 9.5+, April 2026) — see Section 9
- Token stored in `provider_credentials` table, encrypted AES-256-GCM, FORCE-RLS per tenant
- Retrieved at send time: `vault.get_secret(tenant_id, "telegram_bot_token")`

**Source:** [core.telegram.org/bots/tutorial](https://core.telegram.org/bots/tutorial), [core.telegram.org/bots](https://core.telegram.org/bots)

---

### 2. SENDING MESSAGES — Complete Method Reference

**Base URL:** `https://api.telegram.org/bot{token}/{method}`

All methods: HTTP GET or POST. Parameters via URL query string, `application/json`, `application/x-www-form-urlencoded`, or `multipart/form-data`. Methods and parameter names are case-insensitive.

#### 2a. sendMessage

```
POST https://api.telegram.org/bot{token}/sendMessage
{
  "chat_id": "123456789",          // required: user/group/channel int64 or @channelusername
  "text": "Hello {name}!",         // required: 1–4096 chars
  "parse_mode": "HTML",            // optional: "HTML" | "MarkdownV2" (NOT "Markdown")
  "entities": [...],               // optional: alternative to parse_mode — explicit entity list
  "reply_markup": {...},           // optional: InlineKeyboardMarkup | ReplyKeyboardMarkup | ForceReply
  "message_thread_id": 123,        // optional: topic thread ID for supergroups with topics
  "disable_notification": false,   // optional: silent delivery
  "protect_content": false,        // optional: prevent forwarding/saving
  "reply_to_message_id": 456       // optional: reply threading
}
```

**ParseMode HTML tags (supported):** `<b>`, `<i>`, `<u>`, `<s>` (strikethrough), `<code>`, `<pre>`, `<a href="">`, `<tg-spoiler>`, `<blockquote>`, custom emoji `<tg-emoji emoji-id="">`. HTML entities `&amp;`, `&lt;`, `&gt;`, `&quot;` must be escaped in text.

**4096 char limit is per message.** For longer content (e.g. call summaries), chunk at the last newline/sentence boundary before 4096 chars and send multiple messages. The live WhatsApp brain (`caller.py:1518`) already has a truncate pattern; reuse it.

#### 2b. sendPhoto

```
POST .../sendPhoto
{
  "chat_id": "...",
  "photo": "<file_id | URL | multipart bytes>",
  "caption": "...",          // optional, max 1024 chars
  "parse_mode": "HTML",
  "reply_markup": {...}
}
```

**Photo size limits:**
- Via file_id (already on Telegram servers): unlimited
- Via HTTPS URL (Telegram pulls it): **5 MB max, JPEG/PNG/GIF only**
- Via multipart upload: **10 MB max**
- Image dimensions: width + height must not exceed 10,000 px; ratio must be ≤ 20:1

**Famit pattern:** Banner (JPEG, typically 200–500 KB) → DO Spaces presigned URL → pass as `photo` param. Well within 5 MB URL limit.

#### 2c. sendDocument

```
POST .../sendDocument
{
  "chat_id": "...",
  "document": "<file_id | URL | multipart bytes>",
  "caption": "...",         // optional, max 1024 chars
  "thumbnail": "...",       // optional: JPEG thumbnail for the file
  "parse_mode": "HTML"
}
```

**Document limits:**
- Via HTTPS URL: **20 MB max** (and currently only `.PDF` and `.ZIP` files work reliably via URL)
- Via multipart upload: **50 MB max**
- No format restriction for multipart; PDF, Excel, DOCX, any file type accepted

**Famit brochure pattern:** PDF brochure stored in DO Spaces → presigned URL → `document` param. For PDF < 20 MB this works via URL. For > 20 MB: stream bytes from Spaces → multipart upload.

**file_id caching (critical for scale):** After first successful upload, Telegram returns `file_id` in response. Cache this in `communication_asset_cache (tenant_id, spaces_key, telegram_file_id, cached_at)`. Subsequent sends: pass `file_id` directly — no re-upload, zero bandwidth, near-instant delivery.

#### 2d. sendVideo

```
POST .../sendVideo
{
  "chat_id": "...",
  "video": "<file_id | URL | multipart bytes>",
  "caption": "...",
  "duration": 60,            // optional: seconds
  "width": 1280, "height": 720,
  "supports_streaming": true // optional: enable progressive streaming
}
```

**Video limits:**
- MP4 format required for `sendVideo` (H.264 video + AAC audio recommended)
- Via URL: **20 MB max**
- Via multipart: **50 MB max**
- Non-MP4 formats: use `sendDocument` instead (delivered as file, not inline player)

#### 2e. sendAudio / sendAnimation / sendVoice

| Method | Format | Limit | Use |
|---|---|---|---|
| `sendAudio` | MP3, M4A, OGG | 50 MB | Music / audio files with album art + title |
| `sendVoice` | OGG+OPUS only | 50 MB | Voice messages (plays inline) |
| `sendAnimation` | GIF or H.264 MP4 no audio | 50 MB | Looping animations |

#### 2f. sendMediaGroup

Send 2–10 media items as an album (appear together in chat).

```python
POST .../sendMediaGroup
{
  "chat_id": "...",
  "media": [
    {"type": "photo", "media": "<url_or_file_id>", "caption": "Main caption"},
    {"type": "document", "media": "<url_or_file_id>"}
  ]
}
```

**Constraint:** Only ONE caption per group (on the first item). All items must be same media type group (all photos/videos, or all documents). Cannot mix photos + documents in one album.

**Famit use case:** Send banner + brochure together: NOT sendMediaGroup (different types). Send banner as `sendPhoto` → immediately follow with `sendDocument` for brochure. Two-message delivery.

#### 2g. Other useful methods

| Method | Use |
|---|---|
| `copyMessage` | Forward a message without "forwarded from" attribution |
| `forwardMessage` | Forward with attribution |
| `editMessageText` | Edit a previously sent bot message (up to 48h after sending) |
| `editMessageReplyMarkup` | Update inline keyboard on an existing message |
| `deleteMessage` | Delete a message (bot must be admin in group; own messages only in private) |
| `pinChatMessage` | Pin a message in group/channel |
| `sendChatAction` | Show "typing…" / "sending photo…" status to user |
| `getFile` | Get file_id's download URL (valid 1 hour) |

---

### 3. WEBHOOKS vs LONG POLLING — Production Decision

#### Long Polling (getUpdates)

```python
GET .../getUpdates?timeout=30&offset={last_update_id+1}&allowed_updates=["message","callback_query"]
```

**How it works:** Bot calls `getUpdates` in a loop. Telegram holds the connection open for `timeout` seconds (long poll). Returns array of `Update` objects when events arrive.

**Production constraints:**
- `timeout=0` = short polling — hammers Telegram's servers; NEVER use in production
- `timeout=30-60` = correct long-poll window
- **Only ONE process may poll per token simultaneously** — two processes → 409 Conflict
- No incoming traffic from Telegram → suitable for local dev, firewall-blocked environments
- `offset` must be set to `last_update_id + 1` to acknowledge processed updates; otherwise Telegram re-delivers

#### Webhooks (setWebhook)

```python
POST .../setWebhook
{
  "url": "https://famit.in/comm/telegram/webhook/{tenant_id}",
  "certificate": null,               // null for CA-signed cert; PEM file for self-signed
  "max_connections": 40,             // Telegram concurrent connections to your server (default 40, max 100)
  "allowed_updates": ["message", "callback_query", "inline_query"],
  "secret_token": "random_32char_hex_token"  // Telegram sends this in X-Telegram-Bot-Api-Secret-Token header
}
```

**Webhook constraints:**
- **HTTPS mandatory** — no plain HTTP, on any port
- **Supported ports:** 443, 80, 88, 8443 (only these four)
- **CA-signed TLS cert:** no extra param needed — Telegram trusts standard CA roots
- **Self-signed cert:** pass PEM-encoded public cert as `certificate` param
- **secret_token:** Telegram adds `X-Telegram-Bot-Api-Secret-Token: <value>` header to EVERY webhook call. Verify this header server-side to reject forged requests. 1–256 chars, `A-Z`, `a-z`, `0-9`, `_`, `-` only.
- Webhook and getUpdates are **mutually exclusive** — setting webhook disables getUpdates

**Performance verdict (sourced):** Webhook median latency is 3× lower than 100ms aggressive polling; CPU burn is 2× smaller. Webhook is the correct production choice. 2026 roadmap: QUIC-based webhooks to cut TCP handshake RTT by 15–25 ms.

**Famit webhook URL pattern:**
```
https://panel.famit.in/comm/telegram/webhook/{tenant_id}?token={secret_token}
```
OR (cleaner): one URL per bot token → route by token (since each tenant has their own bot).

**deleteWebhook:** Call `.../deleteWebhook` to disable and revert to getUpdates mode.
**getWebhookInfo:** Returns current webhook URL, pending update count, last error.

---

### 4. INLINE KEYBOARDS + CONVERSATION STATE (LLM BRAIN INTEGRATION)

#### InlineKeyboardMarkup

```python
"reply_markup": {
  "inline_keyboard": [
    [
      {"text": "Book a Call", "url": "https://cal.com/famit/30min"},
      {"text": "View Brochure", "callback_data": "brochure:tenant123"}
    ],
    [
      {"text": "Talk to AI", "callback_data": "chat:start"},
      {"text": "Not Interested", "callback_data": "opt_out"}
    ]
  ]
}
```

**callback_data constraints:**
- Max **64 bytes** per button (UTF-8 encoded)
- Convention: `action:payload` prefix pattern (e.g. `chat:start`, `book:slot_3`)
- Received as `CallbackQuery` update → your webhook gets `callback_query.data`
- MUST answer every callback with `answerCallbackQuery` within 10 seconds or Telegram shows loading spinner to user

**Button types:**
| Type | Field | Notes |
|---|---|---|
| Callback | `callback_data` | Max 64 bytes; triggers `CallbackQuery` update |
| URL | `url` | Opens URL in browser / app |
| Deep link | `url: "https://t.me/botname?start=payload"` | Opens bot chat with start param |
| Switch inline | `switch_inline_query` | Invokes inline mode in current chat |
| Login | `login_url` | OAuth login widget |
| WebApp | `web_app: {"url": "..."}` | Opens Mini App |
| Pay | `pay: true` | Payments only (must be first button in keyboard) |

#### Conversation State Machine for LLM Brain

**Pattern for multi-step AI conversation:**

```python
# In caller.py (additive router, never touches earner)
# State stored in: communication_sessions (tenant_id, chat_id, state, history JSONB, updated_at)

@comm_router.post("/comm/telegram/webhook/{tenant_id}")
async def telegram_webhook(tenant_id: str, update: dict, x_token: str = Header(None)):
    # 1. Verify secret_token header
    if x_token != vault.get_secret(tenant_id, "telegram_webhook_secret"):
        raise HTTPException(403)

    # 2. Route update type
    if "message" in update:
        await handle_message(tenant_id, update["message"])
    elif "callback_query" in update:
        await handle_callback(tenant_id, update["callback_query"])

async def handle_message(tenant_id, message):
    chat_id = message["chat"]["id"]
    text = message.get("text", "")
    session = await get_or_create_session(tenant_id, chat_id)

    # 3. Build history + call Groq (reuse existing reply brain pattern from caller.py:1518)
    history = session["history"]
    history.append({"role": "user", "content": text})
    reply = await groq_chat(history, system_prompt=tenant.comm_system_prompt)
    history.append({"role": "assistant", "content": reply})

    # 4. Save state + send reply
    await update_session(tenant_id, chat_id, history)
    await tg_send_message(tenant_id, chat_id, reply, inline_keyboard=build_quick_replies())

async def handle_callback(tenant_id, cb):
    await tg_answer_callback(tenant_id, cb["id"])  # MUST answer within 10s
    action, payload = cb["data"].split(":", 1)
    if action == "opt_out":
        await mark_opted_out(tenant_id, cb["from"]["id"])
    elif action == "chat":
        await start_conversation(tenant_id, cb["message"]["chat"]["id"])
    elif action == "brochure":
        await send_brochure(tenant_id, cb["message"]["chat"]["id"])
```

**State persistence:** `communication_sessions (id, tenant_id, channel, external_chat_id, state TEXT, history JSONB, last_message_at, created_at)` — FORCE-RLS on tenant_id. History is an array of `{role, content}` pairs, same schema as the existing Groq brain in `caller.py:1518`.

---

### 5. DEEP-LINK ONBOARDING — t.me/bot?start=

**Format:** `https://t.me/{bot_username}?start={payload}`

**Payload constraints:**
- Characters: `A-Z`, `a-z`, `0-9`, `_`, `-` only
- Max **64 characters**
- Base64url encoding recommended for binary/structured data: `base64.urlsafe_b64encode(json.dumps({"t": tenant_id, "l": lead_id}).encode()).decode().rstrip("=")`

**What happens when user taps the link:**
1. Telegram app opens (or prompts install)
2. Bot chat opens with a "START" button visible
3. User taps START → bot receives a `Message` update with `text = "/start {payload}"`
4. Bot can parse payload to pre-fill context: `cmd, _, start_param = text.partition(" ")`

**Famit use cases:**

| Scenario | Deep Link | Payload Contents |
|---|---|---|
| Post-call opt-in | `t.me/famit_notify_bot?start=<b64(tenant+lead_id)>` | tenant_id + lead_id → pre-consent the lead |
| Hot-lead alert → founder action | `t.me/famit_notify_bot?start=<b64(session_id)>` | Opens the specific call session for review |
| WhatsApp-to-Telegram bridge | Sent in WA message | Lead clicks → joins bot → receives brochure |
| Campaign-specific onboarding | `t.me/famit_notify_bot?start=<b64(campaign_id)>` | Routes to campaign-specific conversation flow |

**Group deep links:** `https://t.me/{bot_username}?startgroup={payload}` — opens group selection dialog to add bot to a group with the payload.

**Cold-message constraint (CRITICAL for product design):**
Telegram bots **cannot send messages to users who have never interacted with the bot**. The user must tap START (or send any message) first. This is the opt-in gate.

**Implication for Famit:**
- Contact-facing bot: the post-call auto-message can only be sent AFTER the lead has tapped the deep link and started the bot. The deep link is sent via another channel first (SMS or WhatsApp): "Chat with our AI on Telegram: t.me/famit_notify_bot?start=..."
- Founder hot-lead alert bot: founder is the one who created/enabled the bot; they have already started it during setup → no restriction. Founder gets alerts freely.

---

### 6. GROUPS AND CHANNELS — Sending to Group Chats

**How to get chat_id:**
1. Add bot to group → send a message mentioning bot → call `getUpdates` → find `update.message.chat.id` (negative integer for groups, e.g. `-1001234567890`)
2. OR use `/getid` bots like `@RawDataBot` to inspect
3. For channels: bot must be added as admin → channel chat_id is a negative integer starting with `-100`

**Privacy mode (critical for groups):**
- **ENABLED (default):** Bot receives only messages starting with `/`, replies to its own messages, and direct mentions. Does NOT see all group messages.
- **DISABLED:** Bot sees all messages in group. Enable by sending `/setprivacy` → `DISABLE` to BotFather.
- **Recommendation for Famit:** Keep ENABLED (privacy-respecting). The LLM brain triggers via inline button callbacks or `/ask` commands, not passive eavesdropping.

**Sending to groups/channels:**

```python
# Same sendMessage; just use the group's negative chat_id
POST .../sendMessage
{"chat_id": "-1001234567890", "text": "Hot lead alert: ..."}
```

Bot must be:
- In the group/channel
- Have permission to send messages
- For channels: added as admin

**message_thread_id:** For supergroups with "Topics" enabled (Forum mode), use this to send to a specific topic thread. Supported in sendMessage, sendPhoto, sendDocument, sendVideo, etc.

---

### 7. RATE LIMITS — Full Contract

| Scope | Limit | Behavior on exceed |
|---|---|---|
| Same chat | **1 message/second** | 429 + `retry_after` (seconds to wait) |
| Different users | **30 messages/second** default | 429 + `retry_after` |
| Paid Broadcasts (>30/s) | Up to **1,000 messages/second** | 0.1 Stars per message over 30/s limit; requires ≥10,000 Stars balance |
| Group messages | **20 requests/second** to same group | 429 |
| File downloads | Not rate-limited by message rate | Governed by file size + connection limits |

**Handling 429 (FloodWait):**

```python
async def tg_send_with_retry(token, method, payload, max_retries=3):
    url = f"https://api.telegram.org/bot{token}/{method}"
    for attempt in range(max_retries):
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json=payload, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                retry_after = r.json().get("parameters", {}).get("retry_after", 5)
                await asyncio.sleep(retry_after + 0.5)  # +0.5s buffer
            elif r.status_code in (400, 401, 403, 404):
                # Hard errors — don't retry
                raise TelegramError(r.status_code, r.json())
    raise TelegramError("max_retries exceeded")
```

**Famit at scale:** 1 message per call event → well within 30/s free tier. Only relevant at >30 concurrent call completions/second, which is beyond current scale.

---

### 8. MINI APPS (formerly WebApps) — 2026 State

Mini Apps are web apps (HTML/CSS/JS) that open inside Telegram, launched from a bot message button.

**Launch mechanisms:**
- Inline keyboard button: `{"web_app": {"url": "https://app.famit.in/mini"}}`
- Bot menu button (bottom-left in chat): `setMenuButton` with `web_app` type
- Direct URL: `https://t.me/{bot_username}/app` (for bots with linked Mini App)

**Init data authentication (backend verification):**

When user opens a Mini App, Telegram injects `window.Telegram.WebApp.initData` — a URL-encoded string containing:
- `user` — Telegram user object (id, first_name, last_name, username, language_code)
- `auth_date` — Unix timestamp of auth
- `hash` — HMAC-SHA256 signature

**Server-side verification (Python):**
```python
import hmac, hashlib, urllib.parse
def verify_tg_init_data(init_data_raw: str, bot_token: str) -> bool:
    parsed = dict(urllib.parse.parse_qsl(init_data_raw))
    received_hash = parsed.pop("hash", "")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_hash, received_hash)
```

**2026 additions to Mini Apps:**
- Full-screen layouts
- Landscape orientation support
- Home-screen shortcuts (add Mini App to phone home screen)
- Share flows
- Gyroscope access
- Telegram Stars subscriptions (recurring payments in Mini App)

**Famit use case:** Mini App for the post-call landing page — lead taps button → full-screen web app showing call summary, brochure viewer, booking calendar. No App Store required.

---

### 9. 2026 NEW FEATURES — MATERIAL FOR ARCHITECTURE DECISIONS

#### Managed Bots (Bot API 9.5, April 2026)
- A "manager bot" can create and control child bots on behalf of tenants
- `getManagedBotToken` method: manager bot receives token for a child bot after user confirms creation
- **Eliminates the BotFather copy-paste flow entirely**
- Famit can build: "Connect Telegram" onboarding button in panel → opens pre-filled bot creation → on confirm, Famit's manager bot receives the child token automatically → stores in vault
- This is the **correct multi-tenant provisioning path**

#### Bot-to-Bot Communication (Bot API 10.0, May 2026)
- One bot can send a message to another bot's username
- Both must opt in explicitly
- Use case: Famit orchestrator bot → specialized channel bots

#### Streaming Text (June 2026, Desktop 6.9)
- Bot can stream AI-generated text progressively (like ChatGPT streaming)
- Uses `editMessageText` in a loop with `parse_mode="HTML"` and `is_updating=true`
- Reduces perceived latency of LLM responses

#### Guardian Bots (June 2026, Desktop 6.9)
- Bots can automate group join-request processing
- Potential use: auto-approve leads joining a Famit product community group

#### Chat Automation (2026)
- Individual users can connect a bot to their personal Telegram account to handle replies on their behalf
- User controls which conversations the bot can access

---

### 10. FAMIT INTEGRATION CONTRACT — Complete

#### Per-Tenant Setup

```python
# Schema additions (additive, FORCE-RLS):
# communication_tenants:
#   telegram_bot_token TEXT (encrypted AES-256-GCM)
#   telegram_bot_username TEXT
#   telegram_founder_chat_id BIGINT     # founder's personal chat_id for hot-lead alerts
#   telegram_webhook_secret TEXT        # 32-char random hex, set at bot provisioning
#   telegram_file_id_cache JSONB        # {spaces_key: telegram_file_id} per tenant

# communication_sessions:
#   id UUID, tenant_id UUID, channel TEXT ('telegram'),
#   external_chat_id BIGINT, state TEXT,
#   history JSONB,  -- [{role, content}] array
#   lead_id UUID NULL,  -- linked CRM lead if matched
#   created_at TIMESTAMPTZ, last_message_at TIMESTAMPTZ
```

#### Webhook Setup (at tenant onboarding)

```python
async def setup_telegram_webhook(tenant_id: str):
    token = vault.get_secret(tenant_id, "telegram_bot_token")
    secret = secrets.token_hex(16)  # 32-char hex
    vault.set_secret(tenant_id, "telegram_webhook_secret", secret)

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={
                "url": f"https://panel.famit.in/comm/telegram/webhook/{tenant_id}",
                "allowed_updates": ["message", "callback_query"],
                "secret_token": secret,
                "max_connections": 40,
            }
        )
    return r.json()  # {"ok": True, "result": True}
```

#### Hot-Lead Alert (founder-facing — no opt-in needed)

```python
async def send_founder_hot_lead_alert(tenant_id: str, session: CallSession):
    token = vault.get_secret(tenant_id, "telegram_bot_token")
    founder_chat_id = tenant.telegram_founder_chat_id  # set at onboarding by founder
    text = (
        f"<b>HOT LEAD</b> — Score: {session.lead_score}/100\n\n"
        f"<b>Name:</b> {session.lead_name}\n"
        f"<b>Phone:</b> {session.lead_phone}\n"
        f"<b>Campaign:</b> {session.campaign_name}\n\n"
        f"<b>Summary:</b>\n{session.call_summary[:800]}"
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "Call Now", "url": f"tel:{session.lead_phone}"},
            {"text": "View in CRM", "url": f"https://panel.famit.in/crm/leads/{session.lead_id}"},
        ]]
    }
    await tg_send_message(token, founder_chat_id, text, parse_mode="HTML", reply_markup=keyboard)
```

#### Post-Call Auto-Message (contact-facing — requires prior opt-in via deep link)

```python
async def send_post_call_followup_telegram(tenant_id: str, session: CallSession):
    # Gate: contact must have previously started the bot
    contact_session = await get_session(tenant_id, "telegram", session.lead_phone)
    if not contact_session or not contact_session.telegram_chat_id:
        return  # cannot send cold; skip silently (try other channels)

    token = vault.get_secret(tenant_id, "telegram_bot_token")
    chat_id = contact_session.telegram_chat_id

    # 1. Send text summary (up to 4096 chars)
    summary_text = f"Hi {session.lead_name}! Here's your call summary:\n\n{session.call_summary}"
    await tg_send(token, "sendMessage", {"chat_id": chat_id, "text": summary_text[:4096], "parse_mode": "HTML"})

    # 2. Send banner (if configured)
    if session.banner_spaces_key:
        banner_url = spaces.signed_url(session.banner_spaces_key)
        await tg_send(token, "sendPhoto", {"chat_id": chat_id, "photo": banner_url, "caption": tenant.brand_tagline})

    # 3. Send brochure (check file_id cache first)
    if session.brochure_spaces_key:
        file_id = tenant.telegram_file_id_cache.get(session.brochure_spaces_key)
        if file_id:
            doc_param = file_id  # reuse without re-upload
        else:
            doc_param = spaces.signed_url(session.brochure_spaces_key)  # first time: URL upload
        result = await tg_send(token, "sendDocument", {
            "chat_id": chat_id, "document": doc_param,
            "caption": "Your brochure",
            "reply_markup": build_ai_chat_keyboard()
        })
        # Cache the file_id for next time
        if "result" in result and "document" in result["result"]:
            new_file_id = result["result"]["document"]["file_id"]
            await cache_telegram_file_id(tenant_id, session.brochure_spaces_key, new_file_id)
```

---

### 11. ADVERSARIAL FACT CHECKS

**CLAIM: "Telegram Bot API 9.6 is from April 3, 2026"**
SOURCE: TechTimes article on Bot API 10.0 (May 8, 2026) corroborates Bot API 9.6 as prior release. Official changelog at core.telegram.org/bots/api-changelog.
VERDICT: CONFIRMED. Managed Bots introduced in 9.5-9.6 timeframe.

**CLAIM: "sendDocument via URL only works for PDF and ZIP"**
SOURCE: core.telegram.org/bots/api sendDocument docs.
VERDICT: CONFIRMED. Non-PDF/ZIP files via URL may not work reliably. Use multipart for DOCX, XLSX, etc.

**CLAIM: "Bots cannot cold-message users who never interacted"**
SOURCE: core.telegram.org/bots/faq + Latenode community documentation.
VERDICT: CONFIRMED as a hard API restriction. Exception: groups/channels where bot is admin (can post freely without prior user interaction). For 1:1 private chats, user must send first message.

**CLAIM: "Paid Broadcasts require 10,000 Stars balance"**
SOURCE: core.telegram.org/bots/api rate limits section.
VERDICT: CONFIRMED. 0.1 Stars/msg over the free 30 msg/s threshold.

**CLAIM: "Webhook secret_token must be X-Telegram-Bot-Api-Secret-Token header"**
SOURCE: core.telegram.org/bots/api setWebhook docs + Marvin's Webhook Guide.
VERDICT: CONFIRMED. Exact header name. Validate on every incoming request.

**CLAIM: "Callback queries must be answered within 10 seconds"**
SOURCE: core.telegram.org/bots/api answerCallbackQuery docs.
VERDICT: CONFIRMED. After 10s, Telegram shows error/loading spinner to user. Always answer immediately then do heavy processing asynchronously.

---

### 12. KEY ARCHITECTURAL DECISIONS FOR FAMIT

1. **Telegram is the FIRST channel to ship.** Zero approval wait, zero cost, instant rich media, hot-lead alert works today. Ship this before Email and SMS.

2. **One bot per tenant (not one shared bot).** Each tenant creates their own bot → own token → their branding. Use Managed Bots API (Bot API 9.5+) for automated provisioning at onboarding.

3. **Webhook mode in production; long-poll only for local dev.** Mount at `/comm/telegram/webhook/{tenant_id}` in the additive `comm_router`. Verify `X-Telegram-Bot-Api-Secret-Token` header on every request.

4. **file_id cache is mandatory for brochure sends at any volume.** Upload once, cache forever per tenant. Stored in `communication_tenants.telegram_file_id_cache JSONB`.

5. **Founder hot-lead alert is the HIGHEST PRIORITY feature.** Founder starts their own bot during onboarding → stores their chat_id → alerts fire instantly after `_finalize_call()` when `lead_score >= threshold`. This requires ZERO contact opt-in (founder already started the bot).

6. **Contact-facing messaging requires opt-in.** The deep link (`t.me/bot?start=`) is sent to the lead via SMS or WhatsApp FIRST. Only after they tap START does Famit have permission to send. Track in `communication_sessions.telegram_chat_id`.

7. **LLM conversation brain reuses `caller.py:1518` Groq pattern.** History stored as `[{role, content}]` JSONB in `communication_sessions`. Same `FallbackAdapter([groq, openrouter-free])` as the existing brain.

8. **answerCallbackQuery is a hard 10-second contract.** All callback handlers must call it immediately, then process asynchronously. Failure = broken UX (loading spinner never stops for user).

9. **Streaming replies (June 2026 Desktop 6.9):** Implement `editMessageText` streaming for the AI conversation brain — send initial "thinking..." message → stream tokens via periodic edits. Reduces perceived LLM latency from 1-2s to near-instant first character.

10. **ParseMode=HTML, not MarkdownV2.** MarkdownV2 requires escaping almost every special character (`.`, `!`, `(`, etc.) — a reliability nightmare. HTML is cleaner for programmatic generation.

---

**Sources:**
- [Telegram Bot API Reference](https://core.telegram.org/bots/api)
- [BotFather Tutorial](https://core.telegram.org/bots/tutorial)
- [Bots Introduction for Developers](https://core.telegram.org/bots)
- [Bot Features](https://core.telegram.org/bots/features)
- [Marvin's Webhook Guide](https://core.telegram.org/bots/webhooks)
- [Bot API Changelog](https://core.telegram.org/bots/api-changelog)
- [Mini Apps](https://core.telegram.org/bots/webapps)
- [Deep Linking — aiogram](https://docs.aiogram.dev/en/latest/utils/deep_linking.html)
- [python-telegram-bot Conversation Bot](https://deepwiki.com/python-telegram-bot/python-telegram-bot/5.3-conversation-bot)
- [Bot API 10.0 — Bot-to-Bot](https://www.techtimes.com/articles/316790/20260518/telegrams-bot-api-now-lets-autonomous-ai-agents-coordinate-directly-no-federal-multi-agent.htm)
- [Bot API 9.6 — Managed Bots](https://aihola.com/article/telegram-managed-bots-api)
- [Desktop 6.9 — Streaming + Guardian + Rich Text](https://www.techtimes.com/articles/318257/20260611/telegram-desktop-69-bots-get-document-grade-formatting-guardian-controls-streaming.htm)
- [Init Data Authentication — Telegram Mini Apps](https://docs.telegram-mini-apps.com/platform/init-data)
- [Long Polling vs Webhooks — grammY](https://grammy.dev/guide/deployment-types)
- [GitGuardian — Token Leak Remediation](https://www.gitguardian.com/remediation/telegram-bot-token)
- [Telegram Bot API 2026 Guide — ZeroClaw](https://zeroclaws.io/blog/telegram-bot-api-2026-ai-agent-developers-guide)

---

**END telegram-bot-api RESEARCH**

---

## PHASE: cost-routing — Channel Cost Model + Intelligent Cost Routing
**Date:** 2026-06-14
**Scope:** Real per-unit cost of every channel (Telegram, Email, SMS, WhatsApp), cost-optimized routing logic, fallback chains, India-specific considerations, and the Famit billing model. Sourced.

---

### 1. VERIFIED COST TABLE — ALL CHANNELS (India, 2026)

| Channel | Provider | Cost Per Unit | Notes |
|---|---|---|---|
| **Telegram** | Bot API (self-hosted or BotFather) | **₹0** | Free unconditionally for <30 msg/s. Paid Broadcasts at 0.1 Stars/msg only above 30 msg/s rate cap. |
| **Telegram** (paid broadcast) | Bot API | **~₹0.13/msg** (0.1 Stars × $0.013/Star × ₹84/USD) | Only relevant at >30 simultaneous sends/sec — far beyond Famit's current scale. |
| **Email** | Resend (free tier) | **₹0** | 3,000 emails/month, 100/day cap. Covers initial tenants. |
| **Email** | Resend Pro | **~₹0.034/email** ($20/mo for 50K = $0.0004/email × ₹84) | Effectively ₹0.03–0.04 per transactional email. |
| **Email** | Brevo free tier | **₹0** | 300/day (9,000/month) permanent; no credit card. |
| **SMS — promotional** | MSG91 India | **₹0.17–0.25/SMS** (excl. GST) | Promo to non-DND; DLT template required; time-window enforced. |
| **SMS — service implicit** | MSG91 India | **₹0.16–0.18/SMS** (excl. GST) | Post-call followup category; no DND block; no time restriction. |
| **SMS — enterprise** | MSG91 (negotiated) | **₹0.13/SMS** | At large volume; requires account manager. |
| **WhatsApp — marketing** | Meta Cloud API | **~₹0.86/conversation** (Jan 2026) | Per delivered template message (as of Jul 2025 pricing model change). |
| **WhatsApp — utility** | Meta Cloud API | **~₹0.115–0.145/conversation** | Post-call summary within known transaction; lowest approved-template cost. |
| **WhatsApp — service window** | Meta Cloud API | **₹0** | Any message within 24h window opened by a user-initiated message. |

**Key sources:** MSG91 pricing page (₹0.16–0.25 confirmed); Telegram Bot API docs (30 msg/s free); Resend pricing (3K free, $20/50K); WhatsApp India per-message update Jan 2026; Telegram Stars ≈ $0.013/Star.

---

### 2. COST PER MESSAGE — ABSOLUTE RANKING (lowest to highest)

1. **Telegram** — ₹0.00 (free at Famit's scale, permanently)
2. **Email (Resend/Brevo free tier)** — ₹0.00 (up to 3K–9K/month)
3. **Email (Resend Pro)** — ₹0.03–0.04/email (negligible)
4. **WhatsApp utility (template, within 24h window after user reply)** — ₹0.00 (free service window)
5. **WhatsApp utility (cold template outside window)** — ₹0.12–0.15/conversation
6. **SMS service-implicit** — ₹0.16–0.18/SMS (+18% GST = ~₹0.19–0.21 effective)
7. **WhatsApp marketing template** — ₹0.86/conversation (+BSP fees if any)
8. **SMS promotional (to DND numbers via promo route)** — blocked by carrier (₹∞ = undeliverable)

**Strategic conclusion:** Telegram is 16–100× cheaper than SMS on a per-message basis. Email is 5–6× cheaper than SMS. WhatsApp utility sits between email and SMS in cost.

---

### 3. INTELLIGENT COST ROUTING — DECISION LOGIC

The core principle (sourced from MoEngage Smart Channel Routing analysis showing 85% cost reduction): **arrange channels by increasing cost, attempt delivery on the cheapest channel first, fall back only when undeliverable**.

#### 3a. ROUTING TIERS FOR FAMIT

**Tier 0 — Zero-cost channels (attempt first, always):**
1. **Telegram** — if `lead.telegram_chat_id IS NOT NULL` (lead previously started the bot)
2. **Email** — if `lead.email IS NOT NULL AND communication_consents.email = TRUE`
3. **WhatsApp service window** — if within 24h of a user-initiated message (free, no template needed)

**Tier 1 — Near-zero cost (fallback if Tier 0 undeliverable):**
4. **WhatsApp utility template** — ₹0.12–0.15/msg; use when WA window is open but approaching 24h close, or for approved post-call templates

**Tier 2 — Metered (use only when Tier 0 + Tier 1 fail or unregistered):**
5. **SMS service-implicit** (MSG91) — ₹0.16–0.21/msg effective; requires DLT template ID on the send record; gates: `lead.phone_verified = TRUE AND communication_tenants.sms_dlt_template_id IS NOT NULL`

**Never-auto-use (manual/campaign-scheduled only):**
- **WhatsApp marketing template** — ₹0.86/msg; only for explicitly opted-in marketing campaigns, not automated post-call flows

#### 3b. ROUTING PSEUDOCODE (Python, additive to caller.py post-call hook)

```python
async def route_post_call_message(tenant_id: str, session: CallSession):
    """
    Cost-optimized channel router.
    Attempts Tier-0 channels first (free), falls back to metered only if needed.
    Fire-and-forget; never raises into call loop.
    """
    sent = False
    result_log = []

    # --- TIER 0A: Telegram (₹0) ---
    tg_chat_id = await get_telegram_chat_id(tenant_id, session.lead_id)
    if tg_chat_id and tenant.telegram_enabled:
        try:
            await send_telegram_post_call(tenant_id, tg_chat_id, session)
            result_log.append({"channel": "telegram", "cost_paise": 0, "status": "sent"})
            sent = True
        except TelegramError as e:
            result_log.append({"channel": "telegram", "cost_paise": 0, "status": f"failed:{e}"})

    # --- TIER 0B: Email (₹0 on free tier / ~₹0.034) ---
    if not sent and session.lead_email and tenant.email_enabled:
        try:
            await send_email_post_call(tenant_id, session)
            email_cost = await estimate_email_cost_paise(tenant_id)  # 0 if on free tier
            result_log.append({"channel": "email", "cost_paise": email_cost, "status": "sent"})
            sent = True
        except EmailError as e:
            result_log.append({"channel": "email", "cost_paise": 0, "status": f"failed:{e}"})

    # --- TIER 0C: WhatsApp free service window ---
    if not sent and tenant.wa_enabled:
        wa_window_open = await is_wa_window_open(tenant_id, session.lead_phone)
        if wa_window_open:
            try:
                await send_wa_free_text(tenant_id, session)
                result_log.append({"channel": "whatsapp_free", "cost_paise": 0, "status": "sent"})
                sent = True
            except WAError as e:
                result_log.append({"channel": "whatsapp_free", "cost_paise": 0, "status": f"failed:{e}"})

    # --- TIER 1: WhatsApp utility template (~₹0.13) ---
    if not sent and tenant.wa_enabled and tenant.wa_followup_template:
        try:
            await send_wa_template(tenant_id, session)
            result_log.append({"channel": "whatsapp_utility", "cost_paise": 13, "status": "sent"})
            sent = True
        except WAError as e:
            result_log.append({"channel": "whatsapp_utility", "cost_paise": 0, "status": f"failed:{e}"})

    # --- TIER 2: SMS (~₹19 paise effective incl. GST) ---
    if not sent and tenant.sms_enabled and tenant.sms_dlt_template_id:
        consent_ok = await check_sms_consent(tenant_id, session.lead_phone)
        if consent_ok:
            try:
                await send_sms_post_call(tenant_id, session)
                result_log.append({"channel": "sms", "cost_paise": 19, "status": "sent"})
                sent = True
            except SMSError as e:
                result_log.append({"channel": "sms", "cost_paise": 0, "status": f"failed:{e}"})

    # Audit every attempt (additive to existing audit.py pattern)
    await log_channel_attempts(tenant_id, session.call_id, result_log, sent)
    # Meter actual cost in wallet (channel_cost event, paise)
    if result_log:
        total_cost = sum(r["cost_paise"] for r in result_log if r["status"] == "sent")
        if total_cost > 0:
            await wallet.debit(tenant_id, total_cost, channel="comms",
                               reference=session.call_id, idempotency_key=f"comms:{session.call_id}")
```

#### 3c. FOUNDER HOT-LEAD ALERT — SEPARATE (always Telegram, no fallback needed)

```python
async def send_founder_alert(tenant_id: str, session: CallSession):
    """
    Founder-facing alert only. Telegram is the ONLY channel — no fallback needed.
    Founder starts the bot at onboarding, so chat_id is always available.
    Cost: ₹0.
    """
    if session.lead_score < tenant.hot_lead_threshold:
        return  # not a hot lead
    founder_chat_id = tenant.telegram_founder_chat_id
    if not founder_chat_id:
        return  # founder hasn't set up Telegram yet (UI prompts this at onboarding)
    await send_telegram_hot_lead_alert(tenant_id, founder_chat_id, session)
```

---

### 4. COST ROUTING — MESSAGE TYPE MATRIX

Different message types warrant different routing policies (not all messages need all tiers):

| Message Type | Primary | Fallback 1 | Fallback 2 | Skip |
|---|---|---|---|---|
| **Founder hot-lead alert** | Telegram (₹0) | — | — | No SMS/email for founder alerts |
| **Post-call contact summary** | Telegram (₹0) | Email (₹0–0.04) | WA utility (₹0.13) | SMS only if above fails and DLT ready |
| **PDF brochure delivery** | Telegram (₹0) | Email (₹0–0.04, attach) | WA (₹0.13, link) | SMS (branded link only, ₹0.19) |
| **Campaign broadcast** | Email (₹0–0.04) | WA marketing (₹0.86, manual) | SMS promo (₹0.17+, opt-in only) | Not Telegram (cold-msg restriction) |
| **Inbound reply (AI convo)** | Telegram (₹0) | Email threaded (₹0–0.04) | WhatsApp free window (₹0) | SMS (too limited for conversation) |
| **OTP / one-time code** | SMS (₹0.16) | — | — | Telegram/Email unreliable for OTP UX |
| **Booking confirmation** | Email (₹0–0.04) | WA utility (₹0.13) | SMS (₹0.19) | Telegram (contact may not have started bot) |

---

### 5. COST SAVING PROJECTIONS — FAMIT SCALE

**Scenario: 1,000 calls/day → 1,000 post-call messages/day**

**Baseline (SMS-only, no routing):**
- 1,000 × ₹0.19 (incl. GST) = **₹190/day** = **₹5,700/month**

**With intelligent cost routing (assumed distribution):**
- 40% have Telegram bot started → 400 msgs via Telegram @ ₹0 = **₹0**
- 40% have email on file → 400 msgs via email @ ₹0.034 = **₹13.60**
- 15% via WhatsApp utility (no TG/email) → 150 msgs @ ₹0.13 = **₹19.50**
- 5% via SMS (no other channel available, DLT cleared) → 50 msgs @ ₹0.19 = **₹9.50**
- **Total: ₹42.60/day = ₹1,278/month**
- **Saving vs SMS-only: 78% cost reduction**

This mirrors MoEngage's real-world 85% cost reduction finding from channel priority routing.

**At higher Telegram adoption (60%):**
- 600 via Telegram @ ₹0 = ₹0
- 30% email = ₹10.20
- 8% WA = ₹10.40
- 2% SMS = ₹3.80
- **Total: ₹24.40/day = ₹732/month** (87% saving vs baseline)

---

### 6. CHANNEL SELECTION RULES — BILLING POLICY FOR TENANTS

Famit bills tenants at a markup over provider cost. Cost routing also determines the billing event:

| Channel Used | Famit buys at | Bills tenant at | Gross margin | Notes |
|---|---|---|---|---|
| Telegram | ₹0 | ₹0 (bundled in plan) | 100% (platform value) | No per-msg charge; included in subscription |
| Email | ₹0–0.034 | ₹0 (bundled in plan) | 100% | Resend free tier absorbed at launch |
| WhatsApp utility | ₹0.13 | ₹0.25/msg | ~48% margin | Bill separately as "WhatsApp message credit" |
| SMS | ₹0.17–0.19 | ₹0.25–0.30/msg | ~37–47% margin | Bill as "SMS credit" from wallet |
| WhatsApp marketing | ₹0.86 | ₹1.20/conversation | ~28% margin | Campaign blast, tenant-initiated only |

**Implementation:** All metered costs deduct from the existing `wallet_accounts` (paise-denominated ACID ledger, already live). New `channel` field values: `'telegram'`, `'email'`, `'sms'`, `'whatsapp_utility'`, `'whatsapp_marketing'`. Telegram and email = zero-cost events (log audit row with `amount_minor=0`).

---

### 7. FAILURE HANDLING + RETRY COST POLICY

**Don't retry expensive channels if free channels are available:**

```python
RETRY_POLICY = {
    "telegram": {"max_retries": 3, "backoff": "exponential", "cost_per_retry": 0},
    "email": {"max_retries": 3, "backoff": "exponential", "cost_per_retry": 0},
    "whatsapp_utility": {"max_retries": 2, "backoff": "linear_5s", "cost_per_retry": 13},  # paise
    "sms": {"max_retries": 1, "backoff": "none", "cost_per_retry": 19},  # paise; 1 retry max
}
# Rule: never retry SMS if TG or email already succeeded. Never burn 2× SMS cost on duplicate.
# Idempotency key on wallet debit: f"comms:{call_id}:{channel}" prevents double-charge on retry.
```

**Delivery confirmation loop (SMS only):** MSG91 sends delivery webhooks (`POST /comm/webhook/msg91/delivery`). If `status = FAILED` within 60s, escalate to the next cheaper channel if available (e.g., email). Do NOT re-attempt SMS — one SMS per call per contact.

---

### 8. COST-ROUTING COMPLIANCE GATES (India-specific)

These gates must fire BEFORE any channel send, integrated into the router:

| Gate | Channel | Rule |
|---|---|---|
| DLT template registered | SMS | Block send if `sms_dlt_template_id IS NULL` for tenant. Show UI error: "Register DLT template first." |
| DLT promotional time window | SMS promo | Block if local IST time outside 10:00–21:00. Queue for next window. |
| WhatsApp opt-in verified | WA (marketing) | Block if `communication_consents.whatsapp_marketing = FALSE`. |
| WA template approved | WA (utility/marketing) | Block if `wa_status != 'approved'`. |
| Telegram bot started | Telegram | Skip silently (not an error; contact hasn't onboarded bot). |
| DPDP consent stored | SMS + WA | Block if no consent row for this (tenant_id, phone, channel). |
| DND check | SMS promo | Carrier handles automatically when using -P header (DND-blocked numbers rejected by carrier). |

---

### 9. ADVERSARIAL FACT-CHECKS

**CLAIM: "Telegram Bot API is free up to 30 msg/s"**
SOURCE: core.telegram.org Bot API rate limits; Telegram Stars conversion confirmed at $0.013/Star (StarsEarn.com, June 2026).
VERDICT: CONFIRMED. 0.1 Stars × $0.013/Star × ₹84/USD = ₹0.109/msg over the 30/s threshold. Famit does not approach this threshold at current scale.

**CLAIM: "WhatsApp utility template = ₹0.115–0.145 per message (Jan 2026)"**
SOURCE: Multiple India-focused WA pricing guides (whautomate.com, uniquedigitaloutreach.in, chati.ai) all cite Jan 2026 update as per-delivered-message pricing (Meta moved from per-conversation to per-message Jul 2025).
VERDICT: CONFIRMED. Utility = ~₹0.12–0.15; marketing = ~₹0.86. The July 2025 pricing model change from per-conversation to per-delivered-message is material — prior research in this log used "per-conversation" framing; the exact per-message figure is now in the same range for most use cases.

**CLAIM: "85% cost reduction from channel priority routing"**
SOURCE: MoEngage Smart Channel Routing blog (moengage.com); example: $4,700 → $680 for 1M messages.
VERDICT: CONFIRMED as a documented production result. The specific numbers (Push 50% free, Email 40%, SMS 10%) are illustrative; Famit's distribution will differ (Telegram instead of Push). The directional saving (70–87%) is conservative and realistic.

**CLAIM: "MSG91 service SMS = ₹0.16–0.18 + 18% GST"**
SOURCE: msg91.com/in/pricing/sms (live fetch, June 2026): ₹0.17 at 60K–450K tier, ₹0.16 at 962K tier, ₹0.25 at 5K tier. GST 18% is standard on software/API services (India).
VERDICT: CONFIRMED. Effective cost at Famit's volume (30K/month) = ₹0.18 + GST = ~₹0.21/SMS.

**CLAIM: "Brevo free = 300/day, Resend free = 3,000/month (100/day)"**
SOURCE: forwardemail.net Brevo vs Resend comparison (2026); tiergauge.com/tools/resend (April 2026).
VERDICT: CONFIRMED. Brevo's daily cap (300) is 3× Resend's daily cap (100), making Brevo the better free-tier choice for burst sends. Resend is better for consistent low-volume with good developer DX.

**CLAIM: "WhatsApp service window messages = ₹0"**
SOURCE: fyno.io blog (fetched): "WhatsApp Service (24-hour window): Free". Confirmed by Meta pricing documentation.
VERDICT: CONFIRMED. A user replying to a WA message opens a free 24h window. Post-call auto-reply to a lead who already messaged = ₹0.

---

### 10. ROUTING SUMMARY (ONE-LINER PER CHANNEL)

- **Telegram:** Always first, always free, always richest (4096-char text + photo + video + PDF). Ship day 1.
- **Email:** Always second, near-zero cost, highest-trust for brochures and formal summaries. No opt-in restriction for transactional.
- **WhatsApp:** Third — free in 24h window, ₹0.12 utility template outside it. Existing infra. High India reach.
- **SMS:** Last resort only — ₹0.19/msg effective, DLT registration required, carrier compliance overhead. Reserve for leads with no Telegram/email/WA.
- **WhatsApp marketing:** Never in automated post-call flow — ₹0.86/msg, for explicit campaign blasts only.

---

**Sources:**
- [MSG91 SMS Pricing India](https://msg91.com/in/pricing/sms)
- [Telegram Stars Value 2026 — StarsEarn](https://starsearn.com/guides/telegram-stars-price-calculator)
- [Telegram Bot API Pricing 2026 — Botract](https://www.botract.com/blog/telegram-bot-cost-pricing-guide)
- [Resend Pricing 2026 — StackScored](https://www.stackscored.com/pricing/transactional-email/resend/)
- [Brevo vs Resend Comparison 2026 — ForwardEmail](https://forwardemail.net/en/blog/resend-vs-brevo-email-service-comparison)
- [WhatsApp India Pricing 2026 — Unique Digital Outreach](https://uniquedigitaloutreach.in/2026/03/23/whatsapp-business-api-pricing-in-india-2026-complete-cost-breakdown/)
- [WhatsApp vs SMS Cost India — Fyno](https://www.fyno.io/blog/how-to-save-big-on-sms-costs-with-whatsapp-in-india-updated-clst1n275005yxv47ioyo7mff)
- [Smart Channel Routing 85% Saving — MoEngage](https://www.moengage.com/blog/smart-send-send-transactional-messages-most-cost-effectively/)
- [Telegram OTP + Omnichannel Routing — BSG](https://bsg.world/telegram-otp)
- [Omnichannel Channel Fallback — Wizbrand](https://www.wizbrand.com/tutorials/channel-fallback/)
- [WhatsApp Business API Pricing 2026 — ChatMaxima](https://chatmaxima.com/whatsapp-api-pricing/)
- [Email API Pricing June 2026 — BuildMVPFast](https://www.buildmvpfast.com/api-costs/email)

---

**END cost-routing RESEARCH**

---

## PHASE: hot-lead-automation — Hot-Lead Detection, Instant Founder Alert, Post-Alert Drip (2026-06-15)

**Scope:** What signals define a hot lead from voice call transcripts + WhatsApp conversations; real-time trigger architecture; Telegram Bot API instant founder alert payload; post-alert multi-step nurture drip (WhatsApp + Email + SMS); LLM intent extraction from transcripts; multi-tenant isolation. Sourced, adversarially verified, grounded in Famit's live codebase.

---

### 1. HOT-LEAD SIGNALS — What Defines a Hot Lead

#### From Voice Call Transcripts (Primary Signal Source)

The live codebase (`caller.py:_finalize_call` line 1873) already seeds `call_summary`, `next_action`, `call_outcome`, and `interest` (int 0–100) onto the WA thread JSON after every call. The `interest` field IS the hot-lead seed — the pipeline scores against it and enriches it with a full-transcript LLM pass.

**Production-grade signal taxonomy (sourced: Bland AI blog, Kixie, AssemblyAI, Trust Insights):**

| Signal Category | Specific Indicators | Weight |
|---|---|---|
| **Budget language** | "budget approved", "sanctioned", "already allocated", "can pay now" | HIGH |
| **Timeline urgency** | "need this by Friday", "operational by quarter end", "urgently need" | HIGH |
| **Decision-maker presence** | "I'm the MD", "I decide", "our team has reviewed", "will sign off today" | HIGH |
| **Implementation questions** | "how quickly can you deploy?", "what's the onboarding process?", "can we start next week?" | HIGH |
| **Competitor comparison** | "comparing you to X", "we used Y before and it failed" | MEDIUM-HIGH |
| **Positive sentiment spike** | Sustained enthusiasm, rising pitch, fast follow-up questions | MEDIUM |
| **Call duration** | >3 min for outbound (attention held); >6 min = strong buying signal | MEDIUM |
| **Price-specific questions** | "what's the monthly cost?", "is there a setup fee?" (specifics, not browsing) | MEDIUM-HIGH |
| **Third-party involvement** | "let me loop in my accountant/partner" — delay but high real intent | MEDIUM |
| **Follow-up request** | "can you send me more details?", "email me the brochure" | HIGH |

**What does NOT score as hot (adversarially verified):**
- General curiosity ("just checking") without specifics — LOW
- Long calls with persistent objections — negative adjustment to interest
- Price shock ("that's too expensive") without budget negotiation — COLD
- "Call me later" / "busy now" without specific next time — COLD
- "Dual-channel engines fusing acoustic + text beat text-only by ~40% accuracy" (Kixie, 2026) — Famit's `interest` field already incorporates this during the call

#### From WhatsApp Thread (Secondary Signal Source)

Signals from `communication_sessions` thread JSON (already seeded by `_wa_ai_followup`):
- Message count >3 in 24h window = high engagement → upgrade WARM to HOT
- User-initiated media request ("send me the brochure") = HOT
- User shares personal specifics (exact address, product model, team size) = HOT
- User asks "what are the next steps?" = HOT
- Sentiment arc: neutral → positive across multiple turns = moderate signal

---

### 2. SCORING THRESHOLD — Hot / Warm / Cold / Dead

**Recommended thresholds (grounded in live `interest` field, 0–100):**

| Score Band | Classification | Immediate Action |
|---|---|---|
| 75–100 | HOT LEAD | Instant Telegram alert to founder + full drip sequence |
| 50–74 | WARM LEAD | 24h-delay nurture drip; no founder interrupt |
| 25–49 | COOL LEAD | Standard post-call WA template only |
| 0–24 | COLD | Log only; suppress messaging |

**Two-gate qualification:**
- Gate A: `raw_interest >= 50` — fast, no LLM cost, immediate. Spawns the pipeline.
- Gate B: LLM re-score `interest_score >= 75` AND `hot_lead=true` — Groq, 2–5s. Fires founder alert.

Gate A prevents LLM cost on cold calls. Gate B prevents false-positive interrupts to the founder.

**LLM re-scoring prompt schema (sourced: AssemblyAI blog, AssemblyAI JSON output format):**

```python
HOT_LEAD_PROMPT = """
ROLE: You are a senior sales analyst at an AI voice sales company.
CONTEXT: Outbound AI sales call for campaign: {campaign_name}.
TRANSCRIPT:
{transcript_text}

INSTRUCTION: Score this call. Return ONLY valid JSON, no preamble.

FORMAT:
{
  "interest_score": <int 0-100>,
  "hot_lead": <bool>,
  "primary_intent": "<buying|exploring|objecting|neutral>",
  "urgency": "<immediate|weeks|months|none>",
  "budget_signal": "<confirmed|possible|not_mentioned|negative>",
  "decision_maker": <bool>,
  "next_action": "<one concrete next step, max 15 words>",
  "hot_lead_reason": "<15-word explanation if hot_lead=true, else empty string>",
  "key_phrases": ["<phrase1>", "<phrase2>"]
}
"""
```

**Cost:** Groq Llama-3.3-70B = $0.59/1M tokens. Avg call transcript ~1,000 tokens. 1,000 calls/day = $0.59/day. Trivial.

---

### 3. TRIGGER ARCHITECTURE — Webhook-Native, Post-Call Hook

**Verdict: No new infra needed. Extend `_finalize_call()` with an additive asyncio task.**

```python
# caller.py:_finalize_call() — ADDITIVE, after existing _wa_ai_followup() call:
interest = int(call_data.get("interest", 0))
if interest >= int(os.getenv("HOT_LEAD_GATE_A", "50")):
    asyncio.create_task(_hot_lead_pipeline(tenant_id, call_data, transcript))
    # fire-and-forget; never raises into call loop
```

```python
async def _hot_lead_pipeline(tenant_id: str, call_data: dict, transcript: str):
    try:
        # Gate B: LLM re-score
        enriched = await _llm_hot_lead_score(transcript, call_data)
        if not enriched.get("hot_lead") or enriched.get("interest_score", 0) < 75:
            _log_cool_lead(tenant_id, call_data, enriched)
            return

        # Fire all three outputs IN PARALLEL — never wait for one before the next
        await asyncio.gather(
            _alert_founder_telegram(tenant_id, call_data, enriched),
            _start_contact_drip(tenant_id, call_data, enriched),
            _log_hot_lead_db(tenant_id, call_data, enriched),
            return_exceptions=True   # never raise — call already done
        )
    except Exception as e:
        logger.error(f"[HOT-LEAD] pipeline failed: {e}")
```

**Why NOT polling or a separate webhook processor:** The call event is already in memory at `_finalize_call`. Adding an async task costs microseconds. A separate webhook processor (like Retell's `call_analyzed` event) only makes sense if Famit uses an external voice platform — currently Famit owns the loop via LiveKit.

---

### 4. TELEGRAM HOT-LEAD ALERT — Exact Payload

**This is the unblocked path. No Meta verification. No DLT. Zero cost. Instant.**

**Pre-requisite (one-time per tenant):** Founder sends any message to the tenant's bot → bot receives their `chat_id` → stored as `founder_telegram_chat_id` in `provider_credentials` (FORCE-RLS). Thereafter the bot can alert freely.

**Exact API call:**

```python
async def _alert_founder_telegram(tenant_id: str, call_data: dict, enriched: dict):
    token   = vault.get_secret(tenant_id, "telegram_bot_token")
    chat_id = vault.get_secret(tenant_id, "founder_telegram_chat_id")
    if not token or not chat_id:
        return   # not configured — graceful dormancy (same pattern as is_configured())

    text = (
        "<b>HOT LEAD ALERT</b>\n\n"
        f"<b>Name:</b> {call_data.get('lead_name','Unknown')}\n"
        f"<b>Phone:</b> <code>{call_data.get('phone','')}</code>\n"
        f"<b>Campaign:</b> {call_data.get('campaign_name','')}\n"
        f"<b>Duration:</b> {int(call_data.get('duration_s',0))//60}m "
            f"{int(call_data.get('duration_s',0))%60}s\n"
        f"<b>Score:</b> {enriched.get('interest_score',0)}/100\n"
        f"<b>Why hot:</b> {enriched.get('hot_lead_reason','')}\n"
        f"<b>Next action:</b> {enriched.get('next_action','Follow up immediately')}\n"
    )

    reply_markup = {"inline_keyboard": [[
        {"text": "Call Now",        "url": f"tel:{call_data.get('phone','')}"},
        {"text": "View Transcript", "callback_data": f"tscript:{call_data['call_id']}"},
    ],[
        {"text": "Mark Handled",   "callback_data": f"handled:{call_data['call_id']}"},
        {"text": "Snooze 1h",      "callback_data": f"snooze:{call_data['call_id']}:60"},
    ]]}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "reply_markup": reply_markup,
                "disable_notification": False,  # SOUND ON — this is an interrupt
            }
        )
    return resp.json()
```

**Key API facts (sourced: core.telegram.org/bots/api, Rollout guide):**
- Endpoint: `POST https://api.telegram.org/bot{token}/sendMessage`
- Required params: `chat_id` (int64 or @username), `text` (1–4096 chars)
- `parse_mode="HTML"`: use `<b>`, `<i>`, `<code>`, `<a>` — NOT MarkdownV2 (fragile for programmatic text)
- `disable_notification=false`: delivers with SOUND — critical for hot alerts
- `inline_keyboard`: 2D array; `url` buttons open dialer/browser; `callback_data` max 64 bytes fires webhook
- Rate limit: 1 msg/s to same chat, 30 msg/s total across all chats. Famit's volume is negligible.
- Retry: on HTTP 429 (Too Many Requests), Telegram returns `retry_after` seconds. Implement 3-retry exponential backoff.

**Founder actions via callback:**
- "View Transcript" → bot fetches from DO Spaces presigned URL → sends as `sendDocument` (PDF) or `sendMessage` (text chunks)
- "Mark Handled" → `answerCallbackQuery` immediately (≤10s hard deadline) → update `communication_hot_leads.converted_at` → cancel drip tasks
- "Snooze 1h" → `answerCallbackQuery` → schedule re-alert via drip engine at T+60min

---

### 5. POST-ALERT CONTACT NURTURE DRIP

**Two parallel tracks after a hot-lead call:**
- **Track A (founder-facing):** Telegram alert (immediate, above)
- **Track B (contact-facing):** Automated multi-channel nurture sequence

**Verified drip sequence (sourced: TextMagic, Gallabox, chati.ai, Spurnow):**

| Step | Delay | Channel | Content | Goal |
|---|---|---|---|---|
| T+0 | Immediate | WhatsApp (approved utility template) | Call summary + next step + "Reply to continue" | Open 24h conversation window |
| T+0 | Immediate (parallel) | Email (if captured) | Full HTML summary + PDF brochure attached | Trust + reference document |
| T+15m | 15 minutes | Telegram (if contact has messaged bot) | Banner image + "Book a slot" InlineKeyboard | Rich media engagement |
| T+2h | 2 hours | SMS (if DLT approved + opted in) | 160-char teaser + branded short link | Highest SMS open rate window |
| T+24h | 24 hours | WhatsApp (free-form if window open; template if cold) | Personal follow-up or brochure + "When can we connect?" | Keep warm |
| T+3d | 3 days | Email | Case study / social proof ("a similar business…") | Overcome stall |
| T+7d | 7 days | WhatsApp | Final nudge: specific offer or available slot | Urgency |
| T+14d | 14 days | Email | "Closing your inquiry" + strong CTA | FOMO close |

**Drip production rules:**
1. **Stop on ANY inbound reply** from the contact on any channel → `drip_stopped_at = NOW()`, cancel all pending tasks. They're engaged — don't auto-spam.
2. **Stop on conversion** (booking confirmed, form submitted) → cancel drip immediately.
3. **Per-channel opt-out respected** (not per-contact global). WhatsApp STOP → suppresses WA only; Email unsubscribe → suppresses Email only.
4. **Channel priority override:** If contact has active Telegram thread, route T+15m and T+24h through Telegram (free, instant) instead of WA template (paid).
5. **Content escalation across steps:** T+0 = summary; T+24h = proof/brochure; T+3d = social proof; T+7d = urgency; T+14d = FOMO. Never repeat content.
6. **3-3-3 rule (Gallabox sourced):** First 3 messages build context (what we discussed), next 3 offer value (brochure, demo, case study), last 3 push action (CTA, urgency, close).

**WA 24h window management (grounded in wave-build-wa-automation.md):**
- Outbound call alone does NOT open a 24h window. The T+0 utility template send is what opens it.
- Meta charges ₹16/conversation for utility template send (this is the cost of opening the window).
- If contact replies within 24h: all subsequent messages are free-form (no template, no cost).
- T+24h message: if no reply → must use approved utility template again. Pre-register "post_call_followup_d2" template on Meta.

---

### 6. DRIP ENGINE ARCHITECTURE

**Queue-based, not cron-based. Survives restarts. Multi-tenant safe.**

```sql
-- FORCE-RLS on all hot-lead tables
CREATE TABLE communication_hot_leads (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    call_id         TEXT NOT NULL,
    lead_phone      TEXT NOT NULL,
    lead_name       TEXT,
    interest_score  INT NOT NULL,
    llm_enrichment  JSONB,              -- full LLM JSON output
    alerted_at      TIMESTAMPTZ,
    alert_status    TEXT,               -- sent | failed | not_configured
    drip_started_at TIMESTAMPTZ,
    drip_stopped_at TIMESTAMPTZ,        -- null = drip still running
    converted_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE communication_drip_tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    hot_lead_id     UUID REFERENCES communication_hot_leads(id),
    channel         TEXT NOT NULL,      -- whatsapp | email | sms | telegram
    step_index      INT NOT NULL,       -- 0=T+0, 1=T+15m, 2=T+2h, etc.
    execute_at      TIMESTAMPTZ NOT NULL,
    executed_at     TIMESTAMPTZ,
    status          TEXT DEFAULT 'pending'  -- pending | sent | failed | cancelled
);
-- FORCE-RLS on both:
ALTER TABLE communication_hot_leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE communication_hot_leads FORCE ROW LEVEL SECURITY;
ALTER TABLE communication_drip_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE communication_drip_tasks FORCE ROW LEVEL SECURITY;
```

**Worker:** Background loop in `caller.py` (or Hatchet at `10.122.0.3`) polls `communication_drip_tasks WHERE status='pending' AND execute_at <= NOW() AND tenant_id = ANY(active_tenants)`. Executes send → marks `executed_at`, `status`. One task at a time per hot_lead (serial per contact, parallel across contacts/tenants).

---

### 7. MULTI-TENANT ISOLATION

Every function receives `tenant_id` as first positional argument. All DB queries parameterized with `WHERE tenant_id=$1`. FORCE-RLS enforced at the Postgres GUC level (same pattern as `wallet_transactions`). Per-tenant config in `provider_credentials` (AES-256-GCM encrypted):
- `telegram_bot_token`
- `founder_telegram_chat_id`
- `hot_lead_threshold` (default: 75, UI-configurable per tenant)
- `drip_channels` (array: which channels are enabled per tenant)

No global mutable state. No cross-tenant data access possible at the DB layer.

---

### 8. ADVERSARIAL FACT CHECKS

**CLAIM: "Long call duration = hot lead"**
VERDICT: FALSE. Duration is a CONTRIBUTING signal, not a determinant. Long calls with persistent objections score LOW. Famit's `interest` field already accounts for this (LLM-assessed during the call, not a naive duration counter). Duration alone never triggers the hot-lead pipeline.

**CLAIM: "Telegram bot can cold-message any contact"**
VERDICT: FALSE. A bot can only message users who first sent `/start` to the bot. EXCEPTION: founder alert — the founder initiates the bot once (sends `/start`) and thereafter receives alerts freely. Contact-facing Telegram drip requires the contact to have first messaged the bot (via a deep link embedded in WA/Email onboarding messages).

**CLAIM: "WhatsApp 24h window opens on outbound call"**
VERDICT: FALSE. An outbound AI call does NOT open a Meta WhatsApp 24h conversation window. Only an INBOUND message from the contact (or sending them a Business-Initiated template that they reply to) opens the window. The T+0 utility template send IS the window-opening action.

**CLAIM: "Groq Llama-3.3-70B at $0.59/1M tokens is cost-feasible for 1,000 calls/day"**
VERDICT: CONFIRMED. 1,000 calls × ~1,000 tokens = $0.59/day. At Famit's wallet margin (30%), bill tenants at ~₹0.10/call for the scoring — profitable at any volume above ~100 calls/day.

**CLAIM: "Post-call SMS drip is viable in India without DLT registration"**
VERDICT: FALSE (HARD COMPLIANCE GATE). All commercial SMS on Indian domestic networks — including post-call service messages — requires DLT-registered templates with PE ID + template ID in every API call. Unregistered templates are blocked at the carrier level. SMS is therefore the LAST channel in the priority stack; skip it until the tenant completes DLT registration.

**CLAIM: "The `interest` field from caller.py is already an LLM quality score"**
VERDICT: CONFIRMED (grounded in wave-build-wa-automation.md). The voice agent's LLM assesses and sets `interest` during the call. The hot-lead pipeline's LLM re-score is an ENRICHMENT pass (full transcript, post-call, more tokens for analysis) — it validates and enriches, not replaces, the in-call score.

---

### 9. FOUNDER UX — FULL ALERT LIFECYCLE

**T=0s:** Call ends → `_finalize_call()` fires → `raw_interest >= 50` → spawn `_hot_lead_pipeline()` (asyncio task, non-blocking).

**T≈3s:** Groq LLM re-scores. If `hot_lead=true` + `interest_score >= 75`:

Founder receives Telegram message:
```
HOT LEAD ALERT

Name: Ravi Mehta
Phone: +91 98765 43210
Campaign: Real Estate Mumbai Q3
Duration: 4m 32s
Score: 87/100
Why hot: Budget confirmed, requesting next-week deployment
Next action: Send brochure + book demo for Monday

[Call Now]  [View Transcript]
[Mark Handled]  [Snooze 1h]
```

**Founder taps "Call Now":** `tel:+919876543210` deep link → phone dialer opens pre-filled.

**Founder taps "View Transcript":** Bot sends transcript as `sendDocument` (PDF from DO Spaces) or chunked `sendMessage` if no PDF.

**Founder taps "Mark Handled":** `answerCallbackQuery` fires immediately (≤10s) → `communication_hot_leads.converted_at = NOW()` → all pending drip tasks cancelled.

**Founder taps "Snooze 1h":** `answerCallbackQuery` → insert a new `communication_drip_tasks` row with `execute_at = NOW() + interval '1 hour'` for a re-alert.

**If Telegram not configured:** Fallback 1: WhatsApp message to founder's personal number via existing `send_whatsapp_async()`. Fallback 2: log to `communication_hot_leads` for panel review (Hot Leads page badge).

---

### 10. PANEL HOT LEADS PAGE (mandatory — founder's standing rule)

The backend pipeline ships WITH a frontend Hot Leads page. Location: `/crm/hot-leads` (under CRM section, alongside existing calls view).

**Page features:**
- Live feed table: lead name, phone, score, call duration, campaign, alert status, drip step, time elapsed, converted/open badge
- Click row → side panel: LLM enrichment JSON displayed as human-readable card + full call transcript + audio player (presigned DO Spaces URL from recording)
- Filters: Today / This Week / Score range (slider) / Channel / Status (open/converted/stopped)
- Actions per row: "Call Now" (tel: link), "Stop Drip", "Mark Converted", "Restart Drip from Step N"
- Stats banner: hot leads today / converted today / conversion rate / average score
- Alert config button: per-tenant hot_lead_threshold slider + drip channel toggles + Telegram bot setup wizard

---

### 11. COST SUMMARY

| Item | Volume | Unit Cost | Daily Cost |
|---|---|---|---|
| LLM re-scoring (Groq Llama-3.3-70B) | 500 qualifying calls/day | $0.59/1M tokens | $0.30 |
| Telegram founder alert | 50–100 hot leads/day | FREE | $0 |
| WA utility template (T+0 hot leads) | 100 sends/day | ₹16/conversation | ₹1,600 |
| Email T+0 + T+3d + T+14d | 300 emails/day (hot + warm) | Resend: $0/3K free | ~$0 at launch |
| SMS T+2h (DLT-gated) | 50 SMS/day | ₹0.19/SMS MSG91 | ₹9.50 |
| **Total hot-lead pipeline** | ~1,000 calls screened | — | **~₹1,620 + $0.30** |

All costs metered per tenant via `wallet_transactions` (channel='hot_lead_alert', channel='drip_wa', channel='drip_email', channel='drip_sms'). Tenants billed at 30% markup on channel costs.

---

**Sources:**
- [Bland AI — Conversational AI Lead Scoring](https://www.bland.ai/blogs/conversational-ai-lead-scoring)
- [Kixie — Sentiment Analysis in Sales Calls](https://www.kixie.com/sales-blog/how-to-leverage-sentiment-analysis-in-sales-calls-with-ai/)
- [AssemblyAI — Extract Call Insights with LLMs (Python)](https://www.assemblyai.com/blog/extract-call-insights-llms-python)
- [Trust Insights — AI Lead Scoring 12 Use Cases](https://www.trustinsights.ai/blog/2025/12/12-days-of-ai-use-cases-day-2-sales-lead-scoring/)
- [Retell AI — Webhook Overview](https://docs.retellai.com/features/webhook-overview)
- [Telegram Bot API Reference](https://core.telegram.org/bots/api)
- [Rollout — Telegram Bot API Essentials](https://rollout.com/integration-guides/telegram-bot-api/api-essentials)
- [Gallabox — WhatsApp Drip Marketing](https://gallabox.com/blog/whatsapp-drip-marketing)
- [TextMagic — SMS Lead Nurturing Strategies 2025](https://www.textmagic.com/blog/lead-nurturing-strategies-with-sms-marketing/)
- [chati.ai — Automated Multi-Channel Drip Campaigns](https://chati.ai/features/drip-marketing)
- [Spurnow — WhatsApp Drip Campaign Examples](https://www.spurnow.com/en/blogs/whatsapp-drip-campaign-examples)
- [TALK-Q — India SMS Messaging Regulations 2025](https://talk-q.com/sms-messaging-regulation-in-india)
- [Softcery — Voice Agent Platforms Compared 2026](https://softcery.com/lab/choosing-the-right-voice-agent-platform-in-2026)
- [Famit live codebase: caller.py:1873 (_finalize_call), caller.py:1932 (_wa_ai_followup), caller.py:1518 (_wa_reply_text)]
- [wave-build-wa-automation.md — WA post-call hook + `interest` field origin]

---

**END hot-lead-automation RESEARCH**

---

## PHASE: omnichannel-orchestration — Unified Message Bus, Channel Adapters, Fallback, Multi-Tenant Architecture
**Date:** 2026-06-15
**Sources:** Twilio Conversations API blog + docs, Chatwoot DeepWiki (architecture), mudrava.com (Telegram multi-tenant framework), redis.io (AI agent memory), dev.to (LLM memory production patterns), MailChannels (multi-tenant email), emailonacid + DMARC Report (SPF/DKIM/DMARC 2025), sakari.io + callhub.io (10DLC US), TALK-Q + buddyinfotech (India DLT 2026), autocalls.ai (post-call automation), respond.io (AI agent WhatsApp), echoleads.ai (voice+WA platforms 2026)

---

### 1. THE CANONICAL OMNICHANNEL BUS ARCHITECTURE (sourced from Twilio + Chatwoot + Bird)

The industry-standard pattern, verified across Twilio Conversations, Chatwoot, Bird, and Respond.io:

Inbound: /webhook/telegram, /webhook/email, /webhook/sms each hit a dedicated adapter that normalizes to a common internal format: {tenant_id, contact, channel, body, media[], thread_id}. The normalized message hits the Conversation Store (thread lookup/create, FORCE-RLS). The LLM Brain runs with per-tenant system prompt, Redis context, Groq. Reply goes to Outbound Router which picks the channel adapter and delivers.

**Twilio Conversations (sourced):** Treats a "Conversation" as a room connecting participants each with their own channel preference. Core design: "channel equality" — no channel is primary. The API abstracts ParticipantBinding (the channel-specific identity of a participant within a conversation). Adding a new channel = add a new binding type, NOT rewrite conversation logic. Conversation entity has states + timers for lifecycle management.

**Chatwoot (sourced — DeepWiki):** Uses polymorphic ActiveRecord associations. `Inbox belongs_to :channel, polymorphic: true`. The `channel_type_from_params` controller method maps `channel[type]` to the correct class (Channel::Email, Channel::TwilioSms, Channel::Telegram). Every message flows through identical pipeline regardless of source channel. Tenant isolation: EVERY entity (Inbox, Contact, Conversation, Message) carries `account_id` as the root isolation boundary.

**Architectural verdict for Famit:** The channel registry must follow the same polymorphic pattern — `communication_channels` table with `channel_type` polymorphic, `communication_conversations` as the threading entity, `communication_messages` for actual content. The channel_type determines which adapter class handles send/receive.

---

### 2. CHANNEL ADAPTER PATTERN (sourced — Chatwoot + Twilio + mudrava.com)

Each channel is a separate adapter class sharing a common interface (send/receive/is_configured). The EDITABLE_ATTRS pattern (Chatwoot) means each adapter defines which config params are exposed to the UI: ChannelTelegram = [bot_token, founder_chat_id, welcome_message]; ChannelEmail = [smtp_host, imap_host, sender_email, sender_domain]; ChannelSms = [provider, api_key, sender_id, dlt_pe_id].

**Multi-tenant Telegram Bot framework (sourced — mudrava.com):** The production pattern for per-tenant bot tokens uses a Dispatcher with AsyncLocalStorage (Python: contextvars.ContextVar):
1. Webhook arrives at `/webhook/telegram/{tenant_id}` (URL encodes tenant)
2. Dispatcher loads tenant config from cache/DB: bot_token, founder_chat_id, system_prompt
3. Stores in request-scoped context var — no scattered WHERE tenant_id clauses in business logic
4. Bot token never appears in business logic — only the adapter reads it from the vault

**Vertical slice per-channel module (sourced — mudrava.com):** Each channel module contains handler + service + DB schema fragment + webhook registration. Modules communicate via EventBus (Observer pattern) rather than direct imports. This is identical to the existing provider_registry + wallet.py + firewall.py separation already in Famit.

**Per-tenant bot token vault:** Store in `communication_channel_credentials` (same AES-256-GCM, FORCE-RLS, AAD bound to `tenant_id||channel_type||version` as provider_credentials). Never log bot tokens. Telegram setWebhook `secret_token` field + server-side validation as defense-in-depth (sourced: gitguardian.com, bazucompany.com).

---

### 3. UNIFIED THREADING — CROSS-CHANNEL CONVERSATION MODEL

**The problem Twilio Conversations was built to solve (sourced):** Without a thread model, a contact who messages via Telegram, then replies via SMS, then follows up via email = THREE disconnected records. The unified thread stores them all under one conversation_id keyed to (tenant_id, contact_id).

**Thread-merge identity rules:**
- Primary key: tenant_id + contact_phone (SMS/WA) OR tenant_id + telegram_chat_id (TG) OR tenant_id + contact_email (email)
- Cross-channel identity resolution: if same phone appears on SMS and WA, merge into one contact + one conversation thread
- ContactInbox pattern (Chatwoot): join table mapping contact → inbox (channel) with channel-specific identity (source_id = telegram chat_id, email address, or phone per channel)

**Schema for Famit (synthesized):**
- `communication_conversations` (id, tenant_id, contact_id, status, last_channel, call_id FK) — FORCE-RLS
- `communication_conversation_channels` (conversation_id, channel, channel_source_id, tenant_id) — UNIQUE (tenant_id, channel, channel_source_id) — FORCE-RLS
- `communication_messages` (id, tenant_id, conversation_id, direction inbound|outbound, channel, body, media JSONB, status queued|sent|delivered|failed|read, external_id, timestamps) — FORCE-RLS, append-only trigger (no UPDATE/DELETE)

---

### 4. CHANNEL FALLBACK ROUTING (Telegram -> SMS -> Email)

**Production fallback pattern (verified from Twilio + respond.io):** No vendor implements automatic cross-channel fallback as a built-in primitive. Fallback lives in the outbound router layer. The logic: iterate preferred_channels in order, call adapter.send(), on failure log and try next, raise AllChannelsFailed if all fail.

**Fallback trigger conditions:**
- Channel not configured for tenant → skip silently (not a failure)
- HTTP 4xx/5xx from adapter → log + fallback
- Telegram 403 (bot blocked by user) → escalate to SMS
- SMS DLT template not registered (dlt_template_id IS NULL) → skip to email
- Email bounce detected via async webhook → mark contact email invalid

**Escalation vs fallback distinction:**
- Fallback: delivery failure → try next channel for same message
- Escalation: hot lead score >=70 → ALWAYS send Telegram regardless of preference (override)
- Drip sequence: each step defines preferred channel; fallback applies per-step

**Per-contact channel preference table:** `communication_contact_channels` (tenant_id, contact_id, channel, is_opted_in, opted_in_at, opted_out_at, opt_out_reason, last_message_status, channel_source_id). Opt-out must be honored within 24h (10DLC US requirement; DLT India: STOP command).

---

### 5. LLM CONVERSATION BRAIN — STATEFUL CROSS-CHANNEL MEMORY

**The problem (sourced — dev.to):** LLMs have no persistent memory. Every inbound message — Telegram, SMS, or email — must carry context: who are they, what was discussed in the call, what have they asked the AI previously.

**Production three-tier memory architecture (sourced — redis.io):**
- Tier 1 Working memory (Redis Hash, TTL 1h): Key comm:session:{tenant}:{conversation_id}. Last 10 messages + current intent. Injected verbatim into prompt.
- Tier 2 Short-term (Redis Hash, TTL 72h): Key comm:contact:{tenant}:{contact_id}. Call summary, lead score, products discussed, objections, name. Injected as structured context block.
- Tier 3 Long-term (PostgreSQL JSONB, no TTL): Table communication_contact_memory. fact_type, fact_value, confidence, captured_at. Semantic search on new turns.

**Key production insights (sourced — dev.to, redis.io):**
- "Context windows are not memory" — session restart loses everything without external storage
- Sliding window (last N messages) beats full-history injection for latency + cost
- Hierarchical summarization: at 20+ turns, summarize oldest 10 → store Tier 2; keep recent 10 verbatim in Tier 1
- Implement forgetting: decay stale facts (interest expressed 90 days ago is not current signal)
- Retrieval quality > retrieval volume: gate between storage and prompt injection (relevance + freshness + authority)

**Per-channel brain routing:** One ConversationBrain class serves all channels. Channel-specific instructions are injected into the system prompt: Telegram = "use bold, inline buttons, keep <500 chars unless detailed"; SMS = "CRITICAL: max 160 chars GSM7, no emojis, no URLs unless pre-whitelisted"; Email = "professional tone, HTML allowed."

**Groq reuse:** The existing caller.py Groq client + `_wa_reply_text()` (line 1518) is 80% of the implementation. The comm LLM brain is a simplified version: no LiveKit, no audio, just text completion with Redis-backed three-tier memory using the existing ratelimit.py Redis connection (:6380 on box).

---

### 6. MULTI-TENANT RLS ISOLATION

**Pattern (sourced — Chatwoot + existing Famit):** Every entity carries tenant_id. FORCE-RLS on ALL communication tables. Same FORCE-RLS + GUC (SET app.tenant_id) pattern as wallet.py, provider_registry, audit.py already on the live box.

Tables requiring FORCE-RLS: communication_conversations, communication_conversation_channels, communication_messages, communication_channel_credentials (bot tokens/API keys), communication_contact_channels (opt-in state), communication_contact_memory (LLM fact store), communication_templates, communication_template_content, communication_send_log, communication_consents.

**Cross-tenant blast prevention:** Outbound router sets `SET app.tenant_id = $tenant_id` before every DB query. Never allow `WHERE tenant_id IN (...)` patterns — always single-tenant per request.

---

### 7. POST-CALL AUTO-MESSAGE HOOK (sourced — autocalls.ai + caller.py analysis)

**Existing hook (caller.py:1873):** `_finalize_call()` fires on every call completion. Currently calls `_wa_ai_followup()` (line 1932) gated behind `wa_followup` campaign flag. The new omnichannel hook (`_comm_post_call()`) runs from the SAME trigger point, gated behind COMM_ENABLED=1. The WA followup stays untouched (earner safety). Both run in parallel (asyncio.gather).

**Post-call message per channel:**
- Telegram: full summary (4096 chars) + inline "Book a Call" / "View Brochure" buttons (MarkdownV2)
- Email: HTML with call summary + banner (hosted CDN URL) + PDF attached if <5MB (Resend)
- SMS: 160-char GSM7 teaser + branded short link to full summary page (MSG91)
- WhatsApp: existing post_call_followup approved template (already wired, unchanged)

**Sourced proof (autocalls.ai):** 60% faster follow-up, 40% higher reply rates, 70% faster customer updates reported for post-call auto-message pattern.

---

### 8. HOT-LEAD ALERT — TELEGRAM FOUNDER NOTIFICATION

**Why Telegram (sourced — all platforms reviewed):** No Meta business verification, no DLT, no approval process. BotFather bot token + founder's personal chat_id = instant delivery in seconds. This is the confirmed pattern across respond.io, autocalls.ai, echoleads.ai.

**Founder setup flow:** Panel generates a deep link `https://t.me/{bot_username}?start=connect_{tenant_id}_{one_time_token}`. Founder clicks → Telegram opens → starts bot. Bot receives /start payload → validates token → stores chat_id to tenant.founder_telegram_chat_id. This is the OAuth-equivalent for Telegram (one-time token + deep link, no OAuth needed).

**Alert content:** MarkdownV2 message with lead name + phone + campaign + call summary (truncated to 800 chars) + "View Full Transcript" link + inline "Call Now" (tel: URL) + "View CRM" button.

**SEPARATE code path from contact flow:** Founder alert NEVER goes through the channel fallback chain. If Telegram not configured → log warning → do nothing (founders don't want hot-lead SMS at 2am).

---

### 9. EMAIL DELIVERABILITY MULTI-TENANT (sourced — MailChannels 2026)

- Per-tenant DKIM keys: each tenant must have a unique DKIM selector. Resend Scale (1,000 domains) handles this automatically.
- BYOD (Bring Your Own Domain): each tenant sends from their own domain (mail.acmecorp.com). Prevents reputation cross-contamination. Fallback: noreply@mail.famit.in while verifying.
- Shared IP pool gating: Google Postmaster Tools monitoring, spam rate target <0.1%. Freeze promotional sends for any tenant crossing threshold.
- DMARC enforcement (mandatory since May 2025 — Microsoft): SPF + DKIM + DMARC p=quarantine minimum. Gmail + Yahoo enforce since early 2024 for >5K/day senders.

---

### 10. SMS COMPLIANCE GATES

**India DLT (sourced — TALK-Q, buddyinfotech 2026):**
- Famit category: Service (Implicit) — post-call follow-up. Inferred consent. DND does NOT block. No time window restriction.
- Multi-tenant: each tenant registers independently on DLT with their own GSTIN/PAN.
- Timeline: 5–10 business days (clean); 2–4 weeks first-time.
- Hard UI gate: block SMS send if dlt_pe_id OR dlt_template_id is NULL. Same gate in backend API (not just UI).

**US 10DLC (sourced — sakari.io, callhub.io):**
- As of Feb 2025: all major US carriers block unregistered A2P SMS.
- Reseller arrangement (Famit sending on behalf of tenant) requires reseller_id in campaign registration.
- Hard UI gate: block if campaign_registration_id is NULL.

---

### 11. ARCHITECTURAL VERDICTS FOR FAMIT BUILD

**A. Channel Registry = direct clone of Provider Registry.** Same FORCE-RLS tables, same AES-256-GCM AAD vault, same capability-based resolution (registry.get_channel(tenant_id, capability='telegram'|'email'|'sms')), same COMM_ENABLED=0 flag dormancy (404, resting byte-identical). This is PROVIDER-FRAMEWORK-PLAN.md → communication_channel_registry.py clone.

**B. Unified Conversation Thread over Per-Channel Silos.** ONE communication_conversations + communication_messages with a channel column. This is what Twilio, Chatwoot, Bird, and Respond.io all converged on after building the silo approach first.

**C. Telegram First, Everything Else Additive.** Telegram = zero approvals, zero DLT, zero compliance gatekeeping. Ship Telegram (bot token + sendMessage + founder hot-lead alert) in Wave 1. Add Email in Wave 2 (Resend + SPF/DKIM setup guide in panel). Add SMS in Wave 3 (MSG91 + DLT registration wizard). Each wave is additive — COMM_ENABLED flag, no caller.py or agent.py mutation, no voice earner risk.

**D. LLM Brain = Groq (already deployed) + Redis context (already on box).** Existing `_wa_reply_text()` (caller.py:1518) is 80% of the implementation. Use existing ratelimit.py Redis (:6380) for Tier 1 + Tier 2 memory keys. pgvector for long-term semantic memory: defer to Phase 2.

**E. Post-Call Hook = extend _finalize_call(), NOT replace.** Add `_comm_post_call()` as a parallel coroutine alongside `_wa_ai_followup()`, gated behind COMM_ENABLED=1. WA followup stays untouched.

**F. Founder Alert = separate code path from Contact flow.** If Telegram not configured → log warning → stop. Never route to SMS/email fallback for founder alerts.

**G. Cost model:**
- Telegram: $0/message at Famit's volume (below 30 msg/s threshold)
- Email (Resend): $0 free tier (3K/mo) → $20/mo at 50K. Bill tenants at $0.001/email (10x markup)
- SMS India (MSG91): ₹0.18/SMS. Bill at ₹0.25/SMS (39% margin). Metered via wallet_transactions
- Redis memory: existing box Redis (:6380), zero incremental cost
- No new infra needed for Wave 1 (Telegram + post-call hook)

---

### SOURCES (this phase)

- [Twilio Conversations Architecture Blog](https://www.twilio.com/en-us/blog/products/next-generation-conversations-api-for-chat-and-whatever-comes-next)
- [Twilio Flex Conversations Unified API](https://www.twilio.com/en-us/blog/flex-conversations-first-unified-api-digital-channels)
- [Chatwoot Channel Architecture — DeepWiki](https://deepwiki.com/chatwoot/chatwoot/7.1-email-configuration)
- [Chatwoot Multi-Tenant Architecture — DeepWiki](https://deepwiki.com/chatwoot/chatwoot)
- [Telegram Multi-Tenant Bot Framework — mudrava.com](https://mudrava.com/en/now-every-new-bot-takes-three-minutes-instead-of-a-week/)
- [GitGuardian — Telegram Bot Token Vault](https://www.gitguardian.com/remediation/telegram-bot-token)
- [Redis AI Agent Memory Architecture](https://redis.io/blog/ai-agent-memory-stateful-systems/)
- [LLM Memory Production Patterns — dev.to](https://dev.to/pockit_tools/how-to-build-ai-agents-that-actually-remember-memory-architecture-for-production-llm-apps-11fk)
- [MailChannels Multi-Tenant Email Deliverability 2026](https://www.mailchannels.com/multi-tenant-email-deliverability/)
- [Email Authentication 2025 — emailonacid](https://www.emailonacid.com/blog/article/email-deliverability/email-authentication-protocols/)
- [10DLC Compliance 2025 — sakari.io](https://sakari.io/blog/meeting-10dlc-compliance-with-opt-ins)
- [10DLC Registration 2025 — callhub.io](https://callhub.io/blog/compliance/10dlc-2025-registration-callhub/)
- [India DLT SMS Guide 2026 — TALK-Q](https://talk-q.com/sms-messaging-regulation-in-india)
- [India DLT Bulk SMS 2026 — buddyinfotech](https://buddyinfotech.in/blog/dlt-compliance-bulk-sms-regulations-in-india-2026-guide/)
- [Autocalls.ai Post-Call WhatsApp Automation](https://autocalls.ai/integration/whatsapp-business)
- [Autocalls.ai Telegram Bot Integration](https://autocalls.ai/integration/telegram-bot)
- [Respond.io AI Agent WhatsApp](https://respond.io/blog/whatsapp-ai-agent)
- [EchoLeads Voice + WA Platforms 2026](https://echoleads.ai/blog/ai-solutions-for-calling-and-whatsapp-lead-generation-platform-comparison-2026)
- [Event-Driven Architecture Production — Medium](https://medium.com/@himansusaha/the-complete-guide-to-event-driven-architecture-from-pub-sub-to-event-sourcing-in-production-f9dd468ed9e8)
- [CDP for Omnichannel — valantic.com](https://www.valantic.com/en/blog/omnichannel-marketing-automation-customer-data-platform/)

---

**END omnichannel-orchestration RESEARCH**

## PHASE: llm-conversation-brain — Multi-Step LLM Conversation Brain for Messaging
**Date:** 2026-06-15
**Scope:** Context + memory per contact, agentic replies with tool-use (book/qualify/send-brochure), handoff to human, multilingual, cross-channel shared brain. Sourced + adversarially verified.

---

### 1. THE CORE ARCHITECTURE — Brain, Memory, Tool Loop

A production conversation brain for messaging is NOT a stateless chatbot. It is an agentic loop with four layers:

Layer 1 — IDENTITY RESOLUTION: phone/email/TG chat_id maps to lead_id in CRM. If unknown: create provisional lead.

Layer 2 — CONTEXT ASSEMBLY: (a) Short-term: last N turns (JSONB history, current session). (b) Long-term: extracted facts (name, budget, product interest, objections, call summary). (c) Channel context: which channel, prior channels, opt-in status. (d) Campaign context: which campaign the lead entered, last call outcome.

Layer 3 — LLM INFERENCE (Groq, tool use enabled): System prompt = tenant persona + campaign brief + tools available. User message injected with assembled context. Model outputs: reply text OR a tool_call JSON. If tool_call: execute synchronously, inject result, loop (up to 2 steps).

Layer 4 — ACTION DISPATCH: send reply via channel adapter, update session history, update long-term memory (extract facts via asyncio.create_task), log to communication_send_log + audit, check handoff triggers. Next inbound message restarts the loop.

Key insight from Respond.io production architecture (2026): They use micro-agents for task precision + an orchestrator for coordination. Each micro-agent has a narrow tool set — narrower context = fewer hallucinated tool calls. Famit implementation decision: ONE shared orchestrator LLM call selecting from a maximum of 8 tools. "Two-shot agentic" pattern: if tool selected, execute synchronously (<200ms), inject result, re-call LLM once. Proven reliable in production.

---

### 2. MEMORY ARCHITECTURE — Per-Contact, Per-Tenant

State of the art (2026 production, Mem0 arxiv 2504.19413): Hybrid memory = in-session rolling window (fast, cheap) + extracted long-term facts (persistent, semantic). Swapping long-term memory for context-window-only baseline dropped task completion from more than 80% to approximately 45% on multi-session tasks. Long-term memory is not optional for a product that wants to feel like it remembers the lead from their first call.

Two-layer design for Famit:

Layer 1 — Short-term (in-session rolling window): Keep last 20 turns in JSONB history in communication_sessions. No embedding, no vector DB, pure PG. Fits Groq context window (20 turns x 80 tokens avg = 1,600 tokens). Older turns summarized and moved to Layer 2.

Layer 2 — Long-term (extracted facts per contact): communication_contact_memory table with facts JSONB shape covering name, budget, product_interest array, objections array, preferred_call_time, language, stage, last_summary, opt_out_channels array. Optional embedding vector(1536) for pgvector semantic retrieval. Updated asynchronously after each reply via asyncio.create_task — NOT on critical path. Graceful degradation if extraction fails.

Memory extraction pattern: lightweight LLM call (Haiku/Flash for cost, NOT Groq) with prompt "Extract key facts. Return JSON: name, budget, interest, objections, stage". Merge with existing facts — upsert, never overwrite, only ADD new info.

Context injection into system prompt includes: Contact profile (name, interest, budget, objections, language, stage), last call summary, prior channel activity summary. Language rule baked in: "Detect user's language from first message. Reply in that SAME language. Hinglish is acceptable — match their register. Never ask what language they prefer — detect silently."

Source: State of AI Agent Memory 2026 (mem0.ai/blog/state-of-ai-agent-memory-2026), Mem0 Production arxiv 2504.19413, Atlan Memory Architectures (atlan.com/know/agent-memory-architectures/)

---

### 3. TOOL SET — Agentic Actions Available to the Brain

Production principle (Composio + LangGraph 2026): Tool schemas are JSON descriptions. When LLM decides a tool is needed, it outputs structured JSON. System executes, injects result, re-calls LLM for final reply. Total round-trip on Groq: approximately 400ms at 460 tok/s LPU throughput.

Famit tool set (8 tools, intentionally minimal):

check_slot_availability: Query available appointment slots next 7 days. PG query on bookings table. Under 10ms.

book_slot: Book appointment for contact. INSERT bookings, send confirmation via active channel. Under 20ms plus channel send.

send_brochure: Send product PDF or image via active channel. Look up template, dispatch channel adapter. Under 50ms.

qualify_lead: Update lead score + stage in CRM. UPDATE leads.score, append lead_events. Auto-calls trigger_founder_alert if score >= 70. Under 15ms.

escalate_to_human: Hand off to founder or team. INSERT handoff_queue, notify via Telegram, pause AI auto-reply 4h. Under 30ms.

opt_out: Record contact opt-out from channel. UPDATE communication_consents.opted_in = false. Under 10ms.

update_contact_language: Set preferred language for future messages. UPDATE communication_contact_memory.facts.language. Under 10ms.

trigger_founder_alert: Instant hot-lead Telegram to founder. Calls send_founder_hot_lead_alert(). Approximately 100ms.

Total agentic loop latency (two-shot): Groq call 1 approximately 200ms + tool execute 15-50ms + Groq call 2 approximately 150ms + channel send approximately 80ms = p50 approximately 450ms end-to-end. Within the 800ms natural conversation industry threshold (Confident AI 2026).

Source: Groq Agentic Tooling (console.groq.com/docs/agentic-tooling), Composio Tool Calling Guide 2026 (composio.dev/content/ai-agent-tool-calling-guide), Confident AI LLM Evals 2026 (confident-ai.com/blog/llm-agent-evaluation-complete-guide), BuildMVPFast Agent Handoff Patterns 2026.

---

### 4. HUMAN HANDOFF — Design Pattern

Industry state (BlueTweak/BuiltABot 2026): 85% of chatbot handoffs lose context. The ones that do not share one pattern: full conversation history + machine-generated summary travels WITH the handoff notification.

Handoff triggers:
1. Lead explicitly requests human ("talk to someone", "speak to sales") — IMMEDIATE
2. Lead score >= 80 AND no slot booking in last 3 turns — escalate reason: high_value
3. Negative sentiment 3 or more consecutive turns — escalate reason: complaint
4. LLM uncertainty 2 consecutive turns — LLM itself calls escalate_to_human with reason: complex_query
5. Pricing negotiation keywords (discount, negotiate, match price, competitor) — escalate reason: pricing_negotiation
6. Budget above threshold OR product = enterprise — escalate reason: high_value

Handoff execution: (1) Set session.state = human_pending, expires_at = now() + 4h. (2) Notify founder via Telegram with context_summary + last 3 turns + inline Take Over / Let AI Continue buttons. (3) Acknowledge lead on same channel: Connecting you with our team. (4) INSERT into communication_handoff_queue for CRM panel.

When founder taps Take Over: session.state = human_active. Founder types replies in CRM panel chat view; AI brain silenced. 4h of inactivity triggers AI to resume automatically.

Context briefing for founder on take-over: lead profile card + call history + last 5 message turns + AI context_summary. Founder enters informed, not cold.

Source: BlueTweak AI-to-Human Handoff 2026 (bluetweak.com/blog/ai-to-human-handoff/), BuiltABot Hybrid Support 2026 (builtabot.com/blog/ai-chatbot-human-handoff-hybrid-support-guide-2026), BuildMVPFast Agent Handoff Patterns (buildmvpfast.com/blog/agent-handoff-patterns-ai-human-escalation-confidence-threshold-2026), Alhena AI 7-Step Handoff (alhena.ai/blog/ai-human-escalation-chatbot-handoff-best-practices/)

---

### 5. MULTILINGUAL — Hindi / Hinglish / Regional Languages

The India problem: Leads are 60-80% Hindi/Hinglish in north India; south India leads reply in Tamil, Telugu, Kannada, or Malayalam. English-only bots lose engagement fast.

Sarvam AI (already in Famit stack for voice, confirmed 2026): Samvaad supports 11 Indian languages across text + voice in a single thread. Sub-500ms latency for text replies. Cross-channel context (WhatsApp + phone + web) in one memory. SquadStack production pattern: auto-detect language on first message, switch if user switches mid-conversation, context preserved across language switches.

Path A — Groq-native multilingual (Primary, zero additional cost): Llama 4 Scout and Llama 3.3 70B natively understand and respond in Hindi, Hinglish, Tamil, Telugu, Bengali, Kannada, Marathi. No translation layer needed. Pass messages as-is; model replies in user language.

Path B — Sarvam translate/normalize (Fallback for low-resource languages): If Groq output is incoherent for Tamil/Kannada/Malayalam scripts, route through sarvam.translate(text, source_lang, en) then LLM in English then sarvam.translate(reply, en, target_lang). Adds approximately 200ms but guarantees correctness.

Language detection: langdetect (pip install langdetect) or fasttext lid.176 — local, under 5ms, no API cost, returns BCP-47 code (hi, ta, te, en). Store in communication_contact_memory.facts.language.

DLT language note (SMS): Famit must register both English AND Hindi variants of each SMS template separately on the DLT portal — two DLT template IDs per SMS template.

Source: Sarvam AI Samvaad WhatsApp Voice+Chat (x.com/SarvamAI/status/1963548479500030279), Sarvam Conversational Agents (sarvam.ai/products/conversational-agents), SquadStack multilingual (squadstack.ai/voicebot/top-ai-agent-companies-in-india), Robylon Multilingual AI 2026 (robylon.ai/blog/7-best-multilingual-ai-voice-agents-2026)

---

### 6. CROSS-CHANNEL SHARED BRAIN — One Memory, All Channels

The core test (AWS DEV Community multichannel 2026): Does the agent read chat and email history as one timeline? Some platforms keep separate memory per channel — context does NOT actually transfer. The ones that pass this test use a unified actor_id (identity anchor) mapped to all channel IDs.

Famit architecture — unified contact identity model:

communication_contact_identity is the anchor. One row per unique contact, cross-channel. Fields: tenant_id, lead_id foreign key to existing CRM leads table, phone in E.164 format which links SMS + WA + call history, email which links Email channel, telegram_chat_id which links Telegram, whatsapp_contact_id which links WhatsApp.

All communication_sessions reference contact_identity_id (NOT a channel-specific ID). communication_contact_memory is per identity (NOT per channel). This means: lead messages on Telegram and brain pulls their WhatsApp history summary + last 3 call summaries. Brain can say: I remember you asked about pricing on WhatsApp 3 days ago — have you had a chance to review the brochure?

Identity resolution order on inbound: (1) Telegram: chat_id matches identity.telegram_chat_id. (2) SMS/WA: phone matches identity.phone. (3) Email: from-address matches identity.email. (4) No match: create provisional identity row + provisional lead in CRM. (5) Merge: if phone + email match different rows, merge with audit log entry.

Cross-channel timeline (lightweight): communication_contact_memory.cross_channel_timeline JSONB stores array of {channel, ts, summary} objects — compact log of significant cross-channel interactions. This is what gets injected as Prior activity into the system prompt. Summaries only, not full history — keeps context window small.

Source: AWS Multichannel AI Shared Memory DEV Community (dev.to/aws/multichannel-ai-agent-shared-memory-across-messaging-platforms-56j4), Respond.io Cross-Channel AI Agents (respond.io/ai-agents), TringTring Multi-Channel AI Architecture (tringtring.ai/blog/whatsapp-ai/multi-channel-ai-integrating-whatsapp-voice-and-web-chat/)

---

### 7. LEAD SCORING + QUALIFICATION IN CONVERSATION

Production pattern (Jeeva AI / Monday.com 2026): Conversational AI qualification detects 2-5x more qualified buyers than form-fill because it reads actual intent from conversation context, not just counts actions.

BANT framework implemented as qualify_lead tool call: Budget (confirmed amount vs tenant threshold), Authority (decision-maker vs influencer vs unknown), Need (pain points extracted from conversation), Timeline (immediate / this_week / this_month / within_quarter / unknown), plus Engagement depth (call duration above 3 minutes, replied to 3 or more messages). Score 0-100.

Hot-lead threshold: 70/100 — matches existing caller.py logic. When qualify_lead tool returns score >= 70, trigger_founder_alert is called automatically in the same tool execution. Founder gets instant Telegram alert with full lead context.

Source: Jeeva AI Agentic Qualification 2026 (jeeva.ai/blog/agentic-ai-lead-qualification), Monday.com AI Lead Qualification (monday.com/blog/crm-and-sales/ai-driven-lead-qualification/), DigitalApplied Conversational AI Lead Qualification Guide (digitalapplied.com/blog/conversational-ai-lead-qualification-guide), Relevance AI Lead Scoring Agents 2026 (marketplace.relevanceai.com/use-cases/lead-scoring-agents)

---

### 8. THE 99% — FEATURES THE FOUNDER DID NOT NAME

Conversation intelligence (the moat): Sentiment tracking per turn — negative sentiment for 2 or more consecutive turns flags early warning, stored in session.history alongside each turn, visualized in CRM. Topic extraction per session (pricing, demo, objection, competitor, urgency) feeds analytics dashboard. Conversation health score — percentage of turns where lead engaged vs went silent; below 40% = pause campaign for this lead, log as disengaged. Smart silence detection — if lead has not replied in configurable X hours (1h/6h/24h/3d), AI sends gentle re-engagement message; stops after 2 unanswered attempts.

Campaign-context awareness: Brain knows which campaign the lead came from (injected into system prompt). Uses campaign approved talking points + objection-handling scripts + pricing. Does NOT cross-sell other campaigns (per-campaign scoping). Campaign end date: brain auto-closes conversations gracefully when campaign expires.

Appointment confirmation + reminder flow (via Hatchet orchestrator): T+0 immediate booking confirmation via active channel. T-24h reminder with calendar link. T-1h reminder with reply C to confirm or R to reschedule. T+1h after no-show: re-engagement message + rebook offer. All scheduled via existing famit-hatchet box — no new infrastructure.

Brochure analytics: Every brochure send logged with contact_id, brochure_type, channel, sent_at, spaces_key. Email: Resend webhook tracks open + click events, logged to send_log. Telegram: editMessageReplyMarkup removes View Brochure button after 3 days. SMS: branded short link click tracked in short_link_clicks table. Panel shows per-contact brochure engagement feeding the qualify_lead score.

Flow layer before LLM layer (saves approximately 70% of LLM calls): FSM for structured paths. Flow 1: Post-call Telegram opt-in (Yes/No buttons). Flow 2: Demo scheduling (Tomorrow / This Friday / Next Monday quick-reply buttons leading to check_slot_availability then confirm). Flow 3: Brochure request (Product overview / Pricing / Case studies leading to send_brochure). Button taps resolve WITHOUT an LLM call. LLM only fires for free-form text.

Founder control surface (Panel UI): Live conversation view showing all active conversations across all channels in real-time. Manual take-over via one click to human_active mode to type replies directly. Bulk pause to disable AI replies for a specific campaign. System prompt editor per-tenant and per-campaign in panel — no code deploy needed. Conversation replay with tool call annotations showing what AI decided and why. Handoff queue sorted by urgency (immediate, within_1h, within_24h) as founder action list.

Streaming replies on Telegram (June 2026 Desktop 6.9 feature): Send initial thinking... message then stream tokens via periodic editMessageText calls then replace with final reply. Reduces perceived latency from approximately 450ms to near-instant first character. Implementation: Groq streaming + editMessageText loop at 100ms intervals.

Privacy + compliance layer (DPDP 2023 built-in from day 1, not retrofitted): Consent gate on every send. Opt-out honored within one session turn. Data retention: conversation history pruned at 90 days by Hatchet cron, configurable per tenant. Right to be forgotten: DELETE cascade on communication_contact_identity removes all sessions, memory, send_log — audit tombstone record created with no content. FORCE-RLS on all communication_* tables ensures no cross-tenant data bleed.

---

### 9. MODEL SELECTION — Which LLM for the Brain

Primary — Groq LPU (existing Famit stack, zero new cost): Llama 4 Scout (17B active, 109B total MoE) is the recommended default — best quality-to-speed balance, 460+ tok/s, native Hindi/Hinglish, tool use supported, already in GroqCloud allocation. Llama 3 Groq Tool Use 70B is the fallback for complex tool-call sequences — fine-tuned specifically for function calling reliability, approximately 91% tool-call accuracy per BenchLM 2026 versus approximately 82% for generic Llama 3.3 70B.

Memory extraction — cheap model: claude-haiku-3-5 (Anthropic) OR gemini-2-flash (free 500/day). Approximately 200 tokens per call. At 100 conversations/day: 20K tokens = approximately $0.003/day. Route to free tier.

Regional language fallback — Sarvam Saaras-v1: Already integrated in Famit for voice. POST /v1/chat/completions with model sarvam-saaras-v1. Only triggered for Path B (Tamil/Kannada/Malayalam where Groq quality degrades).

Tool call reliability ranking (BenchLM 2026): GPT-4o-mini approximately 94% (highest accuracy, moderate cost). Llama 3 Groq Tool Use 70B approximately 91% (lowest latency). Llama 4 Scout approximately 88% (broader model, not fine-tuned specifically for tool use). Llama 3.3 70B generic approximately 82%.

Decision: Llama 4 Scout as default (quality + speed). Llama 3 Groq Tool Use 70B as fallback for tool-heavy sessions. Sarvam for regional language text. Haiku/Flash for background memory extraction.

Source: Groq Tool Use Docs (console.groq.com/docs/tool-use/overview), Groq Agentic Tooling (console.groq.com/docs/agentic-tooling), BenchLM Tool Calling Rankings 2026 (benchlm.ai/llm-agent-benchmarks), Groq in Production (markaicode.com/usecases/groq-use-cases-low-latency-api-production/)

---

### 10. DATABASE SCHEMA — ADDITIVE (FORCE-RLS on all tables)

communication_contact_identity: id UUID PK, tenant_id UUID, lead_id UUID NULL (FK leads), phone TEXT NULL E.164, email TEXT NULL, telegram_chat_id BIGINT NULL, whatsapp_contact_id TEXT NULL, created_at TIMESTAMPTZ. Index on (tenant_id, phone) and (tenant_id, telegram_chat_id).

communication_sessions: id UUID PK, tenant_id UUID, contact_identity_id UUID FK, channel TEXT (telegram or whatsapp or email or sms), external_chat_id TEXT, state TEXT default active (active or human_pending or human_active or paused or opted_out), state_expires_at TIMESTAMPTZ NULL, history JSONB default empty array, campaign_id UUID NULL, current_flow TEXT NULL, current_step TEXT NULL, created_at TIMESTAMPTZ, last_message_at TIMESTAMPTZ.

communication_contact_memory: id UUID PK, tenant_id UUID, contact_identity_id UUID FK, facts JSONB default empty object, last_call_summary TEXT NULL, cross_channel_timeline JSONB default empty array, embedding vector(1536) NULL for pgvector, updated_at TIMESTAMPTZ.

communication_handoff_queue: id UUID PK, tenant_id UUID, contact_identity_id UUID, channel TEXT, reason TEXT, urgency TEXT (immediate or within_1h or within_24h), context_summary TEXT, status TEXT default pending (pending or accepted or rejected or expired), assigned_to UUID NULL, accepted_at TIMESTAMPTZ NULL, created_at TIMESTAMPTZ.

communication_asset_cache: id UUID PK, tenant_id UUID, spaces_key TEXT, channel TEXT, channel_file_id TEXT (Telegram file_id), cached_at TIMESTAMPTZ. UNIQUE constraint on (tenant_id, spaces_key, channel).

All tables: ALTER TABLE x ENABLE ROW LEVEL SECURITY + appropriate RLS policies tying to tenant_id.

---

### 11. ADVERSARIAL FACT CHECKS

CLAIM: Groq Llama 4 Scout runs at 460+ tok/s
SOURCE: Voiceflow Groq blog 2026 + NeuraPulse Groq developer guide 2026.
VERDICT: CONFIRMED. 460 tok/s on Groq LPU means a 200-token reply finishes in approximately 430ms.

CLAIM: Mem0 task completion drops from more than 80% to approximately 45% without long-term memory
SOURCE: Mem0 State of AI Agent Memory 2026 (their own benchmark, arxiv 2504.19413).
CAVEAT: Self-reported on their own benchmark; third-party reproduction not peer-reviewed.
VERDICT: DIRECTIONALLY ACCURATE. Long-term memory clearly improves multi-session task completion. Treat the direction not the exact numbers as the lesson.

CLAIM: 85% of chatbot handoffs lose context
SOURCE: Cited in BlueTweak + BuiltABot guides; original source not traceable.
VERDICT: WIDELY CITED industry estimate. Directional, not precisely 85%. Design lesson — send full context WITH the handoff — is correct regardless.

CLAIM: Sarvam Samvaad sub-500ms latency for text replies
SOURCE: Sarvam.ai product page + X.com launch announcement June 2026.
VERDICT: CLAIMED by Sarvam; independently unverified. Existing Famit voice integration with Sarvam produces 300-600ms for TTS — consistent with the claim.

CLAIM: Llama 3 Groq Tool Use 70B has approximately 91% tool-call accuracy
SOURCE: BenchLM 2026 tool-calling benchmarks.
VERDICT: PLAUSIBLE. The Groq fine-tuned tool-use model is confirmed in GroqDocs. Accuracy varies by benchmark dataset. Use with temperature=0 and tool_choice=auto for best production reliability.

CLAIM: Lead scoring 2-5x improvement with conversational AI versus form-fill
SOURCE: Jeeva AI blog + DigitalApplied guide — both vendor marketing.
VERDICT: DIRECTIONALLY CORRECT from first principles (conversation extracts richer intent signals than form checkboxes). Specific multiplier is marketing copy. Qualify as industry estimate if citing to founder.

CLAIM: Telegram bots cannot cold-message users who never initiated contact
SOURCE: core.telegram.org/bots/faq — confirmed in prior Telegram phase.
VERDICT: CONFIRMED for private 1:1 chats. EXCEPTION: groups and channels where bot is admin can post freely. Famit uses group/channel for the founder alert stream; deep link for contact opt-in.

---

### 12. KEY ARCHITECTURAL DECISIONS (LLM BRAIN)

1. Two-shot agentic loop, max 2 tool calls. Prevents runaway chains. All tools sync under 200ms. Total latency approximately 450ms p50 — within 800ms natural conversation threshold.

2. JSONB history in PG, no vector DB for MVP. pgvector is an optional upgrade for semantic retrieval. No additional infrastructure required to launch.

3. Groq Llama 4 Scout as primary model. Already in Famit stack. Tool use native. 460 tok/s. Zero new cost.

4. Sarvam Saaras-v1 as language fallback only. Groq handles Hindi/Hinglish natively. Sarvam only for Tamil, Telugu, Kannada, Malayalam where Groq quality degrades.

5. Brain is a new comm_router FastAPI router, mounted additively. ONE additive include_router line in caller.py. Zero risk to voice earner. Lives in droplet_work/communication/ directory.

6. Phone number is the universal identity key for India. It links SMS + WhatsApp + call history. Telegram chat_id linked to phone via deep-link opt-in. Start with phone as the anchor.

7. Human handoff via Telegram is the HIGHEST-VALUE feature for the founder. Takes him from zero visibility into live conversations to instant in-context alerts with one-tap take-over. Zero additional cost because Telegram is already being built.

8. Memory extraction is background via asyncio.create_task. Not on critical path. If extraction fails, session history is still intact (graceful degradation).

9. Flow layer before LLM layer. Button taps resolve without LLM call. LLM only fires for free-form text. Saves approximately 70% of LLM calls on structured interaction flows.

10. DPDP 2023 compliance built-in from day 1. Consent gate on every send. Opt-out in one turn. Data retention enforced by daily Hatchet cron. Nothing to retrofit later.

---

**Sources:**
- State of AI Agent Memory 2026 — Mem0: mem0.ai/blog/state-of-ai-agent-memory-2026
- Mem0 Production Paper — arxiv 2504.19413: arxiv.org/pdf/2504.19413
- Best AI Agent Memory Frameworks 2026 — MachineLearningMastery: machinelearningmastery.com/the-6-best-ai-agent-memory-frameworks-you-should-try-in-2026/
- Agent Memory Architectures — Atlan: atlan.com/know/agent-memory-architectures/
- Groq Tool Use Docs: console.groq.com/docs/tool-use/overview
- Groq Agentic Tooling: console.groq.com/docs/agentic-tooling
- Tool Calling Guide — Composio 2026: composio.dev/content/ai-agent-tool-calling-guide
- LLM Agent Evals 2026 — Confident AI: confident-ai.com/blog/llm-agent-evaluation-complete-guide
- LLM Agent and Tool-Use Benchmarks 2026 — BenchLM: benchlm.ai/llm-agent-benchmarks
- Agent Handoff Patterns — BuildMVPFast 2026: buildmvpfast.com/blog/agent-handoff-patterns-ai-human-escalation-confidence-threshold-2026
- AI-to-Human Handoff Best Practices — BlueTweak: bluetweak.com/blog/ai-to-human-handoff/
- Hybrid Support Guide — BuiltABot 2026: builtabot.com/blog/ai-chatbot-human-handoff-hybrid-support-guide-2026
- AI Handoff 7-Step Context Transfer — Alhena: alhena.ai/blog/ai-human-escalation-chatbot-handoff-best-practices/
- Escalation Best Practices — Cobbai: cobbai.com/blog/chatbot-escalation-best-practices
- Sarvam AI Samvaad WhatsApp Voice and Chat: x.com/SarvamAI/status/1963548479500030279
- Sarvam Conversational Agents: sarvam.ai/products/conversational-agents
- SquadStack India Multilingual AI 2026: squadstack.ai/voicebot/top-ai-agent-companies-in-india
- Robylon Multilingual AI Agents 2026: robylon.ai/blog/7-best-multilingual-ai-voice-agents-2026
- AWS Multichannel AI Shared Memory DEV Community: dev.to/aws/multichannel-ai-agent-shared-memory-across-messaging-platforms-56j4
- Respond.io Cross-Channel AI Agents: respond.io/ai-agents
- TringTring Multi-Channel AI Architecture: tringtring.ai/blog/whatsapp-ai/multi-channel-ai-integrating-whatsapp-voice-and-web-chat/
- Groq in Production — Markaicode: markaicode.com/usecases/groq-use-cases-low-latency-api-production/
- Agentic AI Lead Qualification 2026 — Jeeva AI: jeeva.ai/blog/agentic-ai-lead-qualification
- AI-Driven Lead Qualification — Monday.com: monday.com/blog/crm-and-sales/ai-driven-lead-qualification/
- Conversational AI Lead Qualification Guide — DigitalApplied: digitalapplied.com/blog/conversational-ai-lead-qualification-guide
- AI Lead Scoring Agents 2026 — Relevance AI: marketplace.relevanceai.com/use-cases/lead-scoring-agents
- How Respond.io AI Agents Work at Scale: respond.io/blog/how-respondio-ai-agents-work

---

**END llm-conversation-brain RESEARCH**

---

## PHASE: monetization-sellable — How the Omnichannel Comms Tab MAKES MONEY (pricing / value-metric / wedge / moat)
**Date:** 2026-06-15
**Scope:** The SELLABLE/monetizable brainstorm — pricing model, value metric, the wedge, the moat, and bold out-of-the-box revenue ideas for the Telegram + Email + SMS Communication tab. Founder ask treated as 1%; the 99% below. Grounded in real channel COGS (this log's cost-routing phase) + the existing paise wallet + the 3-tier anchors (Starter Rs 9,999 / Growth Rs 24,999 / Enterprise Rs 75k+, MASTER_DNA_PLAN paragraph 388). READ-ONLY brainstorm — no code.

### THE COST FLOOR (what every price anchors against — from the verified cost table above)
Telegram **Rs 0** · WhatsApp 24h-window **Rs 0** · Email **~Rs 0.03** · SMS **~Rs 0.16-0.25** · WA utility **~Rs 0.12** · WA marketing **~Rs 0.86**. The omnichannel tab's headline COGS is **near-zero** (Telegram + in-window WhatsApp + free-tier email). This is the whole monetization unlock: **we charge for OUTCOMES on a near-zero-cost rail.**

### 0. THE ONE-LINE PITCH (the wedge)
"Your AI calls the lead, then keeps selling them on **Telegram, Email AND SMS** — picking the cheapest channel that reaches them — until they book. One AI brain, every channel, you pay per booked outcome." The wedge is **Telegram = zero Meta gatekeeper**: a tenant is live in 5 minutes with a BotFather token (no business verification, no template approval, no Rs 0.86/msg) — the exact friction that makes WhatsApp a multi-week onboarding. **Land on Telegram (free + instant), expand to Email/SMS/WhatsApp (metered).**

### THE BEST BOLD IDEAS (tight, ranked)

**1. VALUE METRIC = "Conversations that convert", not messages sent.** Do not meter per-message (a race to the bottom that rewards spam). Meter the **AI-handled conversation that produces a tracked outcome** (booking, callback, hot-lead, qualified reply). Messages/min are COGS we absorb; the invoice line is "47 AI conversations -> 12 bookings this month." This is the only metric that (a) aligns our incentive with the buyer's revenue, (b) is defensible vs the Rs 0.10/msg point-tools, and (c) survives channel cost-shifts (Telegram free today, SMS metered) because the customer pays for the result, not the rail.

**2. CHANNEL-AGNOSTIC OUTCOME WALLET (the pricing moat).** Buyer pre-loads ONE paise wallet (already built). The AI's **cost-router** (this log's cost-routing phase) silently picks the cheapest channel that will land — Telegram first (Rs 0), WhatsApp-in-window (Rs 0), email (Rs 0.03), SMS (Rs 0.17), WA-template (Rs 0.86) last. The customer never thinks about channels or per-channel pricing — they just see "Rs X spent -> Y bookings." **We keep the arbitrage spread** between the channel COGS we optimize down and the outcome price we charge. No competitor prices the *loop*; they price a *slice* (Wati = WhatsApp seat, MSG91 = SMS unit). Owning the router IS the margin.

**3. TIER THE TAB AS AN ADD-ON LADDER ON THE EXISTING 3 PLANS — do not reprice the base.**
- **Starter (Rs 9,999):** Telegram channel only (zero COGS) + post-call auto-summary + hot-lead founder alert. The free-to-serve hook that makes the whole plan feel generous.
- **Growth (Rs 24,999 star):** + Email + SMS + the multi-step LLM conversation brain across all channels + cost-router + omnichannel CRM timeline. This is where comms becomes a "team replacement," justifying the jump.
- **Enterprise (Rs 75k+):** + white-label bots (tenant's own brand Telegram/sender domain), bring-your-own SMS DLT + sending domain, dedicated number pool, API + webhooks, conversation-intelligence analytics. **Comms is the feature that pulls Growth->Enterprise** because branding + compliance ownership only matters at scale.

**4. THE HOT-LEAD ALERT IS A PAID TRIGGER, NOT A FREEBIE — "Revenue Radar."** Instant founder Telegram ping (phone + AI summary + one-tap call-back / one-tap "AI, keep nurturing") the moment a lead goes hot. Frame + sell it as a standalone **Rs/mo Revenue Radar add-on** even on Starter: it is the single feature a non-technical owner *feels* ("I caught a Rs 2L lead at 11pm from my phone"). Near-zero COGS (Telegram), high perceived value, demo-able in 30 seconds. **This is the upsell that closes the demo.**

**5. OVERAGE > SEATS. Sell capacity, not logins.** Each plan includes N "outcome conversations"/mo; overage auto-debits the wallet at a published paise rate (transparent, like Twilio). No per-seat tax (the whole point is *replacing* seats). Auto-recharge wallet (Stripe/Razorpay top-up) = recurring revenue with zero churn friction. Low-balance Telegram alert to the founder = self-serve refill, no sales touch.

**6. "BRING YOUR OWN BOT/DOMAIN" = the Enterprise margin printer + a compliance moat.** Tenant pastes their own BotFather token, their own SMS DLT sender ID, their own SPF/DKIM domain -> **their** branding, **their** deliverability reputation, and crucially **their** compliance liability. We charge a premium for white-label yet our COGS DROPS (their rails, their DLT cost). The encrypted per-tenant bot-token vault (AES-256-GCM, already specced) is the technical enabler AND the lock-in: once 3 channels + history + automations live behind our brain, ripping it out means rebuilding the whole loop.

**7. CONVERSATION INTELLIGENCE = the analytics upsell (pure margin, zero marginal COGS).** Sentiment-per-turn, objection/topic extraction, conversation-health score, channel-reach heatmap ("your leads answer Telegram 3x more than SMS — shift budget"), best-time-to-message, drop-off funnel. This is a **dashboard we already have the data for** (the brain logs every turn). Sell it as the Enterprise "Comms Intelligence" tier — buyers pay for insight, and it deepens lock-in because the longer they run, the more their proprietary conversion data lives in our schema.

**8. THE CLOSED-LOOP MOAT (why this is not just "another inbox").** Famit already owns Ad->Call->WhatsApp->Book->CAPI-signal. Adding Telegram/Email/SMS means **every channel's reply feeds the SAME revenue-truth signal back to Meta/Google** (booked-from-Telegram is a conversion event). No omnichannel tool (Wati/Interakt/AiSensy) closes the ads loop; no ads tool owns the conversation. **The unified contact identity across call+WA+TG+email+SMS** (one memory, this log's omnichannel-orchestration phase) is the moat: the AI says "I remember you asked about pricing on WhatsApp 3 days ago" *across channels* — a single point-tool structurally cannot.

**9. METER HONESTLY, MARK UP THE BRAIN — not the bytes.** SMS/WA-marketing pass-through at transparent cost + a small platform fee (buyers tolerate transparent unit pricing; they resent hidden markup). The MARGIN lives in (a) the LLM conversation brain (a "telecaller-replacement" they would pay a human Rs 17-39k/mo for), (b) the cost-router arbitrage, (c) the analytics tier, (d) white-label. **Never get into a per-SMS price war** — that is MSG91's game and it is a 10% margin; ours is the 80%-margin brain on top.

**10. COMPLIANCE-AS-A-FEATURE (turn the boring stuff into a sellable promise).** DLT-template management, opt-in/consent ledger, DND scrubbing, SPF/DKIM setup wizard, one-click unsubscribe, audit trail. For an Indian SMB owner, "we keep you legal on TRAI/DLT and Meta automatically" is a *fear-reversal* selling point (penalties are real, scary, and they do not understand them). Bundle it; charge for it; it is near-zero COGS and it kills the #1 "is this safe?" objection.

### MONETIZATION ONE-LINER FOR THE SALES DECK
"You do not pay for messages — you pay for a robot teammate that reaches every lead on whatever app they actually answer, remembers every past conversation, and only counts when it books you business. Starts free on Telegram. Scales to a full omnichannel revenue desk."

### WHAT TO BUILD FIRST TO UNLOCK REVENUE (sequencing the wedge)
1. **Telegram channel + bot-token vault + hot-lead Revenue Radar alert** — zero COGS, instant onboarding, demo-closes. The land.
2. **Post-call auto-summary (Telegram->Email fallback)** — the "it just works after a call" wow.
3. **Outcome wallet metering + cost-router** — turn it from feature to revenue.
4. **Multi-step LLM brain across channels + unified contact memory** — the Growth-tier "team replacement."
5. **White-label + DLT/SPF compliance + conversation intelligence** — the Enterprise margin/lock-in.

### CROSS-LINKS
Cost floor -> this log's `cost-routing` phase. Unified identity/memory -> `omnichannel-orchestration` + `llm-conversation-brain` phases. Hot-lead trigger -> `hot-lead-automation` phase. Vault/encryption -> `telegram-bot-api` phase (per-tenant AES-256-GCM token). Pricing anchors -> MASTER_DNA_PLAN paragraph 388 (3-tier) + sales research (positioning/pricing/ROI). Channel registry pattern to reuse -> design/PROVIDER-FRAMEWORK-PLAN.md (capability-keyed registry -> a CHANNEL registry).

---

## PHASE - BRAINSTORM: bold positioning + out-of-box product ideas (the 99%)

> READ-ONLY brainstorm. Grounds: MASTER_DNA_PLAN, wa-automation-state, wa-llm-conversation,
> wa-out-of-box, PROVIDER-FRAMEWORK-PLAN (channel-registry pattern), PLAYBOOK. Mirrors+exceeds the
> WhatsApp system; Telegram = unblocked path (BotFather token, no Meta verification). Additive,
> flag-gated, FORCE-RLS, earner-safe (NEVER agent.py). All ideas snap onto EXISTING seams.

### THE POSITIONING (one line)
"One inbox, every channel, owned end-to-end." AiSensy/Wati sell ONE channel (WhatsApp) as a blaster.
Famit owns the WHOLE revenue loop - Ad -> AI Call -> omni-message (Telegram/Email/SMS/WA) -> Book ->
Meta/Google revenue-signal - as ONE autonomous brain with shared memory across every channel. Category
= Revenue Comms OS, not a "messaging tool". The contact is the same person on every channel; the AI
remembers the call on Telegram, the Telegram chat on email, the email on SMS.

### THE 10 BOLD MOATS (ranked - each maps to a real seam; effort S/M/L)

1. CHANNEL REGISTRY (mirror the Provider Registry) - the architectural keystone. [L, do first]
Don't hardcode Telegram/Email/SMS. Build a capability-keyed channel.* registry exactly like
PROVIDER-FRAMEWORK-PLAN: channel.send(tenant, contact, kind, payload) resolves the enabled provider per
tenant+capability (telegram_bot | email_smtp/ses | sms_dlt), applies a request/response field-map,
meters the same wallet, audits the same channel, FORCE-RLS. Adding a 5th channel later (RCS, Slack,
iMessage, Instagram DM) = a DB row + adapter, ZERO new engine. Competitors rebuild per channel; Famit
adds a row. Bot-token/SMTP-creds live in the Vault get_secret() seam, AAD-bound AES-256-GCM, PIN-reveal,
SSRF-guarded for self-hosted SMTP/webhook URLs.

2. ONE UNIFIED CONTACT TIMELINE + cross-channel memory brain. [M]
The WA brain is per-phone flat JSON, thin context (wa-llm-conversation gap). EXCEED it: a single
FORCE-RLS comm_thread table keyed by CONTACT (not channel) fusing call summary + voice memory.py recap +
CRM/booking state + every channel's turns. The Telegram/Email/SMS reply brain loads the SAME enriched
context the WA gap doc asks for - so the AI on Telegram already knows what was said on the call and on
WhatsApp. AiSensy structurally cannot build this (no call plane, no shared memory). "Omnichannel"
elsewhere = same blast to 3 channels; here = ONE continuous conversation that hops channels and never
forgets.

3. SMART CHANNEL ROUTER / WATERFALL - "reach them however works". [M]
Per-contact channel preference + a fallback cascade: try Telegram (free, instant, rich) -> if no
bot-link/undelivered in N min -> Email (free-ish) -> if unopened -> SMS (metered, last resort). The
router learns per-contact which channel gets a reply and prefers it next. Telegram is FREE and un-gated
so it is the DEFAULT cheap path; SMS (DLT-metered, costly) is the deliberate last touch. Direct COST
moat: every message that goes Telegram instead of SMS saves real paise, optimized automatically.
Banner+video+PDF ride free on Telegram (no Meta template approval, no 24h window) - WhatsApp cannot
match this for cold sends.

4. TELEGRAM = the un-gated rich-media superpower (lead with this). [M, ship first channel]
WA cold sends need an APPROVED template + are text-until-window. Telegram via BotFather: send banner,
MP4 video brochure, PDF, inline keyboards (Yes/Book/Talk-to-human), polls, and FREE-FORM AI chat COLD,
instantly, no approval, no 24h window, ZERO per-message cost. Post-call auto-message + hot-lead founder
alert + full LLM conversation all work on Telegram day one with none of WhatsApp's Meta friction.
Positioning: "While your competitor waits weeks for Meta template approval, Famit is already chatting
your leads on Telegram with video brochures - free." Deep-link t.me/<bot>?start=<lead_token> from the
call/SMS/email binds an anonymous contact to their lead row (the contact-linking the WA path hacks via
phone-scan - Telegram gives a clean signed token instead).

5. HOT-LEAD FOUNDER WAR-ROOM (Telegram control channel, two-way). [S-M]
Founder ask = "hot-lead alert to founder Telegram". EXCEED it: a private owner Telegram channel that is
a live REVENUE FEED + remote control. Each hot lead -> rich card (name, phone, score, call summary, "why
hot", one-tap [Call now][Send offer][Assign][Snooze][Take over chat]). Tapping a button fires the
firewall-gated action (PIN step-up for spend/destructive - reuse firewall.py F3 exactly). The founder
runs the business from Telegram. Also the AI Manager's natural mobile surface - "book X for tomorrow
4pm" typed in Telegram routes to the existing ai_manager state machine. No app to build; Telegram IS the
mobile app.

6. POST-CALL AUTO-SUMMARY to the CONTACT, omnichannel + branded. [S-M]
Founder ask = "after a call auto-message the contact their summary". EXCEED it: on _finalize_call (the
existing hook that already fires _wa_ai_followup), the router sends a branded recap card on the contact's
best channel - "Here's what we discussed: ... Your quote: ... [Book a slot][Get brochure PDF][Ask a
question]". Telegram/Email get rich formatting + the PDF + inline CTAs WhatsApp can't do cold. Reuses the
EXISTING _wa_draft_followup_text (already loads tr.summary/next_action/outcome) - just swap the send seam
from wa-only to channel.send. Drives the recap into a booking, not a dead-end.

7. UNIFIED OMNI-INBOX + AI-with-human-handoff (the agent console). [M-L]
A single panel inbox showing every channel's live threads in one list, AI handling them, with seamless
human takeover (the WA handoff words already flag needs_human - generalize it). Founder/agent sees the AI
conversation, jumps in, AI hands back. SLA timers, assignment, canned replies, "AI confidence" badges.
The Intercom/Front surface no India-SMB messaging tool has for AI+voice. Sellable as a standalone "team
inbox" tier.

8. CONSENT / COMPLIANCE / DELIVERABILITY ENGINE (the boring moat that prevents bans). [M, non-negotiable]
Per-channel opt-in ledger + global suppression (reuse WA STOP/opt-out, generalize): SMS = DLT
template-id + sender-id + consent proof (India mandatory, ban-on-violation); Email = SPF/DKIM/DMARC
domain auth, one-click List-Unsubscribe header, bounce/complaint handling, warm-up, per-domain rate caps;
Telegram = bot ToS + per-user block handling. ONE consent table, ONE quiet-hours/frequency-cap engine
across channels (never 2 channels in 5 min, respect 9pm-9am). This lets a tenant scale without getting
their number/domain/bot killed - a hard differentiator vs DIY blasters that get banned. Sell it as
"deliverability insurance".

9. CROSS-CHANNEL TEMPLATE STUDIO + AI multi-step builder (mirror+exceed WA builder). [M]
ONE template authored once -> auto-rendered per channel (Telegram MarkdownV2 + inline keyboard, Email
MJML responsive HTML, SMS 160-char DLT-compliant variant, WA template). AI writes all variants from a
single brief, with channel-native previews side-by-side. Banner/video/PDF attach per channel where
supported, graceful-degrade where not (SMS -> short link to a hosted card). Personalization tokens are
SAFE-fields-only (reuse the WA no-invent text-accuracy firewall). One-click "test send to me" per channel
before going live.

10. REVENUE-SIGNAL LOOP CLOSURE + omni attribution leaderboard. [M]
Every channel touch is variant_id/campaign tagged (reuse the Testing Lab scoreboard seam) so the
cross-channel leaderboard ranks Telegram vs Email vs SMS by reply -> book -> sale - and feeds the WINNING
conversions back to Meta/Google CAPI as the revenue signal. The omni loop becomes a learning machine:
"Telegram-video-brochure converts hot leads 3x cheaper than SMS" -> auto-shift budget. No competitor
closes ad-spend <- omni-conversation -> ad-signal; the Revenue-Truth moat extended to comms. Per-channel
cost/conversion economics shown live (Telegram ~0, SMS ~paise/seg).

### 6 SHARP "OUT-OF-BOX" EXTRAS (smaller, high-delight)
- Telegram inline-keyboard BOOKING - lead taps [Book Tue 4pm] in-chat -> writes the booking via the
  existing booking seam. No form, no link, in-thread. (Telegram-only superpower; WA can't.)
- Voice-note replies - Telegram/WA voice notes in -> STT (reuse the voice STT) -> AI -> reply (or TTS
  voice-note back). Conversational, matches how India SMB leads actually message.
- Drip / nurture sequences as Workflow templates (reuse F1 WA auto-follow-up) generalized to any channel
  + cross-channel ("Telegram day0 -> email day2 -> SMS day5 if silent").
- Scheduled / quiet-hours / timezone-aware send - never message at 2am; batch to the contact's local
  morning. (Deliverability + UX.)
- Founder "broadcast from Telegram" - owner forwards a message/voice-note to the bot -> AI turns it into
  an on-brand omni-campaign to a segment. Run marketing from your phone.
- Per-tenant white-label bot + branded sender - each tenant's own @brand_bot, own email domain, own SMS
  sender-id = it's THEIR product, agency-resellable (the Enterprise/white-label tier).

### THE FILTER (PLAYBOOK discipline applied)
Every idea = a composition of existing seams (channel.send registry over wallet/audit/RLS/firewall +
Workflow Studio nodes + Testing Lab scoreboard + the WA reply-brain pattern + the contact timeline). NONE
invents a new engine/money-door/store. Earner-safe: rides caller.py, NEVER imports agent.py, all
fire-and-forget. Flag-gated (COMM_<CHANNEL>_ENABLED default OFF -> resting byte-identical). Telegram
first (free, un-gated, proves the registry), then Email (SPF/DKIM), then SMS (DLT-metered, last).

### BUILD-ORDER RECOMMENDATION (de-risked)
1) Channel Registry + Vault-seam creds (keystone) ->
2) Telegram channel adapter (send banner/video/PDF/keyboard, cold + free) ->
3) Unified contact timeline + enriched cross-channel reply brain ->
4) Post-call auto-summary via router + Hot-lead founder war-room ->
5) Smart channel router/waterfall + consent/compliance engine ->
6) Email then SMS adapters ->
7) Cross-channel template studio + omni-inbox + revenue-signal leaderboard.

---

## PHASE: BRAINSTORM — Out-of-the-Box Omnichannel Revenue-Comms Ideas (2026-06-15)

> Divergent, founder-mindset ideation. The founder's literal ask (post-call auto-message + hot-lead Telegram alert + LLM chat brain across TG/Email/SMS) is ~1%. Below is the other 99%: bold, sellable, differentiated capabilities a billion-dollar omnichannel revenue-comms product needs — grounded in the VERIFIED channel capabilities logged in prior phases (Telegram free + Mini-Apps + Stars/payments + inline keyboards; Email sequences + open/click webhooks; SMS branded short-links + DLT). Each idea notes the channel(s), the revenue/moat angle. All are additive, flag-gated, never touch the voice earner (agent.py). TIER markers: [S]=ship-early/cheap-fast-high-ROI, [M]=mid, [X]=moonshot/differentiator. This is a brainstorm — the roadmap phase gates/sequences.

### A. TELEGRAM AS A REVENUE SURFACE (the unblocked moat — go far beyond "send a text")

1. **[X] Telegram Mini-App "Deal Room" per hot lead.** After a call, the bot deep-links the contact into a branded Mini-App (TWA): a single-lead micro-site with the call summary, personalized quote, brochure PDF inline, a booking calendar, and a Pay-Now button (Telegram Stars / UPI invoice). The lead goes call -> review -> book -> PAY without leaving Telegram. "Close the loop inside the chat" — no point-tool has this. Per-tenant white-labeled.
2. **[X] In-chat payment collection (Telegram Payments 2.0 / UPI provider token + Stars).** The brain can sendInvoice for a deposit/booking fee mid-conversation. "Pay 500 to lock your slot" -> tap -> paid -> CRM updated -> CAPI "Purchase" fired to Meta. The comms channel becomes a revenue channel; the Revenue-Truth Signal Loop now has a real-money terminal event, not just "booked."
3. **[M] Telegram Channel as a tenant broadcast list.** Each tenant gets an auto-managed Channel; opted-in leads join via the bot. Drip offers, inventory drops, price-cuts, festival blasts at ZERO cost (free <30 msg/s). A free marketing channel vs WhatsApp's ~0.86/marketing-template — a huge cost-story for the sales deck.
4. **[M] Voice-note replies in Telegram (sendVoice + STT).** Indian users love voice notes. Brain accepts an inbound voice note (Sarvam/Groq STT -> text -> LLM) and replies with a sendVoice TTS clip in the lead's language — bridging the voice-agent persona INTO chat ("the same Riya who called me"). Memorable, human, differentiated continuity across voice and chat.
5. **[S] Inline-button "instant qualify" micro-forms.** No LLM call: post-call quick-reply chips (Budget? <5L / 5-10L / 10L+; When? this week / this month / just looking). Each tap updates lead score and routes hot ones to the founder instantly. FSM, ~0 cost, sub-second — qualifies while warm without burning tokens.
6. **[M] Telegram Business Account connect.** Tenant connects their own Telegram Business account so replies appear from THEIR brand handle (greeting/away messages, AI as connected bot) — white-label without them running infra.
7. **[X] Live "war-room" group per hot lead.** When a lead goes hot, auto-spin a Telegram group with the founder + AI bot + optional human closer; AI posts full context/transcript + a recommended pitch and stays to fetch info on demand ("@bot what did they object to?"). Founder closes high-ticket deals with the AI as in-chat co-pilot.
8. **[S] One-tap "Call me now" / "WhatsApp me" deep-link buttons** in every Telegram message — bridges back to the voice earner / WhatsApp on the lead's terms (lead-initiated = compliant, no cold-call risk).

### B. THE "AFTER-A-CALL" MOMENT — make the summary a conversion weapon, not a receipt

9. **[S] Personalized recap CARD, not a text blob.** Auto-render the call summary as a branded image card (reuse the AI Asset Service banner pipeline): lead name, agreed next step, quote, a QR to book. Sent as TG photo / email inline / MMS. A beautiful artifact the lead screenshots and forwards = organic reach.
10. **[X] "Resume where we left off" continuity.** The post-call message is a live continuation of the SAME conversation — the chat brain already holds the full call transcript, so "actually what about EMI?" gets answered in context as if the call never ended. No other tool carries voice-call context into chat. The cross-channel shared-brain payoff, made tangible.
11. **[M] Objection-aware follow-up.** If the transcript shows a stall on price/trust/timing, the follow-up is auto-tailored: price -> financing + ROI card; trust -> testimonials/proof; timing -> limited-time nudge. Pulls from the campaign's approved objection scripts.
12. **[M] Multi-touch "ghost" recovery sequence.** No reply -> cost-aware drip: TG nudge (0) at +6h -> email value-card (0) at +1d -> SMS branded-link (metered) at +3d -> graceful close at +7d. Stops instantly on any reply. The full revenue-recovery cadence around the founder's single "auto-message."
13. **[X] AI send-time optimization.** Learn per-contact engagement windows (open/reply timestamps) and schedule the follow-up for their personal peak via Hatchet. Open rates jump; zero extra cost.

### C. THE HOT-LEAD UPSTREAM — turn the founder's phone into a revenue cockpit

14. **[S] Actionable alert, not just a notification.** The hot-lead Telegram alert carries inline buttons: Call Now (dialer deep-link / trigger outbound), Send Quote, Assign to closer, Snooze 1h, Mark won/lost. The founder runs the next action from the notification — no app-switch. Tiny build, huge value.
15. **[X] "Hot lead is LIVE on the line" interrupt.** During a call trending hot in real time (sentiment + buying-signal on the live transcript), ping the founder mid-call — "Lead on the phone now, very interested, jump in?" -> one tap to barge/whisper or a warm transfer. Catch the deal at peak intent.
16. **[M] Daily/weekly "Revenue Standup" digest** to the founder's Telegram: hottest leads, deals at risk (gone cold), revenue booked, CAPI signals fired, channel spend. The product reports its own ROI — kills churn.
17. **[M] Voice summary to the founder.** The alert can be a 15-sec AI voice note (TTS) to listen to while driving: "Rajesh, 8L budget, ready to buy a 3BHK this month, only blocker is loan approval." Faster than reading.
18. **[X] Team round-robin + SLA escalation.** Multiple closers per tenant; hot leads auto-assigned round-robin / by skill / territory; if the assignee doesn't act within the SLA (e.g. 10 min), auto-escalate to the next person / founder. A solo alert becomes a sales-team operating system.

### D. THE LLM CONVERSATION BRAIN — beyond chat: an agent that DOES things

19. **[X] Agentic actions in-chat (the brain has hands).** Book a slot, send a brochure, generate + send a quote PDF, raise an invoice, apply a discount code, update the CRM, fire a CAPI event — all as tools the brain calls during the conversation. The lead books and pays inside the thread; the founder wakes up to closed deals.
20. **[M] Dynamic quote-builder tool.** Lead describes needs -> brain assembles a line-item quote from the tenant catalog/price rules -> renders a branded quote card/PDF -> sends -> tracks open. Replaces the "let me get back to you on pricing" gap that kills deals.
21. **[X] Cross-channel single brain, single thread.** One contact identity across TG + Email + SMS + WhatsApp + voice; the lead starts on SMS, continues on Telegram, and the AI never loses the thread or repeats itself. Unified inbox in the panel. The omnichannel promise most "omnichannel" tools fake.
22. **[M] Proactive re-engagement brain.** Not just reactive — watches triggers (brochure viewed not bought, quote sent not signed, demo no-show, price drop on a watched item) and reaches out first, on the cheapest channel, with the right message.
23. **[M] Negotiation guardrails + auto-discount ladder.** Tenant sets a discount ceiling + approval threshold; brain offers tier-1 discounts autonomously and escalates past the ceiling to the founder for one-tap approve/deny. Closes price-sensitive leads without giving away margin.
24. **[X] RAG over the tenant's own knowledge.** Brochures, price lists, FAQs, policies, winning transcripts -> the brain answers product questions accurately in the tenant's voice (reuses the built-but-empty RAG). No hallucinated promises.
25. **[S] Multilingual auto-detect (Hindi/Hinglish/regional).** Detect language from the first message and converse natively (Groq Llama-4 for Hindi/Hinglish, Sarvam for Tamil/Kannada/Malayalam). The "talks to every lead in their language" pitch, now in chat.
26. **[M] Sentiment-gated human handoff with a warm baton.** On frustration / high-ticket / explicit "talk to a human," hand off with a one-paragraph context brief + suggested reply; on resolution, hand back. The honest human-handoff named in sales research, productized.

### E. TEMPLATE / CAMPAIGN BUILDER — exceed the WhatsApp builder, not mirror it

27. **[S] ONE message, ALL channels (write-once template).** Author content once; the system auto-adapts per channel (TG rich + buttons, email HTML, SMS 160-char + short-link, WA template) with side-by-side channel-aware preview. The WA builder does one channel; this does all from one authoring surface.
28. **[M] AI copywriter + per-channel variant generation.** "Re-engage cold real-estate leads, festival offer" -> AI drafts TG/email/SMS variants, subject lines, CTAs in the tenant's brand voice. Reuse the existing AI-template backend.
29. **[X] Built-in A/B/n testing + auto-winner.** Send variants to a holdout split, measure open/click/reply/book, auto-promote the winner. The comms product optimizes itself.
30. **[M] Journey/sequence builder (React-Flow), not just single sends.** Visual drag-drop multi-step, multi-channel, branch-on-behavior journeys ("opened email -> wait 1d -> TG nudge; clicked -> notify founder"). Reuse the planned React-Flow workflow builder. The difference between a "message sender" and a "growth automation platform."
31. **[S] Snippet/variable library + dynamic personalization tokens** ({first_name}, {agreed_next_step}, {quote_amount}, {campaign}) with safe fallbacks, validated at author-time.

### F. INTELLIGENCE / ANALYTICS / THE MOAT LAYER

32. **[X] Closed-loop CAPI from EVERY channel event.** Brochure-opened, quote-clicked, slot-booked, invoice-paid — each fires the right Meta/Google conversion signal with quality value. The comms layer becomes the richest fuel for the Revenue-Truth Signal Loop; ad algos learn from real post-click behavior across channels. The billion-dollar differentiator.
33. **[M] Channel attribution + per-channel ROI dashboard.** Which channel/sequence/message drove bookings and revenue; cost per booked appointment per channel. Lets the cost-router optimize on outcomes, not just send-price.
34. **[S] Engagement scoring feeding the lead score.** Opens, clicks, reply latency, sentiment, button taps roll into a live lead-temperature that re-triggers hot-lead alerts and re-prioritizes the founder's queue.
35. **[S] Deliverability/health monitor.** Per-tenant SPF/DKIM/DMARC status, bounce/complaint rates, SMS DLT-template health, Telegram bot-blocked count — surfaced before a tenant's sender reputation tanks.
36. **[X] "Best channel for THIS person" predictor.** Learn each contact's preferred/most-responsive channel and route there first (cheapest that converts). Personal-channel-routing beats global cost-routing.

### G. COMPLIANCE / TRUST / SECURITY (sellable as a feature, not a chore)

37. **[S] Consent + opt-in vault with double opt-in + per-channel consent ledger.** Immutable record of who consented to what channel when (DPDP/DLT/CAN-SPAM proof). One-tap STOP honored within a turn across all channels. Sell "compliant by design."
38. **[M] Per-tenant bot-token / API-key vault** (encrypted at rest, never logged) + a guided self-serve connect wizard (BotFather walk-through, SES/Resend domain-verify, DLT template registration helper). Onboarding that doesn't need an engineer.
39. **[S] Quiet hours + frequency caps + global suppression list** per tenant — never message at 2am or 5x a day; respect DND. Protects sender reputation and the brand.
40. **[S] PII-redaction + audit trail on every send** (reuse the immutable audit leg): who/what/when/cost, replayable.

### H. CROSS-CHANNEL ORCHESTRATION + RELIABILITY

41. **[S] Smart fallback chain.** Telegram (free) -> WhatsApp -> SMS (metered) -> Email; stop on first delivery+read; never double-charge (idempotency key per call_id+channel). Guaranteed reach at lowest cost — part of the cost-router, surfaced as a tenant toggle.
42. **[M] Unified omnichannel inbox in the panel.** One thread per contact across all channels, human take-over in one click, AI/human mode toggle, internal notes. The founder's command surface (his standing rule: every backend gets a UI).
43. **[M] Scheduled / timezone-aware / campaign-window sends** via Hatchet — drip, reminders, festival blasts, follow-ups; durable and reboot-safe on the existing box.

### I. THREE MOONSHOTS (the "wow" for the sales demo)

44. **[X] "From ad click to paid, all inside the chat."** Meta lead-form / click -> instant AI voice call -> if missed, Telegram Mini-App deal-room -> AI chat closes -> in-chat Stars/UPI payment -> CAPI "Purchase" back to Meta. A fully autonomous ad-to-revenue loop with NO human and NO website. Nobody owns this end to end.
45. **[X] Self-improving comms.** Every won/lost outcome feeds back: winning variants, best send-times, best channels per segment are learned and auto-applied. The system gets better at selling the tenant's product the longer it runs — a compounding moat.
46. **[X] "Clone my best telecaller into chat."** Mine the tenant's best human-rep transcripts (voice + chat) to tune the brain's persona/objection-handling per tenant — the chat AI sounds like THEIR star closer, not a generic bot.

### TOP 12 (founder-grade shortlist — highest revenue x differentiation, earner-safe)
1. [X] Cross-channel single brain / single thread (#21) — the omnichannel core.
2. [X] In-chat payment via Telegram Stars/UPI + CAPI "Purchase" (#2, #32) — money terminal + the moat.
3. [X] Telegram Mini-App deal-room per hot lead (#1) — the "wow," white-label, close-in-chat.
4. [S] Actionable hot-lead alert with inline action buttons (#14) — tiny build, huge founder value.
5. [X] Agentic brain with hands — book/quote/invoice/CAPI as tools (#19) — deals close while he sleeps.
6. [S] "Resume where we left off" voice->chat continuity (#10) — the cross-channel payoff made real.
7. [S] Write-once, all-channels unified template builder (#27) — exceeds the WA builder immediately.
8. [M] React-Flow multi-channel journey/sequence builder (#30) — "platform," not "sender."
9. [M] AI send-time + best-channel-per-person routing (#13, #36) — free lift on every send.
10. [S] Personalized recap card (image) post-call (#9) — reuses Asset Service, screenshot-worthy.
11. [X] Built-in A/B/n auto-winner (#29) — self-optimizing comms.
12. [S] Consent vault + compliant-by-design (#37) — sellable trust, unblocks scale.

**ONE-LINE NORTH STAR:** Not a "message sender" — an omnichannel AI revenue closer that carries one brain across Telegram/Email/SMS/WhatsApp/voice, picks up exactly where the call ended, closes and collects payment inside the chat, alerts the founder the instant a lead goes hot, and feeds every real outcome back to the ads — all on the free/cheap channel first, multi-tenant and compliant by design.

---

## PHASE: BOLD-IDEAS — Founder + Product-Visionary Brainstorm (the 99% out-of-the-box)
**Date:** 2026-06-15
**Lens:** Treat the founder's ask (unified Comms tab; Telegram+Email+SMS; mirror+exceed WhatsApp; post-call auto-message; hot-lead founder alert; LLM conversation brain; per-tenant) as the **1%**. Prior phases designed a *competent* omnichannel chatbot (memory, tools, handoff, scoring, cross-channel) + a monetization wedge. This phase asks the harder question: **what makes this a billion-dollar, sellable, MOATED revenue-comms product no competitor (AiSensy/Wati/Interakt/Respond.io/Twilio/Kylas) can copy?** Bold first, feasibility tagged; earner-safe (rides caller.py / the new comm_router, NEVER agent.py), additive, multi-tenant FORCE-RLS, cost-aware. Complements the monetization phase above (this = the PRODUCT/AI bold ideas; that = the business model). No fluff.

> Discipline (PLAYBOOK + the WhatsApp anti-bloat doc design/wa-out-of-box.md): a bold idea ships only if it rides EXISTING seams — the channel registry (clone of provider_registry), the LLM brain tool loop, the wallet/audit/RLS gates, Hatchet, DO Spaces presign, the cross-channel identity anchor, the Creative Studio + Testing Lab + CAPI seams. Anything needing a net-new engine/money-path is sequenced behind, not rejected (a moat idea is worth a new table, never a new payment door).

### TIER 1 — THE MOAT (differentiated, defensible, sellable headline features)

**B1. Revenue-Truth Signal Loop extended to EVERY channel (the #1 moat).** Famit already closes Ad->Call->WhatsApp->Book->Meta-CAPI. The leap: **every Telegram/Email/SMS conversation that converts feeds a quality-weighted conversion signal back to Meta/Google CAPI** — not just calls. A lead who booked via a Telegram brochure click becomes a high-value offline-conversion event teaching the ad algorithm to hunt for answerers who pay across any channel. No point-tool owns the post-click conversation AND the ad-feedback loop. The sales-deck line competitors structurally cannot write. Rides the CAPI seam + the new send_log (channel-tagged conversion events). Feasibility: HIGH.

**B2. One Brain, One Memory, Every Channel — "it remembers you across phone, WhatsApp, Telegram, email, SMS."** The cross-channel identity anchor is the substrate; the BOLD product expression is an experience no competitor delivers: a lead who got a voice call Mon, a Telegram brochure Tue, emails Thu talks to ONE agent that says "I remember you asked about the 3BHK pricing on the call — did the brochure I sent on Telegram help?" Channel invisible to the lead; relationship continuous. Sell as "your AI never forgets a lead, on any channel, in any language." Feasibility: HIGH (anchor + memory tables designed; this is the UX + sales framing).

**B3. Channel-Arbitrage Auto-Router (margin-as-a-feature).** Don't make the tenant pick a channel — the AI picks the **cheapest channel that will land AND get read**, per contact, per message: Telegram if opted-in (free, richest) -> WhatsApp 24h window (cheap utility) -> SMS if urgent (DLT-gated, metered) -> Email for brochures (high-trust). Falls THROUGH on failure (Telegram undelivered 10min -> SMS). Panel shows "saved Rs X this month by routing N messages off SMS." Feasibility: HIGH (cost model + fallback router in the orchestration phase; new = the policy layer + savings view).

**B4. The Comms Copilot — the non-technical founder runs the channel by typing/talking to it (the anti-dashboard).** NL command surface ("blast the new brochure to all hot leads on Telegram", "who went cold this week?", "draft a Diwali offer in Hindi for warm real-estate leads", "pause all SMS, my DLT template got flagged") executed by the AI Manager with PIN/risk/audit. He never learns the UI; he delegates. Reuses the ai_manager state-machine (verify->PIN->permission->delegate). Feasibility: MED.

**B5. Conversation-to-Creative loop ("turn what works in chat into the next ad/brochure").** When a conversation reveals the objection that flips a lead ("the EMI option closed them"), the system **auto-drafts a banner/brochure/ad angle around that winning objection-handle** via the Creative Studio seam, surfaced on a leaderboard. The conversation becomes the A/B lab feeding paid creative — grounded in real conversation intelligence, not just clicks (the WhatsApp F5 idea generalized + deepened). Feasibility: MED.

### TIER 2 — THE INTELLIGENCE (AI/LLM that makes it feel alive, not a bot)

**B6. Per-turn sentiment + "deal temperature" gauge with a LIVE founder feed.** Beyond binary hot/cold: a continuous deal-temperature rising/falling per turn (enthusiasm, objection, ghosting, price-shock), a live sparkline in the CRM AND streamed to founder Telegram for any lead crossing a threshold UP (buy now!) or DOWN (rescue this deal). "Three leads heated up while you slept" is the morning Telegram. Feasibility: HIGH.

**B7. Next-Best-Action engine — the AI tells the founder what to DO, doesn't just report.** Every lead card carries an AI NBA: "Call now — asked twice about site visit", "Send EMI brochure — stuck on price", "Let go — 3 unanswered, disengaged." Turns a CRM (a record) into a **workforce that hands the founder a ranked to-do list by revenue probability** — the difference between Famit and Kylas/LeadSquared. Feasibility: HIGH.

**B8. Objection-handling RAG per tenant ("the AI answers like YOUR best closer").** Tenant uploads (or the system learns from winning conversations) the objection->rebuttal playbook; the brain retrieves the tenant's proven rebuttal the moment a lead raises that objection on any channel. Real-telecaller intelligence, compounding: every closed deal teaches the playbook. Feasibility: MED (RAG built-but-empty on the platform; new = comms-conversation corpus + retrieval into the tool loop).

**B9. AI summarizer + auto-CRM-notes (zero manual data entry).** Every conversation, every channel, auto-distilled into a 3-line CRM note + structured fields (budget/timeline/objection/next-step) the instant it ends — the founder NEVER types a note. The same extraction pass produces the contact-facing after-call summary (his literal ask) AND the CRM note. Feasibility: HIGH (memory extraction already background asyncio; new = CRM-note write + summary template).

**B10. Smart re-engagement with ghost-detection + channel-switch.** Detect silence (no reply in configurable X hours); instead of a dumb "still there?", send a **context-aware, channel-switched** nudge — if Telegram went quiet, try a different angle on WhatsApp; reference the specific thing they cared about ("the floor plan you wanted is ready"). Caps at 2 attempts (DPDP-safe). Feasibility: HIGH.

**B11. Multilingual that MIRRORS the human, not a translate button.** Detect language per message, reply in the SAME register — Hinglish stays Hinglish, Tamil stays Tamil — never asks "which language?", never pins a house style. Bold extension: **per-tenant brand-voice + per-language tone** (a Mumbai realtor sounds different from a Chennai clinic), learned and applied across every channel. Feasibility: HIGH.

### TIER 3 — THE PRODUCT SURFACE (sellable + sticky)

**B12. The Unified Inbox — every channel, one timeline, the founder LIVES here.** One CRM view where Telegram + Email + SMS + WhatsApp + call transcripts interleave on ONE timeline per contact (customer right, AI left; jump in on any channel from the same box). One-tap human take-over silences the AI 4h. The **daily-active surface** that makes Famit sticky — he opens it every morning. Feasibility: HIGH (unified-thread schema + transcript chat-view exist/designed; this composes them).

**B13. Channel-health + reputation cockpit (protect the asset).** Live panel: WhatsApp quality rating, Telegram bot status, email deliverability/bounce/DKIM, SMS DLT template status + DND-block rate. Bold: the AI **auto-protects** — pauses a channel before a quality strike, warns "your DLT template is about to be flagged", throttles velocity to protect sender reputation. Losing a WhatsApp number or sending domain is catastrophic; this is the insurance. Feasibility: MED.

**B14. Compliance-as-a-feature, sold as TRUST (DLT/SPF/opt-in built-in, never bolted on).** Per-channel consent ledger (DPDP 2023), one-turn opt-out honored everywhere, DLT-template assistant for SMS, SPF/DKIM/DMARC wizard for email, Telegram deep-link opt-in. Sell it: "we keep you on the right side of TRAI and Meta automatically." Feasibility: HIGH.

**B15. Pre-built industry comms packs (instant value, zero blank-page).** Real-estate / clinic / coaching / D2C packs: templates, objection playbooks, drip journeys, hot-lead thresholds, brochure layouts — per channel, per language. Onboard in minutes. Makes it sellable to a non-technical owner who can't write one template. Feasibility: HIGH.

**B16. ROI + savings dashboard (prove it pays for itself).** Per channel: sent, cost, replies, bookings, revenue attributed, **and "Rs X saved by routing off SMS / replacing a telecaller."** Famit's monthly cost vs the human team it replaced. The renewal/upsell engine — the number that makes him keep paying. Feasibility: HIGH.

### TIER 4 — THE WILD CARDS (high-ceiling, sequence later)

**B17. Voice-note brain on Telegram/WhatsApp** — leads send voice notes (common in India); transcribe (Sarvam STT, in stack) -> answer in text or a synthesized voice note back. Closes the modality gap chat-only competitors have. Feasibility: MED.

**B18. Proactive event-triggered comms** — birthdays, EMI-due, renewal, site-launch, festival offers: the AI reaches out FIRST on the best channel, in-language, at the lead's best-send-time. From reactive to a proactive revenue clock. Feasibility: MED.

**B19. Group/broadcast intelligence on Telegram** — a tenant runs a Telegram channel/group; the AI moderates, answers FAQs, silently scores members as leads by their questions. Free reach, zero per-message cost, a lead-gen surface WhatsApp can't match. Feasibility: MED.

**B20. The "digital twin" of the tenant's best closer** — over time the brain learns the tenant's winning phrasing, pacing, and objection-handles from real closed deals; the agent literally talks like their #1 salesperson. The ultimate moat: better the more they use it, value non-portable. Feasibility: LOW-MED (the long game).

### THE TOP 7 (build only seven -> these: value x differentiation x feasibility)
1. **B12 Unified Inbox** — the daily surface; makes everything visible + the product sticky. (HIGH)
2. **B2 One Brain / One Memory across channels** — the experiential moat; "never forgets a lead." (HIGH)
3. **B3 Channel-Arbitrage Router** — margin-as-a-feature; cheapest-that-lands per message. (HIGH)
4. **B6+B7 Deal-temperature + Next-Best-Action** — CRM from records into a workforce that tells him what to do. (HIGH)
5. **B1 Revenue-Truth Signal Loop on every channel** — the sales-deck line competitors can't write. (HIGH)
6. **B4 Comms Copilot** — the non-technical founder runs the channel by talking to it. (MED)
7. **B16 ROI/savings dashboard** — proves it replaces the telecaller team; the renewal engine. (HIGH)

**The compounding story (one sentence):** every conversation across every channel flows into ONE brain with ONE memory (B2), the AI picks the cheapest channel that lands (B3), reads the deal temperature and hands the founder a ranked action list (B6+B7), surfaces it all in one inbox he lives in (B12), feeds proven conversions back to the ad algorithm (B1), lets him run it by just talking to it (B4), and shows him the rupees it saved/earned (B16) — a self-improving omnichannel revenue workforce, not a multi-channel chatbot.

**What stays honest (founder's standing rule):** levers, not guarantees; never fabricate metrics/testimonials; cold-start tenants see industry-pack defaults (B15), not invented numbers; every send consent-gated + suppression-checked + reputation-protected; the voice earner is NEVER touched (all of this rides the new comm_router + caller.py, never agent.py); Telegram ships FIRST (zero compliance gate), Email + SMS follow behind their DLT/SPF gates.

---

**END BOLD-IDEAS RESEARCH**

---

## PHASE: brainstorm-convergence — Cross-Phase Synthesis + Net-New Flows (2026-06-15)

> Three independent brainstorm phases (monetization-sellable, bold-positioning, out-of-box-ideas) plus the LLM-brain "99%" all ran. This phase does NOT re-list them — it (1) extracts the CONVERGENT WINNERS (ideas >=2 phases independently surfaced = highest-confidence build signal), and (2) adds only the genuinely NET-NEW flows/angles none of the three named. Tight, no fluff. The roadmap phase sequences; this is the de-duplicated truth-of-consensus.

### THE CONVERGENT 8 (every brainstorm phase independently landed here -> build these first, lowest risk of being wrong)
1. **Channel Registry first** (mirror PROVIDER-FRAMEWORK-PLAN) — capability-keyed `channel.send(tenant,contact,kind,payload)` over the SAME wallet/audit/RLS/firewall; a 5th channel = a DB row, not an engine. The keystone all phases agree precedes everything.
2. **One cross-channel brain + ONE contact-keyed timeline** — the AI on Telegram already knows the call transcript + WA thread + CRM stage. Named by every phase as THE structural moat point-tools cannot copy.
3. **Cheapest-channel-that-works router (Telegram-free -> WA-window -> Email -> SMS-metered last)** — cost becomes a selling point; the arbitrage spread is the margin. Unanimous.
4. **Actionable hot-lead Telegram alert = a command center, not a ping** — inline [Call now][Assign][Snooze][Take over], firewall-gated. Unanimously the highest value/cost feature; the demo-closer.
5. **Post-call auto-summary to the CONTACT as a branded recap (rich card, not text)** — rides the existing `_finalize_call` hook; swap the WA-only send seam for `channel.send`. Reuses the AI Asset card pipeline.
6. **Agentic brain with hands (book / quote / invoice / CAPI as firewall-gated tools)** — "Revenue Workforce," deals close while the founder sleeps. Named by all.
7. **Cross-channel CAPI signal closure** — every channel outcome (booked/paid) fires the Meta/Google revenue signal; extends the company's Revenue-Truth moat into comms. Unanimous billion-dollar differentiator.
8. **Compliance + consent vault as a sellable feature** (DLT/SPF-DKIM/opt-in ledger/quiet-hours/frequency-cap + AES-256-GCM per-tenant token vault) — fear-reversal selling point for Indian SMBs; near-zero COGS; unblocks scale. Unanimous.

### NET-NEW FLOWS (not named in the three prior brainstorms — genuine additions)
- **N1. "Second-attempt" auto-callback orchestration.** If the post-call summary message gets a hot reply on Telegram/WA, the brain can re-trigger an OUTBOUND voice call at the contact's stated good-time (firewall + DID-gated) — text re-opens a closed voice deal. Closes the chat->voice direction (prior phases only did voice->chat).
- **N2. Read-receipt-driven escalation, not just no-reply.** Telegram/Email give delivered+seen signals; WA gives read. Flow: seen-but-silent for X min on a hot lead -> escalate to founder ("they read it, didn't reply — nudge or call?"). Engagement-state machine, sharper than the time-only drip every phase described.
- **N3. Per-tenant "comms persona" inheritance from the voice agent.** The chat brain inherits the SAME named persona (e.g. "Riya") + tone the voice earner used for that tenant, so the lead feels one continuous human across call->chat. Differentiates from generic-bot continuity; reuses the voice persona config.
- **N4. Negative-signal auto-suppress (anti-churn for the TENANT's reputation).** If a contact replies STOP / annoyance / reports the bot on any channel, instantly suppress ALL channels for that contact + flag the campaign if the suppress-rate spikes — protects the tenant's sender reputation proactively, not just per-channel opt-out. A reputation circuit-breaker no prior phase named.
- **N5. "Why this lead is cold" diagnosis (not just a cold flag).** When a lead goes cold, the brain writes a one-line reason from the transcript+engagement ("price objection, never saw the financing card") into the founder digest — turns the digest from a list into a coaching tool.
- **N6. Channel-of-record fallback for delivery proof.** For high-ticket/legal-sensitive tenants, mirror the final agreed terms to Email (timestamped, archivable) regardless of the active chat channel — a compliance/audit artifact buyers in regulated SMB verticals will pay for.

### THE SINGLE SHARPEST CUT (if the founder builds ONE thing this week)
Ship **Telegram channel adapter + post-call auto-summary to the contact + actionable hot-lead alert to the founder**, riding the existing `_finalize_call` hook and a `channel.send` registry, flag-gated `COMM_TELEGRAM_ENABLED=OFF` by default. Zero COGS, zero Meta friction, demo-closes in 30 seconds, and proves the registry that every later channel snaps onto. Everything else is sequencing.

---

## PHASE: ootb-channels — OUT-OF-THE-BOX CHANNELS the founder did NOT name (2026-06-15)

> **Brief [ootb-channels]:** the founder named 3 channels (Telegram + Email + SMS). This phase answers the harder
> question — **which additional comms SURFACES/channels should the omnichannel product carry**, beyond those three,
> that he did NOT name: Telegram Mini-Apps (in-chat booking/payment), RCS, voice-notes, in-app web chat widget,
> web-to-Telegram handoff, WhatsApp-when-unblocked-as-just-another-channel — plus the surfaces NONE of us named.
> The keystone makes this cheap: every surface is **a row + an adapter behind the capability-keyed channel
> registry** (`channel.send(tenant, contact, kind, payload)` — the PROVIDER-FRAMEWORK-PLAN clone), flag-gated
> `COMM_<SURFACE>_ENABLED=OFF` (resting byte-identical), riding the same wallet/audit/RLS/firewall + the ONE
> cross-channel brain + the unified contact timeline. A new surface is NEVER a new engine — so "add a channel"
> is a product decision, not an architecture project. Earner-safe (rides `comm_router`/caller.py, NEVER agent.py).
> This phase is a SELECTION VERDICT (build / sequence / defer), not a re-list of features. Discipline: a surface
> ships only if it (a) adds reach or a revenue terminal the named 3 can't, (b) rides existing seams, (c) is
> compliance-honest. Tiers: **[NOW]** ride Telegram (already first), **[NEXT]** small adapter, **[LATER]** real new
> surface, **[DEFER]** gated on a dependency/compliance, **[REJECT]** anti-bloat.

### THE VERDICT TABLE — which surfaces, and why (one line each)

| # | Surface (channel/sub-channel) | Tier | The one-line WHY (reach / revenue / moat it adds the named-3 can't) |
|---|---|---|---|
| C1 | **Telegram Mini-App "Deal Room" (TWA)** — in-chat micro-site: summary + quote + brochure + calendar + Pay-Now | **[LATER]** | Turns the chat into a **close-and-collect terminal** — lead reviews→books→PAYS without leaving Telegram or needing a website; the "wow," white-label, per-tenant. No point-tool has it. Rides Telegram (already C0), so zero new transport. |
| C2 | **Telegram Payments (UPI provider-token + Stars `sendInvoice`)** | **[LATER]** | The **real-money terminal event** — "Pay ₹500 to lock your slot" → paid → CAPI "Purchase" to Meta. Makes a comms channel a revenue channel and gives the Revenue-Truth loop a *paid* signal, not just "booked." Sub-channel of Telegram, not a new transport. |
| C3 | **Telegram voice-notes (`sendVoice` + STT in/out)** | **[NEXT]** | Indians message in voice notes; inbound voice → Sarvam/Groq STT → brain → optional TTS voice-note back **in the lead's language** = the voice-agent persona ("the same Riya who called") continued INTO chat. Modality reach chat-only rivals lack; reuses the in-stack voice STT/TTS. Equally a WhatsApp audio-message adapter. |
| C4 | **In-app / website Web-Chat Widget (embeddable bubble)** | **[LATER]** | Captures the **anonymous website visitor** the named-3 can't reach (no phone/email/handle yet) — the top-of-funnel entry point; the same brain answers, then asks for a number/Telegram to continue. New transport (WS/SSE adapter) but pure registry add; the richest lead-capture surface a comms suite needs. |
| C5 | **Web-to-Telegram handoff (one-tap deep-link `t.me/bot?start=<token>`)** | **[NEXT]** | The **bridge that migrates a free anonymous web-chat lead onto the free, rich, re-engageable Telegram channel** (so you can follow up later — a web widget alone is ephemeral). Lead-initiated = compliant opt-in. Tiny: a deep-link token map; no new transport. The glue between C4 and Telegram. |
| C6 | **WhatsApp as just-another-registry-channel (when Meta unblocks)** | **[DEFER → fold-in]** | When Meta business-verification clears, WhatsApp stops being a bespoke system and becomes **one more `channel.send` adapter** under the SAME router/brain/timeline/router-arbitrage — unifying the existing WA build into the omni fabric instead of a silo. Gated on founder's Meta verification; the adapter shape is already proven. |
| C7 | **RCS (Rich Communication Services — Google/carrier "SMS 2.0")** | **[DEFER]** | The **branded, verified-sender, rich-card upgrade path for SMS** (logo, carousels, suggested-action chips, read receipts) — the future of the SMS lane. But India RCS reach/agent-onboarding is still maturing + carrier-gated; build the SMS adapter now, slot RCS as the same lane's premium tier when MSG91/Gupshup RCS agent approval lands. Don't block SMS on it. |
| C8 | **Founder-facing push: PushNotification / native app alert as a hot-lead channel** | **[NEXT]** | The hot-lead war-room shouldn't be Telegram-ONLY — model the **founder alert as its own capability** (`channel.send(founder, alert)`) so it can fan to Telegram + a native/push alert + (later) a voice-note call. One-line registry win; makes the "interrupt me" promise device-agnostic. |
| C9 | **Telegram Channel/Group broadcast surface (opt-in list)** | **[LATER]** | A **zero-COGS marketing-broadcast lane** (drip offers, inventory drops, festival blasts to opted-in joiners) vs WhatsApp's ~₹0.86/marketing-template — a hard cost-story for the sales deck. Sub-surface of Telegram; the AI silently scores group members as leads by their questions. |
| C10 | **iMessage / Apple Business Chat** | **[REJECT for India]** | Premium rich channel, but ~negligible Indian SMB-lead penetration + heavy Apple onboarding. No reach ROI for the target market; revisit only for an international/diaspora tenant. |
| C11 | **Instagram/Facebook Messenger DMs** | **[DEFER]** | Real reach for D2C/retail tenants and a natural Meta-CAPI loop sibling, but it's another Meta-verification + 24h-window + policy surface (same friction as WhatsApp). Slot it AFTER WhatsApp folds in (C6), reusing that adapter shape — not before Telegram/Email/SMS prove the registry. |

### THE HIGH-VALUE PICKS (what I'd actually build, in order)

**Ship-soon (small, ride existing seams, high delight):**
- **C3 voice-notes** + **C5 web→Telegram deep-link** + **C8 founder-alert-as-capability** — each is a tiny adapter/token-map over surfaces we already have (Telegram + the voice STT/TTS stack + the hot-lead alert), and each adds a reach or continuity dimension the named-3 structurally can't. Lowest risk, fastest "wow."

**Build-next (a real new surface, but pure registry adds):**
- **C4 Web-Chat Widget** (anonymous-visitor capture — the missing top-of-funnel) → feeds **C5** to migrate that lead onto free Telegram.
- **C1 Mini-App Deal-Room** + **C2 in-chat payment** — the close-and-collect terminal + the *paid* CAPI signal; the demo headline. Sub-surfaces of Telegram, so no new transport, but real product depth.
- **C9 Telegram broadcast list** — the zero-COGS marketing lane / sales-deck cost-story.

**Fold-in / sequence (gated on a dependency, not on us):**
- **C6 WhatsApp-as-a-channel** (on Meta verification) — collapse the existing WA silo into the omni registry.
- **C7 RCS** (on India RCS agent approval) — the premium tier of the SMS lane.
- **C11 IG/Messenger DMs** — after C6, reusing the Meta-window adapter.

**Reject (anti-bloat):** **C10 iMessage** for the India market (no reach ROI). And per PLAYBOOK: NO new surface gets its own engine/money-door/store/identity — every one is `channel.send` + a row + a flag, over the ONE brain, ONE timeline, ONE wallet/audit/RLS, NEVER agent.py.

### THE ONE STRUCTURAL INSIGHT
The named-3 (Telegram/Email/SMS) are **transports**; the real out-of-the-box wins are **two new SURFACE-TYPES the registry should model from day one**: (1) an **anonymous-inbound surface** (C4 web-chat) that the existing 3 can't be — they all need an identity first; and (2) an **in-channel commerce surface** (C1+C2 Mini-App + payments) that turns a conversation into a *paid* terminal event. Design the channel registry's capability enum to include `web_widget` (anonymous inbound) and `in_chat_commerce` (invoice/pay) now — not just `telegram|email|sms` — so these moonshots are a row, not a refactor, later. And make the **founder-alert a first-class capability** (C8) so "interrupt me when a lead goes hot" is device-agnostic from the start.

---

**END ootb-channels RESEARCH**


---


## PHASE: ootb-ai — The Comms AI Brain, the 99% (out-of-the-box AI) (2026-06-15)

> **Scope of THIS phase only:** the founder named six AI capabilities — (1) comms copilot that drafts replies, (2) auto-CRM-sync from chat, (3) lead-scoring from conversation, (4) multilingual auto-reply, (5) sentiment/intent tagging, (6) unified per-contact memory across voice+comms. Prior phases (`llm-conversation-brain`, `hot-lead-automation`, the three brainstorm phases, `monetization-sellable`) already specified the *mechanics* of most of these. This phase does NOT re-list them. It (a) gives the **decision-grade pick** for each named capability — WHICH approach + WHY, grounded in what already exists on the box, and (b) adds the **net-new AI angles** no prior phase named. Every pick rides the new `comm_router`/`caller.py` + the existing Groq/Sarvam/Haiku stack — NEVER `agent.py`. One-line why each, no fluff.

### ARCHITECTURE LAW FOR ALL AI HERE (reuse, do not reinvent)
- **One brain, model-routed by COST not capability** — Groq Llama-4/3.3 70B for the live reply loop (native Hindi/Hinglish/regional, ~450ms two-shot), **Haiku/Flash for the cheap async passes** (fact-extraction, CRM-note, summary, intent-tag) OFF the critical path via `asyncio.create_task`. Reuses `llm_router/provider_pool.py` least-used rotation + Fernet key-store; a new model = a registry row, not code (mirrors PROVIDER-FRAMEWORK).
- **The contact-identity anchor (`communication_contact_identity`) is the spine of EVERY AI feature here** — memory, scoring, copilot, summary all key off ONE `lead_id`, never a channel id. This is the single line every competitor's per-channel bot cannot draw.

### THE FOUNDER'S SIX — the decision-grade pick for each (WHY this way)
1. **Comms Copilot (drafts replies).** *Pick:* TWO modes off ONE draft-engine — (a) **autonomous** (brain replies live, the default), (b) **suggest-only / "approve-to-send"** per-tenant or per-lead-temperature toggle (founder reviews the draft on hot/high-ticket leads before it goes). *Why:* a single "auto vs assist" flag turns the same LLM into both the team-replacement AND the nervous-founder's safety net — the #1 adoption objection ("will it say something dumb to my best lead?") is answered by config, not by a second product. Reuses the AI-Manager NL command surface (B4) for the founder-facing side ("draft a Diwali offer in Hindi for warm leads").
2. **Auto-CRM-sync from chat.** *Pick:* a single **async extraction pass** (Haiku/Flash, `asyncio.create_task`, off critical path) that on every turn-close writes BOTH the structured CRM fields (budget/timeline/objection/next-step/stage) AND a 3-line human CRM note — **upsert-merge, never overwrite** (only ADD new facts). *Why:* the founder types zero notes; the SAME extraction also produces his contact-facing after-call summary (his literal ask) — one cheap pass, three outputs (CRM fields + note + summary). Graceful-degrade if it fails (the reply already shipped).
3. **Lead-scoring from conversation.** *Pick:* **BANT-in-conversation as the `qualify_lead` tool**, 0-100, hot threshold **70** to MATCH the live `caller.py`/voice scoring exactly — so a lead's score is ONE number across call+chat, not two rival scores. Crossing 70 auto-fires `trigger_founder_alert` in the same tool execution. *Why:* unifying the threshold with the voice earner means the hot-lead alert, the CRM temperature, and the router priority all speak one language; conversational qualification reads real intent (2-5x more qualified than form-fill) without a form.
4. **Multilingual auto-reply.** *Pick:* **Groq-native first** (Llama-4/3.3 replies in Hindi/Hinglish/Marathi/Bengali natively, zero added cost/latency), **Sarvam translate-normalize ONLY as fallback** for low-resource scripts (Tamil/Telugu/Kannada/Malayalam) when Groq output degrades; detect with local `langdetect`/fasttext (<5ms, no API). Mirror the register — Hinglish stays Hinglish — **never ask "which language?"**. *Why:* "talks to every lead in their language" is the brand line and it costs ~Rs.0 on the 80% Hindi/Hinglish path; pay the +200ms Sarvam tax only on the 20% that needs it. Reuses the Sarvam keys already in the voice stack.
5. **Sentiment / intent tagging.** *Pick:* tag **per-turn, in the SAME async extraction pass** (no extra LLM call) — sentiment (pos/neutral/neg + a continuous deal-temperature delta) AND intent/topic (pricing / demo / objection / competitor / urgency / ready-to-buy). Stored alongside each turn in session history + rolled into the contact memory. *Why:* it is free (rides pass #2), it powers FOUR downstream things at once — handoff triggers (3x neg = escalate), the deal-temperature feed (B6), the conversation-health auto-pause, and the Enterprise "Comms Intelligence" analytics upsell (pure margin, data we already log).
6. **Unified per-contact memory across voice+comms.** *Pick:* **two-layer hybrid** — short-term rolling 20-turn JSONB window in PG (no vector DB needed) + long-term extracted-facts row per `contact_identity`, with a compact `cross_channel_timeline` (channel, ts, one-line summary) injected as "prior activity" into the system prompt. Optional pgvector only if/when semantic recall is needed. *Why:* this is THE moat — the chat brain pulls the call transcript + WA thread + last summary and says "I remember you asked about pricing on the call Tuesday," which a per-channel point-tool structurally cannot; it is plain Postgres (cheap, fast, already RLS'd), and long-term memory is not optional (drops task completion 80%->45% without it, Mem0 2026).

### NET-NEW AI ANGLES — none of the prior phases named these (the real out-of-the-box)
- **AI-1. Persona inheritance from the voice earner.** The chat brain adopts the SAME named persona + tone the tenant's voice agent used (e.g. "Riya"), so the lead feels ONE continuous human from call -> Telegram -> email. *Why:* continuity is the felt difference vs a generic bot; it reuses the W1 dynamic-vendor-script -> adaptive-persona config already live on the voice side — zero new authoring.
- **AI-2. "Why this lead went cold" diagnosis (a reason, not a flag).** When a lead disengages, the brain writes ONE root-cause line from the transcript+engagement ("price objection, never opened the financing card") into the founder digest. *Why:* turns the morning Telegram digest from a list into a coaching tool — the founder learns WHY he's losing deals, which no CRM "status: cold" field tells him. Pure async LLM, ~Rs.0.
- **AI-3. Next-Best-Action per lead (the brain tells the founder what to DO).** Beyond a score: each hot/warm lead gets a ranked one-tap action ("call now — said free after 6pm", "resend brochure — opened twice, no reply", "offer the Rs.X EMI — that was the objection"), inline in the Telegram alert / CRM. *Why:* converts records into a workforce that prioritizes the founder's day; it's the difference between "here are your leads" and "do these three things first," and it rides data the brain already extracted.
- **AI-4. Channel-preference learning (which channel/time this contact actually answers).** The memory learns per-contact that "answers Telegram in the evening, ignores SMS" and the cost-router + drip schedule USE it (not just the global cheapest-channel rule). *Why:* lifts reply rates AND cuts spend by not paying for SMS to someone who only opens Telegram — a self-tuning loop the static router can't do; one JSONB field on the memory row.
- **AI-5. Self-improving reply quality via won/lost outcome labels (cheap eval loop).** Tag every conversation with its terminal outcome (booked / paid / lost / ghosted) and mine the winners — surface the objection-handling phrasings that correlate with closes back into the per-tenant prompt/snippet library. *Why:* the product gets BETTER the longer a tenant runs it (compounding lock-in + a real differentiator vs static-prompt bots) using only labels we already capture via CAPI/booking — no fine-tune cost, no labeling cost.
- **AI-6. AI compliance guard on the OUTBOUND draft (pre-send safety net).** A fast classifier pass flags a draft that (a) violates DLT/opt-out/quiet-hours, (b) makes an unbacked claim/price, or (c) trips a tenant-defined red-line — block or route to founder-approve. *Why:* protects the TENANT's sender reputation and the founder from a bad auto-send (the deepest trust objection for letting AI talk to customers); near-zero COGS, and it's a sellable "AI won't go off-script" guarantee competitors don't offer.

### THE AI PICKS, RANKED (highest value-per-cost first)
1. **Unified voice+comms memory on the contact-identity anchor** (founder #6) — the structural moat; everything else keys off it. Build first.
2. **One async extraction pass = CRM-sync + summary + sentiment/intent tags** (founder #2 + #5 fused) — three deliverables, one cheap Haiku call, off the hot path. Highest leverage.
3. **Unified-threshold conversational lead scoring** (founder #6, threshold-matched to the voice earner) — makes the hot-lead alert + router + CRM speak one number.
4. **Groq-native multilingual, Sarvam-fallback** (founder #4) — the brand line at ~Rs.0 on the 80% path.
5. **Copilot dual-mode (auto / approve-to-send)** (founder #1) — answers the #1 adoption fear with a flag.
6. **AI-3 Next-Best-Action + AI-2 cold-reason** — turns the digest/CRM from records into a workforce; rides already-extracted data.
7. **AI-1 persona inheritance + AI-4 channel-preference learning** — the felt "one human, right channel" continuity; reuses live config.
8. **AI-5 outcome-labeled self-improvement + AI-6 pre-send compliance guard** — the compounding-quality moat + the trust/safety guarantee; both near-zero COGS.

**One-sentence thesis:** every channel feeds ONE brain that remembers the lead across voice+chat, extracts CRM+summary+sentiment in a single cheap async pass, scores on the SAME number the voice earner uses, replies in the lead's own language as the same named persona, learns which channel/phrasing actually wins, hands the founder a ranked do-this-now list with the reason each lead cooled, and never auto-sends anything that trips compliance — a self-improving omnichannel revenue brain, not a multi-channel autoresponder.

**END ootb-ai PHASE**

## PHASE: ootb-completeness — The 99% Nobody Named (Omnichannel Completeness Sweep)
**Date:** 2026-06-15
**Scope:** Out-of-the-box brainstorm. The founder named ~1% (Telegram/Email/SMS channels, a builder, post-call auto-msg, hot-lead alert, LLM brain). This phase names the OTHER 99% — every layer a billion-dollar, sellable, differentiated omnichannel revenue-comms product needs that nobody has put on paper yet. Grounded in the existing seams (wallet/firewall/audit/RLS/provider-registry/CRM/voice) so each rides existing infra, additive, earner-safe. Deliberately does NOT repeat the channel/cost/template/compliance phases above, nor the WhatsApp campaign features in `design/wa-out-of-box.md` (follow-ups, leaderboard, personalization, voice+WA sequences, promote-to-ad) — it sits ABOVE all of them as the cross-cutting product spine.

### THE FRAME — why "channels + a builder" is not a product
A channel adapter set is a commodity (every BSP has it). The MOAT is the layer ABOVE the channels: ONE identity per human, ONE consent ledger, ONE orchestration brain that picks channel+time+content, ONE deliverability reputation engine, ONE truth-loop back to ads. The founder's named features are nodes; the 99% below is the GRAPH they live in. Without it you have 4 disconnected senders, not a Revenue-Comms OS.

### TIER 1 — MUST-HAVE FOUNDATIONS (the product is broken/unsellable/illegal without these; build before any "feature")

**1. Unified Contact Identity + Channel Resolver (the spine).**
One human = one `contact` row with MANY endpoints (phone, email, telegram_chat_id, wa_id), reachability state per endpoint, and a per-endpoint "last good / bounced / blocked" health flag. Every channel send and every inbound reply resolves to the SAME contact + same CRM lead. WHY: without this, "after-a-call auto-message" cannot know WHICH email/telegram to use, hot-lead alerts double-fire, and the conversation brain has no single memory. This is the #1 unnamed dependency — it is what turns 4 senders into omnichannel. Rides the CRM lead table + `communication_sessions.lead_id` already in the schema.

**2. Unified Consent + Opt-Out Ledger (per channel, per purpose) — legal gate, not a feature.**
Immutable rows: (contact, channel, purpose=transactional|marketing, status, source, timestamp, proof). Honor STOP/unsubscribe/Telegram-block INSTANTLY and ACROSS channels for marketing. WHY: DPDP (India) + CAN-SPAM + TRAI DLT + Telegram ToS all require it; one missed opt-out = fines + WA quality-rating collapse + bot ban. The cost-routing phase listed consent GATES but not the consent STORE/lifecycle that feeds them. Non-negotiable, ships first. Rides `firewall.py` audit + a new FORCE-RLS `communication_consents` table.

**3. Per-Tenant Secret Vault for channel credentials (bot tokens, SMTP/API keys, DLT IDs).**
Telegram bot token, email API key, SMS auth, DLT template IDs — all per-tenant, encrypted at rest (AES-256-GCM, key in env/KMS, NEVER in DB plaintext), decrypt-on-use, rotatable, never logged. WHY: a leaked bot token = a stranger sends as the tenant brand to their leads; a leaked SMTP key = spam-blast on the tenant domain reputation. Founder named "bot-token vault" in passing — this generalizes it to ALL channel secrets and makes it a first-class subsystem. Rides the existing env-secret + RLS pattern.

**4. Outbound Idempotency + Dedup + Suppression (do not message the same human twice / do not message a DND/opted-out human).**
Idempotency key `comms:{cause_id}:{channel}:{contact}` on every send (cost-routing phase has it for wallet debit; generalize it to the SEND itself). Plus a global suppression list (hard-bounced, complained, opted-out, DND). WHY: duplicate post-call messages and messaging an unsubscribed lead are the two fastest ways to look broken and get reported. Cheap, pure infra, prevents the most embarrassing failures.

**5. Webhook Ingress Security (the inbound attack surface nobody hardened).**
Telegram `X-Telegram-Bot-Api-Secret-Token` verify, email inbound-parse signature, SMS provider HMAC, replay-window + nonce, per-tenant routing by webhook path/secret, rate-limit + payload-size cap. WHY: the inbound webhooks are PUBLIC endpoints on the live box — an unauthenticated or spoofable webhook lets anyone inject fake "leads", trigger the LLM brain (burn tokens/money), or poison conversation state. The Telegram phase noted the secret token; this makes ingress hardening a named subsystem for ALL inbound channels. Additive router, never touches the earner.

### TIER 2 — THE DIFFERENTIATORS (what makes it billion-dollar + sellable, not a commodity BSP)

**6. The Orchestration Brain / "Comms Conductor" — channel+time+content decisioning as ONE policy.**
Not "send Telegram then email then SMS" hardcoded — a per-tenant POLICY engine: given (contact, reachable endpoints, consent, message intent, cost ceiling, urgency, history), DECIDE the optimal channel, send-time, and content variant; escalate on no-read; collapse on success. WHY: this is the actual product. The cost-routing phase gave the cost ranking; this is the brain that USES it plus reachability + engagement + urgency. It is what a buyer pays for vs a $5/mo sender. Rides the existing workflow-trigger seam + cost table.

**7. Two-Way Threaded Conversation Memory across ALL channels (omnichannel inbox + unified thread).**
A lead who got a Telegram summary, replied by email, then SMSed — it is ONE thread the AI and the human founder both see. The LLM brain reads cross-channel history (the schema `history JSONB` per session — but UNIFIED per contact, not per channel-session). WHY: the founder named a "multi-step LLM conversation brain" PER channel; the 99% is that the brain must be CHANNEL-AGNOSTIC with one memory, and there must be a human-takeover inbox (founder jumps in, AI steps back, then resumes). This is the WhatsApp/Intercom "shared inbox" table-stakes that turns it into a real product.

**8. Revenue-Truth Signal Loop extended to comms (the existing moat, now omnichannel).**
Every comms outcome (replied / clicked / booked / converted / went-cold) flows back as a quality signal to Meta/Google CAPI — same loop the platform already runs for calls. WHY: this is Famit named moat (per MEMORY: Revenue-Truth Signal Loop). Comms engagement is a HIGH-quality conversion signal ads should bid on. No competitor WhatsApp/SMS tool closes this loop. It is the single most differentiating, already-half-built thing — comms must EMIT into it, not be a dead-end sender.

**9. Engagement Tracking + Attribution (opens, clicks, link-shorten, UTM, per-channel conversion).**
Per-tenant branded short-link domain, click tracking, email open pixel (where legal), Telegram button-callback as a click event, attribution back to campaign + channel + variant. WHY: "which channel/template/banner actually drove the booking" is the question every buyer asks and the input to #6 and #8. The leaderboard in wa-out-of-box measures WhatsApp; this generalizes measurement to ALL channels with real attribution. Rides the audit/event stream.

**10. Best-Channel + Best-Time learning per contact (transparent heuristic, not ML).**
Learn each contact responsive channel + responsive hour from their own reply history; feed #6. WHY: lifts reply rates without a new ML engine — same posture as wa-out-of-box F9 (transparent heuristic). Differentiator that is cheap to build.

**11. Template Versioning + Multi-Language + A/B at the OMNICHANNEL level.**
One logical "message" (e.g. post-call summary) has channel renderings (TG markdown / email HTML / SMS GSM7) + language variants (EN/HI/Hinglish/regional) + A/B variants, versioned + approval-gated. WHY: the template phase defined the cross-channel registry SCHEMA; this is the VERSIONING + i18n + experiment lifecycle on top — the thing that makes content manageable at scale and is the multi-language reach play for India.

### TIER 3 — OPERATIONAL / TRUST / MONETIZATION (the "billion-dollar company runs on this" layer)

**12. Deliverability & Sender-Reputation Engine (warmup, bounce/complaint handling, domain health, WA quality-rating, Telegram-flood-wait, DLT-failure auto-quarantine).**
Per-tenant sender health dashboard + automatic throttle/quarantine when a domain/number/bot degrades. WHY: deliverability IS the product for email/SMS — a tenant who blasts and tanks their domain blames Famit. This protects every tenant (and Famit shared) reputation and is a real enterprise sell. Rides provider webhooks + a health table.

**13. Cross-Tenant Frequency Capping / "Do-Not-Fatigue" + quiet-hours per tenant policy.**
Global cap: "no human gets more than N marketing messages/week across ALL channels"; respect quiet hours + timezone per contact. WHY: the fastest way to get blocked/reported is over-messaging; this is the guardrail that keeps the autonomous engine from nuking a tenant list. Trust = retention = LTV.

**14. Per-channel Cost Metering + Budget Caps + rupee Stop-Loss + margin guard (billing completeness).**
Telegram=₹0, SMS/WA metered (cost-routing has the rates) — but ADD: per-tenant per-period budget caps, a hard stop-loss, low-balance alerts, and a per-message MARGIN so Famit does not sell SMS below cost. WHY: the wallet exists; the comms-specific budgeting + margin + auto-pause-on-empty is the unnamed billing layer that makes it a real SaaS line item, not an uncapped money leak.

**15. Observability: per-send lifecycle status, dead-letter queue, delivery SLA dashboard, replay.**
Every send has a state machine (queued -> sent -> delivered -> read -> replied -> failed) with a DLQ for failures and a founder-visible dashboard. WHY: "did my hot-lead alert actually reach me?" must be answerable. Silent failure on the hot-lead alert = lost deal = founder rage. Observability is what makes it trustworthy.

**16. Scheduling / Drip / Journey at the omnichannel level + a Sandbox/Test-send mode.**
Schedule sends, multi-step omnichannel journeys (generalizes wa F1/F6 across channels), AND a "send to myself / dry-run" test mode so the founder previews EXACTLY what the contact gets on each channel before it goes live. WHY: the named "multi-step builder" needs a runtime (scheduler) and a safety net (test-send) — both are the difference between a toy and a tool.

**17. Founder Command Console over Telegram (two-way, not just alerts).**
The hot-lead alert is one-way; make the founder Telegram a CONTROL surface: reply "call now" -> triggers a call; "snooze"; "handoff to me" -> pauses the AI; daily digest; "/stats". WHY: this fuses with the AI-Manager (a named flagship) — the founder runs the business from Telegram. Massive differentiation, rides the firewall/PIN step-up for any money/destructive action.

### CROSS-CUTTING (applies to every item above)
- **Dormant-until-creds** everywhere (no token -> channel degrades to `not_configured`, never raises into a call/dial loop — the platform house rule).
- **Tenant-from-token, FORCE-RLS** on every new `communication_*` table (zero-`%` DDL); every cross-channel join re-asserts tenant ownership.
- **One money-path** (wallet) + **one audit channel** (immutable PG events) + **one identity** (contact) — no feature opens a second door.
- **Earner-safe/additive**: all of this is a SEPARATE comms plane reached by additive routers; it NEVER edits agent.py / the voice earner. Regression-gate = a real outbound call still rings before+after.
- **Honest, never overclaimed**: routing/timing/best-channel BIAS and ASSIST; they do not guarantee; cold-start contacts fall back to transparent defaults shown as honest empty states (no fake percentages).

### THE TOP-7 HIGH-VALUE PICKS (best value / effort / risk — what to actually sequence first)
1. **Unified Contact Identity + Channel Resolver** — the spine; everything else needs it; without it the founder named features cannot even pick a destination. (Tier-1, build FIRST.)
2. **Unified Consent + Opt-Out Ledger** — legal hard-gate; cheap; ships beside #1; un-skippable for India/global. (Tier-1.)
3. **The Orchestration Brain (Comms Conductor)** — the actual product/moat: decides channel+time+content per contact; turns 4 senders into omnichannel; uses the cost table already researched. (Tier-2, the differentiator.)
4. **Unified Cross-Channel Conversation Memory + Human-Takeover Inbox** — one thread per human the AI+founder share; upgrades the named per-channel brain into a real shared-inbox product. (Tier-2.)
5. **Revenue-Truth Signal Loop extended to comms** — emit every comms outcome to Meta/Google CAPI; Famit named moat, half-built, no competitor closes it; turns comms into a bidding signal not a dead end. (Tier-2.)
6. **Deliverability & Sender-Reputation Engine** — protects every tenant domain/number/bot health + auto-quarantine; deliverability IS the product for email/SMS and a real enterprise sell. (Tier-3, but high.)
7. **Founder Command Console over Telegram (two-way)** — run the business from Telegram (call-now/handoff/digest), fused with the AI-Manager + firewall PIN step-up; huge differentiation on the already-unblocked channel. (Tier-3, high delight.)

**ONE-LINE WHY THIS PHASE MATTERS:** the founder asked for channels + a builder; the difference between that and a billion-dollar product is the IDENTITY + CONSENT + ORCHESTRATION + MEMORY + SIGNAL-LOOP + DELIVERABILITY spine above them — build that spine first (#1, #2), then the conductor and the signal loop are the moat (#3, #5), and the two-way Telegram console (#7) is the unblocked-channel delight that sells.

## PHASE: ootb-automation — The Automation ENGINE (drip · A/B · smart-send-time · fallback ladder · re-engagement · abandoned-flow recovery · event-driven journeys) (2026-06-15)

> Prior phases produced the IDEA surface (brainstorm/convergence) + the static cost-routing tiers + the hot-lead trigger. This phase designs the **automation MACHINERY itself** — the concrete, buildable engine that drives messages through those tiers over TIME: the cadence runtime, the experiment engine, the send-time learner, the engagement state-machine, the recovery loops, the event bus. It does NOT re-list ideas; it specifies the *mechanism* behind the seven named automations + the 99% of automation patterns no prior phase named. **Discipline (PLAYBOOK + wa-out-of-box anti-bloat):** every automation = a Hatchet graph + a row in the new `comm_*` tables over the channel registry (`channel.send`) + the same wallet/audit/RLS/firewall/suppression gates. **One engine (durable journey runtime), not seven bespoke schedulers.** Additive, flag-gated (`COMM_AUTOMATION_ENABLED=OFF`), NEVER touches agent.py. Where a number is needed it is a transparent heuristic, never a fabricated ML claim.

### 0. THE KEYSTONE INSIGHT — all seven are ONE engine

Drip, A/B, smart-send-time, fallback, re-engagement, abandoned-flow, event-journeys are NOT seven features — they are **one durable-journey runtime** with different *entry triggers* and *node policies*. Build the runtime once:

```
Journey = (Trigger) -> [ Step: {wait, condition, send(channel-resolved), branch, goal-check} ]* -> Exit
Runtime  = Hatchet durable workflow (aio_sleep_for / aio_wait_for_event) — survives reboot, one per (tenant, contact, journey).
Send     = channel.send(tenant, contact, kind, payload)  ->  router resolves channel + meters via wallet.
Exit     = GOAL reached | STOP/opt-out | suppress | max-touches | journey superseded.
```
Every named automation below is a **journey template** (a seeded row), not new code. This is the anti-bloat verdict: **a 5th automation is a template, not an engine.**

---

### 1. THE SEVEN NAMED AUTOMATIONS — mechanism + the WHY (each rides the one runtime)

| # | Automation | The MECHANISM (how it actually runs) | One-line WHY (revenue/moat) |
|---|---|---|---|
| **1. Drip / cadence** | A journey template: `enroll -> send(touch1) -> wait(d) -> goal? -> send(touch2)...`. Delay + copy per step are tenant-editable. Durable Hatchet `aio_sleep_for`; **goal-exit checked before EVERY touch** (no nagging a converted lead). | One send underconverts; a 3-5 touch cadence multiplies replies/bookings at ~0 cost (Telegram-first). The single biggest revenue lever. |
| **2. A/B / A/B/n test** | Journey carries `variant_set`; on enroll, **deterministic hash-bucket** `hash(contact_id+exp_id)%100` assigns a variant (sticky, reproducible, no flicker). Outcomes tagged `variant_id` on the send_log; a **sequential significance gate (mSPRT / Thompson)** auto-declares a winner once significant, then **auto-routes 100% to the winner** and emails the founder "Variant B won (+34% reply, 95% conf)." | The comms product **optimizes itself** — copy/subject/send-time/channel all become learnable. Self-improving = compounding moat. |
| **3. Smart send-time** | A **resolver** the wait-node calls before dispatch: `next_good_slot(contact)` = mode of that contact's prior open/reply hours (from send_log timestamps) -> else tenant aggregate -> else local business-hours default. Schedules via durable Delay to the slot. **Transparent heuristic, honestly labeled — NOT a black-box ML service** (that is the rejected bloat). | Free lift on every send (opens/replies rise), and protects WhatsApp quality rating / DLT windows (no 2 a.m. sends). |
| **4. Omnichannel fallback ladder** | Extends the cost-routing tiers into a **per-message delivery state-machine**: `send(Telegram) -> await delivered+read N min -> if undelivered: send(WA-window/utility) -> await -> if undelivered: SMS (DLT-gated, metered)`. **Idempotency key `comms:{journey_run}:{step}:{contact}`** on the wallet debit ensures a retry/fallback NEVER double-charges; **stop on first delivered+read**; never burn 2x SMS. | Guaranteed reach at the **lowest cost that actually lands** — the channel-arbitrage margin, surfaced as "saved Rs X by routing off SMS." Cost-as-a-feature. |
| **5. Re-engagement (win-back)** | A **scheduled enrollment query** ("contacts with `last_engaged_at` older than X and stage not in dead/won") feeds the runtime nightly. The nudge is **context + channel switched** (Telegram quiet -> try WA with a different angle, referencing the specific thing they cared about from memory). Hard-capped (<=2 attempts, DPDP-safe), exits on any reply. | Revives dead pipeline for ~0 cost; turns a silent CRM into a self-replenishing revenue clock. |
| **6. Abandoned-flow recovery** | **Read-receipt / partial-progress state machine** (the sharper, net-new cut): not just "no reply" but **"engaged-then-stalled"** — brochure OPENED not booked, quote CLICKED not signed, Mini-App/deal-room ENTERED not paid, inline-form STARTED not finished, demo NO-SHOW. Each emits a `comm_event`; a goal-scoped micro-journey fires the exact-right recovery (financing card for price-stall, 1-tap re-book for no-show, "complete your booking" deep-link for cart-abandon). | Recovers leads at **peak measured intent** — they already raised their hand. Far higher conversion than cold drip; the difference between a sender and a closer. |
| **7. Event-driven journeys** | A **`comm_event` bus** (one append-only table) is the universal entry point: `call.completed`, `lead.hot`, `message.delivered/read/clicked`, `brochure.opened`, `quote.signed`, `payment.paid`, `form.submitted`, `no_show`, `renewal.due`, `birthday`, `price.drop`, plus **time-cron events**. Any event can `enroll` / `advance` / `exit` any journey. This is the substrate — drip/re-engage/abandon are just journeys with different entry events. | Turns reactive blasting into a **behavioral operating system**: the right message fires the instant the right thing happens, on the cheapest channel, in-language. |

---

### 2. THE 99% — OUT-OF-BOX AUTOMATION PATTERNS THE FOUNDER DID NOT NAME (high-value picks, one-line why)

These ride the SAME runtime + event bus — each is a policy/template, not a new engine.

**Cadence intelligence**
- **A1. Goal-exit + frequency-cap + quiet-hours as GLOBAL journey law** — every touch re-checks goal-reached, per-contact daily cap, tenant quiet-hours, and global suppression BEFORE sending. *Why:* one guard layer protects sender reputation + spend across all seven automations; non-negotiable, near-zero cost.
- **A2. Adaptive cadence (spacing reacts to engagement)** — high engagement compresses the gap (strike while warm); silence stretches it then exits. *Why:* a fixed 24h drip wastes hot leads and annoys cold ones; reactive spacing lifts conversion at 0 cost.
- **A3. Cross-journey de-dup / "one conversation" lock** — a contact in an active journey is NOT enrolled into a conflicting one; a newer high-priority journey (hot-lead) **supersedes** a low-priority drip. *Why:* prevents the #1 omnichannel failure — five bots messaging one person; protects trust + the opt-out rate.

**Experimentation (beyond simple A/B)**
- **A4. Multi-armed bandit send-time + channel + copy** — Thompson-sampling allocation across variants AND channels AND send-slots simultaneously, not one axis. *Why:* finds the winning *combination* faster with less wasted send than sequential single-variable A/B.
- **A5. Holdout / "do-nothing" control group (true incrementality)** — a small % of enrollees get NO message; compare conversion to prove the automation actually *caused* lift, not correlation. *Why:* the honest ROI number the founder can take to a customer — "this drip drove +X% incremental bookings," not vanity opens.
- **A6. Auto-promote winner + auto-kill loser + roll the learning forward** — significant winner becomes the new default template; the learning seeds the NEXT campaign's starting variant. *Why:* the system compounds — every campaign starts smarter than the last.

**Recovery / re-engagement depth**
- **A7. Read-but-silent escalation (engagement-state, not time-only)** — Telegram/Email "seen", WA "read" + no reply on a HOT lead for X min => escalate to the founder ("they read it, didn't reply — nudge or call?"). *Why:* sharper than the time-only drip; catches the deal at the exact stall point.
- **A8. Chat-reopens-voice ("second-attempt callback")** — a hot reply to the post-call summary re-triggers an OUTBOUND voice call at the contact's stated good-time (firewall + DID gated). *Why:* text re-opens a closed voice deal — closes the chat->voice direction no point-tool owns; reuses the live earner *additively* (never edits agent.py).
- **A9. Negative-signal circuit-breaker** — STOP / annoyance / report on ANY channel instantly suppresses ALL channels for that contact AND flags the campaign if the suppress-rate spikes. *Why:* a reputation circuit-breaker that protects the tenant's sender asset proactively — losing a WA number / sending domain is catastrophic.

**Event-driven proactivity**
- **A10. Time-anchored lifecycle clock** — renewal-due, EMI-due, policy-expiry, warranty-end, birthday, festival, site-launch, price-drop-on-a-watched-item each auto-fire the right in-language message at the contact's best send-time. *Why:* converts the CRM from a record into a proactive revenue clock that earns while the founder sleeps.
- **A11. Stage-transition journeys (CRM is the trigger)** — moving a lead new->contacted->qualified->negotiating->won/lost each enrolls/exits the matching journey automatically. *Why:* the founder never manually starts a sequence; the pipeline drives the comms.
- **A12. Inventory/price/availability webhooks (tenant systems trigger comms)** — a tenant's "unit booked / slot freed / price cut" event reaches the watching leads first. *Why:* turns the tenant's own data into a real-time conversion trigger — sticky integration moat.

**Reliability / safety (the unglamorous engine that makes it trustworthy)**
- **A13. Idempotent, exactly-once send ledger** — `comm_event_id` + step key dedupes; a Hatchet retry/replay NEVER double-sends or double-charges. *Why:* the difference between a demo and a billion-dollar system — no duplicate messages, no double-debits, ever.
- **A14. Per-tenant + per-contact rate governor + spend stop-loss** — token-bucket per channel (respects Telegram 30 msg/s, WA quality tier, DLT windows) + a rupee ceiling per journey that PAUSES (not silently drops) on breach with a founder alert. *Why:* protects deliverability + caps autonomous spend — bounded, auditable, never a runaway.
- **A15. Dry-run / simulate / preview-the-journey** — render the full multi-touch sequence (who gets what, when, on which channel, projected cost) BEFORE a single real send. *Why:* the non-technical founder trusts what he can see; prevents the "blasted 4 a.m. SMS to 800 people" disaster.
- **A16. Dead-letter + auto-heal** — a failed send (token expired, DLT flagged, bot blocked) lands in a dead-letter queue, auto-retries with backoff on a different channel, surfaces to the health cockpit if unrecoverable. *Why:* failures are visible + self-healing, not silent revenue leaks.

---

### 3. THE HIGH-VALUE PICKS (build these — value x differentiation x feasibility x earner-safety)

> Selection: ship the ONE runtime + event bus first (unlocks all seven), then the automations with highest revenue-per-effort that ride 0-cost channels and need no Meta/DLT gate. Telegram-first; Email/SMS behind their compliance gates.

1. **The durable journey runtime + `comm_event` bus** (section 0/7) — *the keystone; every other automation is a template on it.* Build once. **[FOUNDATION]**
2. **Drip cadence with goal-exit + global guard law** (1.1 + A1) — *highest-ROI revenue lever, 0 cost on Telegram, pure node composition.* **[SHIP-FIRST]**
3. **Omnichannel fallback ladder with idempotent never-double-charge** (1.4 + A13) — *guaranteed reach at lowest cost; the channel-arbitrage margin = the sales story.* **[SHIP-FIRST]**
4. **Abandoned-flow / read-receipt recovery state-machine** (1.6 + A7) — *recovers leads at peak measured intent; the sharpest net-new cut, far beyond "no-reply" drip.* **[HIGH-VALUE]**
5. **A/B/n with auto-winner + holdout incrementality** (1.2 + A5/A6) — *self-optimizing comms + the honest ROI number for the customer.* **[HIGH-VALUE]**
6. **Smart send-time resolver (transparent heuristic)** (1.3 + A4) — *free lift on every send; protects reputation; explicitly NOT an ML service (anti-bloat).* **[QUICK-WIN]**
7. **Re-engagement + negative-signal circuit-breaker** (1.5 + A9) — *revives dead pipeline for 0 cost while proactively protecting the tenant's sender reputation.* **[HIGH-VALUE]**
8. **Time-anchored lifecycle clock + stage-transition journeys** (A10/A11) — *proactive revenue clock; pipeline drives comms with zero founder effort.* **[COMPOUNDING]**
9. **Dry-run/simulate + spend stop-loss + rate governor** (A15/A14) — *trust + safety for the non-technical founder; prevents the runaway-blast disaster.* **[GUARDRAIL — ship with #2]**
10. **Chat-reopens-voice second-attempt callback** (A8) — *text re-opens a closed voice deal; uniquely-Famit cross-channel loop, additive to the earner.* **[MOAT — sequence after Telegram proves out]**

### 4. WHAT I DELIBERATELY REJECT (anti-bloat — automation that grows a new engine)
- **A bespoke ML send-time/propensity service** — a transparent per-contact heuristic (A4/1.3) gives the lift at 0 infra; black-box ML is deferred bloat.
- **Seven separate schedulers** — ONE durable journey runtime drives all; a new automation is a seeded template row, never new orchestration code.
- **A second send-log / metrics store per automation** — every signal lives on the one channel-tagged `send_log` + `comm_event` bus; leaderboards/A-B/attribution are read-joins.
- **Fire-and-forget mass blaster (no goal-exit, no cap, no quiet-hours)** — violates A1; tanks deliverability + opt-out rate; every journey stays goal-gated + capped + consent-checked.
- **Auto-spend past a ceiling** — the rate governor + stop-loss (A14) PAUSE and alert; autonomous spend is always bounded + step-up-gated past threshold.

### 5. SECURITY / HONESTY POSTURE (inherited by every automation)
One money-path (`wallet`, idempotent, no-double-spend) · tenant-from-token never-body, FORCE-RLS on all `comm_*` tables · suppression + consent + quiet-hours + frequency-cap re-checked before EVERY touch (A1) · dormant-until-creds (no bot token / DLT / SPF => journey degrades to `not_configured`, never raises) · NEVER touches agent.py / the voice earner (rides `channel.send` + the new runtime + `_finalize_call`'s additive hook) · every number is a transparent heuristic with an honest empty state, never fabricated · Telegram (0 cost, no Meta gate) ships FIRST; Email/SMS follow behind SPF-DKIM / DLT gates.

### 6-LINE SUMMARY (for the orchestrator)
1. All seven named automations (drip · A/B · smart-send-time · fallback · re-engagement · abandoned-flow · event-journeys) are **ONE durable journey runtime + a `comm_event` bus**, not seven engines — a new automation is a seeded template row.
2. Each rides the channel registry (`channel.send`) + the SAME wallet/audit/RLS/firewall/suppression gates; flag-gated `COMM_AUTOMATION_ENABLED=OFF`; additive; NEVER agent.py.
3. **16 out-of-box patterns the founder didn't name** (A1-A16) — goal-exit/guard law, adaptive cadence, cross-journey de-dup, bandit + holdout incrementality, read-receipt recovery, chat-reopens-voice, negative-signal circuit-breaker, lifecycle clock, stage-transition triggers, idempotent exactly-once ledger, rate governor + stop-loss, dry-run simulate, dead-letter auto-heal.
4. **Top picks:** runtime+bus (foundation) -> drip+guard-law + idempotent fallback ladder (ship-first, 0 cost) -> abandoned-flow recovery + A/B-auto-winner-with-holdout + smart-send-time heuristic + re-engagement+circuit-breaker (high-value) -> lifecycle/stage journeys + dry-run/stop-loss guardrails -> chat-reopens-voice (moat).
5. **Rejected (anti-bloat):** ML send-time service, seven schedulers, a per-automation metrics store, fire-and-forget blaster, unbounded auto-spend.
6. **Honesty:** levers not guarantees; transparent heuristics with honest empty states (never fabricated); consent/suppression/quiet-hours/cap before every touch; idempotent no-double-charge; Telegram-first then Email/SMS behind compliance gates; the voice earner is untouched.

**END ootb-automation PHASE**

## PHASE: ootb-production — Production-Hardening Backbone (isolation+rate-limits · deliverability monitoring+bounce · unified inbox · omnichannel analytics · opt-in/out compliance · bot-token vault · audit)
**Date:** 2026-06-15
**Role:** the "99%" operational backbone the founder did NOT name — the seven systems that make the Communication tab a billion-dollar product instead of a demo. Each pick is grounded in a REAL Famit seam (so it is earner-safe + cheap to build) and EXCEEDS the WhatsApp system, not just mirrors it.
**Verified 2026 sources:** AWS SES tenant-level suppression + global suppression list (14-day, only hard bounces); Gmail/Yahoo/Microsoft thresholds (Nov-2025: bounce >2% -> permanent 5xx; complaint >0.3% -> enforcement, target <0.1%); GitGuardian Telegram-token remediation + BotFather /revoke + getUpdates-offset-reset gotcha; token-bucket per-tenant fairness + WFQ + jitter (Medium/STOA/Neon 2026). Full URLs in SOURCES below.

> THE FILTER (PLAYBOOK discipline): every system here is ADDITIVE, FORCE-RLS, COMM_ENABLED-gated (resting byte-identical, dormant=404/no-op), rides caller.py + the existing box Redis(:6380)/Postgres/wallet/audit/firewall — NEVER imports agent.py, NEVER on the voice loop. Reuse > invent. Where a Famit primitive already does the job, we point to it; we add exactly the missing layer.

---

### 1. PER-TENANT ISOLATION + RATE-LIMITS — the noisy-neighbour firewall (WHICH + WHY)
The single most important production system: one tenant's blast must never burn another tenant's deliverability, budget, or the shared Telegram bot rate ceiling. Picks:

- **[PICK] Per-tenant token-bucket on EVERY outbound send (Redis Lua, atomic).** Reuse the box's existing `ratelimit.py` Redis(:6380); add buckets keyed `comm:rl:{tenant}:{channel}`. Token bucket = constant-time, natural burst control, the verified production choice. *Why:* stops a 50k-row campaign from starving a real-time hot-lead alert or another tenant's drip — the noisy-neighbour problem, solved at the gateway before it hits any provider.
- **[PICK] Weighted Fair Queuing by plan tier (Starter < Growth < Enterprise weights).** The outbound dispatcher drains a per-tenant queue proportional to plan weight; nobody is fully starved. *Why:* turns "fairness" into a SELLABLE feature — Enterprise literally buys throughput headroom; ties straight into the existing 3-tier pricing.
- **[PICK] Jittered exponential backoff on every 429/5xx retry.** Randomized retry delay. *Why:* without jitter, all throttled tenants retry in lockstep and re-hit the limit simultaneously (synchronization storm) — verified 2026 failure mode. One line, prevents a self-inflicted DDoS.
- **[PICK] Respect Telegram's hard ceilings as a platform-wide governor (30 msg/s global, ~1 msg/s per-chat, 20 msg/min per-group).** A shared global bucket above the per-tenant buckets. *Why:* a single tenant's burst can get the SHARED platform bot IP flood-limited by Telegram, harming everyone — this is the multi-tenant version of the deliverability blast, and it is free to prevent.
- **[PICK] Per-tenant daily/monthly send QUOTA + soft-warn at 80% (Retry-After hint) -> 100% hard-stop.** Surfaced in the panel. *Why:* protects the tenant's own reputation AND the wallet from runaway spend (a misconfigured loop), and the 80% warning is a natural upsell trigger.
- **[PICK] Isolation is structural, not query-discipline: FORCE-RLS + admin-GUC `SET app.tenant_id` on ALL `communication_*` tables; single-tenant per request, NEVER `WHERE tenant_id IN (...)`.** Same pattern as wallet.py/provider_registry already live. *Why:* RLS is the only isolation that survives a code bug — app-level WHERE clauses leak (this exact class caused the P0-LEAK incident the founder lived through).

---

### 2. DELIVERABILITY MONITORING + BOUNCE/COMPLAINT HANDLING — the reputation circuit-breaker (WHICH + WHY)
Email/SMS reputation is a shared, fragile, expensive asset. In 2026 the rails (Gmail/Yahoo/MS) PERMANENTLY reject senders who cross thresholds. This is non-negotiable infrastructure, not a nicety. Picks:

- **[PICK] Per-tenant suppression list (one global list per tenant, channel-scoped sub-lists).** Mirror AWS SES tenant-level suppression: a bounce/complaint on tenant A NEVER suppresses tenant B's sends to the same address. *Why:* shared suppression cross-contaminates reputation between tenants and is a data-isolation leak (you would learn tenant A's contacts bounced for tenant B). The SES tenant model is the verified-correct answer.
- **[PICK] Hard-bounce -> permanent suppress immediately; soft-bounce -> retry <=3 with backoff then suppress.** Parse 4xx (temporary) vs 5xx (permanent) from the provider webhook. Microsoft explicitly names correct bounce-handling as a sender-hygiene signal. *Why:* re-sending to a dead address counts against your bounce rate and tanks the domain — the suppress-on-hard-bounce loop is THE thing that keeps you under 2%.
- **[PICK] Real-time reputation gates with circuit-breaker thresholds (verified 2026 numbers):** freeze a tenant's channel automatically when **bounce >2%** (Gmail/MS permanent-5xx line) or **complaint >0.3%** (enforcement line; alert at >0.1%). Reuse the provider-registry circuit-breaker pattern (3-strikes -> open -> exponential backoff). *Why:* a tenant crossing 2% is about to get the SHARED sending domain blacklisted — auto-freeze + alert is cheaper than a 2-week reputation rebuild. This is the deliverability analog of the rate-limit governor.
- **[PICK] Trend-aware, not snapshot.** Track the trajectory: 0.12% complaint flat = healthy; 0.12% climbing 10%/wk = freeze-soon. Daily rollup via the existing Hatchet cron. *Why:* the verified guidance is that the SLOPE predicts enforcement before the absolute number trips it — catch it early, keep the tenant sending.
- **[PICK] Webhook ingest for delivery events (bounce/complaint/delivered/opened) per provider -> normalize to `communication_messages.status` + an append-only `communication_delivery_events` leg.** Resend/SES/MSG91 all post async webhooks. *Why:* the status column is the funnel substrate for analytics AND the trigger for fallback (bounce -> escalate to next channel) AND the source of the suppression decision — one ingest feeds three systems.
- **[PICK] List-hygiene / spam-trap avoidance: pre-send MX/syntax validation on new emails; never message a never-engaged address after N sends.** *Why:* spam-trap hits are the fastest path to a blacklist and are 100% preventable at near-zero cost.
- **[PICK] Telegram has NO bounce concept — but a `403 bot blocked by user` IS the equivalent.** On 403 -> mark the contact's Telegram channel dead + opt-out + escalate to fallback. *Why:* without this you keep "successfully sending" into the void and the contact silently churns — the cross-channel fallback chain depends on detecting it.

---

### 3. THE UNIFIED INBOX — the daily-active surface (WHICH + WHY)
The single feature that makes the founder open Famit every morning and makes the product STICKY. It composes seams that already exist (the CRM transcript chat-view from the fixes-asset-preview-transcript wave + the unified-thread schema already designed). Picks:

- **[PICK] ONE timeline per contact: Telegram + Email + SMS + WhatsApp + voice-call transcripts interleaved chronologically, CUSTOMER right / AI-or-AGENT left (reuse the exact CRM chat-view already shipped to FORTRESS).** Backed by `communication_conversations` + `communication_messages` (channel column) — the Chatwoot/Twilio "channel equality" model, verified-converged. *Why:* "omnichannel" tools that keep per-channel silos are faking it; the lead who starts on SMS, jumps to Telegram, then emails is THREE records everywhere else and ONE here — that is the demo that closes.
- **[PICK] Cross-channel identity resolution / contact-merge (ContactInbox pattern): same phone on SMS+WA -> one contact + one thread; per-channel `source_id` (telegram chat_id / email / phone).** *Why:* without merge the "one thread" promise breaks the moment a contact uses two channels — identity resolution IS the unified inbox.
- **[PICK] One-tap HUMAN TAKEOVER that silences the AI for N hours on that contact (across ALL channels), with a visible banner + auto-resume.** *Why:* the founder must be able to jump in on a hot lead without the bot talking over him; this is the trust feature that lets him actually rely on the AI for the cold 95% — and it is a one-flag pause, not a new engine.
- **[PICK] Reply/compose from the inbox on ANY channel (the outbound router picks the adapter); quick-replies, send-banner/PDF/video inline.** *Why:* a read-only inbox is a report; a read-write inbox is the workspace — and it reuses the same send adapters the automation uses.
- **[PICK] Live updates (SSE/websocket) + unread badges + per-tenant team assignment.** *Why:* the "live morning cockpit" feel; assignment makes it usable by a tenant with a small team (multi-seat = more revenue).
- **[PICK] Inbox respects RLS + the consent/suppression state inline (a suppressed contact shows "opted out", compose disabled).** *Why:* the human operator must not be able to manually violate opt-out — compliance has to be enforced at the surface, not just the automation.

---

### 4. OMNICHANNEL ANALYTICS — open/reply/conversion per channel (WHICH + WHY)
The proof-of-ROI layer that makes the tab renewable and upgradeable. Mirror the WA delivery-analytics model (`wa_campaign_*`, per template x creative x audience) and generalize it across channels. Picks:

- **[PICK] Per-channel funnel state-machine on each send row: queued -> sent -> delivered -> opened/read -> clicked -> replied -> converted (+ bounced/failed/opted-out terminal states).** Driven by the webhook-ingest from §2. *Why:* one normalized funnel across TG/Email/SMS/WA is the only honest way to compare channels — and it is the same state-machine the WA spec already designed, just channel-keyed.
- **[PICK] The cross-channel COMPARISON view: cost-per-reply and cost-per-conversion PER CHANNEL, so the tenant sees "Telegram converts at 1/8th the cost of SMS."** *Why:* this is the value-metric that drives routing decisions AND the sales story (channel-mix optimization no point-tool can show because they own one channel).
- **[PICK] Attribution to REVENUE, not vanity opens: tie `converted` back to the booking/wallet/CRM outcome, honest attribution boundary (last-touch within the conversation window).** *Why:* opens are theater; "this channel booked Rs X of appointments" is the renewal argument — and it closes the same Ad->Call->WhatsApp->Book->Sale loop that is the company's moat.
- **[PICK] Best-send-time + best-channel-per-contact learning (continuous, from the engagement history).** *Why:* turns analytics from a dashboard into an action — the router uses it; verified to lift reply rates and it is a differentiator vs. static schedulers.
- **[PICK] Deliverability/reputation dashboard PER tenant PER channel (bounce%, complaint%, opt-out%, quality trend) — the monitoring from §2, surfaced.** *Why:* the founder's standing rule = every backend capability ships a frontend; the tenant must SEE their reputation health before it trips a freeze.
- **[PICK] Honest attribution boundary stated in-UI; no fabricated metrics.** *Why:* the founder's hard rule — show real artifacts, never invent numbers; analytics that lie destroy trust and the sales credibility.

---

### 5. OPT-IN / OPT-OUT + COMPLIANCE ENGINE — sold as TRUST, not a chore (WHICH + WHY)
For Indian SMBs, "keep me on the right side of TRAI/Meta automatically" is a FEAR-REVERSAL selling point (the #1 stall is fear-of-change, not price). Build it as a feature. Picks:

- **[PICK] Per-channel consent ledger `communication_consents` (tenant, contact, channel, opted_in, source, ts, opt_out_reason) — opt-out is per-channel by default + a GLOBAL suppress option.** WhatsApp STOP suppresses WA only; email unsubscribe suppresses email only; a global STOP kills all. *Why:* the law differs per channel (DLT vs CAN-SPAM vs Meta) and per-channel opt-out is the verified-correct granularity; one ledger, honored in <1 turn everywhere.
- **[PICK] NEGATIVE-SIGNAL auto-suppress / reputation circuit-breaker (net-new, no prior phase named at the contact level): if a contact replies STOP / annoyance / reports the bot on ANY channel -> instantly suppress ALL channels for that contact AND flag the campaign if suppress-rate spikes.** *Why:* protects the TENANT's sender reputation proactively, not just reactively per-channel — a reputation breaker, the anti-churn analog of the deliverability freeze.
- **[PICK] DLT assistant for SMS (India): hard gate — block send (UI AND backend) if `dlt_pe_id` or `dlt_template_id` is NULL; guided registration wizard.** *Why:* unregistered A2P SMS is simply blocked by carriers — the gate must be in the API not just the UI (a savvy tenant bypasses the UI otherwise).
- **[PICK] SPF/DKIM/DMARC setup WIZARD for email (per-tenant DKIM selector; BYO-domain with `noreply@mail.famit.in` fallback while verifying).** DMARC p=quarantine min, enforced since May-2025. *Why:* deliverability is gated on auth in 2026; a wizard turns a scary DNS task into clicks for a non-technical founder/tenant — and BYO-domain isolates reputation per tenant.
- **[PICK] Telegram deep-link opt-in (`t.me/{bot}?start=connect_{tenant}_{token}`) as the consent capture — no Meta verification, no DLT.** *Why:* the one channel with frictionless, instant, compliant opt-in — the wedge that gets a tenant live in minutes.
- **[PICK] Quiet-hours + frequency-cap per tenant/contact (no messages 9pm-9am, max N/day).** *Why:* over-messaging is the #1 cause of STOP/complaints — capping it protects reputation AND is a humane default the buyer trusts.
- **[PICK] DPDP-2023 built-in from day 1: consent gate on every send; right-to-be-forgotten = DELETE-cascade on contact identity (sessions/memory/send_log) leaving an audit TOMBSTONE with no content; retention prune at 90d (configurable) via Hatchet cron.** *Why:* retrofitting privacy is expensive and risky; building it in is near-free and is itself a sellable enterprise checkbox.

---

### 6. THE BOT-TOKEN / CREDENTIAL VAULT — the white-label margin printer + lock-in (WHICH + WHY)
The technical enabler of "Bring Your Own Bot/Domain/Sender-ID" (Enterprise premium, COGS DROPS to the tenant's rails) AND the security spine. Direct clone of the already-designed `provider_credentials` vault. Picks:

- **[PICK] `communication_channel_credentials`: AES-256-GCM at rest, AAD = `tenant_id||channel_type||version` (MANDATORY), FORCE-RLS, resolved ONLY through the `get_secret()` seam (Vault-ready, flips by `VAULT_BACKEND`).** Same as provider_registry, already proven on the box. *Why:* AAD-binding means copying one tenant's ciphertext into another tenant's row throws `InvalidTag` — cross-tenant credential theft is cryptographically impossible, not just RLS-blocked. Belt AND suspenders.
- **[PICK] Tokens NEVER appear in business logic or logs — only the adapter reads them from the vault; masked display only (`...AB12`); reveal is PIN/firewall step-up + audited.** Reuse firewall.py PIN step-up. *Why:* the verified #1 Telegram-token leak vector is LOGS (CVE-2026-27003 was exactly token-in-logs) and screenshots — never-log + masked-only kills both.
- **[PICK] Telegram `setWebhook` `secret_token` (server validates `X-Telegram-Bot-Api-Secret-Token` on every inbound) as defense-in-depth.** *Why:* even if the webhook URL leaks, forged updates are rejected — and it is a free Telegram-native field.
- **[PICK] One-click ROTATE / REVOKE in the panel — AND handle the getUpdates-offset gotcha: on token change, CLEAR the stored update offset.** Verified 2026 footgun: after BotFather /revoke the new token starts a fresh message_id sequence; a stale offset makes the bot silently deaf to all new messages. *Why:* a rotate that bricks the bot is worse than no rotate — this single line is the difference between a working and a mysteriously-dead bot after a security event.
- **[PICK] Per-tenant credential = per-tenant rate-limit reputation + per-tenant COGS.** BYO-bot/domain/sender-id -> their rails, their reputation, their compliance liability, OUR premium. *Why:* the lock-in moat: once 3 channels + history + automations live behind our brain, ripping it out = rebuilding the whole loop; and our margin goes UP on the highest tier while COGS goes DOWN.
- **[PICK] Scoped reveal: a vendor can paste/rotate THEIR OWN key but can never reveal/rotate a PLATFORM key.** *Why:* same least-privilege split the provider-registry already enforces — the platform's shared bot token is the crown jewel.

---

### 7. AUDIT — immutable, append-only, the trust + forensics spine (WHICH + WHY)
The control-plane is the sharpest knife; every send, consent change, credential reveal, and human-takeover must be provable after the fact. Reuse the live immutable `events` PG leg (NOT JSONL) from audit.py. Picks:

- **[PICK] Append-only `communication_messages` + `communication_delivery_events` (trigger blocks UPDATE/DELETE) — the message history is itself tamper-evident.** *Why:* a deliverability dispute (Meta/TRAI asks "prove the consent + the content") needs an immutable record; mutable rows are worthless as evidence.
- **[PICK] Every privileged/compliance action -> the immutable PG `events` leg: consent grant/revoke, credential reveal/rotate, human-takeover enter/exit, freeze/unfreeze, override-send.** Reuse audit.py. *Why:* these are the actions an attacker or a careless operator abuses; an un-droppable audit is the only deterrent + the only forensics after an incident.
- **[PICK] PII-minimized audit: log the ACTION + ids, not the message body, in the events leg (the body lives once in the RLS'd messages table).** *Why:* the audit log is a high-value breach target; logging bodies twice doubles the blast radius — log "sent template X to contact Y", not the content.
- **[PICK] Right-to-be-forgotten leaves a content-less TOMBSTONE in audit.** *Why:* DPDP requires you CAN prove you deleted, which itself must survive the deletion — the tombstone is the reconciliation of "forget the data" with "keep the proof".

---

### THE TOP-7 PRODUCTION PICKS (if the founder reads ONE line each — highest leverage, all earner-safe, all reuse a live seam)
1. **Per-tenant token-bucket + plan-weighted fairness + Telegram global governor** (reuse ratelimit.py Redis) — stops noisy-neighbour blast + sells throughput per tier.
2. **Per-tenant suppression list + auto-freeze at bounce>2%/complaint>0.3%** (reuse provider-registry circuit-breaker) — keeps the shared sending domain off blacklists; verified 2026 thresholds.
3. **The Unified Inbox** (reuse the shipped CRM transcript chat-view + unified-thread schema) — the daily-active, sticky, demo-closing surface; one timeline, all channels, one-tap human takeover.
4. **Omnichannel analytics tied to REVENUE per channel** (clone wa_campaign_* funnel) — honest cost-per-conversion-per-channel = the renewal + upsell argument + the loop moat.
5. **Per-channel consent ledger + negative-signal auto-suppress + DLT/SPF wizards** — compliance sold as fear-reversal TRUST; the #1 Indian-SMB stall, neutralized.
6. **AES-256-GCM AAD-bound bot-token vault + ROTATE-with-offset-reset + never-log** (clone provider_credentials) — enables BYO-bot Enterprise margin + lock-in; kills the verified token-leak vectors.
7. **Immutable append-only audit (PG events leg) for every send/consent/reveal/takeover** (reuse audit.py) — the forensics + dispute-proof spine; PII-minimized.

### COST POSTURE (this whole backbone)
Near-ZERO incremental infra: rides the existing box Redis(:6380), Postgres, wallet, audit, firewall, Hatchet cron. Telegram = $0. The only metered COGS is Email (Resend ~$0.0004 -> bill $0.001) + SMS (MSG91 Rs 0.18 -> bill Rs 0.25), both on the existing wallet ledger. The hardening systems themselves cost engineering time, not runtime money — and several (BYO-bot/domain, plan-weighted throughput, compliance-as-trust) are net REVENUE, not cost.

### SOURCES (this phase)
- [AWS SES tenant-level suppression + per-tenant reputation](https://docs.aws.amazon.com/ses/latest/dg/tenants.html)
- [AWS SES account-level suppression list (hard-bounce/complaint, 14-day)](https://docs.aws.amazon.com/ses/latest/dg/sending-email-suppression-list.html)
- [AWS SES global suppression list](https://docs.aws.amazon.com/ses/latest/dg/sending-email-global-suppression-list.html)
- [Spam Rate Threshold — every limit (2026)](https://prospeo.io/s/spam-rate-threshold)
- [Email deliverability benchmarks 2026 (bounce>2% -> permanent 5xx Nov-2025)](https://www.digitalapplied.com/blog/email-deliverability-benchmarks-2026-industry)
- [MailChannels multi-tenant email deliverability 2026 (policy engine / freeze-throttle)](https://www.mailchannels.com/multi-tenant-email-deliverability/)
- [Maileroo bounce + complaint handling (4xx vs 5xx)](https://maileroo.com/features/bounce-and-complaint)
- [GitGuardian — remediating Telegram bot-token leaks (/revoke)](https://www.gitguardian.com/remediation/telegram-bot-token)
- [CVE-2026-27003 — Telegram bot token exposure via logs](https://github.com/advisories/GHSA-chf7-jq6g-qrwv)
- [Telegram token rotation breaks getUpdates offset (stale-offset deafness)](https://github.com/openclaw/openclaw/issues/80653)
- [System Design — multi-tenant rate-limiting (token bucket + WFQ)](https://medium.com/@khalilsayed/system-design-multi-tenant-rate-limiting-service-32c63ade5ec7)
- [SaaS per-tenant rate limiting that scales (token bucket, 80%-warn/100%-stop)](https://docs.gostoa.dev/blog/saas-playbook-2-rate-limiting-saas)
- [Noisy-neighbour multitenant (jitter on retry / synchronization storm)](https://neon.com/blog/noisy-neighbor-multitenant)

---

**END ootb-production RESEARCH**


---

## PHASE: RED-TEAM [deliverability] — First-Contact, Inbox, Carrier Reach (2026-06-15)

READ-ONLY adversarial review of the omnichannel design's reach claims. Verdict up front: **the design is honest about the three gates (Telegram /start, email SPF/DKIM, SMS DLT) but it under-builds the SOLUTIONS to two of them, and it ships one silent-failure class that will make the founder think a channel "works" when zero contacts are reachable.** Eight concrete failures below, each with the fix it demands. Fixes are folded as REQUIREMENTS the build waves must satisfy — not optional.

---

### D1 — TELEGRAM FIRST-CONTACT IS THE WHOLE BALLGAME, AND THE DESIGN HAND-WAVES IT

**The failure.** Every arch brief correctly states "the contact bot cannot cold-message a user who never tapped /start" (CONFIRMED, log section 3.5/11/H). Then every brief solves it the same way: "the deep link t.me/{bot}?start= is delivered first via WA/SMS." Read that again. **The unblocked, free, zero-approval flagship channel depends on the two BLOCKED/METERED channels to bootstrap itself.** On day 1 the tenant has: no WA template approved (GAP-C1, Meta review pending), no DLT (5-10 day gate). So the deep link has **no delivery vehicle**. Telegram's "ship day 1, free, instant" promise is false for any NEW contact — it only works for contacts who *already* tapped /start, which on day 1 is zero. The hot-lead FOUNDER alert works (founder pre-started), but the contact-facing leg — post-call summary, the conversation brain, the entire "contact chats with the AI" feature — is dark until a bootstrap channel exists.

**Worse:** the brief assumes the deep link goes in "the WA/SMS follow-up." But the in-call voice agent is the ONE channel that reaches 100% of contacts on day 1 with zero gate. The deep link is never offered as a SPOKEN/voice-delivered artifact. A contact who just had a 3-minute call is the single highest-intent moment to say "I'm texting you a link to chat with me on Telegram" — and the design routes around the only un-gated touchpoint it owns.

**Fix it demands (mandatory):**
1. **Voice-prompted + live-channel bootstrap, ranked.** The deep-link onboarding ladder MUST pick a channel that is ACTUALLY live for that tenant: (a) if WA 24h window is open (contact messaged) -> free WA text with the link, (b) else email IF an email-consent was captured in-conversation (see D4), (c) else SMS — but only once DLT is live (SMS needs DLT too; see D5). If NONE is live, the panel must show the tenant a hard banner: "Telegram cannot reach new contacts until you connect a bootstrap channel (WhatsApp or Email)." Today the design silently emits a deep link into a channel that returns not_configured and the contact is never reached.
2. **QR + short-link on EVERY existing surface** — the panel must mint a t.me/{bot}?start= QR for the tenant to put on their website, invoice, WhatsApp bio, Google Business profile, physical store. First-contact is an onboarding-funnel problem, not a per-call problem; the design treats it only per-call.
3. **Measure it.** A comm_onboarding_funnel metric (links_sent -> links_tapped -> /start_received -> first_reply). Without this the founder cannot see that 0% of contacts onboarded. The design has no first-contact conversion instrument — it assumes the funnel works.

**Honest residual:** even with all three, Telegram contact-reach in India is structurally lower than WhatsApp (penetration + the /start friction). Telegram's real day-1 value is the **founder alert** (un-gated) and **inbound-initiated** chats (contact taps a link THEY found). The "auto-message every contact after a call on Telegram" framing oversells it. Position Telegram honestly: founder-alert + opt-in-funnel channel, NOT a cold-outreach channel.

---

### D2 — THE SILENT-SKIP IS A LIE-TO-THE-FOUNDER FAILURE MODE

**The failure.** Log section 8 and every cost-router brief: *"Telegram bot started — Skip silently (not an error; contact hasn't onboarded bot)."* And the cost-router waterfall "returns the first enabled+consented+capable channel." Combine D1 + this: on day 1, Telegram skips (no chat_id), WA skips (no template/no window), email skips (no domain verified), SMS skips (no DLT). **The cost-router walks the entire ladder, every rung skips, and the post-call summary is sent on ZERO channels — silently, with a 0-paise wallet row that looks like success.** The founder sees "post-call follow-up: enabled" in the UI and believes contacts are being messaged. They are not. This is exactly the "green per-component report masked a broken live product" failure the founder's #1 standing rule warns about.

**Fix it demands (mandatory):**
1. **A waterfall that exhausts to a LOUD state, never a silent 0-paise.** dispatch() MUST return a terminal {ok:false, status:"no_reachable_channel", attempted:[...]} when every rung skips, write it to comm_send_log with a distinct status, and surface it in the Delivery UI as a RED "0 contacts reachable — connect a channel" banner, not a calm empty state. The Dormant<T> "calm empty state" pattern (arch-ui section 5) is correct for *not-yet-built*, but DEADLY for *built-but-nothing-delivered*. These two states must be visually different.
2. **A pre-launch reachability preflight.** Before a campaign/journey launches, the Audience step (arch-ui builder) must compute and SHOW: "of 500 contacts, 0 reachable on any enabled channel" — and BLOCK launch (or force an explicit "send anyway / I understand 0 will be delivered" confirm). The design has consent filters in the Audience step but no *reachability* filter. Reachability != consent: a consented contact with no chat_id/no verified-domain/no DLT is still unreachable.
3. **Per-channel "is this channel actually able to deliver RIGHT NOW" health, surfaced.** Not "enabled" (a toggle) but "deliverable" (chat_id exists / domain verified / DLT present / template approved). The channel-setup page (arch-ui section 9) shows config state; it must also show *live deliverability* state with the blocking reason.

---

### D3 — EMAIL: "DOMAIN VERIFIED" != "LANDS IN INBOX." THE DESIGN STOPS AT THE WRONG GATE.

**The failure.** The design's email gate is binary: domain_verified=true -> send allowed. SPF+DKIM+DMARC passing is **necessary but nowhere near sufficient** for inbox placement in 2026. The log itself ranks Resend at only **72/100 Internet.nl** and notes Google/Yahoo/Microsoft enforce for bulk senders. What the design omits entirely:
- **Cold-start / IP+domain reputation warmup.** A freshly verified tenant domain sending 500 post-call emails on day 1 from Resend's shared pool gets throttled or spam-foldered. There is no warmup ramp (start ~50/day, double daily). The design sends at full volume from a zero-reputation domain.
- **Gmail/Yahoo bulk-sender rules (Feb 2024, strictly enforced 2026):** one-click List-Unsubscribe (RFC 8058, the List-Unsubscribe-Post header — NOT just a footer link), spam-rate kept **under 0.10%** in Google Postmaster (0.30% = hard penalty), valid forward+reverse DNS. The design mentions a footer List-Unsubscribe and the >2%-bounce/>0.3%-complaint freeze — but **0.3% is already the Google penalty ceiling, not a safe operating point.** Freezing AT the ceiling means the tenant's domain is already burned by the time the breaker trips.
- **No Google Postmaster Tools / no seed-list inbox-placement test.** The design measures bounce/complaint (provider webhooks) but not **inbox vs spam placement** — the metric that actually matters. A 0%-bounce campaign can sit 100% in spam and every webhook says "delivered."
- **Shared-pool poisoning on Resend.** The log rejected Brevo for shared-IP poisoning but then picks Resend whose free/Pro tiers are ALSO a shared pool. One bad tenant on Resend's shared IPs degrades every Famit tenant. Per-domain DKIM isolates the d= signature but NOT the sending IP reputation at the lower tiers.

**Fix it demands (mandatory):**
1. **Reputation warmup ramp per tenant domain** — enforced in the router: cap daily volume per newly-verified domain, auto-escalate the cap on clean days. A domain_age_days + daily_cap in communication_channels. No full-volume send from a domain younger than ~14 days.
2. **The freeze threshold must be BELOW the penalty ceiling, with a WARN tier.** Complaint WARN at 0.10%, throttle at 0.20%, freeze at 0.30% — staged, not a single cliff at the ceiling. Same for bounce: WARN 1%, throttle 1.5%, freeze 2%.
3. **One-click List-Unsubscribe (RFC 8058) header on EVERY marketing email**, not a footer link — List-Unsubscribe: <https url>, <mailto> + List-Unsubscribe-Post: List-Unsubscribe=One-Click. This is a 2026 Gmail/Yahoo HARD requirement for bulk; missing it = spam-foldered regardless of DKIM.
4. **Inbox-placement instrumentation, not just delivery webhooks** — integrate Google Postmaster Tools (domain-level reputation/spam-rate read) and/or a seed-list test before any large send. Surface "inbox vs spam" placement, not just "accepted." Without this the founder cannot tell a working email channel from a 100%-spam channel.
5. **Dedicated-IP path for high-volume tenants** — the Resend shared pool is fine at launch volume but the design must name the migration trigger (a tenant >50K/mo or any tenant whose sends justify reputation isolation -> dedicated IP, which the SES fallback or Resend's dedicated-IP tier provides). The "Brevo poisons shared pool" rejection logic applies to Resend's lower tiers too; say so.

---

### D4 — EMAIL FIRST-CONTACT: WHERE DOES THE EMAIL ADDRESS COME FROM, AND IS IT CONSENTED?

**The failure.** The cost-router routes to email "if email present + consent + domain_verified." But a lead who was COLD-CALLED (the core Famit flow) gave their phone to an ad, not their email, and never opted into email. The design assumes an email address materializes with consent attached. For inbound/web leads it might; for the outbound-call flow (the earner) the contact typically has **no email on file and no email consent**. Sending a post-call summary to a scraped/appended email = CAN-SPAM/DPDP violation + spam complaints that poison D3's reputation. The design's consent ledger checks opted_in but never addresses **how email consent is captured in a voice-first flow.**

**Fix it demands:**
1. **Email is opt-in-captured-in-conversation, not assumed.** The voice agent / Telegram brain must explicitly ask "what's the best email for your summary?" and that capture writes comm_consent_log(channel='email', basis='service_explicit', wording=...). No email send without a capture event — appended/guessed emails are forbidden. Add an acceptance test: a contact with an email but NO email-consent row -> email leg SKIPPED (and the skip is loud per D2, not silent).
2. **Email is a SECOND-touch channel in the voice flow, not a default.** Reposition: for cold-call leads, the day-1 channels are WhatsApp (if number on WA) and the Telegram opt-in funnel; email enters only after explicit in-conversation capture. The design's cost-router puts email at rung 3 ahead of WA-template — fine on COST, wrong on CONSENT-REALITY for voice-origin leads.

---

### D5 — SMS: THE DLT GATE IS BUILT, BUT FOUR CARRIER-REJECTION CLASSES BEYOND "TEMPLATE NULL" ARE NOT

**The failure.** The design's SMS gate is block if sms_dlt_template_id IS NULL. Correct and necessary — but DLT-template-present is NOT delivery. The carrier rejects/drops SMS for FOUR more reasons the design doesn't gate or surface:
1. **Template content mismatch.** The sent message must match the registered template **character-for-character** in the fixed portions; only {#var#} slots vary, max 30 chars/var, max 5-6 vars (CONFIRMED log section H). If the LLM brain generates a 160-char summary that doesn't fit the registered template's fixed text + var slots, the carrier **silently drops it** (DND/template-mismatch DLR). The design's brain generates free-form SMS ("160-char GSM7 teaser") — that is fundamentally incompatible with DLT's fixed-template model. **You cannot free-form-generate a DLT SMS.** This is a hard architectural conflict the design has not reconciled.
2. **Header (sender ID) not bound / PE-TM binding missing** (log SMS step 5) — template approved but PE-TM unbound = blocked. Not gated.
3. **CTA URL not whitelisted** (log SMS step 4, mandatory since Oct 2024) — any link in the SMS (the branded go.famit.in short-link!) must be pre-whitelisted on the DLT portal. The design's "media -> branded short-link" pattern will get the SMS DROPPED if that short-link domain isn't DLT-whitelisted. **The cost-saving short-link mechanism directly triggers carrier rejection unless pre-registered.** Not gated.
4. **DLR-FAILED handling is incoherent.** Log section 7 says "if SMS FAILED within 60s, escalate to next cheaper channel" — but there is no cheaper channel than SMS (it's the last rung). Escalating "to email" after SMS fails contradicts the waterfall (email was rung 3, already tried/skipped). The failure path loops back to an already-skipped channel.

**Fix it demands (mandatory):**
1. **The SMS brain does NOT free-generate. It fills the registered DLT template.** comm_template_content.sms_dlt_body is the fixed string with {#var#} slots; the LLM only produces the VARIABLE VALUES (<=30 chars each), and a validator asserts the assembled message matches the registered template before send. Any send whose body deviates from an approved template -> blocked_dlt_mismatch. This is a different generation contract than Telegram/email and must be built as such.
2. **The DLT gate is a COMPOSITE of all 5 registration artifacts**, not just template_id: block unless dlt_pe_id AND dlt_template_id AND sms_sender_id AND pe_tm_bound AND all_cta_urls_whitelisted are present. Add dlt_pe_tm_bound BOOL and a dlt_whitelisted_urls TEXT[] to the schema; the gate checks the short-link domain is in it.
3. **Short-link domain pre-whitelisting is a setup step**, surfaced in the DLT wizard: "add go.famit.in to your DLT CTA whitelist" — else every SMS with a link is dropped. The design sells the short-link as a feature; it's a carrier-rejection trigger without this step.
4. **DLR-driven state, not blind escalation.** On a FAILED DLR, do NOT re-escalate to an already-tried channel; mark the contact sms_undeliverable, write a loud comm_send_log row, and (if a bootstrap channel exists) retry the Telegram-opt-in funnel — never a silent 0-paise success.

---

### D6 — "DELIVERABLE" vs "DELIVERED" vs "READ" IS CONFLATED ACROSS THE WHOLE DESIGN

**The failure.** arch-automation section 3 admits "Deliverable != delivered" for the ladder-stop, but the rest of the design (cost-router, send-log, founder dashboards, the "X-rupees saved vs SMS-only" ticker) treats a synchronous accepted as success. For all four channels the **truth arrives later via DLR/webhook**, and for three of them the gap between accepted and delivered is where reach dies:
- Telegram sendMessage 200 = queued, but if the user **blocked the bot** after /start, you get a 403 "bot was blocked by the user" — async, not at send. Not handled.
- Email accepted by Resend != inbox (D3). The "delivered" webhook != "inbox" (could be spam folder, which Gmail reports as delivered).
- SMS provider accepted != carrier DELIVERED != handset (DLR can be DELIVERED-to-operator but never handset).

**Fix it demands:** the comm_send_log.status state machine must be **explicitly 4-state per channel** (accepted -> sent -> delivered -> read/failed), driven by each channel's DLR/webhook, and the dashboards + savings ticker must compute on delivered (or read where available), NEVER on accepted. The "X saved" claim built on accepted counts is vanity; built on delivered it's truth. Add the Telegram 403-blocked async handler -> flip the contact's chat_id to revoked + write consent opt-out.

---

### D7 — RATE LIMITS + BURST = THROTTLED REACH AT EXACTLY THE WRONG TIME

**The failure.** Telegram: 30 msg/s global, **1 msg/s per chat** (log section 7). Email: provider per-minute caps (SendGrid 600/min free; Resend "no hard limit" really means soft reputation throttle). SMS: carrier TPS caps. A campaign blast or a wave of simultaneous call-completions (the founder's growth scenario) will hit these. The design's only rate-limit handling is "on 429 read retry_after, backoff" (Telegram) — reactive, per-message. A 5,000-contact post-call batch firing through one tenant bot at 30 msg/s = 167s minimum, and the per-chat 1/s is irrelevant for distinct contacts but the GLOBAL 30/s throttles the whole tenant. No proactive token-bucket / queue-pacing.

**Fix it demands:** a per-tenant per-channel **outbound rate-governor (token bucket)** in front of every adapter, sized to each channel's documented limit, with the durable Hatchet queue (already chosen for journeys) pacing the batch — not a reactive 429 retry. Surface "estimated delivery time for this batch" in the UI so the founder knows a 5K blast takes minutes, not instant.

---

### D8 — NO END-TO-END REACH PROOF IN THE ACCEPTANCE GATES

**The failure.** Every arch brief's acceptance gate proves *offline* correctness (RLS, AAD, byte-identical resting, cost-router unit order) and *earner safety* (agent.py md5, 0 5xx). NOT ONE gate proves a real message reached a real handset/inbox/chat. The integrated soak proves "voice loop adds 0ms, 0 5xx" — i.e. it proves the comm system didn't BREAK anything, never that it DELIVERS anything. Per the founder's #1 rule ("a green per-component report != a working product; only the founder's real call/WhatsApp is truth"), the entire design can pass every listed acceptance check while delivering zero messages to zero contacts (see D1/D2).

**Fix it demands (mandatory, non-negotiable):** add a **REAL-REACH acceptance gate per channel**, run by the founder on a real device, before the channel is called "shipped":
- Telegram: founder taps a real deep link on a real phone -> /start -> receives a real post-call summary in the real Telegram app. (Founder-alert: founder receives a real hot-lead alert on their real phone.)
- Email: a real send lands in a real Gmail + Outlook INBOX (not spam) — verified by opening the actual inbox, plus the Postmaster spam-rate read.
- SMS: a real DLT-registered template send arrives on a real Indian handset with the correct sender ID.
This is the only gate that matters and it is currently absent. Every other gate is necessary-not-sufficient.

---

### SUMMARY — THE FIXES THE BUILD MUST CARRY (deliverability red-team verdict)

| # | Failure | Mandatory fix |
|---|---|---|
| D1 | Telegram contact-reach is 0 on day 1 (no bootstrap channel) | Ranked live-channel (WA/email/SMS) bootstrap ladder + QR/short-link on every owned surface + onboarding-funnel metric. Position TG as founder-alert + opt-in funnel, NOT cold outreach. |
| D2 | Cost-router exhausts to a SILENT 0-paise "success" | Loud no_reachable_channel terminal state; pre-launch reachability preflight that BLOCKS; "deliverable now" health (not just "enabled"). |
| D3 | "Domain verified" != inbox placement | Per-domain reputation warmup ramp; staged complaint/bounce thresholds BELOW the Google ceiling; RFC 8058 one-click List-Unsubscribe header; Postmaster/seed-list inbox-placement instrumentation; dedicated-IP migration trigger. |
| D4 | Email consent is ASSUMED in a voice-first flow | Email opt-in captured in-conversation only; no send without a consent-capture event; reposition email as second-touch for cold-call leads. |
| D5 | SMS: only "template null" gated; 4 more carrier-rejection classes ignored; free-gen conflicts with DLT fixed-template | Brain fills the registered template (var-values only, validated to match); composite DLT gate (PE+template+sender+PE-TM-bound+CTA-whitelisted); short-link domain DLT-whitelisting as a setup step; DLR-driven (not blind) escalation. |
| D6 | accepted/delivered/read conflated; savings ticker built on accepted | Explicit 4-state per-channel DLR-driven status; dashboards + savings on delivered/read only; Telegram 403-blocked async handler. |
| D7 | Rate-limit handling is reactive 429-only | Proactive per-tenant per-channel token-bucket governor + Hatchet-paced batch + "est. delivery time" surfaced. |
| D8 | No acceptance gate proves a real message reached anyone | REAL-REACH founder-device gate per channel (TG to real app, email to real INBOX not spam, SMS to real Indian handset) before "shipped." |

**One-line honest verdict:** the architecture is sound and reuse-correct, but it is built to prove it doesn't BREAK the earner, not that it REACHES the customer. The reach gates (Telegram /start, email inbox-placement, SMS DLT-match) are each one layer deeper than the design currently builds — and the cost-router's silent-skip turns all three gaps into an invisible "everything's green, nobody got the message" failure, which is precisely the founder's #1 nightmare. Ship Telegram founder-alert first (the one genuinely un-gated, real-reach-provable path); gate every contact-facing channel behind D2's loud-reachability + D8's real-device proof.

**END RED-TEAM [deliverability] RESEARCH**

---
