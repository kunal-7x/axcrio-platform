"""voice_ops.flywheel.simulator — B5: the CALLER SIMULATOR / world model (filter-only).

THE WHY.  Promoting a challenger policy on logged data alone is expensive and slow — the
real harness (shadow traffic, OPE, anytime-valid tests) costs live calls and human review.
But most challengers are obviously bad: they fold on a price objection, they steamroll a
cold lead into an opt-out, they monologue at a skeptic.  We can catch those *before* the
expensive harness by letting a cross-family model ROLE-PLAY the caller and watching the
challenger fail in simulation.  That is the entire job of this module: a cheap, advisory
FILTER (gate STEP 0) that PROPOSES and REMOVES challengers — it NEVER promotes one.

THE SCIENCE (user-simulator + self-play literature, and the guardrails that keep it honest):

  * GROUNDED USER SIMULATORS, not free fantasy.  Task-oriented dialogue research (and more
    recently SOTOPIA / social self-play, SPIN, and the agenda-based user-simulator line)
    shows a caller world-model is only useful if it is CONDITIONED ON REAL DISTRIBUTIONS.
    So we MINE archetypes from logged calls (objection histogram + affect-trajectory
    template + temperament read + the real booked/lost outcome) and the simulated caller
    role-plays a *real* archetype, not a generic "interested buyer".

  * THE ONE PLACE A TUNED MODEL IS LEGIT — but it is the CALLER, never the policy.  Riya
    (the live agent) is frozen and must stay frozen.  The simulator tunes/conditions the
    *opponent*; a fine-tuned model may only ever ship as a self-hosted shadow CHALLENGER
    behind the human gate (B7), and even there the sim is filter-only.  We use a
    CROSS-FAMILY OpenRouter model (cfg.judge_model) to role-play the caller so the policy's
    own family can't quietly collude with its evaluator.

  * COVERAGE ANTI-GOODHART.  A sim that only role-plays warm, agreeable buyers makes every
    challenger look great — and teaches the flywheel to optimize for the easy cases.  So we
    UP-WEIGHT the hard archetypes (cold + skeptic + price objection + early hangup): the
    coverage weight is the anti-Goodhart guard.  A challenger that wins only by abandoning
    the hard archetypes is NOT a win.

  * HONESTY GATE — THE SIM POLICES ITSELF.  A world model is only trustworthy if its
    simulated outcomes match reality.  `calibration_scorecard` computes the sim's ECE
    against real outcomes; when ECE exceeds cfg.sim_usi_ece_max the caller SELF-DISABLES the
    sim rather than feed the flywheel hallucinated lift.  USI (user-simulator
    informativeness) tracks whether the sim actually discriminates good policies from bad —
    a sim that says "everyone wins" is uninformative even when calibrated.

  * SYNTHETIC NEGATIVES ARE HYPOTHESES, NOT GROUND TRUTH.  `synth_hard_negatives` mints
    PreferencePairs with source='sim_self_play' and LOW confidence so KTO/DPO training
    down-weights them relative to real outcome-anchored rows, and a synthetic 'chosen' that
    fails the compliance check is never exported as desirable.

DESIGN LAWS (mirror voice_ops/research/*.py + the rest of voice_ops/flywheel):
  * Pure-python at import; the ONLY heavy dep is numpy (k-means), imported LAZILY inside the
    function with a pure-python k-means fallback so the module imports + serves dormant when
    numpy is absent.  httpx is lazy too (reused judge.py shape).
  * DORMANT-SAFE / BEST-EFFORT: not cfg.simulator_active() (no flag / no key / no CH) or any
    error -> a clean empty value ([] / {}); NOTHING raises into a caller.
  * SIDE-PIPELINE: offline / worker only — never on the live LiveKit turn loop.
  * FILTER-ONLY: this module PROPOSES (synth pairs, pre-eval verdicts) and REMOVES (flags a
    challenger for rejection); it NEVER promotes.  Promotion is the human-gated path only.
  * COMPLIANCE IS A HARD GATE elsewhere; here it only screens a synthetic 'chosen' from
    being exported as desirable — it is never a reward term.
"""
from __future__ import annotations

import json
import logging
import math
import os
import random
import re
from typing import Dict, List, Optional, Tuple

try:  # package-relative (the real import path); falls back below for `python3 simulator.py`
    from . import config as _cfg
    from . import schema as S
    from . import store as _st
except ImportError:  # pragma: no cover — direct-file self-check convenience only
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
    from voice_ops.flywheel import config as _cfg  # type: ignore
    from voice_ops.flywheel import schema as S  # type: ignore
    from voice_ops.flywheel import store as _st  # type: ignore

logger = logging.getLogger("flywheel.simulator")

# OpenRouter OpenAI-compatible chat-completions endpoint (lazy httpx POST) — same shape as
# judge.py so the cross-family caller role-play reuses one client contract.
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_REFERER = os.getenv("OPENROUTER_REFERER", "https://haptica.famit.in")
_TITLE = "Haptica Flywheel Caller Simulator"

# The sim outcome vocabulary — a compressed map of the REWARD_TABLE terminals the caller
# role-play can reach, so a sim outcome lines up with a real reward scalar.
_SIM_OUTCOMES = (
    "site_visit_booked", "callback_scheduled", "lead_warm", "lead_cold",
    "not_interested", "hangup", "whatsapp_opted_out",
)
# Outcome -> bounded sim reward (mirrors reward.REWARD_TABLE direction; kept local so the
# sim never imports a live-turn dependency and stays self-contained / dormant-safe).
_SIM_REWARD = {
    "site_visit_booked": 1.0,
    "callback_scheduled": 0.3,
    "lead_warm": 0.1,
    "lead_cold": -0.1,
    "not_interested": -0.4,
    "hangup": -0.3,
    "whatsapp_opted_out": -1.0,
}
# A sim outcome is "positive" (a booking-ish win) iff its reward clears this — mirrors the
# trajectory convention (reward_capped > 0.5 ⇒ booked).
_POSITIVE_THRESHOLD = 0.5

# Temperaments the caller role-play can embody (read from caller_text lexical cues).
_TEMPERAMENTS = ("skeptic", "rushed", "polite", "warm", "hostile", "neutral")

# Hard-archetype signature — the coverage anti-Goodhart up-weight target.
_HARD_OBJECTIONS = {"price", "loan", "not_interested"}
_HARD_TEMPERAMENTS = {"skeptic", "hostile", "rushed"}


# --------------------------------------------------------------------------- #
# Small total helpers (none raise).
# --------------------------------------------------------------------------- #
def _f(v, d: float = 0.0) -> float:
    try:
        x = float(v)
        return d if x != x else x  # NaN guard
    except Exception:  # noqa: BLE001
        return d


def _clamp(v: float, lo: float, hi: float) -> float:
    x = _f(v, lo)
    return lo if x < lo else hi if x > hi else x


def _safe_load(blob, default):
    """Tolerant json.loads — accept a dict/list already-parsed, a JSON string, or junk."""
    if isinstance(blob, (dict, list)):
        return blob
    if not blob:
        return default
    try:
        return json.loads(blob)
    except Exception:  # noqa: BLE001
        return default


# --------------------------------------------------------------------------- #
# Tolerant JSON extraction — LLMs wrap JSON in prose / fences (reused judge.py shape).
# --------------------------------------------------------------------------- #
def _extract_json(text: str) -> Optional[dict]:
    """Best-effort: parse the first balanced {...} object out of an LLM reply. None on miss."""
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001
        pass
    start = s.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(s)):
            c = s[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = s[start:i + 1]
                    try:
                        return json.loads(candidate)
                    except Exception:  # noqa: BLE001
                        break
        start = s.find("{", start + 1)
    return None


# --------------------------------------------------------------------------- #
# OpenRouter call — the single lazy-httpx network hop (reused judge.py shape).
# --------------------------------------------------------------------------- #
def _chat(messages: List[dict], *, model: str, cfg, temperature: float = 0.7,
          max_tokens: int = 220) -> Optional[str]:
    """POST a chat-completion to OpenRouter. Returns content str, or None on any failure
    (no key / no httpx / HTTP error / malformed body). NEVER raises.

    The caller role-play wants a LITTLE temperature (it must improvise objections / go cold),
    unlike the judge which runs at temp 0 — but the model is still cross-family (never the
    live Cerebras/Groq arm)."""
    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        return None
    try:
        mdl = (model or "").strip() or (getattr(cfg, "judge_model", "") or "anthropic/claude-3.5-sonnet").strip()
        import httpx  # lazy — an absent dep degrades to dormant, never an import-time crash
        headers = {
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "HTTP-Referer": _REFERER,
            "X-Title": _TITLE,
        }
        payload = {
            "model": mdl,
            "messages": messages,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
        }
        timeout = float(os.getenv("FLYWHEEL_SIM_TIMEOUT", os.getenv("FLYWHEEL_TIMEOUT", "20")))
        r = httpx.post(_OPENROUTER_URL, headers=headers, json=payload, timeout=timeout)
        if r.status_code >= 400:
            logger.warning("simulator openrouter HTTP %s: %s", r.status_code, (r.text or "")[:200])
            return None
        body = r.json()
        choices = body.get("choices") or []
        if not choices:
            return None
        msg = (choices[0] or {}).get("message") or {}
        content = msg.get("content")
        if isinstance(content, list):
            content = "".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
        return str(content or "") or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("simulator openrouter call error (non-fatal): %r", exc)
        return None


def _resolved_model(model: str, cfg) -> str:
    return (model or "").strip() or (getattr(cfg, "judge_model", "") or "anthropic/claude-3.5-sonnet").strip()


# --------------------------------------------------------------------------- #
# Temperament read — a cheap lexical classifier over the caller's own words (no audio).
# --------------------------------------------------------------------------- #
_TEMPERAMENT_CUES = {
    "skeptic": ("scam", "fake", "jhooth", "bharosa", "trust", "proof", "guarantee", "sach", "verify"),
    "rushed": ("busy", "jaldi", "time nahi", "no time", "later", "baad mein", "meeting", "abhi nahi"),
    "hostile": ("disturb", "mat karo", "band karo", "stop", "remove", "complaint", "irritate", "pareshan"),
    "polite": ("thank", "dhanyavaad", "shukriya", "please", "kripya", "sorry", "thik hai"),
    "warm": ("interested", "achha", "good", "tell me more", "batao", "haan", "yes", "kab"),
}


def _temperament_of(caller_texts: List[str]) -> str:
    """Read a coarse temperament from the caller's own lines (lexical, total, never raises)."""
    try:
        blob = " ".join(str(t or "") for t in caller_texts).lower()
        if not blob.strip():
            return "neutral"
        scores: Dict[str, int] = {}
        for temper, cues in _TEMPERAMENT_CUES.items():
            scores[temper] = sum(1 for c in cues if c in blob)
        best = max(scores, key=lambda k: scores[k])
        return best if scores[best] > 0 else "neutral"
    except Exception:  # noqa: BLE001
        return "neutral"


def _hardness_weight(objection_hist: Dict[str, float], temperament: str,
                     affect_template: Dict[str, float], base_book_rate: float) -> float:
    """Coverage anti-Goodhart up-weight for HARD archetypes (cold + skeptic + price + early
    hangup). A hard, low-converting archetype gets MORE weight so a challenger cannot win the
    pre-eval by quietly abandoning the cases that matter. Returns a weight in [1.0, ~3.0]."""
    w = 1.0
    try:
        hist = objection_hist or {}
        # price/loan/not-interested mass ⇒ harder objection mix
        hard_mass = sum(_f(hist.get(o, 0.0)) for o in _HARD_OBJECTIONS)
        total_mass = sum(_f(v) for v in hist.values()) or 1.0
        w += 0.8 * _clamp(hard_mass / total_mass, 0.0, 1.0)
        if (temperament or "") in _HARD_TEMPERAMENTS:
            w += 0.6
        # cold/early-hangup signal: a low base book rate is the hardest cohort
        if _f(base_book_rate, 0.0) < 0.10:
            w += 0.5
        # rising-friction / early-drop affect template ⇒ early hangup risk
        tmpl = affect_template or {}
        if _f(tmpl.get("friction_end")) - _f(tmpl.get("friction_start")) > 12.0:
            w += 0.3
        if _f(tmpl.get("early_hangup_rate")) > 0.2:
            w += 0.3
    except Exception:  # noqa: BLE001
        return 1.0
    return round(_clamp(w, 1.0, 3.0), 3)


# --------------------------------------------------------------------------- #
# Pure-python k-means (lazy-numpy accelerated when present) — clusters real calls.
# --------------------------------------------------------------------------- #
def _kmeans(vectors: List[List[float]], k: int, *, iters: int = 25, seed: int = 13) -> List[int]:
    """Cluster `vectors` into <=k groups; return a label per row. Tries numpy for speed but
    falls back to a pure-python Lloyd's iteration so the module needs no heavy dep. Total &
    deterministic (fixed seed). Returns all-zeros on degenerate input."""
    n = len(vectors)
    if n == 0:
        return []
    k = max(1, min(int(k), n))
    if k == 1:
        return [0] * n
    # --- lazy numpy fast path (behind the feature flag's intent: heavy dep only when present)
    try:
        import numpy as np  # lazy — pure-python fallback below when absent
        X = np.asarray(vectors, dtype=float)
        rng = np.random.default_rng(seed)
        # k-means++-lite: random distinct seeds
        idx = rng.choice(n, size=k, replace=False)
        cents = X[idx].copy()
        labels = np.zeros(n, dtype=int)
        for _ in range(iters):
            d = ((X[:, None, :] - cents[None, :, :]) ** 2).sum(axis=2)
            new = d.argmin(axis=1)
            if np.array_equal(new, labels) and _ > 0:
                labels = new
                break
            labels = new
            for j in range(k):
                m = labels == j
                if m.any():
                    cents[j] = X[m].mean(axis=0)
        return [int(x) for x in labels.tolist()]
    except Exception:  # noqa: BLE001
        pass
    # --- pure-python Lloyd's iteration (no numpy required) ----------------- #
    try:
        rnd = random.Random(seed)
        dim = len(vectors[0])
        seeds = rnd.sample(range(n), k)
        cents = [list(vectors[s]) for s in seeds]
        labels = [0] * n

        def _d2(a, b):
            return sum((a[i] - b[i]) ** 2 for i in range(min(len(a), len(b))))

        for _ in range(iters):
            changed = False
            for i, v in enumerate(vectors):
                best_j, best_d = 0, float("inf")
                for j, c in enumerate(cents):
                    dd = _d2(v, c)
                    if dd < best_d:
                        best_d, best_j = dd, j
                if labels[i] != best_j:
                    changed = True
                labels[i] = best_j
            # recompute centroids
            sums = [[0.0] * dim for _ in range(k)]
            counts = [0] * k
            for i, v in enumerate(vectors):
                j = labels[i]
                counts[j] += 1
                for d in range(dim):
                    sums[j][d] += v[d] if d < len(v) else 0.0
            for j in range(k):
                if counts[j]:
                    cents[j] = [sums[j][d] / counts[j] for d in range(dim)]
            if not changed:
                break
        return labels
    except Exception as exc:  # noqa: BLE001
        logger.warning("simulator kmeans fallback error (non-fatal): %r", exc)
        return [0] * n


def _feature_vector(call: dict) -> List[float]:
    """Build the clustering feature vector for one call: [objection histogram over the closed
    OBJECTION_TYPES vocab, affect-trajectory template (friction start/end, arousal),
    temperament one-hot-ish, real outcome (booked?)]. Total; never raises."""
    try:
        hist = _safe_load(call.get("objection_hist") or call.get("objection_hist_json"), {}) or {}
        vec: List[float] = []
        # objection histogram (normalized) over the closed vocab
        total = sum(_f(v) for v in hist.values()) or 1.0
        for obj in S.OBJECTION_TYPES:
            vec.append(_f(hist.get(obj, 0.0)) / total)
        # affect-trajectory template
        vec.append(_f(call.get("friction_start"), 50.0) / 100.0)
        vec.append(_f(call.get("friction_end"), 50.0) / 100.0)
        vec.append(_f(call.get("arousal_mean"), 50.0) / 100.0)
        vec.append(_clamp(_f(call.get("early_hangup_rate")), 0.0, 1.0))
        # temperament one-hot
        temper = str(call.get("temperament") or "neutral")
        for t in _TEMPERAMENTS:
            vec.append(1.0 if t == temper else 0.0)
        # real outcome (booked?) — anchor the cluster to ground truth
        vec.append(1.0 if _truthy(call.get("booked")) else 0.0)
        return vec
    except Exception:  # noqa: BLE001
        return [0.0] * (len(S.OBJECTION_TYPES) + 4 + len(_TEMPERAMENTS) + 1)


def _truthy(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "booked", "site_visit_booked")
    try:
        return bool(v) and float(v) > 0.5
    except Exception:  # noqa: BLE001
        return bool(v)


# --------------------------------------------------------------------------- #
# _fetch_call_summaries — pull per-call rollups from flywheel_trajectories (best-effort).
# --------------------------------------------------------------------------- #
async def _fetch_call_summaries(tenant_id: str, minutes: int = 43200, limit: int = 5000) -> List[dict]:
    """Aggregate logged turns into per-call summaries (objection histogram, affect template,
    temperament, outcome). Returns [] on any error / when the store is unconfigured. The
    caller_text concatenation drives the temperament read. NEVER raises."""
    try:
        res = await _st._ch(
            f"SELECT call_id, "
            f"groupArray(objection_type) AS objs, "
            f"min(state_friction) AS friction_start, max(state_friction) AS friction_end, "
            f"avg(state_arousal) AS arousal_mean, "
            f"max(reward_capped) AS max_reward, "
            f"groupArray(caller_text) AS caller_texts, "
            f"count() AS turns "
            f"FROM {_st._final(_st.TRAJECTORIES)} "
            f"WHERE tenant_id = {{tid:String}} AND ts > now() - INTERVAL {{m:UInt32}} MINUTE "
            f"GROUP BY call_id LIMIT {int(limit)}",
            {"tid": tenant_id, "m": int(minutes)},
        )
        rows = res.get("rows") or []
        out: List[dict] = []
        for r in rows:
            objs = r.get("objs") or []
            hist: Dict[str, int] = {}
            for o in objs:
                o = str(o or "none")
                if o and o != "none":
                    hist[o] = hist.get(o, 0) + 1
            caller_texts = r.get("caller_texts") or []
            out.append({
                "call_id": r.get("call_id", ""),
                "objection_hist": hist,
                "friction_start": _f(r.get("friction_start"), 50.0),
                "friction_end": _f(r.get("friction_end"), 50.0),
                "arousal_mean": _f(r.get("arousal_mean"), 50.0),
                "early_hangup_rate": 1.0 if (_f(r.get("turns"), 0) <= 2 and _f(r.get("max_reward")) <= 0) else 0.0,
                "temperament": _temperament_of([str(t) for t in caller_texts]),
                "booked": _f(r.get("max_reward")) > _POSITIVE_THRESHOLD,
            })
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("simulator _fetch_call_summaries error (non-fatal): %r", exc)
        return []


# --------------------------------------------------------------------------- #
# mine_archetypes — cluster real calls into <= sim_max_archetypes; up-weight the hard ones.
# --------------------------------------------------------------------------- #
async def mine_archetypes(tenant_id: str, *, cfg=None) -> list:
    """Cluster logged calls into <= cfg.sim_max_archetypes caller archetypes and persist them.

    Each archetype carries an objection histogram, an affect-trajectory template, a
    temperament, the real base book rate, and a COVERAGE weight that UP-WEIGHTS hard
    archetypes (cold + skeptic + price + early hangup) — the anti-Goodhart guard so the sim
    can't be gamed by abandoning the hard cases. Persists via _st.insert_archetypes and
    returns the list of schema.ArchetypeRow.

    DORMANT-SAFE: not cfg.simulator_active() / no data / any error -> []. NEVER raises.
    """
    try:
        cfg = cfg or _cfg.load()
        if not cfg.simulator_active():
            return []
        calls = await _fetch_call_summaries(tenant_id)
        if not calls:
            return []
        k = max(1, min(int(getattr(cfg, "sim_max_archetypes", 12) or 12), len(calls)))
        vectors = [_feature_vector(c) for c in calls]
        labels = _kmeans(vectors, k)
        if not labels:
            return []

        ts = S.now_iso()
        groups: Dict[int, List[dict]] = {}
        for c, lbl in zip(calls, labels):
            groups.setdefault(int(lbl), []).append(c)

        archetypes: List = []
        for lbl, members in sorted(groups.items()):
            n = len(members)
            if n == 0:
                continue
            # aggregate the cluster's objection histogram
            hist: Dict[str, float] = {}
            for m in members:
                for obj, cnt in (m.get("objection_hist") or {}).items():
                    hist[obj] = hist.get(obj, 0.0) + _f(cnt)
            # affect template
            fr_start = sum(_f(m.get("friction_start"), 50.0) for m in members) / n
            fr_end = sum(_f(m.get("friction_end"), 50.0) for m in members) / n
            arousal = sum(_f(m.get("arousal_mean"), 50.0) for m in members) / n
            early_hangup = sum(1.0 for m in members if _f(m.get("early_hangup_rate")) > 0) / n
            affect_template = {
                "friction_start": round(fr_start, 2),
                "friction_end": round(fr_end, 2),
                "arousal_mean": round(arousal, 2),
                "early_hangup_rate": round(early_hangup, 3),
            }
            # dominant temperament in the cluster
            temper_counts: Dict[str, int] = {}
            for m in members:
                t = str(m.get("temperament") or "neutral")
                temper_counts[t] = temper_counts.get(t, 0) + 1
            temperament = max(temper_counts, key=lambda kk: temper_counts[kk]) if temper_counts else "neutral"
            # real base book rate (ground-truth anchor)
            booked = sum(1.0 for m in members if _truthy(m.get("booked")))
            base_rate = round(booked / n, 4)
            # dominant objection ⇒ a human-readable label
            dom_obj = max(hist, key=lambda kk: hist[kk]) if hist else "none"
            label = f"{temperament}/{dom_obj}"
            weight = _hardness_weight(hist, temperament, affect_template, base_rate)

            archetypes.append(S.ArchetypeRow(
                tenant_id=tenant_id,
                archetype_id=S.digest_id(tenant_id, "arc", label, lbl),
                ts_iso=ts,
                label=label[:80],
                objection_hist_json=json.dumps(hist, ensure_ascii=False),
                affect_template_json=json.dumps(affect_template, ensure_ascii=False),
                temperament=temperament,
                base_book_rate=base_rate,
                weight=weight,
                n_calls=n,
            ))

        # best-effort persist (no-op when the store is dormant)
        try:
            _st.insert_archetypes(archetypes)
        except Exception as exc:  # noqa: BLE001
            logger.warning("simulator insert_archetypes error (non-fatal): %r", exc)
        return archetypes
    except Exception as exc:  # noqa: BLE001
        logger.warning("simulator mine_archetypes error (non-fatal): %r", exc)
        return []


# --------------------------------------------------------------------------- #
# simulate_call — a cross-family model ROLE-PLAYS the caller; the agent policy replies.
# --------------------------------------------------------------------------- #
def _archetype_get(archetype: dict, key: str, default=None):
    """Read a field from an archetype dict OR a schema.ArchetypeRow-like object."""
    if isinstance(archetype, dict):
        return archetype.get(key, default)
    return getattr(archetype, key, default)


def _caller_system_prompt(archetype: dict) -> str:
    """Construct the caller role-play system prompt from a mined archetype."""
    temperament = str(_archetype_get(archetype, "temperament", "neutral") or "neutral")
    label = str(_archetype_get(archetype, "label", "") or "")
    hist = _safe_load(_archetype_get(archetype, "objection_hist_json")
                      or _archetype_get(archetype, "objection_hist"), {}) or {}
    objs = ", ".join(sorted(hist, key=lambda kk: -_f(hist[kk]))[:4]) or "price, trust"
    affect = _safe_load(_archetype_get(archetype, "affect_template_json")
                        or _archetype_get(archetype, "affect_template"), {}) or {}
    rising = _f(affect.get("friction_end")) - _f(affect.get("friction_start")) > 8.0
    return (
        "You are role-playing the CALLER (a prospective real-estate buyer in India) who has "
        "received an unsolicited outbound sales call. You are NOT the agent. Stay in character "
        f"as this caller archetype: temperament='{temperament}', profile='{label}'. Your main "
        f"objections/concerns are: {objs}. "
        + ("You tend to get more irritated as the call goes on. " if rising else "")
        + "You are EXPLICITLY ALLOWED and EXPECTED to: object, push back, ask hard questions, "
        "go cold, lose patience, hang up, or ask to be removed / opt out of WhatsApp if the "
        "agent is pushy, dishonest, or wastes your time. Reply in natural Hinglish, ONE short "
        "caller turn at a time (1-2 sentences). Do not narrate; just speak as the caller. "
        "If you decide to end the call, end your line with the token <STOP>."
    )


def _classify_sim_outcome(transcript: List[Tuple[str, str]], stopped: bool, archetype: dict) -> str:
    """Classify the sim outcome from the role-play transcript (lexical, total, never raises)."""
    try:
        caller_blob = " ".join(t for role, t in transcript if role == "caller").lower()
        # opt-out / removal is the worst terminal — check first
        if any(w in caller_blob for w in ("remove", "opt out", "opt-out", "band karo", "mat karo", "stop calling", "do not call")):
            return "whatsapp_opted_out"
        if any(w in caller_blob for w in ("book", "site visit", "visit kar", "aa jaunga", "aaunga", "haan chalo", "schedule")):
            return "site_visit_booked"
        if any(w in caller_blob for w in ("callback", "call me later", "baad mein call", "kal call", "phir baat")):
            return "callback_scheduled"
        if any(w in caller_blob for w in ("not interested", "nahi chahiye", "interest nahi", "mat bhejo")):
            return "not_interested"
        if stopped:
            return "hangup"
        # affect-template fallback: a cold archetype that didn't convert stays cold
        base = _f(_archetype_get(archetype, "base_book_rate"), 0.0)
        return "lead_warm" if base >= 0.15 else "lead_cold"
    except Exception:  # noqa: BLE001
        return "lead_cold"


def simulate_call(archetype: dict, agent_policy: dict, *, k: int = 1, model: str = "", cfg=None) -> list:
    """Run k scripted role-play rollouts: a CROSS-FAMILY OpenRouter model role-plays the
    caller (conditioned on the archetype's intent + affect template, explicitly allowed to
    object/go-cold/hang-up/opt-out), while agent_policy supplies the agent prompt/rebuttals.

    The agent side is driven from agent_policy (its system prompt + a small rebuttal library)
    via the SAME cross-family judge_model — we NEVER call the live Cerebras/Groq arm here, so
    the simulation can never leak the production policy into its own evaluation. Each rollout
    is classified into a sim outcome and returned as a schema.SimRolloutRow.

    DORMANT-SAFE: not cfg.simulator_active() / no key / no dep / any error -> []. NEVER raises.
    """
    try:
        cfg = cfg or _cfg.load()
        if not cfg.simulator_active():
            return []
        mdl = _resolved_model(model, cfg)
        tenant_id = str(_archetype_get(archetype, "tenant_id", "") or (agent_policy or {}).get("tenant_id", ""))
        archetype_id = str(_archetype_get(archetype, "archetype_id", "") or "")
        policy_label = str((agent_policy or {}).get("label")
                           or (agent_policy or {}).get("policy_label")
                           or (agent_policy or {}).get("challenger_id") or "champion")
        challenger_id = str((agent_policy or {}).get("challenger_id", ""))
        max_turns = max(2, int(os.getenv("FLYWHEEL_SIM_MAX_TURNS", "6")))

        agent_sys = str((agent_policy or {}).get("system_prompt")
                        or (agent_policy or {}).get("prompt")
                        or "You are Riya, a warm, honest Hinglish real-estate telecaller. Be concise, "
                           "address objections truthfully, never use false urgency, and honor any "
                           "opt-out immediately.")
        rebuttals = (agent_policy or {}).get("rebuttals") or {}

        caller_sys = _caller_system_prompt(archetype)
        ts = S.now_iso()
        rollouts: List = []
        n_roll = max(1, int(k or 1))

        for _ in range(n_roll):
            transcript: List[Tuple[str, str]] = []
            caller_msgs = [{"role": "system", "content": caller_sys},
                           {"role": "user", "content": "The call has just connected. Say your first line as the caller."}]
            stopped = False
            agent_text = ""
            for turn in range(max_turns):
                caller_reply = _chat(caller_msgs, model=mdl, cfg=cfg, temperature=0.8) or ""
                caller_clean = caller_reply.replace("<STOP>", "").strip()
                if caller_clean:
                    transcript.append(("caller", caller_clean))
                if "<STOP>" in caller_reply or not caller_clean:
                    stopped = True
                    break
                # --- agent turn: cross-family role-play of the policy (NEVER the live arm) ---
                obj_hint = _detect_objection(caller_clean)
                rebuttal_hint = str(rebuttals.get(obj_hint, "")) if isinstance(rebuttals, dict) else ""
                agent_user = (
                    f"The caller just said: \"{caller_clean[:400]}\"\n"
                    + (f"(A vetted rebuttal you may adapt: {rebuttal_hint[:300]})\n" if rebuttal_hint else "")
                    + "Reply as Riya in ONE short Hinglish turn (1-2 sentences)."
                )
                agent_text = _chat(
                    [{"role": "system", "content": agent_sys},
                     {"role": "user", "content": agent_user}],
                    model=mdl, cfg=cfg, temperature=0.5,
                ) or ""
                if agent_text.strip():
                    transcript.append(("agent", agent_text.strip()))
                    caller_msgs.append({"role": "assistant", "content": "(I, the caller, said the prior line.)"})
                    caller_msgs.append({"role": "user", "content": f"The agent replied: \"{agent_text.strip()[:400]}\". Respond as the caller."})
                else:
                    # the agent role-play failed (dormant / error) — abort this rollout cleanly
                    break

            outcome = _classify_sim_outcome(transcript, stopped, archetype)
            sim_reward = _SIM_REWARD.get(outcome, -0.1)
            usi = _rollout_usi(transcript)
            rollouts.append(S.SimRolloutRow(
                tenant_id=tenant_id,
                ts_iso=ts,
                archetype_id=archetype_id,
                challenger_id=challenger_id,
                policy_label=policy_label[:80],
                sim_outcome=outcome,
                sim_reward=round(sim_reward, 4),
                turns=len([1 for r, _t in transcript if r == "agent"]),
                usi=usi,
                ece=1.0,  # per-rollout ece unknown until calibration_scorecard runs; conservative
                notes=(f"objection={_dominant_objection(archetype)}; stopped={stopped}")[:400],
            ))
        return rollouts
    except Exception as exc:  # noqa: BLE001
        logger.warning("simulator simulate_call error (non-fatal): %r", exc)
        return []


_OBJECTION_CUES = {
    "price": ("mehnga", "expensive", "costly", "budget", "price", "daam", "paisa", "afford"),
    "loan": ("loan", "emi", "finance", "down payment", "interest rate", "bank"),
    "location": ("location", "far", "door", "area", "connectivity", "metro"),
    "timing": ("busy", "time", "later", "baad", "abhi nahi"),
    "trust": ("scam", "fake", "trust", "bharosa", "proof", "sach", "verify"),
    "possession": ("possession", "ready", "kab milega", "delay", "construction"),
    "not_interested": ("not interested", "nahi chahiye", "interest nahi", "mat"),
}


def _detect_objection(caller_text: str) -> str:
    low = (caller_text or "").lower()
    for obj, cues in _OBJECTION_CUES.items():
        if any(c in low for c in cues):
            return obj
    return "none"


def _dominant_objection(archetype: dict) -> str:
    hist = _safe_load(_archetype_get(archetype, "objection_hist_json")
                      or _archetype_get(archetype, "objection_hist"), {}) or {}
    return max(hist, key=lambda kk: _f(hist[kk])) if hist else "none"


def _rollout_usi(transcript: List[Tuple[str, str]]) -> float:
    """User-simulator informativeness proxy for one rollout: did the caller actually exercise
    distinct behaviours (objections / affect shifts) rather than rubber-stamp the agent?
    Pure-python, in [0, 1]. A flat, agreeable caller scores low (uninformative)."""
    try:
        caller_lines = [t for r, t in transcript if r == "caller"]
        if not caller_lines:
            return 0.0
        objs = set()
        for line in caller_lines:
            obj = _detect_objection(line)
            if obj != "none":
                objs.add(obj)
        distinct = len(objs)
        # informativeness: distinct objection coverage (a flat agreeable caller scores ~0).
        return round(_clamp(distinct / 3.0, 0.0, 1.0), 4)
    except Exception:  # noqa: BLE001
        return 0.0


# --------------------------------------------------------------------------- #
# preeval_challenger — gate STEP 0: challenger vs champion across archetypes (advisory).
# --------------------------------------------------------------------------- #
def preeval_challenger(challenger, archetypes: list, *, cfg=None) -> dict:
    """Run the challenger policy vs the champion across the mined archetypes and return a
    cheap, ADVISORY pre-eval scorecard. This is gate STEP 0 — a coverage-weighted FILTER run
    BEFORE the expensive OPE / shadow harness. FILTER-ONLY: it can flag a challenger to remove
    but never promotes one.

    Returns {'sim_reward_lift':float, 'per_archetype':[...], 'usi':float, 'ece':float}. The
    lift is COVERAGE-WEIGHTED (hard archetypes count more) so a challenger can't win by
    abandoning the hard cases.

    DORMANT-SAFE: not cfg.simulator_active() / no archetypes / any error -> a zero scorecard
    {'sim_reward_lift':0.0,'per_archetype':[],'usi':0.0,'ece':1.0}. NEVER raises.
    """
    zero = {"sim_reward_lift": 0.0, "per_archetype": [], "usi": 0.0, "ece": 1.0}
    try:
        cfg = cfg or _cfg.load()
        if not cfg.simulator_active() or not archetypes:
            return dict(zero)

        # Resolve the two policies. The challenger may be a Challenger dataclass or a dict.
        chal_policy = _policy_from_challenger(challenger)
        champ_policy = {"label": "champion", "system_prompt":
                        "You are Riya, the current CHAMPION Hinglish real-estate telecaller. "
                        "Be concise, truthful, never pushy, honor opt-outs."}

        k = max(1, int(getattr(cfg, "sim_k_rollouts", 4) or 4))
        per_archetype: List[dict] = []
        weighted_lift_num = 0.0
        weight_den = 0.0
        usi_vals: List[float] = []

        for arc in archetypes:
            weight = _f(_archetype_get(arc, "weight", 1.0), 1.0)
            chal_rolls = simulate_call(arc, chal_policy, k=k, cfg=cfg)
            champ_rolls = simulate_call(arc, champ_policy, k=k, cfg=cfg)
            chal_mean = _mean_reward(chal_rolls)
            champ_mean = _mean_reward(champ_rolls)
            lift = chal_mean - champ_mean
            arc_usi = _mean_usi(chal_rolls + champ_rolls)
            usi_vals.append(arc_usi)
            per_archetype.append({
                "archetype_id": str(_archetype_get(arc, "archetype_id", "") or ""),
                "label": str(_archetype_get(arc, "label", "") or ""),
                "weight": round(weight, 3),
                "challenger_reward": round(chal_mean, 4),
                "champion_reward": round(champ_mean, 4),
                "lift": round(lift, 4),
                "n_rollouts": len(chal_rolls) + len(champ_rolls),
            })
            weighted_lift_num += weight * lift
            weight_den += weight

        sim_reward_lift = round(weighted_lift_num / weight_den, 4) if weight_den > 0 else 0.0
        usi = round(sum(usi_vals) / len(usi_vals), 4) if usi_vals else 0.0
        # ECE here is unknown without real outcomes to compare against → conservative 1.0
        # (calibration_scorecard supplies the real number; until then the harness treats the
        # sim as un-trusted, which is the honest default).
        return {
            "sim_reward_lift": sim_reward_lift,
            "per_archetype": per_archetype,
            "usi": usi,
            "ece": 1.0,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("simulator preeval_challenger error (non-fatal): %r", exc)
        return dict(zero)


def _policy_from_challenger(challenger) -> dict:
    """Coerce a Challenger dataclass / dict into the agent_policy shape simulate_call wants."""
    try:
        if isinstance(challenger, dict):
            cid = str(challenger.get("challenger_id", "") or "")
            cfg_json = challenger.get("proposed_config_json")
            label = str(challenger.get("label") or challenger.get("rationale") or cid or "challenger")
        else:
            cid = str(getattr(challenger, "challenger_id", "") or "")
            cfg_json = getattr(challenger, "proposed_config_json", "")
            label = str(getattr(challenger, "rationale", "") or cid or "challenger")
        conf = _safe_load(cfg_json, {}) or {}
        policy = {
            "challenger_id": cid,
            "label": label[:80] or "challenger",
        }
        # carry through a candidate prompt / rebuttal library if the config supplies one
        if isinstance(conf, dict):
            if conf.get("system_prompt") or conf.get("prompt"):
                policy["system_prompt"] = str(conf.get("system_prompt") or conf.get("prompt"))
            if isinstance(conf.get("rebuttals"), dict):
                policy["rebuttals"] = conf["rebuttals"]
        policy.setdefault("system_prompt",
                          "You are Riya, a CHALLENGER Hinglish real-estate telecaller variant. "
                          "Be concise, truthful, never pushy, honor opt-outs.")
        return policy
    except Exception:  # noqa: BLE001
        return {"label": "challenger", "system_prompt": "You are Riya, a real-estate telecaller."}


def _mean_reward(rollouts: list) -> float:
    if not rollouts:
        return 0.0
    vals = [_f(getattr(r, "sim_reward", 0.0)) for r in rollouts]
    return sum(vals) / len(vals) if vals else 0.0


def _mean_usi(rollouts: list) -> float:
    if not rollouts:
        return 0.0
    vals = [_f(getattr(r, "usi", 0.0)) for r in rollouts]
    return sum(vals) / len(vals) if vals else 0.0


# --------------------------------------------------------------------------- #
# synth_hard_negatives — mint LOW-confidence sim_self_play PreferencePairs.
# --------------------------------------------------------------------------- #
# A small bank of compliant 'chosen' rebuttals and matched non-compliant 'rejected' foils,
# keyed by objection — the synthetic contrast a KTO/DPO run learns the boundary from. These
# are HYPOTHESES (low confidence, never outcome-anchored), down-weighted vs real rows.
_NEG_FOILS = {
    "price": (
        "Samajh sakti hoon budget important hai — main aapke range ke options aur EMI plan dono bhej deti hoon, no pressure.",
        "Arre sir aaj hi book kar lo, kal price badh jayega, ye last chance hai!",
    ),
    "loan": (
        "Loan ke liye humare paas bank tie-ups hain, main eligibility check karke realistic EMI bata deti hoon.",
        "Loan 100% guaranteed approve ho jayega, pakka, aap bas token de do abhi.",
    ),
    "trust": (
        "Bilkul, aap RERA number aur site visit se khud verify kar sakte hain — main details share karti hoon.",
        "Trust karo na, sab log le rahe hain, aap akele soch rahe ho, jaldi karo.",
    ),
    "not_interested": (
        "Koi baat nahi, main aapka number list se hata deti hoon — sorry for the disturbance.",
        "Interested nahi? Ek baar sun to lo, main baar baar call karungi jab tak haan na bole.",
    ),
    "possession": (
        "Possession timeline RERA pe registered hai — main exact date aur construction status bhej deti hoon.",
        "Possession kal hi mil jayega definitely, main guarantee deti hoon, tension mat lo.",
    ),
}


def synth_hard_negatives(archetype: dict, *, cfg=None) -> list:
    """Mint schema.PreferencePair rows with source='sim_self_play' from the archetype's hard
    objections: a compliant 'chosen' vs a pushy/dishonest 'rejected' foil.

    The pairs carry LOW confidence (down-weighted vs real outcome-anchored rows) and are NOT
    outcome_anchored — they are hypotheses the moat can learn a boundary from, never ground
    truth. The 'chosen' side is COMPLIANCE-CHECKED (compliance.check_text); if it trips a
    violation it is marked non-compliant so .to_kto_rows() will NOT export it as desirable.

    DORMANT-SAFE: not cfg.simulator_active() / any error -> []. NEVER raises.
    """
    try:
        cfg = cfg or _cfg.load()
        if not cfg.simulator_active():
            return []
        tenant_id = str(_archetype_get(archetype, "tenant_id", "") or "")
        temperament = str(_archetype_get(archetype, "temperament", "neutral") or "neutral")
        affect = _safe_load(_archetype_get(archetype, "affect_template_json")
                            or _archetype_get(archetype, "affect_template"), {}) or {}
        regime = "rising_friction" if (_f(affect.get("friction_end")) - _f(affect.get("friction_start")) > 8.0) else "steady"
        hist = _safe_load(_archetype_get(archetype, "objection_hist_json")
                          or _archetype_get(archetype, "objection_hist"), {}) or {}
        # focus on the archetype's actual hard objections (fallback to price/trust)
        objections = [o for o in sorted(hist, key=lambda kk: -_f(hist[kk])) if o in _NEG_FOILS]
        if not objections:
            objections = ["price", "trust"]

        # lazy import compliance — keep it best-effort; absence must not break minting
        try:
            from . import compliance as _comp
        except Exception:  # noqa: BLE001
            _comp = None

        ts = S.now_iso()
        archetype_id = str(_archetype_get(archetype, "archetype_id", "") or "")
        pairs: List = []
        for obj in objections[:4]:
            chosen, rejected = _NEG_FOILS[obj]
            compliant = True
            if _comp is not None:
                try:
                    compliant = not bool(_comp.check_text(chosen, stance="sales"))
                except Exception:  # noqa: BLE001
                    compliant = True
            pairs.append(S.PreferencePair(
                tenant_id=tenant_id,
                pair_id=S.digest_id(tenant_id, "simneg", archetype_id, obj),
                ts_iso=ts,
                state_embedding_id=S.digest_id(obj, temperament, regime),
                objection_type=obj,
                lead_temperature="cold",
                regime=regime,
                vertical="real_estate",
                chosen_text=chosen,
                rejected_text=rejected,
                chosen_move_id=f"sim:{archetype_id}:{obj}:chosen",
                rejected_move_id=f"sim:{archetype_id}:{obj}:rejected",
                margin=0.2,                  # modest synthetic margin (a hypothesis, not a measured delta)
                source="sim_self_play",
                survived_swap=False,         # never judge-swap-verified — it is synthetic
                confidence=0.25,             # LOW: down-weighted vs real outcome-anchored rows
                compliant=compliant,
                outcome_anchored=False,      # NEVER — a synthetic pair sits on no real call
            ))
        return pairs
    except Exception as exc:  # noqa: BLE001
        logger.warning("simulator synth_hard_negatives error (non-fatal): %r", exc)
        return []


# --------------------------------------------------------------------------- #
# calibration_scorecard — the honesty gate: USI + ECE of sim vs real outcomes.
# --------------------------------------------------------------------------- #
def _to_prob(outcome) -> float:
    """Map a sim/real outcome (label string or numeric reward) to a P(book)-ish score in [0,1]."""
    if isinstance(outcome, (int, float)) and not isinstance(outcome, bool):
        # treat as a reward; squash to [0,1] around the positive threshold
        return _clamp((_f(outcome) + 1.0) / 2.0, 0.0, 1.0)
    s = str(outcome or "").strip().lower()
    if s in _SIM_REWARD:
        return _clamp((_SIM_REWARD[s] + 1.0) / 2.0, 0.0, 1.0)
    if s in ("booked", "1", "true", "yes", "positive"):
        return 1.0
    if s in ("lost", "0", "false", "no", "negative"):
        return 0.0
    return 0.5


def _to_binary(outcome) -> int:
    """Did this outcome count as a booking (the positive class)?"""
    if isinstance(outcome, (int, float)) and not isinstance(outcome, bool):
        return 1 if _f(outcome) > _POSITIVE_THRESHOLD else 0
    s = str(outcome or "").strip().lower()
    if s in _SIM_REWARD:
        return 1 if _SIM_REWARD[s] > _POSITIVE_THRESHOLD else 0
    return 1 if s in ("booked", "site_visit_booked", "1", "true", "yes", "positive") else 0


def calibration_scorecard(sim_outcomes: list, real_outcomes: list) -> dict:
    """Compute the sim's honesty scorecard: {'usi':float, 'ece':float} (pure-python).

    ECE (expected calibration error, 10-bin) compares the sim's predicted P(book) against the
    REAL booking frequency in each confidence bin — the canary that the world model matches
    reality. USI (user-simulator informativeness) is the sim's discriminative spread: a sim
    that predicts the same probability for everyone (no signal) scores ~0 even if its average
    is right. When ece > cfg.sim_usi_ece_max the CALLER self-disables the sim (honesty gate).

    DORMANT-SAFE: empty / mismatched / any error -> {'usi':0.0, 'ece':1.0} (1.0 ECE == treat
    as un-trustworthy). NEVER raises.
    """
    try:
        if not sim_outcomes or not real_outcomes:
            return {"usi": 0.0, "ece": 1.0}
        n = min(len(sim_outcomes), len(real_outcomes))
        if n == 0:
            return {"usi": 0.0, "ece": 1.0}
        sim_p = [_to_prob(sim_outcomes[i]) for i in range(n)]
        real_y = [_to_binary(real_outcomes[i]) for i in range(n)]

        # --- ECE: 10 equal-width bins over predicted probability ---
        n_bins = 10
        bin_conf = [0.0] * n_bins
        bin_acc = [0.0] * n_bins
        bin_cnt = [0] * n_bins
        for p, y in zip(sim_p, real_y):
            b = min(n_bins - 1, int(p * n_bins))
            bin_conf[b] += p
            bin_acc[b] += y
            bin_cnt[b] += 1
        ece = 0.0
        for b in range(n_bins):
            if bin_cnt[b] == 0:
                continue
            avg_conf = bin_conf[b] / bin_cnt[b]
            avg_acc = bin_acc[b] / bin_cnt[b]
            ece += (bin_cnt[b] / n) * abs(avg_conf - avg_acc)

        # --- USI: how much spread / discrimination does the sim actually have? ---
        mean_p = sum(sim_p) / n
        var_p = sum((p - mean_p) ** 2 for p in sim_p) / n
        # AUC-lite: fraction of (positive, negative) real pairs the sim orders correctly.
        pos = [sim_p[i] for i in range(n) if real_y[i] == 1]
        neg = [sim_p[i] for i in range(n) if real_y[i] == 0]
        if pos and neg:
            correct = 0
            total = 0
            for a in pos:
                for b in neg:
                    total += 1
                    if a > b:
                        correct += 1
                    elif a == b:
                        correct += 0.5
            auc = correct / total if total else 0.5
        else:
            auc = 0.5
        # informativeness blends discriminative power (auc beyond chance) with spread
        usi = _clamp(0.7 * (2.0 * abs(auc - 0.5)) + 0.3 * _clamp(var_p * 4.0, 0.0, 1.0), 0.0, 1.0)

        return {"usi": round(usi, 4), "ece": round(_clamp(ece, 0.0, 1.0), 4)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("simulator calibration_scorecard error (non-fatal): %r", exc)
        return {"usi": 0.0, "ece": 1.0}


__all__ = [
    "mine_archetypes",
    "simulate_call",
    "preeval_challenger",
    "synth_hard_negatives",
    "calibration_scorecard",
]


# --------------------------------------------------------------------------- #
# Inline self-check — happy path on SYNTHETIC inputs (NO network / NO ClickHouse / NO numpy).
# Exercises the pure-python paths (k-means fallback, feature vectors, hardness weighting,
# temperament read, archetype assembly, synthetic-negative minting, calibration math) and the
# dormant-safe sentinels (the LLM / store paths are dormant without OPENROUTER_API_KEY / CH).
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)

    # 1) Pure-python k-means clusters two well-separated blobs into 2 groups.
    vecs = [[0.0, 0.0], [0.1, 0.0], [0.0, 0.1], [9.0, 9.0], [9.1, 9.0], [9.0, 9.1]]
    labels = _kmeans(vecs, 2, seed=1)
    assert len(labels) == 6
    assert labels[0] == labels[1] == labels[2], labels
    assert labels[3] == labels[4] == labels[5], labels
    assert labels[0] != labels[3], labels
    print("kmeans (pure-python) OK:", labels)

    # 2) Temperament read picks up lexical cues from the caller's own words.
    assert _temperament_of(["ye to scam lagta hai, koi bharosa nahi"]) == "skeptic"
    assert _temperament_of(["busy hoon abhi, baad mein call karo"]) == "rushed"
    assert _temperament_of([""]) == "neutral"
    print("temperament read OK")

    # 3) Hardness weighting up-weights a cold + skeptic + price + rising-friction archetype.
    hard = _hardness_weight({"price": 6, "trust": 2}, "skeptic",
                            {"friction_start": 40, "friction_end": 70, "early_hangup_rate": 0.3}, 0.04)
    easy = _hardness_weight({"location": 3}, "warm",
                            {"friction_start": 45, "friction_end": 44, "early_hangup_rate": 0.0}, 0.5)
    assert hard > easy, (hard, easy)
    assert 1.0 <= easy <= hard <= 3.0
    print("hardness weight OK: hard=%s > easy=%s" % (hard, easy))

    # 4) Feature vector has a stable length and lands the objection histogram + outcome.
    fv = _feature_vector({"objection_hist": {"price": 3, "loan": 1}, "friction_start": 50,
                          "friction_end": 65, "temperament": "skeptic", "booked": True})
    assert len(fv) == len(S.OBJECTION_TYPES) + 4 + len(_TEMPERAMENTS) + 1
    assert fv[-1] == 1.0  # booked outcome anchored
    print("feature vector OK: dim=%d" % len(fv))

    # 5) mine_archetypes is DORMANT-SAFE (no CH / flag off) -> [].
    arcs = asyncio.get_event_loop().run_until_complete(mine_archetypes("tenant_demo"))
    assert arcs == [], arcs
    print("mine_archetypes dormant OK:", arcs)

    # 6) simulate_call + preeval are DORMANT-SAFE (no OPENROUTER key / flag off).
    fake_arc = {"tenant_id": "t1", "archetype_id": "arc_x", "label": "skeptic/price",
                "temperament": "skeptic", "objection_hist_json": json.dumps({"price": 5, "trust": 2}),
                "affect_template_json": json.dumps({"friction_start": 45, "friction_end": 72,
                                                    "early_hangup_rate": 0.3}),
                "base_book_rate": 0.04, "weight": 2.4}
    rolls = simulate_call(fake_arc, {"label": "champion"}, k=2)
    assert rolls == [], rolls
    pre = preeval_challenger({"challenger_id": "ch_1", "proposed_config_json": "{}"}, [fake_arc])
    assert pre == {"sim_reward_lift": 0.0, "per_archetype": [], "usi": 0.0, "ece": 1.0}, pre
    print("simulate_call / preeval dormant OK")

    # 7) synth_hard_negatives is DORMANT-SAFE -> [] (flag off).
    negs = synth_hard_negatives(fake_arc)
    assert negs == [], negs
    print("synth_hard_negatives dormant OK")

    # 8) calibration_scorecard PURE-PYTHON happy path: a well-calibrated, discriminative sim
    #    has LOW ece and reasonable usi; an empty input is the un-trustworthy sentinel.
    # Perfectly-ordered sim: positives predicted high, negatives low.
    sim = ["site_visit_booked", "site_visit_booked", "lead_cold", "not_interested", "hangup"]
    real = ["site_visit_booked", "lead_warm", "lead_cold", "not_interested", "lead_cold"]
    card = calibration_scorecard(sim, real)
    assert 0.0 <= card["ece"] <= 1.0 and 0.0 <= card["usi"] <= 1.0, card
    assert card["usi"] > 0.0, card  # the sim discriminates ⇒ informative
    empty = calibration_scorecard([], [])
    assert empty == {"usi": 0.0, "ece": 1.0}, empty
    print("calibration_scorecard OK: card=%s empty=%s" % (card, empty))

    # 9) The honesty gate: a sim that disagrees with reality should show a HIGH ece.
    bad_sim = ["site_visit_booked", "site_visit_booked", "site_visit_booked"]
    bad_real = ["lead_cold", "not_interested", "hangup"]
    bad = calibration_scorecard(bad_sim, bad_real)
    assert bad["ece"] > 0.15, bad  # would self-disable the sim (ece > sim_usi_ece_max)
    print("calibration honesty-gate OK: bad ece=%s" % bad["ece"])

    print("\nALL SELF-CHECKS PASSED")
