# FIXUI WAVE — asset preview + CRM transcript chat-view (FRONTEND)

Branch: backend/handoff-name-clean-line (continuing). Deploy target = FORTRESS panel root@143.110.247.249:/opt/famit-panel.

## Scope (FE only; earner box untouched — different machine)
1. BUG-1 asset preview/click — render presigned url in grid + lightbox/detail.
2. BUG-2 CRM transcript chat-view — click a call row → full transcript chat (customer RIGHT, AI LEFT).

## Backend facts (verified live on box 168.144.153.145, caller :8209)
- Asset detail/list: presigned url ALREADY served (LIST + DETAIL via endpoints.get_asset fold). AssetImage uses native <img>. DONE in commit 1005ccb.
- Transcript: `GET /calls/{call_id}/transcript` LIVE (caller.py:4282, box md5 e802d301). Accepts outbound call id OR room OR inbound session_id. Returns `{call_id,direction,phone,name,turns:[{role:"ai"|"customer",text,ts,seq}],total}`. Roles pre-normalized: ai→LEFT, customer→RIGHT. SMOKE: room famit-916375548830-ad08ff → 94 turns, correct sides. 200.
- Timeline call row carries `source="calls"`, `source_id = call.id or room` (crm/core.py:580) → pass source_id as call_id.
- ⚠️ tracked mirror droplet_work/caller.py (ad121cf4) is BEHIND box (e802d301) — does NOT have transcript route. Box is source of truth; sync mirror in commit (docs only).

## UNITS
- [DONE] U1 asset preview. ROOT CAUSE deepened: live /assets/{id} returns NESTED {asset,versions} + the asset's own url is UNSIGNED (raw path-style → 403). FIX lib/assets.ts getAsset: flatten envelope + override display url/thumb_url with the current version's PRESIGNED url. (Grid/list already presigned + fine.)
- [DONE] U2 crm/client.ts: getCallTranscript(callId) + CallTranscript/TranscriptTurn types (dormant-safe, role normalize).
- [DONE] U3 app/crm/[id]/page.tsx: clickable call timeline row → CallTranscriptModal chat-view (customer RIGHT primary tint, AI LEFT surface).
- [DONE] U4 tsc --noEmit EXIT 0 + npm run build EXIT 0 (BUILD_ID tuuIjqN7fCf_iEL-obLon; /crm/[id] 8.46kB).
- [DONE] U5 deploy FORTRESS root@143.110.247.249 (key do-blr-test/id_ed25519). backup-first *.FIXUIbak.20260613-172953. atomic swap, chown deployuser, restart famit-panel ONLY → active PID 248200. BUILD 4aXNPr1rvAfpK4ku5dNa7→tuuIjqN7fCf_iEL-obLon. 200 on / /login /crm /creative/library /crm/[id] on BOTH loopback:3001 AND panel.famit.in edge; served HTML carries the NEW BUILD_ID (no stale cache). No swap needed (prebuilt artifact, 1.4GB free + 28G disk). EARNER GATE before+after PASS (agent.py md5 9150fabe… unchanged, famit-agent PID 1477083 never restarted, caller /health 200 — earner box is a DIFFERENT machine 168.144.153.145).
- [DONE] U6 commit d9daa86 (4 FE files) + docs.

## GOTCHA logged
- Rapid-fire SSH polling against the hardened FORTRESS box trips sshd/fail2ban rate-limiting → ConnectTimeout. SCP itself succeeded (md5 0ccd08fb matched local). Do the deploy in ONE SSH session (backup→extract→verify→swap→restart) and verify with sparse single connections, not a tight poll loop.
