"""voice_ops.callback.config — CallbackConfig: the cadence + anti-spam knobs.

Default OFF / safe everywhere. The whole engine is inert until a founder-signed
seam wave flips `CALLBACK_CADENCE_ENABLED` AND wires a real durable store; until
then `caller.py` keeps its (currently KILLED, RETRY_SCHEDULER_ENABLED=0) path.

THE FOUNDER BUG this package fixes (from the runaway-spam hotfix 6aa1f32):
  * caller.py:2756 enqueued callback_at on ANY outcome incl ANSWERED -> redial
    after a successful pickup;
  * caller.py:2755+1637 read `attempts` from `it["attempt"]` (always 0) and the
    upsert RESET the existing entry every tick -> the `attempts < max` guard
    never tripped -> infinite redial every backoff[0]=120min (10-11x/night);
  * recon sweep 7294 hardcoded attempts=1 every 60s for lingering calls.

The fix is one cohesive state machine:
  1. WARM-LEAD cadence Day 0 / 1 / 3 / 7 / 14 / 30 (NOT every 2h), hard-capped by
     MAX_RETRIES (default 2 retries => 3 cadence touches max);
  2. NO redial after a connected/answered call;
  3. busy -> ONE short reschedule (BUSY_RETRY_MINS), not a 120-min loop;
  4. "call me at 5pm / tomorrow / Sunday" -> EXACT-time callback, highest
     priority (honored even after a pickup — it is the customer's own intent);
  5. dedup + lead-lock across the whole redial cycle (a lead is never
     double-dialed, never dialed by two worker numbers at once);
  6. continue-from-prior-context (carry the last summary into the callback);
  7. tenant-tunable + per-tenant disable, from the panel.

Flag pattern is the codebase-native one (agent.py:451 OPENER_ALREADY_SAID style):
    os.getenv("NAME", "0") in ("1","true","True","yes","on")
No new config framework. ENV lives under the box .env / systemd drop-in.

ENV:
  CALLBACK_CADENCE_ENABLED   "1" to arm the cadence engine        (default OFF)
  CALLBACK_CADENCE_MINS      comma offsets in MINUTES from arrival
                             (default "0,1440,4320,10080,20160,43200" = D0/1/3/7/14/30)
  CALLBACK_MAX_RETRIES       hard cap on cadence RETRIES (after T0) (default 2)
  CALLBACK_BUSY_RETRY_MINS   short reschedule after BUSY            (default 25)
  CALLBACK_MAX_BUSY_PER_DAY  busy retries allowed per lead per day  (default 1)
  CALLBACK_DND_START_HOUR    quiet-hours start (IST, 24h)           (default 21)
  CALLBACK_DND_END_HOUR      quiet-hours end   (IST, 24h)           (default 9)
  CALLBACK_MIN_GAP_MINS      hard min gap between any two dials     (default 120)
  CALLBACK_MAX_PRIORITY_DIALS  absolute ceiling on 'call me at X' dials
                             so a stale/repeated callback_at can NEVER
                             dial unboundedly (the priority-exemption cap) (default 3)
  CALLBACK_TZ                vendor tz for the DND window           (default Asia/Kolkata)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

_TRUE = ("1", "true", "True", "yes", "on")

# The warm-lead cadence (research W10): minutes from lead arrival / attempt 0.
# D0(immediate), D1, D3, D7, D14, D30. MAX_RETRIES then clamps how many fire.
DEFAULT_CADENCE_MINS = (0, 1440, 4320, 10080, 20160, 43200)


def _flag(name: str, default: str = "0") -> bool:
    v = os.getenv(name, default)
    return (v or "").strip() in _TRUE


def _ints(raw: str) -> tuple[int, ...]:
    out: list[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(float(part)))
        except (ValueError, TypeError):
            continue
    return tuple(out)


@dataclass(frozen=True)
class CallbackConfig:
    """Immutable snapshot of the cadence knobs. Build with `from_env()` in
    production; construct directly in tests. A per-tenant override (`for_tenant`)
    layers the panel-tunable fields on top WITHOUT touching env — that is the
    'tenant can tune/disable' path."""

    enabled: bool = False                              # master OFF default
    cadence_mins: tuple[int, ...] = DEFAULT_CADENCE_MINS
    max_retries: int = 2                               # retries AFTER the first (T0) touch
    busy_retry_mins: int = 25
    max_busy_per_day: int = 1
    dnd_start_hour: int = 21                            # 21:00 IST quiet starts
    dnd_end_hour: int = 9                               # 09:00 IST quiet ends
    min_gap_mins: int = 120                             # hard anti-runaway floor
    max_priority_dials: int = 3                          # ABSOLUTE ceiling on 'call me at X' dials
    tz_name: str = "Asia/Kolkata"

    @classmethod
    def from_env(cls) -> "CallbackConfig":
        cad = _ints(os.getenv("CALLBACK_CADENCE_MINS", "")) or DEFAULT_CADENCE_MINS
        return cls(
            enabled=_flag("CALLBACK_CADENCE_ENABLED"),
            cadence_mins=cad,
            max_retries=int(os.getenv("CALLBACK_MAX_RETRIES", "2")),
            busy_retry_mins=int(os.getenv("CALLBACK_BUSY_RETRY_MINS", "25")),
            max_busy_per_day=int(os.getenv("CALLBACK_MAX_BUSY_PER_DAY", "1")),
            dnd_start_hour=int(os.getenv("CALLBACK_DND_START_HOUR", "21")),
            dnd_end_hour=int(os.getenv("CALLBACK_DND_END_HOUR", "9")),
            min_gap_mins=int(os.getenv("CALLBACK_MIN_GAP_MINS", "120")),
            max_priority_dials=int(os.getenv("CALLBACK_MAX_PRIORITY_DIALS", "3")),
            tz_name=(os.getenv("CALLBACK_TZ") or "Asia/Kolkata").strip(),
        )

    # ------------------------------------------------------- tenant tuning #
    def for_tenant(self, overrides: Optional[dict]) -> "CallbackConfig":
        """Layer a tenant's panel-set overrides onto this base config. The panel
        persists a small dict on the campaign/tenant (e.g. {"enabled": False,
        "cadence_mins": [0,1440,4320], "max_retries": 1}); this folds it in.
        Unknown keys ignored; bad values fall back to the base (fail-safe — a
        broken tenant setting can NEVER widen the cadence into spam)."""
        if not overrides:
            return self
        from dataclasses import replace

        kw: dict = {}
        if "enabled" in overrides:
            kw["enabled"] = bool(overrides["enabled"])
        cad = overrides.get("cadence_mins")
        if isinstance(cad, (list, tuple)) and cad:
            try:
                kw["cadence_mins"] = tuple(int(x) for x in cad)
            except (ValueError, TypeError):
                pass
        for k in ("max_retries", "busy_retry_mins", "max_busy_per_day",
                  "dnd_start_hour", "dnd_end_hour", "min_gap_mins",
                  "max_priority_dials"):
            if k in overrides:
                try:
                    kw[k] = int(overrides[k])
                except (ValueError, TypeError):
                    pass
        # DEFENSE-IN-DEPTH: a tenant override can only ever make the cadence SAFER,
        # never widen it into spam. Clamp the spam-sensitive knobs to a hard floor /
        # ceiling so a panel typo (min_gap=1, max_retries=999) can't disable the
        # anti-runaway guards. The real invariant is the fire_due attempts cap, but
        # we belt-and-braces it here too.
        if "min_gap_mins" in kw:
            kw["min_gap_mins"] = max(self.min_gap_mins, kw["min_gap_mins"])  # never shrink the floor
        if "max_retries" in kw:
            kw["max_retries"] = max(0, min(kw["max_retries"], self.max_retries))  # never raise the cap
        if "max_priority_dials" in kw:
            kw["max_priority_dials"] = max(0, min(kw["max_priority_dials"], self.max_priority_dials))
        if isinstance(overrides.get("tz_name"), str) and overrides["tz_name"].strip():
            kw["tz_name"] = overrides["tz_name"].strip()
        return replace(self, **kw) if kw else self

    # --------------------------------------------------------- derived knobs #
    @property
    def max_cadence_touches(self) -> int:
        """Total cadence dials allowed: the first (T0) + max_retries, bounded by
        the length of the cadence array. This is the hard cap the scheduler
        enforces — the single invariant that makes a runaway loop impossible."""
        return max(1, min(self.max_retries + 1, len(self.cadence_mins)))

    def offset_for(self, touch_index: int) -> int:
        """Minutes-from-arrival for the Nth cadence touch (0-based). Clamps to the
        last entry so an out-of-range index can never wrap to backoff[0]=120 (the
        old bug F) — it saturates at the LONGEST gap, never the shortest."""
        if not self.cadence_mins:
            return 1440
        i = max(0, min(touch_index, len(self.cadence_mins) - 1))
        return self.cadence_mins[i]
