"""voice_ops.research.dynamics — conversational-dynamics / entrainment features (the Engagement axis).

Upgrade #2 from the deep-research plan, and the single biggest NEW signal: rapport/engagement lives
in the TIMING of the conversation, not just one speaker's prosody. Levitan & Hirschberg (NAACL-2012,
Columbia Games Corpus) tie acoustic-prosodic ENTRAINMENT to both labelled rapport AND objective task
success; turn-taking latency, talk-share, backchannels and overlap are classic engagement markers.

Everything here is PURE ARITHMETIC over timestamps we ALREADY capture (speaker, t_sec, duration,
transcript, reply latency) — zero new models, real-time per turn, CPU-trivial. It produces, per CALLER
turn, an `engagement_obs` scalar that feeds the filter's Engagement axis (the filter z-scores it
against the caller's own baseline), plus the component features for the dashboard.

Direction (documented, first-order): engagement RISES with quick replies, balanced talk-share, active
backchannelling; FALLS with long reply latency, long pauses, agent-dominated talk, and silence.
"""
from __future__ import annotations

import re
from typing import Dict, List

# short acknowledgement tokens (English + Hinglish) used to detect backchannels / active listening.
_BACKCHANNELS = {"mm", "mmhmm", "mm-hmm", "hmm", "ok", "okay", "yeah", "yes", "right", "haan",
                 "ha", "achha", "accha", "theek", "sahi", "ji", "hmm-hmm", "uh-huh", "got it"}


def _is_backchannel(text: str, dur_s: float) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return dur_s < 0.8
    words = re.findall(r"[a-z'ऀ-ॿ]+", t)
    if len(words) <= 2 and dur_s < 1.4:
        return True
    return bool(words) and all(w in _BACKCHANNELS for w in words)


def compute_dynamics(turns: List[Dict], *, window: int = 4) -> Dict[int, Dict]:
    """Given the ORDERED full turn stream (caller + agent dicts with speaker/t_sec/audio_duration_s/
    transcript/turn_latency_ms), return {caller_turn_index_in_stream: dynamics-dict}. The dynamics
    dict carries the component features + a composite `engagement_obs` for the affect filter.
    """
    out: Dict[int, Dict] = {}
    caller_dur = agent_dur = 0.0          # rolling talk time (decayed by window)
    recent_caller_durs: List[float] = []
    recent_agent_durs: List[float] = []
    bc_window: List[int] = []
    prev_caller_rate = None
    for i, t in enumerate(turns):
        spk = (t.get("speaker") or "caller")
        dur = float(t.get("audio_duration_s", t.get("voiced_sec", 0.0)) or 0.0)
        rate = float(t.get("speech_rate_sps", 0.0) or 0.0)
        if spk == "caller":
            recent_caller_durs.append(dur)
        else:
            recent_agent_durs.append(dur)
        recent_caller_durs = recent_caller_durs[-window:]
        recent_agent_durs = recent_agent_durs[-window:]
        if spk != "caller":
            continue

        cdur = sum(recent_caller_durs) or 0.0
        adur = sum(recent_agent_durs) or 0.0
        talk_share = cdur / (cdur + adur) if (cdur + adur) > 0 else 0.5

        latency_ms = float(t.get("turn_latency_ms", 0.0) or 0.0)
        latency_s = latency_ms / 1000.0
        pause_ratio = float(t.get("pause_ratio", 0.0) or 0.0)
        bc = _is_backchannel(t.get("transcript", ""), dur)
        bc_window.append(1 if bc else 0)
        bc_window = bc_window[-window:]
        backchannel_rate = sum(bc_window) / len(bc_window) if bc_window else 0.0

        # prosodic entrainment proxy: how stable is the caller's speech rate (low |Δrate| = entrained).
        entrainment = 0.0
        if prev_caller_rate is not None and rate > 0 and prev_caller_rate > 0:
            entrainment = 1.0 - min(1.0, abs(rate - prev_caller_rate) / max(prev_caller_rate, 1e-6))
        if rate > 0:
            prev_caller_rate = rate

        # composite engagement (documented weights; the filter z-scores this vs the caller baseline).
        # talk-balance peaks near 0.5 (a one-sided monologue, either way, is less engaged).
        talk_balance = 1.0 - abs(talk_share - 0.5) * 2.0           # 1 at .5, 0 at 0/1
        engagement_obs = (
            -0.40 * min(latency_s, 3.0)        # quicker reply ⇒ more engaged
            + 0.20 * talk_balance
            + 0.20 * backchannel_rate
            + 0.20 * entrainment
            - 0.30 * pause_ratio               # long silence ⇒ disengaged
        )

        out[i] = {
            "engagement_obs": round(engagement_obs, 4),
            "engagement_conf": 0.7,            # timing is reliable even on 8 kHz (no acoustics needed)
            "talk_share": round(talk_share, 3),
            "backchannel": bool(bc),
            "backchannel_rate": round(backchannel_rate, 3),
            "entrainment": round(entrainment, 3),
            "response_latency_ms": round(latency_ms, 1),
        }
    return out
