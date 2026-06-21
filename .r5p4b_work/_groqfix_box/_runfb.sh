#!/usr/bin/env bash
set -u
PY=/opt/capsy-agent/.venv/bin/python
set -a
eval "$(grep -E '^GROQ_API_KEY=' /opt/famit-agent/.env | head -1)"
eval "$(grep -E '^GROQ_LLM_MODEL=' /opt/famit-agent/.env | head -1)"
set +a
"$PY" /tmp/_fbtest.py 2>&1
