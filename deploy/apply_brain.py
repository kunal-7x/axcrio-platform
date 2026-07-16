#!/usr/bin/env python3
"""Apply (or restore) a campaign's brain_override. DATA change — no worker rebuild needed.
Self-contained (no dependency on any ephemeral /tmp helper that a rebuild would wipe).

  apply_brain.py <campaign_id> <brain_file>   # back up the CURRENT brain -> brain_override_bak, then set the new one
  apply_brain.py <campaign_id> --restore      # restore brain_override from brain_override_bak

The backup ALWAYS captures the brain that is live right now, so --restore reverts exactly one step
(e.g. v2 -> v1-clean), never to some older brain. Writes pretty UTF-8 JSON in place."""
import json
import sys

cid, arg = sys.argv[1], sys.argv[2]
path = f"/data/campaigns/{cid}.json"
d = json.load(open(path, encoding="utf-8"))
f = d["fields"]

if arg == "--restore":
    bak = f.get("brain_override_bak")
    if not bak:
        print("no brain_override_bak to restore from")
        sys.exit(1)
    f["brain_override"] = bak
    print(f"brain RESTORED from backup (len={len(bak)})")
else:
    new = open(arg, encoding="utf-8").read()
    prev = f.get("brain_override", "")
    f["brain_override_bak"] = prev            # always back up the CURRENTLY-LIVE brain
    f["brain_override"] = new
    print(f"brain APPLIED (len={len(new)}); previous brain backed up (len={len(prev)})")

json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
