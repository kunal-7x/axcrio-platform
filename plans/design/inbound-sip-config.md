# Inbound SIP / LiveKit Config — EXACT additive wiring (PLAN-1)

**Status:** CONFIG WRITTEN — **NOT APPLIED.** Read-only inspection of the live box done
2026-06-11; every value below verified against the running stack. Apply only when the founder
says go. **Hard rule:** additive, backup-first, latency-safe. The **live outbound earner**
(`agent.py` "Riya"/`capsy` worker, `famit-agent.service`, outbound trunks `ST_LH8ighJJtHSi` UDP
+ `ST_fmtVmNJmpzKa` TCP) is **NEVER edited, restarted, or reconfigured** by anything here.

Box: `famit@168.144.153.145` (blr1). SSH key `C:\Users\kunal\.ssh\do-blr-test\id_ed25519`.

---

## 0. Live ground truth (re-verified read-only 2026-06-11)

| Fact | Live evidence (this session) |
|---|---|
| `livekit-sip` publishes **UDP only** on 5060 + 10000-10200 | `docker ps` → `0.0.0.0:5060->5060/udp` + RTP udp; **no `/tcp` mapping**. `ss -lnp` → 5060 is `udp UNCONN` (docker-proxy) only, **no tcp LISTEN**. |
| Compose confirms TCP publish is "the NEXT unit" | `/opt/livekit/docker-compose.yml` `sip.ports:` = `"5060:5060/udp"` + `"10000-10200:10000-10200/udp"` only; inline comment: publishing/allowlisting the SIP port "is the NEXT unit." |
| **0 inbound trunks, 0 dispatch rules** today | `lk sip inbound list` → empty table. `lk sip dispatch list` → empty table. |
| Outbound = exactly 2 trunks, both `2c24f731.sip.vobiz.ai`, num `+918071583488`, auth `capsy-project`, enc DISABLE | `lk sip outbound list` → `ST_LH8ighJJtHSi` (UDP) + `ST_fmtVmNJmpzKa` (TCP). **Do not edit.** |
| `lk` CLI | `/tmp/lkbin/lk` (90 MB, present). ⚠️ in `/tmp` — relocate to `/usr/local/bin/lk` before relying on it across reboots. |
| LiveKit creds for `lk` | `LIVEKIT_URL=ws://127.0.0.1:7880`, `LIVEKIT_API_KEY=API553b2cd005f320d0`, secret in `/opt/livekit/sip.runtime.yaml` (`api_secret:`). |
| UFW (5060/5061) | `5060/udp ALLOW IN 13.203.7.132` (#2), `5061/tcp ALLOW IN 13.203.7.132` (#3, stale — Vobiz uses 5060). **No TCP 5060 rule, and only the 1 IP of the 10.** |
| DOCKER-USER firewall | single source of truth = `/usr/local/sbin/livekit-vobiz-fw.sh` (run by `livekit-vobiz-fw.service`, **active**). `VOBIZ_IPS=("13.203.7.132")` only. Clean `apply()` helper + `iptables -F DOCKER-USER` reset each run. **UDP only** today (`apply udp 5060`, `apply udp 10000:10200`, `rtp-any` RETURN). |
| Outbound regression baseline | `famit-agent.service` **active**; `livekit-vobiz-fw.service` **active**. |
| Inbound worker | `/opt/famit-agent/ai_manager/inbound_agent.py` exists as an import-safe **stub** (build-unit 6, DEFERRED): `build_worker_options()` → `WorkerOptions(entrypoint_fnc=inbound_entrypoint, agent_name="manager")`. Activating that worker is a SEPARATE unit (Unit 5), **not** this SIP-config task. |

**The single most important wiring fix** (most likely cause of a failed first call): the box allows
only `13.203.7.132` of Vobiz's **10** signaling IPs, and has **no TCP** path. Both are fixed below.

**The 10 Vobiz SIP-signaling source IPs** (CONFIRMED `docs.vobiz.ai/concepts/ip-whitelisting`,
all AWS ap-south-1):
```
13.203.7.132 65.2.100.211 13.126.98.234 13.235.11.131 13.233.44.61
3.111.255.163 3.111.128.110 43.204.64.203 15.207.232.91 35.154.133.28
```

---

## (a) UNIT 1 — Enable TCP inbound on the SIP container (the real change, additive)

**Why:** container is UDP-only on 5060; Vobiz inbound needs TCP (UDP→0 responses, the known
Vobiz issue). Add the TCP host-publish **without removing** the UDP line (outbound + UDP fallback
share this container).

```bash
# 1. BACKUP (fresh dated)
cp /opt/livekit/docker-compose.yml /opt/livekit/docker-compose.yml.bak.aim.$(date +%s)

# 2. EDIT /opt/livekit/docker-compose.yml — in the `sip:` service `ports:` list, ADD the tcp line.
#    Final ports block must read EXACTLY:
#      ports:
#        - "5060:5060/udp"                 # existing — DO NOT REMOVE (outbound + UDP fallback)
#        - "5060:5060/tcp"                 # ADD — inbound from Vobiz over TCP
#        - "10000-10200:10000-10200/udp"   # existing — RTP
#    (livekit/sip listens on both UDP+TCP on sip_port by default; sip.runtime.yaml stays unchanged.)

# 3. RECREATE ONLY the sip container (does NOT touch livekit-server / redis / famit-agent):
cd /opt/livekit && docker compose up -d sip

# 4. VERIFY tcp listener now up (host side, via docker-proxy):
ss -tlnp | grep ':5060'        # expect a tcp LISTEN on 0.0.0.0:5060
docker ps --format '{{.Names}} {{.Ports}}' | grep livekit-sip   # expect both 5060/udp AND 5060/tcp
```

**Untouched-check after Unit 1:** `docker ps` shows `livekit-server` + `livekit-redis` same uptime;
`systemctl is-active famit-agent` → `active` (outbound never used the host TCP 5060 mapping).

**ROLLBACK Unit 1:** `cp /opt/livekit/docker-compose.yml.bak.aim.<ts> /opt/livekit/docker-compose.yml`
then `cd /opt/livekit && docker compose up -d sip`. Zero outbound impact.

---

## (c) UNIT 2 — Firewall: allow Vobiz inbound TCP 5060, locked to the 10 Vobiz IPs (additive)

Two layers must both allow it: **DOCKER-USER** (Docker-published ports bypass UFW — this is the one
that actually gates the inbound call) and **UFW** (belt-and-braces / host services). Edit the
firewall *script* so a reboot re-applies it — never hand-add transient `iptables` rules.

### 2a. DOCKER-USER — edit the source-of-truth script (the gate that matters)

```bash
# BACKUP
sudo cp /usr/local/sbin/livekit-vobiz-fw.sh /usr/local/sbin/livekit-vobiz-fw.sh.bak.aim.$(date +%s)
sudo iptables-save | sudo tee /root/iptables.aim.bak.$(date +%s) >/dev/null

# EDIT /usr/local/sbin/livekit-vobiz-fw.sh — TWO minimal, additive changes:
#
#   (i) Extend VOBIZ_IPS from the single IP to all 10 (one line replacement):
#       VOBIZ_IPS=("13.203.7.132" "65.2.100.211" "13.126.98.234" "13.235.11.131" "13.233.44.61" \
#                  "3.111.255.163" "3.111.128.110" "43.204.64.203" "15.207.232.91" "35.154.133.28")
#
#   (ii) Add a TCP 5060 allow/deny pair by adding ONE line next to `apply udp 5060`:
#       apply udp 5060
#       apply tcp 5060          # ADD — Vobiz inbound SIP over TCP (uses the same apply() helper)
#
#   The existing apply() loops every VOBIZ_IPS entry with `-j RETURN` then appends a `-j DROP` for
#   all others — so extending the array auto-covers UDP 5060, RTP, AND the new TCP 5060 for all 10.
#   No other edits. The IPv6 DROP-all block already covers tcp implicitly? NO — add 5060/tcp to its
#   dport loop too: change `for dport in 5060 10000:10200; do` ip6 DROP block to also DROP tcp 5060
#   (defense-in-depth; box has no public v6, optional but recommended):
#       ip6tables -A DOCKER-USER -p tcp --dport 5060 --comment "${TAG} deny6" -j DROP || true

# APPLY (idempotent — the script flushes & rebuilds DOCKER-USER each run):
sudo systemctl restart livekit-vobiz-fw.service

# VERIFY
sudo iptables -L DOCKER-USER -n | grep -E '5060'   # expect 10x tcp RETURN (per Vobiz IP) + 1 tcp DROP,
                                                    # plus the existing 10x udp RETURN + udp DROP
```

### 2b. UFW — add TCP 5060 from each of the 10 (host-level belt-and-braces)

```bash
sudo ufw status numbered > /opt/livekit/ufw.aim.bak.$(date +%s).txt
for ip in 13.203.7.132 65.2.100.211 13.126.98.234 13.235.11.131 13.233.44.61 \
          3.111.255.163 3.111.128.110 43.204.64.203 15.207.232.91 35.154.133.28; do
  sudo ufw allow proto tcp from $ip to any port 5060 comment 'Vobiz inbound SIP TCP'
done
# (Optional: also extend the existing single-IP 5060/udp UFW rule to the full 10, mirroring the loop
#  with `proto udp`, so UFW and DOCKER-USER agree. Not required for the call — DOCKER-USER is the gate.)
sudo ufw status numbered | grep 5060   # expect 10x 5060/tcp ALLOW from the Vobiz IPs
```

**Negative check:** a TCP connect to `168.144.153.145:5060` from a non-Vobiz IP is dropped (test
from your laptop: `Test-NetConnection 168.144.153.145 -Port 5060` over TCP should time out/fail).

**ROLLBACK Unit 2:** restore `livekit-vobiz-fw.sh.bak.aim.<ts>` + `sudo systemctl restart
livekit-vobiz-fw.service`; `sudo ufw delete` each added 5060/tcp rule (or restore from the ufw bak).
RTP (udp 10000:10200) is unchanged throughout (already has the `rtp-any` RETURN).

---

## (a) UNIT 3 — LiveKit INBOUND TRUNK for DID +918071583488 (additive; never edits outbound)

Set `lk` env first (relocate `lk` to a stable path first if applying for real):
```bash
export LIVEKIT_URL=ws://127.0.0.1:7880
export LIVEKIT_API_KEY=API553b2cd005f320d0
export LIVEKIT_API_SECRET="$(grep -m1 -oP 'api_secret:\s*\K\S+' /opt/livekit/sip.runtime.yaml)"
```

`aim_inbound_trunk.json`:
```json
{
  "trunk": {
    "name": "aim-inbound",
    "numbers": ["+918071583488"],
    "allowed_addresses": [
      "13.203.7.132", "65.2.100.211", "13.126.98.234", "13.235.11.131", "13.233.44.61",
      "3.111.255.163", "3.111.128.110", "43.204.64.203", "15.207.232.91", "35.154.133.28"
    ],
    "krisp_enabled": false
  }
}
```
- `numbers` = the AI Manager DID `+918071583488` (the founder is reusing the existing DID; if a NEW
  dedicated DID is bought, swap this value).
- `allowed_addresses` = the **10 Vobiz signaling IPs** (LiveKit matches inbound by DID + this list,
  NOT by the carrier Trunk ID `317a5dce-9237-4ff9-8de9-54b85c2dfe2d`, which is informational).
- **Auth:** IP-allowlist preferred (above). If Vobiz can only do SIP-digest inbound, add
  `"auth_username":"aim-inbound","auth_password":"<from ai_manager_INBOUND_SETUP.md A4 Option 2>"` —
  must match exactly what the founder entered in the Vobiz form.

```bash
/usr/local/bin/lk sip inbound create aim_inbound_trunk.json   # capture returned ST_<id> = OUR inbound trunk id
```

**ROLLBACK Unit 3:** `lk sip inbound delete <ST_id>` (independent of the 2 outbound trunks).

---

## (b) UNIT 4 — DISPATCH RULE: DID → fresh room → `manager` agent (additive)

`aim_dispatch_rule.json`:
```json
{
  "name": "aim-inbound-dispatch",
  "trunk_ids": ["ST_<inbound_id_from_unit_3>"],
  "rule": { "dispatchRuleIndividual": { "roomPrefix": "aim-" } },
  "room_config": {
    "agents": [ { "agent_name": "manager" } ]
  }
}
```
- `dispatchRuleIndividual` → a fresh room `aim-<unique>` per inbound call (correct for a 1:1 command
  session). **No rule-level `pin`** — the real per-user Argon2id PIN is enforced in-agent at the
  state-machine PIN/step-up gate (the rule `pin` is a single static value and is NOT our auth).
- `agents:[{agent_name:"manager"}]` auto-dispatches the AI Manager inbound worker — the SECOND
  worker persona registered ALONGSIDE the live `capsy` outbound worker (different process; Unit 5).
  This is "Wiring A" (lowest latency).
- `trunk_ids` is bound to the INBOUND trunk only → the dispatch can never fire on the outbound path.

```bash
/usr/local/bin/lk sip dispatch create aim_dispatch_rule.json
/usr/local/bin/lk sip dispatch list     # shows aim-inbound-dispatch → manager, bound to inbound trunk only
/usr/local/bin/lk sip outbound list     # UNCHANGED: ST_LH8ighJJtHSi + ST_fmtVmNJmpzKa both intact
```

**ROLLBACK Unit 4:** `lk sip dispatch delete <SipDispatchRuleID>`.

---

## UNIT 5 — `manager` inbound worker (SEPARATE unit; not this SIP-config task)

Out of scope for PLAN-1 (this doc is SIP/LiveKit/firewall config). Recorded for completeness:
activate `/opt/famit-agent/ai_manager/inbound_agent.py` (currently a deferred stub) → register a
SECOND LiveKit worker `WorkerOptions(entrypoint_fnc=inbound_entrypoint, agent_name="manager")` in
its **own systemd unit**, co-located on THIS box, copying the tuned `AgentSession` kwargs verbatim
from `agent.py` (preemptive_generation, endpointing, barge-in) so inbound inherits outbound latency.
It imports the AI Manager state machine / firewall / workforce in-process (same as the chat Test
Console) — it does **not** import or restart `agent.py`. Gated dormant by `AIM_ENABLED=1` +
`AIM_INBOUND_TRUNK_ID` set. **Until this worker is running, an inbound call rings/connects but no
agent joins** — so Unit 5 must land before the live test, but it touches NO outbound object.

---

## (d) Confirmation: this is ADDITIVE — the OUTBOUND earner is untouched

| Outbound asset | Touched by Units 1-4? | Why safe |
|---|---|---|
| Outbound trunks `ST_LH8ighJJtHSi` (UDP) + `ST_fmtVmNJmpzKa` (TCP) | **No** | Unit 3 *creates* a new inbound trunk; outbound trunks are distinct `ST_` objects never referenced. `lk sip outbound list` is byte-identical before/after. |
| `agent.py` "Riya" / `capsy` worker | **No** | No file edit; `manager` worker is a separate process (Unit 5), `capsy` registration unchanged. |
| `famit-agent.service` | **No** | Never stopped/restarted. Only the `sip` container is recreated (Unit 1) — a different service. |
| SIP container UDP 5060 + RTP 10000-10200 | **No (preserved)** | Unit 1 *adds* `5060/tcp`, keeps the UDP line; outbound + UDP fallback path intact. |
| `livekit-server`, `livekit-redis` | **No** | `docker compose up -d sip` recreates only `sip`. |
| DOCKER-USER UDP rules / RTP RETURN | **No (preserved)** | Unit 2 *adds* a tcp 5060 allow/deny pair + extends the IP list; the existing udp 5060 + rtp-any rules are rebuilt identically by the same script. |

**Regression gate (run FIRST and LAST):** `lk sip outbound list` shows both outbound trunks
unchanged; `systemctl is-active famit-agent` → `active`; place one real outbound call via the
normal path (`.\call.ps1 <number>`) → Riya answers as before. If outbound regresses at ANY point →
STOP, roll back the last unit only. Full teardown order: Unit 4 → Unit 3 → Unit 5 worker stop →
Unit 2 fw restore → Unit 1 compose restore. Outbound trunks + `agent.py` + `famit-agent.service`
are byte-unchanged throughout.

---

## Sources
- Live read-only inspection 2026-06-11 (this session): `docker ps`, `ss -lnp`, `lk sip
  inbound/dispatch/outbound list`, `/opt/livekit/docker-compose.yml` sip block, `ufw status
  numbered`, `/usr/local/sbin/livekit-vobiz-fw.sh`, service `is-active`, `inbound_agent.py`.
- `design/aim-inbound-wiring-plan.md` (Units 1-6, the 10-IP allowlist, dispatch/trunk shapes).
- `ai_manager_INBOUND_SETUP.md` (founder Vobiz form, DID/IPs/Trunk-ID, test script).
- `docs.vobiz.ai/concepts/ip-whitelisting` (the 10 signaling IPs).
