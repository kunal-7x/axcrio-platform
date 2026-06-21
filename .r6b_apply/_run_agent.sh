#!/bin/bash
cd /opt/famit-agent || exit 1
VENV=/opt/capsy-agent/.venv/bin/python
rm -rf /tmp/r6bagent && mkdir -p /tmp/r6bagent
cp _agent_r6b_test.py /tmp/r6bagent/agent.py
cp _probe_agent_r6b.py /tmp/r6bagent/_probe_agent.py
cd /tmp/r6bagent
echo "=== py_compile (capsy venv) ==="
$VENV -c "import py_compile; py_compile.compile('agent.py', doraise=True); print('AGENT_COMPILE_OK')"
echo "=== behavior probe ==="
PYTHONPATH=/opt/famit-agent:/tmp/r6bagent $VENV _probe_agent.py
