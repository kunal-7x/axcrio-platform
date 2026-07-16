# VOBIZ OUTBOUND "FAKE-ANSWER / NO RING" — ROOT CAUSE INVESTIGATION

Date: 2026-06-12 (investigated)
Box: famit@168.144.153.145 (droplet `famit-livekit`)
Trunk: LiveKit outbound `ST_fmtVmNJmpzKa` (TCP) -> Vobiz `2c24f731.sip.vobiz.ai`
DID / outbound CLI: +918071583488 (account MA_0UX9IR0K)

---

## TL;DR — THE ORIGINAL PREMISE WAS WRONG. IT IS NOT A VOBIZ PROBLEM.

The "fake-answer with no ring" is **NOT** a Vobiz-side carrier / caller-ID / DLT / KYC /
balance / route problem, and **NOT** a caller-ID change.

**The real cause is a host-side firewall bug on the voice box itself.** The droplet's
`DOCKER-USER` iptables chain **silently DROPs the livekit-sip container's OUTBOUND SIP
INVITE to Vobiz on TCP port 5060.** The SIP INVITE therefore **never reaches Vobiz at
all** — so Vobiz never rings the phone. The thing that looked like an "instant SIP join /
fake-answer" in the log is actually the **internal LiveKit room join** (the SIP
participant joining the *LiveKit room*), which happens ~1s after API call and is
**unrelated to the PSTN leg**. ~2 minutes later every one of these calls ends with:

```
SIP invite failed  error="transport<TCP> dial err=dial tcp :0->13.203.7.132:5060: connect: connection timed out"
status=0  result="server_error"  reason="invite-failed"
```

That `connection timed out` is the firewall DROP (a DROP looks like a timeout, not a reject).

---

## EVIDENCE (proven, reproducible)

### 1. The SIP INVITE never connects — it times out at TCP
From `docker logs livekit-sip`, the 21:11 calls to BOTH +917861019021 and +916375548830
(the exact calls cited as "fake-answer"):
- 21:11:39 / 21:11:50 — "SIP participant joined room"  ← LiveKit ROOM join, NOT a PSTN answer
- 21:13:52 / 21:14:04 — "SIP invite failed", `dial tcp :0->13.203.7.132:5060: connect: connection timed out`, `reason=invite-failed`

Every outbound call in the current container's history ends in `invite-failed` (TCP dial timeout).
No `200 OK`, no `180`, no `486` ever came back from Vobiz on the outbound leg — because the INVITE never left the box.

### 2. Host CAN reach Vobiz; the container CANNOT (same destination, same box)
- From the **host** netns:  `TCP 13.203.7.132:5060` and `65.2.100.211:5060` => **OPEN** (3/3 retries).
- From **inside the `livekit_livekit` Docker network** (where livekit-sip runs), via a throwaway
  `nicolaka/netshoot` container on the same network:
  - `13.203.7.132:5060` => **TIMED OUT**
  - `65.2.100.211:5060` => **TIMED OUT**
  - `13.233.44.61:5060`  => **TIMED OUT**
  - `13.203.7.132:5061` (SIP-TLS) => **SUCCEEDED**  ← same IP, different port works
The host bypasses the Docker FORWARD/DOCKER-USER chain; the container does not. Port 5061
works because only 5060 (and the RTP range) are denied.

### 3. The firewall is dropping the packets — counters prove it
`iptables -L DOCKER-USER -n -v --line-numbers` shows, IN ORDER:
- Rules 12–21: `RETURN` (allow) for `tcp dpt:5060` but matched on **SOURCE = <Vobiz IP>** (i.e. these only
  permit traffic *coming FROM* Vobiz — the inbound/return direction).
- Rule 33: `DROP  tcp dpt:5060  /* livekit-vobiz deny */`  with **219 packets / 13000 bytes dropped**.
- Rule 32: `DROP  udp dpt:5060` with 9 packets dropped.

An **outbound** INVITE (container -> Vobiz) has **source = container bridge IP** and dport 5060, so it
matches NONE of the `-s <vobiz>` allow rules and falls straight through to rule 33 = DROP.
There is **no** `-d <vobiz>` (destination) allow rule and **no** conntrack ESTABLISHED/RELATED RETURN
at the top of the chain. So the firewall is effectively *inbound-only*: it lets Vobiz reach the
container but blocks the container from reaching Vobiz.

This is why inbound calls (e.g. fromUser 06375548830, status 486 in the same log) worked fine
while every outbound call dies.

---

## WHY THE "CALLER-ID / DLT / VOBIZ ROUTE" THEORY IS RULED OUT
- The CLI `+918071583488` IS correctly set (it is the trunk `Numbers` field on both
  `ST_LH8ighJJtHSi` UDP and `ST_fmtVmNJmpzKa` TCP). `create_sip_participant` in caller.py:2059
  passes NO per-call from-number, so the From always comes from the trunk = +918071583488. It did not change.
- A caller-ID/DLT/KYC reject would produce a SIP **4xx/6xx response** (e.g. 403/603) FROM Vobiz.
  Here Vobiz sends **nothing** — the INVITE never arrives (TCP SYN dropped at our own box). A carrier
  cannot "fake-answer" a call it never received.

---

## THE FIX (box-side, safe, no agent.py touch)

Add allow (RETURN) rules to `DOCKER-USER` **before** the deny rules, matching the OUTBOUND
direction by **destination** IP = Vobiz on dport 5060 (TCP + UDP). Most robust is also to add a
conntrack ESTABLISHED,RELATED RETURN at the top so return packets are never reconsidered.

Vobiz SIP signaling IPs (the full allow-set already used for inbound, reused here for `-d`):
  13.203.7.132, 65.2.100.211, 13.233.44.61, 13.235.11.131, 13.126.98.234,
  3.111.255.163, 3.111.128.110, 43.204.64.203, 15.207.232.91, 35.154.133.28

Minimum to ring NOW (trunk is TCP): allow `-d 13.203.7.132` and `-d 65.2.100.211` on tcp/5060.
(Applied — see "FIX APPLIED" below.)

This change is purely additive (insert RETURN rules above the DROPs). It does not touch agent.py,
caller.py, the LiveKit trunk, or the Vobiz account. famit-caller does not even need a restart for
iptables (the kernel applies immediately); livekit-sip picks up the next call attempt.

### Make it persist across reboot
The DOCKER-USER rules are not auto-persistent unless something re-applies them. After verifying,
persist with `netfilter-persistent save` (if installed) OR add the insert commands to the same
script/unit that currently builds the DOCKER-USER vobiz rules (search the box for the script that
wrote the `livekit-vobiz allow/deny` comments and add the `-d` outbound allows there).

---

## FIX APPLIED + TEST RESULT  ✅ RESOLVED

### What was changed (box-side only; agent.py NOT touched)
File: `/usr/local/sbin/livekit-vobiz-fw.sh` (the systemd-managed Vobiz firewall builder).
Added an "OUTBOUND aim-fix" block that inserts, at the TOP of `DOCKER-USER` (before the DROPs):
1. `-m conntrack --ctstate ESTABLISHED,RELATED -j RETURN`  (let return traffic pass untouched)
2. For each of the 10 Vobiz IPs: `-p tcp -d <ip> --dport 5060 -j RETURN` and the udp equivalent
   (allow the container's NEW outbound INVITE by DESTINATION = Vobiz).
Then re-ran `systemctl restart livekit-vobiz-fw.service` (Type=oneshot, enabled, RemainAfterExit) so
it is **persistent across reboot and docker restarts**.

Backups (on box): `/usr/local/sbin/livekit-vobiz-fw.sh.OUTBOUNDbak.1781213131`,
`/root/iptables.OUTBOUNDbak.1781213131` (full `iptables-save`).
ROLLBACK: restore the script backup + `systemctl restart livekit-vobiz-fw.service` (or
`iptables-restore < /root/iptables.OUTBOUNDbak.1781213131`).

### Verification
- Container -> Vobiz `5060` BEFORE: timed out (both IPs).  AFTER: `Connection ... 5060 succeeded!` (both IPs).
- `DOCKER-USER` rule 33 (`tcp dpt:5060 deny DROP`) had **219 dropped packets** before; counter now **0** and not incrementing.
- **Live test call placed to +917861019021** via `place_call.py` => returned **`ANSWERED`**.
  SIP log (room `famit-917861019021-934de6`, callID SCL_KyrKbVv5k5vF):
  INVITE 21:27:40 -> ~13s of real ringing -> 21:27:53 `using codecs PCMU/8000` + media dest
  `18.96.230.208:18004` -> **`Outbound SIP call established`** -> RTP stream accepted, track subscribed.
  This is the full, healthy carrier lifecycle that was previously impossible (every prior call died at
  `invite-failed / connection timed out`).

### Bottom line for the founder
- The phone now RINGS and connects. Nothing to do on the Vobiz portal. No Vobiz support ticket needed.
- The caller-ID +918071583488 is correct and approved (inbound to it works; outbound now connects with it).
- This was a self-inflicted host firewall rule (built for inbound-only) silently dropping the outbound
  SIP INVITE. Now fixed and persistent. If outbound ever breaks again after a Vobiz IP change, add the new
  Vobiz IP to `VOBIZ_IPS` in `/usr/local/sbin/livekit-vobiz-fw.sh` and restart the service.

