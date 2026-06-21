#!/bin/bash
set -u
cd /opt/famit-panel || exit 1
EXIT=$(cat /tmp/r6b_build8.exit 2>/dev/null || echo 99)
if [ "$EXIT" != "0" ] || [ ! -f .next-build/BUILD_ID ]; then
  echo "GUARD: build not green ($EXIT) or no BUILD_ID - NOT swapping"
  systemctl start famit-panel
  for svc in crowdsec crowdsec-firewall-bouncer fail2ban do-agent; do systemctl start "$svc" 2>/dev/null; done
  exit 1
fi
TS=$(date +%Y%m%d-%H%M%S)
NEWID=$(cat .next-build/BUILD_ID)
echo "swapping NEW BUILD_ID=$NEWID into .next"
mv .next .next.R6Bprev.$TS
mv .next-build .next
chown -R deployuser:deployuser .next
echo "=== restart panel + daemons ==="
systemctl start famit-panel
sleep 4
for svc in crowdsec crowdsec-firewall-bouncer fail2ban do-agent; do systemctl start "$svc" 2>/dev/null; done
systemctl is-active famit-panel
echo "LIVE BUILD_ID: $(cat .next/BUILD_ID)"
curl -s -o /dev/null -w "local HTTP %{http_code}\n" http://127.0.0.1:3001/
echo "prior good build kept at: .next.R6Bprev.$TS"
# free the build swapfile
swapoff /swapfile_build 2>/dev/null
test -f /swapfile_build && shred -u /swapfile_build 2>/dev/null || rm -f -- /swapfile_build 2>/dev/null
df -h /opt | tail -1
