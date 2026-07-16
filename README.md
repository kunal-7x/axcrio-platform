# Haptic by Famit AI

AI voice telecaller ("Riya") + admin dashboard. An outbound voice agent that calls
leads, runs a campaign script, and books next steps — driven from a web dashboard.

This repo is the **working, cleaned** build:
- **Lean voice brain** (loop-free; ~860 tokens/turn) — the big legacy brain caused
  `llama` to loop / hang under prompt bloat, so this uses the compact brain.
- Dashboard → backend → LiveKit + SIP (Vobiz) → real phone call.

## Layout
```
famit-panel/    Next.js dashboard (frontend)
droplet_work/   Python backend (caller.py = FastAPI) + voice agent (agent.py) + brain (prompt.py)
voice_kernel/   optional kernel modules (OFF by default)
voice_ops/      backend ops (booking, reporting, telephony, ...)
selfhost/       docker-compose for local LiveKit + SIP + Redis
scripts/        setup helpers (e.g. setup_vobiz_trunk.py)
knowledge/      RAG corpus
run_backend.py  launcher: backend on :8091
run_worker.py   launcher: voice-agent worker (registers as 'famit-local')
plans/          all planning / design / state docs (moved out of the way)
```

## Secrets (NOT in git)
Copy `.env.example` to `droplet_work/.env` and fill in real keys (Groq, ElevenLabs,
Sarvam, Vobiz SIP trunk, LiveKit). These are shared out-of-band — never commit them.
`famit-var/` (admin secret + tenants) is runtime data and is git-ignored.

## Run locally
```bash
# 1. Infra (LiveKit + SIP + Redis)
docker compose -f selfhost/docker-compose.yaml up -d

# 2. Python env
python3 -m venv .venv && . .venv/bin/activate
pip install "livekit-agents[elevenlabs,groq,sarvam,silero,turn-detector]~=1.3" \
            livekit-api fastapi "uvicorn[standard]" python-multipart httpx python-dotenv protobuf
python droplet_work/agent.py download-files   # one-time model weights

# 3. Backend  (terminal A)
python run_backend.py            # http://127.0.0.1:8091

# 4. Worker   (terminal B)
python run_worker.py             # registers 'famit-local'

# 5. Frontend (terminal C)
cd famit-panel && npm install --legacy-peer-deps && npm run dev -- -p 3001
```
The frontend proxies `/api/*` to the backend (see `famit-panel/next.config.ts`).

Open http://localhost:3001 → log in → **Run a Campaign** → add your own number as the
one lead → Start. Your phone rings and Riya speaks.

> A campaign-dial places a **real** Vobiz call — test only with your own number.

## Tuning
- Reply length: `GROQ_MAX_TOKENS` in `run_worker.py` (default 200).
- Groq free tier is 6,000 tokens/min; upgrade to Dev tier for production.
