# OUTBOUND EARNER DIAGNOSIS — 2026-06-12 (box famit@168.144.153.145)

## VERDICT
The inbound AI Manager build did **NOT** break outbound call **delivery**. Two
**separate** issues were found; one is a real infra bug I FIXED, the other is a
**Vobiz carrier-side** problem (the reason the founder's phone never rings).

## ISSUE A (FIXED on the box) — flaky TCP/5060 to Vobiz → 50% invite-failed
- Outbound earner dials the **TCP** trunk `ST_fmtVmNJmpzKa`, address =
  hostname `2c24f731.sip.vobiz.ai` which **round-robins across 10 Vobiz IPs**.
  Only **4 of 10** accept TCP/5060 (13.203.7.132, 65.2.100.211, 13.233.44.61,
  15.207.232.91); the other 6 time out on TCP connect.
- Result: ~50% of dials (`10 invite-failed / 10 joined` in a 6h window) died with
  `transport<TCP> dial err=... connect: connection timed out` → no INVITE → no call.
- **FIX APPLIED:** added `extra_hosts: "2c24f731.sip.vobiz.ai:13.203.7.132"` to the
  `sip` service in `/opt/livekit/docker-compose.yml` (backup
  `docker-compose.yml.OUTFIXbak.20260611-205649`), recreated ONLY `livekit-sip`.
  Container now resolves the host to the one reliably-TCP-open IP. Post-fix:
  **0 invite-failed / multiple joined** — the SIP-connect coin-flip is gone.
- NOTE: `lk sip outbound update` is unavailable on this LiveKit server version
  (twirp bad_route), so the trunk address itself can't be edited in place — the
  `extra_hosts` DNS pin is the equivalent fix.
- ROLLBACK: restore the compose backup + `docker compose up -d sip`.

## ISSUE B (ROOT CAUSE of "no phone rings") — Vobiz not delivering to PSTN
- Every connected call shows **instant join (~1s, NO 180 Ringing phase)** then
  `outcome=no_answer`. Vobiz returns 200 OK + bridges media (audio_rx/tx > 0) but
  the **actual mobile never rings** → carrier "fake answer", call is dead air.
- **TIMELINE PROVES it is NOT the inbound build:**
  - Last REAL human pickup: **Jun 10 09:15:06** (+917861019021, interest=80).
  - Inbound AIM build touched the box: **Jun 11 ~16:44–16:47** (31h LATER).
  - All outbound since ~Jun 10 morning = `no_answer` (no handset ever rings),
    including Jun 11 06:04 — BEFORE the inbound work.
  - Lifetime real pickups (answered/interested/not_interested/opt_out) all ≤ Jun 10 09:15.
- ⇒ Outbound PSTN delivery died ~Jun 10, well before any inbound change. This is a
  **Vobiz account/route issue** — most likely outbound balance exhausted OR the
  outbound route/DID was suspended/changed on the Vobiz portal.

## NEXT STEP (founder / carrier — cannot be fixed from the box)
Contact Vobiz / check the Vobiz portal:
1. Outbound calling balance / wallet for account `MA_0UX9IR0K`.
2. Whether outbound termination on DID +918071583488 is active (not suspended).
3. Whether a 180-Ringing / real PSTN route is provisioned (currently auto-answering).
Vobiz creds in `caps/.env.local` §13 (API MA_0UX9IR0K, base https://api.vobiz.ai/api/v1).

## BOX STATE (clean, verified)
- famit-caller / famit-agent / famit-bridge / aim-voice-agent = active. 0 stuck rooms.
- agent.py md5 `9150fabe4ff62b4b4470f9a87df346e5` (earner code byte-identical, untouched).
- Inbound trunk ST_K785ASpNh5ow + dispatch SDR_RaCvweSMA2p5 left in place (scoped to
  inbound trunk only; verified outbound dispatches `agent_name=capsy`, no hijack).
- Firewall RTP (udp 10000-10200) RETURN for any source — never blocked outbound media.
