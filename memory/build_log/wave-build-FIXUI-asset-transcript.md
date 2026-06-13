# Wave build — FIXUI: asset-detail presigned preview + CRM call transcript chat-view

Date: 2026-06-13. Branch `backend/handoff-name-clean-line`. Commit `d9daa86`.
FRONTEND-only. Earner UNTOUCHED (different machine). Deployed LIVE to FORTRESS.

## Scope
1. BUG-1 — asset preview / clicking an image asset = empty. Render the presigned
   URL in the grid + the lightbox/detail.
2. BUG-2 — CRM lead profile transcript chat-view: click a call timeline row →
   full transcript as a chat (CUSTOMER right, AI left, ordered).

## BUG-1 — asset-detail preview (deeper root cause)
Grid was already fine (live LIST `/assets` items carry presigned `url`/`thumb_url`,
`X-Amz-Signature` present → GET 200). The CLICK detail was still broken because:
- live `GET /assets/{id}` returns a NESTED envelope `{asset:{...}, versions:[...]}`;
  the FE `getAsset` returned `res.json()` raw → `full.headline`/meta undefined
  (nested under `full.asset.*`).
- the `asset` object's own `url`/`thumb_url` are RAW UNSIGNED path-style Spaces
  URLs (no `X-Amz-Signature`) → private bucket 403 → blank image. Only the VERSION
  rows carry the presigned signature.

FIX — `lib/assets.ts getAsset` (additive, FE-only):
- flatten `{asset,versions}` → flat `Asset` (`base={...data.asset}`, `base.versions=data.versions`).
- override `base.url`/`base.thumb_url` with the current (else newest) version's
  PRESIGNED url so the native `<img>` (AssetImage) renders the signed image, and
  headline/CTA/meta populate.

`AssetImage` (native `<img>`, presigned src, graceful placeholder), `AssetCard`
(`thumb_url||url` presigned-first), `AssetDetail` (version-url-before-/raw) were
already correct from commit `1005ccb`.

LIVE PROOF (real tenant hmac token, asset svc 10.122.0.4:8310):
- LIST item url/thumb_url → `X-Amz-Signature` present (signed=True).
- DETAIL top_keys = `['asset','versions']`; `asset.url` unsigned; `versions[0].url` signed.

## BUG-2 — CRM call transcript chat-view
Backend `GET /calls/{call_id}/transcript` ALREADY LIVE on the box (caller.py:4282,
box md5 e802d301). NOTE: tracked mirror `droplet_work/caller.py` (ad121cf4) LACKS
the route — box is source of truth (resync the mirror later).
- accepts outbound call id OR room OR inbound session_id.
- returns `{call_id,direction,phone,name,turns:[{role:"ai"|"customer",text,ts,seq}],total}`,
  roles pre-normalized (ai→LEFT, customer→RIGHT), tenant-scoped (outbound BOLA 404,
  inbound RLS).
- SMOKE: room famit-916375548830-ad08ff → 94 turns, correct sides, 200.

Wiring: a CRM timeline `call` row carries `source_id = call.id || room`
(crm/core.py:580) — pass it as `call_id`.

FE:
- `app/crm/client.ts` — `getCallTranscript(callId)` + `CallTranscript`/`TranscriptTurn`
  types. Dormant-safe (404/501/5xx/offline → empty transcript, never an error wall;
  401 → /login). Re-normalizes roles client-side for safety.
- `app/crm/[id]/page.tsx` — a `call` timeline row is a clickable `<button>` (hover
  "View transcript" affordance). Opens `CallTranscriptModal` (Core_2 `Modal isSlidePanel`,
  right slide-over): CUSTOMER bubbles RIGHT (`bg-primary-01/12`), AI bubbles LEFT
  (`bg-b-surface2 ring-1 ring-s-subtle`), ordered, labelled, footer legend; calm
  "No transcript for this call" empty state. Token-pure (matches AIM session player).

## Build + deploy
- `tsc --noEmit` EXIT 0. `npm run build` EXIT 0. BUILD_ID `tuuIjqN7fCf_iEL-obLon`
  (`/crm/[id]` 8.46kB ↑ from 7.09).
- tar `.next`+`app`+`lib` (59MB, md5 `0ccd08fb1a45175c1fcb8cf454f001c7`) → scp to
  FORTRESS root@143.110.247.249 (key do-blr-test/id_ed25519) → md5-gate local==box.
- ONE SSH session: backup-first `*.FIXUIbak.20260613-172953` → extract `_fixui_stage`
  → grep-verify new code in stage → atomic `mv` swap → `chown -R deployuser:deployuser`
  → `systemctl restart famit-panel` ONLY → active PID 248200.
- BUILD_ID `4aXNPr1rvAfpK4ku5dNa7` → `tuuIjqN7fCf_iEL-obLon`.
- PROOF: 200 on `/ /login /crm /creative/library /crm/[id]` on loopback:3001 AND
  panel.famit.in edge; served HTML carries the NEW BUILD_ID (no stale cache).

## Earner gate (before + after) — PASS
- agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED.
- famit-agent MainPID `1477083` / ActiveEnter `2026-06-10 19:58:18` NEVER restarted.
- caller `/health` = 200. No `/run`, no ring test (HARD RULE — DID resting).

## Gotcha
A tight `stat`-every-6s SSH poll-loop watching SCP progress trips the hardened box's
sshd/fail2ban rate-limiting → ConnectTimeout (SCP itself succeeded, md5 matched).
Do the deploy in ONE SSH session; verify with sparse single connections.

## Rollback
On the FORTRESS box: `cd /opt/famit-panel && systemctl stop famit-panel && mv .next .next.bad && mv .next.FIXUIbak.20260613-172953 .next && mv app app.bad && mv app.FIXUIbak.20260613-172953 app && mv lib lib.bad && mv lib.FIXUIbak.20260613-172953 lib && chown -R deployuser:deployuser .next app lib && systemctl start famit-panel`

---

## INTEGRATED RE-VERIFY (2026-06-13, read-only, real HTTP, NO outbound call) — 3/3 PASS

Independent honest verification against the LIVE boxes. Token minted on-box: `tid + '.' + hmac_sha256(tid, /opt/famit-agent/var/secret).hexdigest()` (tenants from `/opt/famit-agent/var/tenants.json`). Asset svc binds the VPC IP `10.122.0.4:8310` (NOT loopback — an empty `.probe_token` 401s; mint the hmac token).

- **PASS — BUG-1 asset-click image.** Founder tenant `21d0a13603da` (axcrio), asset `ca_43a127f9a6f1412b`: `GET /assets/{id}` is the NESTED `{asset,versions}` envelope; FE-folded current-version PRESIGNED url HTTP-GET = **200 image/jpeg 50813B**. Admin tenant (46 assets) sample folded url = **200 image/jpeg 63436B**. List url carries `X-Amz-Signature`. Blank-on-click bug GONE.
- **PASS — BUG-2 transcript chat-view + tenant isolation.** `GET /calls/famit-916375548830-ad08ff/transcript` on the owning (admin) tenant = **200, total=94, direction=outbound, distinct roles {ai,customer}** (ai→LEFT, customer→RIGHT, alternating correctly). SAME room on the founder tenant = **404** (BOLA-guarded, no cross-tenant leak). FE `ChatBubble`: customer `justify-end`+`bg-primary-01/12`, AI `justify-start`+`bg-b-surface2` — token-pure.
- **PASS — FORTRESS deploy live.** `/opt/famit-panel/.next/BUILD_ID` = `tuuIjqN7fCf_iEL-obLon`, famit-panel `active` PID `248200`, `/crm/[id]` in build manifest; 200 on `/ /login /crm /creative/library` on loopback:3001 AND panel.famit.in edge.
- **EARNER GATE PASS (before+after, md5+process+health ONLY — DID resting per HARD RULE, NO /run, NO ring):** `/opt/famit-agent/agent.py` md5 `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED; famit-agent MainPID `1477083` / ActiveEnter `2026-06-10 19:58:18` NEVER restarted; caller `/health`=200; famit-aiasset `active` (not restarted this pass). Nothing edited or restarted on any box during this verify.

Commits in history: `d9daa86` (code), `6940742` (docs). This re-verify pass touched only docs/ledgers locally.
