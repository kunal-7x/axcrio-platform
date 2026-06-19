# W-FRONTEND-DEPLOY — W15/W16 Consolidated Panel Deploy

**Date:** 2026-06-18
**Branch shipped:** `fix/realtime-voice-kernel-v2`
**Deploy target:** FORTRESS panel box only (`root@143.110.247.249`) — voice/earner box UNTOUCHED.

---

## WHAT WAS DEPLOYED

W15 unified dashboard + GlobalFilters + LeadBadge + W16 WhatsApp media — the new consolidated Next.js panel.

### New / upgraded surfaces visible after deploy:
- **`/` (root)** — W15 consolidated "Dashboard / Today" cockpit, GlobalFilters-driven unified view
- **`/crm`** — CRM list with LeadBadge component
- **`/crm/[id]`** — CRM lead detail
- **`/calls`** — Call Logs
- **`/callbacks`** — Callback queue
- **`/run`** — Run Campaign
- **`/whatsapp`** — WhatsApp (with W16 media support)
- **`/analytics`** — Reports (formerly `/reports` — now at `/analytics` by W15 design)
- **`/ai-manager`** + **`/ai-manager/sessions`**
- **`/super-admin`** — Control plane
- **`/billing`**, **`/booking`**, **`/forms`**, **`/funnels`**, **`/workflows`**

### Routes that return 404 (NOT regressions — by design):
- `/dashboard` — dashboard IS the root `/` in W15 design
- `/reports` — Reports moved to `/analytics`

---

## BUILD DETAILS

| Item | Value |
|------|-------|
| Old BUILD_ID | `xF8YUvBmTwYj_yP4w7WY4` |
| New BUILD_ID | `Zg_bPJTYqOR9zsYkgoJ3c` |
| BUILD_EXIT | 0 (clean, no errors) |
| `package.json` md5 | unchanged (no dependency churn) |
| `package-lock.json` md5 | unchanged |
| Service status | `active`, `NRestarts=0`, no journal errors |
| Local smoke (127.0.0.1:3001) | 200 OK, new BUILD_ID confirmed |
| Public smoke (Cloudflare) | 200 OK, new BUILD_ID confirmed |

---

## LIVE URL

**https://panel.famit.in** (Cloudflare -> nginx -> next on 127.0.0.1:3001)

---

## BACKUP PATHS (on box root@143.110.247.249)

| Backup | Path |
|--------|------|
| `.next` hot-swap backup (W16) | `/opt/famit-panel/.next.W16bak.20260618-191059` |
| Full source tar (92M) | `/opt/famit-panel.W16bak.20260618-191059.tar.gz` |
| Prior safety net (.next) | `/opt/famit-panel/.next.leadsmgmtbak.20260615-124143` |

---

## ROLLBACK COMMAND

```bash
ssh -i ~/.ssh/do-blr-test/id_ed25519 root@143.110.247.249 \
  "rm -rf /opt/famit-panel/.next && \
   cp -a /opt/famit-panel/.next.W16bak.20260618-191059 /opt/famit-panel/.next && \
   chown -R deployuser:deployuser /opt/famit-panel/.next && \
   systemctl restart famit-panel && \
   sleep 4 && \
   curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3001"
```

Should return `200`. If it does, the old build is live again.

---

## SECRETS / ENV

- `.env.local` on box (`NEXT_PUBLIC_API_BASE=/api`) preserved, excluded from ship tar, verified intact.
- No voice box IP baked into the build.
- No secrets committed or shipped.

---

## DISK (post-deploy)

- Pruned ~7GB of stale `.next.*bak` dirs before deploy.
- Box now at 73% used / 14GB free.

---

## STATUS: DEPLOYED
