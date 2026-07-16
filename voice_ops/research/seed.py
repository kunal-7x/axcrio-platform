"""voice_ops.research.seed — populate the Famit Research ClickHouse tables with demo calls.

For a LIVE demo (real rows in famit_research_turns / famit_research_calls instead of the on-the-fly
demo fallback) and to verify the write path. Runs the SAME real affect filter over scripted archetype
calls and INSERTs them. No-op safe: prints a plan when no ClickHouse write URL is configured.

    # apply the DDL once, then:
    FAMIT_RESEARCH_ENABLED=1 CLICKHOUSE_URL=http://obs:8123 \
        python3 -m voice_ops.research.seed --tenant <tenant_id>
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone

from .demo import archetype_label, _DEMO_CALLS, synthetic_call


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Seed Famit Research demo calls into ClickHouse.")
    ap.add_argument("--tenant", default="demo", help="tenant_id to stamp on the demo rows")
    ap.add_argument("--dry-run", action="store_true", help="build + print, never write")
    args = ap.parse_args(argv)

    # import the recorder from the backend package (droplet_work must be importable)
    try:
        sys.path.insert(0, "droplet_work")
        import research_analytics as ra  # type: ignore
    except Exception as exc:  # noqa: BLE001
        print(f"! could not import research_analytics ({exc}); make sure you run from the repo root")
        return 2

    write_url = ra._ch_write_url()  # noqa: SLF001 — intentional: show the operator what was resolved
    print(f"tenant={args.tenant}  clickhouse_write_url={write_url or '(none)'}  active={ra.active()}")
    total_turns = 0
    base = datetime.now(timezone.utc) - timedelta(hours=6)   # spread the demo calls over the last 6h
    for i, (call_id, arch) in enumerate(_DEMO_CALLS):
        started = (base + timedelta(minutes=37 * i)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        rows, summ = synthetic_call(args.tenant, call_id, arch, started_iso=started)
        total_turns += len(rows)
        print(f"  {call_id:18s} {archetype_label(arch):28s} turns={len(rows):2d} "
              f"peak_friction={summ.friction_peak:5.1f} outcome={summ.outcome} converted={summ.converted}")
        if not args.dry_run:
            ok = ra.persist_call(rows, summ, force=True)
            print(f"      → persisted: {ok}")
    print(f"\n{len(_DEMO_CALLS)} calls, {total_turns} turns "
          f"{'(dry-run, nothing written)' if args.dry_run else 'processed'}.")
    if not write_url and not args.dry_run:
        print("NOTE: no ClickHouse write URL configured → nothing was actually written. "
              "Set CLICKHOUSE_URL (and apply deploy/observability/voice_analytics.sql) first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
