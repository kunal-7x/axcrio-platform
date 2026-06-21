#!/bin/bash
set -u
cd /opt/famit-panel || exit 1

echo "=== add 3G swap (disk has ~4G free) so the build worker can spill ==="
if [ ! -f /swapfile3 ]; then
  fallocate -l 3G /swapfile3 2>/dev/null || dd if=/dev/zero of=/swapfile3 bs=1M count=3072
  chmod 600 /swapfile3
  mkswap /swapfile3 >/dev/null 2>&1
  swapon /swapfile3
  echo "swapfile3 added"
else
  swapon /swapfile3 2>/dev/null
  echo "swapfile3 already exists"
fi
free -h | grep -i swap

echo "=== ensure next.config builds into an ISOLATED distDir so the LIVE .next is never touched ==="
python3 - <<'PYEOF'
f = "next.config.ts"
s = open(f, encoding="utf-8").read()
changed = False
# isolated build dir (only when BUILD_ISOLATED env is set, via a literal we toggle)
if "distDir" not in s:
    anchor = "const nextConfig: NextConfig = {"
    i = s.find(anchor)
    ins = ('\n    // R6b: build into an isolated dir (env-selected) so an OOM-failed build NEVER'
           '\n    // corrupts the live .next. We rename the finished dir into place only on EXIT 0.'
           '\n    distDir: process.env.NEXT_DIST_DIR || ".next",')
    s = s[:i+len(anchor)] + ins + s[i+len(anchor):]
    changed = True
# also disable the webpack build worker to bound memory
if "webpackBuildWorker" not in s:
    s = s.replace("experimental: { cpus: 1, workerThreads: false },",
                  "experimental: { cpus: 1, workerThreads: false, webpackBuildWorker: false },")
    changed = True
open(f, "w", encoding="utf-8").write(s)
print("next.config updated" if changed else "next.config already set")
PYEOF

echo "=== keep panel RUNNING (build is isolated into .next-build; live .next untouched) ==="
free -h | grep -i mem
rm -rf /opt/famit-panel/.next-build
LOG=/tmp/r6b_build3.log
nohup bash -lc 'cd /opt/famit-panel && sudo -u deployuser env NEXT_DIST_DIR=.next-build NODE_OPTIONS="--max-old-space-size=2560" npm run build > /tmp/r6b_build3.log 2>&1; echo $? > /tmp/r6b_build3.exit' >/dev/null 2>&1 &
echo "build3 launched PID=$!  (building into .next-build; live .next untouched)"
