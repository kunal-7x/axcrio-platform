# Famit / Axcrio — AI Revenue OS (monorepo)

Strangler monorepo for the live AI tele-calling SaaS at **https://panel.famit.in**.
The verdict is **STRANGLE & EVOLVE** — the live system keeps earning; every change is
additive, flag-gated, and non-breaking. See `EXECUTION_PLAN.md` and `design/*.md`.

## Intended layout (target — curation is phased, NOT yet performed)

```
caps/                      # this repo root
├─ backend/                # uv-managed FastAPI /api + LiveKit voice agent (FLAT modules,
│                          #   mirrors /opt/famit-agent exactly). NOT YET POPULATED — the
│                          #   live source lives in droplet_work/ and is git-mv'd in later,
│                          #   serialized with the Phase-1 Postgres work (see EXECUTION_PLAN).
├─ frontend/               # pnpm-managed Next.js panel. NOT YET POPULATED — current app is
│                          #   famit-panel/ ; moved under frontend/ in a later curation unit.
├─ infra/                  # (DROPPED for P0) DigitalOcean is managed via the DO API directly,
│                          #   not Terraform. No infra/ dir or terraform in this phase.
├─ design/                 # execution-ready design specs (one per subsystem)
├─ .github/workflows/      # CI: backend.yml + frontend.yml (dormant until curation) + secrets.yml
├─ .githooks/pre-commit    # gitleaks staged-scan gate (core.hooksPath=.githooks)
├─ droplet_work/           # LIVE backend source (gitignored until curated — local scratch)
├─ famit-panel/            # LIVE frontend source (current Next.js app)
└─ .gitignore .gitleaks.toml .gitattributes .worktreeinclude  # the secrets-gate
```

> Current state: this commit establishes the **git foundation + secrets-gate + CI scaffolding
> + branch model**. It does NOT restructure `droplet_work/` → `backend/` or `famit-panel/` →
> `frontend/`; that curation is a later, P1-coordinated unit (it serializes on the 3,422-line
> `caller.py`). `backend/` and `frontend/` therefore do not exist yet, and the `backend.yml` /
> `frontend.yml` CI jobs are dormant scaffolding (their `paths:` filters won't trigger until
> those directories appear).

## 🔒 THE SECRETS RULE (read before any commit)

This box was compromised once. **A committed secret is an irreversible production incident.**
- `.gitignore` is line 1 (`.env*`, `fortress/`, `droplet_work/`, `*.bak.*`, `*.tgz`, `.next/`,
  `.venv/`, `.claude/`, SSH keys, `**/cred.md`, `**/ALL_CREDENTIALS.md`).
- **`gitleaks` is the net** — `.githooks/pre-commit` runs `gitleaks git --staged` on every commit
  and `.github/workflows/secrets.yml` runs it on every push/PR (full history). Both block on any
  finding. If unsure whether something is a secret, treat it as one and ignore it.
- Secrets live OUTSIDE the repo (`fortress/cred.md` is gitignored; `lead/ALL_CREDENTIALS.md` is
  outside the tree). Founder must ROTATE the burned `.env.local` keys (Groq/ElevenLabs/Sarvam/Vobiz).

## Contributing / branch model

See `CONTRIBUTING.md`: worktree → `feat/*` → PR → green CI → squash-merge → protected `main`.

---

# LiveKit Agent Capsy (legacy standalone skeleton — NOT the deployed backend)

> The section below documents the older standalone LiveKit skeleton under `src/`, `selfhost/`,
> `scripts/` + the root `pyproject.toml`. It is **not** what runs in production (the live backend
> is `droplet_work/`, deployed flat at `/opt/famit-agent`). Kept for reference; left in place.

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
