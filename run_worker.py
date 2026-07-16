#!/usr/bin/env python3
"""Local launcher for the Famit voice-agent WORKER (agent.py dev mode) — portable.

- FAMIT_VAR matches run_backend.py so the worker reads the campaigns the dashboard
  saves (otherwise it falls back to the default GODREJ campaign).
- Unique agent name 'famit-local' so the dashboard dispatch reaches ONLY this worker.
- Unique HTTP port 8092 (8090 may be taken by another local LiveKit worker; sharing
  it makes the job subprocess fail with EADDRINUSE -> the agent never joins -> silence).
- GROQ_MAX_TOKENS raises the per-reply cap so Riya gives fuller answers.

NOTE: agent.main() MUST stay guarded by `if __name__ == "__main__"`. LiveKit spawns
each job in a subprocess (multiprocessing 'spawn') that re-imports THIS module; an
unguarded main() would re-run the worker and re-bind the port -> crash -> silent call.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DW = os.path.join(ROOT, "droplet_work")

os.environ.setdefault("FAMIT_VAR", os.path.join(ROOT, "famit-var"))
os.environ["LIVEKIT_AGENT_NAME"] = "famit-local"
os.environ["AGENT_HTTP_PORT"] = "8092"
os.environ["GROQ_MAX_TOKENS"] = "120"   # per-reply cap + runaway backstop (200 let a ramble run ~37s = a hang)
os.environ["GROQ_LLM_TEMPERATURE"] = "0.55"  # warmer/more natural than the 0.25 default (flat)
os.environ["LANG_MIRROR_V2"] = "1"      # per-turn language steering (English-mirror override)
os.environ["EL_STABILITY"] = "0.65"     # steadier + less emphasis spike on the name
# Smarter, more curious model (0% loop on the lean brain); overrides GROQ_LLM_MODEL in .env.
os.environ["GROQ_LLM_MODEL"] = "meta-llama/llama-4-scout-17b-16e-instruct"
os.chdir(DW)
sys.path.insert(0, DW)

from dotenv import load_dotenv
load_dotenv(os.path.join(DW, ".env"))

if __name__ == "__main__":
    sys.argv = ["agent.py", "dev"]
    import agent
    agent.main()
