# BRAIN — Hatchet Orchestration Engine (F3 deploy)

Durable facts + hard-won learnings for the Hatchet spine. Append, never delete.
Spec: `caps/design/orchestration-hatchet.md`. Build log: `memory/build_log/wave-build-F3-hatchet.md`.

## WHAT IT IS / SCOPE
- Hatchet = self-hosted durable-orchestration engine (V1) for the platform's future multi-day flows,
  WhatsApp cadences, approvals, AI Manager + Workflow Studio. The OS (orchestration spine) plane.
- **F3 engine deploy = DONE on its OWN independent droplet.** The caller.py write-path cutovers
  (spec UNITs 5/7) are a SEPARATE LATER unit, gated on F1 (Postgres strangler). Not built yet.

## THE BOX (famit-hatchet)
- Droplet **576483610**, blr1, s-2vcpu-4gb, ubuntu-24.04. Public **68.183.94.38**, **priv 10.122.0.3**.
- In default-blr1 VPC (same as famit-livekit @ 10.122.0.4) → cross-box gRPC path exists.
- SSH: `ssh -i C:\Users\kunal\.ssh\do-blr-test\id_ed25519 root@68.183.94.38` (key-only).
- Dedicated tag `hatchet` + firewall `hatchet-fw` (b0da15f0-81c1-49e0-ae8a-9b0438cb6aae). NOT `fortress`.
- **Stack = hatchet-lite** at `/opt/hatchet/docker-compose.lite.yml`. API+dashboard `127.0.0.1:8888`,
  gRPC `127.0.0.1:7077`. Dashboard via SSH tunnel `-L 8888:127.0.0.1:8888` then http://localhost:8888.
- Port scan from internet: 22 open, 8888/7077/5432 CLOSED (firewall + localhost bind). Verified.

## CONNECTION ENV (for the future caller.py cutover — on famit-livekit)
```
HATCHET_CLIENT_TOKEN     = /opt/hatchet/.hatchet-token on the box (487-char JWT, chmod600; never git)
HATCHET_CLIENT_HOST_PORT = 10.122.0.3:7077   # PRIVATE VPC IP, NOT 127.0.0.1 (cross-box)
HATCHET_CLIENT_TLS_STRATEGY = none
default tenant id = 707d0855-80ab-4e1f-a156-f1c4546cbf52
```
Cutover prereqs IN ORDER (NOT done now — gRPC closed cross-box): (1) open hatchet-fw inbound tcp/7077
from 10.122.0.4/32 + publish lite gRPC on the private IP; (2) set `SERVER_GRPC_BROADCAST_ADDRESS=
10.122.0.3:7077` in compose + recreate lite (currently 127.0.0.1:7077 → cross-box client breaks);
(3) **REGENERATE the token AFTER (2)** — the token EMBEDS the broadcast address, so the current token
(bound to 127.0.0.1:7077) is stale for cross-box; mint fresh via `/hatchet-admin token create --config
/config --tenant-id 707d0855-…`; (4) THEN copy the fresh token to famit-livekit `.env`.

## HARD-WON LEARNINGS (do not relearn)
- **Postgres-as-broker works; drop RabbitMQ.** `SERVER_MSGQUEUE_KIND=postgres` in setup-config +
  remove all rabbitmq services. Current docs support it. The spec's "RabbitMQ required" is OUTDATED.
  Lighter footprint, fewer containers.
- **hatchet-sdk 1.33.6 uses `input_validator=`, NOT `input_type=`** in `hatchet.workflow(...)`. The
  docs snippet shows `input_type` — wrong for this version. Inspect `Hatchet.workflow` sig if unsure.
- **Stale `__pycache__` bites:** after editing a workflow module on the box, `rm -rf __pycache__` or
  the old compiled version re-runs and you chase a phantom error.
- **Run the worker as systemd, not `nohup &` over SSH.** Background `&`/`setsid` launched inside an SSH
  one-shot gets SIGHUP'd on session teardown and dies. systemd unit (`hatchet-hello-worker.service`)
  survives and auto-restarts. Token in an `EnvironmentFile` (chmod600), not inline.
- **Token via CLI, not dashboard UI:** `docker compose run --no-deps --rm setup-config
  /hatchet/hatchet-admin token create --config /hatchet/config --tenant-id <tenant>`. Dashboard is
  localhost-bound so the UI needs a tunnel+browser; CLI is headless and what the worker needs anyway.
- **gRPC is the load-bearing path** (worker + trigger + caller.py all use it) — it works.
- **The multi-container `:latest` stack 502s on ALL REST** (dashboard nginx proxies `/api→localhost:8080`
  inside the dashboard container, but the engine image exposes gRPC 7070 + healthcheck 8733, NOT the
  HTTP API on 8080). **FIX = use `hatchet-lite`** (single container, API+UI+engine on 8888 + gRPC 7077)
  — REST works out of the box. We run lite. Don't fight the multi-container REST wiring on a single box.
- **hatchet-lite binary/config paths differ:** admin binary at `/hatchet-admin` (not `/hatchet/...`),
  config dir `/config` (not `/hatchet/config`). Token: `docker exec <lite-ctr> /hatchet-admin token
  create --config /config --tenant-id 707d0855-80ab-4e1f-a156-f1c4546cbf52`.
- **lite needs `SERVER_AUTH_SET_EMAIL_VERIFIED=t`** + `SERVER_URL=http://localhost:8888` +
  `SERVER_GRPC_PORT=7077` (the lite container's gRPC is 7077 directly, not 7070).

## DURABLE PROOF (F3 acceptance)
- hello-world `f3-hello-world` ran end-to-end over gRPC. Run id 9f7a107d-b65f-4bab-9f75-fb9c7ee4a937.
  Worker journal: rx start step -> [task greet] Hello,F3! -> finished step run. State persisted in
  Hatchet Postgres. Engine healthy, internals firewalled/localhost-only, live boxes untouched.

## DROPLET LIMIT
- DO account droplet_limit = **3**, now ALL 3 used (livekit, panel-2, hatchet). Next new box needs a
  limit raise (DO billing/support ticket).
