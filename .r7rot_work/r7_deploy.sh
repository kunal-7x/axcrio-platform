#!/bin/bash
set -u
VENV=/opt/capsy-agent/.venv/bin/python
DROPIN=/etc/systemd/system/famit-agent.service.d/kernel-outbound.conf
TS=$(date +%Y%m%d-%H%M%S)
BK=/opt/famit-agent/agent.py.PREROT.$TS
DROPIN_BK=${DROPIN}.PREROT.$TS

echo "TS=$TS"

# Pre-flight: ROTNEW present + correct md5
ROT_MD5=$(md5sum /tmp/agent.py.ROTNEW | awk '{print $1}')
echo "ROTNEW md5=$ROT_MD5"
if [ "$ROT_MD5" != "bdf89031fa188c24351180bf3ec7afb9" ]; then
  echo "ABORT: ROTNEW md5 mismatch"
  exit 1
fi

# 1) Backup live agent.py + drop-in
sudo cp -p /opt/famit-agent/agent.py "$BK"
sudo cp -p "$DROPIN" "$DROPIN_BK"
echo "BACKUP agent=$BK"
echo "BACKUP dropin=$DROPIN_BK"

# 2) Deploy ROTNEW
sudo cp /tmp/agent.py.ROTNEW /opt/famit-agent/agent.py
sudo chown famit:famit /opt/famit-agent/agent.py
echo "live agent.py md5 now: $(md5sum /opt/famit-agent/agent.py | awk '{print $1}')"

# 3) py_compile under box venv
if sudo -u famit $VENV -m py_compile /opt/famit-agent/agent.py; then
  echo "PY_COMPILE=OK"
else
  echo "PY_COMPILE=FAIL -> rollback"
  sudo cp -p "$BK" /opt/famit-agent/agent.py
  sudo chown famit:famit /opt/famit-agent/agent.py
  echo "ROLLED BACK agent.py to golden ($(md5sum /opt/famit-agent/agent.py | awk '{print $1}'))"
  exit 2
fi

# 4) Set EARNER_POOL_LLM=1 in drop-in (idempotent; keep max=90, KERNEL_OUTBOUND=0, no penalty)
if grep -q '^Environment=EARNER_POOL_LLM=' "$DROPIN"; then
  sudo sed -i 's/^Environment=EARNER_POOL_LLM=.*/Environment=EARNER_POOL_LLM=1/' "$DROPIN"
else
  # insert after the KERNEL_OUTBOUND line (inside [Service])
  sudo sed -i '/^Environment=KERNEL_OUTBOUND=0/a Environment=EARNER_POOL_LLM=1' "$DROPIN"
fi
echo "=== drop-in after edit ==="
grep -E 'EARNER_POOL_LLM|GROQ_MAX_TOKENS|KERNEL_OUTBOUND|PENALTY' "$DROPIN"

# 5) daemon-reload + restart
sudo systemctl daemon-reload
sudo systemctl reset-failed famit-agent
sudo systemctl restart famit-agent
sleep 6
ACTIVE=$(systemctl is-active famit-agent)
echo "post-restart active=$ACTIVE"

# 6) auto-rollback if not active
if [ "$ACTIVE" != "active" ]; then
  echo "SERVICE NOT ACTIVE -> AUTO-ROLLBACK"
  sudo cp -p "$BK" /opt/famit-agent/agent.py
  sudo chown famit:famit /opt/famit-agent/agent.py
  sudo cp -p "$DROPIN_BK" "$DROPIN"
  sudo systemctl daemon-reload
  sudo systemctl reset-failed famit-agent
  sudo systemctl restart famit-agent
  sleep 5
  echo "ROLLBACK active=$(systemctl is-active famit-agent) agent.py md5=$(md5sum /opt/famit-agent/agent.py | awk '{print $1}')"
  echo "DEPLOY=ROLLED_BACK"
  exit 3
fi

echo "DEPLOY=OK BACKUP=$BK DROPIN_BK=$DROPIN_BK"
