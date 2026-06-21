#!/usr/bin/env bash
set -uo pipefail
echo "---GROQ_TOTALS---"
sudo /opt/capsy-agent/.venv/bin/python - <<'PY'
import json
p="/opt/famit-agent/var/usage_events.json"
gin=gout=rows=0; today_in=today_out=today_rows=0
try:
    arr=json.load(open(p,encoding="utf-8"))
except Exception as e:
    print("load_err", repr(e)); arr=[]
for r in arr:
    if isinstance(r,dict) and r.get("vendor")=="groq":
        i=int(r.get("in_tokens",0) or 0); o=int(r.get("out_tokens",0) or 0)
        gin+=i; gout+=o; rows+=1
        if str(r.get("ts","")).startswith("2026-06-20") or str(r.get("ts","")).startswith("2026-06-21"):
            today_in+=i; today_out+=o; today_rows+=1
print("ALLTIME groq_rows", rows, "in", gin, "out", gout, "ratio", round(gin/max(1,gout),1))
print("RECENT(20/21) rows", today_rows, "in", today_in, "out", today_out, "ratio", round(today_in/max(1,today_out),1))
# per-call avg input over recent
if today_rows:
    print("RECENT avg_in_per_groqrow", round(today_in/today_rows))
PY
echo "---KEY_PREFIXES (masked, order)---"
sudo /opt/capsy-agent/.venv/bin/python - <<'PY'
import re
keys=[]
for line in open("/opt/famit-agent/.env",encoding="utf-8"):
    m=re.match(r'^(GROQ_API_KEY(?:_\d+)?)\s*=\s*(.+)$', line.strip())
    if m:
        name=m.group(1); v=m.group(2).strip().strip('"').strip("'")
        keys.append((name, (v[:8]+"..."+v[-4:]) if len(v)>14 else "SHORT", len(v)))
for n,mask,ln in keys:
    print(f"{n}\t{mask}\tlen={ln}")
print("TOTAL_KEYS", len(keys))
PY
echo "---DONE---"
