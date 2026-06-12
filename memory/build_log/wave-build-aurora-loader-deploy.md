# GENERATION LOADER UPLIFT — "Signal Aurora" — BUILD + FORTRESS DEPLOY — 2026-06-12

Scope: replace the cheap "Rendering creative / Thinking" grey-dots-on-black
generation loader with a premium living WebGL aurora window (Google Flow / Runway
/ Midjourney class). Drop-in on the existing `GenerationLoader` (public API
unchanged) so image-gen + WhatsApp template-gen + banner-gen all upgrade at once.
FRONTEND ONLY (famit-panel). Backend / voice / WhatsApp backend NOT touched.

## CODE (committed `044dafb` on feat/premium-ui, by the build session)
- NEW `components/GenerationLoader/aurora.ts` — raw-WebGL fragment shader
  (domain-warped 4-octave FBM value-noise, 3-stop Signal-blue palette #2a85ff,
  central bloom + conic shimmer sweep + film grain). 1 draw call/frame, oversized
  -tri quad, powerPowerPreference low-power, dpr cap 2, CPU analytic luma mirror
  (no GPU readback), context-lost handling + dispose(). Runs on the USER gpu.
- `components/GenerationLoader/field.ts` — sparks ride the aurora (brighten/grow/
  blue-tint on crests, additive `lighter` glow).
- `components/GenerationLoader/index.tsx` — aurora layer under spark canvas; single
  eased `intensity` driven by real backend phase (queued .22 -> rendering 1.0 ->
  done .4); framer-motion@12.5 (already a dep, NO new npm dep) status crossfade;
  GL disposed on unmount + CSS-field switch; reuses RAF-pause-on-hidden + IO.
- `app/globals.css` — aurora/grain/vignette chrome + token-pure palette vars
  `--gl-aur-a/b/c` + `--gl-spark-tint` (on --primary-01) + animated gradient-mesh
  fallback `.gl-field--mesh` (reduced-motion / no-WebGL).
- Wired (no changes needed, already pass the contract): whatsapp/_steps/
  TemplatesStep.tsx, whatsapp/_steps/BannerStep.tsx, creative/_components/
  GenerationQueue.tsx.
- LOCAL gate: tsc --noEmit EXIT 0; npm run build EXIT 0.

## FORTRESS DEPLOY (this session)
Box `root@143.110.247.249` (famit-panel-2, 2GB RAM, swappiness 10, permanent 2G
/swapfile). App `/opt/famit-panel` (deployuser; systemd `famit-panel` ->
`next start -H 127.0.0.1 -p 3001`). nginx `/`->3001. SSH key
`~/.ssh/do-blr-test/id_ed25519`.
- BASELINE pre-deploy: MainPID 169243 (start 14:50:28 UTC), BUILD_ID
  iXqk1zARuKtCYGcHcvQcS; loopback+edge /login /whatsapp /campaigns /creative all
  200; disk 59%. No git repo on box (tarball-deployed).
- TARBALL: `git archive feat/premium-ui:famit-panel` -> /tmp/famit-panel-aurora.tgz
  (22M, md5 bb86917cbe312ad2ffbddd10ce9d29ba). git archive = ONLY committed content
  (node_modules/.next/.env.local are gitignored so NOT in archive -> extract-over
  preserves the box copies). Avoided shipping the 45 unrelated dirty working-tree
  files from a parallel session.
- BACKUP: `cp -a /opt/famit-panel /opt/famit-panel.CUIbak.1781281898` (4.2G).
  ROLLBACK = rm -rf /opt/famit-panel && mv that back && systemctl restart famit-panel.
- EXTRACT over /opt/famit-panel (archive root = panel contents, no prefix) ->
  aurora.ts/field.ts/index.tsx landed; .env.local + node_modules preserved; chown
  deployuser.
- OOM SWAP: added TEMP 4G /swapfile.build (swapon) + swappiness 60 for the build
  (2GB box OOM-kills next build otherwise; swap peaked ~3.3G in use during build).
- BUILD ON BOX (deployuser, node v20.20.2): npm install --legacy-peer-deps (deps
  current) + `NODE_OPTIONS=--max-old-space-size=3072 npm run build` -> EXIT 0,
  53 routes, new BUILD_ID mMfcn-1xYHnnF52JegjFf.
- RESTART famit-panel ONLY: MainPID 169243 -> 174963 (start 16:43:38 UTC, AFTER
  build). Served /login HTML embeds BUILD_ID mMfcn-1xYHnnF52JegjFf (not stale .next).
- TEARDOWN: swapoff + rm /swapfile.build; swappiness back to 10; verified NOT in
  /etc/fstab; only permanent 2G /swapfile remains.
- CLEANUP: rm /tmp tarball.

## REGRESSION GATE — PASS
- Loopback :3001 200: /login /whatsapp /campaigns /creative /creative/library.
- Public edge (Cloudflare https://panel.famit.in) 200: /login /whatsapp /campaigns
  /creative.
- Aurora compiled into live bundle: static chunk 9767-e11bc2fae041de56.js + css
  478236b9551cd93a.css (gl-aur-a token + aurora field present).
- journal since restart = ZERO error/exception. famit-panel + nginx active.
- Backend NOT touched (frontend box has no caller.py).

## WHERE THE FOUNDER SEES IT (live now on panel.famit.in)
- /whatsapp -> Templates step (template generation) + Banner step (banner gen).
- /creative -> the generation queue (AI image/asset gen).
Any "generate" action across these now shows the fluid aurora generation window.

## STATUS: LIVE. Build EXIT 0; famit-panel active (PID 174963); loopback+edge 200.
Temp build swap removed, swappiness restored to 10. Backup
/opt/famit-panel.CUIbak.1781281898 retained for rollback.
