# LiveKit Agent Capsy

Realtime Hinglish voice agent using:

- LiveKit Agents for realtime rooms and SIP calls
- Vobiz SIP trunking for phone connectivity
- ElevenLabs realtime STT (`scribe_v2_realtime`) or Sarvam STT (`saarika:v2.5`)
- Groq Llama LLM (`llama-3.1-8b-instant` by default)
- Sarvam Bulbul TTS (`bulbul:v3`) or ElevenLabs TTS (`eleven_flash_v2_5`)

## Setup

1. Copy `.env.example` to `.env.local` and fill in the keys.
2. Install dependencies:

```bash
uv sync
```

3. Download local LiveKit model assets:

```bash
uv run python -m livekit.agents download-files
```

4. Start local LiveKit in another terminal:

```bash
livekit-server --dev
```

The local defaults in `.env.local` are:

```bash
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret
```

5. Run the agent for development:

```bash
uv run python src/agent.py dev
```

For latency testing and production-like calls, use `start` mode instead. It
prewarms worker processes and avoids file-watch reloads during calls:

```bash
uv run python src/agent.py start --log-level info
```

`livekit-server --dev` is enough for local room/agent testing, but not enough for SIP phone calls. Self-hosted SIP also requires Redis and the `livekit-sip` service connected to the same LiveKit server. Without those, SIP trunk setup fails with `sip not connected (redis required)`.

To run the full self-hosted SIP stack instead:

```bash
docker compose -f selfhost/docker-compose.yaml up -d
```

See `selfhost/README.md` for SIP port and Vobiz notes.

## Vobiz Connection

Create a Vobiz SIP trunk in the Vobiz console and add these values to `.env.local`:

- `VOBIZ_SIP_DOMAIN`
- `VOBIZ_SIP_TRANSPORT` (`udp`, `tcp`, `tls`, or `auto`)
- `VOBIZ_USERNAME`
- `VOBIZ_PASSWORD`
- `VOBIZ_PHONE_NUMBER`

Then create the LiveKit outbound trunk:

```bash
uv run python scripts/setup_vobiz_trunk.py
```

Add the printed `LIVEKIT_SIP_TRUNK_ID` to `.env.local`.

Make an outbound call:

```bash
uv run python scripts/make_call.py +91XXXXXXXXXX
```

The call script waits up to `CALL_RINGING_TIMEOUT_SECONDS` for the PSTN leg to answer or fail.

For inbound calls with local LiveKit, you also need a local LiveKit SIP service and a public reachable address/tunnel for Vobiz. Route the Vobiz trunk inbound destination to that SIP address, then create a LiveKit inbound trunk and dispatch rule with agent name `voice-assistant`.

## Knowledge / RAG

The agent can ground answers in local files from `knowledge/`. Add `.md`,
`.txt`, or `.csv` files there and restart the worker. Files beginning with `_`
are ignored.

Search is local and runs before every LLM turn, so it avoids a second API call
and keeps latency predictable. Tune it with:

```bash
KNOWLEDGE_ENABLED=true
KNOWLEDGE_DIR=knowledge
KNOWLEDGE_TOP_K=2
KNOWLEDGE_MAX_CHARS=500
KNOWLEDGE_CHUNK_CHARS=650
KNOWLEDGE_MIN_SCORE=0.45
SALES_BRAIN_ENABLED=false
SALES_BRAIN_FILE=knowledge/groq_real_estate_sales_brain.md
```

Test retrieval before a call:

```bash
uv run python scripts/search_knowledge.py "Mumbai flat budget"
```

## Required Environment

The agent requires:

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `GROQ_API_KEY`
- `ELEVEN_API_KEY` if `STT_PROVIDER=elevenlabs` or `TTS_PROVIDER=elevenlabs`
- `SARVAM_API_KEY` if `STT_PROVIDER=sarvam` or `TTS_PROVIDER=sarvam`

Provider switches:

```bash
STT_PROVIDER=elevenlabs
TTS_PROVIDER=elevenlabs
```

For the lowest-latency stable default, use ElevenLabs realtime STT, Groq Llama
8B Instant, short replies, and ElevenLabs Flash TTS:

```bash
STT_PROVIDER=elevenlabs
GROQ_LLM_MODEL=llama-3.1-8b-instant
TTS_PROVIDER=elevenlabs
ELEVEN_STT_SERVER_VAD=true
ELEVEN_STT_MIN_SILENCE_DURATION_MS=350
ELEVEN_TTS_MODEL=eleven_flash_v2_5
ELEVEN_TTS_VOICE_ID=your_api_enabled_voice_id
ELEVEN_TTS_AUTO_MODE=true
ELEVEN_TTS_STREAMING_LATENCY=1
ELEVEN_TTS_SYNC_ALIGNMENT=false
GROQ_LLM_MAX_COMPLETION_TOKENS=64
AGENT_MAX_ENDPOINTING_DELAY=0.4
```

Vobiz outbound calling also requires:

- `VOBIZ_SIP_DOMAIN`
- `VOBIZ_SIP_TRANSPORT`
- `VOBIZ_USERNAME`
- `VOBIZ_PASSWORD`
- `VOBIZ_PHONE_NUMBER`
- `LIVEKIT_SIP_TRUNK_ID`
