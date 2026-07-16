"""voice_ops.research.conformal — conformal "intervene now" trigger (Phase 2, Upgrade #5).

Replaces the hand-set regime thresholds (e.g. friction>=60) with a split-conformal threshold plus a
Conformal-PID online recalibration, so the in-call "intervene now" flag fires at a CONTROLLED, honest
false-alarm rate that self-corrects as 8 kHz line conditions / call mix drift.

Guarantee (split conformal, exchangeability): calibrate the risk threshold on the WON calls' risk
scores at level alpha → on a fresh WON call, P(fire) <= alpha (we control the rate of "crying wolf" on
calls that were actually going to convert). Conformal-PID (Angelopoulos et al., NeurIPS-2023) nudges
the threshold online to hold long-run coverage under distribution shift.

Pure-Python, O(1) per turn. Falls back to a sane default threshold before any calibration data exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ConformalTrigger:
    alpha: float = 0.2                 # target false-alarm rate on won calls (fire P<=alpha)
    threshold: float = 62.0            # risk threshold (0..100); sane default pre-calibration
    pid_lr: float = 1.5               # Conformal-PID learning rate (threshold units / step)
    _err_ema: float = 0.0

    def calibrate(self, won_call_risks: List[float]) -> "ConformalTrigger":
        """Split-conformal: threshold = the (1-alpha) empirical quantile of risk over WON calls, with
        the finite-sample (n+1) correction. Higher threshold → fewer false alarms on converters."""
        xs = sorted(float(r) for r in won_call_risks if r is not None)
        if len(xs) >= 5:
            import math
            k = min(len(xs) - 1, max(0, math.ceil((len(xs) + 1) * (1 - self.alpha)) - 1))
            self.threshold = round(xs[k], 1)
        return self

    def pid_update(self, fired: bool, was_won: bool) -> None:
        """Online Conformal-PID: if we fired on a call that actually converted, that's an error vs the
        alpha budget → push the threshold up; otherwise relax it down toward alpha coverage."""
        if not was_won:
            return                      # only converters constrain the false-alarm guarantee
        err = 1.0 if fired else 0.0
        self._err_ema = 0.9 * self._err_ema + 0.1 * err
        self.threshold = max(0.0, min(100.0, self.threshold + self.pid_lr * (self._err_ema - self.alpha)))

    def fire(self, risk: float, *, rising: bool = True) -> bool:
        """Fire the 'intervene now' flag when calibrated risk crosses threshold AND it is still rising
        (don't nag once an objection is already resolving)."""
        return float(risk or 0.0) >= self.threshold and rising

    def first_trigger_turn(self, risk_curve: List[float]) -> Optional[int]:
        """The earliest turn index at which the trigger fires on a risk curve (rising = risk increased
        vs the previous turn). None if it never fires."""
        for i, r in enumerate(risk_curve):
            rising = i == 0 or r >= risk_curve[i - 1]
            if self.fire(r, rising=rising):
                return i
        return None
