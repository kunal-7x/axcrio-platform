# W2 STATE — the conversation brain (reply-only) · DONE (built OFF, offline-green)

> All 6 units DONE. 8/8 offline suites PASS (3 new + 5 prior, zero regression). gitleaks 0.
> NO caller.py edit (webhook already mounted in W1-P2). Resting byte-identical (flags OFF).
> Committed on fe/unify-run-wavec. LIVE flip = founder-gated (tap bot + setWebhook + flip flag).

Branch `fe/unify-run-wavec`. Resume from here on a crash.

## SCOPE (this wave)
Reply-only LLM brain on Telegram: inbound webhook message -> brain -> Telegram reply
(the contact chats with "Riya"), grounded in the prior call (call_summary/next_action/
outcome seeds + the rolling-20 turns + cross-call memory recap + the campaign brand).
Signed single-use `?start=` consent deep-link. Inbound media must not crash. Per-tenant
rate/body/Groq cap. `COMM_TOOLS_ENABLED=0` (no tools this wave — reply-only).

## EARNER LAW (unchanged)
agent.py md5 `9150fabe` UNCHANGED · famit-agent NOT restarted · this rides caller.py only ·
imports NO agent.py · flags default OFF -> resting byte-identical. NO caller.py edit this
wave (the webhook route + brain are already mounted via W1-P2's endpoints; W2 only flips a
reply ON inside the EXISTING webhook handler + adds brain/deeplink modules). The reply is a
NEW flag `COMM_BRAIN_ENABLED` (default OFF).

## UNITS (flip to DONE as each verifies)
- [ ] U1 `comm/brain.py` — generate_reply(snap-like ctx) reply-only; pre-LLM opt-out/handoff
      keyword gate FIRST; ONE Groq call (copy `_wa_reply_text` grounding); tools OFF.
      Groq client = a thin local `_groq_chat` copy (httpx, key from env) — NOT importing caller.
- [ ] U2 `comm/deeplink.py` — base64url(tenant||nonce||hmac(secret, tenant||nonce||phone)),
      minted server-side, single-use (own jti file like firewall), short TTL. verify/forge/replay/expire.
- [ ] U3 `comm/lang.py` — best-effort langdetect (degrade to '' — never raises, optional dep).
- [ ] U4 wire `webhook.py` — after store, if COMM_BRAIN_ENABLED: build ctx from the session +
      cross-call grounding -> brain.generate_reply -> engine.send reply -> append assistant turn.
      Per-tenant rate-limit + body-size cap (already partly in endpoints) + daily Groq ceiling
      BEFORE any LLM call. Opt-out word -> suppress + NO Groq call. Media -> ack, don't crash.
- [ ] U5 offline tests: test_brain_offline, test_deeplink_offline, test_webhook_reply_offline.
- [ ] U6 py_compile all + gitleaks 0 + agent-import grep 0 + commit + APPEND build log.

## NEW FLAGS (default OFF)
- `COMM_BRAIN_ENABLED` — the master reply flag (webhook reply path). OFF -> W1 store+ack only.
- `COMM_TOOLS_ENABLED` — agentic tools (OFF this wave; reply degrades to plain text).
- `COMM_GROQ_DAILY_CAP` — per-tenant daily LLM-call ceiling (default 500). `COMM_REPLY_MAX_TURNS` (12).

## KEY REUSE FACTS (verified on disk)
- `_wa_reply_text` caller.py:2189-2235 (the grounding shape to COPY, not import).
- `_groq_chat` caller.py:1428-1442 (httpx POST to Groq; key GROQ_KEY, model GROQ_MODEL).
- opt-out words caller.py:2017; handoff words caller.py:2020.
- sessions.get_session returns call_summary/next_action/outcome/interest + turns (seeds may be '').
- webhook.handle stores the inbound turn at sessions.append_turn THEN acks (W1). W2 inserts the
  reply between store and ack, flag-gated.
- engine.send(tenant, SendEnvelope(to_ref=chat_id, kind="text", purpose="service", text=reply))
  is the outbound seam (per-channel wait_for timeout owned there).
