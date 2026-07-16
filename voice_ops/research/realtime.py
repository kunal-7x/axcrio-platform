"""voice_ops.research.realtime — the in-call learned-arousal worker (Phase 3, Upgrade #3).

Runs dimensional SER inference in a SEPARATE PROCESS so the GIL-heavy DSP/model work can NEVER stall
the LiveKit agent event loop — the verification's hard constraint (livekit/agents #4183: any sync
block >~20 ms on the loop drops barge-ins; librosa.pyin is ~1400 ms for 5 s). The agent's audio tap
(agent_tap.py) buffers per-turn PCM and submits it here; the worker emits an arousal estimate that the
research event carries as `ssl_arousal` (a calibrated acoustic channel replacing the in-call
confidence-0.45 ASR-metadata proxy).

Latency (verified): a 1-2 s window infers in ~5-160 ms of WORKER time on a CPU core — RTF << 1, NO GPU
(Wav2Small 9 ms/5 s on a Xeon; audeering large 372 ms/5 s = RTF 0.07). CPU-only is the correct default.

Model: if FAMIT_SER_ONNX_PATH points at an arousal/valence ONNX (e.g. audeering
wav2vec2-large-robust-12-ft-emotion-msp-dim, ONNX export) AND onnxruntime is importable, we use it.
Otherwise we degrade to a real librosa PROSODY PROXY for arousal (energy + F0 + rate), and finally to an
energy-only proxy — each with an honest, lower confidence and a `source` tag. Best-effort, never raises.

Gated by FAMIT_RESEARCH_REALTIME (default OFF → the tap is never spawned, zero overhead).
"""
from __future__ import annotations

import logging
import math
import multiprocessing as mp
import os
import queue
from typing import Optional, Tuple

logger = logging.getLogger("research.realtime")


def _truthy(v: str) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def enabled() -> bool:
    return _truthy(os.getenv("FAMIT_RESEARCH_REALTIME", "0"))


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, z))))


# --------------------------------------------------------------------------- #
# Inference (runs INSIDE the worker process). Graceful degradation chain.
# --------------------------------------------------------------------------- #
def infer_arousal(pcm, sr: int) -> Tuple[float, float, str]:
    """pcm: mono float32 in [-1,1]. Returns (arousal_0_1, confidence_0_1, source). Never raises."""
    onnx_path = (os.getenv("FAMIT_SER_ONNX_PATH") or "").strip()
    if onnx_path:
        out = _infer_onnx(pcm, sr, onnx_path)
        if out is not None:
            return out
    out = _infer_librosa_proxy(pcm, sr)
    if out is not None:
        return out
    return _infer_energy_proxy(pcm, sr)


def _infer_onnx(pcm, sr: int, path: str):
    try:
        import numpy as np
        import onnxruntime as ort  # type: ignore
        sess = _onnx_session(path, ort)
        x = np.asarray(pcm, dtype="float32").reshape(1, -1)
        # audeering dim model: input 'signal' (1,T) @16k → outputs [arousal, dominance, valence] in [0,1]
        out = sess.run(None, {sess.get_inputs()[0].name: x})
        vec = np.asarray(out[-1]).reshape(-1)
        arousal = float(vec[0]) if vec.size else 0.5
        return (max(0.0, min(1.0, arousal)), 0.85, "ssl_onnx")
    except Exception as exc:  # noqa: BLE001
        logger.warning("realtime ONNX infer failed, degrading: %r", exc)
        return None


_ONNX_SESS = {}


def _onnx_session(path: str, ort):
    if path not in _ONNX_SESS:
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(os.getenv("FAMIT_SER_THREADS", "1"))  # pin small; don't starve the box
        _ONNX_SESS[path] = ort.InferenceSession(path, sess_options=so, providers=["CPUExecutionProvider"])
    return _ONNX_SESS[path]


def _infer_librosa_proxy(pcm, sr: int):
    """A REAL prosody→arousal proxy (energy + F0): higher loudness & pitch ⇒ higher arousal. This is
    the well-established acoustic-arousal mapping (RMS+pitch), honestly labelled at modest confidence."""
    try:
        import numpy as np
        import librosa
        y = np.asarray(pcm, dtype=float)
        if y.size < sr * 0.2:
            return None
        rms = float(np.mean(librosa.feature.rms(y=y)[0]))
        rms_db = 20.0 * math.log10(rms + 1e-6)               # ~ -50..0
        try:
            f0, vflag, _ = librosa.pyin(y, fmin=65, fmax=400, sr=sr)
            f0v = f0[np.isfinite(f0)] if f0 is not None else np.array([])
            f0_mean = float(np.mean(f0v)) if f0v.size else 160.0
            voiced = float(np.mean(vflag)) if vflag is not None and vflag.size else 0.4
        except Exception:  # noqa: BLE001
            f0_mean, voiced = 160.0, 0.4
        arousal = _sigmoid(0.06 * (rms_db + 30.0) + 0.012 * (f0_mean - 160.0))
        conf = max(0.0, min(0.7, 0.4 + 0.4 * voiced)) * (0.7 if sr <= 8000 else 1.0)
        return (arousal, round(conf, 3), "ssl_proxy_librosa")
    except Exception:  # noqa: BLE001
        return None


def _infer_energy_proxy(pcm, sr: int):
    try:
        import numpy as np
        y = np.asarray(pcm, dtype=float)
        rms = float(np.sqrt(np.mean(y * y))) if y.size else 0.0
        rms_db = 20.0 * math.log10(rms + 1e-6)
        return (_sigmoid(0.06 * (rms_db + 30.0)), 0.3, "energy_proxy")
    except Exception:  # noqa: BLE001
        return (0.5, 0.15, "none")


# --------------------------------------------------------------------------- #
# Worker process + manager (used by agent_tap.py).
# --------------------------------------------------------------------------- #
def _worker_loop(in_q: "mp.Queue", out_q: "mp.Queue") -> None:
    while True:
        try:
            item = in_q.get()
        except (EOFError, OSError):
            return
        if item is None:                       # poison pill → shut down
            return
        try:
            call_id, turn_num, pcm, sr = item
            arousal, conf, source = infer_arousal(pcm, sr)
            out_q.put((call_id, turn_num, arousal, conf, source))
        except Exception as exc:  # noqa: BLE001
            logger.warning("realtime worker item failed: %r", exc)


class RealtimeAffectWorker:
    """Owns the inference subprocess. submit() is non-blocking (drops on a full queue rather than
    ever blocking the caller); poll() drains results. Spawn ONE per agent process."""

    def __init__(self, maxsize: int = 8) -> None:
        self._in: Optional[mp.Queue] = None
        self._out: Optional[mp.Queue] = None
        self._proc: Optional[mp.Process] = None
        self._maxsize = maxsize

    def start(self) -> bool:
        try:
            ctx = mp.get_context("spawn")       # spawn: no inherited LiveKit/asyncio state
            self._in = ctx.Queue(maxsize=self._maxsize)
            self._out = ctx.Queue()
            self._proc = ctx.Process(target=_worker_loop, args=(self._in, self._out), daemon=True)
            self._proc.start()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("realtime worker start failed: %r", exc)
            return False

    def submit(self, call_id: str, turn_num: int, pcm, sr: int) -> None:
        if self._in is None:
            return
        try:
            self._in.put_nowait((call_id, turn_num, pcm, sr))
        except queue.Full:
            pass                                # never block the media loop; just drop this window
        except Exception:  # noqa: BLE001
            pass

    def poll(self):
        """Drain available results → list of (call_id, turn_num, arousal, conf, source)."""
        out = []
        if self._out is None:
            return out
        try:
            while True:
                out.append(self._out.get_nowait())
        except queue.Empty:
            pass
        except Exception:  # noqa: BLE001
            pass
        return out

    def stop(self) -> None:
        try:
            if self._in is not None:
                self._in.put_nowait(None)
            if self._proc is not None:
                self._proc.join(timeout=2.0)
                if self._proc.is_alive():
                    self._proc.terminate()
        except Exception:  # noqa: BLE001
            pass
