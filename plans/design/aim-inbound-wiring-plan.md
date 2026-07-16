# AI Manager — Inbound Voice Wiring Plan (OUR side)

**Status:** PLAN ONLY. Apply this **after the AI Manager build finishes** and after the founder
returns the Vobiz Trunk ID + inbound source IP (see `ai_manager_INBOUND_SETUP.md` Section C).
**Hard rule:** additive, backup-first, latency-safe. The **live outbound earner** (`agent.py` /
`capsy` worker, `famit-agent.service`, outbound trunks `ST_fmtVmNJmpzKa`/`ST_LH8ighJJtHSi`) is
**NEVER touched, restarted, or reconfigured** by anything here. Inbound is a *separate, parallel*
ingress that reuses the same media plane.

---

## 0. Ground truth verified on the box (read-only, 2026-06-10)

Box `famit-livekit` `168.144.153.145` (blr1). `ssh -i C:\Users\kunal\.ssh\do-blr-test\id_ed25519 famit@168.144.153.145`.

| Fact | Evidence |
|---|---|
| LiveKit stack = docker compose at `/opt/livekit/` | `livekit-server` (v1.8, 127.0.0.1:7880), `livekit-sip` (`livekit/sip:latest`), `livekit-redis`. |
| **SIP container publishes UDP only** | docker-compose `sip.ports`: `"5060:5060/udp"`, `"10000-10200:10000-10200/udp"`. **No TCP 5060 host mapping.** |
| SIP signaling port = 5060, RTP = 10000-10200 | `/opt/livekit/sip.yaml` + `sip.runtime.yaml` (`sip_port: 5060`, `rtp_port: 10000-10200`, `use_external_ip: true`). |
| **0 inbound trunks, 0 dispatch rules today** | `lk sip inbound list` → empty; `lk sip dispatch list` → empty. |
| 2 outbound trunks (the live earner) | `ST_fmtVmNJmpzKa` (TCP) + `ST_LH8ighJJtHSi` (UDP), both `2c24f731.sip.vobiz.ai`, num `+918071583488`, auth `capsy-project/****`, encryption DISABLE. **Do not edit these.** |
| `lk` CLI present | `/tmp/lkbin/lk` (relocate to a stable path before relying on it; `/tmp` may be cleared on reboot). |
| LiveKit creds (for `lk`) | `/opt/livekit/sip.runtime.yaml` + `/opt/famit-agent/.env`: `LIVEKIT_API_KEY=API553b2cd005f320d0`, secret in those files. URL `ws://127.0.0.1:7880`. |
| UFW | allows `5060/udp` from `13.203.7.132` (Vobiz signaling), **`5061/tcp` from `13.203.7.132` (Vobiz SIP TLS — opened but nothing listens on it)**, `10000:10200/udp` from `13.203.7.132` AND from Anywhere (RTP open both dirs), SSH/22. |
| DOCKER-USER iptables | RETURN for udp 10000:10200 (rtp-any) + udp 5060/RTP from `13.203.7.132`; **DROP udp 5060 from everyone else**. **All rules are UDP only** — no TCP path through the Docker chain. |

**The one blocker for inbound:** Vobiz requires **TCP** (UDP→0 responses, memory `famit-voice-agent-working-setup` fix #1). Our SIP container **does not listen on TCP** and the Docker/UFW path is UDP-only. So inbound-over-TCP needs an additive our-side change (Unit 1 below). (Inbound *could* be attempted over UDP since the box does listen UDP — but treat that as a fallback experiment only; the proven-working Vobiz transport is TCP.)

---

## 1. Our inbound SIP endpoint (what Vobiz dials)

For a **self-hosted** LiveKit SIP server the inbound endpoint is simply the box's **public IP : SIP
port** — there is no cloud SIP-domain. So:

```
Origination URI (in Vobiz)  =  sip:168.144.153.145:5060
Transport                   =  TCP   (UDP fallback only)
```

LiveKit matches the inbound call to a trunk by the **dialed DID** + an **IP allowlist**
(`allowedAddresses` = Vobiz signaling IP), then a **dispatch rule** creates a room and dispatches
the `manager` agent. (Confirmed: LiveKit self-host SIP listens on `<public-ip>:5060`, supports
UDP+TCP; with TCP the SIP response IP resolves to the public IP correctly.)

---

## 2. Wiring units (apply in order; each is independently reversible)

### Unit 1 — Enable TCP inbound on the SIP container (additive, backup-first) ⚠️ the real change

**Why:** container publishes UDP 5060 only; Vobiz needs TCP.
**What:** publish **TCP 5060** on the host and ensure the SIP service accepts TCP, WITHOUT removing
the existing UDP mapping (outbound uses the same container; do not disrupt it).

1. **Backup:** `cp /opt/livekit/docker-compose.yml /opt/livekit/docker-compose.yml.bak.aim.$(date +%s)`
   (a `.bak` already exists — make a fresh dated one). Backup `sip.runtime.yaml` likewise.
2. **Add the TCP host port** to the `sip` service `ports:` (keep the UDP line):
   ```yaml
   ports:
     - "5060:5060/udp"          # existing — DO NOT REMOVE (outbound + UDP fallback)
     - "5060:5060/tcp"          # ADD — inbound from Vobiz over TCP
     - "10000-10200:10000-10200/udp"   # existing
   ```
   - The LiveKit SIP service listens on both UDP and TCP on `sip_port` by default; publishing the
     TCP host port is the missing piece. If a newer image needs an explicit transport flag, set it
     in `sip.yaml`/`sip.runtime.yaml` (re-render via the `envsubst` recipe documented in
     docker-compose comments) — verify against `livekit/sip` docs for the pinned image tag first.
3. **Re-render runtime config** (only if you changed `sip.yaml`): the documented recipe —
   `set -a; . /opt/livekit/.env; set +a; envsubst < /opt/livekit/sip.yaml > /opt/livekit/sip.runtime.yaml; chmod 600 /opt/livekit/sip.runtime.yaml`.
4. **Recreate ONLY the sip container** (does NOT touch livekit-server/redis, does NOT touch the
   outbound agent): `cd /opt/livekit && docker compose up -d sip` (compose recreates just `sip`).
   ⚠️ Confirm `livekit-server`, `livekit-redis`, and `famit-agent.service` are untouched after
   (`docker ps`, `systemctl status famit-agent` — should be unchanged/running).
5. **Verify TCP listener:** `ss -tlnp | grep 5060` shows a LISTEN on tcp/5060 (host side, via docker-proxy).
6. **ROLLBACK:** restore the dated `.bak`, `docker compose up -d sip`. Zero impact on outbound
   (it never used the host TCP 5060 mapping).

### Unit 2 — Firewall: allow Vobiz inbound TCP signaling (lock to Vobiz IPs)

**Why:** UFW + DOCKER-USER are UDP-only today; TCP 5060 must be allowed only from Vobiz.
**Note:** UFW already has `5061/tcp` from `13.203.7.132` (stale — Vobiz uses 5060 here). We open 5060/tcp.

1. **Backup current rules:** `sudo iptables-save > /root/iptables.aim.bak.$(date +%s)` (or `famit`’s sudo);
   `sudo ufw status numbered > /opt/livekit/ufw.aim.bak.$(date +%s).txt`.
   **Vobiz SIP-signaling source IPs (CONFIRMED, `docs.vobiz.ai/concepts/ip-whitelisting`, 2026-06-10):**
   `13.203.7.132 65.2.100.211 13.126.98.234 13.235.11.131 13.233.44.61 3.111.255.163 3.111.128.110 43.204.64.203 15.207.232.91 35.154.133.28`
   (all AWS ap-south-1). Inbound can arrive from ANY of these 10 → allowlist **all 10**, not just `13.203.7.132`.
   The box today allows only `13.203.7.132`; this step extends to the full set. (Vobiz notes IPs are
   "subject to change" — re-verify the published list if a call fails from an unlisted source IP.)
2. **UFW** — allow TCP 5060 from EACH of the 10 Vobiz signaling IPs (loop over the list above):
   ```
   for ip in 13.203.7.132 65.2.100.211 13.126.98.234 13.235.11.131 13.233.44.61 \
             3.111.255.163 3.111.128.110 43.204.64.203 15.207.232.91 35.154.133.28; do
     sudo ufw allow proto tcp from $ip to any port 5060 comment 'Vobiz inbound SIP TCP'
   done
   ```
3. **DOCKER-USER chain** — the existing UDP-only chain (`/usr/local/sbin/livekit-vobiz-fw.sh`, run by
   `livekit-vobiz-fw.service`) must gain a **TCP** RETURN for 5060 from each Vobiz IP + a single DROP
   for everyone else, mirroring the UDP rules. Edit that script (backup first), add (loop the 10 IPs):
   ```
   for ip in 13.203.7.132 65.2.100.211 13.126.98.234 13.235.11.131 13.233.44.61 \
             3.111.255.163 3.111.128.110 43.204.64.203 15.207.232.91 35.154.133.28; do
     iptables -I DOCKER-USER -p tcp -s $ip --dport 5060 -j RETURN   # vobiz inbound TCP allow
   done
   iptables -A DOCKER-USER -p tcp --dport 5060 -j DROP              # vobiz inbound TCP deny others
   ```
   then `sudo systemctl restart livekit-vobiz-fw.service` (it's idempotent on boot). Keep the script
   the single source of truth so a reboot re-applies it (don't hand-add transient `iptables` rules).
   RTP (udp 10000:10200) already has the `rtp-any` RETURN covering inbound media — no change needed.
4. **ROLLBACK:** `sudo ufw delete` the added rule(s); restore the fw script `.bak` + restart the service.

### Unit 3 — Create the LiveKit INBOUND trunk (additive; never edits the outbound trunks)

Set env for `lk` first (use the relocated binary, e.g. `/usr/local/bin/lk`):
```
export LIVEKIT_URL=ws://127.0.0.1:7880
export LIVEKIT_API_KEY=API553b2cd005f320d0
export LIVEKIT_API_SECRET=<from /opt/livekit/sip.runtime.yaml>
```
Create an inbound trunk JSON (`aim_inbound_trunk.json`):
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
- `numbers` = the AI Manager DID (swap if the founder bought a NEW dedicated DID → that number).
- `allowed_addresses` = the **10 Vobiz signaling IPs** (CONFIRMED from `docs.vobiz.ai/concepts/ip-whitelisting`,
  2026-06-10; all AWS ap-south-1). Inbound can come from any of them, so list all 10. Carrier Trunk ID
  for this DID = `317a5dce-9237-4ff9-8de9-54b85c2dfe2d` (`AIM_INBOUND_TRUNK_ID`, informational — LiveKit
  matches by DID + `allowed_addresses`, not by the carrier Trunk ID).
- **Auth:** prefer IP-allowlist (above). If Vobiz can only do SIP-digest inbound, add
  `"auth_username":"aim-inbound","auth_password":"<the password from ai_manager_INBOUND_SETUP.md>"`
  — and it MUST match exactly what the founder entered in the Vobiz form.

Apply: `lk sip inbound create aim_inbound_trunk.json` → capture the returned `ST_<id>` (this is OUR
inbound trunk id; distinct from the carrier's "Trunk ID" the founder sends).

### Unit 4 — Create the DISPATCH RULE (DID → room → `manager` agent)

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
- `dispatchRuleIndividual` → a fresh room per inbound call (`aim-<unique>`), correct for a 1:1
  command session. (Do NOT use a static `pin` on the rule — our real per-tenant hashed PIN is
  enforced in-agent at S2/S6, per `design/aim-voice-telephony.md` §4.2. The rule-level pin is a
  static single value and is NOT our auth.)
- `agents: [{agent_name:"manager"}]` auto-dispatches the AI Manager inbound worker (the 2nd worker
  persona, `agent_name="manager"`, registered ALONGSIDE the live `capsy` outbound worker — never the
  same process). This is **Wiring A** from the telephony design (lowest latency).

Apply: `lk sip dispatch create aim_dispatch_rule.json`. Verify: `lk sip dispatch list` shows it bound
to the inbound trunk only; `lk sip outbound list` is **unchanged** (both outbound trunks intact).

### Unit 5 — Register/start the `manager` inbound worker (the 2nd persona)

- The AI Manager voice front registers a **second** LiveKit worker:
  `WorkerOptions(entrypoint_fnc=inbound_entrypoint, agent_name="manager", port=<AIM_AGENT_HTTP_PORT>)`,
  in its **own systemd unit** (per the dedicated-service architecture / `design/aim-architecture.md`),
  **co-located on this box** so STT/LLM/TTS round-trips match the outbound agent's ~1.1s latency
  (residual-risk #5 in the telephony design — do NOT land it on the API box).
- It **copies the tuned `AgentSession` kwargs verbatim** from `agent.py` L597-651 (preemptive_generation,
  endpointing delays, barge-in) so latency is inherited, not re-derived. It imports the AI Manager
  service modules (state machine, firewall/policy/risk) — it does **not** import or restart `agent.py`.
- Dormancy: gated by `AIM_ENABLED=1` + `AIM_INBOUND_TRUNK_ID` set. With them unset the worker doesn't
  dispatch and inbound is inert (status `sip:not_configured`).

### Unit 6 — Map the founder as an authorized user + enroll PIN

1. **Authorized user:** insert/seed into `ai_manager_authorized_users` (the dedicated service's PG
   schema, FORCE-RLS, vendor-scoped) for the founder's tenant:
   - `phone_number = "+917861019021"` (as entered), `normalized_phone_number = "917861019021"`
     (canonical digits). Store BOTH so caller-ID matching works across formats.
   - **Match logic must use the `_match_forms()` expansion** (`{917861019021, 7861019021, 07861019021}`)
     vs `normalized_phone_number` — the CRM-core silent-join fix — or a `+91…` row won't match a
     caller-ID arriving as bare-10/leading-0 (`design/aim-voice-telephony.md` §2.2).
   - `role` = `admin` (founder), `is_active = true`.
2. **Enroll PIN:** set the founder's PIN via the secure path (dashboard / service `set_pin`), which
   stores **Argon2id (per-user, peppered)** — never plaintext, never over the voice line
   (`memory/brain/mod-ai-manager.md`: real symbol is `set_pin`/`check_pin`, NOT `verify_pin`). 4 or
   6 digits per the founder's choice.
3. **Verify mode:** set `ai_manager_profiles.verify_mode` for this tenant — default `dtmf` (keypad
   digits arrive as events, never through STT/recording — the leak-proof channel). Spoken-PIN is the
   recording-suppressed fallback.

---

## 3. Verify steps (prove inbound works WITHOUT breaking outbound)

1. **Outbound untouched (do FIRST and LAST):** `lk sip outbound list` shows both
   `ST_fmtVmNJmpzKa` + `ST_LH8ighJJtHSi` unchanged; `systemctl status famit-agent` active;
   place one test outbound call via the normal path (`.\call.ps1 <number>`) → Riya answers as before.
   If outbound regressed at any point → STOP, roll back the last unit.
2. **TCP listener up:** `ss -tlnp | grep ':5060'` shows tcp LISTEN (Unit 1).
3. **Firewall correct:** `sudo ufw status | grep 5060` shows tcp allow from Vobiz only; DOCKER-USER
   has the TCP allow+deny pair (Unit 2). A TCP connect to 5060 from a non-Vobiz IP is dropped.
4. **Trunk + rule present:** `lk sip inbound list` shows `aim-inbound` (DID + allowed address);
   `lk sip dispatch list` shows `aim-inbound-dispatch` → `manager`.
5. **Worker registered:** the `manager` worker shows healthy on its HTTP port; LiveKit lists the
   agent as available.
6. **Live call:** founder calls `+918071583488` from `+917861019021` → SIP INVITE hits the box
   (tail `docker logs livekit-sip` for the INVITE from `13.203.7.132`) → room `aim-…` created →
   `manager` joins → greeting heard. Then run the founder TEST SCRIPT (`ai_manager_INBOUND_SETUP.md`
   §B2): safe command (no PIN) → risky command (PIN demanded) → correct PIN+confirm executes →
   wrong PIN refuses+locks.
7. **Audit + masking:** `ai_manager_sessions` row written; transcript present; **grep the session +
   audit for the raw PIN → 0 hits** (PIN masked in text AND recording-suppressed around capture).

---

## 4. Reversal (full teardown, no trace on outbound)

In reverse order: delete dispatch rule (`lk sip dispatch delete <id>`) → delete inbound trunk
(`lk sip inbound delete <ST_id>`) → stop/disable the `manager` worker unit → remove the TCP UFW +
DOCKER-USER rules (Unit 2 rollback) → restore `docker-compose.yml.bak.aim.*` and `docker compose up
-d sip` (Unit 1 rollback). Outbound trunks, `agent.py`, and `famit-agent.service` are byte-unchanged
throughout — they never referenced any inbound object.

---

## 5. Open items carried from the founder (gate the live test)
- Vobiz **Trunk ID** (carrier-side) — ✅ RECEIVED: `317a5dce-9237-4ff9-8de9-54b85c2dfe2d`
  (`.env.local` `TRUNK_ID` = `AIM_INBOUND_TRUNK_ID`). Informational only.
- Vobiz **inbound source IP(s)** — ✅ RESOLVED from Vobiz public docs: the **10 signaling IPs** listed
  in Units 2/3 (`13.203.7.132` is one of them). The box currently allows only `13.203.7.132`, so the
  **single most important wiring fix is extending UFW + DOCKER-USER + `allowed_addresses` to all 10** —
  **this is the most likely cause of a failed first call.** (Vobiz says IPs are subject to change;
  optional belt-and-braces = ask Vobiz which IP serves this DID, to tighten the list.)
- **Transport** — confirm Vobiz inbound is TCP (Unit 1 enables it). If Vobiz only originates UDP,
  test the UDP path (box already listens UDP) but expect the known UDP-flakiness; push for TCP.
- **DID choice** — reuse `+918071583488` vs a new dedicated DID (changes `numbers` in Unit 3).
- **DLT registration** — carrier-side compliance; not a technical blocker for the test call but
  required for production calling in India.
- Founder **PIN** + verify mode — enrolled in Unit 6.

## Sources
- Live box read-only inspection 2026-06-10 (docker-compose, sip.yaml/sip.runtime.yaml, `lk sip
  inbound/outbound/dispatch list`, `ufw status`, `iptables -L DOCKER-USER`).
- `design/aim-voice-telephony.md` (Wiring A/B, state machine S0–S_END, §2.2 `_match_forms`, §4 PIN).
- `memory/brain/mod-ai-manager.md` (real firewall symbols set_pin/check_pin/mint_step_up; Argon2id PIN).
- `memory/famit-voice-agent-working-setup.md` (TCP-not-UDP, RTP firewall, tuned latency).
- LiveKit self-hosted SIP docs (`<public-ip>:5060`, UDP+TCP, inbound trunk `allowed_addresses` +
  dispatch rule); Vobiz docs (Origination URI `sip:host:port` + transport udp/tcp/tls, IP-ACL vs creds).
</content>
