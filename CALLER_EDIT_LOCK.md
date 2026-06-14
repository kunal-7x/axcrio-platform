# 🔒 CALLER_EDIT_LOCK — serialize caller.py edits across waves

> Only ONE wave edits `caller.py` at a time. Acquire (set HELD-BY below) before editing;
> WAIT if another wave holds it; release (set FREE) after the earner gate passes.
> Edit FROM THE BOX GOLDEN (`droplet_work/caller.py.LIVEBOX.py`, md5 must == box
> `/opt/famit-agent/caller.py`) via ANCHOR-STRING insertions (never line numbers — 3
> caller.py variants exist on disk). Additive only (0 deletions).

## CURRENT LOCK STATE

- **STATUS:** HELD
- **HELD-BY:** comm-w1-p2 (Communication Wave 1 — webhook + endpoints + mount)
- **ACQUIRED:** 2026-06-15
- **BOX GOLDEN md5 (verified at acquire):** `44b867eaa3a448792a82c9760db0d76b` (== box `/opt/famit-agent/caller.py`, == local `caller.py.LIVEBOX.py`)
- **SCOPE:** mount `comm.router.build_router(...)` at the END of the include-router block
  (anchor after the whatsapp-builder mount), flag-gated `COMM_ENABLED`. Additive, 0 deletions.
- **EARNER GATE (before+after, under induced Telegram outage):** agent.py md5
  `9150fabe4ff62b4b4470f9a87df346e5` UNCHANGED · famit-agent PID NOT restarted · caller
  /health 200 · 0 5xx · NO ring. Restart ONLY famit-caller.

## HISTORY
- 2026-06-15 — comm-w1-p2 acquired (webhook + comm endpoints + caller mount).
