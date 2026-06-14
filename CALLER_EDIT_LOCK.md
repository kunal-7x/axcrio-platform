# 🔒 CALLER_EDIT_LOCK — serialize caller.py edits across waves

> Only ONE wave edits `caller.py` at a time. Acquire (set HELD-BY below) before editing;
> WAIT if another wave holds it; release (set FREE) after the earner gate passes.
> Edit FROM THE BOX GOLDEN (`droplet_work/caller.py.LIVEBOX.py`, md5 must == box
> `/opt/famit-agent/caller.py`) via ANCHOR-STRING insertions (never line numbers — 3
> caller.py variants exist on disk). Additive only (0 deletions).

## CURRENT LOCK STATE

- **STATUS:** FREE
- **HELD-BY:** (none)
- **LAST GOLDEN md5 (box live + local caller.py.LIVEBOX.py):** `73d7be4f05bd5e9decdd27cafb6a3f48`
  (was `44b867eaa3a448792a82c9760db0d76b` before the comm mount). Re-pull + re-verify before the next edit.

## HISTORY
- 2026-06-15 — comm-w1-p2 acquired then RELEASED. Mounted `comm.router.build_router(...)` (prefix
  /comm) after the whatsapp-builder include_router. Additive: +43 lines, 0 deletions. Anchor-string
  insertion from the box golden `44b867ea`. Deployed (md5-gate), flag `COMM_ENABLED=1` +
  `COMM_TELEGRAM_ENABLED=1`. Box live caller.py = `73d7be4f`. EARNER GATE before+after (under an
  induced api.telegram.org black-hole): agent.py `9150fabe` UNCHANGED · famit-agent PID 2808658 NOT
  restarted · caller /health 200 · 0 5xx · NO ring · webhook fail-closed in 9ms · outbound bounded.
