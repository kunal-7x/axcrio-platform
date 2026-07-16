# Famit — Where We Are, and What I Need From You

**Plain-English founder brief. No jargon. Read top to bottom — it takes 5 minutes.**

Last updated: 2026-06-10 · Live product: https://panel.famit.in

---

## The one-paragraph truth

Your platform is **real and live**, not a demo. The AI calling engine, the leads, the
call logs, the campaigns, the billing meter that tracks exactly what each vendor costs
you — all of it runs on **real data** right now (96 real calls, 8 real campaigns, real
vendor costs of about ₹68 this month). The "it all looks like a dummy" feeling comes
from two harmless things: (1) some screens look empty simply because there's nothing in
them yet (e.g. no callbacks scheduled), and (2) a batch of **newer features is switched
OFF** waiting for me to flip them on or for you to hand me a few accounts. **Nothing is
fake.** The foundation — secure database, each customer's data walled off from every
other customer, the billing meter, and the live voice-calling engine — is **done**.

To make the *entire* platform run on real data and be sellable, I need a short list of
accounts/keys from you. They're all in **Section 2**, ordered by how much they unlock.

---

# SECTION 1 — STATUS (where we are)

### The foundation is DONE and real

| Foundation piece | State | What it means for you |
|---|---|---|
| Secure database (Postgres) | **DONE** | All real data lives here, backed up and live. |
| Multi-customer isolation | **DONE** | Each customer (tenant) only ever sees their own data. Safe to sell to many businesses. |
| Security hardening | **DONE** | Servers are locked down, firewalled, alerting on intrusions. |
| Real billing meter | **DONE** | We measure the *actual* cost of every call per vendor (voice, AI, telephony) — not estimates. |
| Live AI voice-calling engine | **DONE** | The thing you already trust ("Run a Campaign") — it really dials, talks, and logs outcomes. |

### Every feature — at a glance

**Legend:** ✅ WORKS NOW (real data, live) · 🟡 TURNING ON NOW (I flip a switch, no account, no money) · 🔑 WAITING ON YOU (needs one account/key from you — see Section 2) · 🗺️ PLANNED (roadmap, intentionally not built yet)

| Feature | Status | Notes |
|---|---|---|
| Dashboard | ✅ WORKS NOW | Real totals: 96 calls, 38 answered, 8 campaigns. |
| Campaigns | ✅ WORKS NOW | 8 real campaigns (e.g. "Codename Joy 3.0"), real AI voices. |
| Run a Campaign | ✅ WORKS NOW | The live dialer you already use. |
| Leads | ✅ WORKS NOW | Real leads with scores (e.g. "Aarav", score 100, hot). |
| Call Logs | ✅ WORKS NOW | Real call rows with outcome and interest level. |
| Callbacks | ✅ WORKS NOW | Looks empty only because none are scheduled yet. |
| Do-Not-Call / Suppression | ✅ WORKS NOW | Real suppressed numbers, compliance-ready. |
| Webhooks | ✅ WORKS NOW | Empty until you add one — by design. |
| Analytics | ✅ WORKS NOW | Real funnel: 96 dialed → 84 connected → 18 qualified. |
| Vendors (admin) | ✅ WORKS NOW | Real tenant list. |
| Settings / Profile | ✅ WORKS NOW | Real admin account. |
| Billing — Overview | ✅ WORKS NOW | Real metered spend (₹68.31 this month). |
| Billing — Vendors | ✅ WORKS NOW | Real per-vendor cost (telephony, ElevenLabs, Groq, Sarvam, LiveKit). |
| Billing — Cost Explorer | ✅ WORKS NOW | Real per-call cost breakdown. |
| Billing — Audit | ✅ WORKS NOW | Our ledger vs. what vendors report — reconciled. |
| Billing — Plan & Ledger | ✅ WORKS NOW | Real plan and minute tracking. |
| Funnels | 🟡 TURNING ON NOW | No account needed. Runs on the live database. |
| Workflows (automation) | 🟡 TURNING ON NOW | No account needed. |
| Form Builder | 🟡 TURNING ON NOW | No account needed. |
| CRM (contacts) | 🟡 TURNING ON NOW | No account needed. Uses the live database. |
| Customer Support | 🟡 TURNING ON NOW | Works in basic mode now; smarter replies optionally need an AI key (Section 2 #7). |
| Booking | 🟡 TURNING ON NOW | Core booking works now; 2-way Google Calendar sync optional later. |
| AI Manager | 🟡 TURNING ON NOW | Dashboard works on flip; advanced phone features optional later. |
| **WhatsApp** | 🔑 WAITING ON YOU | Fully built and dormant. Needs Meta WhatsApp account → **Section 2 #1**. |
| **Ad Automation** | 🔑 WAITING ON YOU | Needs Meta or Google Ads account → **Section 2 #2 / #3**. |
| **Payments** | 🔑 WAITING ON YOU | Needs Razorpay or Stripe → **Section 2 #4**. |
| **Media-Gen (AI video/image)** | 🔑 WAITING ON YOU | Needs an AI media key + storage → **Section 2 #5 / #6**. |
| Create Studio (Script/Voice/Flow/A-B) | 🗺️ PLANNED | Shown as dimmed "Soon" pills on purpose. Not built yet. |

### What I do the moment you give me the green light (no accounts, no money)

I flip ~6 switches on the server and restart one service. That **immediately** turns on:
**Funnels, Workflows, Form Builder, CRM, Customer Support (basic), Booking (core), and
AI Manager** — all running on the database that's already live.

> ⚠️ One honest blocker on my side: this session I could **not** reach the backend
> server over SSH (its firewall is allow-listing only certain IPs and timed me out 5
> times). The flip itself is a 2-minute job — I just need to do it from an allow-listed
> machine or through the internal network path. This is a *me* task, not a *you* task;
> I'm flagging it so you know why "turning on now" hasn't already happened.

---

# SECTION 2 — WHAT I NEED FROM YOU

**This is the whole point of this file.** Each card below is one account or key. They are
ordered **by impact** — the first ones unlock the most. For each: what it is, what it
unlocks, why it's needed, **exact click-by-click steps** to get it, what to copy, and how
to send it to me safely.

### 🔒 How to send me ANY of these safely (read once)

- **Never** paste secret keys into a normal chat, email, or screenshot you post publicly.
- Best: put each value in a **private note** and share it with me directly in our working
  session, OR use a one-time secret link (go to **https://onetimesecret.com**, paste the
  value, click *Create a secret link*, send me the link — it self-destructs after I open it).
- Label each value with its name (e.g. "RAZORPAY_KEY_ID = ...") so I know where it goes.
- I paste them into the server's locked config file (`/opt/famit-agent/.env`) and restart
  the service. You never touch a terminal.

---

## 1. Meta WhatsApp Cloud API  — *highest impact*

**What it is:** Official WhatsApp business messaging from Meta (Facebook).
**Unlocks:** The **WhatsApp** feature — sending WhatsApp messages to leads/customers and
logging replies. The whole pipeline is already built and waiting; this is the only thing
missing.
**Why needed:** WhatsApp will not let any software send messages without an approved
business number and an approved message template. There is no way around this — it's
Meta's rule.

**Click-by-click:**
1. Go to **https://business.facebook.com** and sign in (create a free Meta Business
   account if you don't have one). Menu: **Business Settings**.
2. In the left menu, open **Accounts → WhatsApp Accounts → Add**. Follow the prompts to
   create a WhatsApp Business Account.
3. Go to **https://developers.facebook.com** → **My Apps → Create App** → choose
   **Business** → name it (e.g. "Famit"). Inside the app, click **Add Product** and add
   **WhatsApp**.
4. In the app's **WhatsApp → API Setup** screen you'll see:
   - a **Phone number ID** (a long number) — **copy it**.
   - a temporary token; for production we need a **permanent** one (next step).
5. Get a **permanent token:** Business Settings → **Users → System Users → Add** (create
   an "Admin" system user) → **Generate New Token** → select your app → tick the
   `whatsapp_business_messaging` and `whatsapp_business_management` permissions →
   **Generate**. **Copy this token** (you only see it once).
6. **Approve a message template:** in **WhatsApp Manager → Message Templates → Create
   Template** (pick a category like *Marketing* or *Utility*, write your message, submit).
   Approval usually takes minutes to a day. **Tell me the template name** once approved.

**Send me these 3 things:**
- `Phone number ID` = ……
- `WHATSAPP_TOKEN` (the permanent token) = ……
- `Template name` (approved) = ……

---

## 2. Meta Marketing / Ads API (+ ad account + business verification)

**What it is:** The same Meta Business account, but the part that lets software create and
manage Facebook/Instagram **ads**.
**Unlocks:** **Ad Automation** — auto-creating and managing ad campaigns from inside Famit.
**Why needed:** Meta requires an authorized app, an ad account, and a verified business
before any tool can spend ad money or read ad performance.

**Click-by-click:**
1. **https://business.facebook.com → Business Settings → Accounts → Ad Accounts.** If you
   don't have one, **Add → Create a New Ad Account** (set currency to INR, timezone India).
   **Copy the Ad Account ID** (looks like `act_1234567890`).
2. **Verify your business:** Business Settings → **Security Center → Start Verification**
   (you'll upload a business document — this unlocks higher ad limits and the API). This
   can take a few days, so start it early.
3. In your Meta **app** (from card #1, or create another at
   **https://developers.facebook.com → My Apps**), **Add Product → Marketing API.**
4. App **Settings → Basic**: copy the **App ID** and **App Secret**.
5. Generate an **access token** with ads permissions (Marketing API → Tools → Get Token,
   tick `ads_management`, `ads_read`, `business_management`).

**Send me these 4 things:**
- `META_ADS_ACCESS_TOKEN` = ……
- `META_ADS_ACCOUNT_ID` = …… (the `act_...` value)
- `META_ADS_APP_ID` = ……
- `META_ADS_APP_SECRET` = ……

*(You can do Meta OR Google Ads — see #3 — you don't need both. Meta is the common choice for India SMB.)*

---

## 3. Google Ads API (alternative to #2)

**What it is:** Google's version — manage Google Search/YouTube ads via software.
**Unlocks:** **Ad Automation** on Google instead of (or in addition to) Meta.
**Why needed:** Google requires a special "developer token" plus a login handshake (OAuth)
before any tool can touch your ad account.

**Click-by-click:**
1. Have a **Google Ads account** (https://ads.google.com). Note your **Customer ID**
   (top right, format `123-456-7890`).
2. Apply for a **developer token:** in Google Ads, **Tools & Settings → Setup → API
   Center** → request a token. (Starts in "test" mode; request "Basic access" for live use.)
3. Create OAuth credentials: **https://console.cloud.google.com → APIs & Services →
   Credentials → Create Credentials → OAuth client ID** (type: *Desktop* or *Web*). Copy
   the **Client ID** and **Client Secret**.
4. I'll help you do the one-time OAuth "allow" step to produce a **refresh token** (we do
   this together on a screen-share — it's a single click on a Google consent page).

**Send me these:**
- `GOOGLE_ADS_DEVELOPER_TOKEN` = ……
- `GOOGLE_ADS_CLIENT_ID` = ……
- `GOOGLE_ADS_CLIENT_SECRET` = ……
- `GOOGLE_ADS_CUSTOMER_ID` = …… (digits only, no dashes)
- (refresh token + login-customer-id — we generate together)

---

## 4. Payments — Razorpay (India) and/or Stripe

**What it is:** A payment gateway so the platform can charge customers / collect money.
**Unlocks:** The **Payments** feature (invoices, collecting subscription fees, etc.).
**Why needed:** To move real money you need a licensed gateway and its secret keys; we
also need a "webhook secret" so the gateway can securely tell us when a payment succeeds.

**Razorpay (recommended for India):**
1. Sign up at **https://razorpay.com** and complete KYC (business documents).
2. Dashboard → **Settings → API Keys → Generate Key.** Copy **Key ID** and **Key Secret**
   (the secret is shown once — save it).
3. Dashboard → **Settings → Webhooks → Add New Webhook.** I'll give you the exact URL to
   paste; you set a **secret** phrase there and send me the same phrase.

**Send me these:**
- `RAZORPAY_KEY_ID` = ……
- `RAZORPAY_KEY_SECRET` = ……
- `RAZORPAY_WEBHOOK_SECRET` = …… (the phrase you set on the webhook)

**Stripe (if you prefer international):**
1. **https://stripe.com → Developers → API keys.** Copy the **Secret key** (`sk_live_...`).
2. **Developers → Webhooks → Add endpoint** (I give you the URL) → copy the **Signing
   secret** (`whsec_...`).
- `STRIPE_SECRET_KEY` = …… · `STRIPE_WEBHOOK_SECRET` = ……

*(Pick one to start. Razorpay if your customers pay in INR.)*

---

## 5. AI Media provider (video / image generation)

**What it is:** A service that generates AI **videos and images** from a text prompt.
**Unlocks:** **Media-Gen** — auto-creating ad creatives, social posts, product videos.
**Why needed:** Generating media costs GPU money; the provider's key is how they bill and
authorize you.

**Pick one (all are sign-up + copy-a-key):**
- **Luma** (video): **https://lumalabs.ai** → account → **API / Developer** → create key.
  Send `LUMA_API_KEY = ……`
- **Higgsfield** (video): **https://higgsfield.ai** → account → API key.
  Send `HIGGSFIELD_API_KEY = ……`
- **Replicate** (runs many video/image/3D models): **https://replicate.com → Account →
  API Tokens → Create token.** Send `REPLICATE_API_TOKEN = ……`

**Send me:** any **one** of the above keys (Replicate is the most flexible to start).

---

## 6. DigitalOcean Spaces (storage for generated media)

**What it is:** Cloud file storage (like a private Dropbox) where generated videos/images
are saved and served from.
**Unlocks:** Makes **Media-Gen** (#5) actually usable — the files need somewhere to live.
**Why needed:** Generated media has to be stored and served on a fast, public URL.

**Click-by-click:**
1. **https://cloud.digitalocean.com** (your existing DO account) → left menu **Spaces
   Object Storage → Create a Spaces Bucket.** Pick a region (e.g. **BLR1 / Bangalore**),
   name the bucket (e.g. `famit-media`). **Copy the bucket name, region, and endpoint URL.**
2. Top menu **API → Spaces Keys → Generate New Key.** Copy the **Key** and **Secret**
   (secret shown once).

**Send me these:**
- `SPACES_KEY` = …… · `SPACES_SECRET` = ……
- `SPACES_BUCKET` = …… · `SPACES_REGION` = …… · `SPACES_ENDPOINT` = …… (e.g. `blr1.digitaloceanspaces.com`)

---

## 7. Paid AI key — Groq and/or Cerebras (faster, more reliable calls)

**What it is:** A paid plan for the AI "brain" that powers the voice agent's responses.
**Unlocks:** **Consistent low call latency** (the agent replies faster, more reliably,
under load) and smarter **Customer Support** auto-replies.
**Why needed:** Free tiers throttle under volume — calls can lag or fail at busy times.
A paid key removes those limits. *(Calls work today on free keys; this is a quality/scale
upgrade, not a blocker.)*

**Click-by-click:**
- **Groq:** **https://console.groq.com → API Keys → Create API Key** → add a paid/billing
  plan under **Billing**. Send `GROQ_API_KEY = ……`
- **Cerebras (optional second):** **https://cloud.cerebras.ai → API Keys.** Send
  `CEREBRAS_API_KEY = ……`
- *(Optional, for best-quality support replies:* an Anthropic key from
  **https://console.anthropic.com → API Keys.** Send `ANTHROPIC_API_KEY = ……`)

**Send me:** the **Groq** paid key at minimum.

---

## 8. Logto Google login (let customers sign in with Google)

**What it is:** A Google "Sign in with Google" button for your customers' login.
**Unlocks:** One-click **social login** (nicer signup, fewer passwords) on the customer
portal.
**Why needed:** Google requires you to register an app to issue the login client id/secret.

**Click-by-click:**
1. **https://console.cloud.google.com → APIs & Services → Credentials → Create
   Credentials → OAuth client ID** (type **Web application**).
2. Under **Authorized redirect URIs**, paste the one I give you (Logto's callback URL).
3. Copy the **Client ID** and **Client Secret**.

**Send me:** `GOOGLE_OAUTH_CLIENT_ID = ……` · `GOOGLE_OAUTH_CLIENT_SECRET = ……`

---

## 9. Cloudflare API token (DNS / domain automation)

**What it is:** A scoped key that lets me manage your domain's DNS and edge security
automatically.
**Unlocks:** Faster, safer domain/SSL changes and putting your sites behind Cloudflare's
protection without manual console work.
**Why needed:** The previous token was de-scoped during the security rebuild; I need a
fresh one limited to just DNS for your zone.

**Click-by-click:**
1. **https://dash.cloudflare.com → (top-right profile) → My Profile → API Tokens →
   Create Token.**
2. Use the **"Edit zone DNS"** template → under **Zone Resources** pick your domain
   (e.g. `famit.in`) → **Continue → Create Token.** Copy it (shown once).

**Send me:** `CLOUDFLARE_API_TOKEN = ……`

---

## 10. DigitalOcean account housekeeping (do this yourself in the console)

**What it is:** Account-level settings on DigitalOcean (where the servers live).
**Why it matters:** We are **using all 3 of 3 allowed servers** — I cannot add new
capacity (e.g. a dedicated server for the new modules at scale) until the limit is raised.

**Click-by-click:**
1. **https://cloud.digitalocean.com → Settings → Billing →** confirm a valid **payment
   method (card)** is on file.
2. Raise the droplet limit: open a quick request at **https://cloud.digitalocean.com →
   Support / "Get Help"** → ask to **"increase my Droplet limit from 3 to (say) 8."** It's
   usually approved within a day once billing is healthy.

**Tell me** once (a) a card is on file and (b) the limit is raised. *(No key to send —
these are account toggles only you can do.)*

---

## 11. Domain / DNS items (only if changing domains)

**What it is:** Your domain name(s) and where their DNS is managed.
**Why it matters:** If you want new customer-facing domains (e.g. a marketing site or
white-label domains), I need access to add DNS records.
**What to do:** Tell me which domain registrar you use (GoDaddy, Namecheap, etc.) and the
domain(s) you want live. If they're on Cloudflare, card #9 covers it. Otherwise I'll send
you the exact 2–3 DNS records to paste at your registrar.

---

# Send me these and I make it all real

**Top 4 by impact — start here:**
1. **WhatsApp** (Meta) — Phone number ID + permanent token + approved template → turns on WhatsApp.
2. **Ads** — Meta Marketing API (or Google Ads) keys → turns on Ad Automation.
3. **Payments** — Razorpay (or Stripe) keys + webhook secret → turns on Payments.
4. **Media** — one AI media key (#5) + DO Spaces storage (#6) → turns on Media-Gen.

**Then the polish keys:** paid Groq (#7) for faster calls, Google login (#8), Cloudflare
token (#9), and the DO account housekeeping (#10).

**Quick wins that already work — for free, right now:**
- The entire original product (Dashboard, Campaigns, Run, Leads, Call Logs, Callbacks,
  Suppression, Webhooks, Analytics, Billing, Settings) is **live on real data**.
- The moment you say go, I flip ~6 switches and **Funnels, Workflows, Form Builder, CRM,
  Customer Support, Booking, and AI Manager** light up — **no accounts, no money.**

> The only thing standing between "looks like a demo" and "fully real and sellable" is
> the short list above — almost all free to set up, and the few that cost money
> (payments gateway fees, ad spend, AI media) only cost when you actually use them.

---

# Creative Studio (AI banner/poster maker) — what I need to turn it on

This is the new "tell-the-AI-what-you-need, it-makes-the-banner" studio. I've designed and can
build the whole engine **dormant and free** — it produces real banners only once you paste ONE
key. Here is the short list, easiest first:

**Already provided / handled — nothing for you to do:**
- **The OpenRouter key** you gave me (`OPNEROUTER_API_KEY` in your `.env.local`) is what makes real
  banners. I'll paste it on the server when we go live. **This is the only must-have for the first
  real banner.** (Heads-up: I spotted the env name is spelled `OPNE…` not `OPEN…` — I handle that
  in code, no action needed.)

**Interim defaults already chosen (work now, upgrade later):**
- **Storage** — banners save to the server's own disk for now. To get fast CDN delivery + durability
  later, send me **DO Spaces** keys (same as Media-Gen card #6 above — one set covers both).
- **Speed at scale** — big batches use a simple in-process runner now; the durable Hatchet queue
  (already built on its own box) turns on once I open one network port between boxes (my job, no key).
- **Smarter prompts** — uses your existing call/Groq key; gets sharper with a paid Groq key (#7).

**Only when you want to PUBLISH a banner to WhatsApp:**
- **Meta WhatsApp** (card #1 above — phone-number-id + permanent token + an approved template).
  Browsing, previewing and attaching banners works without it; the actual *send* needs Meta live.

**Bottom line:** paste nothing and I build the entire Creative Studio for free (it just uses test
images). Paste the **OpenRouter key** (already in your `.env.local`) and it makes **real banners
from your real campaigns**. Everything else is a later quality/speed/storage upgrade.

> _(original closing note below)_
> The only thing standing between "looks like a demo" and "fully real and sellable" is
> the short list above — almost all free to set up, and the few that cost money
> (payments gateway fees, ad spend, AI media) only cost when you actually use them.

---

## 2026-06-11 — WhatsApp + DO Spaces creds RECEIVED & TESTED (external, read-only)
Full report: `WHATSAPP_GOLIVE.md`. Summary:
- **DO Spaces creds = VALID** (real PUT/GET/DELETE roundtrip passed on bucket `capsy-recordings`/sgp1). Asset storage ready.
- **WhatsApp webhook = WORKING & DEPLOYED.** Correct callback URL to paste in Meta: `https://panel.famit.in/api/whatsapp/inbound`, verify token `evsaivoiceagent`. (Founder's verification failed only because he used the wrong path, e.g. `/whatsapp/webhook` — real route is `/whatsapp/inbound`.) Proven: Meta's GET handshake returns 200 echoing the challenge.
- **WhatsApp SEND = BLOCKED.** `META_WA_TOKEN` (Section 5) is App-ID-shaped, NOT a real token → Graph API returns 401. **MUST replace with a permanent System-User token (`EAA…`, scopes whatsapp_business_messaging+management).** This is the #1 send blocker.
- Post-Control-Layer wave to apply: fix `META_WA_TOKEN` in `/opt/famit-agent/.env`, confirm approved template, set FEATURE_WHATSAPP flag, add Spaces creds to AI Asset service env, restart famit-caller, re-test send+inbound.

## 2026-06-11 (update) — WhatsApp NOW LIVE end-to-end ✅
Founder pasted the real permanent `EAA…` token. Re-tested:
- WhatsApp SEND = PASS — real text message DELIVERED to +917861019021 (wamid returned). Token valid (auths as system user "famit"); number now Cloud-API registered (one-time /register, pin 000000, success).
- Webhook = already connected on Meta's side (`webhook_configuration` shows https://panel.famit.in/api/whatsapp/inbound).
- Notes: WABA is branded "MedFlow" / +91 97550 40013 (confirm it's the intended number). Only `hello_world` template approved, which can't be used on a real number → need a real approved (UTILITY) template for cold sends. BOX .env still has the OLD bad token → update to the EAA… token in the post-Control-Layer wave, then FEATURE_WHATSAPP + restart famit-caller.

## 2026-06-11 — AI ASSET SERVICE / CREATIVE STUDIO: live banner proof DONE; founder follow-ups
The AI Asset Service is now LIVE on the box and PROVEN end-to-end (C3 verify, 2026-06-11): a fresh job
generated 2 real banners, stored them in DO Spaces, served them via a presigned image URL, and charged the
wallet the actual Rs6.76 with no double-charge — plus tenant isolation and WhatsApp templates both passed.
It is ON for the **admin** tenant so you can try it. The ONE thing blocking a clickable BROWSER demo:

0. **⚠ THE PANEL CAN'T REACH CREATIVE STUDIO YET — one-line frontend fix (engineering, no key from you).**
   `https://panel.famit.in/api/assets/...` currently TIMES OUT in the browser, even though the engine
   behind it is fully working (proven over the private network). Cause: the frontend server's web-proxy
   rule for `/api/assets/` still points at the old address; the service has since moved to the private VPC
   address `10.122.0.4:8310` (and the backend firewall already allows it). Fix = repoint that one nginx
   `proxy_pass` line to `http://10.122.0.4:8310;` on the frontend box and reload nginx. I could not do this
   in-session — I don't have SSH access to the frontend box with the current key. Once it's repointed, the
   Creative Studio screens light up with zero further backend work. (Everything else — auth, generation,
   Spaces storage, wallet, isolation — is GREEN.)

1. **DO Spaces for production asset storage — ✅ DONE & VERIFIED (C3).** Banners now store in Spaces
   (`creative/admin/banner/<job>/0.png`) and serve via presigned URLs; bucket `capsy-recordings`/sgp1.
   `SPACES_*` set in the AI Asset service `.env`. (Minor: the DB row still labels storage as `local` though
   the bytes ARE in Spaces and fetchable — a one-line label fix, doesn't affect the working image URL.)
2. **Per-tenant OpenRouter keys (optional).** All tenants share the one `OPNEROUTER_API_KEY` now. To bill a
   tenant on its OWN OpenRouter account, set `OPNEROUTER_API_KEY__<tenant_id>` in the service `.env` (the
   adapter prefers the per-tenant key). Not required — the shared key works.
3. **Per-tenant ON/OFF gating** (engineering follow-up). `AIASSET_ENABLED` is a global flag today; before the
   public `/api/assets/` route is opened to all vendors, add a per-tenant allowlist / `ai_asset_provider_state`
   row so Creative Studio can be turned on vendor-by-vendor (same pattern as the other modules).
4. **Two small engineering gaps** (recorded, non-blocking): the DB `version.local_path` is left empty so
   `GET /assets/{id}/raw` can't stream the file yet (the PNG IS on disk) — one-line map fix; and the
   cross-module PG `events` audit leg is not written from the standalone process (the per-vendor immutable
   `ai_asset_audit_logs` IS). Both in `memory/build_log/wave-build-aiasset-A4.md`.

## 2026-06-11 — AI Manager can now make REAL banners by voice/chat (B3 wired)
The AI Manager is now connected to the Creative Studio engine: a command like "create 2 ad banners for the
Codename Joy 3.0 campaign" (in the AI Manager Test Console) actually generates a real banner — credit-charged
the true cost, no double-charge, with a full audit trail and each customer's data walled off. Proven live on
the admin account. Nothing below blocks that; these are the remaining items to take it further:
1. **A real Meta-approved WhatsApp template** (and confirm the "MedFlow" / +91 97550 40013 number is the one
   you want) — needed ONLY to SEND a generated banner to a cold WhatsApp contact. Browsing, generating and
   attaching banners works today without it. (Same ask as Section 2 #1 / the WhatsApp card.)
2. **(my engineering follow-up, no key from you):** turn Creative Studio on per-customer (it's globally
   on for the admin test account today) before opening it to every vendor; and teach the AI Manager to map a
   spoken campaign name to its exact campaign so banners pick up that campaign's real price/offer/location.
