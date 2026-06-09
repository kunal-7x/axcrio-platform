# Self-Hosted LiveKit SIP

This starts the pieces required for Vobiz SIP calls:

- Redis
- LiveKit server
- LiveKit SIP service

Start it:

```bash
docker compose -f selfhost/docker-compose.yaml up -d
```

This compose file uses Docker bridge networking with explicit port publishing so it works on Docker Desktop for macOS. For a Linux VPS, host networking is cleaner, but this setup is easier to run from this project folder.

Check status:

```bash
docker compose -f selfhost/docker-compose.yaml ps
docker compose -f selfhost/docker-compose.yaml logs -f livekit sip
```

The compose file uses the same local credentials already in `.env.local`:

```bash
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
```

After the stack is running:

```bash
uv run python scripts/setup_vobiz_trunk.py
```

Copy the printed `LIVEKIT_SIP_TRUNK_ID` into `.env.local`, then place an outbound call:

```bash
uv run python scripts/make_call.py +91XXXXXXXXXX
```

For real inbound/outbound media from Vobiz, the host running this stack must be reachable from the internet on:

- `5060/tcp`
- `5060/udp`
- `10000-10100/udp`

For a laptop behind NAT, that means router port forwarding or a proper public tunnel that supports SIP/RTP UDP. A VPS with a public IP is usually simpler. For higher call capacity, expand both the compose port mapping and `rtp_port` back to `10000-20000`.

For Vobiz inbound routing, the SIP URI should be:

```text
<public-ip-address>:5060
```
