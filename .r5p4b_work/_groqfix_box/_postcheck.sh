#!/usr/bin/env bash
set -u
echo "=== active + restarts ==="
systemctl is-active famit-agent
echo "NRestarts=$(systemctl show famit-agent -p NRestarts --value)"
echo "MainPID=$(systemctl show famit-agent -p MainPID --value)"
echo "=== registered worker? (look for 'registered worker') ==="
journalctl -u famit-agent --since '90 seconds ago' --no-pager | grep -iE 'registered worker|error|traceback|exception|fail' | tail -20 || echo "(no error/registered lines)"
echo "=== current live md5s ==="
md5sum /opt/famit-agent/agent.py /opt/famit-agent/prompt.py
echo "=== backups present ==="
ls -1 /opt/famit-agent/agent.py.GROQFIXbak.* /opt/famit-agent/.env.GROQFIXbak.* 2>/dev/null | tail -4
