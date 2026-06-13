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
- [ ] U4 tsc --noEmit EXIT 0 + npm run build EXIT 0.
- [ ] U5 deploy FORTRESS backup-first (*.FIXUIbak.<ts>), OOM-swap, restart famit-panel only, 200 loopback + edge.
- [ ] U6 commit + docs (AGENT_LEARNINGS, ORCHESTRATOR, build_log).
