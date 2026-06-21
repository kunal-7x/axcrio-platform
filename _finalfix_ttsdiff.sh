#!/bin/bash
cd /opt/famit-agent || exit 9
# Extract ONLY the elevenlabs.TTS(...) constructor: from the line with 'elevenlabs.TTS('
# up to and including the first line that is exactly '    )' at that indent (the close).
extract_tts() {
  awk '
    /tts = elevenlabs\.TTS\(/ {f=1}
    f {print}
    f && /^    \)$/ {exit}
  ' "$1"
}
extract_tts agent.py > /tmp/_tts_live.txt
extract_tts agent.py.FINALFIXbak.20260620-finalfix > /tmp/_tts_golden.txt
echo "=== live TTS constructor ==="
cat /tmp/_tts_live.txt
echo "=== diff live vs golden FINALFIXbak (empty = identical) ==="
if diff /tmp/_tts_live.txt /tmp/_tts_golden.txt; then echo "TTS_CONSTRUCTOR_BYTE_IDENTICAL_OK"; else echo "TTS_CONSTRUCTOR_DIFFERS"; fi
echo "=== also diff vs R6bbak (the brain we restored) ==="
extract_tts agent.py.R6bbak.20260620-r6b > /tmp/_tts_r6.txt
if diff /tmp/_tts_live.txt /tmp/_tts_r6.txt; then echo "TTS_VS_R6_IDENTICAL_OK"; else echo "TTS_VS_R6_DIFFERS"; fi
