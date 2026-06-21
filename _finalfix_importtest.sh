#!/bin/bash
cd /opt/famit-agent || exit 9
VENV=/opt/capsy-agent/.venv/bin/python
echo "=== F) TTS constructor span DIFF vs FINALFIXbak (expect identical) ==="
# isolate lines 1005..1035 region (the TTS constructor) from both and diff
sed -n '1000,1040p' agent.py > /tmp/_tts_new.txt
# find same region in backup by anchoring on 'tts = elevenlabs.TTS('
awk '/tts = elevenlabs\.TTS\(/{f=1} f{print} /turn_detection|tts=tts,/{if(f)exit}' agent.py.FINALFIXbak.20260620-finalfix > /tmp/_tts_bak_block.txt
awk '/tts = elevenlabs\.TTS\(/{f=1} f{print} /turn_detection|tts=tts,/{if(f)exit}' agent.py > /tmp/_tts_new_block.txt
if diff -q /tmp/_tts_bak_block.txt /tmp/_tts_new_block.txt >/dev/null; then echo "TTS_BLOCK_IDENTICAL_OK"; else echo "TTS_BLOCK_DIFFERS_FAIL"; diff /tmp/_tts_bak_block.txt /tmp/_tts_new_block.txt; fi

echo "=== G) import-test agent module under service venv (no DB/no network init) ==="
# import without running entrypoint; LIVEKIT/agents import is the risk surface for the LLM wiring
$VENV - <<'PYEOF'
import sys, importlib.util, traceback, os
os.environ.setdefault("GROQ_API_KEY","test-dummy-key-not-used-for-import")
spec = importlib.util.spec_from_file_location("agent_under_test", "/opt/famit-agent/agent.py")
m = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(m)
    print("IMPORT_OK: agent.py imported, no exception")
except SystemExit as e:
    print("IMPORT_SYSEXIT (entrypoint guard, acceptable):", e)
except Exception:
    print("IMPORT_FAIL:")
    traceback.print_exc()
    sys.exit(1)
PYEOF

echo "=== H) PROVE extra_body assignment works on a real groq.LLM instance ==="
$VENV - <<'PYEOF'
import os, traceback
os.environ.setdefault("GROQ_API_KEY","test-dummy-key-not-used")
try:
    from livekit.plugins import groq
    llm = groq.LLM(model="meta-llama/llama-4-scout-17b-16e-instruct", max_completion_tokens=220)
    # exactly what the patch does:
    existing = getattr(llm._opts, "extra_body", None)
    merged = dict(existing) if isinstance(existing, dict) else {}
    merged.update({"frequency_penalty":0.5, "presence_penalty":0.3})
    llm._opts.extra_body = merged
    assert llm._opts.extra_body == {"frequency_penalty":0.5,"presence_penalty":0.3}, llm._opts.extra_body
    print("EXTRA_BODY_ASSIGN_OK ->", llm._opts.extra_body)
except Exception:
    print("EXTRA_BODY_ASSIGN_FAIL:")
    traceback.print_exc()
    raise SystemExit(1)
PYEOF
