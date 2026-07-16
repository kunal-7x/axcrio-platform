"""voice_ops.research — Famit Research: instrumented conversation science (side-pipeline).

The premium, science-grade observability lab for voice calls. Every OTHER voice-AI
dashboard shows you WHAT happened (connected, lead hot, duration); Famit Research
measures the *dynamics* of HOW it happened — a calibrated, per-speaker-baselined
arousal / engagement-friction trace with real uncertainty bands, prosody time-series
(pitch contour, loudness, speaking rate, pause structure), and a closed-loop view of
which prompt/playbook variants actually move outcomes.

DESIGN LAWS (mirror voice_analytics / the kernel — the live call must NEVER be affected):
  * SIDE-PIPELINE ONLY. Nothing in this package runs on the live LiveKit turn loop.
    The cheap per-turn signal (ASR-derived speech rate, pause timing) is emitted
    fire-and-forget; the heavy acoustic + latent-affect work runs POST-CALL off the
    recording egress, in a separate process.
  * HONEST SCIENCE, NOT MARKETING. We deliberately do NOT ship the things that sound
    clinical but are wrong on 8 kHz telephony:
      - jitter/shimmer via std-of-diff of a frame-rate F0/RMS contour (that is not
        jitter/shimmer under any standard definition, needs glottal-cycle detection,
        is meaningless on 250 ms windows, and per the 2025 systematic review does not
        even predict stress) → optional, segment-aggregated, confidence-gated, NEVER
        a headline metric;
      - librosa.beat.beat_track for speech rate (a music tempo tracker) → replaced by
        ASR word-timestamps / de Jong-Wempe syllable nuclei;
      - PINN / UDE / "cognitive-friction PDE" / one-Adam-step-per-turn "training"
        (no governing law, no conserved quantity, numerically meaningless) → replaced
        by an honest online Bayesian filter (Kalman / EWMA leaky-integrator), which is
        the *correct* form of the very mean-reversion ODE the spec wrote.
  * EVERY NUMBER MAPS TO A PUBLISHED, VALIDATABLE METHOD. Confidence-gated features,
    in-product "low-confidence on 8 kHz telephony" badges, citations shown in the UI
    (AVEC-2016 Kalman affect tracking, eGeMAPS, de Jong-Wempe 2009). A latent you can
    not validate is not a measurement — outputs are labelled exploratory until a
    held-out validation harness lands.

Public surface kept tiny and dependency-light so callers (the recorder, the demo
generator, the offline worker) import exactly what they need:
  * schema.py       — the wire contract (ResearchTurn / ResearchSummary).
  * affect_filter.py— the latent affect tracker (pure-Python Kalman / EWMA). NO numpy
                      hard-dep so it runs anywhere and is trivially unit-testable.
  * features.py     — honest per-turn feature extraction with graceful degradation
                      (cheap ASR-metadata path always; librosa.pyin / parselmouth only
                      when installed, confidence-gated).
  * extractor.py    — orchestrates features → filter → ResearchTurn rows for a call.
  * demo.py         — scientifically-consistent synthetic calls (run through the REAL
                      filter) so the dashboard is alive before live data flows.
"""
from __future__ import annotations

from .schema import ResearchTurn, ResearchSummary  # noqa: F401
from .affect_filter import AffectTracker, AffectConfig  # noqa: F401

__all__ = ["ResearchTurn", "ResearchSummary", "AffectTracker", "AffectConfig"]
