#!/bin/bash
# Atomically swap the freshly-built .next-build into place + restart panel + restart the
# security daemons we stopped for the build. Only run AFTER build4 exit == 0.
set -u
cd /opt/famit-panel || exit 1

EXIT=$(cat /tmp/r6b_build4.exit 2>/dev/null || echo 99)
if [ "$EXIT" != "0" ]; then
  echo "BUILD NOT GREEN (exit=$EXIT) — NOT swapping. Restarting services on the OLD good .next."
  systemctl start famit-panel
  for svc in crowdsec crowdsec-firewall-bouncer fail2ban do-agent; do systemctl start "$svc" 2>/dev/null; done
  exit 1
fi

if [ ! -f .next-build/BUILD_ID ]; then
  echo "ERROR: .next-build/BUILD_ID missing — build incomplete. NOT swapping."
  systemctl start famit-panel
  for svc in crowdsec crowdsec-firewall-bouncer fail2ban do-agent; do systemctl start "$svc" 2>/dev/null; done
  exit 1
fi

TS=$(date +%Y%m%d-%H%M%S)
NEWID=$(cat .next-build/BUILD_ID)
echo "new BUILD_ID=$NEWID — swapping into .next"
# keep the current good .next as a backup, then atomically move the new one in
[ -d .next ] && mv .next .next.R6Bprev.$TS
mv .next-build .next
chown -R deployuser:deployuser .next
systemctl start famit-panel
sleep 4
for svc in crowdsec crowdsec-firewall-bouncer fail2ban do-agent; do systemctl start "$svc" 2>/dev/null; done
echo "=== panel status ==="
systemctl is-active famit-panel
echo "live BUILD_ID: $(cat .next/BUILD_ID)"
curl -s -o /dev/null -w "local panel HTTP %{http_code}\n" http://127.0.0.1:3001/
echo "BACKUP of prior good build: .next.R6Bprev.$TS"
