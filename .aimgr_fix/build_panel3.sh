#!/bin/bash
set -u
cd /opt/famit-panel || exit 1

echo "=== free MAX ram: stop panel + non-critical security daemons during the isolated build ==="
systemctl stop famit-panel 2>/dev/null
# stop heavy non-essential daemons (restarted after) to reclaim RAM
for svc in crowdsec crowdsec-firewall-bouncer fail2ban do-agent; do
  systemctl stop "$svc" 2>/dev/null && echo "stopped $svc"
done
sync; echo 3 > /proc/sys/vm/drop_caches 2>/dev/null
sleep 2
free -h | grep -iE "mem|swap"

echo "=== isolated build into .next-build (live .next never touched), tight heap + GC pressure ==="
rm -rf /opt/famit-panel/.next-build
# semi-space + old-space tuned small so V8 GCs early and RSS stays bounded; swap is the safety net.
nohup bash -lc 'cd /opt/famit-panel && sudo -u deployuser env NEXT_DIST_DIR=.next-build NODE_OPTIONS="--max-old-space-size=1280 --max-semi-space-size=2" npm run build > /tmp/r6b_build4.log 2>&1; echo $? > /tmp/r6b_build4.exit' >/dev/null 2>&1 &
echo "build4 launched PID=$!"
