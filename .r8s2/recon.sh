#!/usr/bin/env bash
set -uo pipefail
echo "OK_CONNECTED host=$(hostname)"
echo "---MD5---"
md5sum /opt/famit-agent/agent.py /opt/famit-agent/prompt.py 2>/dev/null
echo "---LKVER---"
/opt/capsy-agent/.venv/bin/python - <<'PY'
import livekit.agents as a
print("livekit-agents", getattr(a, "__version__", "?"))
try:
    from livekit.agents.llm import ChatContext
    cc = ChatContext.empty()
    print("ChatContext attrs:", [x for x in dir(cc) if not x.startswith("_")])
    print("has_truncate", hasattr(cc, "truncate"))
    import inspect
    if hasattr(cc, "truncate"):
        print("truncate_sig", inspect.signature(cc.truncate))
except Exception as e:
    print("ChatContext import/probe err:", repr(e))
PY
echo "---USAGE_TODAY---"
cat /opt/famit-agent/var/usage_events.json 2>/dev/null | /opt/capsy-agent/.venv/bin/python - <<'PY'
import sys, json, collections
try:
    data = json.load(sys.stdin)
except Exception as e:
    print("usage parse err", repr(e)); raise SystemExit
rows = data if isinstance(data, list) else data.get("events", [])
gin=gout=0; ncalls=collections.Counter()
for r in rows:
    if r.get("vendor")=="groq":
        gin += int(r.get("in_tokens",0) or 0)
        gout += int(r.get("out_tokens",0) or 0)
        ncalls["groq_rows"]+=1
print("groq_rows", ncalls["groq_rows"], "total_in", gin, "total_out", gout, "ratio", round(gin/max(1,gout),1))
PY
echo "---SVC---"
systemctl show famit-agent -p ActiveState,SubState,NRestarts,MainPID --no-pager 2>/dev/null
echo "---ENV_GROQ_KEYCOUNT---"
sudo grep -cE '^GROQ_API_KEY' /opt/famit-agent/.env 2>/dev/null || grep -cE '^GROQ_API_KEY' /opt/famit-agent/.env 2>/dev/null
echo "---ENV_PERMS---"
sudo stat -c '%U:%G %a' /opt/famit-agent/.env 2>/dev/null
echo "---DONE---"
