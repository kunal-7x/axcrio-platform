# voice-agent-v2 — clean voice telecaller (ROUND-10)

A new, self-contained LiveKit voice-telecaller worker that runs **side-by-side** with the live
earner (`capsy`) as **`capsy-v2`**. The perfect voice is preserved byte-for-byte; the bug
machinery + prompt scripts are gone; the brain runs on a bigger model. The live earner is never
touched. The founder's real call is the only verdict.

## What changed vs the live agent (everything else is byte-identical)
1. **Clean script-free prompt** (`prompt.py`) — role + hard rules + facts only, no scripts.
2. **Closure trimmed** (`agent.py`) — the call ends ONLY on the caller's explicit hang-up
   ("bye"/"रखता हूँ"/"cut the call"/do-not-call). Objections never cut the call; no auto-book.
3. **Bigger model** (`.env`) — `GROQ_LLM_MODEL=llama-3.3-70b-versatile`.

## Files
- `agent.py` — entrypoint (= live `f4d75e49` with 2 subtractive edits). The voice/STT/LLM/opener/
  language/booking/memory constructors are verbatim from live.
- `prompt.py` — the clean brain.
- `memory.py`, `langdetect.py`, `voice_ops/booking/datetime_resolve.py` — verbatim copies from the box.
- `tests/replay.py` — offline live-Groq sanity gate.

## Deploy (isolated — live earner untouched)
```bash
# 1. ship the code to a SEPARATE dir (never /opt/famit-agent)
rsync -a voice-agent-v2/ famit@168.144.153.145:/opt/famit-agent-v2/   # (exclude tests if desired)

# 2. build v2's .env = the live .env with ONLY the model + agent-name + port changed
ssh famit@... 'cp /opt/famit-agent/.env /opt/famit-agent-v2/.env
  sed -i "s#^GROQ_LLM_MODEL=.*#GROQ_LLM_MODEL=llama-3.3-70b-versatile#" /opt/famit-agent-v2/.env
  grep -q "^GROQ_LLM_MODEL=" /opt/famit-agent-v2/.env || echo "GROQ_LLM_MODEL=llama-3.3-70b-versatile" >> /opt/famit-agent-v2/.env
  echo "LIVEKIT_AGENT_NAME=capsy-v2" >> /opt/famit-agent-v2/.env
  echo "AGENT_HTTP_PORT=8091"        >> /opt/famit-agent-v2/.env'   # distinct from live :8090

# 3. syntax-check on the box venv
ssh famit@... '/opt/capsy-agent/.venv/bin/python -m py_compile /opt/famit-agent-v2/agent.py /opt/famit-agent-v2/prompt.py && echo OK'

# 4. sanity gate (prints replies on the failing scenarios; never prints keys)
ssh famit@... 'cd /opt/famit-agent-v2 && /opt/capsy-agent/.venv/bin/python tests/replay.py'

# 5. run v2 as its OWN systemd unit (registers as agent_name capsy-v2)
#    EnvironmentFile=/opt/famit-agent-v2/.env, ExecStart=.../python /opt/famit-agent-v2/agent.py start
ssh famit@... 'systemctl start famit-agent-v2 && systemctl status famit-agent-v2 --no-pager | head'
```
A test call dispatched to **`capsy-v2`** routes to the new worker; every live call (dispatch
`capsy`) keeps hitting the untouched earner.

## Verify before the founder's call
- `famit-agent` (live `capsy`) still `active`, md5 of `/opt/famit-agent/agent.py` == `f4d75e49…`.
- `famit-agent-v2` `active`, NRestarts=0, no tracebacks in `journalctl -u famit-agent-v2`.
- `replay.py` replies read like a warm human: objection → keeps selling, English → English,
  price → one number in words, "haan" w/o time → asks for a time, no `## Step` / `₹` / digit-spam.

## Rollback
Nothing to roll back on the earner — `capsy` ran untouched throughout. Stop v2 with
`systemctl stop famit-agent-v2`. (A later live flip → v2 is a separate, deliberate step.)
