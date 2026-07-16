#!/usr/bin/env python3
"""Launcher for the Haptica Flywheel side-pipeline WORKER (voice_ops.flywheel.worker).

Runs in its OWN process (systemd unit on the obs/app droplet) — NEVER inside the voice agent
process (the live turn loop must never share a process with the GIL-heavy offline scoring). It
reads ClickHouse + the campaign store, refreshes the per-move PRM / bandit posteriors, mines the
preference moat, enriches a sample with the RLAIF judge, computes the Goodhart monitors, and writes
the dispatch policy snapshot — every FLYWHEEL_WORKER_INTERVAL_S.

DORMANT-SAFE: with FLYWHEEL_ENABLED off (or no ClickHouse url) the loop wakes, no-ops, and sleeps.
Mirrors run_worker.py's env bootstrap so it sees the same FAMIT_VAR + .env as the rest of the stack.

  systemd (example):  ExecStart=/usr/bin/python3 /opt/haptica/flywheel_worker.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DW = os.path.join(ROOT, "droplet_work")

os.environ.setdefault("FAMIT_VAR", os.path.join(ROOT, "famit-var"))
sys.path.insert(0, ROOT)
sys.path.insert(0, DW)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(DW, ".env"))
except Exception:  # noqa: BLE001 — dotenv optional in prod (env injected by systemd)
    pass


def main() -> None:
    import asyncio
    import logging
    logging.basicConfig(
        level=getattr(logging, os.getenv("FLYWHEEL_LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from voice_ops.flywheel import worker, config
    log = logging.getLogger("flywheel.launcher")
    log.info("flywheel worker boot; active=%s status=%s", config.active(), config.status())
    try:
        asyncio.run(worker.run_forever())
    except KeyboardInterrupt:
        log.info("flywheel worker stopped")


if __name__ == "__main__":
    main()
