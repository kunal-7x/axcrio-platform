# WhatsApp + DO Spaces Go-Live — END-TO-END CRED TEST + WEBHOOK DIAGNOSIS

**Date:** 2026-06-11  **Mode:** EXTERNAL API + read-only SSH greps (no caller.py edits, no restarts, no deploy). All cred tests done via direct vendor API calls.

> **UPDATE (2026-06-11, later):** the founder pasted the **real permanent `EAA…` token** into ALL_CREDENTIALS.md. Re-tested → the WhatsApp send now **PASSES end-to-end (real message delivered)**. Details in the updated TEST 1 below. OpenRouter image generation also tested and PASSES (the Creative Studio engine key works).

---

## TL;DR (one-screen verdict)

| Test | Result | Detail |
|------|--------|--------|
| **WhatsApp send (Graph API)** | ✅ **PASS** | After the new `EAA…` token + a one-time Cloud-API `/register`, a real **text message delivered** to +917861019021. HTTP 200, `wamid` returned. |
| **OpenRouter image gen** | ✅ **PASS** | `google/gemini-2.5-flash-image` returned a real 1.39 MB PNG; actual cost $0.0387 in `usage.cost`. Creative Studio engine key is live-ready. |
| **DO Spaces (PUT/GET/DELETE)** | ✅ **PASS** | PUT 200, GET 200 (content matched), DELETE 204. Creds fully valid. |
| **Webhook endpoint (our side)** | ✅ **PASS** | `https://panel.famit.in/api/whatsapp/inbound` echoes the challenge, HTTP 200. Verify token on box MATCHES Section 5. Meta already shows this URL in `webhook_configuration`. |
| **Webhook (why founder's verification once failed)** | ⚠️ **WRONG URL ENTERED IN META** | The real path is `/api/whatsapp/inbound`, not `/whatsapp/webhook`. |

**Bottom line:** WhatsApp is now LIVE end-to-end (send + receive + webhook), storage is go, and the image-gen key works. Remaining founder-facing notes: (1) the WABA is branded **"MedFlow" / +91 97550 40013** — confirm that's the intended number; (2) `hello_world` is the only approved template and is restricted to Meta test numbers, so production template sends need a real approved template; (3) the box `.env` still holds the OLD bad token — it must be updated in the post-Control-Layer wave.

---

## ⭐ PASTE THESE INTO META (App → WhatsApp → Configuration → Webhook → Edit)

```
Callback URL:  https://panel.famit.in/api/whatsapp/inbound
Verify token:  evsaivoiceagent
```

Then click **Verify and Save**. It WILL succeed (proven below — Meta's exact GET handshake against this URL returns HTTP 200 echoing the challenge). After it saves, under **Webhook fields** subscribe to **`messages`**.

---

## TEST 1 — WhatsApp SEND (real Graph API call) — ✅ PASS (after token fix + register)

**Final result — a real message was DELIVERED to the founder:**
```
POST https://graph.facebook.com/v21.0/1092495863955117/messages   (Bearer EAA… new token)
body: {"messaging_product":"whatsapp","to":"917861019021","type":"text",
       "text":{"body":"Famit go-live test: WhatsApp Cloud API is now LIVE..."}}
→ HTTP 200
  {"messages":[{"id":"wamid.HBgMOTE3ODYxMDE5MDIxFQIAERgSQjE1NTUwM0VFNzc4MUEwMTA0AA=="}]}
```
The founder should SEE this message on +917861019021.

**Path to PASS (three findings, in order):**
1. **Old token was invalid.** The first value (`4234…`, 16 digits = App-ID-shaped) returned HTTP 401 "Cannot parse access token". → Founder replaced it with a real permanent **System-User `EAA…` token** (202 chars). `GET /me` now authenticates as system user **"famit"**.
2. **`hello_world` template is restricted.** With the good token, sending the `hello_world` template returned `(#131058) Hello World templates can only be sent from the Public Test Numbers` — `hello_world` only works on Meta's sandbox numbers, not this real production number.
3. **Number needed one-time Cloud-API registration.** A template/text send first returned `(#133010) Account not registered`. Fixed with a one-time `POST /{phone_id}/register {"messaging_product":"whatsapp","pin":"000000"}` → `{"success":true}`. After that, the plain **text** send delivered (HTTP 200 + wamid), because a 24h session was open (the founder had messaged the number).

**Cred status now:** token VALID; phone-number-id, WABA id, app secret, verify token all correct and present.

> ⚠️ **TWO things the founder should know:**
> - **The WABA is branded "MedFlow", number +91 97550 40013** (`verified_name:"MedFlow"`). Confirm this is the intended WhatsApp business/number for Famit.
> - **Only `hello_world` is approved** on this WABA, and it can't be used on a real number. For business-initiated (cold, outside-24h) sends you need a **real approved template** (Meta → WhatsApp → Message Templates → create + submit, e.g. a UTILITY "your enquiry details" template). Today, sends only work to contacts with an **open 24h session** (someone who messaged the number).
>
> **Box `.env` still has the OLD bad token** — it must be updated to the new `EAA…` token in the post-Control-Layer wave (see backend changes below) before the in-app `/whatsapp/send` path works.

---

## TEST 2 — DO Spaces (real S3 PUT → GET → DELETE) — ✅ PASS

**Creds used (Section 2):** key `DO008…` [FOUND], secret [FOUND/REDACTED], bucket `capsy-recordings`, region `SGP1`, endpoint `https://sgp1.digitaloceanspaces.com`.

**Result (manual SigV4 roundtrip):**
```
PUT  famit-asset-test.txt   -> 200
GET  famit-asset-test.txt   -> 200   (downloaded bytes == uploaded bytes ✓)
DELETE famit-asset-test.txt -> 204
RESULT: SPACES PASS
```
**Verdict:** Spaces creds are 100% valid — auth, bucket, region all correct. Asset storage for the AI Asset Service is ready.

> Note: a first boto3 attempt failed with `RequestTimeTooSkewed` — that was **the local laptop's clock being ~35 min behind** real time (SigV4 allows max 15 min skew), NOT a cred problem. Proven by signing with the live server clock → full roundtrip passed. The production box's clock is NTP-synced, so this won't recur there.

---

## TEST 3 — WEBHOOK DIAGNOSIS — ✅ endpoint works; founder entered the wrong URL

**(a) The route in code** (`/opt/famit-agent/caller.py`):
- **`GET  /whatsapp/inbound`** (caller.py:4352) = Meta verification handshake. Reads `hub.mode` / `hub.verify_token` / `hub.challenge`; echoes the challenge as `text/plain` 200 when `mode==subscribe` AND `token == os.getenv("META_WA_VERIFY_TOKEN")`; else 403.
- **`POST /whatsapp/inbound`** (caller.py:4406) = receive messages; verifies `X-Hub-Signature-256` (HMAC-SHA256 w/ `META_WA_APP_SECRET`), parses sender+text, always returns fast 200.
- The send side is `POST /whatsapp/send` (caller.py:4313) via `whatsapp.py` → `graph.facebook.com/v21.0/{phone_id}/messages` with `Bearer META_WA_TOKEN`.

> ⚠️ The route is **`/whatsapp/inbound`**, NOT `/whatsapp/webhook`. This single naming difference is the cause of the founder's failed verification.

**(b) The public callback URL.** nginx fronts `https://panel.famit.in` and maps `/api/` → backend (caller.py on `168.144.153.145:8209`), stripping the `/api` prefix. So:
```
panel.famit.in/api/whatsapp/inbound   →   backend GET /whatsapp/inbound   ✅
```
Proven: `/api/whatsapp/webhook` returns FastAPI `{"detail":"Not Found"}` 404 (no such route), while `/api/whatsapp/inbound` returns 200.

**(c) Verify-token match.** Box `/opt/famit-agent/.env` has `META_WA_VERIFY_TOKEN=evsa…` which **MATCHES** Section-5 `evsaivoiceagent`. ✅ No mismatch.

**(d) Live external proof of the handshake:**
```
GET https://panel.famit.in/api/whatsapp/inbound?hub.mode=subscribe&hub.verify_token=evsaivoiceagent&hub.challenge=famit123
  → HTTP 200   body: famit123            ✅ PASS (echoes the challenge)

(negative control) ...hub.verify_token=WRONGTOKEN...
  → HTTP 403   body: verification failed  ✅ correct security behavior
```

**(e) EXACT cause + fix.**
- **CAUSE:** The founder pasted the **wrong callback URL** in Meta (anything other than `/api/whatsapp/inbound` — e.g. `/whatsapp/webhook`, `/api/whatsapp/webhook`, or the bare domain). The backend route, the verify token, the deploy, and the nginx mapping are all correct and live. (A secondary possibility — a verify-token typo in Meta — is ruled out as long as he enters exactly `evsaivoiceagent`.)
- **FIX:** In Meta App → WhatsApp → Configuration → Webhook, set Callback URL = `https://panel.famit.in/api/whatsapp/inbound` and Verify token = `evsaivoiceagent`, then Verify and Save. Subscribe to the **`messages`** field.

---

## BACKEND CHANGES STILL NEEDED TO FULLY GO LIVE
*(APPLY in a careful wave AFTER the Control Layer build finishes — do NOT collide with it. The webhook needs NOTHING. These are for the in-app SEND path.)*

1. **Update `META_WA_TOKEN`** in `/opt/famit-agent/.env` — the box still holds the OLD bad `4234…` value; replace it with the new permanent `EAA…` token (now in ALL_CREDENTIALS.md Section 5). **This is the #1 fix for the in-app send path.** (verify token + phone id + WABA id + app secret are already correctly set on the box; the number is now Cloud-API-registered.)
2. **Create + submit a real approved template** in Meta (UTILITY framing, e.g. "your enquiry details") and wire its name/language into the send config. `hello_world` can't be used on this real number. Business-initiated (cold) sends require an approved template.
3. **Activate the WhatsApp feature flag** — set `FEATURE_WHATSAPP` / `WHATSAPP_ENABLED` (whichever the activated build uses) in `/opt/famit-agent/.env`. (None set today; module is dormant-safe.)
4. **Restart + verify** after env changes: `systemctl restart famit-caller`, then re-test:
   - send: `POST /api/whatsapp/send` → expect HTTP 200 + a `messages[0].id`, and a real message on `+917861019021`.
   - inbound: reply on WhatsApp → confirm `POST /api/whatsapp/inbound` 200 + thread stored.
5. **Confirm the WABA/number** — the WABA is branded **"MedFlow" / +91 97550 40013**; verify that's the intended Famit WhatsApp number before going to scale.

---

## Cred status (no secrets printed)

| Cred | Status |
|------|--------|
| META_WA_PHONE_NUMBER_ID | [FOUND] correct shape, set on box |
| META_WA_BUSINESS_ACCOUNT_ID | [FOUND] correct shape, set on box |
| META_WA_TOKEN | [FOUND] **VALID `EAA…` permanent token — real send delivered. (Box .env still has the OLD token → update it.)** |
| META_WA_VERIFY_TOKEN | [FOUND] `evsaivoiceagent` — matches box, webhook verified |
| META_WA_APP_SECRET | [FOUND] 32-hex, correct shape, set on box |
| WABA / number | "MedFlow" / **+91 97550 40013** — registered on Cloud API; confirm it's the intended number |
| Approved templates | only `hello_world` (test-number-only) — **need a real approved template** for cold sends |
| DO_SPACES_KEY / SECRET | [FOUND] **valid — full PUT/GET/DELETE passed** |
| TESTE_PHONE_NO | [FOUND] `+917861019021` |
