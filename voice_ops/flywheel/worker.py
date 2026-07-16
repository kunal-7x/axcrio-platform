"""voice_ops.flywheel.worker — the side-pipeline loop (Layer E).

Runs in a SEPARATE process (flywheel_worker.py, like run_worker.py), NEVER inside the voice
process. Every FLYWHEEL_WORKER_INTERVAL_S it, per tenant with recent activity:

  1. refresh the per-move PRM  P(book | move at state)        → flywheel_move_prm
  2. recompute the bandit posteriors from logged outcomes      → flywheel_arm_posteriors
  3. (judge_active) enrich a SAMPLE of calls — RLAIF judge + cohort credit → rewrites trajectories
  4. mine the (chosen,rejected) preference moat + human-label triggers → flywheel_preferences / _labels
  5. compute the Goodhart-canary monitors                       → flywheel_monitors
  6. write a compact dispatch POLICY SNAPSHOT to famit-var/     (the only thing the live path reads)

Every step is independently wrapped (best-effort) and the whole loop is dormant-safe: with the
flag off `run_once` returns immediately. The worker NEVER promotes a challenger — promotion is a
human click in the console (router POST /challengers/{id}/approve); the worker only PROPOSES
challengers (optimizer, gated by FLYWHEEL_OPTIMIZER_ENABLED) for a human to review.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from typing import Dict, List, Optional

from . import config as _cfg
from . import schema as S
from . import store as _st

logger = logging.getLogger("flywheel.worker")

_MAX_CALLS_PER_RUN = int(os.getenv("FLYWHEEL_MAX_CALLS_PER_RUN", "500"))
_MAX_ENRICH_PER_RUN = int(os.getenv("FLYWHEEL_MAX_ENRICH_PER_RUN", "30"))


def _policy_dir() -> str:
    base = (os.getenv("FAMIT_VAR") or os.getenv("FAMIT_VAR_DIR") or "famit-var").strip() or "famit-var"
    return os.path.join(base, "flywheel")


# --------------------------------------------------------------------------- #
class FlywheelLoop:
    """Orchestrates one pass. Stateless across runs (everything lives in ClickHouse)."""

    def __init__(self, cfg: Optional["_cfg.FlywheelConfig"] = None) -> None:
        self.cfg = cfg or _cfg.load()

    # -- tenant discovery --------------------------------------------------- #
    async def discover_tenants(self, minutes: int = None) -> List[str]:
        m = int(minutes or self.cfg.worker_interval_s // 60 * 4 or 240)
        res = await _st._ch(
            f"SELECT DISTINCT tenant_id FROM {_st._final(_st.TRAJECTORIES)} "
            f"WHERE ts > now() - INTERVAL {{m:UInt32}} MINUTE LIMIT 1000", {"m": m})
        return [r.get("tenant_id") for r in (res.get("rows") or []) if r.get("tenant_id")]

    # -- 1) per-move PRM ---------------------------------------------------- #
    async def refresh_move_prm(self, tenant_id: str) -> int:
        try:
            from . import credit
            rows = await credit.build_move_prm(tenant_id)
            if rows:
                _st.insert_move_prm(rows)
            return len(rows or [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("refresh_move_prm[%s] failed: %r", tenant_id, exc)
            return 0

    # -- 2) bandit posteriors (batch recompute from logged outcomes) -------- #
    async def refresh_bandit(self, tenant_id: str) -> int:
        try:
            from .schema import ArmPosterior
            written = 0
            arms_by_knob: Dict[str, List[ArmPosterior]] = {}
            for knob, col in (("variant", "arm_variant"), ("model", "arm_model"), ("voice", "arm_voice")):
                res = await _st._ch(
                    f"SELECT campaign_id, any(vertical) AS vertical, {col} AS arm, "
                    f"uniqExact(call_id) AS plays, "
                    f"uniqExactIf(call_id, reward_capped > 0.5) AS wins, "
                    f"uniqExactIf(call_id, reward_capped < -0.5) AS optouts "
                    f"FROM {_st._final(_st.TRAJECTORIES)} "
                    f"WHERE tenant_id = {{tid:String}} AND {col} != '' "
                    f"GROUP BY campaign_id, {col} HAVING plays >= 1 LIMIT 2000",
                    {"tid": tenant_id})
                arms: List[ArmPosterior] = []
                for r in res.get("rows") or []:
                    plays = int(r.get("plays", 0) or 0)
                    wins = int(r.get("wins", 0) or 0)
                    optouts = int(r.get("optouts", 0) or 0)
                    arms.append(ArmPosterior(
                        tenant_id=tenant_id, campaign_id=r.get("campaign_id", "") or "",
                        vertical=r.get("vertical", "real_estate") or "real_estate",
                        knob=knob, arm_id=str(r.get("arm", "")), context_bucket="all",
                        ts_iso=S.now_iso(),
                        alpha=1.0 + wins, beta=1.0 + max(0, plays - wins),
                        plays=plays, reward_sum=float(wins),
                        last_reward_ts=S.now_iso(),
                        discounted=float(wins),
                        guardrail_optout_rate=round(optouts / plays, 4) if plays else 0.0))
                if arms:
                    _st.insert_posteriors(arms)
                    written += len(arms)
                    arms_by_knob[knob] = arms
            self._write_policy_snapshot(tenant_id, arms_by_knob)
            return written
        except Exception as exc:  # noqa: BLE001
            logger.warning("refresh_bandit[%s] failed: %r", tenant_id, exc)
            return 0

    def _write_policy_snapshot(self, tenant_id: str, arms_by_knob: Dict[str, List]) -> None:
        """The ONLY artefact the live dispatch path reads — a local dict, never a CH/inference
        call mid-dial. flywheel_app.select_arm_for_dispatch loads this."""
        try:
            d = _policy_dir()
            os.makedirs(d, exist_ok=True)
            snap = {"tenant_id": tenant_id, "ts": S.now_iso(), "knobs": {}}
            for knob, arms in (arms_by_knob or {}).items():
                snap["knobs"][knob] = [
                    {"campaign_id": a.campaign_id, "arm_id": a.arm_id, "alpha": a.alpha,
                     "beta": a.beta, "plays": a.plays, "optout_rate": a.guardrail_optout_rate}
                    for a in arms]
            tmp = os.path.join(d, f"policy_{tenant_id}.json.tmp")
            with open(tmp, "w") as f:
                json.dump(snap, f)
            os.replace(tmp, os.path.join(d, f"policy_{tenant_id}.json"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("policy snapshot[%s] failed: %r", tenant_id, exc)

    # -- helper: pull recent trajectory turns grouped by call -------------- #
    async def _recent_calls(self, tenant_id: str, minutes: int) -> Dict[str, List[dict]]:
        res = await _st._ch(
            f"SELECT call_id, turn_num, campaign_id, vertical, lead_temperature, move_type, "
            f"objection_type, state_friction, state_arousal, state_regime, affect_delta, "
            f"judge_score, credit_advantage, reward_capped, confidence, low_conf, agent_text, caller_text "
            f"FROM {_st._final(_st.TRAJECTORIES)} WHERE tenant_id = {{tid:String}} "
            f"AND ts > now() - INTERVAL {{m:UInt32}} MINUTE ORDER BY call_id, turn_num "
            f"LIMIT 200000", {"tid": tenant_id, "m": int(minutes)})
        calls: Dict[str, List[dict]] = {}
        for r in res.get("rows") or []:
            calls.setdefault(r.get("call_id", ""), []).append(r)
        # bound the number of calls processed per run
        items = list(calls.items())[:_MAX_CALLS_PER_RUN]
        return dict(items)

    # -- 4) preference moat ------------------------------------------------- #
    async def mine_preferences(self, tenant_id: str, minutes: int) -> int:
        try:
            from . import preference
            calls = await self._recent_calls(tenant_id, minutes)
            all_pairs: List = []
            all_labels: List = []
            grouped: Dict[str, List[dict]] = {}
            for call_id, turns in calls.items():
                meta = {"tenant_id": tenant_id, "call_id": call_id,
                        "campaign_id": (turns[0].get("campaign_id") if turns else "") or "",
                        "vertical": (turns[0].get("vertical") if turns else "real_estate") or "real_estate"}
                try:
                    pairs, labels = preference.mine_call(turns, meta)
                    all_pairs.extend(pairs or [])
                    all_labels.extend(labels or [])
                except Exception:  # noqa: BLE001
                    pass
                # accumulate the matched-state grouping (cross-call moat)
                for t in turns:
                    bucket = preference.state_bucket(t.get("objection_type", "none"),
                                                     t.get("lead_temperature", "unknown"),
                                                     t.get("state_regime", "steady"))
                    grouped.setdefault(bucket, []).append({
                        "text": t.get("agent_text", ""), "reward": float(t.get("reward_capped", 0) or 0),
                        "outcome_anchored": float(t.get("reward_capped", 0) or 0) > 0.5,
                        "compliant": not t.get("low_conf", False) or True,
                        "move_id": f"{call_id}:{t.get('turn_num', 0)}",
                        "campaign_id": t.get("campaign_id", ""), "regime": t.get("state_regime", "steady"),
                        "objection_type": t.get("objection_type", "none"),
                        "lead_temperature": t.get("lead_temperature", "unknown")})
            try:
                all_pairs.extend(preference.mine_matched_state(grouped) or [])
            except Exception:  # noqa: BLE001
                pass
            # stamp tenant on every pair/label (defensive — multi-tenant boundary)
            for p in all_pairs:
                if not getattr(p, "tenant_id", ""):
                    p.tenant_id = tenant_id
            for lb in all_labels:
                if not getattr(lb, "tenant_id", ""):
                    lb.tenant_id = tenant_id
            if all_pairs:
                _st.insert_preferences(all_pairs)
            if all_labels:
                _st.insert_human_labels(all_labels)
            return len(all_pairs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("mine_preferences[%s] failed: %r", tenant_id, exc)
            return 0

    # -- 3) judge enrichment (sampled, gated) ------------------------------- #
    async def enrich_calls(self, tenant_id: str, minutes: int) -> int:
        if not self.cfg.judge_active():
            return 0
        try:
            from . import judge, reward, credit
            from .schema import TrajectoryRow, RewardComponents
            calls = await self._recent_calls(tenant_id, minutes)
            enriched = 0
            # B3 critic (learned V(state)) + B1 ensemble (pessimistic LCB) — loaded ONCE per pass.
            crit = None
            if self.cfg.critic_active():
                try:
                    from . import critic as _crit
                    crit = (_crit, await _crit.load_critic(tenant_id))
                except Exception:  # noqa: BLE001
                    crit = None
            ens = None
            if self.cfg.ensemble_active():
                try:
                    from . import ensemble as _ens
                    ens = _ens
                except Exception:  # noqa: BLE001
                    ens = None
            for call_id, turns in list(calls.items())[:_MAX_ENRICH_PER_RUN]:
                # sample: always-on for converting calls, sub-sample the rest
                converted = any(float(t.get("reward_capped", 0) or 0) > 0.5 for t in turns)
                if not converted and self.cfg.judge_sample_rate < 1.0:
                    h = int(S.digest_id(call_id), 16) % 100
                    if h >= int(self.cfg.judge_sample_rate * 100):
                        continue
                rows: List[TrajectoryRow] = []
                prev_v = None
                for t in turns:
                    state = {"friction": t.get("state_friction", 50), "regime": t.get("state_regime", "steady")}
                    affect_ctx = {"friction": t.get("state_friction", 50),
                                  "regime": t.get("state_regime", "steady"),
                                  "low_conf": bool(t.get("low_conf", False))}
                    jr = judge.score_turn(state, t.get("agent_text", ""), t.get("caller_text", ""),
                                          affect_ctx, rubric_version=self.cfg.rubric_version)
                    judge_score = float(jr.get("score", 0.0) or 0.0)
                    affect_delta = float(t.get("affect_delta", 0.0) or 0.0)
                    disagreement = (judge_score * affect_delta < 0) and abs(judge_score - affect_delta) > 0.5
                    rc = RewardComponents(
                        capped_outcome=float(t.get("reward_capped", 0) or 0),
                        terminal_credit=float(t.get("credit_advantage", 0) or 0),
                        affect_delta=affect_delta, judge_score=judge_score,
                        w_outcome=self.cfg.w_outcome, w_affect=self.cfg.w_affect, w_judge=self.cfg.w_judge,
                        judge_model_id=jr.get("model_id", ""), rubric_version=self.cfg.rubric_version,
                        confidence=float(jr.get("confidence", 0.0) or 0.0), disagreement=disagreement)
                    # B3 critic: V(state) = P(book), live momentum, centred value head.
                    v_state = 0.0; v_momentum = 0.0; value_head = 0.0
                    if crit is not None and crit[1] is not None:
                        try:
                            v_state = float(crit[0].predict(crit[0].featurize(t), crit[1]) or 0.0)
                            v_momentum = (v_state - prev_v) if prev_v is not None else 0.0
                            prev_v = v_state
                            value_head = (v_state - 0.5) * 2.0      # centre P(book) to ~[-1, 1]
                        except Exception:  # noqa: BLE001
                            pass
                    # B1 ensemble: fold the 4th head in + fill the pessimistic LCB on rc.
                    if ens is not None:
                        try:
                            rc = ens.fuse_pessimistic(rc, value_head=value_head, cfg=self.cfg)
                        except Exception:  # noqa: BLE001
                            pass
                    rows.append(TrajectoryRow(
                        tenant_id=tenant_id, call_id=call_id, turn_num=int(t.get("turn_num", 0) or 0),
                        ts_iso=S.now_iso(), campaign_id=t.get("campaign_id", ""),
                        vertical=t.get("vertical", "real_estate"),
                        lead_temperature=t.get("lead_temperature", "unknown"),
                        move_type=t.get("move_type", "other"), objection_type=t.get("objection_type", "none"),
                        state_friction=t.get("state_friction", 50), state_arousal=t.get("state_arousal", 50),
                        state_regime=t.get("state_regime", "steady"),
                        affect_delta=affect_delta, judge_score=judge_score,
                        rubric_json=json.dumps(jr.get("dimensions", {}))[:2000],
                        credit_advantage=float(t.get("credit_advantage", 0) or 0),
                        reward_capped=float(t.get("reward_capped", 0) or 0),
                        reward_components_json=rc.to_json(),
                        confidence=float(jr.get("confidence", 0.0) or 0.0),
                        low_conf=bool(t.get("low_conf", False)),
                        judge_model_id=jr.get("model_id", ""), rubric_version=self.cfg.rubric_version,
                        agent_text=t.get("agent_text", ""), caller_text=t.get("caller_text", ""),
                        v_state=round(v_state, 5), v_momentum=round(v_momentum, 5),
                        ensemble_mean=rc.ensemble_mean, ensemble_var=rc.ensemble_var,
                        lcb_reward=rc.lcb_reward, value_head=rc.value_head,
                        list_source=t.get("list_source", ""), play_template_id=t.get("play_template_id", "")))
                if rows:
                    _st.insert_trajectories(rows)   # ReplacingMergeTree → enriched replaces the seed
                    enriched += 1
            return enriched
        except Exception as exc:  # noqa: BLE001
            logger.warning("enrich_calls[%s] failed: %r", tenant_id, exc)
            return 0

    # -- 5) Goodhart-canary monitors --------------------------------------- #
    async def compute_monitors(self, tenant_id: str, minutes: int) -> int:
        try:
            from .schema import MonitorPoint
            pts: List[MonitorPoint] = []
            res = await _st._ch(
                f"SELECT uniqExact(call_id) AS calls, "
                f"uniqExactIf(call_id, reward_capped < -0.5) AS optouts, "
                f"avg(affect_delta) AS friction_shift, "
                f"corr(judge_score, reward_capped) AS jvo "
                f"FROM {_st._final(_st.TRAJECTORIES)} WHERE tenant_id = {{tid:String}} "
                f"AND ts > now() - INTERVAL {{m:UInt32}} MINUTE", {"tid": tenant_id, "m": int(minutes)})
            row = (res.get("rows") or [{}])[0]
            calls = int(row.get("calls", 0) or 0)
            optout_rate = round((row.get("optouts", 0) or 0) / calls, 4) if calls else 0.0
            jvo = row.get("jvo")
            jvo = round(float(jvo), 4) if jvo not in (None, "nan") and not (isinstance(jvo, float) and math.isnan(jvo)) else 0.0
            now = S.now_iso()
            pts.append(MonitorPoint(tenant_id=tenant_id, ts_iso=now, metric="optout_rate",
                                    value=optout_rate, threshold_breached=optout_rate > 0.15))
            pts.append(MonitorPoint(tenant_id=tenant_id, ts_iso=now, metric="friction_trend",
                                    value=round(float(row.get("friction_shift", 0) or 0), 4)))
            # judge-vs-outcome correlation: the STOP signal — proxy up but real bookings flat ⇒ breach.
            pts.append(MonitorPoint(tenant_id=tenant_id, ts_iso=now, metric="judge_vs_outcome_corr",
                                    value=jvo, threshold_breached=(jvo < 0.0)))
            if pts:
                _st.insert_monitors(pts)
            return len(pts)
        except Exception as exc:  # noqa: BLE001
            logger.warning("compute_monitors[%s] failed: %r", tenant_id, exc)
            return 0

    # -- power-up tier passes (each gated by its own active() predicate) ----- #
    async def refresh_critic(self, tenant_id: str) -> bool:
        """B3 — (re)train the learned V(state)→P(book) critic. Persists itself; returns active?."""
        if not self.cfg.critic_active():
            return False
        try:
            from . import critic
            model = await critic.train_critic(tenant_id, cfg=self.cfg)
            return bool(getattr(model, "active", False))
        except Exception as exc:  # noqa: BLE001
            logger.warning("refresh_critic[%s] failed: %r", tenant_id, exc)
            return False

    async def refresh_causal(self, tenant_id: str) -> int:
        """B4 — DR X-learner CATE per (move, state). build_move_cate persists itself."""
        if not self.cfg.causal_active():
            return 0
        try:
            from . import causal
            rows = await causal.build_move_cate(tenant_id, cfg=self.cfg)
            return len(rows or [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("refresh_causal[%s] failed: %r", tenant_id, exc)
            return 0

    async def refresh_policy(self, tenant_id: str) -> bool:
        """B6 — (re)train the contextual LinTS per-state selector. Persists itself."""
        if not self.cfg.policy_active():
            return False
        try:
            from . import policy
            model = await policy.train_policy(tenant_id, cfg=self.cfg)
            return bool(getattr(model, "active", False))
        except Exception as exc:  # noqa: BLE001
            logger.warning("refresh_policy[%s] failed: %r", tenant_id, exc)
            return False

    async def refresh_simulator(self, tenant_id: str) -> int:
        """B5 — (re)mine caller archetypes for the world model. Persists itself."""
        if not self.cfg.simulator_active():
            return 0
        try:
            from . import simulator
            arcs = await simulator.mine_archetypes(tenant_id, cfg=self.cfg)
            return len(arcs or [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("refresh_simulator[%s] failed: %r", tenant_id, exc)
            return 0

    async def export_distill(self, tenant_id: str) -> dict:
        """B7 — export the preference moat as a KTO training set (a self-hosted shadow challenger
        is trained + gated separately; never the live model)."""
        if not self.cfg.distill_active():
            return {"ok": False}
        try:
            from . import distill
            return await distill.export_kto(tenant_id, cfg=self.cfg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("export_distill[%s] failed: %r", tenant_id, exc)
            return {"ok": False, "error": str(exc)[:120]}

    # -- one full pass ------------------------------------------------------ #
    async def run_once(self, tenant_id: str) -> dict:
        if not self.cfg.active():
            return {"active": False}
        minutes = max(60, self.cfg.worker_interval_s // 60 * 24)   # look back ~a day of activity
        out = {"tenant_id": tenant_id, "active": True}
        # power-up models refreshed FIRST so enrich_calls can use the freshest critic.
        out["critic_active"] = await self.refresh_critic(tenant_id)
        out["enriched"] = await self.enrich_calls(tenant_id, minutes)
        out["move_prm"] = await self.refresh_move_prm(tenant_id)
        out["move_cate"] = await self.refresh_causal(tenant_id)        # B4 causal
        out["bandit_arms"] = await self.refresh_bandit(tenant_id)
        out["policy_active"] = await self.refresh_policy(tenant_id)    # B6 contextual policy
        out["archetypes"] = await self.refresh_simulator(tenant_id)   # B5 world model
        out["preferences"] = await self.mine_preferences(tenant_id, minutes)
        out["monitors"] = await self.compute_monitors(tenant_id, minutes)
        if self.cfg.distill_active():
            out["distill"] = (await self.export_distill(tenant_id)).get("ok", False)
        logger.info("flywheel run_once %s", out)
        return out

    async def run_all(self) -> List[dict]:
        if not self.cfg.active():
            logger.info("flywheel dormant — run_all no-op")
            return []
        tenants = await self.discover_tenants()
        return [await self.run_once(t) for t in tenants]

    async def run_forever(self) -> None:
        logger.info("flywheel worker starting; interval=%ss active=%s",
                    self.cfg.worker_interval_s, self.cfg.active())
        while True:
            try:
                self.cfg = _cfg.load()                  # honour a runtime flag flip
                if self.cfg.active():
                    await self.run_all()
            except Exception as exc:  # noqa: BLE001
                logger.warning("flywheel loop iteration error: %r", exc)
            await asyncio.sleep(max(60, self.cfg.worker_interval_s))


_LOOP: Optional[FlywheelLoop] = None


def get_loop() -> FlywheelLoop:
    global _LOOP
    if _LOOP is None:
        _LOOP = FlywheelLoop()
    return _LOOP


async def run_once(tenant_id: str) -> dict:
    return await get_loop().run_once(tenant_id)


async def run_forever() -> None:
    await get_loop().run_forever()


__all__ = ["FlywheelLoop", "get_loop", "run_once", "run_forever"]
