# WhatsApp Delivery Diagnosis — 2026-06-12 (READ-ONLY diagnosis, no fix applied)

## VERDICT (root cause, from Meta's own health_status API)
The WhatsApp WABA is **BLOCKED by Meta** — `can_send_message: BLOCKED`:
- **error_code 141006 — "There is an error with the payment method. This will block
  business initiated conversations."**  ← the real blanket blocker. Every send (template
  AND text) returns Meta HTTP **500 `code:2 OAuthException is_transient:true`** because of this.
- error_code 141010 — Business has NOT passed business verification
  (`business_verification_status: not_verified`).
- Display name "MedFlow" not yet approved → low messaging tier (TIER_250).

The code, env, token, and number are ALL fine. This is an **account/billing block at Meta**,
not a Famit bug. Timeline confirms: `post_call_followup` returned `sent:200 ok=True` at
2026-06-11 23:01 and a brochure at 2026-06-12 12:47 (free-tier conversations), then every
send from ~14:03 onward flipped to 500 — consistent with the free allowance ending / payment
method failing.

## FIX (founder action at Meta — NOT a code change)
1. Add/repair a valid **payment method** on the WhatsApp Business Account (resolves 141006).
   Meta Business Settings → WhatsApp Accounts → Billing/Payment methods.
2. Complete **Business Verification** (resolves 141010) — Business Settings → Security Center.
3. Submit the **display name** for approval to lift the messaging tier.
Until #1 is fixed, NOTHING will deliver regardless of template/window.

## EVIDENCE (redacted)
- Token: valid, System User, non-expiring (`expires_at:0`), scopes
  whatsapp_business_management + whatsapp_business_messaging. App "christeenstudio"
  (app_id 2741460946218468).
- Number: id 109…117, +91 97550 40013 "MedFlow", status CONNECTED, account_mode LIVE,
  platform CLOUD_API, code VERIFIED, TIER_250, quality UNKNOWN.
- Templates at Meta (only 3): post_call_followup=APPROVED(en), hello_world=APPROVED(en_US),
  limited_time_offer=REJECTED. NOT present: hot_lead_alert, benefit_focus, special_offer →
  those sends 404/500 (template-not-found) on top of the payment block.
- 5 consecutive live sends (incl. canonical hello_world + plain text) ALL = HTTP 500 code:2.

## LIVE ENV (redacted — names + present/len only; /opt/famit-agent/.env, propagated to proc)
- META_WA_PHONE_NUMBER_ID len=16  ✓ SET
- META_WA_TOKEN len=202            ✓ SET
- META_WA_BUSINESS_ACCOUNT_ID len=16 ✓ SET
- META_WA_VERIFY_TOKEN len=15 / META_WA_APP_SECRET len=32 / META_WA_APP_ID len=16  ✓ SET
- WA_API_URL len=0 / WA_API_KEY len=0 / WA_FROM len=0  (legacy generic BSP — intentionally empty)
- WA_AUTO_FOLLOWUP=1, WA_FOLLOWUP_TEMPLATE=post_call_followup(18), WA_LANG=en
→ meta_configured()=TRUE live. So BOTH manual + post-call paths use native Meta Cloud API.

## SEND-PATH MAP (Angle 2)
Every WA send funnels through whatsapp.py; Meta path wins when META_WA_* set (it is).
- **Panel manual-send**: lib/api.ts `sendWhatsApp()` → POST /api/whatsapp/send →
  caller.py `whatsapp_send` (@4879) → `_wa_send` → `send_whatsapp_async`/`send_whatsapp_text_async`.
  RUNS LIVE via Meta. (The whatsapp/ builder wizard waapi.ts is a SEPARATE dormant surface.)
- **Post-call auto**: caller.py @2263 `_wa_ai_followup` (fires every completed call;
  gate WA_AUTO_FOLLOWUP=1 OR campaign flag + score>min). Cold → approved TEMPLATE
  post_call_followup [name,product]; open 24h window → free-form text. Same Meta sender.
- **Brochure**: `_wa_send_brochure` → `send_whatsapp_document_async` (Meta document, presigned link).
- **Reply**: inbound webhook POST /whatsapp/inbound → `_wa_handle_inbound` → `_wa_reply_text`
  (LLM) → `send_whatsapp_text_async`. Webhook verify GET /whatsapp/inbound uses META_WA_VERIFY_TOKEN.
- **MISMATCH VERDICT**: NO real two-path credential mismatch. There is ONE sender (whatsapp.py)
  that prefers Meta (META_WA_*) and falls back to legacy generic (WA_API_*). Live = Meta path
  for ALL routes. The ONLY "mismatch" is COSMETIC: DeliveryStep.tsx:71-72 hard-codes the stale
  message "Add WA_API_URL / WA_API_KEY / WA_FROM" (legacy names) when a log row is
  skipped_no_config — misleading copy, NOT the cause of non-delivery.

## INBOUND WEBHOOK (Angle for replies)
Routes EXIST + mounted: GET /whatsapp/inbound (verify, uses META_WA_VERIFY_TOKEN),
POST /whatsapp/inbound (X-Hub-Signature-256 verified w/ META_WA_APP_SECRET). NOT verified
here whether Meta's webhook callback URL is configured + subscribed in the Meta app — that is
the next check for multi-step conversation once the payment block is cleared.
