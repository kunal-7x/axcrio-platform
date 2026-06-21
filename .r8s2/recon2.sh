#!/usr/bin/env bash
set -uo pipefail
echo "---USAGE_HEAD---"
sudo head -c 300 /opt/famit-agent/var/usage_events.json 2>/dev/null; echo
echo "---USAGE_WC---"
sudo wc -c /opt/famit-agent/var/usage_events.json 2>/dev/null
echo "---USAGE_PARSE---"
sudo cat /opt/famit-agent/var/usage_events.json 2>/dev/null | /opt/capsy-agent/.venv/bin/python - <<'PY'
import sys, json
raw=sys.stdin.read().strip()
gin=gout=rows=0
def acc(r):
    global gin,gout,rows
    if isinstance(r,dict) and r.get("vendor")=="groq":
        gin+=int(r.get("in_tokens",0) or 0); gout+=int(r.get("out_tokens",0) or 0); rows+=1
try:
    d=json.loads(raw)
    arr=d if isinstance(d,list) else d.get("events",[])
    for r in arr: acc(r)
    print("JSON_ARRAY rows", len(arr))
except Exception:
    n=0
    for line in raw.splitlines():
        line=line.strip().rstrip(',')
        if not line: continue
        try: acc(json.loads(line)); n+=1
        except Exception: pass
    print("NDJSON_lines_parsed", n)
print("groq_rows", rows, "in", gin, "out", gout, "ratio", round(gin/max(1,gout),1))
PY
echo "---PROMPTSIZE---"
sudo grep -c . /opt/famit-agent/prompt.py 2>/dev/null
echo "---J429---"
sudo journalctl -u famit-agent --since "today" --no-pager 2>/dev/null | grep -iE "429|rate.?limit|quota|cooling|TPD|tokens per day" | tail -n 20
echo "---J429COUNT---"
sudo journalctl -u famit-agent --since "today" --no-pager 2>/dev/null | grep -ciE "429|rate.?limit|quota"
echo "---DONE---"
