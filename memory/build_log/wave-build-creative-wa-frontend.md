# Wave build — Creative Studio + WhatsApp Campaign Builder frontend

> Durable per-wave build report. APPEND-ONLY (never delete). Newest unit at bottom.

This wave shipped the Creative Studio frontend (W2a), the WhatsApp Campaign
Builder workspace (W2b), the GenerationLoader hero loader (W1), and finally
UNIT W3 = build-green + nginx `/api/assets/` + FORTRESS deploy to the live
frontend box. Component-level build notes for W1/W2a/W2b live in
`memory/ui-reuse-core2-never-from-scratch.md` (2026-06-11 entries) and the
per-page STATE files. This log focuses on the W3 integration/deploy unit.

---

## UNIT W3 — BUILD GREEN + NGINX + DEPLOY (2026-06-11)

**Result: SHIPPED LIVE. Build EXIT 0 (local + box). All public routes 200.
nginx `/api/assets/` location added + proven routing to backend :8310.**

### 1. Build (local, `C:\Users\kunal\Desktop\caps\famit-panel`)
- `npm install --legacy-peer-deps` → "up to date" (deps already resolved).
- `npm run build` → **"✓ Compiled successfully", EXIT 0**, all 50+ routes
  rendered. NO fixes needed — the W1/W2a/W2b ports left the tree green (no
  leftover PageHeader/Gilroy/missing-component/TS errors).
- Toolchain: node v22.11.0, npm 10.9.0, Next 15 (`package.json` name = `core-2`).

### 2. nginx `/api/assets/` location (frontend box root@143.110.247.249)
- Config = single site `/etc/nginx/sites-available/panel.famit.in` (symlinked in
  sites-enabled), TWO server blocks (`:80` + `:443 ssl`, Cloudflare Full-Strict).
- **Backup first:** `/etc/nginx/sites-available/panel.famit.in.bak.20260610-214347`.
- Inserted a more-specific `location /api/assets/ {` block immediately BEFORE
  each existing `location /api/ {` (both server blocks) via an idempotent python3
  insertion guarded by `grep -q "location /api/assets/"`.
- Block proxies to the AI Asset service on the backend over the VPC:
  `proxy_pass http://10.122.0.4:8310/;` (trailing slash STRIPS the `/api/assets/`
  prefix, so `/api/assets/status` → backend `:8310/status` — matches what
  `lib/assets.ts` expects: ASSET_BASE=`/api/assets`, routes `/status`,
  `/jobs/{id}/stream`, `/generate`, `/assets/...`). Mirrors the existing `/api/`
  block's proxy headers + `limit_req zone=fp_api`, PLUS SSE-friendly directives
  for `/jobs/{id}/stream`: `proxy_set_header Connection ""`, `proxy_buffering off`,
  `proxy_cache off`, `proxy_read_timeout 3600s`.
- `nginx -t` = **syntax ok / test successful**; `systemctl reload nginx` = OK.
- Additive: the existing generic `/api/ → :8209` and `/ → :3001` blocks are
  untouched. Because nginx prefix-matching picks the longest match,
  `/api/assets/*` wins over `/api/*`.

### 3. ⚠️ KEY FINDING — backend :8310 NOT reachable over the VPC yet
- From the frontend box, a TCP connect to `10.122.0.4:8310` is **CLOSED/FILTERED**
  (`:8209` is OPEN). All curls to `:8310/*` returned `000` at the socket level.
- After the nginx change, `https://panel.famit.in/api/assets/status` returns a
  **504** (origin) and the nginx error log shows
  `upstream: "http://10.122.0.4:8310/status" ... upstream timed out (110: Connection timed out)`.
  This is **PROOF the nginx routing is correct** (right upstream, prefix
  stripped) — the failure is purely that backend `:8310` is not exposed to the
  VPC / not listening on the private interface / blocked by the backend firewall.
- Brief = "do NOT touch the backend box." So the fix (open `:8310` on the backend
  to the frontend priv IP 10.122.0.2, or bind the asset service to the VPC iface)
  is a BACKEND/deploy-of-asset-service task, recorded as a blocker — NOT done here.
- Frontend is **dormant-safe by design** (`lib/assets.ts` + DormantCard + the
  WhatsApp `_lib/waapi.ts` safeGet/safePost): a 504/timeout/unreachable `:8310`
  degrades Creative Studio + the WhatsApp AI-template/Creative surfaces to the
  calm premium "coming soon" card — never a broken page. So the panel is safe to
  serve live now; Creative generation simply lights up the moment `:8310` opens.

### 4. FORTRESS deploy (famit-panel → /opt/famit-panel)
- tar (excl node_modules/.next/.git/.env.local/famit-panel.tgz/build.log) →
  22 MB → scp to `/root/famit-panel.tgz` (retry loop, OK attempt 1).
- **BACKUP live dir FIRST:** `cp -a /opt/famit-panel /opt/famit-panel.bak.20260610-214804`
  (1.1 GB, rollback target).
- Extracted OVER live (preserved node_modules/.next/.env.local — `.env.local`
  confirmed present 26 bytes). `chown -R deployuser:deployuser`.
- As `deployuser`: `npm install --legacy-peer-deps` → ok; `npm run build` →
  **"✓ Compiled successfully", EXIT 0**.
- `systemctl restart famit-panel` → **active (running)**, Main PID up,
  `127.0.0.1:3001/login` → 200 on attempt 1.

### 5. VERIFY (route table)
LOCALHOST:3001 — all 200: `/ /login /campaigns /whatsapp /creative
/creative/library /creative/brand /ai-manager /super-admin /run /leads
/billing/overview /workflows`. (`/creative-studio` = 404 — the brief's shorthand;
the AS-BUILT route is `/creative`, per design/cs-workspace-final.md + W2a.)

PUBLIC https://panel.famit.in — all 200: same list (`/ /login /campaigns
/whatsapp /creative /creative/library /creative/brand /ai-manager /super-admin
/run /leads /billing/overview /workflows`).

Asset proxy: `/api/assets/status` → 504/000 (origin routes to :8310, which is
down) while generic `/api/whoami` → 404 (reaches :8209) — routing split PROVEN.

GenerationLoader: component deployed (`components/GenerationLoader/{field.ts,index.tsx}`),
`gl-*` loader classes compiled into the served `.next/static/css` bundle (renders).

Font proof (production served bytes): `/login` body className = `font-inter`,
**zero `gilroy`** references.

### 6. Rollback (if needed)
- App: `rm -rf /opt/famit-panel && cp -a /opt/famit-panel.bak.20260610-214804 /opt/famit-panel && systemctl restart famit-panel`.
- nginx: `cp /etc/nginx/sites-available/panel.famit.in.bak.20260610-214347 /etc/nginx/sites-available/panel.famit.in && nginx -t && systemctl reload nginx`.

### 7. OPEN / HANDOFF
- **BLOCKER (backend side):** expose backend `:8310` to the VPC (open the backend
  firewall to frontend priv 10.122.0.2, or bind the AI Asset service to the
  private iface). Until then Creative Studio generation + WA AI-templates stay
  dormant-safe (coming-soon). Verify after: `curl https://panel.famit.in/api/assets/status`
  should return JSON from :8310 (e.g. `{enabled:...}`), not a 504.
- nginx is permanently wired — no further frontend change needed once :8310 opens.
