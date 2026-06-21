#!/bin/bash
cd /opt/famit-agent || exit 9
VENV=/opt/capsy-agent/.venv/bin/python
echo "=== A) py_compile both ==="
$VENV -m py_compile agent.py prompt.py && echo "PY_COMPILE_OK" || echo "PY_COMPILE_FAIL"
echo "=== B) grep the new wiring ==="
grep -nE "_hot_llm = groq\.LLM|_hot_llm\._opts\.extra_body|llm=_hot_llm|GROQ_FREQ_PENALTY|GROQ_PRES_PENALTY|frequency_penalty|presence_penalty" agent.py
echo "=== C) confirm NO leftover inline llm=groq.LLM( ==="
grep -nE "llm=groq\.LLM\(" agent.py && echo "BAD: inline still present" || echo "GOOD: no inline llm=groq.LLM( remains"
echo "=== D) md5 (prompt MUST be 759b6f5c; agent changed from e353b775) ==="
md5sum agent.py prompt.py
echo "=== E) TTS constructor span byte-identical vs FINALFIXbak (THE LAW) ==="
# extract the elevenlabs TTS constructor region and diff vs golden backup
grep -nE "elevenlabs\.TTS\(|VoiceSettings\(|voice_id|EL_STABILITY|QTKSa2Iyv0yoxvXY2V8a|model=.*flash|stability" agent.py | head -40
