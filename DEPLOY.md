# DEPLOY — run this product on any cloud

**This repo is the product.** AWS, GCP, Azure, Hetzner, Vultr, Linode, Oracle, DigitalOcean, or a
laptop under your desk — the procedure is identical, because everything host-specific is either
auto-detected or lives in one env file.

> **If you are an AI agent** (Claude Code or similar) and someone said *"self-host my product on this
> cloud"*: read this file top to bottom, then run the three commands in **Quick start**. Everything you
> need is in this repo except `deploy/.env.deploy` (secrets) and the data bundle — ask the owner for both.
> **Read `deploy/KNOWN_ISSUES.md` first** — several issues are harmless on the old box and become
> outages on a new one (especially #1 if you put this behind a load balancer).

---

## What this is

An AI voice-telecaller. Outbound calls to Indian numbers over a VOBIZ SIP trunk, LiveKit for media,
STT/LLM/TTS for the conversation, a Next.js control panel, Twenty CRM, ClickHouse analytics.

**13 containers, one `docker compose` command.**

| Layer | Service | Where it comes from |
|---|---|---|
| Voice | `livekit`, `sip`, `egress` | **upstream open source** (pinned by digest) |
| Voice | `worker` — *the agent* | **this repo** (`droplet_work/`, built from `Dockerfile.worker`) |
| App | `backend` | **this repo** (`droplet_work/caller.py`, `Dockerfile.backend`) |
| App | `frontend` | **this repo** (`famit-panel/`, `Dockerfile.frontend`) |
| Edge | `caddy` | **this repo** (`Dockerfile.caddy`) — TLS via Cloudflare DNS-01 |
| Data | `clickhouse`, `redis` | upstream |
| CRM | `twenty`, `twenty-worker`, `twenty-db`, `twenty-redis` | upstream |

The open-source pieces are **pulled from their registries, not vendored** — nothing to back up. What is
irreplaceable is *your* code (the agent, backend, frontend), and it is all here.

---

## Quick start — bare Ubuntu 22.04/24.04 → running product

```bash
# 1. get the code
git clone https://github.com/kunal-7x/axcrio-platform.git && cd axcrio-platform
git checkout live/do-prod-truth-20260717        # the branch that matches production

# 2. supply the one thing that isn't in git
cp deploy/.env.deploy.example deploy/.env.deploy
#    fill in the 66 empty values (the 172 non-empty ones are real production defaults)

# 3. go
sudo ./deploy/bootstrap.sh --data /path/to/haptica-data-bundle-YYYYMMDD.tar.gz
```

`bootstrap.sh` is idempotent and does the whole host: docker, 4GB swap, ufw + fail2ban,
Cloudflare-only 80/443, VOBIZ-only 5060, RTP open, **chains DOCKER-USER→ufw so docker can't bypass the
firewall**, then builds, starts, restores data, and verifies.

First run pulls ~14GB and builds 4 images: **10–20 minutes**.

### Sizing
Production ran on **4 vCPU / 8GB / 160GB** and used ~4GB RAM at load 0.41. **8GB is the floor** — the
Next.js build OOMs below it without swap (bootstrap adds 4GB swap for this reason). Disk ≥40GB.

---

## The three things that are not in git — by design

| | What | Where to get it |
|---|---|---|
| 1 | **`deploy/.env.deploy`** — 238 keys, 66 of them secret (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GROQ_*`, `ELEVEN_API_KEY`, `VOBIZ_PASSWORD`, `LIVEKIT_API_SECRET`, `CF_API_TOKEN`, AWS keys…) | the owner's vault. `.env.deploy.example` has every key name + all non-secret defaults |
| 2 | **Data bundle** (~3MB) — `calls.json`, `cost_ledger.json`, ClickHouse rows, Twenty CRM | `./deploy/backup-data.sh` on the old host |
| 3 | **DNS + TLS** — `haptica.famit.in` A-record | Cloudflare. Caddy issues TLS itself via DNS-01 once `CF_API_TOKEN` is set |

**There is no application database to migrate.** `DATABASE_URL` is empty. State is JSON files on the
`haptica-ai_haptica-data` volume. That surprises people — see `KNOWN_ISSUES.md` #8.

---

## Cutover to a new cloud (safe order)

1. **Old host:** `./deploy/backup-data.sh` → copy the bundle + `.env.deploy` to the new host **out of band** (scp — never git).
2. **New host:** `sudo ./deploy/bootstrap.sh --data <bundle>` → wait for `verify.sh` to pass.
3. **Prove telephony:** `./deploy/verify.sh --call` → **a human listens to a real call.**
   A green container check proves nothing about whether the phone rings. If VOBIZ turns out to need the
   new IP whitelisted (`KNOWN_ISSUES.md` #5), this is where you find out — before any DNS change.
4. **Freeze the old host:** stop `backend` + `worker` so nothing new writes to the JSON store, then
   re-run `backup-data.sh` and `restore-data.sh --force` for a final delta. Skipping this loses every
   call between step 1 and cutover.
5. **Flip DNS:** Cloudflare A-record → new IP. Caddy gets certs automatically.
6. **Keep the old host running for ~7 days.** It is your rollback. Rolling back = flip the A-record back.
7. Only then decommission.

**Do not do steps 5–7 on a day you aren't watching.**

---

## Commands

```bash
sudo ./deploy/bootstrap.sh            # host → running product (idempotent)
sudo ./deploy/bootstrap.sh --no-deploy # prepare the host only
./deploy/verify.sh                    # prove infrastructure
./deploy/verify.sh --call             # prove telephony (real call, real money)
./deploy/backup-data.sh               # capture all state → one ~3MB bundle
./deploy/restore-data.sh <bundle>     # restore onto a fresh host
```

Manual compose (what bootstrap runs) — **note the file order; `pin.yml` must be last**:
```bash
docker compose -f deploy/docker-compose.yml \
               -f deploy/docker-compose.tls.yml \
               -f deploy/docker-compose.voice.yml \
               -f deploy/docker-compose.twenty.yml \
               -f deploy/docker-compose.pin.yml \
               --env-file deploy/.env.deploy up -d --build
```

## Housekeeping you must not skip

```bash
# The old box hit 80% disk. 107GB of the 123GB "used" was docker build cache.
echo '0 4 * * 0 root docker builder prune -f --filter until=168h' > /etc/cron.d/docker-prune

# Nothing else backs up the JSON store. It IS the database.
echo '0 3 * * * root cd /opt/axcrio-platform && ./deploy/backup-data.sh /var/backups/haptica' > /etc/cron.d/haptica-backup
```

## Cloud-specific notes

- **AWS / GCP / Azure / any managed LB** → **read `KNOWN_ISSUES.md` #1 first.** `/health` returns 503
  permanently. Point the LB at `/health?deep=0` or the product is dead on arrival.
- **Hetzner** — no India region; nearest is Singapore (~51ms from Mumbai vs ~0ms in Bangalore). This is
  real-time voice for Indian callers. Also: no stated SIP/VoIP policy, and Singapore egress is €7.40/TB.
- **Oracle Cloud free tier (Mumbai)** — 4 OCPU/24GB Ampere is **arm64**. The `FROM` bases used here are
  multi-arch, but this has **not been tested on ARM**. Verify a real call before trusting it.
- **Anywhere without a cloud firewall** (Hetzner, Vultr, bare metal) → `KNOWN_ISSUES.md` #3 is load-bearing.
  DO's `haptica-fw` is currently masking the docker/ufw bypass. bootstrap.sh fixes it; don't `--skip-harden`.
