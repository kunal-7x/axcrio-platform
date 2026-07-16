"""voice_ops.flywheel.trajectory — Layer-A trajectory capture (the dataset seed).

This is where a finished voice call first becomes RL fuel. Every other layer of the
Flywheel (reward fusion, credit assignment, preference mining, the bandit, OPE, the
optimizer) reads the rows this module writes — so the science is only as honest as the
(state, action, reward) tuples we lay down here.

WHY this module is SYNC + in-memory only
-----------------------------------------
`capture_finalized` runs on the droplet's call-finalize path (via asyncio.to_thread, OFF
the LiveKit turn loop). It must be FAST and must NEVER block on the network: the per-turn
affect trace (arousal/friction from Famit Research) lags the call by seconds-to-minutes,
so we deliberately DO NOT read ClickHouse here. We capture what is already in memory — the
transcript + the droplet call record (the live policy arm + the terminal outcome) — and
write a NEUTRAL-state seed row per agent turn (`low_conf=True`, neutral friction/arousal).
The worker later joins `famit_research_turns` and the RLAIF judge to ENRICH these seeds in
place (the trajectories table is a ReplacingMergeTree keyed on (call, turn), so the
enriched row collapses the seed — read with FINAL).

WHAT a trajectory row is
------------------------
One row per AGENT turn = one RL (state, action, reward) unit:
  * action  — the agent's text this turn, tagged to a MOVE_TYPE (+ the OBJECTION_TYPE it
              answered) and stamped with the live arm (model/voice/variant) + its propensity
              (load-bearing for honest off-policy estimation downstream).
  * state   — neutral here; the worker fills state_friction/arousal/regime from affect.
  * reward  — computed ONCE per call: the terminal outcome (capped + deal-multiplied) is
              distributed across turns by credit assignment, and the terminal turn carries
              the fused, provenance-stamped RewardComponents. We NEVER emit a fused number
              without its parts (honest science), and the outcome term is the only thing
              optimised — compliance lives in its own hard gate, never here.

HONEST SCIENCE / DORMANT-SAFE: every public function swallows its own errors (→ WARNING)
and degrades to a clean empty/zero value. `capture_finalized` returns 0 rather than ever
raising into the finalize path; this module imports even with no ClickHouse / no deps.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from . import config as _cfg
from . import credit
from . import reward
from . import schema as S
from . import store as _st

logger = logging.getLogger("flywheel.trajectory")


# --------------------------------------------------------------------------- #
# Rule-based taggers (pure, deterministic, Hinglish-aware) — no model calls.
# These run on the hot finalize path, so they are cheap substring/keyword rules;
# the worker can upgrade tags later if a richer tagger ships.
# --------------------------------------------------------------------------- #
def _norm(text: str) -> str:
    """Lowercased, whitespace-collapsed copy — safe on any input (None → '')."""
    try:
        return " ".join((text or "").lower().split())
    except Exception:  # noqa: BLE001
        return ""


def _any(hay: str, needles) -> bool:
    return any(n in hay for n in needles)


# Objection cue tables (Hinglish romanised + English). Order matters: the first
# matching family wins, so the table is ordered most-specific → least-specific.
_OBJ_CUES = (
    ("price", ("price", "costly", "mehng", "mehang", "budget", "expensive",
               "afford", "rupee", "rupay", "paisa", "daam", "rate")),
    ("loan", ("loan", "emi", "finance", "down payment", "downpayment",
              "interest rate", "instal", "kist", "bank")),
    ("location", ("location", "area", "door", "far", "durr", "dur ", "distance",
                  "metro", "connectivity", "kaha hai")),
    ("timing", ("busy", "baad", "later", "abhi nahi", "abhi nahin", "time nahi",
                "time nahin", "no time", "call later", "phir", "abhi busy")),
    ("rera", ("rera",)),
    ("possession", ("possession", "ready to move", "ready-to-move", "kab milega",
                    "handover", "hand over", "completion", "ready hai")),
    ("trust", ("trust", "fraud", "genuine", "scam", "fake", "bharosa", "dhoka",
               "cheat")),
    ("spouse_decision", ("wife", "husband", "family", "discuss", "patni", "pati",
                         "ghar me", "ghar mein", "spouse", "partner se")),
    ("already_bought", ("already", "le liya", "liya hai", "bought", "purchase kar",
                        "khareed liya", "kharid liya", "book kar diya")),
    ("not_interested", ("not interested", "nahi chahiye", "nahin chahiye",
                        "mat karo", "interested nahi", "interested nahin",
                        "no interest", "nahi karna")),
)


def tag_objection(caller_text: str) -> str:
    """Rule-based map of a CALLER turn → one of schema.OBJECTION_TYPES.

    Best-effort and deterministic. Returns 'none' on empty/unmatched input (never
    raises). The first matching family in `_OBJ_CUES` wins (specific → generic)."""
    try:
        hay = _norm(caller_text)
        if not hay:
            return "none"
        for obj, cues in _OBJ_CUES:
            if _any(hay, cues):
                return obj
        return "none"
    except Exception:  # noqa: BLE001
        return "none"


# Move cue tables for the AGENT turn. Evaluated with priority logic in tag_move
# (a price frame beats a generic probe, an objection answer beats inform, etc.).
_MV_OPENING = ("hello", "hi ", "namaste", "namaskar", "good morning", "good afternoon",
               "good evening", "main bol", "mai bol", "calling from", "ki taraf se",
               "baat kar raha", "baat kar rahi", "my name is", "mera naam")
# NOTE: a bare "budget" is intentionally NOT here — *asking* about budget is a probe;
# price_reveal means the agent is STATING a number (lakh/crore/₹/"starting at ...").
_MV_PRICE = ("price", "lakh", "lac", "crore", "cr ", "₹", "rs.", "rs ", "rupee", "rupay",
             "starting at", "shuru hota", "per sq", "psf", "cost is", "daam", "keemat")
_MV_CTA = ("site visit", "visit", "book", "appointment", "aaiye", "aaye", "milte",
           "schedule", "aa jaiye", "dekhne", "dekh lijiye", "slot", "chalte hai",
           "chaliye", "visit kar")
_MV_HANDOFF = ("senior", "manager", "team", "callback", "call back", "expert",
               "specialist", "colleague", "transfer", "connect you", "connect kar")
_MV_PROBE = ("?", "kya", "kab", "kaha", "kahan", "kitna", "kitne", "budget kya",
             "konsa", "kaunsa", "how about", "would you", "aap ka", "aapka",
             "tell me", "bataiye")
_MV_EMPATHIZE = ("samajh", "bilkul", "no problem", "koi baat nahi", "sure", "of course",
                 "i understand", "samajhta", "samajhti", "right", "sahi", "absolutely")
_MV_CLOSE = ("thanks", "thank you", "dhanyavaad", "dhanyawad", "bye", "goodbye",
             "shukriya", "have a", "great day", "milte hai phir", "alvida")


def tag_move(agent_text: str, prior_state: dict = None, objection_type: str = "none") -> str:
    """Rule-based map of an AGENT turn → one of schema.MOVE_TYPES.

    Priority (most load-bearing move wins): objection_rebuttal (when the caller raised a
    live objection — the most salient move to measure, so it beats a loose greeting match)
    → opening → price_reveal → cta_push → handoff_offer → probe → empathize → close →
    inform → other. `prior_state` is accepted for future state-aware tagging but is
    intentionally unused on the hot path. Never raises."""
    try:
        hay = _norm(agent_text)
        if not hay:
            return "other"
        # 1) the agent is answering a LIVE objection (caller raised one the prior turn). A live
        #    objection dominates — "which move handled the objection" is the founder's key question,
        #    so this wins over a loose opening/greeting keyword match.
        if objection_type and objection_type != "none":
            return "objection_rebuttal"
        # 2) opening / who-am-I-why-calling.
        if _any(hay, _MV_OPENING):
            return "opening"
        # 3) explicit price / budget framing.
        if _any(hay, _MV_PRICE):
            return "price_reveal"
        # 4) ask for the next step.
        if _any(hay, _MV_CTA):
            return "cta_push"
        # 5) offer a human / senior callback.
        if _any(hay, _MV_HANDOFF):
            return "handoff_offer"
        # 6) discovery / qualifying question.
        if _any(hay, _MV_PROBE):
            return "probe"
        # 7) acknowledge / rapport.
        if _any(hay, _MV_EMPATHIZE):
            return "empathize"
        # 8) wrap.
        if _any(hay, _MV_CLOSE):
            return "close"
        # 9) a product fact / USP (has some substance but matched nothing above).
        if len(hay) >= 12:
            return "inform"
        return "other"
    except Exception:  # noqa: BLE001
        return "other"


# --------------------------------------------------------------------------- #
# State + lead-temperature mapping.
# --------------------------------------------------------------------------- #
def _temperature_from_rec(rec: dict) -> str:
    """Map the droplet record's interest/outcome → a schema.LEAD_TEMPERATURES bucket.

    Prefers an explicit `lead_temperature`/`interest` field, then infers from the
    terminal outcome (a booked visit ⇒ hot, a hard 'not interested' ⇒ cold/dead).
    Returns 'unknown' when nothing is decodable. Never raises."""
    try:
        rec = rec or {}
        # explicit signal first.
        for key in ("lead_temperature", "temperature", "interest"):
            v = _norm(str(rec.get(key, "")))
            if v in S.LEAD_TEMPERATURES:
                return v
            if v in ("high", "interested", "positive"):
                return "hot"
            if v in ("medium", "maybe", "lukewarm"):
                return "warm"
            if v in ("low", "negative"):
                return "cold"
        # infer from outcome.
        outcome = _norm(str(rec.get("outcome", "")))
        if _any(outcome, ("booked", "site_visit", "visit", "callback", "scheduled", "hot")):
            return "hot"
        if _any(outcome, ("interested", "warm", "follow")):
            return "warm"
        if _any(outcome, ("not_interested", "not interested", "dnd", "do_not")):
            return "cold"
        if _any(outcome, ("dead", "wrong_number", "invalid", "disconnected")):
            return "dead"
        return "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def build_state(turn_row: dict) -> dict:
    """Project a turn dict → the neutral state vector this layer can know without affect.

    On the finalize path we have NO affect yet (Famit Research lags), so friction/arousal
    default to the neutral 50.0 the schema uses and `regime` to 'steady'. The worker
    overwrites these from `famit_research_turns`. Honours any pre-filled values a caller
    already attached. Never raises."""
    try:
        turn_row = turn_row or {}
        return {
            "friction": S._f(turn_row.get("state_friction", turn_row.get("friction", 50.0)), 50.0),
            "arousal": S._f(turn_row.get("state_arousal", turn_row.get("arousal", 50.0)), 50.0),
            "regime": str(turn_row.get("state_regime", turn_row.get("regime", "steady")) or "steady"),
            "lead_temperature": str(turn_row.get("lead_temperature", "unknown") or "unknown"),
            "vertical": str(turn_row.get("vertical", "real_estate") or "real_estate"),
        }
    except Exception:  # noqa: BLE001
        return {"friction": 50.0, "arousal": 50.0, "regime": "steady",
                "lead_temperature": "unknown", "vertical": "real_estate"}


# --------------------------------------------------------------------------- #
# Transcript normalisation — tolerate the several shapes a transcript can arrive in.
# --------------------------------------------------------------------------- #
_AGENT_ROLES = ("agent", "assistant", "bot", "riya", "ai")
_CALLER_ROLES = ("caller", "user", "customer", "lead", "human")


def _speaker_of(turn: dict) -> str:
    """Normalise a turn's speaker → 'agent' | 'caller' | '' (unknown)."""
    raw = _norm(str(turn.get("speaker", turn.get("role", "")) or ""))
    if raw in _AGENT_ROLES:
        return "agent"
    if raw in _CALLER_ROLES:
        return "caller"
    # tolerate prefixes like 'agent:' / 'user_1'.
    if any(raw.startswith(a) for a in _AGENT_ROLES):
        return "agent"
    if any(raw.startswith(c) for c in _CALLER_ROLES):
        return "caller"
    return ""


def _text_of(turn: dict) -> str:
    for k in ("text", "transcript", "content", "message"):
        v = turn.get(k)
        if v:
            return str(v)
    return ""


def _normalize_transcript(transcript, rec: dict) -> List[dict]:
    """Coerce the transcript (explicit arg → rec['transcript'] → rec['turns']) into an
    ordered list of {'speaker','text','turn_num','t_sec'}. Returns [] if nothing usable."""
    src = transcript
    if not src:
        src = (rec or {}).get("transcript") or (rec or {}).get("turns")
    if not src or not isinstance(src, (list, tuple)):
        return []
    out: List[dict] = []
    for i, t in enumerate(src):
        if not isinstance(t, dict):
            # tolerate a bare ('agent', 'text') tuple/list.
            if isinstance(t, (list, tuple)) and len(t) >= 2:
                t = {"speaker": t[0], "text": t[1]}
            else:
                continue
        out.append({
            "speaker": _speaker_of(t),
            "text": _text_of(t),
            "turn_num": int(t.get("turn_num", t.get("index", i)) or i),
            "t_sec": S._f(t.get("t_sec", t.get("ts_sec", 0.0)), 0.0),
        })
    return out


def _pair_agent_turns(norm: List[dict]) -> List[dict]:
    """Walk the transcript and emit one record per AGENT turn, each paired with the
    MOST RECENT preceding CALLER turn (the turn that prompted the agent's action)."""
    paired: List[dict] = []
    last_caller = ""
    for t in norm:
        sp = t["speaker"]
        if sp == "caller":
            last_caller = t["text"]
        elif sp == "agent":
            paired.append({
                "turn_num": t["turn_num"],
                "agent_text": t["text"],
                "caller_text": last_caller,
                "t_sec": t["t_sec"],
            })
            last_caller = ""  # consumed; a following agent turn pairs with '' unless a new caller speaks
        else:
            # unknown speaker: treat non-empty text as a caller context clue, don't emit a row.
            if t["text"] and not last_caller:
                last_caller = t["text"]
    return paired


# --------------------------------------------------------------------------- #
# capture_finalized — the SYNC, never-raises finalize hook (Layer-A seed write).
# --------------------------------------------------------------------------- #
def capture_finalized(tenant_id: str, call_id: str, rec: dict, transcript=None) -> int:
    """Build + persist the trajectory SEED for a finished call. SYNC, fast, never raises.

    Returns the number of rows written (0 on any failure or when dormant). Called off the
    loop via asyncio.to_thread from `flywheel.on_call_finalized`.

    Flow:
      1) normalise the transcript (arg → rec['transcript'] → rec['turns']); if nothing is
         usable, write ONE coarse close-row (turn_num=0) so the call is still counted.
      2) per AGENT turn → a neutral-state TrajectoryRow stamped with the live arm + tags.
      3) compute the terminal reward ONCE (reward.outcome_from_rec → reward.terminal_reward),
         credit-assign it across turns (credit.assign), and attach the fused, provenance-
         stamped RewardComponents (reward.fuse) to the LAST (terminal) turn.
      4) best-effort INSERT (store.insert_trajectories) — a no-op when dormant.
    """
    try:
        cfg = _cfg.load()
        tenant_id = str(tenant_id or "")
        call_id = str(call_id or "")
        rec = rec or {}

        campaign_id = str(rec.get("campaign_id", "") or "")
        vertical = str(rec.get("vertical", "real_estate") or "real_estate")
        lead_temp = _temperature_from_rec(rec)
        arm_model = str(rec.get("chosen_model", rec.get("arm_model", "")) or "")
        arm_voice = str(rec.get("chosen_voice", rec.get("arm_voice", "")) or "")
        arm_variant = str(rec.get("variant_id", rec.get("arm_variant", "")) or "")
        propensity = S._f(rec.get("propensity", 1.0), 1.0)
        ts = S.now_iso()

        # ---- 1) transcript → paired agent turns ----------------------------- #
        norm = _normalize_transcript(transcript, rec)
        paired = _pair_agent_turns(norm)

        rows: List[S.TrajectoryRow] = []
        if not paired:
            # Nothing usable: one coarse seed row so the call still lands in the warehouse.
            rows.append(S.TrajectoryRow(
                tenant_id=tenant_id, call_id=call_id, turn_num=0, ts_iso=ts,
                campaign_id=campaign_id, vertical=vertical, lead_temperature=lead_temp,
                move_type="close", objection_type="none",
                arm_model=arm_model, arm_voice=arm_voice, arm_variant=arm_variant,
                propensity=propensity, low_conf=True,
                agent_text="", caller_text="",
            ))
        else:
            for p in paired:
                objection = tag_objection(p["caller_text"])
                move = tag_move(p["agent_text"], None, objection)
                rows.append(S.TrajectoryRow(
                    tenant_id=tenant_id, call_id=call_id, turn_num=int(p["turn_num"]),
                    ts_iso=ts, campaign_id=campaign_id, vertical=vertical,
                    lead_temperature=lead_temp, move_type=move, objection_type=objection,
                    arm_model=arm_model, arm_voice=arm_voice, arm_variant=arm_variant,
                    propensity=propensity,
                    # neutral state — the worker fills affect from famit_research_turns.
                    state_friction=50.0, state_arousal=50.0, state_regime="steady",
                    low_conf=True,
                    agent_text=p["agent_text"], caller_text=p["caller_text"],
                ))

        # ---- 2) terminal reward, computed ONCE ------------------------------ #
        try:
            outcome_key, deal_value = reward.outcome_from_rec(rec)
            raw_outcome, capped_outcome = reward.terminal_reward(outcome_key, deal_value, cfg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("flywheel trajectory: terminal reward failed for %s: %r", call_id, exc)
            raw_outcome, capped_outcome = 0.0, 0.0

        # ---- 3) credit assignment across turns ------------------------------ #
        # Hand credit.assign lightweight turn dicts (it only needs move/objection/order).
        turns_as_dicts = [{
            "turn_num": r.turn_num, "move_type": r.move_type,
            "objection_type": r.objection_type, "lead_temperature": r.lead_temperature,
        } for r in rows]
        credits: List[float] = []
        try:
            credits = credit.assign(turns_as_dicts, capped_outcome, (0.0, 1.0), cfg=cfg) or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("flywheel trajectory: credit.assign failed for %s: %r", call_id, exc)
            credits = []
        # Align the credit vector to the rows (pad/truncate defensively).
        if len(credits) != len(rows):
            padded = list(credits)[:len(rows)]
            padded += [0.0] * (len(rows) - len(padded))
            credits = padded
        for r, adv in zip(rows, credits):
            r.credit_advantage = S._f(adv, 0.0)

        # ---- 4) terminal turn carries the fused, provenance-stamped reward --- #
        last = rows[-1]
        last.reward_raw = S._f(raw_outcome, 0.0)
        last.reward_capped = S._f(capped_outcome, 0.0)
        terminal_credit = last.credit_advantage if credits else S._f(capped_outcome, 0.0)
        try:
            comps = reward.fuse(
                terminal_credit=terminal_credit,
                affect_delta=0.0,            # no affect on the seed; worker enriches
                judge_score=0.0,             # unjudged at capture time
                confidence=0.0, judge_model_id="", rubric_version=cfg.rubric_version,
                disagreement=False, cfg=cfg,
            )
            last.reward_components_json = comps.to_json()
            last.rubric_version = cfg.rubric_version
        except Exception as exc:  # noqa: BLE001
            logger.warning("flywheel trajectory: reward.fuse failed for %s: %r", call_id, exc)

        # ---- persist (best-effort; no-op when dormant) ---------------------- #
        _st.insert_trajectories(rows)
        logger.info("flywheel trajectory: captured %d seed row(s) for call %s", len(rows), call_id)
        return len(rows)
    except Exception as exc:  # noqa: BLE001
        # The finalize path must NEVER break because of the flywheel.
        logger.warning("flywheel trajectory.capture_finalized error (non-fatal) for %s: %r",
                       call_id, exc)
        return 0


# --------------------------------------------------------------------------- #
# assemble_call — ASYNC enriched read: trajectory seed ⨝ Famit Research affect.
# --------------------------------------------------------------------------- #
async def assemble_call(tenant_id: str, call_id: str) -> List[dict]:
    """Return the enriched per-turn trajectory for one call: the captured rows joined
    (on turn_num) with the per-turn affect trace from `famit_research_turns` when present.

    Best-effort: returns the bare trajectory on any affect-read failure, and [] on a total
    failure. Never raises."""
    try:
        base = await _st.read_trajectory(tenant_id, call_id)
        turns = list(base.get("turns") or [])
        if not turns:
            return []

        # Pull the affect trace for this call (best-effort; absent → no enrichment).
        affect_by_turn: Dict[int, dict] = {}
        try:
            res = await _st._ch(
                "SELECT turn_num, arousal, friction, regime, confidence, low_conf "
                "FROM famit_research_turns "
                "WHERE tenant_id = {tid:String} AND call_id = {cid:String} "
                "ORDER BY turn_num ASC LIMIT 5000",
                {"tid": str(tenant_id or ""), "cid": str(call_id or "")},
            )
            for row in (res.get("rows") or []):
                try:
                    affect_by_turn[int(row.get("turn_num", 0) or 0)] = row
                except Exception:  # noqa: BLE001
                    continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("flywheel trajectory.assemble_call affect read failed for %s: %r",
                           call_id, exc)

        # Merge affect into each trajectory turn (only fill when the affect channel exists).
        for t in turns:
            try:
                tn = int(t.get("turn_num", 0) or 0)
            except Exception:  # noqa: BLE001
                tn = 0
            aff = affect_by_turn.get(tn)
            if not aff:
                continue
            if aff.get("friction") is not None:
                t["state_friction"] = S._f(aff.get("friction"), t.get("state_friction", 50.0))
            if aff.get("arousal") is not None:
                t["state_arousal"] = S._f(aff.get("arousal"), t.get("state_arousal", 50.0))
            if aff.get("regime"):
                t["state_regime"] = str(aff.get("regime"))
            if aff.get("confidence") is not None:
                t["confidence"] = S._f(aff.get("confidence"), t.get("confidence", 0.0))
            if aff.get("low_conf") is not None:
                t["low_conf"] = bool(aff.get("low_conf"))
        return turns
    except Exception as exc:  # noqa: BLE001
        logger.warning("flywheel trajectory.assemble_call error (non-fatal) for %s: %r",
                       call_id, exc)
        return []


__all__ = [
    "tag_objection", "tag_move", "build_state",
    "capture_finalized", "assemble_call",
]


# --------------------------------------------------------------------------- #
# Inline self-check — happy path on synthetic inputs (NO network / NO ClickHouse).
# Dormant by default (FLYWHEEL_ENABLED unset) so the INSERT is a clean no-op; this
# exercises tagging, pairing, credit alignment, fusion + the coarse-row fallback.
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # 1) taggers --------------------------------------------------------------- #
    assert tag_objection("ye to bahut mehnga hai, budget nahi hai") == "price"
    assert tag_objection("mujhe loan chahiye, EMI kitni hogi") == "loan"
    assert tag_objection("location bahut door hai metro se") == "location"
    assert tag_objection("abhi busy hoon, baad me call karna") == "timing"
    assert tag_objection("RERA registered hai kya?") == "rera"
    assert tag_objection("possession kab milega?") == "possession"
    assert tag_objection("wife se discuss karna hoga") == "spouse_decision"
    assert tag_objection("maine already ek flat le liya hai") == "already_bought"
    assert tag_objection("nahi chahiye, not interested") == "not_interested"
    assert tag_objection("") == "none"
    assert tag_objection("haan theek hai bataiye") == "none"

    assert tag_move("Namaste, main Riya bol rahi hoon DLF ki taraf se") == "opening"
    assert tag_move("Price 85 lakh se shuru hota hai") == "price_reveal"
    assert tag_move("Bilkul samajhta hoon, koi baat nahi", None, "price") == "objection_rebuttal"
    assert tag_move("Aap site visit ke liye aaiye, slot book kar dun?") == "cta_push"
    assert tag_move("Main aapko senior manager se connect kar deti hoon") == "handoff_offer"
    assert tag_move("Aapka budget kitna hai?") == "probe"
    assert tag_move("Bilkul, no problem sir") == "empathize"
    assert tag_move("Dhanyavaad, have a great day") == "close"
    assert tag_move("Is project me clubhouse aur swimming pool included hai") == "inform"
    assert tag_move("") == "other"

    # 2) build_state ----------------------------------------------------------- #
    st = build_state({"lead_temperature": "warm"})
    assert st["friction"] == 50.0 and st["regime"] == "steady" and st["lead_temperature"] == "warm"

    # 3) full happy-path capture (dormant → INSERT is a no-op, returns rows count) #
    transcript = [
        {"speaker": "agent", "text": "Namaste, main Riya bol rahi hoon Prestige ki taraf se"},
        {"speaker": "caller", "text": "haan boliye"},
        {"speaker": "agent", "text": "Aapka budget kitna hai is project ke liye?"},
        {"speaker": "user", "text": "thoda mehnga lag raha hai, price zyada hai"},
        {"speaker": "assistant", "text": "Bilkul samajhti hoon, EMI option bhi hai"},
        {"speaker": "caller", "text": "acha possession kab milega?"},
        {"speaker": "agent", "text": "Aap site visit ke liye aaiye, main slot book kar deti hoon"},
    ]
    rec = {
        "campaign_id": "camp_demo", "vertical": "real_estate", "interest": "high",
        "outcome": "site_visit_booked", "chosen_model": "scout-17b",
        "chosen_voice": "riya-hi", "variant_id": "v3", "propensity": 0.42,
        "deal_value": 8_500_000.0,
    }
    n = capture_finalized("tenant_demo", "call_demo_1", rec, transcript)
    assert n == 4, f"expected 4 agent rows, got {n}"  # 4 agent turns in the transcript

    # 4) coarse-row fallback (no transcript anywhere) -------------------------- #
    n2 = capture_finalized("tenant_demo", "call_demo_2", {"outcome": "not_interested"}, None)
    assert n2 == 1, f"expected 1 coarse fallback row, got {n2}"

    # 5) tuple-shaped transcript + rec['turns'] fallback ----------------------- #
    rec3 = {"turns": [("agent", "Hello ji"), ("caller", "kaun?"), ("agent", "Main Riya")]}
    n3 = capture_finalized("tenant_demo", "call_demo_3", rec3, None)
    assert n3 == 2, f"expected 2 agent rows from rec['turns'], got {n3}"

    print(f"[trajectory self-check OK] capture rows: {n}, fallback: {n2}, tuple-shape: {n3}")
