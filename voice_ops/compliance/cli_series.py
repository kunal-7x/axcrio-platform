"""voice_ops.compliance.cli_series — the 140 / 1600 (160) CLI-series gate (W26 Tier A #2).

A commercial AI call's originating CLI must be a TRAI-registered series, NOT a plain
10-digit mobile (dialing commercial calls from an ordinary mobile is itself a violation
that gets the number disconnected). This module classifies the outbound CLI and decides
eligibility for a dial PURPOSE:

  * 140-series  -> PROMOTIONAL outbound (campaigns/offers). Eligible for 'campaign'.
  * 160 / 1600  -> TRANSACTIONAL / service (reminders, OTP, account alerts). Eligible
                   for service/transactional calls (and, conservatively, NOT for pure
                   promotional campaigns — a service number must not be used to spam).
  * 1601        -> IRDAI health-insurer transactional (a 1600 subtype).
  * mobile      -> a 10-digit mobile (starts 6/7/8/9) -> NOT eligible for ANY commercial
                   dial. This is the violation the gate blocks.
  * unknown     -> fail-closed: treated as ineligible (never dial on unknown identity).

The classification is pure string analysis over a normalised E.164 / national number;
the AUTHORITATIVE registration state (is this 140 number actually DLT-registered + active)
lives in the dlt_registry (engine.py reads it) — this module answers the SERIES SHAPE
question. The two together gate A2.

PURE: stdlib only; NEVER raises (garbage -> 'unknown' -> ineligible).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# dial purposes (mirror trunk_registry.schema.Purpose vocabulary).
PURPOSE_CAMPAIGN = "campaign"          # promotional, at volume -> needs 140
PURPOSE_TRANSACTIONAL = "transactional"  # service/reminder -> 160/1600
PURPOSE_TEST = "test"                  # single founder test ring -> series not gated
PURPOSE_MANUAL = "manual"              # single founder manual recall -> series not gated

# series tags
SERIES_140 = "140"
SERIES_160 = "160"
SERIES_1600 = "1600"
SERIES_1601 = "1601"
SERIES_MOBILE = "mobile"
SERIES_UNKNOWN = "unknown"

_DIGITS = re.compile(r"\D+")


def _national(number: str) -> str:
    """Strip to digits and drop a leading 91 country code / leading 0 so we look at the
    national significant number (140xxxx, 1600xxxx, or a 10-digit mobile)."""
    d = _DIGITS.sub("", number or "")
    if d.startswith("0091"):
        d = d[4:]
    elif d.startswith("91") and len(d) > 10:
        d = d[2:]
    elif d.startswith("0") and len(d) > 10:
        d = d[1:]
    return d


def classify(number: str) -> str:
    """Classify an outbound CLI into its series tag. NEVER raises."""
    d = _national(number)
    if not d:
        return SERIES_UNKNOWN
    if d.startswith("1601"):
        return SERIES_1601
    if d.startswith("1600"):
        return SERIES_1600
    if d.startswith("160"):
        return SERIES_160
    if d.startswith("140"):
        return SERIES_140
    # a 10-digit (or 11-with-trunk) Indian mobile starts 6/7/8/9.
    if len(d) == 10 and d[0] in "6789":
        return SERIES_MOBILE
    if len(d) == 10:
        # 10-digit landline-style — not a registered commercial series.
        return SERIES_UNKNOWN
    return SERIES_UNKNOWN


@dataclass(frozen=True)
class SeriesVerdict:
    series: str
    eligible: bool
    reason: str


def check(number: str, *, purpose: str = PURPOSE_CAMPAIGN) -> SeriesVerdict:
    """Is `number` an eligible CLI for this dial `purpose`?
      * TEST / MANUAL (a single founder-placed ring) -> series NOT gated (eligible),
        mirroring trunk_registry.schema.Purpose semantics.
      * CAMPAIGN (promotional at volume) -> requires 140-series.
      * TRANSACTIONAL (service) -> requires 160/1600/1601.
      * mobile / unknown -> ALWAYS ineligible for a commercial purpose (fail-closed).
    NEVER raises."""
    p = (purpose or PURPOSE_CAMPAIGN).strip().lower()
    series = classify(number)

    if p in (PURPOSE_TEST, PURPOSE_MANUAL):
        # a single founder test/manual ring skips the series gate (never an auto-dial).
        if series == SERIES_MOBILE or series == SERIES_UNKNOWN:
            return SeriesVerdict(series, True, f"{p}_single_ring_series_ungated")
        return SeriesVerdict(series, True, f"{p}_single_ring")

    if series == SERIES_MOBILE:
        return SeriesVerdict(series, False, "10_digit_mobile_commercial_dial_is_a_violation")
    if series == SERIES_UNKNOWN:
        return SeriesVerdict(series, False, "unregistered_or_unknown_series_fail_closed")

    if p == PURPOSE_CAMPAIGN:
        if series == SERIES_140:
            return SeriesVerdict(series, True, "140_series_promotional_ok")
        return SeriesVerdict(series, False, f"{series}_not_eligible_for_promotional_campaign")

    if p == PURPOSE_TRANSACTIONAL:
        if series in (SERIES_160, SERIES_1600, SERIES_1601):
            return SeriesVerdict(series, True, f"{series}_transactional_ok")
        return SeriesVerdict(series, False, f"{series}_not_eligible_for_transactional")

    # unknown purpose -> fail-closed.
    return SeriesVerdict(series, False, f"unknown_purpose_{p}_fail_closed")
