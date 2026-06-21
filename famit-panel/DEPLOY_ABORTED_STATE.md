# DEPLOY ABORTED — Panel box OOM crash (2026-06-18/19)

## TL;DR
Gated deploy of merged panel build (HEAD `6272505`) ABORTED at Step 4.
On-box `npm run build` was **OOM-killed** (SIGKILL on Next.js build worker).
The panel box `143.110.247.249` then went **unreachable** (SSH port 22 TCP timeout,
all ports blocked). It needs a **manual power-cycle from the DigitalOcean console**.

## Earner-safe: CLEAN
Voice/earner box was NEVER touched. Only ever SSH'd to the panel box `143.110.247.249`.
Never touched `famit-agent` / `agent.py` / `caller.py`.

## What completed
- Step 1 PASS: local HEAD = `6272505` (filter-wiring) over `9e43a91` (nav-restore). Both present.
- Step 2 PASS: 85M source tar shipped + extracted over `/opt/famit-panel` (node_modules/.git/.next preserved).
  Verified `Brand Kit` / `/creative/brand` now in box `contstants/navigation.tsx`.
- Step 3 PASS: live `.next` backed up to `/opt/famit-panel/.next.RBbak.20260618-201101`.
- Step 4 FAIL: `npm run build` OOM-killed. Output: `Next.js build worker exited with code: null and signal: SIGKILL`.
  No new `.next` produced; old `.next` untouched. Box went unreachable right after.
- Steps 5-7: NOT REACHED.

## Box state as of abort
- SSH port 22: TCP timeout (every attempt, IPv4 + IPv6).
- App port 3001 (direct): timeout.
- HTTPS panel.famit.in: 200 (Cloudflare cached — origin likely down).
- Diagnosis: OOM event killed sshd / hung the droplet. Not self-recovering after ~1h.

## USER ACTION REQUIRED
Power-cycle the droplet from DO console:
  DigitalOcean → Droplets → famit-panel-2 (143.110.247.249) → Power → "Power Cycle"
After reboot, `famit-panel` service should auto-start on the OLD (pre-build) `.next`,
which is intact. Site should return to current rolled-back-build state.

## ROLLBACK (only if box comes back in a bad state — old .next was NOT overwritten so likely unneeded)
ssh -i ~/.ssh/do-blr-test/id_ed25519 root@143.110.247.249 'rm -rf /opt/famit-panel/.next && cp -a /opt/famit-panel/.next.RBbak.20260618-201101 /opt/famit-panel/.next && chown -R deployuser:deployuser /opt/famit-panel/.next && systemctl restart famit-panel'

## NEXT ATTEMPT — DO NOT BUILD ON THE BOX (it OOMs)
The box lacks RAM for a Next.js 15 prod build. Two safe paths:
1. PREFERRED — ship the pre-built `.next` from local (local build already passed,
   BUILD_ID `VNXiFciwSb00cwCATUFqK`). Tar ONLY `.next` locally → scp → extract on box →
   chown deployuser → restart. No on-box build = no OOM.
   NOTE: local `.next` BUILD_ID must match the shipped source; rebuild locally if source changed.
2. Or add a 2GB swapfile on the box before any on-box build:
   `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`
   then `npm run build`. (swapfile is slower but won't OOM-kill.)
