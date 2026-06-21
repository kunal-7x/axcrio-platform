# WhatsApp Approved-Template LIVE Send Test — RESULT

> Live test of the approved post-call WhatsApp template against the Meta Cloud API.
> Date: 2026-06-12. Box: `famit@168.144.153.145:/opt/famit-agent/`.
> Creds: `caps/.env.local` + `lead/ALL_CREDENTIALS.md` (Section 5 WhatsApp). Secrets NOT printed here.

## VERDICT: SEND SUCCEEDED — Meta accepted it (HTTP 200 + wamid).

The founder **should receive the message on WhatsApp** at the test number below.

## What was sent (exactly ONE message)

- **Template:** `post_call_followup` — **APPROVED · MARKETING · language `en`** (confirmed live
  against the WABA `message_templates` graph endpoint before sending).
- **Body:** `"Hi {{1}}, thanks for taking our call about {{2}}. Reply here if you have questions or
  want to take the next step."` + 2 quick-reply buttons (`Yes, tell me more`, `Not Interested`).
- **2 variables:** `{{1}}` = name, `{{2}}` = product/enquiry. I filled sensible test values:
  - `{{1}}` = `Kunal`
  - `{{2}}` = `your property enquiry`
- **Recipient:** **`917861019021`** (founder test number — `test_phone_number_2` /
  `TESTE_PHONE_NO=+917861019021` in the creds).
- **Phone Number ID:** `1092495863955117` · **WABA:** `1006344518646333` · Graph `v21.0`.
- **Payload shape:** identical to what `whatsapp.py:_meta_template_body` (`:127`/`:291
  send_whatsapp_async`) builds — `type=template`, `language.code=en`, `components[0].type=body`
  with 2 text params. (Sent directly to Meta to avoid touching the live box; same wire format.)

## Meta API response (authoritative confirmation)

```
HTTP 200
{
  "messaging_product": "whatsapp",
  "contacts": [{ "input": "917861019021", "wa_id": "917861019021" }],
  "messages": [{
      "id": "wamid.HBgMOTE3ODYxMDE5MDIxFQIAERgSQTMwM0E0M0E2QzFBQjM4QzBEAA==",
      "message_status": "accepted"
  }]
}
```

- **wamid:** `wamid.HBgMOTE3ODYxMDE5MDIxFQIAERgSQTMwM0E0M0E2QzFBQjM4QzBEAA==`
- **message_status:** `accepted` (Meta has queued it for delivery — the success signal for a
  template send). `wa_id` resolved → the number is a valid WhatsApp user.

### Delivery/read status
Meta delivers `sent` → `delivered` → `read` asynchronously via the **status webhook**
(`caller.py:4415 /whatsapp/inbound` POST, parsed at `_parse_meta_inbound`). Those callbacks
land seconds–minutes later and were not yet in the box journal at check time (and this send went
straight to Meta, not through the box, so it isn't in `var/wa_log.json`). The `accepted` + wamid
is the definitive "Meta took it" confirmation; `delivered`/`read` will follow on the founder's
handset. No error code was returned, so it is NOT blocked by template-status / name / lang / token /
test-recipient-allowlist issues.

## Errors? NONE. (and the fix that pre-empted the known 404)

No error. The one known failure mode from prior manual sends (`sent:404` in `wa_log.json`) was a
**language-code mismatch**: the template is `en`, but sends defaulting to `en_US`/`hi` 404.
**Fix applied here:** passed `language.code=en` explicitly (matches the template). This is GAP-G4
in `wa-automation-state.md` and is the cause of the historical manual 404s — confirmed by the clean
200 once `en` is used.

## Regression gate (live earner safe — nothing broken)

The send touched **zero** files/services on the box (direct Meta API call). Verified after:
- `famit-caller` / `famit-agent` / `famit-bridge` → **all active**.
- Core HTTP on caller (`127.0.0.1:8209`): `campaigns=200`, `leads=200`, `me=200`, `health=200`.
- `agent.py` (the outbound earner) untouched; no restart performed.

## Bottom line for the founder

- The approved template **WORKS end-to-end against Meta**. It SENT to **+91 7861019021**, wamid
  `wamid.HBg...QTMwM0E0M0E2QzFBQjM4QzBEAA==`, status **accepted**.
- **You should see it on WhatsApp** as: *"Hi Kunal, thanks for taking our call about your property
  enquiry. Reply here if you have questions or want to take the next step."* with two buttons.
- The correct cold-send recipe for the automation pipeline is now proven: template
  `post_call_followup`, **`language.code=en`**, body params `[name, product/enquiry]`. That is
  exactly what GAP-G1/G2/G4 need wired into `_wa_ai_followup`.
