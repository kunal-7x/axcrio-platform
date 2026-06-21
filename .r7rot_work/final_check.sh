#!/bin/bash
ROT=/tmp/agent.py.ROTNEW
GOLD=/opt/famit-agent/agent.py
echo "===== md5 (ROTNEW staged on box) ====="
md5sum "$ROT" "$GOLD"
echo
echo "===== forbidden-token grep on box ROTNEW (must be empty) ====="
if grep -nE 'frequency_penalty|presence_penalty|extra_body|FREQ_PENALTY|PRES_PENALTY' "$ROT"; then
  echo "RESULT: FOUND forbidden penalty/extra_body tokens"
else
  echo "RESULT: CLEAN — no penalty / extra_body"
fi
echo "--- literal 220 occurrences ---"
grep -n '220' "$ROT" || echo "RESULT: no '220' anywhere"
echo
echo "===== max_completion_tokens (should be the single env-90 line) ====="
grep -n 'max_completion_tokens' "$ROT"
echo
echo "===== TTS constructor span md5 (golden vs ROTNEW) — VOICE LAW ====="
# extract from 'tts = elevenlabs.TTS(' through the ctl[\"tts_code\"] line inclusive
extract_tts() {
  awk '/tts = elevenlabs\.TTS\(/{f=1} f{print} /ctl\["tts_code"\]/{if(f)exit}' "$1"
}
echo -n "golden : "; extract_tts "$GOLD" | md5sum
echo -n "ROTNEW : "; extract_tts "$ROT"  | md5sum
echo
echo "===== EARNER_POOL_LLM code default still safe '0' ====="
grep -n 'EARNER_POOL_LLM = ' "$ROT"
echo "===== DONE ====="
