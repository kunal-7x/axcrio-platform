#!/usr/bin/env bash
set -eu
PY=/opt/capsy-agent/.venv/bin/python
SRC=/tmp/agent_candidate.py
OUT=/tmp/_groqlogic.py
# Extract ONLY the key-selection logic (collect/keys/helper) into a standalone module
# so the sim does not drag in livekit/memory/etc. We pull the three functions + globals
# by line range markers that are stable in the file.
"$PY" - "$SRC" "$OUT" <<'PYEOF'
import sys, re
src = open(sys.argv[1], encoding="utf-8").read()
# grab from "import itertools as _itertools" through end of _groq_keys_for_call
start = src.index("import itertools as _itertools")
end_marker = "def _collect_sarvam_keys"
end = src.index(end_marker)
chunk = src[start:end]
# the chunk references os/json/logger? only os + itertools + threading + hashlib(local).
header = "import os\n"
open(sys.argv[2], "w", encoding="utf-8").write(header + chunk)
print("EXTRACTED_BYTES", len(chunk))
PYEOF
cp /tmp/_groqlogic.py /opt/famit-agent/_groqlogic.py 2>/dev/null || cp /tmp/_groqlogic.py ./_groqlogic.py
# patch the sim to import the standalone logic module
sed 's#CAND = "/opt/famit-agent/_agent_sim_import.py"#CAND = "/tmp/_groqlogic.py"#' /tmp/_sim.py > /tmp/_sim2.py
# export the real GROQ keys from the live .env so _collect_groq_keys() sees the true pool
set -a
eval "$(grep -E '^GROQ_API_KEY' /opt/famit-agent/.env)"
set +a
"$PY" /tmp/_sim2.py
