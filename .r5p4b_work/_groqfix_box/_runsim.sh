#!/usr/bin/env bash
set -u
PY=/opt/capsy-agent/.venv/bin/python
cp /tmp/agent_candidate.py /opt/famit-agent/_agent_sim_import.py
cd /opt/famit-agent
"$PY" /tmp/_sim.py 2>&1
rc=$?
rm -f /opt/famit-agent/_agent_sim_import.py
exit $rc
