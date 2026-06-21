#!/bin/bash
echo "=== service active ==="
systemctl is-active famit-agent
echo "=== show ==="
systemctl show famit-agent -p MainPID -p NRestarts -p ActiveState -p SubState
echo "=== live agent.py md5 ==="
md5sum /opt/famit-agent/agent.py
echo "=== staged ROTNEW md5 ==="
md5sum /tmp/agent.py.ROTNEW 2>/dev/null || echo "ROTNEW MISSING"
echo "=== drop-in env ==="
grep -E 'EARNER_POOL_LLM|GROQ_MAX_TOKENS|KERNEL_OUTBOUND|PENALTY' /etc/systemd/system/famit-agent.service.d/kernel-outbound.conf
echo "=== prompt.py md5 (do not touch) ==="
md5sum /opt/famit-agent/prompt.py
