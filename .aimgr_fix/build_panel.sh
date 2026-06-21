#!/bin/bash
set -u
cd /opt/famit-panel || exit 1
TS=$(date +%Y%m%d-%H%M%S)
cp next.config.ts next.config.ts.R6Bbak.$TS 2>/dev/null

# Inject experimental single-worker config (bound build memory on the 1.9GB box).
python3 - <<'PYEOF'
f = "next.config.ts"
s = open(f, encoding="utf-8").read()
if "cpus: 1" in s:
    print("cpus already set")
else:
    anchor = "const nextConfig: NextConfig = {"
    i = s.find(anchor)
    if i == -1:
        print("ANCHOR NOT FOUND")
    else:
        ins = ("\n    // R6b: bound build memory on the small panel box (1.9GB RAM) - single worker,"
               "\n    // no parallel threads - so the build worker is never OOM-killed. Runtime unchanged."
               "\n    experimental: { cpus: 1, workerThreads: false },")
        s2 = s[:i+len(anchor)] + ins + s[i+len(anchor):]
        open(f, "w", encoding="utf-8").write(s2)
        print("experimental cpus:1 injected")
PYEOF

echo "=== stop running panel to free RAM ==="
systemctl stop famit-panel
sleep 2
free -h | grep -i mem

echo "=== rebuild (single worker, bounded heap) ==="
LOG=/tmp/r6b_build2.log
EXITF=/tmp/r6b_build2.exit
test -f "$LOG" && cp /dev/null "$LOG"
test -f "$EXITF" && cp /dev/null "$EXITF"
nohup bash -lc 'cd /opt/famit-panel && sudo -u deployuser env NODE_OPTIONS="--max-old-space-size=1536" npm run build > /tmp/r6b_build2.log 2>&1; echo $? > /tmp/r6b_build2.exit' >/dev/null 2>&1 &
echo "rebuild launched PID=$!"
