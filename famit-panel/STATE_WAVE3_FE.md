# WAVE 3 FRONTEND — STATE

Owner: frontend agent. Build additively against WAVE 3 contract in HANDOFF.md.

## TASKS
- [DONE] lib/api.ts wrappers: getMe, login(role), webhooks CRUD, ab results, billing, billing ledger, setBilling, whatsapp send/log, RunError(402)
- [DONE] lib/auth.ts: localStorage me cache {role,is_admin,...}, useMe hook, can() helpers
- [DONE] login stores role/is_admin/name/tenant_id
- [DONE] Sidebar role-gated (Vendors+Billing admin-only; Webhooks+WhatsApp manager+; hide mutating where agent)
- [DONE] navigation.tsx add Webhooks, Billing, WhatsApp (+roles meta)
- [DONE] RBAC gating: run page (agent read-only), campaigns (agent no create/delete), vendors role picker, 403 toast helper
- [DONE] webhooks page (/webhooks)
- [DONE] billing page (/billing) + admin config
- [DONE] whatsapp page (/whatsapp)
- [DONE] A/B variants editor in campaigns + wa_followup toggle + /ab results modal
- [DONE] 402 insufficient-balance surfaced on run page
- [DONE] build npm install --legacy-peer-deps && npm run build (Compiled successfully; /billing /webhooks /whatsapp routes present)
- [DONE] also gated leads Add panel for agent
- [IN PROGRESS] deploy to voice-2 OR write DEPLOY_WAVE3_FE.md

## CONTRACT NOTES (exact)
- GET /me -> {tenant_id,email,name,role,is_admin}; role in admin|manager|agent
- POST /login -> {token,tenant_id,name,is_admin,role}
- webhooks events: call.completed, lead.qualified, callback.scheduled, lead.opted_out
- GET /webhooks -> {webhooks:[{id,tenant_id,url,secret,events[],active,created_at}]}
- POST /webhooks form url,secret(opt),events(space/comma) -> {id,url,secret}
- DELETE /webhooks/{id} -> {deleted}
- variants: fields.variants=[{id,label,weight,fields_override:{opener,agent_name,voice_id}}]
- GET /campaigns/{id}/ab -> {campaign_id,variants:[{id,label,weight,dialed,connected,interested,qualified,avg_interest}]}
- GET /billing -> {tenant_id,plan,currency,rate_per_min,rate_per_call,balance,included_minutes,month_to_date:{calls,minutes,cost}}
- GET /billing/ledger?limit=100 -> {ledger:[{id,call_id,phone,campaign_id,duration_s,cost,currency,outcome,at}],total}
- POST /billing/{tenant_id} (admin) form plan,rate_per_min,rate_per_call,currency,balance,included_minutes,topup -> full record
- POST /run 402 -> {error:"insufficient balance",message,balance,currency}
- POST /whatsapp/send (manager+) form to, template OR text, params(comma/pipe) -> {ok,status,to,configured}; status skipped_no_config when no creds
- GET /whatsapp/log -> {log:[{tenant_id,phone,template,kind,status,ok,at}]}
- campaign fields: wa_followup(bool default OFF), wa_template_interested, wa_template_callback, wa_template_qualified, wa_template_noanswer
