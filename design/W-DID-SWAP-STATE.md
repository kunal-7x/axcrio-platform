# W-DID-SWAP-STATE.md — Outbound DID swap (Vobiz spam-flag rotation)

> **Status: DONE + VERIFIED LIVE (2026-06-15).** Outbound RINGS again on the NEW DID.
> Old DID `91XXXXXX488` was carrier spam-flagged (SIP 486, no ring). Founder bought a NEW
> DID on the SAME Vobiz account/trunk. This was a pure caller-ID/trunk number swap — no
> pipeline/code rewrite, agent.py untouched.

---

## What changed (minimal change set)

The outbound caller-ID is NOT in `.env` as a number var and NOT hardcoded in any `.py`.
It lives in the **LiveKit SIP OUTBOUND trunk's `numbers` field**. The LiveKit server on the
box (v1.8) does **not** support `UpdateSIPOutboundTrunk` (twirp `bad_route`), so the swap was
done by **creating a new outbound trunk with the new DID** and **repointing the env trunk-id**.

| Item | OLD | NEW |
|---|---|---|
| Outbound trunk in use | `ST_fmtVmNJmpzKa` (vobiz-outbound-tcp, DID `91XXXXXX488`) | `ST_bpGqmc9TL9Ph` (vobiz-outbound-new-did, DID `91XXXXXX457`) |
| `/opt/famit-agent/.env` line 13 `LIVEKIT_SIP_TRUNK_ID` | `ST_fmtVmNJmpzKa` | `ST_bpGqmc9TL9Ph` |
| Vobiz SIP host | `2c24f731.sip.vobiz.ai` | **same** |
| Trunk auth user | `capsy-project` | **same** |
| Trunk auth pass | (same) | **same** — new DID is on the SAME Vobiz trunk/account; no new creds needed |
| Transport | TCP | TCP |

- **agent.py UNCHANGED** — md5 `9150fabe4ff62b4b4470f9a87df346e5` before AND after. Earner not edited, not restarted.
- The new trunk-id is read from env by `place_call.py`, `bridge.py`, `caller.py`, and `aim_voice_agent.py`
  (all `os.getenv("LIVEKIT_SIP_TRUNK_ID", ...)`), so the swap propagates to all outbound dial paths
  via the single env line — no `.py` edit.
- Old trunks `ST_fmtVmNJmpzKa` (TCP) and `ST_LH8ighJJtHSi` (UDP) were **left intact** for instant rollback.
- **INBOUND untouched** — separate trunk `ST_K785ASpNh5ow` (aim-inbound) not modified.

## Backups (on box)
- `.env`: `/opt/famit-agent/.env.VOBIZbak.20260615-164935`
- Outbound trunks JSON snapshot: `/opt/famit-agent/var/did_swap_backup/outbound_trunks.20260615-164817.json`

## Action taken
1. Earner gate BEFORE: agent.py `9150fabe…` / famit-agent PID 2808658 active / caller /health 200.
2. Found caller-ID source = LiveKit outbound trunk `numbers` (not env/code). Same Vobiz host+auth.
3. `lk sip outbound update` unsupported on this LiveKit → created new trunk `ST_bpGqmc9TL9Ph` (same host/auth/TCP, new DID).
4. Backed up `.env`, swapped `LIVEKIT_SIP_TRUNK_ID` line 13 → `ST_bpGqmc9TL9Ph`.
5. Restarted **only** famit-caller (PID 3022373). famit-agent NOT restarted.
6. Placed **exactly ONE** outbound test call to `TEST_PHONE_NO` via `place_call.py` (new trunk). retry_queue left PAUSED.

## Ring result (concrete SIP evidence)
Call `SCL_8QpqwzW6SU4T` / room `famit-…-b9e89e`, via trunk `ST_bpGqmc9TL9Ph`:
- **`inviteToRingingMs: 3463`** → IT RANG (was SIP 486 / no ring before).
- **`inviteToAcceptMs: 21083`** → answered.
- `Outbound SIP call established`; two-way RTP (240 audio packets each way); agent track subscribed.
- famit-agent (earner) received the job, `agent job connected`, ran ~27s, `transcript saved … outcome=answered`.
- Ended by remote **BYE** (`result: success, reason: bye`) = called party hung up. NOT a 486.
- **Conclusion: the carrier spam-flag is GONE on the new DID. Outbound works.**

## Earner gate (before / after)
| Check | Before | After |
|---|---|---|
| agent.py md5 | `9150fabe4ff62b4b4470f9a87df346e5` | `9150fabe4ff62b4b4470f9a87df346e5` (unchanged) |
| famit-agent PID | 2808658 active | 2808658 active (NOT restarted) |
| famit-caller /health | 200 | 200 |
| caller 5xx | 0 | 0 |
| inbound trunk (aim-inbound) | intact | intact |

## ROLLBACK (if the new DID ever misbehaves)
```bash
ssh -i ~/.ssh/do-blr-test/id_ed25519 famit@168.144.153.145
# 1. restore the old env trunk-id
cp /opt/famit-agent/.env.VOBIZbak.20260615-164935 /opt/famit-agent/.env
# (or just: sed -i 's|^LIVEKIT_SIP_TRUNK_ID=ST_bpGqmc9TL9Ph$|LIVEKIT_SIP_TRUNK_ID=ST_fmtVmNJmpzKa|' /opt/famit-agent/.env)
# 2. restart ONLY famit-caller (do NOT restart famit-agent)
sudo systemctl restart famit-caller
# 3. optional cleanup: delete the new trunk
#   lk sip outbound delete ST_bpGqmc9TL9Ph
```
Old trunks `ST_fmtVmNJmpzKa` / `ST_LH8ighJJtHSi` were never deleted, so rollback is just the env line + caller restart.

## Founder action on vobiz.ai (his side — confirm, simple)
Outbound now rings, so nothing is blocking you. To keep it healthy long-term, just confirm with
Vobiz support that the **new number `91XXXXXX457`** is:
1. **Provisioned for OUTBOUND** on your `capsy-project` trunk (it answered our test, so this is already true — just confirm it's permanent, not a trial).
2. **Caller-ID / KYC approved** for outbound dialing (so it doesn't get spam-flagged like the old one).
3. (Optional, recommended) Ask them to keep the **old number `91XXXXXX488` for INBOUND** only — inbound still routes to your box on it.
You do NOT need to touch any console — the swap is done on our side. This is just a "please confirm" message to Vobiz.

---
_Last updated 2026-06-15 by W-DID-SWAP. Earner gate at update: agent.py 9150fabe / PID 2808658 / /health 200 / 0 5xx._
