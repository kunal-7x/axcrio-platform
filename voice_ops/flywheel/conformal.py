"""voice_ops.flywheel.conformal — B2 DISTRIBUTION-FREE Mondrian split-conformal calibration.

WHY THIS EXISTS
---------------
Riya's booking predictor and the LLM judge both emit a POINT score (a probability of booking, a
0..1 turn quality). Downstream we let those scores *gate* challengers and *shape* rewards — but a raw
point estimate has no honesty: a model can be confidently wrong, and worse, it can be MIS-CALIBRATED
in a way that drifts per cohort (a tiny new tenant's cold-list calls look nothing like the big
tenant's hot-list calls the model was mostly fit on). If we consume the point estimate as-if-truth we
bake Goodhart straight into the flywheel. B2 wraps every such predictor in a coverage guarantee and
forces the rest of the pipeline to read the PESSIMISTIC lower bound, never the raw point.

THE SCIENCE (split conformal + Mondrian taxonomy)
-------------------------------------------------
Split (inductive) conformal prediction (Vovk; the gentle intro is Angelopoulos & Bates 2023,
"A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification").
Given a held-out CALIBRATION set the model never trained on, define a nonconformity score per row
s_i = |pred_i - label_i| (absolute residual — the regression score). The conformal quantile

    q_hat = the  ceil((n+1)(1-alpha)) / n  -th empirical quantile of {s_1..s_n}

is the FINITE-SAMPLE-corrected (the (n+1) is the conformal correction, not a cosmetic +1) threshold
such that, under exchangeability ALONE — no Gaussianity, no model-correctness assumption — a fresh
test residual is <= q_hat with probability >= 1 - alpha. So [pred - q_hat, pred + q_hat] covers the
true label with frequency >= 1 - alpha. We only ever USE the lower edge `pred - q_hat`: the worst
plausible value of the prediction at confidence 1 - alpha. Consuming that lower bound is precisely the
ANTI-GOODHART / HONEST-SCIENCE law — the optimizer can never be fooled by an over-confident point.

MONDRIAN (group-conditional) conformal. Marginal coverage hides per-group under-coverage: the
guarantee can hold on average while systematically failing the small new tenant. Mondrian conformal
(Vovk) restores the guarantee PER BUCKET by computing a separate q_hat within each taxonomy cell
(here: a (campaign, lead_temperature, vertical) cohort string). The catch is data hunger — a bucket
with few calibration rows yields a noisy, often INFINITE q_hat (no usable bound). So we fall back to
the PARENT / marginal q_hat (computed over ALL rows pooled) whenever a bucket has < min_calib rows.
That trades a hair of group-conditionality for a finite, honest bound on small cohorts that would
otherwise silently under-cover. n == 0 anywhere → +inf sentinel = "no calibration, trust nothing".

DESIGN LAWS HONOURED
--------------------
PURE-PYTHON (math/statistics only — no numpy/sklearn/torch; the whole module is O(n log n) sorting,
nothing heavy to lazy-import). SIDE-PIPELINE: offline/worker calibration over rows the warehouse
already holds — no network, no ClickHouse, no LLM in this module. DORMANT-SAFE + BEST-EFFORT: every
public function swallows its own errors (→ logging.warning) and returns a clean sentinel (+inf q_hat,
empty dict / list), so a malformed calibration row can NEVER raise into the worker or the gate. ANTI-
GOODHART: the only quantity downstream is allowed to read is the PESSIMISTIC lower bound.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional

from . import schema as S

logger = logging.getLogger("flywheel.conformal")

# Sentinel for "no usable calibration" — an infinite ceiling means the lower bound collapses to
# pred - inf = -inf, i.e. the gate/optimizer treats an uncalibrated predictor as worthless (HONEST).
INF: float = float("inf")

__all__ = [
    "INF",
    "nonconformity",
    "conformal_quantile",
    "calibrate_mondrian",
    "pessimistic_lower",
    "calib_rows",
]


# --------------------------------------------------------------------------- #
# Core scores.
# --------------------------------------------------------------------------- #
def nonconformity(pred: float, label: float) -> float:
    """Regression nonconformity score s = |pred - label| (the absolute residual).

    This is the simplest, most defensible split-conformal score for a real-valued / probability
    predictor: it makes NO assumption about the shape of the error and is symmetric, so the resulting
    interval pred ± q_hat is a valid two-sided distribution-free band (we then read only its lower
    edge). A larger s means the row "conforms" less to the model — exactly what the empirical quantile
    of these scores is summarising. Best-effort: non-numeric inputs → +inf (maximally non-conforming,
    so a junk row can only widen — never falsely tighten — the calibrated q_hat).
    """
    try:
        return abs(float(pred) - float(label))
    except Exception:  # noqa: BLE001 — dormant-safe: a junk row must never raise
        logger.warning("conformal.nonconformity: non-numeric (pred=%r label=%r)", pred, label)
        return INF


def conformal_quantile(scores: List[float], alpha: float = 0.1) -> float:
    """Finite-sample-corrected conformal quantile of nonconformity `scores` at miscoverage `alpha`.

    Returns the  ceil((n+1)(1-alpha)) / n  empirical quantile (sorted ascending, 1-indexed rank),
    which is the smallest q with P(s_test <= q) >= 1 - alpha under exchangeability. Two honest edge
    cases:
      * n == 0            → +inf  (no calibration data: no bound, trust nothing downstream).
      * rank > n          → +inf  (when (n+1)(1-alpha) exceeds n — i.e. n is too small to certify the
                            requested coverage, e.g. n=8, alpha=0.1 needs the 9th of 8 → impossible —
                            the only honest answer is the unbounded interval, NOT the max score).
    Both map to the same "I cannot certify 1-alpha coverage here" sentinel rather than a fake number.
    """
    try:
        xs = sorted(float(s) for s in scores if s is not None and not _is_nan(s))
        n = len(xs)
        if n == 0:
            return INF
        a = min(max(float(alpha), 0.0), 1.0)
        # 1-indexed rank of the desired order statistic (the conformal (n+1) finite-sample correction).
        rank = math.ceil((n + 1) * (1.0 - a))
        if rank > n:
            # Not enough samples to guarantee 1-alpha coverage → unbounded interval (honest sentinel).
            return INF
        if rank < 1:
            rank = 1
        return float(xs[rank - 1])
    except Exception:  # noqa: BLE001
        logger.warning("conformal.conformal_quantile: failed (n=%d alpha=%r)", len(scores or []), alpha)
        return INF


# --------------------------------------------------------------------------- #
# Mondrian (group-conditional) calibration with a parent / marginal fallback.
# --------------------------------------------------------------------------- #
def calibrate_mondrian(
    rows: List[dict],
    *,
    alpha: float = 0.1,
    min_calib: int = 50,
) -> Dict[str, float]:
    """Per-bucket conformal q_hat with a marginal fallback for thin buckets.

    `rows` is a list of {'bucket': str, 'score': float} (score = a precomputed nonconformity, i.e.
    |pred - label|). We:
      1. compute the MARGINAL q_hat over ALL scores pooled (the parent — always present so every
         bucket has *some* finite-ish bound to fall back on),
      2. for each bucket with >= min_calib own scores, compute its OWN Mondrian q_hat,
      3. for every thinner bucket, inherit the marginal q_hat (small tenants under-cover otherwise).

    Returns {bucket: q_hat, ..., '_marginal': q_hat_all}. Buckets seen in `rows` but too thin still
    appear in the map (pointing at the marginal value) so a downstream lookup is a single dict hit.
    Best-effort: malformed rows are skipped; total failure → {'_marginal': +inf} (a safe "trust
    nothing" map). The '_marginal' key (leading underscore) can never collide with a real bucket
    string because buckets are composed from (campaign, lead_temperature, vertical) joined values.
    """
    try:
        by_bucket: Dict[str, List[float]] = {}
        all_scores: List[float] = []
        for r in rows or []:
            try:
                b = str(r.get("bucket", "all") or "all")
                s = r.get("score")
                if s is None or _is_nan(s):
                    continue
                sf = float(s)
                by_bucket.setdefault(b, []).append(sf)
                all_scores.append(sf)
            except Exception:  # noqa: BLE001 — skip one bad row, keep calibrating
                continue

        marginal = conformal_quantile(all_scores, alpha=alpha)
        out: Dict[str, float] = {"_marginal": marginal}
        mc = max(int(min_calib), 0)
        for b, ss in by_bucket.items():
            if len(ss) >= mc and mc > 0:
                q = conformal_quantile(ss, alpha=alpha)
                # A bucket that still cannot certify coverage (q == inf) falls back to the parent too.
                out[b] = q if math.isfinite(q) else marginal
            else:
                out[b] = marginal  # thin bucket → inherit the parent (Mondrian fallback)
        return out
    except Exception:  # noqa: BLE001
        logger.warning("conformal.calibrate_mondrian: failed (n_rows=%d)", len(rows or []))
        return {"_marginal": INF}


def pessimistic_lower(pred: float, q_hat: float) -> float:
    """The conformal LOWER bound  pred - q_hat  that the downstream gate / optimizer reads.

    This is the ONLY quantity B2 lets the rest of the flywheel consume from a calibrated predictor:
    the worst plausible value of `pred` at confidence 1 - alpha. With an uncalibrated predictor
    (q_hat == +inf) this collapses to -inf, i.e. "no credit" — the anti-Goodhart default. Best-effort:
    bad inputs → -inf (treat as worthless rather than risk an over-optimistic number leaking through).
    """
    try:
        p = float(pred)
        q = float(q_hat)
        if not math.isfinite(q):
            return -INF
        return p - q
    except Exception:  # noqa: BLE001
        logger.warning("conformal.pessimistic_lower: bad input (pred=%r q_hat=%r)", pred, q_hat)
        return -INF


# --------------------------------------------------------------------------- #
# Persistence — build schema.ConformalCalib rows (latest q_hat per (model_key, bucket)).
# --------------------------------------------------------------------------- #
def calib_rows(
    tenant_id: str,
    model_key: str,
    qmap: Dict[str, float],
    alpha: float,
    ncounts: Optional[Dict[str, int]] = None,
) -> List["S.ConformalCalib"]:
    """Build schema.ConformalCalib rows from a calibrate_mondrian() qmap for persistence.

    `qmap` is the dict returned by calibrate_mondrian (per-bucket q_hat + '_marginal'); `ncounts` is
    an optional {bucket: n_calib} so each persisted row carries its honest calibration sample count
    (sample counts travel WITH every estimate — HONEST SCIENCE). The '_marginal' pseudo-bucket is
    persisted under the literal bucket name 'all' so the parent fallback is itself queryable.

    A non-finite (+inf) q_hat is persisted as-is via the dataclass's float coercion downstream is the
    store's concern; here we keep it numeric and let to_row()/ClickHouse round-trip it. Best-effort:
    one bad entry is skipped, never raises; total failure → []. The ts is stamped ONCE so a whole
    calibration batch shares a timestamp (one logical calibration event).
    """
    out: List["S.ConformalCalib"] = []
    try:
        ts = S.now_iso()
        nc = ncounts or {}
        for bucket, q in (qmap or {}).items():
            try:
                persisted_bucket = "all" if bucket == "_marginal" else str(bucket)
                n_calib = int(nc.get(bucket, nc.get(persisted_bucket, 0)) or 0)
                out.append(
                    S.ConformalCalib(
                        tenant_id=str(tenant_id or ""),
                        model_key=str(model_key or ""),
                        bucket=persisted_bucket,
                        ts_iso=ts,
                        q_hat=float(q),
                        alpha=float(alpha),
                        n_calib=n_calib,
                    )
                )
            except Exception:  # noqa: BLE001 — skip one bad bucket, keep the rest
                logger.warning("conformal.calib_rows: skipped bucket=%r q=%r", bucket, q)
                continue
        return out
    except Exception:  # noqa: BLE001
        logger.warning("conformal.calib_rows: failed (tenant=%r model_key=%r)", tenant_id, model_key)
        return []


# --------------------------------------------------------------------------- #
# Internal helpers.
# --------------------------------------------------------------------------- #
def _is_nan(x: object) -> bool:
    """True iff x is a float NaN (NaNs poison a sort/quantile silently — drop them up front)."""
    try:
        return isinstance(x, float) and math.isnan(x)
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# Pure-python self-check (NO network / NO ClickHouse / NO numpy). Run: python -m ...conformal
# --------------------------------------------------------------------------- #
if __name__ == "__main__":  # pragma: no cover
    import random

    random.seed(7)

    # 1) nonconformity: simple absolute residual + junk → +inf.
    assert abs(nonconformity(0.8, 0.5) - 0.3) < 1e-9   # |0.8-0.5| (float-safe compare)
    assert nonconformity("not-a-number", 1.0) == INF   # non-numeric junk → maximally non-conforming
    print("[1] nonconformity OK  |0.8-0.5|=", nonconformity(0.8, 0.5))

    # 2) conformal_quantile: finite-sample correction + honest sentinels.
    assert conformal_quantile([], alpha=0.1) == INF                  # no data
    assert conformal_quantile([0.1] * 8, alpha=0.1) == INF           # n too small for 90% coverage
    big = [round(random.random(), 4) for _ in range(500)]
    q90 = conformal_quantile(big, alpha=0.1)
    assert math.isfinite(q90) and 0.0 <= q90 <= 1.0
    # Empirical coverage of |residual| <= q_hat on a fresh draw should be ~>= 1-alpha.
    fresh = [round(random.random(), 4) for _ in range(2000)]
    cover = sum(1 for s in fresh if s <= q90) / len(fresh)
    print(f"[2] conformal_quantile OK  q90={q90:.4f}  empirical_coverage={cover:.3f} (target>=0.90)")
    assert cover >= 0.86, cover  # finite-sample slack, but must be in the right ballpark

    # 3) calibrate_mondrian: a fat bucket gets its own q_hat; a thin bucket inherits the marginal.
    rows: List[dict] = []
    for _ in range(300):                                              # fat bucket 'hot'
        rows.append({"bucket": "hot", "score": round(random.random() * 0.4, 4)})
    for _ in range(5):                                                # thin bucket 'cold' (< min_calib)
        rows.append({"bucket": "cold", "score": round(random.random(), 4)})
    qmap = calibrate_mondrian(rows, alpha=0.1, min_calib=50)
    assert "_marginal" in qmap and math.isfinite(qmap["_marginal"])
    assert math.isfinite(qmap["hot"]) and qmap["hot"] <= 0.4 + 1e-9   # own (tighter) q_hat
    assert qmap["cold"] == qmap["_marginal"]                          # thin → parent fallback
    print(f"[3] calibrate_mondrian OK  hot={qmap['hot']:.4f}  cold(=marginal)={qmap['cold']:.4f}")

    # 4) pessimistic_lower: pred - q_hat; uncalibrated (inf) → -inf (anti-Goodhart default).
    assert abs(pessimistic_lower(0.7, q90) - (0.7 - q90)) < 1e-12
    assert pessimistic_lower(0.7, INF) == -INF
    print(f"[4] pessimistic_lower OK  lb(0.7)={pessimistic_lower(0.7, q90):.4f}  lb(uncalibrated)=-inf")

    # 5) calib_rows: build schema rows (with sample counts) + verify they serialise via to_row().
    ncounts = {"hot": 300, "cold": 5, "_marginal": 305}
    crows = calib_rows("tenant_demo", "judge", qmap, alpha=0.1, ncounts=ncounts)
    assert len(crows) == len(qmap)
    by_bucket = {r.bucket: r for r in crows}
    assert "all" in by_bucket and by_bucket["all"].n_calib == 305    # '_marginal' persisted as 'all'
    assert by_bucket["hot"].model_key == "judge" and by_bucket["hot"].n_calib == 300
    sample_row = by_bucket["hot"].to_row()
    assert sample_row["model_key"] == "judge" and "q_hat" in sample_row
    print(f"[5] calib_rows OK  {len(crows)} rows; sample to_row()={sample_row}")

    print("\nALL conformal.py self-checks passed (pure-python, no deps).")
