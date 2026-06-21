set -e
cd /opt/famit-agent
TS=20260620-finalfix
echo "=== STEP 1: backup current live (golden) as FINALFIXbak ==="
cp -p agent.py  agent.py.FINALFIXbak.$TS
cp -p prompt.py prompt.py.FINALFIXbak.$TS
cp -p /etc/systemd/system/famit-agent.service.d/kernel-outbound.conf /etc/systemd/system/famit-agent.service.d/kernel-outbound.conf.FINALFIXbak.$TS 2>/dev/null || sudo cp -p /etc/systemd/system/famit-agent.service.d/kernel-outbound.conf /etc/systemd/system/famit-agent.service.d/kernel-outbound.conf.FINALFIXbak.$TS
echo "backed-up current agent.py md5:"; md5sum agent.py.FINALFIXbak.$TS prompt.py.FINALFIXbak.$TS

echo "=== STEP 2: verify R6 backup md5 BEFORE restoring ==="
md5sum agent.py.R6bbak.20260620-r6b prompt.py.R6bbak.20260620-r6b

echo "=== STEP 3: restore R6 brain to live files ==="
cp -p agent.py.R6bbak.20260620-r6b  agent.py
cp -p prompt.py.R6bbak.20260620-r6b prompt.py
echo "live md5 after restore (expect agent e353b775 / prompt 759b6f5c):"
md5sum agent.py prompt.py
