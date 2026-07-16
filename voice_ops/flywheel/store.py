"""voice_ops.flywheel.store — ClickHouse read/write for the Flywheel warehouse.

WRITES mirror research_analytics._insert (sync, best-effort, batched JSONEachRow); READS
mirror research_query._ch (async httpx, readonly=2, tenant bound as {tid:String}). ClickHouse
has NO row-level security — the Python-side `WHERE tenant_id = {tid:String}` IS the tenant
boundary (the top invariant: a missing filter would leak cross-tenant data to a super-admin).

DESIGN LAWS: dormant-safe (no-op unless a CH url is configured), best-effort (every public
function swallows errors → WARNING log, never raises), and reuses the SAME CLICKHOUSE_* env as
voice_analytics / Famit Research. DDL is applied ONCE by the operator
(voice_ops/flywheel/db/ddl_flywheel.sql) — this module never auto-creates a table.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional

from . import config as _cfg

logger = logging.getLogger("flywheel.store")

TRAJECTORIES = "flywheel_trajectories"
PREFERENCES = "flywheel_preferences"
POSTERIORS = "flywheel_arm_posteriors"
MOVE_PRM = "flywheel_move_prm"
CHALLENGERS = "flywheel_challengers"
HUMAN_LABELS = "flywheel_human_labels"
MONITORS = "flywheel_monitors"
# --- power-up tier tables (B1–B7) ---
MOVE_CATE = "flywheel_move_cate"            # B4 causal CATE per move/state
CRITIC_MODELS = "flywheel_critic_models"    # B3 learned V(state) coefficients
POLICY_MODELS = "flywheel_policy_models"    # B6 contextual LinTS sufficient stats
PLAY_LIBRARY = "flywheel_play_library"      # B6 rebuttal/template action space
ARCHETYPES = "flywheel_archetypes"          # B5 mined caller archetypes
SIM_ROLLOUTS = "flywheel_sim_rollouts"      # B5 simulator rollout audit
DISTILL_RUNS = "flywheel_distill_runs"      # B7 KTO/SimPO training-run audit
SEQUENTIAL_STATE = "flywheel_sequential_state"  # B2 anytime-test running stats
CONFORMAL_CALIB = "flywheel_conformal_calib"    # B2 Mondrian q_hat per bucket

# ReplacingMergeTree tables — read with FINAL to collapse the latest row per key.
# trajectories: seed (finalize hook) → enriched (worker) collapse to one row per (call, turn).
_REPLACING = {TRAJECTORIES, POSTERIORS, CHALLENGERS,
              CRITIC_MODELS, POLICY_MODELS, PLAY_LIBRARY, ARCHETYPES,
              SEQUENTIAL_STATE, CONFORMAL_CALIB}


def _rows(objs: List) -> List[dict]:
    """Coerce a list of dataclasses (with .to_row()) or dicts → JSONEachRow dicts."""
    out: List[dict] = []
    for o in objs or []:
        if o is None:
            continue
        if hasattr(o, "to_row"):
            out.append(o.to_row())
        elif isinstance(o, dict):
            out.append(o)
    return out


# --------------------------------------------------------------------------- #
# WRITE — sync, best-effort, batched (mirrors research_analytics._insert).
# --------------------------------------------------------------------------- #
def _insert(table: str, objs: List, *, force: bool = False) -> bool:
    """Batched INSERT … FORMAT JSONEachRow. No-op unless active() (or force=True for a
    one-shot backfill with an explicit url). Returns True on a clean POST. Never raises."""
    try:
        cfg = _cfg.load()
        if not (cfg.active() or force):
            return False
        url = cfg.ch_write_url
        if not url:
            return False
        rows = _rows(objs)
        if not rows:
            return True
        import httpx
        from urllib.parse import urlsplit
        body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
        params = {"query": f"INSERT INTO {table} FORMAT JSONEachRow"}
        # ClickHouse rejects an Authorization header AND user/password params together
        # (Code 516): only add env creds when the URL carries no userinfo (mirror voice_analytics).
        if "@" not in (urlsplit(url).netloc or ""):
            user = (os.getenv("CLICKHOUSE_USER") or "").strip()
            pw = (os.getenv("CLICKHOUSE_PASSWORD") or "").strip()
            if user:
                params["user"] = user
            if pw:
                params["password"] = pw
        r = httpx.post(url + "/", params=params, content=body.encode("utf-8"),
                       timeout=float(os.getenv("FLYWHEEL_TIMEOUT", "8")))
        if r.status_code >= 400:
            logger.warning("flywheel insert -> %s failed: HTTP %s %s", table, r.status_code, (r.text or "")[:200])
            return False
        logger.info("flywheel insert -> %s ok (%d rows)", table, len(rows))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel insert -> %s error: %r", table, exc)
        return False


def insert_trajectories(rows: List, *, force: bool = False) -> bool:
    return _insert(TRAJECTORIES, rows, force=force)


def insert_preferences(pairs: List, *, force: bool = False) -> bool:
    return _insert(PREFERENCES, pairs, force=force)


def insert_posteriors(arms: List, *, force: bool = False) -> bool:
    return _insert(POSTERIORS, arms, force=force)


def insert_move_prm(rows: List, *, force: bool = False) -> bool:
    return _insert(MOVE_PRM, rows, force=force)


def insert_challengers(challengers: List, *, force: bool = False) -> bool:
    return _insert(CHALLENGERS, challengers, force=force)


def insert_human_labels(labels: List, *, force: bool = False) -> bool:
    return _insert(HUMAN_LABELS, labels, force=force)


def insert_monitors(points: List, *, force: bool = False) -> bool:
    return _insert(MONITORS, points, force=force)


# --- power-up tier writers ------------------------------------------------- #
def insert_move_cate(rows: List, *, force: bool = False) -> bool:
    return _insert(MOVE_CATE, rows, force=force)


def insert_critic_model(models: List, *, force: bool = False) -> bool:
    return _insert(CRITIC_MODELS, models, force=force)


def insert_policy_model(models: List, *, force: bool = False) -> bool:
    return _insert(POLICY_MODELS, models, force=force)


def insert_play_templates(templates: List, *, force: bool = False) -> bool:
    return _insert(PLAY_LIBRARY, templates, force=force)


def insert_archetypes(rows: List, *, force: bool = False) -> bool:
    return _insert(ARCHETYPES, rows, force=force)


def insert_sim_rollouts(rows: List, *, force: bool = False) -> bool:
    return _insert(SIM_ROLLOUTS, rows, force=force)


def insert_distill_runs(rows: List, *, force: bool = False) -> bool:
    return _insert(DISTILL_RUNS, rows, force=force)


def insert_sequential_state(rows: List, *, force: bool = False) -> bool:
    return _insert(SEQUENTIAL_STATE, rows, force=force)


def insert_conformal_calib(rows: List, *, force: bool = False) -> bool:
    return _insert(CONFORMAL_CALIB, rows, force=force)


# --------------------------------------------------------------------------- #
# READ — async, tenant-scoped (mirrors research_query._ch). Returns {"rows": [...]} /
# {"error": ...}; NEVER raises. The caller adds a demo fallback when rows is empty.
# --------------------------------------------------------------------------- #
async def _ch(sql: str, params: Optional[dict] = None) -> dict:
    base = _cfg.load().ch_read_url
    if not base:
        return {"error": "flywheel store not configured", "rows": []}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(base + "/", content=sql.encode("utf-8"),
                             params={**(params or {}), "default_format": "JSONEachRow",
                                     "readonly": "2", "max_execution_time": "30",
                                     "max_result_rows": "200000", "result_overflow_mode": "break"})
        if r.status_code != 200:
            return {"error": (r.text or "")[:300].strip(), "rows": []}
        rows = []
        for ln in r.text.splitlines():
            ln = ln.strip()
            if ln:
                try:
                    rows.append(json.loads(ln))
                except Exception:  # noqa: BLE001
                    pass
        return {"rows": rows}
    except Exception:  # noqa: BLE001
        return {"error": "flywheel store unreachable", "rows": []}


def _final(table: str) -> str:
    return f"{table} FINAL" if table in _REPLACING else table


async def read_trajectory(tenant_id: str, call_id: str) -> dict:
    """Per-call (state, move, reward, credit) turns — the honest-science detail view."""
    res = await _ch(
        f"SELECT turn_num, toString(ts) AS ts, move_type, objection_type, "
        f"state_friction, state_arousal, state_regime, arm_model, arm_voice, arm_variant, "
        f"propensity, affect_delta, judge_score, credit_advantage, reward_raw, reward_capped, "
        f"reward_components_json, confidence, low_conf, agent_text, caller_text "
        f"FROM {_final(TRAJECTORIES)} WHERE tenant_id = {{tid:String}} AND call_id = {{cid:String}} "
        f"ORDER BY turn_num ASC LIMIT 2000",
        {"tid": tenant_id, "cid": call_id},
    )
    return {"call_id": call_id, "turns": res.get("rows") or [], "error": res.get("error")}


async def read_moves(tenant_id: str, vertical: str = "", minutes: int = 43200) -> dict:
    """Per-move PRM table (lift + CI + n) — answers 'which move is +/-'."""
    where = "tenant_id = {tid:String} AND ts > now() - INTERVAL {m:UInt32} MINUTE"
    p = {"tid": tenant_id, "m": int(minutes)}
    if vertical:
        where += " AND vertical = {v:String}"
        p["v"] = vertical
    res = await _ch(
        f"SELECT move_type, objection_type, regime, lead_temperature, "
        f"argMax(book_rate, ts) AS book_rate, argMax(baseline_rate, ts) AS baseline_rate, "
        f"argMax(lift, ts) AS lift, argMax(n_samples, ts) AS n_samples, "
        f"argMax(ci_low, ts) AS ci_low, argMax(ci_high, ts) AS ci_high "
        f"FROM {MOVE_PRM} WHERE {where} "
        f"GROUP BY move_type, objection_type, regime, lead_temperature "
        f"ORDER BY lift DESC LIMIT 500", p)
    return {"moves": res.get("rows") or [], "error": res.get("error")}


async def read_bandit(tenant_id: str, campaign_id: str = "") -> dict:
    """Arm posteriors with means + guardrails (latest per arm via FINAL)."""
    where = "tenant_id = {tid:String}"
    p = {"tid": tenant_id}
    if campaign_id:
        where += " AND campaign_id = {cid:String}"
        p["cid"] = campaign_id
    res = await _ch(
        f"SELECT campaign_id, vertical, knob, arm_id, context_bucket, alpha, beta, plays, "
        f"reward_sum, discounted, guardrail_optout_rate, guardrail_cost_per_booking, toString(ts) AS ts "
        f"FROM {_final(POSTERIORS)} WHERE {where} ORDER BY knob, (alpha/(alpha+beta)) DESC LIMIT 1000", p)
    rows = res.get("rows") or []
    for r in rows:
        a, b = float(r.get("alpha", 1) or 1), float(r.get("beta", 1) or 1)
        r["mean"] = round(a / (a + b), 4) if (a + b) > 0 else 0.0
    return {"arms": rows, "error": res.get("error")}


async def read_challengers(tenant_id: str, status: str = "") -> dict:
    """Promotion queue (latest status per challenger via FINAL)."""
    where = "tenant_id = {tid:String}"
    p = {"tid": tenant_id}
    if status:
        where += " AND status = {st:String}"
        p["st"] = status
    res = await _ch(
        f"SELECT challenger_id, toString(ts) AS ts, kind, campaign_id, proposed_config_json, "
        f"rationale, ope_snips_value, gates_passed, replay_delta, shadow_ok, status, approved_by, "
        f"reward_lift, ttft_ms, cost_per_appointment "
        f"FROM {_final(CHALLENGERS)} WHERE {where} ORDER BY ts DESC LIMIT 200", p)
    return {"challengers": res.get("rows") or [], "error": res.get("error")}


async def read_preferences(tenant_id: str, objection: str = "", temp: str = "", limit: int = 100) -> dict:
    """Sanitized mined (chosen, rejected) pairs + counts (the moat browser)."""
    where = "tenant_id = {tid:String}"
    p = {"tid": tenant_id, "lim": int(limit)}
    if objection:
        where += " AND objection_type = {obj:String}"
        p["obj"] = objection
    if temp:
        where += " AND lead_temperature = {tmp:String}"
        p["tmp"] = temp
    res = await _ch(
        f"SELECT pair_id, toString(ts) AS ts, objection_type, lead_temperature, regime, vertical, "
        f"chosen_text, rejected_text, margin, source, survived_swap, confidence, compliant, "
        f"outcome_anchored, campaign_id "
        f"FROM {PREFERENCES} WHERE {where} ORDER BY ts DESC LIMIT {{lim:UInt32}}", p)
    return {"pairs": res.get("rows") or [], "error": res.get("error")}


async def read_labels(tenant_id: str, only_open: bool = True, limit: int = 200) -> dict:
    where = "tenant_id = {tid:String}"
    p = {"tid": tenant_id, "lim": int(limit)}
    if only_open:
        where += " AND label = ''"
    res = await _ch(
        f"SELECT call_id, turn_num, toString(ts) AS ts, trigger, label, labeler, rationale, "
        f"used_for_calibration FROM {HUMAN_LABELS} WHERE {where} ORDER BY ts DESC LIMIT {{lim:UInt32}}", p)
    return {"labels": res.get("rows") or [], "error": res.get("error")}


async def read_monitors(tenant_id: str, minutes: int = 43200) -> dict:
    res = await _ch(
        f"SELECT metric, toString(ts) AS ts, value, arm_id, threshold_breached "
        f"FROM {MONITORS} WHERE tenant_id = {{tid:String}} AND ts > now() - INTERVAL {{m:UInt32}} MINUTE "
        f"ORDER BY ts DESC LIMIT 2000", {"tid": tenant_id, "m": int(minutes)})
    return {"monitors": res.get("rows") or [], "error": res.get("error")}


async def read_dashboard(tenant_id: str, minutes: int = 43200) -> dict:
    """Moat KPIs: trajectory + preference growth, outcome-linkage, judge coverage, the
    objection×temperature coverage grid. Pure-SQL aggregates so the panel reads one call."""
    m = max(1, min(int(minutes), 525600))
    traj = await _ch(
        f"SELECT count() AS turns, uniqExact(call_id) AS calls, "
        f"avgIf(reward_capped, reward_capped != 0) AS avg_reward, "
        f"avg(confidence) AS confidence, sumIf(1, low_conf=1) AS low_conf_turns, "
        f"sumIf(1, judge_score != 0) AS judged_turns "
        f"FROM {_final(TRAJECTORIES)} WHERE tenant_id = {{tid:String}} AND ts > now() - INTERVAL {{m:UInt32}} MINUTE",
        {"tid": tenant_id, "m": m})
    pref = await _ch(
        f"SELECT count() AS pairs, sumIf(1, outcome_anchored=1) AS outcome_anchored, "
        f"sumIf(1, survived_swap=1) AS survived_swap, avg(confidence) AS pair_conf "
        f"FROM {PREFERENCES} WHERE tenant_id = {{tid:String}} AND ts > now() - INTERVAL {{m:UInt32}} MINUTE",
        {"tid": tenant_id, "m": m})
    grid = await _ch(
        f"SELECT objection_type, lead_temperature, count() AS n "
        f"FROM {PREFERENCES} WHERE tenant_id = {{tid:String}} "
        f"GROUP BY objection_type, lead_temperature ORDER BY n DESC LIMIT 200",
        {"tid": tenant_id})
    return {
        "trajectory": (traj.get("rows") or [{}])[0],
        "preferences": (pref.get("rows") or [{}])[0],
        "coverage_grid": grid.get("rows") or [],
        "error": traj.get("error") or pref.get("error"),
    }


# --- power-up tier readers ------------------------------------------------- #
async def read_move_cate(tenant_id: str, vertical: str = "", minutes: int = 43200) -> dict:
    """Causal CATE per move/state (latest GROUP — the console shows raw_lift vs causal cate side-by-side)."""
    where = "tenant_id = {tid:String} AND ts > now() - INTERVAL {m:UInt32} MINUTE"
    p = {"tid": tenant_id, "m": int(minutes)}
    if vertical:
        where += " AND vertical = {v:String}"
        p["v"] = vertical
    res = await _ch(
        f"SELECT move_type, objection_type, regime, lead_temperature, "
        f"argMax(cate, ts) AS cate, argMax(cate_lower, ts) AS cate_lower, "
        f"argMax(cate_upper, ts) AS cate_upper, argMax(raw_lift, ts) AS raw_lift, "
        f"argMax(n_treated, ts) AS n_treated, argMax(overlap_min, ts) AS overlap_min, "
        f"argMax(sign_agree, ts) AS sign_agree "
        f"FROM {MOVE_CATE} WHERE {where} "
        f"GROUP BY move_type, objection_type, regime, lead_temperature "
        f"ORDER BY cate DESC LIMIT 500", p)
    return {"moves": res.get("rows") or [], "error": res.get("error")}


async def read_critic(tenant_id: str) -> dict:
    res = await _ch(
        f"SELECT toString(ts) AS ts, vertical, model_type, platt_a, platt_b, auc, ece, n_rows, active, coef_json "
        f"FROM {_final(CRITIC_MODELS)} WHERE tenant_id = {{tid:String}} ORDER BY ts DESC LIMIT 10",
        {"tid": tenant_id})
    return {"critics": res.get("rows") or [], "error": res.get("error")}


async def read_policy(tenant_id: str, campaign_id: str = "") -> dict:
    where = "tenant_id = {tid:String}"
    p = {"tid": tenant_id}
    if campaign_id:
        where += " AND campaign_id = {cid:String}"
        p["cid"] = campaign_id
    res = await _ch(
        f"SELECT toString(ts) AS ts, campaign_id, vertical, knob, n_features, ope_snips, ope_fqe, "
        f"ope_magic, ope_lower, active, arms_json FROM {_final(POLICY_MODELS)} WHERE {where} "
        f"ORDER BY ts DESC LIMIT 50", p)
    return {"policies": res.get("rows") or [], "error": res.get("error")}


async def read_play_library(tenant_id: str, objection: str = "") -> dict:
    where = "tenant_id = {tid:String} AND active = 1"
    p = {"tid": tenant_id}
    if objection:
        where += " AND objection_type = {obj:String}"
        p["obj"] = objection
    res = await _ch(
        f"SELECT template_id, objection_type, text, label FROM {_final(PLAY_LIBRARY)} WHERE {where} "
        f"LIMIT 1000", p)
    return {"templates": res.get("rows") or [], "error": res.get("error")}


async def read_archetypes(tenant_id: str) -> dict:
    res = await _ch(
        f"SELECT archetype_id, label, temperament, base_book_rate, weight, n_calls, "
        f"objection_hist_json, affect_template_json FROM {_final(ARCHETYPES)} "
        f"WHERE tenant_id = {{tid:String}} ORDER BY weight DESC LIMIT 100", {"tid": tenant_id})
    return {"archetypes": res.get("rows") or [], "error": res.get("error")}


async def read_sim_rollouts(tenant_id: str, minutes: int = 43200) -> dict:
    res = await _ch(
        f"SELECT toString(ts) AS ts, archetype_id, challenger_id, policy_label, sim_outcome, "
        f"sim_reward, turns, usi, ece FROM {SIM_ROLLOUTS} WHERE tenant_id = {{tid:String}} "
        f"AND ts > now() - INTERVAL {{m:UInt32}} MINUTE ORDER BY ts DESC LIMIT 1000",
        {"tid": tenant_id, "m": int(minutes)})
    return {"rollouts": res.get("rows") or [], "error": res.get("error")}


async def read_sequential_state(tenant_id: str, challenger_id: str = "") -> dict:
    where = "tenant_id = {tid:String}"
    p = {"tid": tenant_id}
    if challenger_id:
        where += " AND challenger_id = {cid:String}"
        p["cid"] = challenger_id
    res = await _ch(
        f"SELECT challenger_id, metric, n, running_mean, cs_lower, cs_upper, significant "
        f"FROM {_final(SEQUENTIAL_STATE)} WHERE {where} ORDER BY challenger_id LIMIT 500", p)
    return {"states": res.get("rows") or [], "error": res.get("error")}


async def read_distill_runs(tenant_id: str) -> dict:
    res = await _ch(
        f"SELECT toString(ts) AS ts, run_id, method, base_model, n_desirable, n_undesirable, "
        f"status, adapter_uri FROM {DISTILL_RUNS} WHERE tenant_id = {{tid:String}} "
        f"ORDER BY ts DESC LIMIT 100", {"tid": tenant_id})
    return {"runs": res.get("rows") or [], "error": res.get("error")}


__all__ = [
    "TRAJECTORIES", "PREFERENCES", "POSTERIORS", "MOVE_PRM", "CHALLENGERS",
    "HUMAN_LABELS", "MONITORS", "MOVE_CATE", "CRITIC_MODELS", "POLICY_MODELS",
    "PLAY_LIBRARY", "ARCHETYPES", "SIM_ROLLOUTS", "DISTILL_RUNS", "SEQUENTIAL_STATE",
    "CONFORMAL_CALIB", "_insert", "_ch", "_final",
    "insert_trajectories", "insert_preferences", "insert_posteriors", "insert_move_prm",
    "insert_challengers", "insert_human_labels", "insert_monitors",
    "insert_move_cate", "insert_critic_model", "insert_policy_model", "insert_play_templates",
    "insert_archetypes", "insert_sim_rollouts", "insert_distill_runs",
    "insert_sequential_state", "insert_conformal_calib",
    "read_trajectory", "read_moves", "read_bandit", "read_challengers",
    "read_preferences", "read_labels", "read_monitors", "read_dashboard",
    "read_move_cate", "read_critic", "read_policy", "read_play_library", "read_archetypes",
    "read_sim_rollouts", "read_sequential_state", "read_distill_runs",
]
