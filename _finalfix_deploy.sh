#!/bin/bash
set -e
DROP=/etc/systemd/system/famit-agent.service.d/kernel-outbound.conf
TS=20260620-finalfix
echo "=== current drop-in (before) ==="
cat "$DROP"
echo "=== backup drop-in -> .FINALFIXbak.$TS ==="
sudo cp -p "$DROP" "$DROP.FINALFIXbak.$TS"
ls -la "$DROP.FINALFIXbak.$TS"

echo "=== write new drop-in (GROQ_MAX_TOKENS=220 + penalties) ==="
sudo tee "$DROP" >/dev/null <<'CONF'
[Service]
Environment=KERNEL_OUTBOUND=0
Environment=GROQ_MAX_TOKENS=220
Environment=GROQ_FREQ_PENALTY=0.5
Environment=GROQ_PRES_PENALTY=0.3
Environment=BOOKING_HTTP_ENABLED=1
Environment=W5_SPEECH=0
Environment=OPENER_IN_CTX=1
Environment=OPENER_ALREADY_SAID=1
Environment=OPENER_DELAY_S=0.8
CONF
echo "=== new drop-in (after) ==="
cat "$DROP"

echo "=== daemon-reload + py_compile guard + restart ==="
sudo systemctl daemon-reload
/opt/capsy-agent/.venv/bin/python -m py_compile /opt/famit-agent/agent.py /opt/famit-agent/prompt.py && echo "PRE_RESTART_PYCOMPILE_OK"
sudo systemctl restart famit-agent
echo "RESTARTED"
