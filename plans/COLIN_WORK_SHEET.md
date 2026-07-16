 
  
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
