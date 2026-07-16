"""droplet_work.flywheel_app — thin droplet glue between caller.py and voice_ops.flywheel.

Isolates the few droplet-specific concerns (the finalize-hook adapter + the dispatch-time arm
selection) so the voice_ops.flywheel package stays droplet-free and unit-testable. EVERYTHING here
is best-effort + dormant-safe: a missing package / disabled flag / any error is a silent no-op so a
flywheel hiccup can NEVER break the call-finalize path or the dial loop (mirrors the grow glue).
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("flywheel.app")

try:
    import voice_ops.flywheel as _flywheel          # the package (active()/on_call_finalized)
    from voice_ops.flywheel import config as _fwcfg
except Exception:  # noqa: BLE001 — package absent ⇒ glue is inert
    _flywheel = None
    _fwcfg = None


def active() -> bool:
    try:
        return bool(_flywheel and _flywheel.active())
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# 1) post-call capture (called from caller._finalize_call via asyncio.to_thread)
# --------------------------------------------------------------------------- #
def on_call_finalized_hook(tenant_id: str, rec: dict, tr: dict | None = None, transcript=None) -> None:
    """Adapt the droplet (rec, tr) → the package's on_call_finalized(tenant_id, call_id, rec, transcript).
    Folds the per-call truth `tr` (booked / site_visit / deal_value / opt_out / interest) onto `rec` so
    reward.outcome_from_rec sees the strongest outcome signal. Never raises."""
    try:
        if not active():
            return
        rec = dict(rec or {})
        tr = tr or {}
        # fold the strongest reward signals from tr onto rec (reward.outcome_from_rec reads these)
        if tr.get("booked") or tr.get("appointment") or tr.get("site_visit"):
            rec["booked"] = True
        if tr.get("opt_out"):
            rec["opt_out"] = True
        if tr.get("callback_at") or tr.get("commitment"):
            rec["callback"] = True
        for k in ("deal_value", "interest", "site_visit"):
            if k in tr and k not in rec:
                rec[k] = tr[k]
        call_id = rec.get("id") or rec.get("call_id") or ""
        if not call_id:
            return
        # prefer an explicit transcript; else the droplet may have stashed turns on tr/rec
        tx = transcript or tr.get("turns") or rec.get("turns") or rec.get("transcript")
        _flywheel.on_call_finalized(tenant_id, call_id, rec, tx)
    except Exception as exc:  # noqa: BLE001 — flywheel must NEVER break finalize
        logger.warning("flywheel finalize hook error (non-fatal): %r", exc)


# --------------------------------------------------------------------------- #
# 2) dispatch-time arm selection (the ONLY live-path touch — a local dict read)
# --------------------------------------------------------------------------- #
def _policy_path(tenant_id: str) -> str:
    base = (os.getenv("FAMIT_VAR") or os.getenv("FAMIT_VAR_DIR") or "famit-var").strip() or "famit-var"
    return os.path.join(base, "flywheel", f"policy_{tenant_id}.json")


def select_arm_for_dispatch(tenant_id: str, campaign_id: str, context: dict | None = None) -> dict:
    """Pick a VARIANT arm for this dial from the worker's precomputed policy snapshot (a local JSON
    read — NEVER a ClickHouse/inference call on the live path). Returns {'variant_id', 'propensity'}
    or {} (⇒ caller keeps its existing round-robin = byte-identical). Dormant unless bandit_active.
    Never raises."""
    try:
        if not (_fwcfg and _fwcfg.load().bandit_active()):
            return {}
        path = _policy_path(tenant_id)
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            snap = json.load(f)
        variant_arms = [a for a in (snap.get("knobs", {}).get("variant") or [])
                        if a.get("campaign_id") == campaign_id and a.get("arm_id")]
        if not variant_arms:
            return {}
        from voice_ops.flywheel import bandit
        from voice_ops.flywheel.schema import ArmPosterior
        cfg = _fwcfg.load()
        arms = [ArmPosterior(tenant_id=tenant_id, campaign_id=campaign_id, knob="variant",
                             arm_id=a["arm_id"], alpha=float(a.get("alpha", 1) or 1),
                             beta=float(a.get("beta", 1) or 1), plays=int(a.get("plays", 0) or 0),
                             guardrail_optout_rate=float(a.get("optout_rate", 0) or 0))
                for a in variant_arms]
        # respect the guardrail: drop arms whose opt-out rate is unsafe (never explore harm)
        safe = [a for a in arms if bandit.guardrails(a, max_optout=0.15).get("ok", True)] or arms
        arm_id, propensity = bandit.select_arm(safe, epsilon=cfg.bandit_epsilon,
                                               explore_cap=cfg.bandit_explore_cap)
        if not arm_id:
            return {}
        return {"variant_id": arm_id, "propensity": round(float(propensity), 5)}
    except Exception as exc:  # noqa: BLE001 — never break dispatch
        logger.warning("select_arm_for_dispatch error (non-fatal): %r", exc)
        return {}


def stamp_arm(rec: dict, fields: dict | None = None, md_obj: dict | None = None,
              arm: dict | None = None) -> None:
    """Record the FINAL policy arm on the call record so the flywheel can correlate outcome↔arm.
    Pure metadata — harmless whether or not the bandit is on. Never raises."""
    try:
        fields = fields or {}
        md_obj = md_obj or {}
        override = md_obj.get("fields_override") or {}
        rec["chosen_model"] = (override.get("llm_model") or fields.get("llm_model")
                               or os.getenv("GROQ_LLM_MODEL", "") or "default")
        rec["chosen_voice"] = (override.get("voice_id") or fields.get("voice_id")
                               or os.getenv("ELEVENLABS_VOICE_ID", "") or "default")
        if md_obj.get("variant_id") and not rec.get("variant_id"):
            rec["variant_id"] = md_obj["variant_id"]
        if arm and arm.get("propensity") is not None:
            rec["propensity"] = arm["propensity"]
        else:
            rec.setdefault("propensity", 1.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("stamp_arm error (non-fatal): %r", exc)


__all__ = ["active", "on_call_finalized_hook", "select_arm_for_dispatch", "stamp_arm"]
