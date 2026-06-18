"""voice_ops.telephony.health — phone-number SPAM-reputation health scorer (W12 #3).

Per-NUMBER (per-DID) rolling-window reputation: every dial outcome (answered /
rejected / blocked / no-answer / spam-flag) is appended to a per-number ring buffer;
a 0..1 health score is derived and mapped to a NumberState the router obeys:

  HEALTHY     score >= recover_at  -> full traffic
  DEGRADED    degrade_at <= score < recover_at, OR below recover after a degrade
              -> reduced traffic (router prefers other numbers; this one is last-resort)
  QUARANTINED score < quarantine_at (with enough samples) -> RESTED for quarantine_minutes;
              the router skips it entirely until the rest expires, then it re-enters DEGRADED
              (probation) and must EARN its way back to HEALTHY.

This SHADOWS the live trunk_registry per-trunk quarantine (droplet_work, gitignored)
with finer per-DID rolling-window scoring — it never imports it; the seam doc shows
how `auto_reduce_traffic` feeds the existing `pick_did(avoid=[bad_dids])` parameter.

Scoring (transparent, monotone, bounded):
  weight per outcome: answered=+1.0, no_answer=+0.25 (neutral-ish; ringing isn't spam),
                      rejected=-0.6 (carrier/user reject — a spam signal),
                      blocked=-1.0, spam_flag=-1.0 (explicit spam labelling — worst).
  score = clamp01( 0.5 + mean(weighted_outcomes_in_window) * 0.5 )
  i.e. an all-answered number trends to 1.0, an all-blocked number to 0.0, with a
  neutral 0.5 prior so a brand-new/low-sample number is treated as "unproven", not bad.

Hysteresis: a QUARANTINE only fires with >= min_samples outcomes (never rest a number
on one bad call); recovery requires crossing recover_at (a higher bar than degrade_at)
so a number doesn't flap between states. State + rest-until are kept per number.

In-process, async-safe (threading.Lock — the scorer is sync, called from the dial
loop). A LATER seam wave can persist the rolling counters to the FORCE-RLS
`phone_number_pool` columns (answered_24h/rejected_24h/etc.); the score math is the
same. PURE: stdlib + config; NEVER raises into the dial loop.
"""
from __future__ import annotations

import datetime as _dt
import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, List, Optional, Tuple

from .config import TelephonyOpsConfig

log = logging.getLogger("voice_ops.telephony.health")

# outcome vocabulary + spam weight (load-bearing: the only place weights live).
ANSWERED = "answered"
NO_ANSWER = "no_answer"
REJECTED = "rejected"
BLOCKED = "blocked"
SPAM_FLAG = "spam_flag"

_WEIGHT: Dict[str, float] = {
    ANSWERED: 1.0,
    NO_ANSWER: 0.25,
    REJECTED: -0.6,
    BLOCKED: -1.0,
    SPAM_FLAG: -1.0,
}

# number states the router obeys.
HEALTHY = "healthy"
DEGRADED = "degraded"
QUARANTINED = "quarantined"


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


@dataclass
class HealthSnapshot:
    """Read-only view of a number's current reputation (for the router + the panel)."""
    number: str
    score: float
    state: str
    samples: int
    answered: int = 0
    rejected: int = 0
    blocked: int = 0
    spam_flag: int = 0
    no_answer: int = 0
    rest_until: Optional[str] = None      # ISO; set while QUARANTINED
    reasons: List[str] = field(default_factory=list)

    @property
    def is_dialable(self) -> bool:
        """True unless the number is currently resting (quarantined). DEGRADED is
        still dialable — the router just de-prioritises it."""
        return self.state != QUARANTINED

    @property
    def traffic_factor(self) -> float:
        """How much traffic the router should send relative to a HEALTHY peer:
        1.0 healthy, ~0.3 degraded, 0.0 quarantined. Used to auto-reduce/auto-increase."""
        if self.state == QUARANTINED:
            return 0.0
        if self.state == DEGRADED:
            return 0.30
        return 1.0


class SpamReputation:
    """Per-number rolling reputation scorer + state machine. Construct once per
    process: `SpamReputation(cfg)`. Thread-safe (sync, dial-loop-callable)."""

    def __init__(self, cfg: Optional[TelephonyOpsConfig] = None,
                 now_fn: Optional[Callable[[], _dt.datetime]] = None):
        self.cfg = cfg or TelephonyOpsConfig.from_env()
        self._now = now_fn or _now
        self._lock = threading.Lock()
        # number -> deque[(ts, outcome)]
        self._events: Dict[str, Deque[Tuple[_dt.datetime, str]]] = {}
        # number -> (state, rest_until|None)
        self._state: Dict[str, Tuple[str, Optional[_dt.datetime]]] = {}

    # --------------------------------------------------------- record #
    def record(self, number: str, outcome: str, *, answered: Optional[bool] = None,
               duration_s: Optional[float] = None) -> HealthSnapshot:
        """Append ONE outcome for `number` and re-derive its state. `outcome` is one
        of the vocabulary constants; for convenience you may pass `answered`/`duration_s`
        from the dial loop and let us infer: answered=True -> ANSWERED, else a
        zero-duration unanswered -> REJECTED (the carrier-reject spam signal), else
        NO_ANSWER. Unknown outcome -> treated as NO_ANSWER (neutral). NEVER raises."""
        num = (number or "").strip()
        if not num:
            return HealthSnapshot(number="", score=0.5, state=HEALTHY, samples=0)
        oc = (outcome or "").strip().lower()
        if oc not in _WEIGHT:
            if answered is True:
                oc = ANSWERED
            elif answered is False:
                oc = REJECTED if (duration_s is not None and float(duration_s or 0) <= 0.0) else NO_ANSWER
            else:
                oc = NO_ANSWER
        now = self._now()
        with self._lock:
            dq = self._events.setdefault(num, deque())
            dq.append((now, oc))
            self._prune(num, now)
            return self._evaluate_locked(num, now)

    # --------------------------------------------------------- reads #
    def snapshot(self, number: str) -> HealthSnapshot:
        """Current reputation snapshot for `number` (re-evaluating rest expiry)."""
        num = (number or "").strip()
        now = self._now()
        with self._lock:
            if num not in self._events and num not in self._state:
                # unknown number = unproven, treated HEALTHY at the neutral prior.
                return HealthSnapshot(number=num, score=0.5, state=HEALTHY, samples=0,
                                      reasons=["unproven"])
            self._prune(num, now)
            return self._evaluate_locked(num, now)

    def is_dialable(self, number: str) -> bool:
        return self.snapshot(number).is_dialable

    def unhealthy_numbers(self, numbers: List[str]) -> List[str]:
        """The `avoid=` list for the router / trunk_registry.pick_did: every number
        currently QUARANTINED (resting). DEGRADED numbers stay dialable (de-prioritised),
        so they are NOT in the avoid list."""
        out: List[str] = []
        for n in numbers or []:
            if self.snapshot(n).state == QUARANTINED:
                out.append(n)
        return out

    # --------------------------------------------------- internals #
    def _prune(self, number: str, now: _dt.datetime) -> None:
        dq = self._events.get(number)
        if not dq:
            return
        horizon = now - _dt.timedelta(seconds=int(self.cfg.health_window_seconds))
        while dq and dq[0][0] < horizon:
            dq.popleft()

    def _evaluate_locked(self, number: str, now: _dt.datetime) -> HealthSnapshot:
        """Derive score + apply the hysteresis state machine. Caller holds the lock."""
        dq = self._events.get(number, deque())
        counts = {ANSWERED: 0, NO_ANSWER: 0, REJECTED: 0, BLOCKED: 0, SPAM_FLAG: 0}
        weighted = 0.0
        for _ts, oc in dq:
            counts[oc] = counts.get(oc, 0) + 1
            weighted += _WEIGHT.get(oc, 0.0)
        samples = sum(counts.values())
        score = _clamp01(0.5 + (weighted / samples) * 0.5) if samples else 0.5

        prev_state, rest_until = self._state.get(number, (HEALTHY, None))
        reasons: List[str] = []

        # 1) If currently resting, honour the rest until it expires.
        if prev_state == QUARANTINED and rest_until is not None and rest_until > now:
            reasons.append(f"resting_until={rest_until.isoformat()}")
            self._state[number] = (QUARANTINED, rest_until)
            return self._snap(number, score, QUARANTINED, counts, samples, rest_until, reasons)

        # 2) Rest expired -> drop into DEGRADED probation (must re-earn HEALTHY).
        if prev_state == QUARANTINED and (rest_until is None or rest_until <= now):
            prev_state = DEGRADED
            reasons.append("rest_expired_probation")

        c = self.cfg
        # 3) New quarantine ONLY with enough samples + score under the floor.
        if samples >= c.health_min_samples and score < c.health_quarantine_at:
            until = now + _dt.timedelta(minutes=int(c.quarantine_minutes))
            self._state[number] = (QUARANTINED, until)
            reasons.append(f"score<{c.health_quarantine_at}->quarantine")
            log.info("number %s QUARANTINED score=%.2f samples=%d until=%s",
                     number, score, samples, until.isoformat())
            return self._snap(number, score, QUARANTINED, counts, samples, until, reasons)

        # 4) Degrade/recover with hysteresis (recover bar > degrade bar -> no flapping).
        if samples >= c.health_min_samples:
            if score < c.health_degrade_at:
                state = DEGRADED
                reasons.append(f"score<{c.health_degrade_at}->degraded")
            elif score >= c.health_recover_at:
                state = HEALTHY
                if prev_state != HEALTHY:
                    reasons.append(f"score>={c.health_recover_at}->recovered")
            else:
                # in the hysteresis band: stay where we were (sticky), defaulting to DEGRADED
                # only if we were already degraded; a fresh-ish number stays HEALTHY.
                state = DEGRADED if prev_state == DEGRADED else HEALTHY
                reasons.append("hysteresis_band_hold")
        else:
            # too few samples to trust -> unproven, treat as HEALTHY (neutral prior).
            state = HEALTHY
            reasons.append("low_samples_unproven")

        self._state[number] = (state, None)
        return self._snap(number, score, state, counts, samples, None, reasons)

    @staticmethod
    def _snap(number, score, state, counts, samples, rest_until, reasons) -> HealthSnapshot:
        return HealthSnapshot(
            number=number, score=round(score, 4), state=state, samples=samples,
            answered=counts.get(ANSWERED, 0), rejected=counts.get(REJECTED, 0),
            blocked=counts.get(BLOCKED, 0), spam_flag=counts.get(SPAM_FLAG, 0),
            no_answer=counts.get(NO_ANSWER, 0),
            rest_until=rest_until.isoformat() if rest_until else None,
            reasons=reasons,
        )

    # --------------------------------------------------- test helper #
    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._state.clear()
