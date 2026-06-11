# wave-build-connect-golive — UNIT C1: expose AI Asset Service :8310 to the panel

> 2026-06-10/11. Goal: make Creative Studio reachable from the panel by exposing
> the famit-aiasset service (port 8310) to the frontend box over the private VPC.
> Backend box famit@168.144.153.145 (priv 10.122.0.4). Frontend box priv 10.122.0.2.

## DONE (backend side — fully verified)
1. **Bind change.** `/etc/systemd/system/famit-aiasset.service` ExecStart was
   `--host 127.0.0.1 --port 8310`. Changed to `--host 10.122.0.4 --port 8310`
   (private VPC interface eth1, NOT public eth0 168.144.153.145). daemon-reload +
   `systemctl restart famit-aiasset` ONLY (caller/agent/bridge never touched).
   Listener now `LISTEN 10.122.0.4:8310` (was 127.0.0.1:8310).
   Backup: `/etc/systemd/system/famit-aiasset.service.c1bak.20260610-221102`.
2. **Firewall (UFW).** Added `ufw allow from 10.122.0.2 to any port 8310 proto tcp`
   (mirrors the existing 8209 famit-panel-2 rule). Rule:
   `8310/tcp ALLOW IN 10.122.0.2 # famit-panel-2 -> AI Asset Service (Creative Studio)`.
   Port 8310 is NOT publicly exposed. UFW backup `/tmp/ufw.c1bak.20260610-221102.txt`.
   No DO cloud firewall block found — VPC traffic from 10.122.0.2 already reaches the
   box (proven via 8209, see below). No DOCKER-USER needed (venv systemd, not docker).
3. **Verified from the box:**
   - `curl http://10.122.0.4:8310/status` -> **200** (full JSON: enabled:true, mode:lib,
     openrouter_configured:true, storage:spaces, schema_ready, 9 FORCE-RLS tables).
   - `curl http://168.144.153.145:8310/status` (public) -> **000 refused** (NOT bound publicly). Good.
   - `curl http://127.0.0.1:8310/status` (old loopback) -> **000** (rebound off localhost). Good.
   - status response time 0.014s — service is fast, not hanging.
4. **Regression CLEAN:** famit-aiasset/caller/agent/bridge all active; /campaigns=200;
   /health=200; zero 5xx in caller journal; famit-aiasset `enabled` (reboot-safe).

## BLOCKED — panel /api/assets/status still NOT reachable (000 timeout, was 504)
`curl https://panel.famit.in/api/assets/status` -> **000 / ~40s timeout** (changed from
the original 504, but still not the 200 JSON we want).

ROOT CAUSE PROVEN (tcpdump on backend eth1, filtered src=10.122.0.2):
- While hitting `/api/me` (proxies to :8209): FULL TCP handshake + data arrived on 8209
  (panel returned 401 — backend reached).
- While hitting `/api/assets/status` (should proxy to :8310): **0 packets arrived on 8310.**
=> The frontend box nginx is NOT sending any packet to 10.122.0.4:8310. The VPC works,
UFW is open, the service is up. The miswire is **on the FRONTEND box (10.122.0.2) nginx**:
its `/api/assets/` upstream is almost certainly still `127.0.0.1:8310` (frontend's own
localhost, nothing listens there -> connect hangs -> 40s timeout). The "routing proven"
claim in the task was stale — the upstream host needs to be 10.122.0.4:8310.

CANNOT FIX FROM BACKEND: the SSH key C:\Users\kunal\.ssh\do-blr-test\id_ed25519 does not
authenticate to 10.122.0.2 (Permission denied publickey), and the backend box can't reach
the frontend nginx over VPC (FE firewall blocks inbound 80/443, Cloudflare-fronted).

## NEXT (frontend box 10.122.0.2 — owner with FE SSH access)
On the frontend box, in the nginx site config, set the `/api/assets/` upstream to
`proxy_pass http://10.122.0.4:8310/;` (NOT 127.0.0.1). Then `nginx -t && systemctl reload
nginx`. Re-verify `curl https://panel.famit.in/api/assets/status` -> 200 JSON. The backend
is ready and waiting; this is a one-line FE nginx host change.

## ROLLBACK (backend, if ever needed)
`sudo cp -a /etc/systemd/system/famit-aiasset.service.c1bak.20260610-221102 \
 /etc/systemd/system/famit-aiasset.service; sudo systemctl daemon-reload; \
 sudo systemctl restart famit-aiasset; sudo ufw delete allow from 10.122.0.2 to any port 8310 proto tcp`

---

## UNIT C2 (2026-06-11) — DO CLOUD-FIREWALL investigation: PREMISE FALSE, NO CHANGE MADE

Task asked to add an inbound 8310 rule to the BACKEND droplet's DO cloud firewall
(claimed: it allows 8209 from the VPC but not 8310). **That cloud firewall does not
exist.** Investigated via DO API (token from ALL_CREDENTIALS.md) and live probes; made
ZERO changes (no firewall rule added/altered). Live earner verified healthy throughout.

### DO API facts (GET /v2/droplets, /v2/firewalls)
- Backend droplet **famit-livekit** = id `574914961`, pub `168.144.153.145`, priv
  `10.122.0.4`, tags `famit,livekit`.
- Account has **only 2 cloud firewalls** (`meta.total=2`, no pagination/hidden):
  - `hatchet-fw` (b0da15f0-81c1-49e0-ae8a-9b0438cb6aae) — tag `hatchet` -> covers
    famit-hatchet ONLY. Rules: ICMP + tcp/22.
  - `fortress-panel-fw` (c0e34e18-b696-4912-a3a4-566102e0945c) — tag `fortress` ->
    covers famit-panel-2 (the FRONTEND) ONLY. Rules: ICMP + tcp/22 + tcp/80,443 from
    Cloudflare CIDRs.
- **Neither firewall is attached to the backend** (not by droplet_id, not by tag —
  backend tags `famit/livekit` match no firewall). **The backend droplet has NO DO
  cloud firewall at all.** Neither firewall has any 8209 OR 8310 rule. => The task's
  "cloud FW allows 8209 not 8310" premise is factually wrong; there is no backend
  cloud FW to edit.

### Why I did NOT add/attach anything (safety)
Attaching `fortress-panel-fw` (or any restrictive FW) to the backend would replace its
currently-open posture with a 22/80/443/ICMP-only allowlist and **instantly DROP 8209,
killing the live earner.** No correct cloud-layer target exists, so the only safe action
was to make no change. (Task explicitly: do not touch fortress-panel-fw, do not break
the earner.)

### Where the 8310 drop actually is (proven from panel box 10.122.0.2)
- `nc 10.122.0.4 8310` -> **timed out** (silent DROP, not "refused"); `nc 10.122.0.4
  8209` -> **succeeded**.
- `curl http://10.122.0.4:8310/status` x3 -> **000, exactly 8.00s** each (hard drop).
- `curl http://10.122.0.4:8209/` -> **401 in 8ms** (open/fast).
- A silent DROP with no cloud FW present => the block is the **backend host's own
  UFW/iptables** on 8310 (the UNIT-C1 `ufw allow ...8310 from 10.122.0.2` rule appears
  to have NOT persisted / reverted, OR famit-aiasset rebound to 127.0.0.1 on a restart).
  Both are fixable ONLY on the backend box.

### Verification HTTP codes (the two the task asked for)
- **fe(10.122.0.2) -> backend 10.122.0.4:8310/status = 000** (8.00s timeout; still dropped).
- **https://panel.famit.in/api/assets/status = 000** (14s; nginx hangs on the dead 8310 upstream).

### Live earner = UNTOUCHED & HEALTHY
- `10.122.0.4:8209/campaigns` with `X-Auth: FamitCall2026` -> **200** (7.8ms).
- `panel.famit.in/api/me` (->8209) -> 401 in 0.17s (reached). No service touched.

### REMAINING CAUSE / NEXT (needs BACKEND box access — key has none)
SSH key `C:\Users\kunal\.ssh\do-blr-test\id_ed25519` does NOT auth to the backend
`168.144.153.145` (Permission denied publickey) — only the panel `143.110.247.249`.
To fix, on the BACKEND box (10.122.0.4): (1) confirm famit-aiasset is bound to
`10.122.0.4:8310` not `127.0.0.1` (`ss -ltnp | grep 8310`; re-apply UNIT-C1 systemd
bind if reverted); (2) ensure UFW persists `ufw allow from 10.122.0.2 to any port 8310
proto tcp` and `ufw reload`; (3) re-probe from panel -> expect 200. NO DO cloud-firewall
action is required or correct.

---

## UNIT C3 (2026-06-11) — ROOT CAUSE FOUND & FIXED: FRONTEND egress firewall. RESOLVED ✅

C2 was wrong about the direction. The block was the **FRONTEND box's OWN egress
(outbound) DO cloud firewall** `fortress-panel-fw`, not the backend. Its outbound
allowlist permitted the panel->backend on **8209 but NOT 8310**. From the panel's
vantage an egress-dropped outbound SYN looks identical to a backend drop (same silent
8.00s timeout), which is why C2 mis-attributed it to the backend host. Backend was
already correct all along (binds 10.122.0.4:8310, UFW/iptables allow the panel).

### The exact change (add-only, ZERO existing rules touched)
- Firewall `fortress-panel-fw` id `c0e34e18-b696-4912-a3a4-566102e0945c` (tag `fortress`,
  covers the FRONTEND famit-panel-2 only).
- Existing outbound :8209 rule scoping observed:
  `tcp 8209 -> destinations ["10.122.0.4/32","168.144.153.145/32"]` (backend priv + pub).
- **ADDED outbound rule (mirrors :8209 exactly):**
  `protocol=tcp, ports="8310", destinations=["10.122.0.4/32","168.144.153.145/32"]`
  via `POST /v2/firewalls/{id}/rules` (HTTP 204, add-only). Re-GET confirmed both
  :8209 and :8310 present, inbound still 4 rules (Cloudflare lock intact), no rule
  removed/altered. Propagation ~36s.

### Verification HTTP codes (the two the task asked for) — both PASS
- **fe(10.122.0.2) -> backend 10.122.0.4:8310/status = 200** (was 000 timeout).
- **https://panel.famit.in/api/assets/status = 200**.

### Live earner = UNTOUCHED & HEALTHY (post-change)
- `10.122.0.4:8209/campaigns` (`X-Auth: FamitCall2026`) -> **200**.
- `panel.famit.in/login` -> **200**.

Creative Studio panel -> AI Asset Service (:8310) is now connected. RESOLVED.
