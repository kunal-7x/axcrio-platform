# Famit Research — instrumented conversation science

The premium, science-grade observability lab for voice calls. Every other voice-AI dashboard shows
you **what** happened (connected, lead hot, duration). Famit Research measures the **dynamics of how**
it happened — a calibrated, per-speaker-baselined **Arousal / Friction** latent state *with real
uncertainty bands*, prosody time-series (pitch contour, loudness, speaking rate, pause structure),
regime flags, and a closed-loop view of which trajectory shapes actually move outcomes.

It is built on a deliberately **honest** subset of an ambitious original spec. Three independent
adversarial reviews (with citations) found large parts of that spec to be marketing-grade; this
module keeps the genuinely-real ideas and replaces the broken ones with published, validatable
methods — while preserving the entire impressive dashboard vision.

## What we kept vs replaced (and why)

| Original spec | Verdict | What this module ships |
|---|---|---|
| Jitter/shimmer via `std(diff(piptrack))` as headline stress signal | ❌ not jitter/shimmer under any definition; meaningless on 250 ms of 8 kHz telephony; doesn't predict stress | Optional parselmouth jitter/shimmer/HNR over ≥1 s voiced speech, **confidence-gated, never headline** (`features._voice_quality`) |
| `librosa.beat.beat_track` for speech rate | ❌ a music tempo tracker (category error) | de Jong & Wempe (2009) intensity-peak syllable nuclei + ASR-derived rate (`features._syllable_nuclei_rate`) |
| `librosa.piptrack` for F0 | ⚠️ dated | pYIN (`librosa.pyin`) voiced-frame F0 stats |
| PINN / UDE / "cognitive-friction PDE" + one-Adam-step-per-turn "training" | ❌ no governing law, no conserved quantity, numerically meaningless | An online **Kalman filter** (linear-Gaussian state space) — `affect_filter.py` |
| Mean-reversion ODE `d(state)/dt = -γ(state−baseline)` | ✅ real | Kept as the **Ornstein-Uhlenbeck process model** (its discrete solution is the EWMA baseline mode) |
| Affect as a smooth latent state | ✅ real, published (AVEC-2016) | The core model |
| 500–700 ms RTT on Groq/Cerebras + ElevenLabs/Deepgram | ✅ achievable on existing infra | Live path **untouched** — research is a post-call side-pipeline |

The credibility moat is **intellectual honesty made visible**: confidence-gated features, in-product
"low-confidence on 8 kHz telephony" badges, `source`/`demo` provenance on every number, and citations
shown in the UI. This is more convincing to a sophisticated buyer than a confident fake "stress score".

## The model (defensible, real-time, validatable)

State `x = [arousal, friction]ᵀ` in z-units relative to the **caller's own opening (~first turns)
baseline** (so "high arousal" means high *for this speaker*). Process: mean-reverting OU
(`x_t = a·x_{t-1} + w`). Observation: a fixed, documented linear combination of z-scored prosody
features, with **measurement noise scaled by 1/confidence** so 8 kHz uncertainty shows up as honest
±1σ bands (the filter covariance). Citable to Somandepalli et al., *Online Affect Tracking with
Multimodal Kalman Filters*, AVEC-2016. No gradient "training"; no sigmoid-of-noise.

Unit tests: `python3 -m voice_ops.research.tests.test_affect_filter` (10 property tests — mean
reversion, confidence-weighting, regime detection, real pYIN F0 tracking).

## Files

```
voice_ops/research/
  affect_filter.py   # Kalman / EWMA latent affect tracker (pure-Python, zero hard deps)
  features.py        # honest feature extraction (ASR-metadata cheap path + librosa/parselmouth offline)
  extractor.py       # per-call: features → filter → ResearchTurn rows + ResearchSummary
  schema.py          # the wire contract (ResearchTurn / ResearchSummary)
  demo.py            # scientifically-consistent synthetic calls (real filter, scripted archetypes)
  seed.py            # populate ClickHouse with demo calls (verify the write path)
  tests/             # property tests for the scientific core
droplet_work/
  research_analytics.py  # ResearchRecorder → ClickHouse (mirrors voice_analytics.py; FAMIT_RESEARCH_ENABLED)
  research_query.py      # tenant-scoped reads (mirrors obs_query.py) + demo fallback
deploy/observability/voice_analytics.sql   # + famit_research_turns / famit_research_calls DDL
famit-panel/app/research/  # the premium dashboard (page + _charts + _overview/_call/_outcomes)
```

## Enable it

1. Apply the DDL once on the obs ClickHouse: `deploy/observability/voice_analytics.sql` (adds the two
   `famit_research_*` tables).
2. Set `FAMIT_RESEARCH_ENABLED=1` (+ `CLICKHOUSE_URL`) on the backend.
3. (Optional) seed a demo: `FAMIT_RESEARCH_ENABLED=1 CLICKHOUSE_URL=… python3 -m voice_ops.research.seed --tenant <id>`.
4. Grant the `mod.research` entitlement to the tenant (super-admin). The nav entry + `/research` route
   are gated by it.

Reads always work even before any of this — they fall back to a clearly-labelled `demo:true` dataset
(the real filter over scripted archetype calls) so the dashboard is alive day one.

**Endpoints** (tenant-scoped, `resolve_tenant`): `GET /research/dashboard?minutes=`,
`GET /research/call/{call_id}`, `GET /research/health`.

## Advanced upgrades (v2 — from the power/latency deep-research)

A second deep-research pass (papers + adversarial verification) found the biggest wins are NOT a giant
acoustic model (on 8 kHz telephony the SSL valence gain is ~80% *linguistic*, which we already have),
so the multimodal design leans on signals we already produce:

- **#1 LLM-as-valence/friction sensor** (`llm_affect.py`) — the LLM (or a bilingual heuristic) emits a
  structured affect/intent read → the Friction observation. Friction is ~80% linguistic (Wagner TPAMI-2023;
  AlloSat text CCC .92 vs acoustic .81). Highest ROI, +0 latency.
- **#2 Conversational-dynamics Engagement axis** (`dynamics.py`) — talk-share, response latency,
  backchannels, prosodic entrainment (Levitan & Hirschberg NAACL-2012). Pure arithmetic.
- **#3 Live learned-arousal tap** (`realtime.py`, `agent_tap.py`) — a 2nd `rtc.AudioStream` + a SER ONNX
  (or librosa proxy) in a **separate process** → `ssl_arousal`. CPU-only, RTF << 1, no GPU.
- **#4 Conversion-risk head** (`outcome.py`) — a calibrated per-turn risk *curve* (logistic over the
  trajectory; `.fit()` learns from your won/lost labels) replacing "trend = last − first".
- **#5 Conformal intervene trigger** (`conformal.py`) — split-conformal + Conformal-PID for a guaranteed
  false-alarm rate, replacing hand-set `friction>60` thresholds.
- **#6 Kalman tuning** — arousal→friction coupling + observation delay (Huang Interspeech-2017), in the
  now multi-axis `affect_filter.py`.
- **#7 Adaptive-TTS loop** (`adaptive_tts.py`, `live.py`) — affect → ElevenLabs speed/stability at the next
  turn; mirror rate/loudness, **never pitch** (Benus 2018). Gated, kill-switched.

The filter is now an N-D multimodal Kalman (Arousal / Friction / Engagement) with per-axis
confidence-weighted noise — each axis observed by its best modality. 31 tests
(`test_affect_filter` + `test_advanced` + `test_realtime`).

In-call flags (default OFF — validate on a real Vobiz call first with
`python3 -m voice_ops.research.validate_tap`):
`FAMIT_RESEARCH_REALTIME`, `FAMIT_SER_ONNX_PATH`, `FAMIT_RESEARCH_ADAPTIVE_TTS`.

## Deliberately NOT wired yet (live-call safety)

To keep the live LiveKit turn loop **provably untouched**, this slice does not modify the hot agent
path. Two follow-ups complete the live data flow and each needs a real call test before merge:

1. **Cheap in-call emit** — in `droplet_work/agent.py` `_MirrorAgent.on_user_turn_completed`, after the
   kernel `on_turn` returns, emit `voice_kernel.events.taxonomy.acoustic_metrics(...)` (the factory is
   already added) fire-and-forget through the existing EventBus with a hard timeout. NO raw PCM (not
   exposed at the turn boundary) — just `STTMetrics.audio_duration` + transcript word count + VAD pause.
2. **Heavy post-call extract** — on `RECORDING_READY` in `voice_ops/recording/pipeline.py`, spawn
   `voice_ops.research.extractor.extract_call(...)` in a **separate process** (GIL safety) over the
   egress audio and `research_analytics.persist_call(...)` the result.

Both consume the same `ResearchTurn` contract this slice already proved end-to-end.

3. **In-call real-time loop** (Phases 3-4) — all machinery is built + unit-tested in `realtime.py` /
   `agent_tap.py` / `adaptive_tts.py` / `live.py`, bundled so the agent wiring is TWO guarded lines:

   ```python
   # in agent.py entrypoint, after ctx.connect():
   from voice_ops.research import live as _res_live
   _research = _res_live.maybe_start(ctx.room, tenant_id=tid, call_id=cid, llm=_affect_llm)  # None if flags OFF
   # at the END of on_user_turn_completed (inside its existing try):
   if _research:
       _research.on_turn(txt, apply_prosody=_threadsafe_prosody_apply)   # _threadsafe_prosody_apply
       # mirrors _apply_language_switch: run_coroutine_threadsafe → tts.update_options(voice_settings=...)
   ```

   Left for the user to merge **after a real Vobiz call** clears the SIP #690 PCM-silence risk and the
   adaptive-TTS pre-warm timing — because `update_options` touches the live TTS (dead-air history). With
   both flags off, `maybe_start` returns None and the agent is byte-identical to today.

## Citations

AVEC-2016 Kalman affect tracking · Wagner et al. TPAMI-2023 (linguistic valence) · AlloSat (telephone
text-vs-acoustic) · Levitan & Hirschberg NAACL-2012 (entrainment↔rapport) · Huang Interspeech-2017
(Kalman delay+dynamics) · Wav2Small / audeering w2v2-dim (CPU SER) · Conformal Risk Control (ICLR-2024) ·
de Jong & Wempe 2009 · Benus 2018 (entrain rate/intensity, never pitch). See the in-product **Method** panels.

AVEC-2016 Kalman affect tracking · eGeMAPS (openSMILE) · de Jong & Wempe 2009 (syllable nuclei) ·
Ornstein-Uhlenbeck / leaky-integrator. See the in-product **Method** panels.
