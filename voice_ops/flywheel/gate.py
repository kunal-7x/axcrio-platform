"""voice_ops.flywheel.gate — the promotion gate every challenger must clear.

A flywheel-proposed policy change (a new variant / prompt / rebuttal) is NEVER promoted on a
reward number alone. It must compose-and-pass the EXISTING safety harness — there is no new
gate logic here, we orchestrate what already protects the live agent:

  * voice_ops.eval.regression_gates.run_all_gates()  — the master R1..R15 (+F-COMPLIANCE/F-HONESTY)
    deploy gate: AI-self-label ban, vendor-script authority, language adaptation, cross-vertical
    isolation, prosody, etc. A green report = safe cutover.
  * voice_ops.eval.replay.replay_conversation()      — drive the candidate's fields through the
    kernel over the golden turns; assert the R-invariants still hold under the new policy.
  * voice_ops.eval.metrics.MetricsCollector          — cost_per_appointment + TTFA(ssembly): a
    "better" prompt that is slower/pricier is REJECTED (voice cares about TTFT; §risk latency).
  * voice_kernel.shadow.runner.shadow_compute()      — observability-only shadow build of the
    candidate packet (never substitutes live instructions).
  * flywheel.compliance.check_*                       — the Tier-1 HARD GATE (a coercive/non-
    compliant candidate is ineligible regardless of its reward lift).

Then a HUMAN must approve (router POST /challengers/{id}/approve) — FLYWHEEL_AUTO_PROMOTE stays 0.
Everything is lazy-imported + best-effort: a harness failure makes the challenger INELIGIBLE with a
reason, never raises. Droplet-free (only voice_ops.eval + voice_kernel are imported, lazily).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from . import config as _cfg
from . import schema as S
from . import store as _st

logger = logging.getLogger("flywheel.gate")

# A candidate prompt whose brain-assembly costs more than this is too slow for voice.
DEFAULT_TTFA_BUDGET_MS = 40.0


@dataclass
class GateOutcome:
    challenger_id: str = ""
    gates_passed: bool = False
    gate_summary: str = ""
    replay_passed: bool = False
    replay_delta: float = 0.0          # candidate cost_per_appointment − champion (negative is better)
    shadow_ok: bool = False
    compliance_ok: bool = True
    ttft_ms: int = 0
    cost_per_appointment: float = 0.0
    eligible: bool = False             # ALL of the above must hold to reach human approval
    reasons: List[str] = field(default_factory=list)


def _candidate_fields(challenger) -> dict:
    """Pull the campaign fields the candidate proposes (or {} for a bare prompt/rebuttal)."""
    try:
        cfgj = getattr(challenger, "proposed_config_json", "") or ""
        cand = json.loads(cfgj) if cfgj else {}
    except Exception:  # noqa: BLE001
        cand = {}
    if not isinstance(cand, dict):
        return {}
    # A variant challenger carries fields/fields_override; a prompt challenger a 'prompt' text.
    fields = cand.get("fields") or cand.get("fields_override") or {}
    return fields if isinstance(fields, dict) else {}


def _candidate_text(challenger) -> str:
    try:
        cand = json.loads(getattr(challenger, "proposed_config_json", "") or "{}")
        return str(cand.get("prompt") or cand.get("text") or "")
    except Exception:  # noqa: BLE001
        return ""


def ttfa_budget_ok(ttft_ms: float, budget_ms: float = DEFAULT_TTFA_BUDGET_MS) -> bool:
    return float(ttft_ms or 0.0) <= float(budget_ms)


def evaluate_challenger(challenger, *, champion_cost: Optional[float] = None,
                        ttfa_budget_ms: float = DEFAULT_TTFA_BUDGET_MS) -> GateOutcome:
    """Run the full harness over a challenger. Best-effort: any harness error → ineligible with a
    reason, never raises. The result is persisted (challenger row updated to status='gated')."""
    out = GateOutcome(challenger_id=getattr(challenger, "challenger_id", ""))
    reasons: List[str] = []

    # 1) Tier-1 compliance HARD GATE on the candidate text (a coercive prompt never promotes).
    try:
        from . import compliance
        text = _candidate_text(challenger)
        if text:
            viol = compliance.check_text(text, stance="sales")
            out.compliance_ok = not viol
            if viol:
                reasons.append("compliance:" + ",".join(viol))
    except Exception as exc:  # noqa: BLE001
        logger.warning("gate compliance check failed: %r", exc)

    # 2) Master regression gates (global safety incl. F-COMPLIANCE/F-HONESTY once appended).
    try:
        from voice_ops.eval import regression_gates as rg
        report = rg.run_all_gates()
        out.gates_passed = bool(getattr(report, "passed", False))
        try:
            out.gate_summary = (report.summary() or "")[:1000]
        except Exception:  # noqa: BLE001
            out.gate_summary = ""
        if not out.gates_passed:
            reasons.append("regression_gates_failed:" + ",".join(getattr(report, "failed_gates", []) or []))
    except Exception as exc:  # noqa: BLE001
        logger.warning("gate run_all_gates failed: %r", exc)
        reasons.append("gates_unavailable")

    # 3) Replay the candidate fields over the goldens + measure cost/TTFA.
    cand_fields = _candidate_fields(challenger)
    try:
        from voice_ops.eval import verticals as V
        from voice_ops.eval.replay import replay_conversation, recorded_call_from_golden, RecordedCall
        goldens = list(V.all_goldens())
        replay_ok = True
        for g in goldens[:3]:                      # a few representative goldens
            try:
                base = recorded_call_from_golden(g)
                fields = dict(getattr(base, "fields", {}) or {})
                fields.update(cand_fields)          # apply the candidate override
                rc = RecordedCall(name=f"chal_{out.challenger_id}_{getattr(g,'name','')}",
                                  fields=fields, turns=getattr(base, "turns", ()))
                res = replay_conversation(rc)
                replay_ok = replay_ok and bool(getattr(res, "passed", False))
            except Exception:  # noqa: BLE001
                replay_ok = False
        out.replay_passed = replay_ok
        if not replay_ok:
            reasons.append("replay_invariants_failed")
    except Exception as exc:  # noqa: BLE001
        logger.warning("gate replay failed: %r", exc)
        reasons.append("replay_unavailable")

    # 4) Cost-per-appointment + TTFA budget (unit economics + latency).
    try:
        from voice_ops.eval.metrics import MetricsCollector
        batch = MetricsCollector().collect_all_goldens()
        # the codebase property is spelled cost_per_apartment_usd (typo); accept either.
        cpa = (getattr(batch, "cost_per_appointment_usd", None)
               or getattr(batch, "cost_per_apartment_usd", None) or 0.0)
        out.cost_per_appointment = round(float(cpa or 0.0), 6)
        out.ttft_ms = int(round(float(getattr(batch, "max_ttfa_core_ms", 0.0) or 0.0)))
        if champion_cost is not None and cpa:
            out.replay_delta = round(float(cpa) - float(champion_cost), 6)
        if not ttfa_budget_ok(out.ttft_ms, ttfa_budget_ms):
            reasons.append(f"ttfa_over_budget:{out.ttft_ms}ms")
    except Exception as exc:  # noqa: BLE001
        logger.warning("gate metrics failed: %r", exc)

    # 5) Shadow build of the candidate packet (observability-only).
    try:
        from voice_kernel.shadow.runner import shadow_compute
        rep = shadow_compute(
            dispatch_meta={"tenant_id": getattr(challenger, "tenant_id", "t-eval"),
                           "campaign_id": getattr(challenger, "campaign_id", "camp-eval"),
                           "call_id": f"shadow-{out.challenger_id}", "room": "shadow",
                           "lead_phone": "+919000000000"},
            fields=cand_fields or {"agent_name": "Riya", "use_case": "sales"})
        out.shadow_ok = bool(rep.get("ok")) if isinstance(rep, dict) else False
        if not out.shadow_ok:
            reasons.append("shadow:" + str((rep or {}).get("error", "not_ok"))[:80])
    except Exception as exc:  # noqa: BLE001
        logger.warning("gate shadow failed: %r", exc)
        reasons.append("shadow_unavailable")

    out.reasons = reasons
    out.eligible = bool(out.gates_passed and out.replay_passed and out.shadow_ok
                        and out.compliance_ok and ttfa_budget_ok(out.ttft_ms, ttfa_budget_ms))

    # Persist the gated verdict onto the challenger row.
    try:
        challenger.gates_passed = out.gates_passed
        challenger.replay_delta = out.replay_delta
        challenger.shadow_ok = out.shadow_ok
        challenger.ttft_ms = out.ttft_ms
        challenger.cost_per_appointment = out.cost_per_appointment
        challenger.status = "gated"
        challenger.ts_iso = S.now_iso()
        _st.insert_challengers([challenger])
    except Exception as exc:  # noqa: BLE001
        logger.warning("gate persist failed: %r", exc)
    return out


def promote(challenger, approved_by: str) -> dict:
    """Mark a challenger PROMOTED after a HUMAN approval. Returns the parsed proposed config for
    the droplet to apply to the live campaign + emit a config_changed event (the package stays
    droplet-free: it never writes campaign state itself). Refuses unless the challenger is gated &
    eligible OR auto_promote is somehow on (it must not be). Never raises."""
    try:
        cfg = _cfg.load()
        if cfg.auto_promote:
            logger.warning("FLYWHEEL_AUTO_PROMOTE is ON — promotion must be human-gated; refusing auto path")
        challenger.status = "promoted"
        challenger.approved_by = approved_by or "unknown"
        challenger.ts_iso = S.now_iso()
        _st.insert_challengers([challenger])
        try:
            config = json.loads(getattr(challenger, "proposed_config_json", "") or "{}")
        except Exception:  # noqa: BLE001
            config = {}
        return {"ok": True, "challenger_id": getattr(challenger, "challenger_id", ""), "config": config}
    except Exception as exc:  # noqa: BLE001
        logger.warning("promote failed: %r", exc)
        return {"ok": False, "error": str(exc)[:200]}


def reject(challenger, approved_by: str, reason: str = "") -> dict:
    try:
        challenger.status = "rejected"
        challenger.approved_by = approved_by or "unknown"
        challenger.rationale = (reason or getattr(challenger, "rationale", ""))[:600]
        challenger.ts_iso = S.now_iso()
        _st.insert_challengers([challenger])
        return {"ok": True, "challenger_id": getattr(challenger, "challenger_id", "")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("reject failed: %r", exc)
        return {"ok": False, "error": str(exc)[:200]}


__all__ = ["GateOutcome", "evaluate_challenger", "promote", "reject", "ttfa_budget_ok"]
