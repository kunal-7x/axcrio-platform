#!/bin/bash
set -u
cd /opt/famit-panel || exit 1

# swap safety net (disk has ~9.9G free)
if [ ! -f /swapfile_build ]; then
  fallocate -l 4G /swapfile_build 2>/dev/null
  chmod 600 /swapfile_build
  mkswap /swapfile_build >/dev/null 2>&1
fi
swapon /swapfile_build 2>/dev/null

echo "=== free RAM for build (stop panel + heavy daemons) ==="
systemctl stop famit-panel 2>/dev/null
for svc in crowdsec crowdsec-firewall-bouncer fail2ban do-agent; do systemctl stop "$svc" 2>/dev/null; done
sync; echo 3 > /proc/sys/vm/drop_caches 2>/dev/null
sleep 2
free -h | grep -iE "mem|swap"

echo "=== STANDARD build (original config, NO experimental flags), 4GB RAM, isolated dir ==="
rm -rf /opt/famit-panel/.next-build
nohup bash -lc 'cd /opt/famit-panel && sudo -u deployuser env NEXT_DIST_DIR=.next-build NODE_OPTIONS="--max-old-space-size=3584" npm run build > /tmp/r6b_build8.log 2>&1; echo $? > /tmp/r6b_build8.exit' >/dev/null 2>&1 &
echo "build8 launched PID=$!"
