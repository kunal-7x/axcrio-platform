"""voice_ops.compliance.window_floor — the LEGAL calling-window hard floor (W26 §3.4).

THE FOUNDER-CRITICAL FIX: the live default calling window is 09:00–21:00 IST, which is
OUT OF LEGAL BOUNDS. The legal commercial window is 10:00–19:00 recipient-local
(BFSI/collections 08:00–19:00). This module owns the single rule a tenant CANNOT escape:

    effective_window = INTERSECT(tenant_window, legal_floor[vertical])

Intersection means the effective open = max(tenant_open, floor_open) and effective close
= min(tenant_close, floor_close). A tenant configuring 09:00–21:00 is clamped to
10:00–19:00; a tenant configuring 11:00–17:00 (tighter) is honoured verbatim. There is NO
input that widens the window past the legal floor — the max/min math makes widening
structurally impossible (the property the test pins).

PURE: stdlib only; NEVER raises. The legal floor itself is read from ComplianceConfig
(so counsel can tune it per the §9 sign-off via env) but DEFAULTS to the conservative
in-force values, and an unknown/garbage tenant window collapses to the floor (fail-safe).
"""
from __future__ import annotations

from typing import Optional, Tuple

from .config import ComplianceConfig

# Module-level legal floor constants (the in-force defaults; env can tune via config).
LEGAL_COMMERCIAL = ((10, 0), (19, 0))     # 10:00–19:00 recipient-local
LEGAL_BFSI = ((8, 0), (19, 0))            # 08:00–19:00 (collections/BFSI)

# ABSOLUTE STATUTORY CEILING — the env floor can only ever be TIGHTENED, never widened
# past these. Even a misconfigured COMPLIANCE_WINDOW_START/END can never authorize a dial
# outside these bounds. Commercial: never before 10:00, never after 19:00. BFSI/collections
# may open as early as 08:00 (the regulated earlier slot) but never close after 19:00.
# (TCCCPR/TRAI commercial-call window; the env knob exists only for counsel to NARROW it.)
ABS_COMMERCIAL = ((10, 0), (19, 0))
ABS_BFSI = ((8, 0), (19, 0))

_BFSI_VERTICALS = {"bfsi", "banking", "insurance", "finance", "financial",
                   "collections", "lending", "nbfc"}


def _to_minutes(hm: Tuple[int, int]) -> int:
    return int(hm[0]) * 60 + int(hm[1])


def _from_minutes(m: int) -> Tuple[int, int]:
    m = max(0, min(24 * 60, int(m)))
    return (m // 60, m % 60)


def legal_floor(vertical: str = "", cfg: Optional[ComplianceConfig] = None
                ) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """The legal floor (open,close) for a vertical. BFSI/collections get the 08:00 open;
    everything else the 10:00 commercial floor. Reads ComplianceConfig when supplied so
    counsel can NARROW it via env — but the env input is itself clamped to the ABSOLUTE
    statutory ceiling (ABS_*), so a misconfigured/hostile COMPLIANCE_WINDOW_* can NEVER
    authorize a dial outside 10:00–19:00 (08:00–19:00 BFSI). The env knob can only tighten."""
    v = (vertical or "").strip().lower()
    if cfg is not None:
        (abs_o, abs_c) = ABS_BFSI if v in _BFSI_VERTICALS else ABS_COMMERCIAL
        if v in _BFSI_VERTICALS:
            env_open = _parse_hhmm(cfg.bfsi_window_start, (8, 0))
            env_close = _parse_hhmm(cfg.bfsi_window_end, (19, 0))
        else:
            env_open = _parse_hhmm(cfg.window_start, (10, 0))
            env_close = _parse_hhmm(cfg.window_end, (19, 0))
        # Clamp the operator/env floor INTO the absolute ceiling: the effective floor can
        # only ever be NARROWER — open no earlier than abs_open, close no later than abs_close.
        eff_open = _from_minutes(max(_to_minutes(env_open), _to_minutes(abs_o)))
        eff_close = _from_minutes(min(_to_minutes(env_close), _to_minutes(abs_c)))
        # A degenerate/empty env intersection collapses to the absolute ceiling (fail-safe).
        if _to_minutes(eff_close) <= _to_minutes(eff_open):
            return (abs_o, abs_c)
        return (eff_open, eff_close)
    return LEGAL_BFSI if v in _BFSI_VERTICALS else LEGAL_COMMERCIAL


def _parse_hhmm(s, default: Tuple[int, int]) -> Tuple[int, int]:
    if isinstance(s, tuple) and len(s) == 2:
        try:
            return (int(s[0]), int(s[1]))
        except (TypeError, ValueError):
            return default
    try:
        hh, mm = str(s or "").strip().split(":")
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return (h, m)
    except Exception:  # noqa: BLE001
        pass
    return default


def clamp_to_legal_floor(
    tenant_start: Tuple[int, int],
    tenant_end: Tuple[int, int],
    *,
    vertical: str = "",
    cfg: Optional[ComplianceConfig] = None,
) -> Tuple[Tuple[Tuple[int, int], Tuple[int, int]], str]:
    """INTERSECT a tenant window with the legal floor. Returns
    ((eff_start, eff_end), note). The tenant can only ever NARROW the window —
    effective_open = max(tenant_open, floor_open); effective_close = min(tenant_close,
    floor_close). A garbage/empty tenant window collapses to the floor (fail-safe).

    The KEY invariant the test pins: for ANY tenant input, the returned window is a
    SUBSET of the legal floor — it never starts earlier than the floor open nor ends
    later than the floor close."""
    (fo_h, fo_m), (fc_h, fc_m) = legal_floor(vertical, cfg)
    floor_open = _to_minutes((fo_h, fo_m))
    floor_close = _to_minutes((fc_h, fc_m))

    ts = _parse_hhmm(tenant_start, (fo_h, fo_m))
    te = _parse_hhmm(tenant_end, (fc_h, fc_m))
    tenant_open = _to_minutes(ts)
    tenant_close = _to_minutes(te)

    # If the tenant window is degenerate (open >= close), collapse to the floor.
    if tenant_close <= tenant_open:
        return ((( fo_h, fo_m), (fc_h, fc_m)), "tenant_degenerate->floor")

    eff_open = max(tenant_open, floor_open)
    eff_close = min(tenant_close, floor_close)

    # If the intersection is empty (tenant window entirely outside the floor), the
    # effective window is the floor's nearest legal slice -> collapse to the floor
    # (never produce a window that allows dialing outside the floor).
    if eff_close <= eff_open:
        return (((fo_h, fo_m), (fc_h, fc_m)), "tenant_outside_floor->floor")

    note = "intersected" if (eff_open != tenant_open or eff_close != tenant_close) else "tenant_within_floor"
    return ((_from_minutes(eff_open), _from_minutes(eff_close)), note)


def widens_floor(tenant_start: Tuple[int, int], tenant_end: Tuple[int, int],
                 *, vertical: str = "", cfg: Optional[ComplianceConfig] = None) -> bool:
    """True iff the RESULT of clamping is still inside the floor (it always is) — a
    helper the test uses to assert that no tenant input ever widens the floor. Always
    returns False by construction; provided as an explicit, auditable assertion point."""
    (eff_start, eff_end), _note = clamp_to_legal_floor(
        tenant_start, tenant_end, vertical=vertical, cfg=cfg)
    (fo, fc) = legal_floor(vertical, cfg)
    return (_to_minutes(eff_start) < _to_minutes(fo)) or (_to_minutes(eff_end) > _to_minutes(fc))
