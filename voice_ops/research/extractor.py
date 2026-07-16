"""voice_ops.research.extractor — turn a call into Famit Research rows.

Orchestrates: per caller turn → features (acoustic if audio present, else ASR-metadata) →
AffectTracker (the online Bayesian filter) → a `ResearchTurn`. Then summarises the call.

Designed to run POST-CALL in a SEPARATE process (off the LiveKit/agent event loop) so the
GIL-heavy librosa work can never contend with a live call (the verdict's explicit warning).
Pure orchestration; the only heavy work is inside features.extract_acoustics, which is itself
best-effort and degrades to the metadata path.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from .affect_filter import AffectConfig, AffectTracker
from .conformal import ConformalTrigger
from .dynamics import compute_dynamics
from .features import extract_acoustics, turn_features_from_metadata
from .llm_affect import llm_affect_for_turn
from .outcome import OutcomeModel
from .schema import ResearchSummary, ResearchTurn

logger = logging.getLogger("research.extractor")


def _iso(base_iso: str, t_sec: float) -> str:
    try:
        base = datetime.fromisoformat(base_iso.replace("Z", "+00:00")) if base_iso else datetime.now(timezone.utc)
    except Exception:  # noqa: BLE001
        base = datetime.now(timezone.utc)
    return (base + timedelta(seconds=float(t_sec or 0.0))).astimezone(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def extract_call(
    tenant_id: str,
    call_id: str,
    turns: List[Dict],
    *,
    sr: Optional[int] = None,
    started_iso: str = "",
    cfg: Optional[AffectConfig] = None,
    with_voice_quality: bool = False,
    llm: Optional[Callable[[str], str]] = None,
    outcome_model: Optional[OutcomeModel] = None,
    trigger: Optional[ConformalTrigger] = None,
) -> List[ResearchTurn]:
    """`turns`: ordered FULL turn stream (caller + agent). Each dict may carry:
        transcript, audio_duration_s, silence_s, turn_latency_ms, t_sec, turn_num, speaker,
        audio (mono float waveform → acoustic path), ssl_arousal/ssl_conf (live SER tap).
    Caller turns drive the multimodal filter (Arousal←SER/prosody, Friction←LLM, Engagement←dynamics);
    agent turns inform conversational dynamics. Then a per-turn conversion-risk curve + conformal
    intervene flag are computed. `llm` (optional) wires the real affect sensor; else a heuristic."""
    tracker = AffectTracker(cfg)
    dyn = compute_dynamics(turns)                       # {stream_index: dynamics-dict}
    out: List[ResearchTurn] = []
    n = 0
    ctx: List[str] = []
    for i, t in enumerate(turns):
        spk = (t.get("speaker") or "caller")
        if spk != "caller":
            ctx.append(f"agent: {(t.get('transcript','') or '')[:120]}")
            ctx = ctx[-4:]
            continue
        n += 1
        transcript = t.get("transcript", "") or ""
        audio = t.get("audio")
        if audio is not None and sr:
            feats = extract_acoustics(audio, int(sr), transcript=transcript,
                                      turn_latency_ms=t.get("turn_latency_ms", 0.0),
                                      with_voice_quality=with_voice_quality)
        else:
            feats = turn_features_from_metadata(
                transcript=transcript, audio_duration_s=t.get("audio_duration_s", 0.0),
                silence_s=t.get("silence_s", 0.0), turn_latency_ms=t.get("turn_latency_ms", 0.0))
        # Upgrade #1 — LLM-as-valence/friction sensor (or heuristic fallback).
        la = llm_affect_for_turn(transcript, context="\n".join(ctx), llm=llm)
        feats["llm_friction_z"] = la["llm_friction_z"]
        feats["llm_conf"] = la["llm_conf"]
        # Upgrade #2 — conversational-dynamics engagement observation.
        d = dyn.get(i, {})
        for k in ("engagement_obs", "engagement_conf"):
            if k in d:
                feats[k] = d[k]
        # Upgrade #3 — live learned-arousal tap (when the realtime worker attached it to the turn).
        if t.get("ssl_arousal") is not None:
            feats["ssl_arousal"] = t["ssl_arousal"]
            feats["ssl_conf"] = t.get("ssl_conf", 0.8)

        st = tracker.update(feats)
        t_sec = float(t.get("t_sec", i) or 0.0)
        rt = ResearchTurn(
            tenant_id=tenant_id, call_id=call_id, turn_num=int(t.get("turn_num", n)),
            ts_iso=_iso(started_iso, t_sec), t_sec=round(t_sec, 2), speaker="caller",
            f0_mean_hz=feats.get("f0_mean_hz", 0.0), f0_range_hz=feats.get("f0_range_hz", 0.0),
            f0_slope_hz_s=feats.get("f0_slope_hz_s", 0.0), f0_var_hz=feats.get("f0_var_hz", 0.0),
            loudness_db=feats.get("loudness_db", 0.0), speech_rate_sps=feats.get("speech_rate_sps", 0.0),
            pause_ratio=feats.get("pause_ratio", 0.0), turn_latency_ms=feats.get("turn_latency_ms", 0.0),
            voiced_sec=feats.get("voiced_sec", 0.0),
            arousal=st.arousal, arousal_var=st.arousal_var,
            friction=st.friction, friction_var=st.friction_var,
            engagement=st.engagement, engagement_var=st.engagement_var,
            valence_hint=feats.get("valence_hint", 0.0),
            llm_valence=la.get("llm_valence"), intent=la.get("intent", ""),
            objection=la.get("objection"), buying_intent=la.get("buying_intent"),
            talk_share=d.get("talk_share"), backchannel_rate=d.get("backchannel_rate"),
            entrainment=d.get("entrainment"), ssl_arousal=t.get("ssl_arousal"),
            confidence=st.confidence, source=feats.get("source", "asr_metadata"),
            regime=st.regime, low_conf=bool(feats.get("low_conf", False)),
            jitter_local=feats.get("jitter_local"), shimmer_local=feats.get("shimmer_local"),
            hnr_db=feats.get("hnr_db"), transcript=transcript[:280],
        )
        out.append(rt)
        ctx.append(f"customer: {transcript[:120]}")
        ctx = ctx[-4:]

    # Phase 2 — per-turn conversion-risk curve + conformal intervene trigger.
    _apply_risk(out, outcome_model or OutcomeModel(), trigger or ConformalTrigger())
    return out


def _apply_risk(turns: List[ResearchTurn], model: OutcomeModel, trigger: ConformalTrigger) -> None:
    if not turns:
        return
    seq = [{"friction": t.friction, "arousal": t.arousal, "engagement": t.engagement,
            "turn_latency_ms": t.turn_latency_ms, "intent": t.intent,
            "buying_intent": t.buying_intent} for t in turns]
    risk = model.risk_curve(seq)
    for i, t in enumerate(turns):
        t.conversion_risk = risk[i]
        rising = i == 0 or risk[i] >= risk[i - 1]
        t.intervene = trigger.fire(risk[i], rising=rising)


def summarize(
    turns: List[ResearchTurn], *, duration_s: float = 0.0, started_iso: str = "",
    outcome: str = "", converted: Optional[bool] = None, deal_value: float = 0.0,
) -> ResearchSummary:
    if not turns:
        return ResearchSummary(started_iso=started_iso, outcome=outcome, converted=converted, deal_value=deal_value)
    # header timestamp = explicit call start, else the first turn's stamped time (NOT "now").
    started = started_iso or turns[0].ts_iso
    ar = [t.arousal for t in turns]
    fr = [t.friction for t in turns]
    eng = [t.engagement for t in turns]
    rates = [t.speech_rate_sps for t in turns if t.speech_rate_sps > 0]
    f0s = [t.f0_mean_hz for t in turns if t.f0_mean_hz > 0]
    pauses = [t.pause_ratio for t in turns]
    risks = [t.conversion_risk for t in turns if t.conversion_risk is not None]
    intents = [t.intent for t in turns if t.intent]
    regimes: List[str] = []
    for t in turns:                                  # ordered, de-duplicated run of regimes
        if t.regime != "steady" and (not regimes or regimes[-1] != t.regime):
            regimes.append(t.regime)
    return ResearchSummary(
        tenant_id=turns[0].tenant_id, call_id=turns[0].call_id, started_iso=started, turns=len(turns),
        duration_s=round(duration_s or (turns[-1].t_sec - turns[0].t_sec), 1),
        arousal_mean=round(sum(ar) / len(ar), 1), arousal_peak=round(max(ar), 1),
        friction_mean=round(sum(fr) / len(fr), 1), friction_peak=round(max(fr), 1),
        arousal_trend=round(ar[-1] - ar[0], 1), friction_trend=round(fr[-1] - fr[0], 1),
        engagement_mean=round(sum(eng) / len(eng), 1), engagement_peak=round(max(eng), 1),
        engagement_trend=round(eng[-1] - eng[0], 1),
        conversion_risk=round(risks[-1], 1) if risks else 0.0,
        intervene=any(t.intervene for t in turns),
        top_intent=Counter(intents).most_common(1)[0][0] if intents else "",
        f0_mean_hz=round(sum(f0s) / len(f0s), 1) if f0s else 0.0,
        speech_rate_sps=round(sum(rates) / len(rates), 2) if rates else 0.0,
        pause_ratio=round(sum(pauses) / len(pauses), 3),
        confidence=round(sum(t.confidence for t in turns) / len(turns), 3),
        source=(lambda ss: next(iter(ss)) if len(ss) == 1 else "mixed")({t.source for t in turns}),
        regimes=regimes,
        outcome=outcome, converted=converted, deal_value=deal_value,
    )
