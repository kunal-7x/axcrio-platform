# Known issues — read before deploying to a new cloud

Found by inspecting the **live production box** (haptica-prod, DO blr1) on 2026-07-17.
None of these are new. They are all live in production today. They are listed here because
several of them are harmless *on the current box* and become **outages on a different cloud**.

---

## 🔴 1. `/health` returns 503 permanently — will take the product down behind a load balancer

**Measured on live production, right now:**
```json
{"status":"unhealthy","checks":{
  "db":   {"ok":false,"error":"ImportError(\"cannot import name 'engine' from 'db' (unknown location)\")"},
  "redis":{"ok":false,"error":"ModuleNotFoundError(\"No module named 'redis'\")"},
  "livekit":{"ok":true}}}
```
`droplet_work/caller.py:3885` — the logic is `code = 200 if db_ok else 503`.

- The `db` check does `from db import engine` — a **SQLAlchemy engine this architecture does not have.**
  `DATABASE_URL` is empty; app state is JSON files on a volume. The check is vestigial.
- The `redis` check fails because the `redis` python package isn't installed in the backend image.
- So `db_ok` is *always* False → **`/health` has always returned 503.**

**Why it's harmless today:** nothing consumes it. No load balancer; no compose `healthcheck:` on backend.

**Why it breaks a cloud move:** the moment this sits behind **AWS ALB/NLB, GCP LB, Azure LB, a k8s
readiness probe, or DO's own LB**, the health check fails → the target is marked unhealthy → **100% of
traffic is dropped on arrival.** It will look like "the migration broke it". It didn't; this did.

**Fix before using any managed load balancer** (pick one):
- point the LB at **`/health?deep=0`** — that path already returns `{"status":"ok"}` and is a true liveness check; **or**
- make `_hc_db` check the real data plane (can it read/write the `haptica-data` dir?) instead of importing `engine`; **or**
- `pip install redis` in `Dockerfile.backend` and drop the bogus `db` check.

`deploy/verify.sh` deliberately probes `/health?deep=0` and ignores the deep check.

---

## 🟠 2. Upstream images were pinned to `:latest` — a redeploy would silently change LiveKit

`livekit/livekit-server`, `livekit/sip` (running **v1.5.0**), `livekit/egress` were all `:latest`.
A fresh deploy months from now would pull whatever is current — a different LiveKit than this product
was tuned against, with no warning.

**Handled:** `deploy/docker-compose.pin.yml` pins every upstream image to the exact digest that was
running in production on 2026-07-17. Keep it last in the `-f` chain. To upgrade deliberately: drop it,
verify with a real call, re-capture digests.

**Still floating (accepted):** the `FROM` bases in `Dockerfile.{backend,frontend,worker,caddy}`
(`python:3.12-slim`, `node:20-alpine`, `caddy:2-alpine`). Pinning these was not done because it changes
build inputs and could not be verified end-to-end in this pass. Documented rather than silently changed.

---

## 🟠 3. Docker bypasses ufw — every published port is internet-facing regardless of firewall rules

Docker writes its own `DOCKER-USER` iptables rules that are evaluated **before** ufw. A box that
*looks* firewalled (`ufw status` → active, 5060 restricted to VOBIZ) is in fact exposing 5060,
10000-10100, 3100 to the whole internet.

On the current box this is masked by **DigitalOcean's cloud firewall** (`haptica-fw`), which sits
outside the host. **Most clouds do not give you that by default** — and on Hetzner/Vultr/bare metal
you'd be wide open with a green `ufw status`.

**Handled:** `bootstrap.sh` chains `DOCKER-USER` → `ufw-user-input`, and `verify.sh` asserts it.

---

## 🟡 4. RTP media must stay open to the world — do not "tighten" it

`ufw allow 10000:10100/udp` looks careless next to the locked-down 5060. It is deliberate.
SIP *signalling* comes from VOBIZ's edge (`13.203.7.132`, `65.2.100.211`); **RTP media can arrive from
any carrier/relay IP.** Restricting the RTP range to the signalling IPs produces the classic failure:
**the call connects, then there is silence.**

---

## 🟡 5. VOBIZ IP whitelisting — believed unnecessary, but unproven

`deploy/docker-compose.voice.yml:9` states: *"Vobiz auth is credential-based so no IP whitelisting is
needed."* The `.env` supports this (`VOBIZ_PASSWORD`, `CREDENTIAL_ID`, `USERNAME`/`PASSWORD`), and the
product is **outbound** calling (`calls.json` records are all `to: +91…`).

If true, a new cloud IP needs **no ticket on VOBIZ's side** — the firewall rule is only *our* inbound
protection.

**This is a code comment, not a measurement.** The only real proof is `./deploy/verify.sh --call` from
the new host. **Do not decommission the old host until a real call connects with audio.**

---

## 🟡 6. LiveKit runs in `--dev` mode with `devkey`/`secret`

`docker-compose.voice.yml:24` → `livekit-server --dev`, with `api_key: 'devkey' / api_secret: 'secret'`
hardcoded in the SIP and egress configs.

Acceptable today because LiveKit's port is **not published to the host** — it's only reachable on the
internal docker network. It becomes a real vulnerability the moment anyone publishes 7880 or attaches
the container to a shared/host network. If you ever expose LiveKit, replace `--dev` with real keys.

---

## 🟡 7. Disk: 107 GB of the 123 GB "used" was docker build cache

The production box reported 80% full. Actual breakdown: **build cache 106.9 GB (75.25 GB reclaimable)**,
real content ~16 GB. `docker builder prune -f` reclaims it. A fresh host needs ≥40 GB but will grow the
same way — **add `docker builder prune -f --filter until=168h` to cron** or you will hit disk-full again.

---

## 🟡 8. The database is JSON files with no transactions

`calls.json`, `cost_ledger.json`, `billing.json` are read-modify-written by both `backend` and `worker`,
which share the `haptica-data` volume. There is no locking and no transactions. Concurrent writes can
lose records, and a crash mid-write can truncate a file.

Not in scope to fix here, and it has evidently been survivable at 243 calls. It will not survive volume.
`restore-data.sh` stops both writers before restoring for exactly this reason.
