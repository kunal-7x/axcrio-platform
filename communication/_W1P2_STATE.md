# W1-P2 STATE — webhook + comm endpoints + caller.py mount (crash-safe scratch)

Branch: fe/unify-run-wavec. Box golden caller md5 = 44b867eaa3a448792a82c9760db0d76b.

## UNITS (flip DONE as each verifies)
1. [DONE] comm/sessions.py — comm_sessions read/upsert (RLS-scoped, best-effort)
2. [DONE] comm/webhook.py — handle(tenant_id, header_value, raw) FAIL-CLOSED. secret_token =
   hmac(signing, "telegram-webhook||tenant||def_id"); compare_digest; verify BEFORE GUC; bot bind via
   provider_def; no-secret/dormant/wrong/cross-tenant -> 403; update_id idempotency; W1 reply-DISABLED.
3. [DONE] comm/endpoints.py — build_router(...). GET /comm/channels · POST .../telegram/test ·
   .../derive-chat-id · .../set-webhook · GET /comm/sessions[/{id}] · POST /comm/send ·
   POST /comm/webhook/telegram/{tenant_id} (unauth fail-closed). (dropped `from __future__ annotations`
   so FastAPI resolves Request/Body annotations.)
4. [DONE] comm/router.py — thin build_router re-export.
5. [DONE] offline tests — test_webhook_offline (17/17 PASS) + test_endpoints_offline (9/9 PASS);
   telegram 22/22 + engine 9/9 regression PASS. agent-import grep 0. empty-env import rc 0. gitleaks 0.
6. [DONE] py_compile all + gitleaks 0. COMMITTED (non-caller.py unit).
7. [DONE] caller.py mount (anchor after whatsapp-builder include_router) — +43 lines, 0 deletions.
   Box golden 44b867ea -> 73d7be4f. md5-gated deploy. Flags COMM_ENABLED=1 + COMM_TELEGRAM_ENABLED=1.
8. [DONE] earner gate BEFORE+AFTER under induced Telegram outage — ALL GREEN. LIVE T-WEBHOOK 6/6 PASS.
   Lock RELEASED. _BUILD-LOG.md appended. WHOLE PHASE COMPLETE.

## KEY DECISIONS
- Webhook secret_token DERIVED (not a new DB column): hmac_sha256(WEBHOOK_SIGNING_SECRET, tenant||provider_def_id),
  hex. Bound to PATH tenant + the bot's provider_def. setWebhook sets it; the inbound header must match it.
  WEBHOOK_SIGNING_SECRET falls back to the existing caller signing secret if a dedicated one is absent.
- W1 webhook is reply-DISABLED (no brain until W2): it verifies fail-closed, stores the inbound turn into
  comm_sessions, returns 200 fast. This keeps the security surface (S2) shippable now; the brain mounts W2.
- All comm endpoints token-derive tenant (build_router pattern); the webhook is the ONLY unauth route and
  is fail-closed (secret bound to path tenant, GUC set only AFTER verify).
