"""voice_ops.config.keyhealth — the HEALTH-SCORED API-key pool (W13).

This is the founder's "route to the healthiest key + instant failover, fail-LOUD" engine. It
EXTENDS the W5 primitive `voice_kernel.providers.keypool.KeyPool` (binary healthy/cooldown rotation)
into a multi-factor SCORE so the pool picks the *best* key, not merely the next non-cooling one:

  capacity     — remaining quota headroom (1.0 = full, 0.0 = exhausted)
  rate_limit   — recent 429 pressure (decays as 429s age out of the window)
  latency      — EWMA of observed call latency vs a target budget
  error_rate   — EWMA of non-429 failures (5xx / transport)
  reliability   — long-run success ratio (consecutive successes lift it, failures cut it)

A composite `score in [0,1]` (weighted) ranks healthy keys; `pick()` returns the HIGHEST-scoring
key whose circuit is closed, or None (the LOUD exhaustion signal the router turns into a logged
failover — never a silent default). A key that 429s or errors past threshold trips its circuit
(cooldown with 30→60→120s backoff like provider_registry.health) and is SKIPPED until it recovers;
every skip/trip/failover is recorded in `last_decisions` so nothing is ever silent.

Keys are identified by a NON-reversible fingerprint (vault.fingerprint) — this module NEVER holds a
plaintext secret. The caller maps fingerprint→ciphertext via the key store; the pool only scores.

Pure stdlib, deterministic (time source injectable). Importing this pulls ZERO droplet/agent code.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

log = logging.getLogger("voice_ops.config.keyhealth")

# circuit backoff schedule (seconds), mirrors provider_registry.health.
_BACKOFFS = (30.0, 60.0, 120.0, 240.0)
# 429s older than this window stop counting against rate-limit pressure.
_RL_WINDOW_S = 60.0
# composite score weights (sum = 1.0). reliability + capacity dominate; latency is a tie-breaker.
_W = {"capacity": 0.30, "rate_limit": 0.20, "latency": 0.15, "error_rate": 0.15, "reliability": 0.20}


@dataclass
class KeyHealth:
    """Live health of ONE key (referenced by fingerprint, never plaintext)."""

    fingerprint: str
    # raw signals
    remaining_capacity: Optional[int] = None   # from provider rate-limit headers; None = unknown
    capacity_limit: Optional[int] = None
    _recent_429_ts: list = field(default_factory=list, repr=False)
    latency_ewma_ms: float = 0.0
    error_ewma: float = 0.0                     # EWMA of non-429 failures in [0,1]
    reliability: float = 1.0                    # long-run success ratio in [0,1]
    # circuit
    open: bool = False
    consecutive_fails: int = 0
    trips: int = 0
    cooldown_until: float = 0.0
    last_error: str = ""
    last_code: Optional[int] = None
    # P2 usage analytics (lifetime counters for the Service Control Center health view)
    success_count: int = 0
    fail_count: int = 0
    rate_limit_count: int = 0       # subset of fail_count that were 429s
    pick_count: int = 0
    last_used_ts: float = 0.0

    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return 1.0 if total <= 0 else self.success_count / total

    def status_label(self) -> str:
        """Coarse health bucket for the UI badge: healthy | degraded | cooling."""
        if self.open:
            return "cooling"
        if self.reliability < 0.6 or self.error_ewma > 0.25 or len(self._recent_429_ts) >= 2:
            return "degraded"
        return "healthy"

    def _capacity_score(self) -> float:
        if self.remaining_capacity is None or not self.capacity_limit:
            return 1.0  # unknown headroom -> don't penalize (provider gives no header)
        if self.capacity_limit <= 0:
            return 0.0
        return max(0.0, min(1.0, self.remaining_capacity / self.capacity_limit))

    def _rate_limit_score(self, now: float) -> float:
        recent = [t for t in self._recent_429_ts if now - t <= _RL_WINDOW_S]
        self._recent_429_ts = recent
        # each recent 429 costs 0.25; 0 → 1.0, 4+ → 0.0
        return max(0.0, 1.0 - 0.25 * len(recent))

    def _latency_score(self, target_ms: float) -> float:
        if self.latency_ewma_ms <= 0:
            return 1.0
        if target_ms <= 0:
            return 1.0
        # at target -> ~0.5; well under -> ~1.0; 2x over -> ~0.0
        ratio = self.latency_ewma_ms / target_ms
        return max(0.0, min(1.0, 1.0 - 0.5 * (ratio - 0.0)))

    def score(self, now: float, target_latency_ms: float) -> float:
        """Composite [0,1]. An OPEN circuit scores 0 (never picked)."""
        if self.open:
            return 0.0
        return (
            _W["capacity"] * self._capacity_score()
            + _W["rate_limit"] * self._rate_limit_score(now)
            + _W["latency"] * self._latency_score(target_latency_ms)
            + _W["error_rate"] * (1.0 - self.error_ewma)
            + _W["reliability"] * self.reliability
        )


@dataclass
class HealthDecision:
    """One non-silent decision record (pick / skip / trip / recover / failover)."""

    action: str
    fingerprint: str
    detail: str
    score: float = 0.0


class HealthScoredKeyPool:
    """A score-ranked, circuit-aware, fail-LOUD pool over N keys of ONE provider.

    Construct with the list of key fingerprints (the key store supplies them). `pick()` returns the
    highest-scoring closed-circuit fingerprint or None. Feed outcomes back via `report_success` /
    `report_failure` (429 / 5xx / transport) and `observe_latency` / `set_capacity`. Every routing
    decision appends to `last_decisions` so a failover is auditable, never silent."""

    def __init__(
        self,
        provider: str,
        fingerprints: tuple[str, ...] = (),
        *,
        target_latency_ms: float = 1500.0,
        fail_threshold: int = 3,
        now: Optional[Callable[[], float]] = None,
        ewma_alpha: float = 0.3,
    ) -> None:
        self.provider = (provider or "").strip().lower()
        self.target_latency_ms = float(target_latency_ms)
        self.fail_threshold = int(fail_threshold)
        self.ewma_alpha = float(ewma_alpha)
        import time
        self._now = now or time.monotonic
        self._keys: dict[str, KeyHealth] = {fp: KeyHealth(fp) for fp in fingerprints if fp}
        self.last_decisions: list[HealthDecision] = []
        self._rr: int = 0  # round-robin cursor, breaks ties among equally-healthy keys
        # how close two scores must be to count as a "tie" eligible for round-robin sharing.
        self.tie_epsilon: float = 0.05

    # --------------------------------------------------------- membership -- #
    def set_keys(self, fingerprints: tuple[str, ...]) -> None:
        """Reconcile the live key set (hot-add/remove). New keys join at full health (so a freshly
        added key is immediately eligible); removed keys drop; existing keys KEEP their health
        state across reconciles (so rotation history isn't lost when one key is added)."""
        want = {fp for fp in fingerprints if fp}
        for fp in want:
            if fp not in self._keys:
                self._keys[fp] = KeyHealth(fp)
                self._decide("added", fp, "key joined pool at full health", 1.0)
        for fp in list(self._keys):
            if fp not in want:
                del self._keys[fp]
                self._decide("removed", fp, "key removed from pool", 0.0)

    @property
    def healthy_count(self) -> int:
        self._refresh_circuits()
        return sum(1 for h in self._keys.values() if not h.open)

    def __len__(self) -> int:
        return len(self._keys)

    # ------------------------------------------------------------- picking -- #
    def _refresh_circuits(self) -> None:
        t = self._now()
        for h in self._keys.values():
            if h.open and h.cooldown_until and t >= h.cooldown_until:
                h.open = False
                h.consecutive_fails = 0
                h.cooldown_until = 0.0
                self._decide("recover", h.fingerprint, "cooldown elapsed -> circuit closed", 0.0)

    def pick(self) -> Optional[str]:
        """Return the best closed-circuit key fingerprint, or None. Among keys whose score is within
        `tie_epsilon` of the top score we ROUND-ROBIN (so two equally-healthy keys SHARE load instead
        of hammering one) — that is the live-rotation behaviour. A clearly-healthier key still wins
        outright. None is the explicit, LOUD exhaustion signal — the router turns it into a logged
        failover, never a silent default."""
        self._refresh_circuits()
        now = self._now()
        scored: list[tuple[float, str]] = []
        for fp, h in self._keys.items():
            if h.open:
                continue
            scored.append((h.score(now, self.target_latency_ms), fp))
        if not scored:
            self._decide("exhausted", "", "ALL keys unhealthy/open — pool exhausted (LOUD)", 0.0)
            log.warning("keyhealth[%s]: pool EXHAUSTED — no healthy key (failover required)", self.provider)
            return None
        top = max(s for s, _ in scored)
        # all keys near the top score share load round-robin; the rest are skipped.
        contenders = sorted((fp for s, fp in scored if top - s <= self.tie_epsilon))
        chosen = contenders[self._rr % len(contenders)]
        self._rr += 1
        ch = self._keys.get(chosen)
        if ch is not None:
            ch.pick_count += 1
            ch.last_used_ts = now
        self._decide("pick", chosen, f"selected healthiest key ({len(contenders)} tied)", top)
        return chosen

    def snapshot(self) -> dict:
        """UI-shaped health snapshot (NO secrets — fingerprints only). The health-badge data."""
        now = self._now()
        keys = []
        for fp, h in self._keys.items():
            keys.append({
                "fingerprint": fp,
                "status": h.status_label(),
                "score": round(h.score(now, self.target_latency_ms), 3),
                "open": h.open,
                "trips": h.trips,
                "consecutive_fails": h.consecutive_fails,
                "latency_ewma_ms": round(h.latency_ewma_ms, 1),
                "error_ewma": round(h.error_ewma, 3),
                "reliability": round(h.reliability, 3),
                "remaining_capacity": h.remaining_capacity,
                "retry_in_s": max(0.0, round(h.cooldown_until - now, 1)) if h.open else 0.0,
                "last_error": h.last_error,
                "last_code": h.last_code,
                # P2 usage analytics
                "success_count": h.success_count,
                "fail_count": h.fail_count,
                "rate_limit_count": h.rate_limit_count,
                "pick_count": h.pick_count,
                "success_rate": round(h.success_rate(), 3),
                "last_used_ts": round(h.last_used_ts, 1) if h.last_used_ts else 0.0,
            })
        keys.sort(key=lambda k: k["score"], reverse=True)
        return {"provider": self.provider, "healthy": self.healthy_count, "total": len(self._keys), "keys": keys}

    # ----------------------------------------------------------- feedback -- #
    def observe_latency(self, fingerprint: str, latency_ms: float) -> None:
        h = self._keys.get(fingerprint)
        if h is None or latency_ms <= 0:
            return
        h.latency_ewma_ms = latency_ms if h.latency_ewma_ms <= 0 else (
            self.ewma_alpha * latency_ms + (1 - self.ewma_alpha) * h.latency_ewma_ms
        )

    def set_capacity(self, fingerprint: str, remaining: int, limit: int) -> None:
        h = self._keys.get(fingerprint)
        if h is None:
            return
        h.remaining_capacity = int(remaining)
        h.capacity_limit = int(limit)

    def report_success(self, fingerprint: str, *, latency_ms: float = 0.0) -> None:
        h = self._keys.get(fingerprint)
        if h is None:
            return
        h.success_count += 1
        if latency_ms > 0:
            self.observe_latency(fingerprint, latency_ms)
        h.consecutive_fails = 0
        h.error_ewma = (1 - self.ewma_alpha) * h.error_ewma  # decay toward 0
        h.reliability = min(1.0, h.reliability + 0.05 * (1.0 - h.reliability))
        # a success does NOT auto-close an open circuit (cooldown owns that) — but it heals score.

    def report_failure(self, fingerprint: str, code: int, *, detail: str = "") -> None:
        """Feed a failure. 429 = rate-limit pressure + circuit trip on threshold. 5xx/transport =
        error-rate + reliability hit + circuit trip. 4xx (≠429,408) does NOT trip — it's a request
        bug, not a key problem (mirrors KeyPool.report_failure). Every trip is LOGGED, never silent."""
        h = self._keys.get(fingerprint)
        if h is None:
            return
        h.last_code = code
        h.last_error = (detail or f"code {code}")[:160]
        if 400 <= code < 429 and code != 408:
            self._decide("ignore_4xx", fingerprint, f"{code} is a request bug, not a key fault", 0.0)
            return
        now = self._now()
        h.fail_count += 1
        if code == 429:
            h.rate_limit_count += 1
            h._recent_429_ts.append(now)
        else:
            h.error_ewma = self.ewma_alpha + (1 - self.ewma_alpha) * h.error_ewma
            h.reliability = max(0.0, h.reliability - 0.15)
        h.consecutive_fails += 1
        if h.consecutive_fails >= self.fail_threshold:
            self._trip(h, now)

    def _trip(self, h: KeyHealth, now: float) -> None:
        h.open = True
        backoff = _BACKOFFS[min(h.trips, len(_BACKOFFS) - 1)]
        h.cooldown_until = now + backoff
        h.trips += 1
        self._decide("trip", h.fingerprint,
                     f"circuit OPEN after {h.consecutive_fails} fails (code={h.last_code}) — "
                     f"cooldown {backoff:.0f}s", 0.0)
        log.warning("keyhealth[%s]: key %s circuit OPEN (%.0fs backoff, code=%s)",
                    self.provider, h.fingerprint, backoff, h.last_code)

    def _decide(self, action: str, fp: str, detail: str, score: float) -> None:
        self.last_decisions.append(HealthDecision(action=action, fingerprint=fp, detail=detail, score=round(score, 3)))
        # bounded so a long-lived pool can't grow unbounded.
        if len(self.last_decisions) > 200:
            self.last_decisions = self.last_decisions[-100:]
