# WAVE BUILD F3 — Hatchet Durable-Orchestration Engine (engine deploy only)

Phase F3 of MASTER_PLATFORM_ROADMAP. Spec: `design/orchestration-hatchet.md`.
Scope of THIS unit: stand up the Hatchet self-hosted engine on a NEW INDEPENDENT droplet, secure it,
prove a hello-world workflow runs durably, and capture the HATCHET_* env the LATER caller.py cutover
needs. **The caller.py write-path cutovers (UNITs 5/7 of the spec) are NOT in scope here** — they are a
later spine unit gated on F1 (Postgres strangler). The live boxes were not touched.

Date: 2026-06-09/10. Engine: Hatchet **V1**. SDK: hatchet-sdk **1.33.6**.

---

## 1. INFRA PROVISIONED (new, independent — live boxes untouched)

| Item | Value |
|---|---|
| Droplet name | **famit-hatchet** |
| Droplet id | **576483610** |
| Public IP | **68.183.94.38** |
| **Private VPC IP** | **10.122.0.3**  ← the host the future caller.py cutover dials over the VPC |
| Region / size / image | blr1 / s-2vcpu-4gb / ubuntu-24-04-x64 |
| VPC | `61f1950d-a7c4-4144-99b9-f1cda3d4c627` (default-blr1) — **same VPC as famit-livekit** (priv 10.122.0.4), so the cross-box gRPC path exists |
| Tag | **hatchet** (dedicated — NOT the `fortress` tag, to avoid cross-applying panel-2's firewall) |
| Firewall | **hatchet-fw** `b0da15f0-81c1-49e0-ae8a-9b0438cb6aae` (targets tag `hatchet`) |
| SSH key | DO key 56762232? → **56622232** (c13-blr-test-key) == local `C:\Users\kunal\.ssh\do-blr-test\id_ed25519` |
| Backups / monitoring | enabled at create |

**Droplet-limit note:** account limit = **3**; was 2 used (famit-livekit, famit-panel-2). This deploy
takes the 3rd slot. **No headroom left** — any further new droplet needs the limit raised (DO support
ticket / billing). Not a blocker for F3, but flagged for the next infra phase.

---

## 2. WHAT'S DEPLOYED + VERSION

**FINAL stack = `hatchet-lite` single-container** (spec §0.2), **Postgres-as-broker**
(`SERVER_MSGQUEUE_KIND=postgres`) — **no RabbitMQ**. (Initially deployed the multi-container engine+
dashboard stack; its REST/dashboard-API returned 502 — see §7 — so pivoted to lite, which serves REST
correctly. The multi-container compose is kept as `caps/infra/hatchet/docker-compose.hatchet.yml` for
reference; the LIVE stack is `docker-compose.hatchet-lite.yml`.)

Compose at `/opt/hatchet/docker-compose.lite.yml` on the box (source:
`caps/infra/hatchet/docker-compose.hatchet-lite.yml`):
- `postgres:15.6` (healthy) — Hatchet's own metadata DB, logically + physically isolated from the app
  `famit` DB and the JSON stores. Volume `hatchet_lite_postgres_data`. PG password = strong random in
  `/opt/hatchet/.env` (chmod 600).
- `hatchet-lite:latest` (`ghcr.io/hatchet-dev/hatchet/hatchet-lite`) — bundles migrate + API +
  dashboard + engine. **API + dashboard on `127.0.0.1:8888`, gRPC on `127.0.0.1:7077`.** Engine
  version pinned **V1**. `SERVER_AUTH_SET_EMAIL_VERIFIED=t` (headless). Admin binary at `/hatchet-admin`,
  config dir `/config` (NOT `/hatchet/config` — that path is the multi-container layout).

All ports bound to **127.0.0.1 only** (never public). Resource ceilings in compose (lite 1.5cpu/1.5G,
pg 1cpu/1G). Actual idle usage tiny (lite ~68 MB, pg ~300 MB; ~370 MB RAM total). Box has 3.9 GB.

**Health verified:** `curl 127.0.0.1:8888/api/ready` = 200; dashboard = 200; gRPC + REST both work.
**Durability verified:** `docker restart` the lite container → run history persists in Postgres
(re-queried `runs.list()` == 1 after restart).

**Worker:** systemd `hatchet-hello-worker.service` (active, enabled) runs the hello-world worker (Python
venv at `/opt/hatchet/.venv`, hatchet-sdk 1.33.6).

**Reboot-safe:** lite + postgres containers both `restart: always`; the worker is an enabled systemd
unit. A droplet reboot brings the whole stack back automatically.

---

## 3. HELLO-WORLD PROOF (durable execution works)

Workflow `f3-hello-world` (`/opt/hatchet/hello_world.py`, src `caps/infra/hatchet/hello_world.py`):
`hatchet.workflow(name="f3-hello-world", input_validator=HelloInput)` + one `@hello_wf.task() greet`.

Triggered with `hello_wf.run(HelloInput(name="F3"))`. Result:
```
RUN RESULT: {'greet': {'message': 'Hello, F3! Hatchet F3 durable execution works.', 'ok': True}}
```
Worker journal (the definitive end-to-end + durability proof — state persisted in Hatchet's Postgres):
```
rx: start step run: 9f7a107d-b65f-4bab-9f75-fb9c7ee4a937/f3-hello-world:greet
run: start step: f3-hello-world:greet/9f7a107d-...
[task greet] -> Hello, F3! Hatchet F3 durable execution works.
finished step run: f3-hello-world:greet/9f7a107d-...
```
Run id **9f7a107d-b65f-4bab-9f75-fb9c7ee4a937**. The trigger→gRPC dispatch→worker execute→return path
(exactly the path caller.py will use) is fully functional.

---

## 4. HATCHET_* ENV — what the LATER caller.py cutover needs

The future cutover lives on **famit-livekit (a DIFFERENT box)**, so it reaches Hatchet over the VPC.
**Use the PRIVATE IP, not 127.0.0.1** (the spec's `127.0.0.1:7077` assumed co-location — wrong here):

```
HATCHET_CLIENT_TOKEN=<487-char JWT on the box at /opt/hatchet/.hatchet-token, chmod600 — DO NOT paste in git>
HATCHET_CLIENT_HOST_PORT=10.122.0.3:7077          # famit-hatchet private VPC IP : gRPC
HATCHET_CLIENT_TLS_STRATEGY=none                  # self-host insecure gRPC
# default tenant id (seeded by quickstart): 707d0855-80ab-4e1f-a156-f1c4546cbf52
```

**THE CUTOVER MUST DO THIS, IN THIS EXACT ORDER (record — do NOT do now, gRPC is not open cross-box yet):**
1. **Open the firewall:** add inbound `tcp 7077` to `hatchet-fw` from famit-livekit's private IP
   `10.122.0.4/32` only. Also bind the lite container's published gRPC port to the private IP (or
   `0.0.0.0` behind the VPC-only firewall) instead of `127.0.0.1` in `docker-compose.lite.yml`.
2. **Change the gRPC broadcast address.** Lite currently broadcasts `SERVER_GRPC_BROADCAST_ADDRESS=
   127.0.0.1:7077`. A cross-box client connecting to `10.122.0.3:7077` gets `127.0.0.1` broadcast back
   and gRPC reconnection misbehaves. Set `SERVER_GRPC_BROADCAST_ADDRESS=10.122.0.3:7077` in the compose,
   then `docker compose up -d` (recreate lite).
3. **REGENERATE THE TOKEN AFTER step 2** (ordering matters): the Hatchet client token *embeds the
   server/broadcast address* — that is exactly why the docs say a broadcast-address change "requires
   re-issuing an API token." The current token (`/opt/hatchet/.hatchet-token`) is bound to
   `127.0.0.1:7077`; reusing it cross-box can fail in confusing ways even with HATCHET_CLIENT_HOST_PORT
   overridden. So: (a) set broadcast=`10.122.0.3:7077` → (b) recreate lite → (c)
   `docker exec <lite-ctr> /hatchet-admin token create --config /config --tenant-id 707d0855-…` to mint
   a FRESH token → (d) THEN copy that fresh token to famit-livekit's `/opt/famit-agent/.env` (chmod 600).
   Until cutover, flags stay `legacy` and a missing token forces legacy (spec §3 safety interlock).

---

## 5. SECURITY POSTURE

- **DO Cloud Firewall `hatchet-fw`** (dedicated tag, isolated from other boxes): inbound = SSH 22
  (key-only) + ICMP ONLY; **no public 8080/7077/5432**. Outbound = DNS/NTP/80/443/ICMP allow-list
  (egress-locked per FORTRESS playbook — a rooted box still can't be conscripted into a volumetric DDoS).
- **All Hatchet internals bound to 127.0.0.1** on the box — dashboard + gRPC + PG are never internet-
  reachable. Reach the dashboard via SSH tunnel:
  `ssh -i <key> -L 8080:127.0.0.1:8080 root@68.183.94.38` then http://localhost:8080.
- **OS hardening (cloud-init, born-hardened):** key-only SSH (`PasswordAuthentication no`,
  `PermitRootLogin prohibit-password`), UFW (inbound 22 only), fail2ban, unattended-security-upgrades,
  sysctl (SYN cookies / rp_filter / no redirects / ASLR), 2G swap. Marker `/var/lib/hatchet-provisioned`.
- **Secrets:** PG password (`/opt/hatchet/.env`) + Hatchet token (`/opt/hatchet/.hatchet-token`) +
  worker env (`/opt/hatchet/worker.env`) all chmod 600. Nothing committed to git.
- **Backups:** DO managed backups on; daily snapshot cron recommended (not yet added — note for hardening).

---

## 6. THE LIVE SYSTEM IS UNTOUCHED

- famit-livekit (168.144.153.145) and famit-panel-2 (143.110.247.249): no API calls, no SSH, no config
  changes. Only READ their metadata (VPC membership) via the DO API.
- caller.py was NOT edited (the cutover units are out of scope). No `ORCH_*`/`HATCHET_*` env added to the
  live box. Orchestration on the live box remains 100% legacy.

---

## 7. RESOLVED — the multi-container 502, fixed by pivoting to hatchet-lite

The first attempt used the multi-container `:latest` stack (engine + dashboard). Its dashboard nginx
proxies `/api → localhost:8080` inside the dashboard container, where no API server binds (the engine
image exposes gRPC 7070 + healthcheck 8733 but not the HTTP API on 8080) → **502 on all REST**
(`runs.list()`, `workflows.list()`, dashboard data, the spec §6 `/status` read-back). gRPC execution
worked throughout; only REST was down.

**Fixed:** torn down the multi-container stack, deployed `hatchet-lite` (spec §0.2 endorsed it). Lite
bundles API+UI+engine in one container and serves REST correctly. Re-verified on lite: gRPC trigger
returns the result; `hatchet.workflows.list()` → `['f3-hello-world']`; `hatchet.runs.list()` → 1 run;
dashboard 200. **No remaining 502.** (Lite re-ran quickstart against a fresh PG, so the token was
re-issued — the current valid token is on the box; the old multi-container token is dead.)

Learning recorded in brain: with the multi-container `:latest` images, REST isn't served by the engine
or dashboard out of the box; hatchet-lite is the working single-box path. No open items block F3.

---

## 8. FILES (local source of truth)
- `caps/infra/hatchet/docker-compose.hatchet.yml` — the stack (pg-broker variant).
- `caps/infra/hatchet/hatchet-cloud-init.sh` — born-hardened user_data (Docker + OS hardening).
- `caps/infra/hatchet/hello_world.py` — the proof workflow (worker|trigger).
- `caps/infra/hatchet/F3_HATCHET_STATE.md` — crash-safe per-unit ledger.
- On box: `/opt/hatchet/{docker-compose.yml,.env,.hatchet-token,worker.env,hello_world.py,.venv}`,
  systemd `hatchet-hello-worker.service`.
