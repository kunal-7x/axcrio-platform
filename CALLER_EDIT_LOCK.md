# 🔒 CALLER_EDIT_LOCK — serialize caller.py edits across waves

> Only ONE wave edits `caller.py` at a time. Acquire (set HELD-BY below) before editing;
> WAIT if another wave holds it; release (set FREE) after the earner gate passes.
> Edit FROM THE BOX GOLDEN (`droplet_work/caller.py.LIVEBOX.py`, md5 must == box
> `/opt/famit-agent/caller.py`) via ANCHOR-STRING insertions (never line numbers — 3
> caller.py variants exist on disk). Additive only (0 deletions).

## CURRENT LOCK STATE

- **STATUS:** FREE
- **HELD-BY:** —
- **LAST GOLDEN md5 (box live + local caller.py.LIVEBOX.py):** `32e6062f5fcfd8448437a2cbcad4b7e9`
  (was `ccf9715bbc2da14ed989dac3af95c5fe` before the leads-mgmt routes). Re-pull + re-verify before the next edit.

## HISTORY
- 2026-06-15 — leads-mgmt-feature acquired then RELEASED. Additive leads CRUD/sort: GET /leads
  full sort selector (default=recent/newest; oldest/name/status/score); +POST /leads/delete
  (delete-by-ids, BOLA tenant_id-scoped, idempotent — unknown/cross-tenant ids skipped);
  +DELETE /leads?confirm=DELETE (delete-all, STRICT tenant_id scope NEVER cross-tenant even for
  admin token, confirm-gated). Mounted at the END of the leads route block (anchor: after
  @app.delete("/leads/{lead_id}")). Additive only, py_compile OK. Box golden ccf9715b -> live
  32e6062f. Deployed (md5-gate, famit-caller restarted ONLY; backup
  /opt/famit-agent/caller.py.leadsmgmtbak.20260615-174918). VERIFIED over loopback (SAFE, total
  unchanged at 30): no-auth=401, sort recent≠oldest, DELETE w/o confirm=400, bulk empty/bogus
  ids→deleted=0. EARNER GATE: agent.py 9150fabe UNCHANGED · famit-agent PID 2808658 NOT restarted
  · caller /health 200 · 0 5xx · NO ring.
- 2026-06-15 — comm-w1-p3 acquired then RELEASED. Inserted the post-call COMMUNICATION block at
  the END of `_finalize_call` (anchor: after the hot-lead `notify_handoff_team` except). PURE-SYNC
  `comm.post_call.snapshot(rec,tr,camp_fields,...)` then `asyncio.create_task(comm.post_call.run(snap))`
  — DETACHED, NEVER awaited on the dial loop; flag-gated `COMM_ENABLED`. Additive: +28 lines, 0
  deletions (single hunk `2795a2796,2822`). Box golden `73d7be4f` -> live `ccf9715b`. Deployed
  (md5-gate, famit-caller restarted ONLY). Flags `FEATURE_TELEGRAM_FOUNDER_ALERT=1` +
  `FEATURE_TELEGRAM_FOLLOWUP=1` ON (founder tenant). EARNER GATE under an induced api.telegram.org
  black-hole: snapshot 0.047ms + create_task 0.015ms (only hot-path cost) · detached run bounded
  0.10s under outage · agent.py `9150fabe` UNCHANGED · famit-agent PID 2808658 NOT restarted · caller
  /health 200 · 0 5xx · token redacted · 0 residual pins.
- 2026-06-15 — comm-w1-p2 acquired then RELEASED. Mounted `comm.router.build_router(...)` (prefix
  /comm) after the whatsapp-builder include_router. Additive: +43 lines, 0 deletions. Anchor-string
  insertion from the box golden `44b867ea`. Deployed (md5-gate), flag `COMM_ENABLED=1` +
  `COMM_TELEGRAM_ENABLED=1`. Box live caller.py = `73d7be4f`. EARNER GATE before+after (under an
  induced api.telegram.org black-hole): agent.py `9150fabe` UNCHANGED · famit-agent PID 2808658 NOT
  restarted · caller /health 200 · 0 5xx · NO ring · webhook fail-closed in 9ms · outbound bounded.
