#!/usr/bin/env python3
"""Set (or clear) the live primary LLM provider in /data/voice_keys.json. No rebuild; the NEXT call
picks it up (llm_provider is read per-call). Clearing falls back to the env/per-campaign default.
  set_provider.py groq     # Groq primary (model from GROQ_LLM_MODEL env)
  set_provider.py sarvam   # Sarvam primary
  set_provider.py ""       # clear
"""
import json
import sys

prov = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
p = "/data/voice_keys.json"
d = json.load(open(p, encoding="utf-8"))
if prov:
    d["llm_provider"] = prov
else:
    d.pop("llm_provider", None)
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("llm_provider ->", d.get("llm_provider", "(cleared)"))
