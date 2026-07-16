"""voice_ops.flywheel.optimizer — Layer-D offline PROMPT IMPROVEMENT.

WHY THIS LAYER (and why it is OFFLINE-only)
-------------------------------------------
The bandit (bandit.py) tunes the SELECTION between existing arms; this layer GENERATES
the next arm. It mines the warehouse for the agent's own *winning plays* — the highest
fused-reward turns, grouped by the move they made — and turns them into a candidate
system-prompt instruction block (OPRO-style: "here is a leaderboard of variants and their
scores + feedback; write an improved instruction"). Optionally it runs DSPy MIPROv2 over a
labelled trainset to compile a stronger prompt.

THE HARD RULE: a candidate is never written live. The ONLY artefact this module emits is a
schema.Challenger with status='proposed'. That challenger must then pass OPE (ope.py), the
regression gates (incl. the compliance/honesty HARD gates in compliance.py), and a SHADOW
run with a HUMAN click before it can ever become a champion (config.auto_promote stays
False by law). This module proposes; humans + gates dispose.

DESIGN LAWS (mirror voice_ops/research/*.py + the rest of the flywheel):
  * Pure-python at import time. httpx (OpenRouter) and dspy (MIPROv2) are imported LAZILY
    inside the one function that needs them, wrapped so an absent dep degrades to a clean
    no-op (return the current prompt unchanged / an empty distillation) — NEVER an
    ImportError at module load, NEVER a raise into a caller.
  * DORMANT-SAFE: with no OPENROUTER_API_KEY the OPRO call returns current_prompt verbatim;
    with no dspy installed MIPRO returns current_prompt verbatim. The module imports and
    self-checks with zero network and zero ClickHouse.
  * HONEST SCIENCE: the distillation is grounded in real, reward-ranked rows; we never
    fabricate a "winning play". Anti-Goodhart: only outcome-anchored / capped-reward rows
    feed the leaderboard, so the optimizer can't chase an unbounded shaping term.
  * SIDE-PIPELINE: post-call / worker-time only. Never touches the live LiveKit turn loop.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Dict, List, Optional

from . import config as _cfg
from . import schema as S
from .schema import Challenger

logger = logging.getLogger("flywheel.optimizer")

# OpenRouter chat-completions endpoint (same as droplet_work/script_gen.py + judge.py).
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Bound the leaderboard / exemplar text we ever feed a model or store, so a runaway
# transcript can't blow the prompt size or the challenger config row.
_MAX_LEADERBOARD = 24
_TEXT_CLIP = 280
_FEEDBACK_CLIP = 600


# --------------------------------------------------------------------------- #
# Small local helpers (no heavy deps; mirror schema._f / research _finite style).
# --------------------------------------------------------------------------- #
def _f(v, d: float = 0.0) -> float:
    try:
        x = float(v)
        return d if x != x else x          # NaN guard
    except Exception:  # noqa: BLE001
        return d


def _s(v, clip: int = _TEXT_CLIP) -> str:
    try:
        return (str(v) if v is not None else "")[:clip]
    except Exception:  # noqa: BLE001
        return ""


def _row_reward(r: dict) -> float:
    """The reward a row is ranked by — prefer the capped/fused number (anti-Goodhart),
    fall back to the raw outcome only when nothing else is present."""
    for k in ("reward_capped", "reward", "fused", "reward_raw"):
        if k in (r or {}):
            return _f(r.get(k))
    return 0.0


# --------------------------------------------------------------------------- #
# distill_winning_plays — turn the top reward-ranked turns into prompt exemplars.
# --------------------------------------------------------------------------- #
def distill_winning_plays(top_rows: List[dict], *, max_examples: int = 8) -> dict:
    """Sort the agent's turns by capped reward (desc), keep the single best example PER
    move_type (so the few-shot covers the move palette, not 8 copies of one rebuttal),
    and emit a compact distillation:

        {'exemplars': [{'state','move','text','reward'} ...<=max_examples],
         'summary':   '<=6 winning-play bullets describing what worked'}

    Best-effort: malformed rows are skipped, never raised on. Empty input → empty bundle.
    """
    try:
        rows = [r for r in (top_rows or []) if isinstance(r, dict)]
        rows.sort(key=_row_reward, reverse=True)

        cap = max(1, int(max_examples or 8))
        exemplars: List[dict] = []
        seen_moves: set = set()
        bullets: List[str] = []

        for r in rows:
            move = _s(r.get("move_type") or "other", 32) or "other"
            if move in seen_moves:
                continue                      # de-dupe by move_type — one champion per move
            seen_moves.add(move)

            text = _s(r.get("agent_text") or r.get("text") or "")
            if not text:
                continue
            reward = round(_row_reward(r), 4)
            # state context the model can condition on (objection / temperature / regime).
            state = {
                "objection_type": _s(r.get("objection_type") or "none", 32),
                "lead_temperature": _s(r.get("lead_temperature") or "unknown", 16),
                "regime": _s(r.get("state_regime") or r.get("regime") or "steady", 24),
            }
            exemplars.append({"state": state, "move": move, "text": text, "reward": reward})

            if len(bullets) < 6:
                bullets.append(
                    f"On {state['objection_type']}/{state['lead_temperature']} "
                    f"({state['regime']}), the '{move}' move that scored {reward} said: "
                    f"\"{text[:120]}\""
                )
            if len(exemplars) >= cap:
                break

        summary = "Winning plays distilled from logged calls:\n- " + "\n- ".join(bullets) if bullets else ""
        return {"exemplars": exemplars, "summary": summary}
    except Exception as exc:  # noqa: BLE001
        logger.warning("distill_winning_plays error (non-fatal): %r", exc)
        return {"exemplars": [], "summary": ""}


# --------------------------------------------------------------------------- #
# build_feedback_string — rich textual feedback for ONE call (the OPRO signal).
# --------------------------------------------------------------------------- #
def build_feedback_string(call_row: dict) -> str:
    """Human-readable feedback the optimizer can reason over: the call's OUTCOME, the
    affect regimes it traversed, the judge's verdict, and (if derivable) which MOVE
    stalled the call. Pure-text, best-effort — never raises; '' on garbage in."""
    try:
        r = call_row or {}
        if not isinstance(r, dict):
            return ""

        outcome = _s(r.get("outcome") or r.get("result") or "unknown", 48)
        reward = _row_reward(r)
        parts: List[str] = [f"Outcome: {outcome} (reward {round(reward, 4)})."]

        temp = _s(r.get("lead_temperature") or "", 16)
        if temp:
            parts.append(f"Lead was {temp}.")

        # Regimes traversed — accept either a list or a single regime tag.
        regimes = r.get("regimes") or r.get("state_regime") or r.get("regime")
        if isinstance(regimes, (list, tuple)):
            seq = ", ".join(_s(x, 24) for x in regimes if x)
            if seq:
                parts.append(f"Affect regimes: {seq}.")
        elif regimes:
            parts.append(f"Affect regime: {_s(regimes, 24)}.")

        # Judge verdict (scalar + optional rationale).
        js = r.get("judge_score")
        if js is not None:
            jline = f"Judge score: {round(_f(js), 3)}"
            verdict = _s(r.get("judge_verdict") or r.get("judge_rationale") or "", 200)
            if verdict:
                jline += f" — {verdict}"
            parts.append(jline + ".")

        # Which move stalled — explicit field if the worker tagged one, else infer the
        # lowest-credit move from the per-turn breakdown when present.
        stalled = _s(r.get("stalled_move") or r.get("worst_move") or "", 48)
        if not stalled:
            turns = r.get("turns")
            if isinstance(turns, (list, tuple)) and turns:
                try:
                    worst = min(
                        (t for t in turns if isinstance(t, dict)),
                        key=lambda t: _f(t.get("credit_advantage"), 0.0),
                        default=None,
                    )
                    if worst is not None and _f(worst.get("credit_advantage"), 0.0) < 0:
                        stalled = _s(worst.get("move_type") or "", 48)
                except Exception:  # noqa: BLE001
                    stalled = ""
        if stalled:
            parts.append(f"The '{stalled}' move stalled the call (lowest credit).")

        return " ".join(p for p in parts if p)[:_FEEDBACK_CLIP]
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_feedback_string error (non-fatal): %r", exc)
        return ""


# --------------------------------------------------------------------------- #
# opro_propose — ONE OpenRouter call asking for an improved instruction block.
# --------------------------------------------------------------------------- #
def _format_leaderboard(leaderboard: List[dict]) -> str:
    """Render the (variant, score, feedback) leaderboard into a compact, bounded prompt."""
    lines: List[str] = []
    rows = [r for r in (leaderboard or []) if isinstance(r, dict)]
    # Highest score first so the model sees the strongest variants up top.
    rows.sort(key=lambda r: _f(r.get("score", r.get("reward"))), reverse=True)
    for i, r in enumerate(rows[:_MAX_LEADERBOARD], 1):
        variant = _s(r.get("variant") or r.get("variant_id") or r.get("arm_id") or f"v{i}", 60)
        score = round(_f(r.get("score", r.get("reward"))), 4)
        fb = _s(r.get("feedback") or r.get("rationale") or "", _FEEDBACK_CLIP)
        line = f"{i}. variant={variant} score={score}"
        if fb:
            line += f" | {fb}"
        lines.append(line)
    return "\n".join(lines)


def opro_propose(leaderboard: List[dict], current_prompt: str,
                 *, model: str = "", cfg=None) -> str:
    """v0 OPRO: a SINGLE OpenRouter chat call (same shape as judge.py / script_gen.py)
    that, given a scored leaderboard of prompt variants + per-variant feedback, returns an
    improved system-prompt instruction block.

    DORMANT-SAFE: returns `current_prompt` unchanged when there is no OPENROUTER_API_KEY,
    no leaderboard, the call fails, or the optimizer is disabled. Never raises; lazy httpx.
    """
    current = current_prompt or ""
    try:
        cfg = cfg or _cfg.load()
        key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        if not key:
            logger.info("opro_propose: no OPENROUTER_API_KEY → returning current prompt unchanged")
            return current

        board = _format_leaderboard(leaderboard)
        if not board:
            return current

        mdl = (model or getattr(cfg, "judge_model", "") or "anthropic/claude-3.5-sonnet").strip()

        system = (
            "You are an OPRO meta-optimizer improving the SYSTEM-PROMPT instruction block of a "
            "Hinglish real-estate OUTBOUND VOICE telecaller. You are given a leaderboard of prompt "
            "variants with their measured reward scores and feedback. Write ONE improved instruction "
            "block that should outscore the best variant. HARD CONSTRAINTS: stay fully compliant and "
            "honest — never make the agent pushy, manipulative, or deceptive; never invent facts, "
            "prices, or RERA/possession claims; keep it natural spoken Hinglish; do not lengthen "
            "needlessly. Return ONLY the improved instruction block as plain text, no preamble."
        )
        user = (
            "LEADERBOARD (variant, measured score, feedback — higher score is better):\n"
            f"{board}\n\n"
            "CURRENT INSTRUCTION BLOCK:\n"
            f"{current[:4000]}\n\n"
            "Now write the improved instruction block."
        )

        import httpx  # lazy: an absent httpx must not break module import
        with httpx.Client(timeout=float(os.getenv("FLYWHEEL_OPRO_TIMEOUT", "45"))) as c:
            r = c.post(
                _OPENROUTER_URL,
                headers={
                    "Authorization": "Bearer " + key,
                    "content-type": "application/json",
                    "HTTP-Referer": (os.getenv("PANEL_BASE_URL") or "https://haptica.famit.in"),
                    "X-Title": "Haptica Flywheel OPRO",
                },
                json={"model": mdl, "max_tokens": 1500, "temperature": 0.6,
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": user}]},
            )
        if r.status_code != 200:
            logger.warning("opro_propose: OpenRouter HTTP %s %s", r.status_code, (r.text or "")[:200])
            return current
        data = r.json()
        text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        text = (text or "").strip()
        return text or current
    except Exception as exc:  # noqa: BLE001
        logger.warning("opro_propose error (non-fatal): %r", exc)
        return current


# --------------------------------------------------------------------------- #
# mipro_optimize — LAZY DSPy MIPROv2 (absent dspy → no-op, return current prompt).
# --------------------------------------------------------------------------- #
def mipro_optimize(trainset: List, metric_fn: Callable,
                   *, current_prompt: str = "") -> str:
    """Compile a stronger system-prompt with DSPy's MIPROv2 over a labelled `trainset`
    scored by `metric_fn`.

    LAZY by law: `import dspy` happens inside this function; if dspy is not installed we
    return `current_prompt` unchanged (a clean no-op) and log the reason. Never raises.

    TODO(MIPROv2 wiring): the full implementation builds a dspy.Signature for the
    telecaller turn, wraps it in a dspy.Module, and runs
    `dspy.MIPROv2(metric=metric_fn).compile(module, trainset=trainset)`, then extracts the
    optimized instruction from the compiled program. That requires a configured dspy.LM
    (pointed at OpenRouter) and is gated on the same OPENROUTER_API_KEY; until that LM
    plumbing lands here this stays a guarded no-op so the package never hard-depends on
    dspy or on a live model.
    """
    current = current_prompt or ""
    try:
        if not trainset:
            return current
        try:
            import dspy  # noqa: F401  # lazy heavy dep — absent → graceful no-op
        except Exception:  # noqa: BLE001  (ImportError or a broken transitive dep)
            logger.info("mipro_optimize: dspy not installed → returning current prompt unchanged")
            return current

        # dspy IS present but the MIPROv2 program/LM wiring is intentionally not built yet
        # (see TODO above). Returning the current prompt keeps this a safe, honest no-op
        # rather than emitting a half-optimized prompt from an unconfigured LM.
        logger.info("mipro_optimize: dspy available but MIPROv2 wiring pending → no-op (TODO)")
        return current
    except Exception as exc:  # noqa: BLE001
        logger.warning("mipro_optimize error (non-fatal): %r", exc)
        return current


# --------------------------------------------------------------------------- #
# emit_challenger — the ONLY artefact this module produces (status='proposed').
# --------------------------------------------------------------------------- #
def emit_challenger(candidate: dict, *, tenant_id: str, campaign_id: str = "",
                    kind: str = "prompt", rationale: str = "") -> Challenger:
    """Wrap a proposed candidate config into a schema.Challenger (status='proposed').

    This is NOT a promotion — it only enqueues a proposal for the gating pipeline (OPE →
    regression gates incl. the compliance/honesty HARD gates → shadow → HUMAN approval).
    Best-effort: a malformed `candidate` still yields a valid Challenger (empty config),
    never raises.
    """
    import json
    try:
        try:
            config_json = json.dumps(candidate if candidate is not None else {}, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001
            config_json = "{}"

        k = _s(kind or "prompt", 24)
        if k not in S.CHALLENGER_KINDS:
            k = "prompt"

        return Challenger(
            tenant_id=_s(tenant_id or "", 120),
            challenger_id=S.new_id("ch_"),
            ts_iso=S.now_iso(),
            kind=k,
            campaign_id=_s(campaign_id or "", 120),
            proposed_config_json=config_json,
            rationale=_s(rationale or "", _FEEDBACK_CLIP),
            status="proposed",
            gates_passed=False,
            shadow_ok=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("emit_challenger error (non-fatal): %r", exc)
        # Last-ditch: a minimally-valid proposed challenger so the caller never gets None.
        return Challenger(tenant_id=str(tenant_id or "")[:120], challenger_id=S.new_id("ch_"),
                          ts_iso=S.now_iso(), kind="prompt", status="proposed")


__all__ = [
    "distill_winning_plays",
    "build_feedback_string",
    "opro_propose",
    "mipro_optimize",
    "emit_challenger",
]


# --------------------------------------------------------------------------- #
# Inline self-check — happy path, synthetic inputs, NO network / NO ClickHouse.
# --------------------------------------------------------------------------- #
if __name__ == "__main__":  # pragma: no cover
    import json as _json

    # 1) distill_winning_plays: de-dupe by move, sort by reward, cap.
    top_rows = [
        {"move_type": "objection_rebuttal", "objection_type": "price", "lead_temperature": "warm",
         "state_regime": "rising_friction", "agent_text": "Sir EMI option bhi hai, ₹25k/month se shuru.",
         "reward_capped": 1.42},
        {"move_type": "objection_rebuttal", "objection_type": "price", "lead_temperature": "warm",
         "agent_text": "(weaker dup rebuttal)", "reward_capped": 0.30},
        {"move_type": "cta_push", "objection_type": "none", "lead_temperature": "hot",
         "state_regime": "warming", "agent_text": "Is Saturday ko ek free site visit fix kar dun?",
         "reward_capped": 1.10},
        {"move_type": "empathize", "agent_text": "Samajh sakta hoon, decision bada hai.",
         "reward_capped": 0.65},
    ]
    distilled = distill_winning_plays(top_rows, max_examples=8)
    assert isinstance(distilled, dict) and "exemplars" in distilled and "summary" in distilled
    moves = [e["move"] for e in distilled["exemplars"]]
    assert len(moves) == len(set(moves)), "exemplars must be de-duped by move_type"
    assert moves[0] == "objection_rebuttal", "highest-reward move should rank first"
    assert distilled["summary"].startswith("Winning plays")
    print(f"distill: {len(distilled['exemplars'])} exemplars, moves={moves}")

    # 2) build_feedback_string: outcome + regime + judge + stalled move.
    call_row = {
        "outcome": "callback_scheduled", "reward_capped": 0.8, "lead_temperature": "warm",
        "regimes": ["steady", "rising_friction", "resolving"], "judge_score": 0.42,
        "judge_verdict": "warm and compliant, slightly slow to the ask",
        "turns": [
            {"move_type": "opening", "credit_advantage": 0.1},
            {"move_type": "price_reveal", "credit_advantage": -0.4},
            {"move_type": "cta_push", "credit_advantage": 0.3},
        ],
    }
    fb = build_feedback_string(call_row)
    assert fb and "callback_scheduled" in fb and "price_reveal" in fb, fb
    print(f"feedback: {fb}")

    # 3) opro_propose: DORMANT (clear any key) → returns current prompt unchanged.
    _saved = os.environ.pop("OPENROUTER_API_KEY", None)
    base_prompt = "You are Riya, a warm Hinglish real-estate telecaller. Be helpful and compliant."
    leaderboard = [
        {"variant": "champ", "score": 0.91, "feedback": "best closer; sometimes too fast to the ask"},
        {"variant": "chall_a", "score": 0.74, "feedback": "great rapport, weak CTA"},
    ]
    out = opro_propose(leaderboard, base_prompt)
    assert out == base_prompt, "dormant opro_propose must return current prompt unchanged"
    print("opro_propose dormant: returned current prompt unchanged ✓")

    # 4) mipro_optimize: dspy absent (or wiring pending) → returns current prompt unchanged.
    out2 = mipro_optimize([{"x": 1}], (lambda *_a, **_k: 1.0), current_prompt=base_prompt)
    assert out2 == base_prompt, "mipro_optimize must no-op to current prompt"
    print("mipro_optimize no-op: returned current prompt unchanged ✓")

    # 5) emit_challenger: valid proposed Challenger with serialized config.
    candidate = {"system_prompt": out, "distilled": distilled["summary"][:120]}
    ch = emit_challenger(candidate, tenant_id="t_demo", campaign_id="camp_1",
                         kind="prompt", rationale="distilled from 4 winning turns")
    assert isinstance(ch, Challenger) and ch.status == "proposed"
    assert ch.challenger_id.startswith("ch_") and ch.tenant_id == "t_demo"
    row = ch.to_row()
    assert row["status"] == "proposed" and row["gates_passed"] == 0
    parsed = _json.loads(ch.proposed_config_json)
    assert parsed.get("system_prompt") == out
    print(f"challenger: id={ch.challenger_id} kind={ch.kind} -> row keys={sorted(row)[:5]}...")

    if _saved is not None:  # restore env we mutated
        os.environ["OPENROUTER_API_KEY"] = _saved

    print("optimizer self-check OK")
