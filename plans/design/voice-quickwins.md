# PHASE 0 — VOICE QUICK-WINS — EXECUTION-READY SPEC
Owner persona: VOICE-LATENCY-ENG. Status: design (build agent implements verbatim).
Verdict context: STRANGLE & EVOLVE. The live call earns money RIGHT NOW. Every change here is
**ADDITIVE, behind an env flag, with VAD fallback, crash-safe per unit, instantly revertible**.
Nothing ships unverified by a real bidirectional call + the regression gate.

> READ-ONLY grounding done. Citations below are `file:line` against the LOCAL source of truth
> `C:\Users\kunal\Desktop\caps\droplet_work\` (which is `md5`-tracked equal to the deployed
> `/opt/famit-agent/`). DO NOT trust line numbers blindly at implement time — `grep` the anchor
> string first (the brain warns deployed copy can differ by CRLF only; normalize before concluding stale).

---

## 0. SCOPE (exactly three deliverables, in order)

1. **PRE-FLIGHT** — prove the LiveKit semantic turn-detector model (`MultilingualModel`, ~396 MB,
   open-weight ONNX) actually LOADS + RUNS on the live box (`livekit-plugins-turn-detector`
   installed in the agent venv, CPU headroom, assets downloaded). This GATES everything else.
   The master plan flags the "$0 flip-one-line" framing as overstated — verify before claiming.
2. **Semantic turn-detection swap** — `agent.py` `turn_detection="vad"` → `MultilingualModel()`
   behind flag `TURN_DETECTION` (values `vad` | `semantic`), with automatic VAD fallback if the
   model fails to construct. Default ships `vad` (no behavior change) until the real call passes.
2b. **Semantic swap also REQUIRES raising `max_endpointing_delay`** — with the model turn-detector
   this is the "user is mid-thought, wait" patience window. Left at the VAD-era 0.45s the agent
   finalizes the user's turn after 0.45s of silence REGARDLESS of the model, cutting the USER off
   mid-sentence (the exact thing this wave exists to fix). Context7's own `MultilingualModel()`
   example pairs it with `max_endpointing_delay=5.0`. Under `semantic` we raise the default to ~1.8s.
3. **Adaptive barge-in** — distinguish backchannel from a true interrupt at the RIGHT layer:
   prefer native `min_interruption_words` (~2) so a bare "haan" won't interrupt but "ruko, price
   batao" will; raise `min_interruption_duration` 0.25 -> ~0.45 (env, already wired); enable
   `resume_false_interruption` so a false barge-in resumes the agent's sentence; keep a cheap
   `backchannel.py` as belt-and-suspenders.

Out of scope (later phases, do NOT touch): Postgres, dynamic JSON context/RAG, prompt rewrites,
Logto, the FSM. Keep the existing prompt, STT=`unknown`, EL flash_v2_5, Groq scout/rotation.

---

## 1. ENVIRONMENT FACTS (pinned — do not re-derive, do not guess)

| Fact | Value |
|---|---|
| Box (voice+backend) | `famit-livekit` `168.144.153.145` |
| SSH | `ssh -i C:\Users\kunal\.ssh\do-blr-test\id_ed25519 famit@168.144.153.145` (user `famit`, sudo) |
| Agent code dir | `/opt/famit-agent/` (deploy target) |
| **Agent venv (TRAP)** | **`/opt/capsy-agent/.venv`** — livekit plugins live HERE, NOT in famit-agent. ALL pip/python probes MUST use `/opt/capsy-agent/.venv/bin/python`. (HANDOFF.md:550, build_log/wave-P0-security.md:11, brain/playbooks.md:21) |
| Agent service | systemd `famit-agent` (agent_name `capsy`, http port 8090) |
| Backend service | systemd `famit-caller` (uvicorn :8209) — NOT touched by this wave |
| Restart (agent only) | `sudo systemctl restart famit-agent` (do NOT restart famit-caller for this wave; no caller.py change) |
| Env file | `/opt/famit-agent/.env` (agent loads it: agent.py:35) |
| Public API | `https://panel.famit.in/api` ; auth header `X-Auth: FamitCall2026` |
| Test ring number | `6375548830` (founder answers) |
| Test campaign | Shapoorji `c17e55e9f3` (HANDOFF) or DLF `66c3b656af` |
| Local deploy key | `C:\Users\kunal\.ssh\do-blr-test\id_ed25519` |

### SSH/quoting traps (brain/mistakes.md 2026-06-05) — the build agent WILL hit these:
- Use **PowerShell** for ssh (the Bash tool mangles `C:\…\id_ed25519` backslashes → Permission
  denied). OR use forward-slash key path `C:/Users/.../id_ed25519` in the Bash tool.
- Pass the **remote command SINGLE-quoted** so PowerShell does not expand `$(...)` locally.
- Nested `python -c "…"` over ssh strips inner quotes → **scp a small `.py` to `/tmp` and run it**
  with the venv python. This pattern "worked first try every time."
- `journalctl -u … -f` streaming over ssh dies in this harness (Monitor exits 255). To watch a
  call, POLL in a short background loop that re-attaches ssh per iteration and greps for the
  terminal marker `transcript saved`.

---

## 2. THE CURRENT CODE (anchors for the diff)

`agent.py` builds ONE `AgentSession` at `entrypoint` (agent.py:324). The session block today
(agent.py:487-524), trimmed to the lines we change:

```python
session = AgentSession(
    stt=sarvam.STT(... language="unknown" ...),            # ~488  KEEP
    llm=groq.LLM(... max_completion_tokens=140 ...),        # ~498  KEEP
    tts=tts,                                                # 512   KEEP
    vad=silero.VAD.load(),                                  # 513   KEEP (now also the fallback)
    preemptive_generation=True,                             # 515   KEEP
    min_endpointing_delay=float(os.getenv("MIN_EP_DELAY", "0.25")),  # 516 KEEP
    max_endpointing_delay=float(os.getenv("MAX_EP_DELAY", "0.45")),  # 517 see note
    aec_warmup_duration=0.0,                                # 518   KEEP
    min_interruption_duration=float(os.getenv("MIN_INT_DUR", "0.25")),  # 521 CHANGE DEFAULT 0.25->0.45
    false_interruption_timeout=1.0,                         # 522   KEEP (pairs w/ resume flag)
    turn_detection="vad",                                   # 523   CHANGE -> flagged MultilingualModel|"vad"
)
```

Imports today (agent.py:23): `from livekit.plugins import elevenlabs, groq, sarvam, silero`
— `turn_detector` is NOT imported yet.

The per-turn user hook already exists: `_MirrorAgent.on_user_turn_completed(self, turn_ctx, new_message)`
(agent.py:666-696). This is where backchannel handling hooks in — it already extracts the user text
robustly (`text_content()` / `content`, list-join) at agent.py:672-678. **Reuse that extraction.**

There is NO `prewarm`/`JobProcess` today; `WorkerOptions(entrypoint_fnc=…, agent_name=…, port=…)`
only (agent.py:730-738). VAD is loaded per-job inline at agent.py:513 (acceptable; we keep it).

Probe script already on disk: `droplet_work/_inspect_td.py` (imports
`livekit.plugins.turn_detector.multilingual.MultilingualModel`, prints its signature). Use it in
the pre-flight (scp to box, run with the venv python).

`langdetect.py` is the existing cheap, network-free, per-turn text classifier (`classify_text`,
`LanguageTracker`) — we extend its lexicon idea for backchannels but in a NEW tiny module so we
don't perturb the language path.

---

## 3. API CONFIRMED (LiveKit Agents v1.x — via context7 /livekit/agents)

- Install: `pip install livekit-plugins-turn-detector`.
- Import + use:
  ```python
  from livekit.plugins.turn_detector.multilingual import MultilingualModel
  session = AgentSession(..., turn_detection=MultilingualModel(), vad=silero.VAD.load(), ...)
  ```
  VAD is STILL passed alongside the semantic model (silence/VAD remains the co-pilot; the EOU
  model decides *semantic* end-of-turn). This matches our keeping `vad=silero.VAD.load()`.
- Model assets are downloaded out-of-band by: `python -m livekit.agents download-files`
  (downloads ALL configured plugin assets, incl. the turn-detector ONNX + tokenizer, ~396 MB,
  to the HF cache). This is the asset-download step the master plan calls out.
- `MultilingualModel()` takes no required args (the inspect probe prints the real signature).

> If `download-files` is not wired to fetch the turn-detector asset in this version, the first
> `MultilingualModel()` construction downloads lazily — but that adds cold latency to the FIRST
> call and risks a job timeout. The pre-flight MUST pre-download so production never downloads
> on the call hot path.

---

## 4. STEP ORDER (each step = one verifiable unit; verify+record before the next)

Crash-safe rule: do ONE unit → run its ACCEPTANCE TEST → append result to
`droplet_work/STATE_VOICE_QUICKWINS.md` (mark `IN PROGRESS`→`DONE`) → only then start the next.
A box backup precedes every deploy.

### STEP 1 — PRE-FLIGHT (read-only on the box; NO behavior change; NO restart)  [model: opus]
Goal: a YES/NO answer to "does `MultilingualModel` load + run on this box, with headroom?"

1.1 **Snapshot headroom** (so we can prove no regression and that there's room for the model):
```
ssh ... 'nproc; free -m; uptime; df -h /; systemctl is-active famit-agent famit-caller'
```
Record: cores, free RAM (MB), load avg, disk free on `/`. Pass bar: free RAM ≥ ~700 MB head
(the model footprint is small at inference; the 396 MB is the on-disk asset) AND disk free ≥ ~1.5 GB.

1.2 **Confirm livekit-agents version + plugin presence** in the AGENT venv:
```
ssh ... '/opt/capsy-agent/.venv/bin/python -c "import livekit.agents as a; print(a.__version__)"'
ssh ... '/opt/capsy-agent/.venv/bin/python -c "import importlib.util as u; print(bool(u.find_spec(\"livekit.plugins.turn_detector\")))"'
```
Decision:
- version `>= 1.5` AND spec True → proceed to 1.4.
- spec False → STEP 1.3 (install). Pin compatibility: install the turn-detector plugin **matching
  the installed agents version** (`pip install "livekit-plugins-turn-detector==<same-minor-as-agents>"`
  if a matching release exists; else the newest that resolves without upgrading `livekit-agents`).
  Do NOT upgrade `livekit-agents` itself in Phase 0 (that risks the whole voice stack — out of scope).
- version `< 1.5` → STOP. Semantic turn-detection needs `livekit-agents >= 1.5`. Record
  `PREFLIGHT: BLOCKED — agents <1.5; semantic swap deferred`. Ship ONLY Step 3 (barge-in) which
  needs no new plugin. Surface to founder via STATE file (an agents upgrade is a separate,
  riskier unit, not a Phase-0 quick win).

1.3 **(only if missing) install into the AGENT venv** (back up the freeze first):
```
ssh ... '/opt/capsy-agent/.venv/bin/python -m pip freeze > /opt/capsy-agent/freeze.preTD.$(date +%s).txt'
ssh ... '/opt/capsy-agent/.venv/bin/python -m pip install "livekit-plugins-turn-detector==<ver>"'
```
Re-run 1.2 spec check → must be True. If pip pulls an incompatible `livekit-agents`/`onnxruntime`,
ABORT + `pip install -r` the saved freeze to restore, and record BLOCKED.

1.4 **Download the model asset** (out-of-band, NOT on a call):
```
ssh ... '/opt/capsy-agent/.venv/bin/python -m livekit.agents download-files'
```
Then verify the HF cache actually grew (asset present):
```
ssh ... 'du -sh ~/.cache/huggingface 2>/dev/null; ls -la ~/.cache/huggingface/* 2>/dev/null | head'
```
(If the agent service runs as a different user, the cache dir is that user's HOME — confirm via
`systemctl cat famit-agent | grep -E "User=|Environment=HF_HOME|WorkingDirectory"`; download as
the SAME user the service runs as, or set `HF_HOME` consistently, so production finds the asset.)

1.5 **Load + run probe + SIGNATURE DUMP** — scp `droplet_work/_inspect_td.py` to `/tmp` and run
it, AND a load-timing + AgentSession-signature wrapper. The signature dump is load-bearing: it
confirms the EXACT kwarg names (`resume_false_interruption`, `false_interruption_timeout`,
`min_interruption_words`, `min/max_endpointing_delay`) so the kwarg-filter doesn't silently drop a
misnamed kwarg and leave the feature dead. Create `droplet_work/_preflight_td.py`:
```python
# _preflight_td.py — prove the semantic EOU model loads + runs, AND dump the AgentSession knobs.
import time, inspect
t0 = time.time()
from livekit.plugins.turn_detector.multilingual import MultilingualModel
t1 = time.time()
m = MultilingualModel()                      # constructs/loads the model
t2 = time.time()
print(f"IMPORT_OK import={t1-t0:.2f}s construct={t2-t1:.2f}s")
print("MODEL_OK", type(m).__name__)
from livekit.agents import AgentSession
sig = inspect.signature(AgentSession.__init__)
knobs = [p for p in sig.parameters if any(k in p for k in
         ("interrupt", "endpoint", "turn_detect", "false_interruption", "resume"))]
print("SESSION_KNOBS", knobs)             # confirms exact names + whether min_interruption_words exists
print("HAS_VAR_KW", any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()))
```
```
scp -i <key> droplet_work/_preflight_td.py famit@168.144.153.145:/tmp/
ssh ... '/opt/capsy-agent/.venv/bin/python /tmp/_preflight_td.py'
ssh ... '/opt/capsy-agent/.venv/bin/python /tmp/_inspect_td.py'
```
**Record the printed `SESSION_KNOBS` list.** Then in §5:
- If `min_interruption_words` is present → it is the PRIMARY backchannel discriminator (set
  `min_interruption_words=int(os.getenv("MIN_INT_WORDS","2"))` via the filtered kwargs). backchannel.py
  stays as belt-and-suspenders. If ABSENT → backchannel.py + the raised floor + resume are the only levers.
- If `resume_false_interruption` is NOT in the list (name differs by version) → use the real name the
  dump shows, or drop it (degrade, don't break).
- **Use the measured `construct=` time to decide prewarm (#3 risk):** if construct > ~0.3 s, do NOT
  build the model per-call in `_resolve_turn_detection()` — move it to a `prewarm`/`JobProcess`
  (`proc.userdata["turn_model"]=MultilingualModel()`, passed via `WorkerOptions(prewarm_fnc=…)`,
  exactly as context7's example prewarms VAD) so the ~396 MB model loads ONCE per worker, not on
  every call's hot path (else it silently delays answer→first-audio, which Step-4 metrics don't catch).
  If construct ≤ ~0.3 s, per-call construction is fine; keep §5.2 as written.

**ACCEPTANCE (Step 1):** `IMPORT_OK` + `MODEL_OK` + `SESSION_KNOBS` printed, construct time recorded
(decides prewarm vs inline), no OOM/segfault, headroom snapshot healthy,
`famit-agent`/`famit-caller` STILL active (we never restarted). Write
`PREFLIGHT: PASS (agents=<v>, construct=<x>s, freeRAM=<m>MB)` to the STATE file. If any sub-step
fails → record the exact failure, leave the box untouched, ship only Step 3.

> Step 1 changes NOTHING the live agent uses. Even installing the plugin + downloading the asset
> does not alter behavior until `agent.py` references it AND the flag is flipped. Zero risk to live calls.

### STEP 2 — SEMANTIC SWAP behind a flag (code + deploy, DEFAULT stays vad)  [model: opus]
2.1 Edit `agent.py` (see §5 diff). Add the import, a guarded loader, and make `turn_detection`
flag-driven with VAD fallback. **Default `TURN_DETECTION` unset → behaves as `"vad"` (byte-equivalent
behavior).** Do NOT set the env yet.

2.2 **Local smoke (INSTANTIATE, not just ast-parse)** — the brain's #1 deploy lesson: ast.parse
passed while the agent crashed on every call. Create `droplet_work/_smoke_td.py` that imports
`agent`'s loader and builds the session pieces, OR minimally: set `TURN_DETECTION=semantic` and
construct `_resolve_turn_detection()` + `MultilingualModel()` in isolation. Run with the box venv
(locally we may not have the plugin; if not, run this smoke ON the box after scp). Must print OK,
no `TypeError`.

2.3 **Backup on box, then deploy agent.py ONLY**:
```
ssh ... 'cp /opt/famit-agent/agent.py /opt/famit-agent/agent.py.VQWbak.$(date +%s)'
scp -i <key> droplet_work/agent.py famit@168.144.153.145:/opt/famit-agent/
ssh ... 'python3 -c "import ast; ast.parse(open(\"/opt/famit-agent/agent.py\").read())"'
ssh ... '/opt/capsy-agent/.venv/bin/python /tmp/_smoke_td.py'   # instantiate-smoke ON the box
ssh ... 'sudo systemctl restart famit-agent'
ssh ... 'systemctl is-active famit-agent famit-caller'
```
Because default is `vad`, the restarted agent is behavior-identical. **Regression gate now**
(see §7) — must be green BEFORE flipping the flag.

2.4 **Flip the flag** in `/opt/famit-agent/.env` (backup .env first) and restart agent:
```
ssh ... 'cp /opt/famit-agent/.env /opt/famit-agent/.env.VQWbak.$(date +%s)'
ssh ... 'grep -q ^TURN_DETECTION= /opt/famit-agent/.env && sed -i s/^TURN_DETECTION=.*/TURN_DETECTION=semantic/ /opt/famit-agent/.env || echo TURN_DETECTION=semantic >> /opt/famit-agent/.env'
ssh ... 'sudo systemctl restart famit-agent'
```
Confirm the log line `turn_detection: SEMANTIC (MultilingualModel) loaded` (we log it — see diff).
If instead you see `turn_detection: VAD (fallback: <err>)`, the model failed to load at runtime →
the agent STILL WORKS on VAD (non-breaking), investigate the error, do not proceed to the real call.

**ACCEPTANCE (Step 2):** agent active; with flag unset → identical; with flag=semantic → log
confirms semantic loaded AND no startup crash. Real-call acceptance is Step 4 (combined).

### STEP 3 — ADAPTIVE BARGE-IN (code + deploy)  [model: opus]
Four sub-changes, all in `agent.py`, all env-gated, all reuse existing structures:

3a **Raise the interruption floor default** 0.25 → 0.45 (8 kHz telephony: 0.25 s of any sound,
incl. a cough/line-noise/backchannel, was cutting the agent). Keep env override `MIN_INT_DUR`.

3a2 **`min_interruption_words` ≈ 2 (the PRIMARY discriminator, native + at the right layer).** If
the pre-flight `SESSION_KNOBS` dump shows this param exists, set it via the filtered kwargs (env
`MIN_INT_WORDS`, default 2): an interruption is only honored once ≥2 words land, so a bare "haan"
can't cut the agent but "ruko, price batao" does. This is the real backchannel/true-interrupt
discriminator (it acts BEFORE the turn commits, unlike the post-hoc hook). If the param is ABSENT,
3c + the raised floor + resume are the fallback levers.

3b **Enable resume-on-false-interruption.** Pass `resume_false_interruption=True` (env
`RESUME_FALSE_INT`, default on) so when an "interruption" turns out not to be a real turn (e.g. a
short "haan"), the agent RESUMES the sentence it was speaking instead of dropping it. This pairs
with the existing `false_interruption_timeout=1.0` (agent.py:522).
> COMPAT: `resume_false_interruption` is a newer `AgentSession` kwarg. Pass it via a **kwargs dict
> filtered against the real signature** (see §5) so an older agents build that lacks the kwarg does
> NOT crash (the brain's `max_tokens` TypeError lesson). If absent, we silently skip it — VAD/semantic
> still work; we just don't get auto-resume.

3c **Backchannel non-interruption** in `_MirrorAgent.on_user_turn_completed` (reuse the text
extraction at agent.py:672-678). NEW module `droplet_work/backchannel.py` (cheap, network-free,
mirrors langdetect.py style): `is_backchannel(text) -> bool` matching a small high-signal Indian
backchannel set (haan/haanji/hmm/hm/achha/acha/accha/theek/thik/ok/okay/ji/sahi/right/yes/yeah/
bilkul/sahi-hai…), only when the utterance is SHORT (≤ ~2 tokens / ≤ ~12 chars) so a real sentence
that merely starts with "haan" is NOT swallowed.
- HONEST SCOPE: `on_user_turn_completed` fires AFTER the turn/interrupt is already committed, so 3c
  does NOT itself prevent an interruption — `min_interruption_words` (3a2) is the lever that does
  that, at the right layer. 3c only suppresses OUR extra per-turn handling (no stray language nudge
  off a "haan") and records the signal. So 3c is a
  **defensive belt-and-suspenders layer for the VAD path** and for the residual cases: when
  `is_backchannel(txt)` is true, LOG it and do NOT inject any steering note; rely on
  `resume_false_interruption` + the raised floor to keep the agent talking. **Do NOT call
  `session.interrupt()` or alter turn flow here** — only suppress our own extra handling and record
  the signal. (Keeping 3c minimal avoids fighting the framework's own turn logic — the brain warns
  against brittle per-turn machinery.)

3d Deploy (same recipe as 2.3: backup → scp agent.py + new backchannel.py → ast-parse →
instantiate-smoke → restart famit-agent → regression gate).

**ACCEPTANCE (Step 3):** agent active; smoke shows `is_backchannel("haan")==True`,
`is_backchannel("haan मुझे price बताओ")==False`; session built with the resume kwarg when present
(log line `barge-in: min_int=0.45 resume_false=on`). Real-call proof = Step 4.

### STEP 4 — REAL BIDIRECTIONAL CALL ACCEPTANCE (the only proof that matters)  [model: opus]
This is the gate the master plan names: *"a real call shows lower eou + no mid-sentence cuts, no
latency regression; site untouched."* A silent pickup does NOT count (brain: silent calls log
`no_answer` and never exercise turn-taking). Founder (or a human) must actually converse.

Procedure:
1. Ensure the test campaign's calling window covers NOW (Shapoorji/DLF). If you widen it, **restore
   it after** (brain mistake: a prior agent left a live campaign at 00:00–23:59 = TRAI problem).
2. Place ONE call:
```
curl -H "X-Auth: FamitCall2026" -X POST https://panel.famit.in/api/run \
  -F campaign_id=c17e55e9f3 -F "leads=Kunal Kumar, 6375548830" -F concurrency=1
```
3. Human answers and deliberately exercises ALL FOUR behaviors:
   (a) **true interrupt** — let the agent talk, INTERRUPT mid-sentence with a real instruction
   ("रुको, price बताओ") → agent must stop promptly (~0.5 s).
   (b) **backchannel** — say "haan"/"hmm" WHILE the agent talks → agent must NOT cut itself off /
   must resume the sentence.
   (c) **mid-sentence PAUSE (the semantic model's headline benefit)** — start a sentence, PAUSE
   ~1 s, then continue ("मुझे... [pause] ...price aur loan dono batao") → agent must WAIT for the
   continuation, NOT jump in during the pause. (On VAD with max_ep 0.45 it WOULD jump in; semantic
   + max_ep ~1.8 should hold.) This is the test the VAD path structurally fails.
   (d) **normal back-and-forth** to feel EOU snappiness.
4. Pull the metrics from the journal (poll, don't stream): grep the room's `eou`, `llm_ttft`,
   `tts_ttfb`, `transcript saved` markers (agent logs `metrics_collected`, agent.py:632), AND the
   **answer→first-agent-audio** gap = time from room/participant join to the opener's first
   `tts_ttfb` (this catches a per-call model-load/startup regression that the in-conversation
   metrics miss — see Risk #3; if it regressed, prewarm the model per §1.5).

**ACCEPTANCE (Step 4) — compare against the VOICEFIX baseline (build_log/wave-voicefix.md):**
| Metric | Baseline (VAD) | Target (semantic) | Pass rule |
|---|---|---|---|
| eou_delay | 0.5–1.0 s | lower / tighter | median not WORSE; ideally ↓ toward ~0.4–0.6 |
| **caller cut off on a mid-sentence PAUSE** | happens (VAD) | none | agent WAITS through a ~1 s pause, doesn't jump in (3c above) |
| mid-sentence cuts on backchannel | happened | none | human confirms "it stopped cutting me off" |
| true interrupt latency | ok | still prompt | agent stops within ~0.5 s of a REAL interrupt |
| **answer→first-agent-audio** | (measure now) | not worse | no new startup lag from model load (else prewarm) |
| llm_ttft | 0.5–1.2 s (occ. spike) | unchanged | no NEW systematic regression (Groq-key, not ours) |
| tts_ttfb | 0.19–0.47 s | unchanged | unchanged |
| Existing flow | green | green | §7 regression gate still 200s; transcript+summary+₹cost written |

Subjective gate (founder is the oracle): "feels more human, didn't cut me off, not slower."
If PASS → record DONE + leave `TURN_DETECTION=semantic`. If the semantic path feels WORSE
(e.g. EOU too eager/laggy) → set `TURN_DETECTION=vad` + restart (instant rollback, §6), keep the
barge-in wins (they're independent), record the finding.

---

## 5. THE DIFF (apply to `droplet_work/agent.py`)

All edits are small + targeted (brain: never rewrite this file; serialize edits). Anchor on the
quoted strings, not the line numbers.

### 5.1 Import (anchor: the existing plugins import, agent.py:23)
```python
# BEFORE
from livekit.plugins import elevenlabs, groq, sarvam, silero
# AFTER
from livekit.plugins import elevenlabs, groq, sarvam, silero
# Phase-0 voice quick-win: semantic end-of-turn model (flagged; VAD remains the fallback).
try:
    from livekit.plugins.turn_detector.multilingual import MultilingualModel as _SemanticTurnModel
except Exception:  # noqa: BLE001 — plugin may be absent; agent MUST still run on VAD
    _SemanticTurnModel = None
```

### 5.2 New helpers (place near the top-level helpers, BEFORE `entrypoint`)
```python
import inspect as _inspect  # add near the stdlib imports if not already present

def _resolve_turn_detection():
    """Return the turn_detection value for AgentSession, honoring TURN_DETECTION env.

    TURN_DETECTION=semantic  -> MultilingualModel() if the plugin is importable + constructs,
                                else transparently fall back to "vad" (never break a call).
    TURN_DETECTION=vad (default / anything else) -> "vad" (today's behavior, byte-equivalent).
    """
    mode = (os.getenv("TURN_DETECTION", "vad") or "vad").strip().lower()
    if mode == "semantic" and _SemanticTurnModel is not None:
        try:
            model = _SemanticTurnModel()
            logger.info("turn_detection: SEMANTIC (MultilingualModel) loaded")
            return model
        except Exception as exc:  # noqa: BLE001
            logger.warning("turn_detection: VAD (semantic load failed: %r)", exc)
            return "vad"
    if mode == "semantic":
        logger.warning("turn_detection: VAD (TURN_DETECTION=semantic but plugin not importable)")
    else:
        logger.info("turn_detection: VAD (mode=%s)", mode)
    return "vad"


def _session_kwargs_filter(kwargs: dict) -> dict:
    """Drop any AgentSession kwarg the installed livekit-agents build doesn't accept,
    so a newer kwarg (e.g. resume_false_interruption) can't TypeError-crash an older build.
    (Brain lesson: max_tokens vs max_completion_tokens crashed every call.)"""
    try:
        sig = _inspect.signature(AgentSession.__init__)
        if any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
            return kwargs  # **kwargs present → it accepts anything
        allowed = set(sig.parameters)
        return {k: v for k, v in kwargs.items() if k in allowed}
    except Exception:  # noqa: BLE001
        return kwargs
```

### 5.3 The AgentSession construction (anchor: `session = AgentSession(` at agent.py:487)
TWO edits in this call: (A) `max_endpointing_delay` (line 517) becomes mode-conditional; (B) the
tail (lines 521-523) gets the new floor + resolver + filtered kwargs.

**(A)** First, just BEFORE `session = AgentSession(` (agent.py:487), add the mode flag:
```python
    _semantic_on = (os.getenv("TURN_DETECTION", "vad").strip().lower() == "semantic")
```
Then change the `max_endpointing_delay` line (agent.py:517):
```python
# BEFORE
        max_endpointing_delay=float(os.getenv("MAX_EP_DELAY", "0.45")),  # default ~6s!
# AFTER  (semantic needs patience or it cuts the USER off mid-thought; VAD keeps 0.45)
        max_endpointing_delay=float(os.getenv("MAX_EP_DELAY", "1.8" if _semantic_on else "0.45")),
```

**(B)** Replace the tail of the `AgentSession(...)` call:
```python
# BEFORE (agent.py:521-523)
        min_interruption_duration=float(os.getenv("MIN_INT_DUR", "0.25")),
        false_interruption_timeout=1.0,
        turn_detection="vad",                        # fast; no heavy model
    )
# AFTER
        # Phase-0 quick-win: raise the barge-in floor for 8kHz telephony. 0.25s of ANY sound
        # (cough/line-noise/backchannel "haan") was cutting the agent mid-sentence. 0.45s still
        # lets a real interrupt land fast (<0.5s) but ignores a stray blip. Env-overridable.
        min_interruption_duration=float(os.getenv("MIN_INT_DUR", "0.45")),
        false_interruption_timeout=float(os.getenv("FALSE_INT_TIMEOUT", "1.0")),
        # Phase-0 quick-win: semantic end-of-turn (flagged) with automatic VAD fallback.
        turn_detection=_resolve_turn_detection(),
        **_session_kwargs_filter({
            # Resume the agent's own sentence if an "interruption" turns out to be a false
            # barge-in (e.g. a short backchannel). Pairs with false_interruption_timeout.
            # Filtered out automatically on an older build that lacks the kwarg.
            "resume_false_interruption":
                (os.getenv("RESUME_FALSE_INT", "1") not in ("0", "false", "False")),
            # Native backchannel discriminator (the RIGHT layer): require N words before an
            # interruption is honored, so a bare "haan"/"hmm" can't cut the agent but a real
            # phrase ("ruko, price batao") still does. Only include if the pre-flight SESSION_KNOBS
            # dump showed this param exists; the filter drops it otherwise.
            "min_interruption_words": int(os.getenv("MIN_INT_WORDS", "2")),
        }),
    )
    logger.info("barge-in: min_int=%s min_int_words=%s resume_false=%s max_ep=%s",
                os.getenv("MIN_INT_DUR", "0.45"), os.getenv("MIN_INT_WORDS", "2"),
                os.getenv("RESUME_FALSE_INT", "1"), os.getenv("MAX_EP_DELAY"))
```
> CRITICAL on `max_endpointing_delay` (agent.py:517): this is version-aware.
> - On the **VAD path** (`TURN_DETECTION=vad`): keep 0.45 (the brain shows the framework default
>   ~6 s is what made VAD "beat too late"). Unchanged.
> - On the **SEMANTIC path**: 0.45 DEFEATS the model — it force-finalizes the user's turn after
>   0.45 s of silence even when the model predicts the user is mid-thought (trailing off), so the
>   agent cuts the USER off. Context7's `MultilingualModel()` example uses `max_endpointing_delay=5.0`.
>   Set the default to **~1.8 s when `TURN_DETECTION=semantic`** (the model still cuts EARLY, floored
>   by `min_endpointing_delay`, when the user is clearly done; the higher max only adds patience in
>   the genuinely-ambiguous pause). Implement by making the default conditional on the mode:
>   `max_endpointing_delay=float(os.getenv("MAX_EP_DELAY", "1.8" if _semantic_on else "0.45"))`
>   where `_semantic_on = (os.getenv("TURN_DETECTION","vad").strip().lower() == "semantic")`.
>   Tune 1.5–2.5 s on the real call. `min_endpointing_delay` (0.25) stays — it floors the fast case.

### 5.4 Backchannel suppression in the existing hook (anchor: `class _MirrorAgent`, agent.py:666)
Add ONE early branch inside `on_user_turn_completed`, reusing the already-extracted `txt`
(agent.py:672-678). Insert right AFTER `txt` is computed and BEFORE the langdetect nudge:
```python
                # Phase-0 quick-win: recognise a short Indian backchannel (haan/hmm/achha/ok…)
                # and do NOT treat it as a steer/turn. The semantic EOU model + resume_false_
                # interruption do the heavy lifting; this is a cheap belt-and-suspenders log so
                # we never inject a language nudge off a mere "haan". We deliberately do NOT alter
                # turn flow here (no session.interrupt) — fighting the framework's turn logic is
                # the brittle path the brain warns against.
                try:
                    import backchannel as _bc
                    if _bc.is_backchannel(str(txt)):
                        logger.info("backchannel detected (%r) — no steer", str(txt)[:32])
                        return
                except Exception:  # noqa: BLE001
                    pass
```

### 5.5 NEW file `droplet_work/backchannel.py`
```python
"""backchannel.py — cheap, network-free Indian-English/Hindi backchannel detector for the
Famit voice agent (Phase-0 voice quick-win). A 'backchannel' is a short listening token
(haan/hmm/achha/ok/ji…) the caller utters WHILE the agent talks — it must NOT be treated as a
turn or an interruption. Mirrors langdetect.py: pure-local, allocation-cheap, never raises.

Public API:
    is_backchannel(text) -> bool
"""
from __future__ import annotations
import re

# High-signal, SHORT acknowledgement tokens (romanized + common English). Kept tight so a real
# sentence that merely begins with one of these is NOT misclassified (we also length-gate).
_BACKCHANNEL = frozenset("""
haan haanji han hanji hmm hm hmmm achha acha accha achchha theek thik thikhai ok okay okk
ji jee sahi yes yeah yep yup right bilkul bilkul-hi haan-haan ya yaa uhhuh aha hahn
""".split())

# Devanagari one-word backchannels (script form).
_BACKCHANNEL_DEV = frozenset(["हाँ", "हां", "जी", "हम्म", "अच्छा", "ठीक", "सही", "बिल्कुल", "हाँजी"])

_WORD_RE = re.compile(r"[a-zA-Zऀ-ॿ]+")
_MAX_TOKENS = 2          # ≤2 words → candidate backchannel
_MAX_CHARS = 14          # and short overall


def is_backchannel(text: str) -> bool:
    """True iff `text` is a short standalone acknowledgement, not a real turn. Never raises."""
    try:
        if not text:
            return False
        t = text.strip().lower()
        if not t or len(t) > _MAX_CHARS:
            return False
        words = _WORD_RE.findall(t)
        if not words or len(words) > _MAX_TOKENS:
            return False
        # Every word must itself be a known backchannel token (so "haan price" -> False,
        # because "price" is not a backchannel and the length gate already trimmed long turns).
        for w in words:
            if w in _BACKCHANNEL or w in _BACKCHANNEL_DEV:
                continue
            return False
        return True
    except Exception:
        return False
```

> The build agent MUST also scp `backchannel.py` to `/opt/famit-agent/` (it's imported lazily
> inside the hook; `sys.path` already includes the agent dir since `import langdetect`/`memory`
> work the same way — agent.py:26,31).

---

## 6. FEATURE FLAGS + ROLLBACK (the whole point — instant, non-breaking)

| Flag (env in `/opt/famit-agent/.env`) | Default | Effect |
|---|---|---|
| `TURN_DETECTION` | `vad` | `semantic` → MultilingualModel (auto-fallback to vad on any load error). |
| `MIN_INT_DUR` | `0.45` (new default) | barge-in floor seconds. |
| `MIN_INT_WORDS` | `2` | words required before an interrupt is honored (only applied if the param exists; primary backchannel discriminator). |
| `RESUME_FALSE_INT` | `1` (on) | resume the agent's sentence after a false barge-in. |
| `FALSE_INT_TIMEOUT` | `1.0` | unchanged knob, now env-exposed. |
| `MIN_EP_DELAY` | `0.25` | unchanged (floors the fast EOU case). |
| `MAX_EP_DELAY` | `0.45` (vad) / **`1.8` (semantic)** | mode-conditional default; semantic needs patience or it cuts the user off on a pause. Tune 1.5–2.5 s. |

**Rollback ladder (fastest first; each ~5 s, no redeploy):**
1. Semantic feels worse → `TURN_DETECTION=vad` + `systemctl restart famit-agent`. (Barge-in wins stay.)
2. Barge-in too sticky/insensitive → tune `MIN_INT_DUR` (e.g. back to `0.30`) or `RESUME_FALSE_INT=0` + restart.
3. Anything wrong with the code itself → restore the box backup:
   `cp /opt/famit-agent/agent.py.VQWbak.<ts> /opt/famit-agent/agent.py && systemctl restart famit-agent`
   (and `.env.VQWbak.<ts>` if env was changed). This returns to the exact pre-wave state.
4. Plugin install caused a venv problem → `pip install -r /opt/capsy-agent/freeze.preTD.<ts>.txt`.

Because the default ships `vad` and the semantic path self-falls-back, **the live call cannot be
broken by deploying the code**; only flipping the flag changes behavior, and that flip is one line
to revert.

---

## 7. REGRESSION GATE (run after EVERY deploy in steps 2 & 3; the global verification law)

No paid call needed for the gate; Step 4 is the one intentional paid call.
```
# services up
ssh ... 'systemctl is-active famit-agent famit-caller'        # both 'active'
# API still 200 + tenant-scoped (legacy admin token)
curl -s -o NUL -w "%{http_code}\n" -H "X-Auth: FamitCall2026" https://panel.famit.in/api/stats
curl -s -o NUL -w "%{http_code}\n" -H "X-Auth: FamitCall2026" https://panel.famit.in/api/campaigns
curl -s -o NUL -w "%{http_code}\n" -H "X-Auth: FamitCall2026" https://panel.famit.in/api/calls?limit=5
# dispatch a job WITHOUT a real ring is not possible cleanly; rely on Step 4's single call for E2E.
```
Pass: services active; the three GETs return `200`; agent log shows the expected turn_detection +
barge-in lines; no traceback in `journalctl -u famit-agent --since "2 min ago"`. md5 the deployed
agent.py == local (CRLF-normalize before comparing — brain trap).

---

## 8. STATE / CRASH-SAFETY FILE (create FIRST, update per unit)

Create `droplet_work/STATE_VOICE_QUICKWINS.md`:
```
# PHASE 0 VOICE QUICK-WINS — STATE / TASKS  (owner VOICE-LATENCY-ENG)
Box famit@168.144.153.145 /opt/famit-agent ; venv /opt/capsy-agent/.venv ; svc famit-agent.
Flags: TURN_DETECTION(vad), MIN_INT_DUR(0.45), RESUME_FALSE_INT(1).

- [ ] S1 PREFLIGHT: agents ver, plugin present/installed, download-files, load+run probe, headroom. RESULT: ____
- [ ] S2 SEMANTIC SWAP: agent.py diff + instantiate-smoke + deploy (default vad) + regression green; then flag=semantic + log confirms.
- [ ] S3 BARGE-IN: min_int 0.45 + resume_false + backchannel.py + deploy + regression green.
- [ ] S4 REAL CALL: bidirectional; eou not worse; no mid-sentence cut on "haan"; founder says better; flow 200s.
RESTORE: backups agent.py.VQWbak.<ts>, .env.VQWbak.<ts>, freeze.preTD.<ts>.txt.
```
Flip `[ ]`→`[x]` with the measured result after each unit verifies. One `IN PROGRESS` line at a
time tells a resuming session exactly where it stopped.

---

## 9. DEPENDENCIES

- `livekit-plugins-turn-detector` (matching the installed `livekit-agents` minor; do NOT upgrade
  agents in Phase 0) in venv `/opt/capsy-agent/.venv`.
- The ~396 MB turn-detector model asset downloaded to the service user's HF cache via
  `python -m livekit.agents download-files` (pre-flight, not on a call).
- `livekit-agents >= 1.5` (hard requirement for semantic turn detection; if `< 1.5`, semantic is
  BLOCKED and only the barge-in unit ships).
- No new Python deps for barge-in / `backchannel.py` (stdlib `re` only).
- No `caller.py` / frontend / DB changes. Backend service untouched.

---

## 10. MODEL ROUTING (for the implementing agent)

| Unit | Model | Why |
|---|---|---|
| S1 Pre-flight (ssh probes, version/headroom/load) | **opus** | Judgement call on go/no-go + version-compat + the venv/HF-cache traps; a wrong call here risks the live stack. |
| S2 Semantic swap (the guarded diff + smoke) | **opus** | Touches the live call path; must get the fallback/kwarg-filter exactly right (the `max_tokens` class of bug). |
| S3 Barge-in (diff + backchannel.py) | **opus** | Same hot path; subtle turn-taking semantics. |
| S4 Real-call verify + metrics read | **opus** | Interprets eou/ttft vs baseline + the founder's subjective verdict; decides ship vs rollback. |
| (mechanical) scp/backup/grep/curl plumbing within a step | sonnet acceptable | If delegated, but the whole wave is small + on the live earner — keeping it opus end-to-end is the safe default. One agent, sequential, never two on agent.py. |

Single agent, one unit at a time, COMMIT/record per verified unit. Never run a second agent on
`agent.py` concurrently (brain: serialize edits to this file).

---

## 11. OPEN RISKS / WATCH-OUTS (surfaced honestly)

1. **agents `< 1.5` on the box** → semantic is blocked; upgrading livekit-agents is a separate,
   higher-risk unit (could disturb the whole Vobiz→LiveKit→Sarvam→Groq→EL chain). Phase-0 then
   ships barge-in only and records the upgrade as a future gated unit.
2. **Cold model download on first call** if `download-files` doesn't fetch the turn-detector asset
   in this version → first semantic call could lag or time out. Mitigation: pre-flight forces a
   construct (`_preflight_td.py`) which triggers the download out-of-band; verify HF cache grew.
3. **HF cache under the wrong user** — if `famit-agent` runs as a different user than the one who
   ran `download-files`, prod won't find the asset. Confirm `systemctl cat famit-agent` User= and
   download as that user (or set a shared `HF_HOME` in the env file).
4. **`resume_false_interruption` kwarg name/availability** varies by agents version — handled by
   `_session_kwargs_filter`, but if the build is old it simply won't resume (degrade, not break).
5. **Semantic EOU could feel laggier**, not snappier, on Hinglish (the model is multilingual but
   tuned broadly). The real call is the arbiter; instant flag rollback to `vad` if so. eou target
   is "not worse," with improvement as the goal — do not ship a regression to chase a metric.
6. **CPU headroom** — the EOU model runs inference per turn on CPU. If the box is already tight
   (concurrent calls), watch load during Step 4. If it pushes latency, that's a capacity decision
   (warm pool / bigger box — Phase 2), not a Phase-0 code change; fall back to `vad`.
7. **Backchannel over-suppression** — `backchannel.py` is intentionally conservative (≤2 tokens,
   ≤14 chars, every token must be a known ack). If it ever swallows a real one-word command, tighten
   the set; it never alters turn flow, so worst case is a missed language nudge, not a broken call.
8. **Do not let the smoke test be ast-parse only** — the single biggest deploy lesson on this code:
   INSTANTIATE the objects (`MultilingualModel()`, the session kwargs) on the box venv before restart.

---

## RED-TEAM FIXES (folded) — these OVERRIDE any conflicting text above

> Adversarial principal review, grounded against the LIVE source (`droplet_work/agent.py`),
> the durable brain, and the master plan. Where this section conflicts with an earlier line,
> **this section wins** (it is the corrected design). Verdict for the subsystem: **GO-WITH-FIXES**
> (approach is sound and version-supported; none of these flips the GO, but A/B/C are BLOCKING —
> ship them or the "non-breaking" guarantee is false).

### RTF-0. Version risk DOWNGRADED (was Risk #1 "agents <1.5 blocks semantic")
Durable ground truth: the box already runs **`livekit-agents 1.5.17`** — recorded in
`build_log/wave-P2-voice-brain.md:12` ("KEY RUNTIME CAPABILITIES USED (livekit-agents 1.5.17)")
and corroborated by `brain/decisions.md:12-13` (the turn-detector plugin was already chosen,
Hindi 99.4% TPR, CPU-only). So `>= 1.5` is **almost certainly already satisfied**; semantic is
NOT expected to be blocked. The pre-flight still RE-CONFIRMS the version (cheap), but treat
"BLOCKED on <1.5" as a remote contingency, not the expected branch. **The real residual unknown
is NOT the version** — it is whether 1.5.17 exposes `min_interruption_words` /
`resume_false_interruption` as `AgentSession` kwargs (context7's 1.5 READMEs did NOT surface them).
That is load-bearing on the §1.5 `SESSION_KNOBS` dump — keep the kwargs-filter; do not assume.

### RTF-A. [BLOCKING — correctness] The auto-fallback is NOT byte-equivalent to today; fix `_semantic_on`
**The single most important fix.** As written, §5.3 derives `_semantic_on` from the ENV flag:
```python
_semantic_on = (os.getenv("TURN_DETECTION", "vad").strip().lower() == "semantic")   # WRONG SOURCE
```
…but `turn_detection=_resolve_turn_detection()` **falls back to the string `"vad"` when the model
fails to construct** (the whole safety net). Trace the failure path: `TURN_DETECTION=semantic` +
the model raises at construct → `turn_detection="vad"` **AND** `max_endpointing_delay=1.8`. That is
**VAD running with the semantic patience window** → the agent waits up to 1.8 s of silence before
finalizing EVERY user turn → up to ~1.35 s of dead air added on every turn, on the live earner,
exactly when something already went wrong. This **directly contradicts** §0/§6's promise that the
fallback is "byte-equivalent to today / cannot break the live call." The auto-fallback is the
entire safety story, and it's laggy.

**FIX — derive the mode from the RESOLVED detector, not the env.** Replace the §5.3(A) snippet and
the §5.3(B) `turn_detection=` line with this single ordering (resolve ONCE, then branch on the real
object):
```python
    # Resolve the detector ONCE; _semantic_on is true ONLY if a real model actually loaded.
    _td = _resolve_turn_detection()            # MultilingualModel() instance OR the string "vad"
    _semantic_on = not isinstance(_td, str)    # a model object → semantic; "vad" string → VAD
    ...
        max_endpointing_delay=float(os.getenv("MAX_EP_DELAY", "1.8" if _semantic_on else "0.45")),
    ...
        turn_detection=_td,                    # use the SAME resolved value (do NOT call resolve twice)
```
Now an env of `semantic` that fails to load degrades to **true** today-behavior (VAD + 0.45), and a
manual `MAX_EP_DELAY` override still wins. Note also: §5.2's `_resolve_turn_detection()` constructs
the model and logs inside the resolver — calling it twice (once for `_semantic_on`, once for
`turn_detection=`) would build the ~396 MB model TWICE per call and double-log. **Resolve once into
`_td`; reuse it.** (This also tightens RTF-D: `_td` is the single handle a prewarm path swaps.)

### RTF-B. [BLOCKING — breaking-change + missing test] Barge-in defaults ship LIVE on deploy, gated on nothing
§6 claims "deploying the code can't change behavior; only flipping the flag does." **That is FALSE
for the barge-in unit.** The barge-in changes ship as new **defaults** that take effect the instant
Step 3 deploys, independent of `TURN_DETECTION`:
- `MIN_INT_DUR` default 0.25 → **0.45** (a real interrupt now needs ~0.45 s of speech, not 0.25),
- `min_interruption_words` = **2** (if the param exists → a 1-word command no longer interrupts),
- `resume_false_interruption` = **on**.
These are genuine turn-taking behavior changes on the live earner. And §7's regression gate is
**API-health only** (3 GETs + `systemctl is-active`) — it exercises **zero turn-taking**, so the
changed barge-in behavior rides on real production calls **verified by nothing** until the single
intentional Step-4 human call. Pick ONE (this spec chooses **(a)** for doctrine-consistency):

- **(a) PREFERRED — gate barge-in behind a flag too, defaults = today.** Ship `MIN_INT_DUR` default
  **0.25** (unchanged), `min_interruption_words` default **0/unset**, `resume_false_interruption`
  default **off** — i.e. deploying Step 3 is byte-equivalent. Then turn the improvements ON via env
  in the SAME flip-window as `TURN_DETECTION=semantic` (set `MIN_INT_DUR=0.45 MIN_INT_WORDS=2
  RESUME_FALSE_INT=1`). This restores the literal truth of §6 ("deploy changes nothing; the env flip
  changes behavior; the flip reverts in ~5 s") for BOTH units and lets barge-in roll back independ-
  ently by clearing those envs. **Update §6's defaults table accordingly** (the "(new default)"
  0.45 / "2" / "1 (on)" rows become the FLIPPED values, not the shipped defaults).
- **(b) ALTERNATIVE — keep the improved defaults, but then DELETE the "deploy can't change behavior"
  claim for barge-in** and make the Step-4 human call **mandatory and immediate** after the Step-3
  deploy (not "deferrable to later"), because nothing else verifies it.

Either way: **add a turn-taking smoke to the gate** where cheaply possible — at minimum assert in
the box smoke that the built `AgentSession` actually carries the intended `min_interruption_duration`
/ `min_interruption_words` (introspect the instance), so a silently-dropped kwarg (RTF-0) is caught
before the paid call, not during it.

### RTF-C. [BLOCKING — crash-safe] §5's single diff collapses Step 2 and Step 3 into one deploy
§4 sequences **Step 2** (semantic swap → deploy → regression-green → *then* flip) and **Step 3**
(barge-in → separate deploy → regression-green) as two independently verifiable, independently
revertible units — the crash-safe core of this plan. But §5.3(B) presents the `AgentSession(...)`
tail as **one replacement block** that contains BOTH the `turn_detection` swap (Step 2) AND every
barge-in kwarg (Step 3: the 0.45 floor, `resume_false_interruption`, `min_interruption_words`,
`false_interruption_timeout`). A build agent told to "apply the §5 diff" in Step 2 ships **all of it
at once** — collapsing two units, and (with RTF-B) making the supposedly byte-equivalent Step-2
deploy silently change barge-in too. **FIX:** annotate every §5 sub-edit with its owning step and
apply them in step order:
- `[STEP 2]` §5.1 import; §5.2 `_resolve_turn_detection`; §5.3 the `_td`/`_semantic_on` resolve +
  `turn_detection=_td` + the mode-conditional `max_endpointing_delay`. (Deploy, regression-green,
  flip `TURN_DETECTION=semantic`, verify — BEFORE touching barge-in.)
- `[STEP 3]` §5.2 `_session_kwargs_filter`; the `min_interruption_duration` default change; the
  `**_session_kwargs_filter({...})` block; §5.4 hook branch; §5.5 `backchannel.py`. (Separate
  deploy, separate regression-green.)
If a build agent finds it impractical to edit the same `AgentSession(...)` call twice, it MAY do
both edits in one code-pass — but it MUST still deploy/verify Step 2's behavior (flag drives only
turn_detection) with the barge-in defaults held at TODAY's values (RTF-B(a)) so the two behaviors
are still proven separately. The unit boundary is about *what's proven when*, not line-count.

### RTF-D. [latency / real-box] Prewarm is referenced but never specified — provide the diff now
§1.5 and Risk #2 correctly flag that a per-call `MultilingualModel()` construct (~396 MB) on the hot
path can add answer→first-audio lag, and say "move it to a `prewarm`/`JobProcess` like context7's
example." But there is **no prewarm diff**, and `WorkerOptions` today is
`WorkerOptions(entrypoint_fnc=…, agent_name=…, port=…)` (agent.py:733-738) with **no `prewarm_fnc`**.
If the pre-flight construct-time check says "prewarm," the build agent would be improvising an
entrypoint/WorkerOptions change live on the earner. **Make it a ready unit.** context7 confirms the
exact shape (`def prewarm(proc: JobProcess): proc.userdata["..."] = ...; WorkerOptions(prewarm_fnc=
prewarm, ...)`). Ready-to-apply (only used if §1.5 measures construct > ~0.3 s):
```python
# [STEP 2, conditional] near main()/WorkerOptions — build the heavy EOU model ONCE per worker.
def _prewarm(proc: agents.JobProcess) -> None:
    # Only construct when semantic is actually selected; on vad this is a no-op (cheap).
    if (os.getenv("TURN_DETECTION", "vad").strip().lower() == "semantic") and _SemanticTurnModel is not None:
        try:
            proc.userdata["turn_model"] = _SemanticTurnModel()
            logger.info("prewarm: MultilingualModel constructed once for this worker")
        except Exception as exc:  # noqa: BLE001
            logger.warning("prewarm: turn model construct failed (%r) — will fall back to vad", exc)
# add prewarm_fnc=_prewarm to the existing WorkerOptions(...)
```
…and in `_resolve_turn_detection()`, **prefer the prewarmed instance** before constructing:
```python
    if mode == "semantic":
        cached = getattr(getattr(ctx, "proc", None), "userdata", {}).get("turn_model")  # if entrypoint has ctx
        # (pass ctx.proc.userdata into the resolver, OR read it where ctx is in scope and pass the model in)
```
Implementation note: `_resolve_turn_detection()` is a top-level helper with no `ctx`. Cleanest wiring
= have `entrypoint` read `ctx.proc.userdata.get("turn_model")` and pass it into the resolver as an
optional arg (`_resolve_turn_detection(prewarmed=ctx.proc.userdata.get("turn_model"))`), returning it
when present, else constructing. **Do NOT silently leave the per-call construct in if the measurement
says prewarm** — that's the invisible-lag trap Step-4's answer→first-audio metric exists to catch.

### RTF-E. [over-engineering] Drop `backchannel.py` unless the pre-flight shows the native lever is absent
The spec already half-admits this; making it explicit. The REAL hook (`agent.py:667-696`) only acts
when `conf >= 0.55 AND lang in ("english","gujarati")` — a 1-2-word "haan"/"hmm" will NOT trip that
(it's Hindi/Hinglish and low-signal), so the §5.4 branch **guards a language-nudge that would not
fire anyway**, while adding a hot-path edit + a new module + a lazy import to the live earner. Given
the box is 1.5.17, the **native `min_interruption_words` is the correct-layer discriminator and very
likely present**. Therefore:
- If the §1.5 `SESSION_KNOBS` dump shows `min_interruption_words` **present** (expected): **SHIP
  `min_interruption_words` ONLY; DROP §5.4 and §5.5 entirely.** No `backchannel.py`, no hook edit.
  One env knob does the whole job at the right layer.
- Only if `min_interruption_words` is **absent** (unexpected on 1.5.17): ship `backchannel.py` + the
  §5.4 branch as the documented fallback. Even then it's belt-and-suspenders, not a turn-flow change.
This removes a module + a live-earner hot-path edit from the default path — strictly fewer moving
parts on the earner for the same behavior.

### RTF-F. [smaller correctness / ops notes]
- **`MIN_EP_DELAY` 0.25 vs the semantic floor.** On the VAD path the live baseline is 0.25/0.45
  (verified). Under semantic, `min_endpointing_delay` (0.25) still floors the fast "user clearly
  done" case — keep 0.25. But the master plan's eou target is sub-700-800 ms and the §4 table wants
  median "not worse"; if the real call shows semantic feeling laggy on snappy yes/no turns, the first
  tuning lever is **lowering `MAX_EP_DELAY` toward ~1.2 s** (not raising `MIN_EP_DELAY`) — keep the
  fast floor, trim the patience ceiling. (Tune-on-the-call note for Step 4, not a code change.)
- **`download-files` user/HF-cache (Risk #3) is a HARD pre-req, not a footnote.** The service runs as
  user `famit` (HANDOFF). `python -m livekit.agents download-files` MUST run as that same user (or
  with a shared `HF_HOME` set in `/opt/famit-agent/.env`), else production constructs the model on
  the FIRST call and risks a job timeout — re-introducing exactly the cold-download lag RTF-D guards.
  Confirm `systemctl cat famit-agent | grep -E "User=|HF_HOME|WorkingDirectory"` BEFORE downloading,
  and verify the cache grew under the RIGHT home. Promote this from "Risk #3" to a Step-1 gate.
- **Regression-gate `md5 local==deployed` for `agent.py`:** the brain's CRLF trap is real
  (`mistakes.md`: deployed looked bigger by line-count but md5 matched mod line-endings). Normalize
  LF before comparing, AND — because a flaky scp can land partially (exit 45) — additionally `grep`
  the SPECIFIC new markers on the box (`turn_detection: SEMANTIC`, `barge-in: min_int=`) rather than
  trusting "some marker present."
- **Do not restart `famit-caller`.** Correct in the spec; reaffirmed — this wave touches only
  `agent.py`/`backchannel.py`; `famit-caller` (and the P1 Postgres strangler mid-flight per
  `P1_FOUNDATION_STATE.md: U1 IN PROGRESS`) must be left alone. One agent on `agent.py`, never two.

### RED-TEAM verdict (subsystem): **GO-WITH-FIXES**
Approach is sound, version-supported (1.5.17), and genuinely non-breaking **once RTF-A/B/C land**.
- **Blocking, must fold before handoff:** RTF-A (auto-fallback lag — derive `_semantic_on` from the
  resolved detector), RTF-B (barge-in ships live with no gate + no test — flag it or make Step-4
  mandatory-immediate), RTF-C (split the §5 diff into Step-2 vs Step-3 units).
- **Strongly recommended:** RTF-D (ship the prewarm diff as a ready unit), RTF-E (drop `backchannel.py`
  if the native lever exists — expected), RTF-F notes.
- **Residual risk after fixes (honest):** (1) whether 1.5.17 actually exposes `min_interruption_words`
  / `resume_false_interruption` is unproven until the `SESSION_KNOBS` dump — the kwargs-filter makes
  a miss degrade-not-break, but the *feature* silently won't engage if absent (the RTF-B introspect
  assertion catches this pre-call). (2) Semantic EOU could feel laggier on Hinglish than VAD — the
  real bidirectional call is the only arbiter; instant `TURN_DETECTION=vad` rollback preserves the
  (independent) barge-in wins. (3) CPU headroom under concurrent calls (per-turn inference) is a
  Phase-2 capacity question; if it pushes latency, fall back to vad. None of these flips the GO.
