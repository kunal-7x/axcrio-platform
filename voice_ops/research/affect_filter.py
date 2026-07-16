"""voice_ops.research.affect_filter — the honest, multimodal latent-affect tracker.

Scientific core of Famit Research, and the deliberate REPLACEMENT for the original spec's
PINN / UDE / "cognitive-friction PDE" / one-Adam-step-per-turn machinery (numerically
meaningless; no governing law; unfalsifiable). Affect evolves as a SMOOTH LATENT STATE and
the correct tool is online Bayesian FILTERING (Somandepalli et al., "Online Affect Tracking
with Multimodal Kalman Filters", AVEC-2016), not gradient "training".

THE MODEL (multimodal, per-axis, real-time, validatable)
--------------------------------------------------------
State  x_t = [Arousal, Friction, Engagement]^T, in z-units relative to the CALLER'S OWN
opening baseline (so "high" means high *for this speaker* on 8 kHz telephony).

Process — mean-reverting OU / leaky integrator (the spec's ODE, discretised correctly):
    x_t = a * x_{t-1} + w ,  a = 1 - 1/tau ,  w ~ N(0, Q)

Observation — linear-Gaussian, MULTIMODAL with PER-AXIS confidence (AVEC-2016):
    z_t = H x_t + v ,  v ~ N(0, R_t) ,  R_t = diag(base / conf_axis)
Each axis is observed by its BEST available modality, each with its own confidence, so the
filter trusts a strong channel and widens the band on a weak one:
  * Arousal   ← a learned SER model's arousal estimate (ssl_arousal) if present, else the
                z-scored prosody combo (F0+loudness+rate). Arousal is the prosody-strong axis.
  * Friction  ← the LLM's own structured read (llm_friction_z) if present — because the
                verification is unambiguous that valence/friction is ~80% LINGUISTIC content
                (Wagner et al. TPAMI-2023; AlloSat arXiv:2310.04481: text CCC .92 vs acoustic
                .81 on 8 kHz telephone) which prosody-only handcrafted features CANNOT recover.
                Falls back to the prosody+lexical combo when no LLM read is available.
  * Engagement← conversational-dynamics / entrainment (response latency, talk-share, overlap,
                backchannels, prosodic mirroring) — Levitan & Hirschberg NAACL-2012 tie
                entrainment to rapport AND task success. Pure arithmetic from timing we have.

H carries an optional arousal→friction COUPLING off-diagonal and the update can apply an
OBSERVATION DELAY — Huang et al. (Interspeech-2017, RECOLA) show delay + dynamics modelling
alone yields up to ~5% rel CCC arousal / ~58% rel valence over a vanilla Kalman, at zero cost.

The covariance P_t IS the uncertainty band the UI renders. Pure-Python NxN linear algebra
(zero numpy hard-dep → runs anywhere, trivially unit-testable). An `ewma` mode keeps the
even-simpler leaky-integrator baseline.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# z -> 0..100 display index. 50 == the caller's own baseline; SCALE maps ~3 sigma to the rails.
INDEX_CENTER = 50.0
INDEX_SCALE = 16.6667           # 50 + 16.6667*3 ~= 100

DEFAULT_AXES = ("arousal", "friction", "engagement")


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _finite(v, d: float = 0.0) -> float:
    """Coerce to a finite float; NaN / inf / None / garbage → `d`. update() takes externally-supplied
    feature dicts; one NaN must NOT poison the running baseline (Welford) and every later turn.
    `_clamp` deliberately does NOT catch NaN, so sanitise here before the value is used."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return d
    return x if math.isfinite(x) else d


@dataclass
class AffectConfig:
    """All knobs in one place (citable defaults). dt is "1 turn"; tau is in turns."""
    mode: str = "kalman"                 # "kalman" | "ewma"
    axes: tuple = DEFAULT_AXES
    tau_turns: float = 3.5               # OU relaxation time-constant → a = 1 - 1/tau
    process_noise: float = 0.16          # Q diagonal — how fast the state may genuinely move
    base_meas_noise: float = 0.55        # R baseline (z-units^2) at confidence==1
    min_confidence: float = 0.15         # floor so a 0-confidence turn doesn't blow R up to inf
    baseline_warmup: int = 2             # turns over which the z-score is damped (tiny baseline)
    baseline_lock: int = 4               # after this many turns the resting baseline FREEZES
    init_var: float = 1.0                # P0 diagonal (we start unsure)

    # Upgrade #6 (Huang et al. Interspeech-2017): zero-cost dynamics tuning. Defaults are modest
    # so the proven arousal/friction behaviour is preserved while adding the documented gain.
    arousal_friction_coupling: float = 0.12   # H[friction,arousal]: rising arousal lifts the
                                              # friction *measurement model* (tension co-moves)
    obs_delay_turns: int = 0                   # lag the measurement to align with perception lag

    # prosody observation weights (the FALLBACK when no learned/LLM channel is present).
    w_arousal: Dict[str, float] = field(default_factory=lambda: {
        "f0": 0.45, "loudness": 0.35, "rate": 0.20,
    })
    w_friction: Dict[str, float] = field(default_factory=lambda: {
        "pause": 0.40, "rate": -0.25, "loudness": -0.20, "f0": -0.05, "valence": -0.10,
    })


class _Welford:
    """Online mean/variance (Welford) — for per-caller baseline z-scoring. Stable, O(1)."""
    __slots__ = ("n", "mean", "m2")

    def __init__(self) -> None:
        self.n = 0
        self.mean = 0.0
        self.m2 = 0.0

    def push(self, x: float) -> None:
        self.n += 1
        d = x - self.mean
        self.mean += d / self.n
        self.m2 += d * (x - self.mean)

    @property
    def std(self) -> float:
        if self.n < 2:
            return 0.0
        return math.sqrt(max(self.m2 / (self.n - 1), 0.0))


class BaselineCalibrator:
    """Learns each feature's resting mean/std from the caller's own early turns, then FREEZES it
    (z-score vs the caller's opening, so sustained genuine affect stays elevated rather than being
    normalised away). std floors keep a flat/low-variance opening from being hair-trigger."""

    _STD_FLOOR = {"f0": 12.0, "loudness": 2.5, "rate": 0.4, "pause": 0.06, "valence": 0.3,
                  "ssl_arousal": 0.12, "engagement": 0.5}

    def __init__(self, warmup: int = 3, lock: int = 6) -> None:
        self.warmup = max(1, warmup)
        self.lock = max(self.warmup, lock)
        self._stats: Dict[str, _Welford] = {}

    def z(self, name: str, x: float) -> float:
        w = self._stats.setdefault(name, _Welford())
        xv = _finite(x)
        if w.n < self.lock:
            w.push(xv)
        std = max(w.std, self._STD_FLOOR.get(name, 1.0))
        z = (xv - w.mean) / std
        if w.n <= self.warmup:
            z *= (w.n / (self.warmup + 1.0))
        return _clamp(z, -4.0, 4.0)


# --- small pure-Python NxN linear algebra (N is 2-3; no numpy needed) --------- #
def _ident(n: int) -> List[List[float]]:
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def _matvec(M, v):
    return [sum(M[i][k] * v[k] for k in range(len(v))) for i in range(len(M))]


def _matmul(A, B):
    n, p, m = len(A), len(B), len(B[0])
    return [[sum(A[i][k] * B[k][j] for k in range(p)) for j in range(m)] for i in range(n)]


def _matT(M):
    return [[M[i][j] for i in range(len(M))] for j in range(len(M[0]))]


def _matsub(A, B):
    return [[A[i][j] - B[i][j] for j in range(len(A[0]))] for i in range(len(A))]


def _inv(M):
    """Gauss-Jordan inverse with partial pivoting for a small symmetric-PD-ish matrix. Falls back
    to a tiny ridge on a near-singular pivot so the filter never throws."""
    n = len(M)
    A = [list(M[i]) + _ident(n)[i] for i in range(n)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(A[r][c]))
        if abs(A[piv][c]) < 1e-12:
            A[c][c] += 1e-9                      # ridge: nudge off singular
            piv = c
        A[c], A[piv] = A[piv], A[c]
        d = A[c][c]
        A[c] = [v / d for v in A[c]]
        for r in range(n):
            if r != c and A[r][c] != 0.0:
                f = A[r][c]
                A[r] = [A[r][k] - f * A[c][k] for k in range(2 * n)]
    return [row[n:] for row in A]


@dataclass
class AffectState:
    arousal: float = 50.0
    arousal_var: float = 0.0
    friction: float = 50.0
    friction_var: float = 0.0
    engagement: float = 50.0
    engagement_var: float = 0.0
    regime: str = "steady"
    confidence: float = 0.0
    values: dict = field(default_factory=dict)   # {axis: index} for any extra axes
    vars: dict = field(default_factory=dict)


class AffectTracker:
    """Per-call online multimodal affect filter. Feed one feature-dict per caller turn.

    feats keys (all optional):
      prosody/fallback: f0_mean_hz, loudness_db, speech_rate_sps, pause_ratio, valence_hint
      learned/LLM channels (preferred when present, each with its own *_conf 0..1):
        ssl_arousal (0..1 SER arousal), ssl_conf
        llm_friction_z (z-units, +=more friction), llm_conf
        engagement_obs (z-ish from conversational dynamics), engagement_conf
      confidence: overall feature confidence (drives R when a channel has no own conf)
    """

    def __init__(self, cfg: Optional[AffectConfig] = None) -> None:
        self.cfg = cfg or AffectConfig()
        self.axes = list(self.cfg.axes)
        self.N = len(self.axes)
        self.idx = {a: i for i, a in enumerate(self.axes)}
        self.cal = BaselineCalibrator(self.cfg.baseline_warmup, self.cfg.baseline_lock)
        v0 = self.cfg.init_var
        self._x = [0.0] * self.N
        self._P = [[v0 if i == j else 0.0 for j in range(self.N)] for i in range(self.N)]
        self._ewma = [0.0] * self.N
        self._ewma_var = [v0] * self.N
        self._hist: List[Dict[str, float]] = []           # per-turn {axis: index}
        self._delay = deque(maxlen=max(1, self.cfg.obs_delay_turns + 1))
        # H: identity + arousal→friction coupling (only if both axes exist)
        self._H = _ident(self.N)
        if "arousal" in self.idx and "friction" in self.idx and self.cfg.arousal_friction_coupling:
            self._H[self.idx["friction"]][self.idx["arousal"]] = self.cfg.arousal_friction_coupling

    # -- build the per-axis observation vector + per-axis confidence -------------- #
    def _observe(self, feats: dict):
        zf = {
            "f0": self.cal.z("f0", feats.get("f0_mean_hz", 0.0)),
            "loudness": self.cal.z("loudness", feats.get("loudness_db", 0.0)),
            "rate": self.cal.z("rate", feats.get("speech_rate_sps", 0.0)),
            "pause": self.cal.z("pause", feats.get("pause_ratio", 0.0)),
            "valence": _finite(feats.get("valence_hint", 0.0)),
        }

        def combine(weights):
            num = sum(weights.get(k, 0.0) * zf.get(k, 0.0) for k in weights)
            l1 = sum(abs(w) for w in weights.values()) or 1.0
            return num / l1

        base_conf = _clamp(_finite(feats.get("confidence", 0.5), 0.5), 0.0, 1.0)
        obs = [0.0] * self.N
        conf = [base_conf] * self.N

        # Arousal: learned SER arousal (z-scored vs caller baseline) preferred, else prosody.
        if "arousal" in self.idx:
            if feats.get("ssl_arousal") is not None:
                obs[self.idx["arousal"]] = self.cal.z("ssl_arousal", feats["ssl_arousal"])
                conf[self.idx["arousal"]] = _clamp(_finite(feats.get("ssl_conf", 0.8), 0.8), 0.0, 1.0)
            else:
                obs[self.idx["arousal"]] = combine(self.cfg.w_arousal)

        # Friction: the LLM's structured read (already in z-units) preferred — valence is linguistic.
        if "friction" in self.idx:
            if feats.get("llm_friction_z") is not None:
                obs[self.idx["friction"]] = _clamp(_finite(feats["llm_friction_z"]), -4.0, 4.0)
                conf[self.idx["friction"]] = _clamp(_finite(feats.get("llm_conf", 0.75), 0.75), 0.0, 1.0)
            else:
                obs[self.idx["friction"]] = combine(self.cfg.w_friction)

        # Engagement: conversational-dynamics observation (z-scored), else neutral (no signal).
        if "engagement" in self.idx:
            if feats.get("engagement_obs") is not None:
                obs[self.idx["engagement"]] = self.cal.z("engagement", feats["engagement_obs"])
                conf[self.idx["engagement"]] = _clamp(_finite(feats.get("engagement_conf", 0.7), 0.7), 0.0, 1.0)
            else:
                obs[self.idx["engagement"]] = 0.0
                conf[self.idx["engagement"]] = self.cfg.min_confidence  # no signal → barely move

        return obs, conf, base_conf

    def update(self, feats: dict) -> AffectState:
        obs, conf, base_conf = self._observe(feats)
        # observation delay (Huang 2017): apply a lagged measurement when configured.
        self._delay.append((obs, conf))
        if len(self._delay) > self.cfg.obs_delay_turns:
            obs, conf = self._delay[0] if self.cfg.obs_delay_turns > 0 else (obs, conf)
        st = self._update_ewma(obs, conf, base_conf) if self.cfg.mode == "ewma" \
            else self._update_kalman(obs, conf, base_conf)
        self._hist.append({a: getattr_axis(st, a) for a in self.axes})
        st.regime = self._regime()
        return st

    def _update_kalman(self, obs, conf, base_conf) -> AffectState:
        cfg = self.cfg
        a = 1.0 - 1.0 / max(cfg.tau_turns, 1.0001)
        q = cfg.process_noise
        # PREDICT: x = a x ; P = a^2 P + Q I
        x = [a * xi for xi in self._x]
        a2 = a * a
        P = [[a2 * self._P[i][j] + (q if i == j else 0.0) for j in range(self.N)] for i in range(self.N)]
        H, Ht = self._H, _matT(self._H)
        R = [[(cfg.base_meas_noise / max(conf[i], cfg.min_confidence)) if i == j else 0.0
              for j in range(self.N)] for i in range(self.N)]
        # S = H P H^T + R ; K = P H^T S^-1
        HP = _matmul(H, P)
        S = [[sum(HP[i][k] * Ht[k][j] for k in range(self.N)) + R[i][j] for j in range(self.N)] for i in range(self.N)]
        PHt = _matmul(P, Ht)
        K = _matmul(PHt, _inv(S))
        Hx = _matvec(H, x)
        y = [obs[i] - Hx[i] for i in range(self.N)]
        x = [x[i] + sum(K[i][k] * y[k] for k in range(self.N)) for i in range(self.N)]
        KH = _matmul(K, H)
        P = _matmul(_matsub(_ident(self.N), KH), P)
        self._x, self._P = x, P
        return self._emit(x, [P[i][i] for i in range(self.N)], base_conf)

    def _update_ewma(self, obs, conf, base_conf) -> AffectState:
        cfg = self.cfg
        nx, nv = list(self._ewma), list(self._ewma_var)
        for i in range(self.N):
            alpha = (1.0 / max(cfg.tau_turns, 1.0001)) * max(conf[i], cfg.min_confidence)
            resid = obs[i] - self._ewma[i]
            nx[i] = self._ewma[i] + alpha * resid
            nv[i] = (1 - alpha) * (self._ewma_var[i] + alpha * resid * resid)
        self._ewma, self._ewma_var = nx, nv
        return self._emit(nx, nv, base_conf)

    def _emit(self, x, var, conf) -> AffectState:
        s2 = INDEX_SCALE * INDEX_SCALE
        idxv = {a: round(_clamp(INDEX_CENTER + INDEX_SCALE * x[self.idx[a]], 0.0, 100.0), 1) for a in self.axes}
        varv = {a: round(s2 * max(var[self.idx[a]], 0.0), 1) for a in self.axes}
        return AffectState(
            arousal=idxv.get("arousal", 50.0), arousal_var=varv.get("arousal", 0.0),
            friction=idxv.get("friction", 50.0), friction_var=varv.get("friction", 0.0),
            engagement=idxv.get("engagement", 50.0), engagement_var=varv.get("engagement", 0.0),
            regime="steady", confidence=round(conf, 3), values=idxv, vars=varv,
        )

    # -- regime detection (now engagement-aware) --------------------------------- #
    def _slope(self, axis: str, n: int = 3) -> float:
        h = [p.get(axis, 50.0) for p in self._hist[-n:]]
        if len(h) < 2:
            return 0.0
        return (h[-1] - h[0]) / (len(h) - 1)

    def _regime(self) -> str:
        if not self._hist:
            return "steady"
        last = self._hist[-1]
        fr = last.get("friction", 50.0)
        eng = last.get("engagement", 50.0)
        d_ar, d_fr, d_eng = self._slope("arousal"), self._slope("friction"), self._slope("engagement")
        if fr >= 60 and d_fr >= 2.5:
            return "rising_friction"
        if (d_ar <= -3.0 and d_fr >= 1.0) or (eng <= 42 and d_eng <= -3.0):
            return "disengaging"
        if fr >= 56 and d_fr <= -3.0:
            return "resolving"
        if (d_ar >= 3.0 and fr < 56) or (d_eng >= 3.0 and eng >= 58):
            return "warming"
        return "steady"


def getattr_axis(st: AffectState, axis: str) -> float:
    return st.values.get(axis, getattr(st, axis, 50.0))
