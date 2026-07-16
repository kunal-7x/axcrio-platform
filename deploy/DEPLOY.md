# Deploying Haptica AI (panel + backend)

Turnkey Docker deploy for the **Haptica AI** panel and the `caller.py` backend.
Designed to drop onto an **existing box without disturbing whatever already runs
there** (e.g. the live `panel.famit.in` on `famit-panel-2`).

> Status: **prepared, not yet deployed.** Run the steps below once you have SSH
> access to the target box. Nothing here touches DigitalOcean infra by itself.

---

## What this deploys
- **frontend** — the Next.js 15 / React 19 panel (`famit-panel/`), `next start` on container :3000.
- **backend** — `droplet_work/caller.py` (FastAPI) via uvicorn on container :8091.

**Not** included: the LiveKit **voice agent** (`agent.py`). It needs raw SIP/RTP
UDP and runs as its own worker — add it later (it already lives on `famit-livekit`).

## How it's wired (non-disruptive)
```
browser ──► host :${PANEL_PORT:-3100} ──► [frontend container :3000]
                                              │  Next proxies /api/* ──► [backend container :8091]
                                              ▼
                                          (live site on :80/:443 is untouched)
```
- The panel publishes on **:3100 by default** (not 80/443) → no clash with the live site.
- The backend is **internal-only** (no host port) — reached only by the panel via the Docker network.
- Backend data (admin secret + tenants, `FAMIT_VAR`) lives in a named volume `haptica-data`.

---

## Prerequisites on the box
- Docker + Docker Compose v2 (`docker compose version`)
- `git`
- The backend's real env values (the existing box's `droplet_work/.env` is the easiest source)

## Deploy — step by step
```bash
# 1. SSH in (use the authorized deploy key)
ssh root@<box-ip>

# 2. Get the code
git clone https://github.com/NikhilVerma12/haptic-by-famit-ai.git
cd haptic-by-famit-ai
# (or: cd haptic-by-famit-ai && git pull)

# 3. Provide backend env (NEVER commit this file)
cp deploy/env.deploy.example deploy/.env.deploy
#   then edit deploy/.env.deploy — easiest is to copy the box's working backend env:
#   cp /path/to/existing/droplet_work/.env deploy/.env.deploy   # then add PANEL_PORT=3100
nano deploy/.env.deploy

# 4. One command — build + start + healthcheck
chmod +x deploy/deploy.sh
./deploy/deploy.sh
```

## Verify
```bash
docker compose -f deploy/docker-compose.yml ps
curl -I http://127.0.0.1:3100/login          # expect HTTP 200
docker compose -f deploy/docker-compose.yml logs -f frontend backend
```
Open `http://<box-ip>:3100/login` in a browser. Log in with a real tenant to
confirm the backend is reachable (the panel calls it through `/api/*`).

## Go live (cutover — do this only after verifying)
The live site keeps serving the whole time. To expose Haptica AI:
- **Staging subdomain (recommended):** point e.g. `haptica.famit.in` via Cloudflare
  (or an nginx/Caddy vhost) at `http://<box-ip>:3100`. Cloudflare terminates TLS.
- **Full cutover:** once happy, repoint the main hostname (or set `PANEL_PORT=80`
  in `.env.deploy` after stopping the old site) — your call, deliberately.

## Update later
```bash
git pull && ./deploy/deploy.sh        # rebuilds + restarts; data volume persists
```

## Roll back
```bash
docker compose -f deploy/docker-compose.yml down     # stops Haptica AI, keeps data
```
The live site is unaffected at every step.

---

## Troubleshooting
- **Backend import error / `ModuleNotFoundError`** — `deploy/requirements.backend.txt`
  is a curated list. The authoritative set is a freeze from the working box venv:
  `</path/to>.venv/bin/python -m pip freeze > deploy/requirements.backend.txt`, then
  rebuild. Add anything a backend module needs (e.g. `boto3`, `redis`, `numpy`).
- **Port 3100 already in use** — set `PANEL_PORT` to a free port in `.env.deploy`.
- **Panel loads but login fails** — backend env is incomplete; recopy the box's
  `droplet_work/.env` into `deploy/.env.deploy` and `./deploy/deploy.sh` again.
- **next/image Spaces errors** — already handled (`unoptimized` + remotePatterns).

## Security
- `deploy/.env.deploy` is **gitignored** — never commit real secrets.
- The backend port is not published to the host (internal Docker network only).
- `droplet_work/` is committed **without** any `.env`; secrets come only from `.env.deploy`.
