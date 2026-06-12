# Inbound SIP wiring — APPLIED ARTIFACTS (Queue #3, wave sip3wire, 2026-06-12)

DID **+918071583488** → LiveKit inbound trunk → dispatch → `manager` worker. Additive,
earner-gated. Box `famit@168.144.153.145` `/opt/livekit/` + `/usr/local/sbin/livekit-vobiz-fw.sh`.

## Live object IDs (verified on box)
- **Inbound trunk** `ST_K785ASpNh5ow` (`aim-inbound`) — numbers `+918071583488`, 10 Vobiz
  `allowed_addresses`, enc DISABLE.
- **Dispatch rule** `SDR_RaCvweSMA2p5` (`aim-inbound-dispatch`) — trunk `ST_K785ASpNh5ow`,
  Individual(Caller) room prefix `aim-`, agent `manager`.
- **Outbound trunks UNCHANGED** (the earner): `ST_LH8ighJJtHSi` (UDP) + `ST_fmtVmNJmpzKa` (TCP).

## Reproduce (if torn down)
```
export LIVEKIT_URL=ws://127.0.0.1:7880 LIVEKIT_API_KEY=API553b2cd005f320d0
export LIVEKIT_API_SECRET="$(grep -m1 -oP 'api_secret:\s*\K\S+' /opt/livekit/sip.runtime.yaml)"
/usr/local/bin/lk sip inbound  create aim_inbound_trunk.json   # -> ST_<id>
# edit aim_dispatch_rule.json trunk_ids -> that ST_<id>
/usr/local/bin/lk sip dispatch create aim_dispatch_rule.json
```

## Layers (all already applied on box from prior wave; verified this wave)
- **U1** SIP container publishes `5060/tcp` + `5060/udp` + RTP `10000-10200/udp`
  (`/opt/livekit/docker-compose.yml` sip.ports). DNS pin `extra_hosts: 2c24f731.sip.vobiz.ai:13.203.7.132`.
- **U2** `/usr/local/sbin/livekit-vobiz-fw.sh`: 10 Vobiz IPs, `apply tcp 5060` (inbound allow/deny),
  conntrack ESTABLISHED RETURN + dest-IP outbound allows (earner fix), IPv6 tcp 5060 deny.
- **U3/U4** trunk + dispatch above.
- **U5** `manager` worker (`aim-voice-agent.service`, port 8091) REGISTERED + dispatchable.

## Files in this dir
- `inbound_trunks.json` / `dispatch_rules.json` / `outbound_trunks.json` — live `lk ... list --json` exports.
- `aim_inbound_trunk.json` / `aim_dispatch_rule.json` — reproducible create payloads.

Provenance backups on box: `*.SIPbak.20260612-035043` (compose, fw script, `/root/iptables.SIPbak.*`).
