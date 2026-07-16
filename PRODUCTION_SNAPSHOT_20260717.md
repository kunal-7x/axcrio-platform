# Production Snapshot — haptica-prod (DigitalOcean blr1) — 2026-07-17

**What this branch is:** a faithful capture of the code that was *actually running in production*
on droplet `haptica-prod` (`168.144.85.191`, DO Bangalore) at `/opt/haptica`, taken 2026-07-17.

**Why it exists:** before this commit, **the live production code was not in git anywhere.**
It existed on exactly one droplet, with no backup, on an 80%-full disk, in an account flagged `warning`.

## The gap this closes

| | Live droplet (2026-07-17) | Newest copy previously in git |
|---|---|---|
| `droplet_work/agent.py` | **196,617 bytes** (mtime Jul 6) | 92,514 bytes (`restore/live-earner-snapshot-20260621`) |
| md5 | `9b3a0ebc83d45235994162ff1a1480f6` | `c33c03e2ea380b210863a7177729ae9c` |

`agent.py` — the core of the earning product — was **more than 2× larger in production than
anything committed**. This branch adds those ~1,736 lines. 865 files here had never been committed.

## Provenance & integrity

- Pulled via `tar` over SSH from `root@168.144.85.191:/opt/haptica`, 2026-07-17.
- **Verified:** extracted `agent.py` md5 matches the live file byte-for-byte (`9b3a0ebc…`, 196,617 B).
- Base: `restore/live-earner-snapshot-20260621` (`55fe27c`) — the closest ancestor that contained `agent.py`.
- **Non-destructive:** 0 deletions. Nothing in the repo was removed or overwritten by this snapshot.
- Excluded (regenerable): `node_modules/`, `.next/`, `__pycache__/`, `*.pyc`, `*.tgz`.

## ⚠️ Secrets are NOT in this branch — by design

All 17 `.env.deploy*` files (**119 populated keys**, incl. `DO_API_TOKEN`, `AWS_ACCESS_KEY_ID`/`SECRET`,
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GROQ_*`, `ELEVEN_API_KEY`, `VOBIZ_PASSWORD`, `LIVEKIT_API_SECRET`)
were **quarantined before commit** and are held outside git.

A deep pattern scan of every staged blob returned **zero live secrets**. The only `AKIA…` string present is
`AKIAIOSFODNN7EXAMPLE` — AWS's public documentation placeholder, not a credential.

**To redeploy you need the vault** — the runtime config is not reconstructible from this branch alone.
See `.env.example` for the shape. Ask the repo owner for the real values.

## What production actually was (measured, not assumed)

- 13 containers via Docker Compose at `deploy/` (`docker-compose.yml` + `.voice.yml` + `.twenty.yml` + `.tls.yml`)
- livekit-server · livekit/sip (5060 tcp+udp, RTP 10000-10100/udp) · livekit/egress · backend (8091) ·
  worker (the voice agent) · frontend (3100→3000) · caddy (80/443) · clickhouse · redis ·
  Twenty CRM + worker + postgres:16 + redis
- Domain `haptica.famit.in` → Caddy → frontend; TLS via Cloudflare DNS-01; DNS at Cloudflare
- **No app Postgres.** `DATABASE_URL` was empty — production state is JSON files on the
  `haptica-ai_haptica-data` volume (`calls.json`, `cost_ledger.json`, `billing.json`, …), ~4.5 MB total.
- SIP trunk: VOBIZ (`2c24f731.sip.vobiz.ai`), reachable only from whitelisted IPs `13.203.7.132` / `65.2.100.211`.

**Data is not in this branch** (it is state, not code): ~1.65 GB total —
`haptica-data` 4.5 MB · `clickhouse-data` 1.55 GB · `twenty-db-data` 85 MB.

## Status

This is a **snapshot for safety and portability**, not a proposed code change. It is the base for
migrating off DigitalOcean. Review at your leisure — its job was to make the code survive
the loss of the droplet. It now does.
