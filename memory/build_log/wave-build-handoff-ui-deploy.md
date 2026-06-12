# PER-TENANT HANDOFF TEAM UI — FORTRESS DEPLOY — 2026-06-12

Scope: deploy the per-tenant Handoff/Escalation Team panel UI (built + committed
`65dbe26` on `feat/premium-ui` by the build session) to the LIVE frontend box.
FRONTEND ONLY (famit-panel-2). Backend / voice / WhatsApp / caller.py / agent.py
NOT touched — this box has no `/opt/famit-agent` (NO_AGENT_DIR), so the earner is
physically out of reach here.

## CODE (committed `65dbe26` on feat/premium-ui, by the build session)
Wires the LIVE `/brain/handoff*` contract (tenant-from-token, write-role gated)
into the panel. 9 files, +1048:
- `lib/api.ts` — `HandoffMember` type + `getHandoffTeam()` (dormant-safe: 404/network
  -> empty `{team:[]}`, tolerates bare array OR `{handoff:[]}`/`{team:[]}`, sorts by
  priority, default-true `enabled`) / `addHandoffMember()` (POST /add, omit priority
  -> backend auto-appends max+1) / `removeHandoffMember(phone)` (DELETE ?phone=) /
  `saveHandoffOrder(list)` (PUT JSON {handoff:[…]} re-numbered — the ONE call behind
  reorder + enable-toggle + bulk save) + `HandoffError` + `explainHandoffError()`
  ({error} body -> plain English; invalid-phone 400 -> "must start with +91").
- `app/ai-manager/_handoff.tsx` (NEW, 449) — ONE reusable `<HandoffTeam compact?>`
  manager: list / add-modal / reorder up-down chevrons / enable Switch / delete trash;
  optimistic PUT with roll-back-on-failure; client-side +91 normalize as instant
  feedback (backend still the real validator); read-only roles see list, NO edit
  controls; empty -> calm "No handoff team yet" block.
- `app/ai-manager/handoff/page.tsx` (NEW) — dedicated management view (Layout +
  top explainer "the AI rings these people in order — first available is bridged
  live; if none answer the hot lead goes to their WhatsApp").
- `app/ai-manager/live/page.tsx` (NEW, 282) — Live Calls monitor; polls
  GET /ai-manager/live every 3s; renders the handoff stepper
  "Dialing #1 -> #2 -> Bridged" (green) / "Failed -> WhatsApp + callback" (red);
  attempt index parsed OUT of the backend "Dialing #N" label (zero schema change).
- `app/ai-manager/_lib.ts` — `getAimLive()` + `aimLiveCalls()`/`handoffPhase()`/
  `handoffAttemptNo()`.
- `contstants/navigation.tsx` — "Live Calls" + "Handoff Team" UNKEYED children
  under the manager-gated AI Manager group (never entitlement-hidden).
- `app/run/page.tsx` — `<HandoffTeam compact />` as card #7 in the left rail
  before the launch bar (same component + same /brain/handoff* calls).
- Reference kit (Card/Button/Badge/Icon/Modal/Switch), Inter Display, zero raw hex.
- LOCAL gate (this deploy session): `npx tsc --noEmit` EXIT 0.

## FORTRESS DEPLOY (this session) — followed the learning #5 recipe exactly
Box `root@143.110.247.249` (famit-panel-2, 2GB RAM, swappiness 10, permanent 2G
`/swapfile`), SSH key `~/.ssh/do-blr-test/id_ed25519`, app `/opt/famit-panel`
(deployuser, systemd `famit-panel` = `next start -H 127.0.0.1 -p 3001`), node
v20.20.2, nginx `/`->3001, Cloudflare edge. NO git repo on box -> tarball deploy.

1. `git archive --format=tar.gz feat/premium-ui:famit-panel` -> 22.7MB. Ships ONLY
   COMMITTED content (node_modules/.next/.env.local are gitignored -> NOT in archive
   -> extract-over PRESERVES box copies; also dodges the heavy parallel-session dirty
   working tree). Archive root = panel CONTENTS (no famit-panel/ prefix). Scanned:
   zero `.env`/secret files inside.
2. scp + md5-verify on box (`3f33049962d8093328330681ba87f907` matched).
3. Backup-first: `cp -a /opt/famit-panel /opt/famit-panel.HUIbak.1781288658` (4.3G).
   Rollback = `rm -rf /opt/famit-panel && mv /opt/famit-panel.HUIbak.1781288658
   /opt/famit-panel && systemctl restart famit-panel`.
4. `tar xzf -C /opt/famit-panel` + `chown -R deployuser:deployuser`. New files landed.
5. OOM swap: temp `/swapfile.build` 4G (fallocate/chmod600/mkswap/swapon) +
   `sysctl vm.swappiness=60` (the resident 2G swap is NOT enough for next build).
6. Build as deployuser: `npm install --legacy-peer-deps` then
   `NODE_OPTIONS=--max-old-space-size=3072 npm run build` -> **EXIT 0**,
   "✓ Compiled successfully", "✓ Generating static pages (52/52)". Both new routes
   in the table: `ƒ /ai-manager/handoff` 1.57kB, `ƒ /ai-manager/live` 2.46kB.
   (NOTE: on LINUX the build exits 0 cleanly — the Windows-only `kill EPERM` worker-
   teardown quirk the build session saw does NOT happen on the box.)
7. `systemctl restart famit-panel` (ONLY that unit) — PID 178771 -> 188199, active,
   ActiveEnter after the build.
8. VERIFY 200 + fresh BUILD_ID:
   - OLD_BUILD_ID `VPtGSsTgpNpL2uccV0SnA` -> NEW `XyeGd-iyCjs-emBYS8-q8`.
   - Loopback :3001: /ai-manager/handoff 200, /ai-manager/live 200, /run 200,
     /login 200; served /login HTML carries the NEW BUILD_ID (no stale .next).
   - Public edge https://panel.famit.in: handoff 200, live 200, /run 200, /login 200.
9. TEARDOWN (critical): `swapoff /swapfile.build && rm -f /swapfile.build &&
   sysctl vm.swappiness=10`; confirmed only permanent 2G `/swapfile` remains,
   swappiness=10, NOT in /etc/fstab. Removed `/tmp/panel-hui.tar.gz`.

## EARNER SAFETY
This box is FRONTEND ONLY — `ls /opt/famit-agent` = NO_AGENT_DIR; only `famit-panel`
is the app unit (+ DO/crowdsec/postfix system services). No caller.py/agent.py here,
so a deploy CANNOT touch the voice earner. Only `famit-panel` was restarted.

## FOUNDER PATH
Sidebar -> AI Manager -> Handoff Team (`/ai-manager/handoff`). Live progression =
AI Manager -> Live Calls (`/ai-manager/live`). Also embedded in Run a Campaign
(`/run`, card #7) so escalation people can be reviewed/added right before launch.

## RESIDUAL
- `/ai-manager/live` shows real progression only when a live handoff is in flight
  (GET /ai-manager/live emits "Dialing #N" + target); idle = calm empty state.
- Backend list is per-tenant from token; an admin-token session sees the admin
  seed (+916375548830 p1, +917861019021 p2). A real vendor sees only their own.
