# F3 — Hatchet Engine Deploy STATE (crash-safe ledger)

Phase F3: deploy Hatchet self-hosted durable-orchestration engine on a NEW INDEPENDENT droplet.
Live boxes (famit-livekit 168.144.153.145, famit-panel-2 143.110.247.249) MUST stay untouched.
caller.py write-path cutovers are a LATER spine unit (gated on F1) — NOT in scope here.

## DECISIONS (locked)
- NEW droplet `famit-hatchet`, blr1, s-2vcpu-4gb, ubuntu-24-04-x64.
- JOIN the default-blr1 VPC `61f1950d-a7c4-4144-99b9-f1cda3d4c627` (famit-livekit is in it @ priv 10.122.0.4)
  so the FUTURE caller.py cutover can reach Hatchet gRPC over the private network.
- Dedicated tag `hatchet` + dedicated firewall `hatchet-fw` (NOT the `fortress` tag — that has its own
  firewall `fortress-panel-fw` and would cross-apply rules to another box).
- Firewall: inbound SSH(22) key-only from anywhere + ICMP. NO public 8888/8080/7077/5432/5672.
  Egress allow-list (DNS/NTP/80/443/ICMP) for docker pulls.
- Hatchet self-host = POSTGRES-AS-BROKER variant (SERVER_MSGQUEUE_KIND=postgres) — drops RabbitMQ
  (current docs support it; lighter footprint). Stack: postgres + migration + setup-config +
  hatchet-engine + hatchet-dashboard. Engine V1.
- Dashboard/gRPC bound to localhost only on the box; reach dashboard via SSH tunnel.
- API token generated headless via `hatchet-admin token create` in the setup-config container.
- SSH key: DO key id 56622232 (c13-blr-test-key) == local C:\Users\kunal\.ssh\do-blr-test\id_ed25519.

## UNITS
- [DONE] U0  orientation: spec + creds + brain + roadmap read; advisor consulted.
- [ ] U1  provision droplet (tag+firewall+VPC, cloud-init installs Docker + OS harden).
- [DONE] U1  droplet 576483610 active; Docker 29.5.3 + compose v5.1.4; key-only SSH; UFW; cloud-init done.
- [DONE] U2  Hatchet compose (pg-broker) up: postgres healthy, engine+dashboard Up. gRPC 7077 OK.
- [DONE] U3  token created (CLI); hello-world ran end-to-end OVER gRPC. Run id 9f7a107d-b65f-4bab-9f75-fb9c7ee4a937.
             worker journal: rx start step -> [task greet] Hello,F3! -> finished step run. DURABLE PROOF.
- [DONE] U4  build_log + brain + STATE written. HATCHET_* env captured (priv 10.122.0.3).
- [DONE]  REST 502 RESOLVED — pivoted to hatchet-lite (spec §0.2). Now: gRPC trigger OK +
          workflows.list()=['f3-hello-world'] + runs.list()=1 + dashboard 200. Durability: run history
          survives `docker restart`. Ports 8888/7077/5432 CLOSED from internet (verified). Live boxes active.
ALL UNITS DONE. F3 engine deploy complete. caller.py cutover = later unit (gated on F1).

## LIVE FACTS (fill as we go)
- droplet_id: 576483610 (famit-hatchet)
- public_ip: 68.183.94.38
- private_ip (VPC, == future HATCHET_CLIENT_HOST_PORT host): 10.122.0.3
- firewall_id: b0da15f0-81c1-49e0-ae8a-9b0438cb6aae (hatchet-fw, tag hatchet)
- HATCHET token: stored on box /opt/hatchet/.hatchet-token (chmod600), recorded in build_log.

U1 IN PROGRESS: droplet created 576483610, polling for active+IPs.
