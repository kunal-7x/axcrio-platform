#!/usr/bin/env bash
set -u
PY=/opt/capsy-agent/.venv/bin/python
echo "=== py_compile ==="
if "$PY" -m py_compile /tmp/agent_candidate.py; then echo COMPILE_OK; else echo COMPILE_FAIL; fi
echo "=== import-smoke (in /opt/famit-agent so sibling modules resolve) ==="
cp /tmp/agent_candidate.py /opt/famit-agent/_agent_candidate_import.py
cd /opt/famit-agent
if "$PY" -c "import importlib.util,sys; sys.argv=['x']; spec=importlib.util.spec_from_file_location('agent_cand','/opt/famit-agent/_agent_candidate_import.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('IMPORT_OK keys=%d' % len(m._GROQ_KEYS)); print('HELPER_OK' if hasattr(m,'_groq_keys_for_call') else 'HELPER_MISSING')"; then echo IMPORT_DONE; else echo IMPORT_FAIL; fi
rm -f /opt/famit-agent/_agent_candidate_import.py
