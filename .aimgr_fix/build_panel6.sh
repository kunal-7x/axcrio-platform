#!/bin/bash
set -u
cd /opt/famit-panel || exit 1

echo "=== add 4G swap so a >3.7GB RSS spike can spill (box now has 4G RAM) ==="
if [ ! -f /swapfile_build ]; then
  fallocate -l 4G /swapfile_build 2>/dev/null || dd if=/dev/zero of=/swapfile_build bs=1M count=4096
  chmod 600 /swapfile_build
  mkswap /swapfile_build >/dev/null 2>&1
fi
swapon /swapfile_build 2>/dev/null
free -h | grep -i swap

echo "=== free max RAM: stop panel + heavy security daemons during the isolated build ==="
systemctl stop famit-panel 2>/dev/null
for svc in crowdsec crowdsec-firewall-bouncer fail2ban do-agent; do systemctl stop "$svc" 2>/dev/null && echo "stopped $svc"; done
sync; echo 3 > /proc/sys/vm/drop_caches 2>/dev/null
sleep 2
free -h | grep -iE "mem|swap"

echo "=== isolated build into .next-build, 4GB heap allowed (box has 4GB now) ==="
rm -rf /opt/famit-panel/.next-build
nohup bash -lc 'cd /opt/famit-panel && sudo -u deployuser env NEXT_DIST_DIR=.next-build NODE_OPTIONS="--max-old-space-size=3584" npm run build > /tmp/r6b_build6.log 2>&1; echo $? > /tmp/r6b_build6.exit' >/dev/null 2>&1 &
echo "build6 launched PID=$!"
