"""voice_ops.research.validate_tap — pre-flight for the Phase 3 real-time audio tap.

Run BEFORE trusting FAMIT_RESEARCH_REALTIME on production. Two checks:
  1. INFERENCE: measure the arousal worker's per-window latency on synthetic audio (must be << the
     turn cadence; verifies the model/proxy + the process round-trip work on this box).
  2. SIP TAP (manual): the one risk a script can't fully self-test is python-sdks #690 — a SECOND
     rtc.AudioStream on a transcoded SIP/Opus track can silently return all-zero PCM. This prints the
     exact live check to run on a real Vobiz call (watch tap.healthy() go True).

    python3 -m voice_ops.research.validate_tap
"""
from __future__ import annotations

import time


def main() -> int:
    try:
        import numpy as np
    except Exception:
        print("! numpy required"); return 2
    from voice_ops.research.realtime import RealtimeAffectWorker, infer_arousal

    sr = 16000
    t = np.linspace(0, 1.5, int(sr * 1.5), endpoint=False)
    pcm = (0.4 * np.sin(2 * np.pi * 200 * t)).astype("float32")

    # 1) inference latency (in-process)
    t0 = time.perf_counter()
    a, c, src = infer_arousal(pcm, sr)
    dt = (time.perf_counter() - t0) * 1000
    print(f"[inference] source={src} arousal={a:.3f} conf={c:.3f}  latency={dt:.1f} ms / 1.5 s window "
          f"(RTF={dt/1500:.3f})")

    # 2) worker round-trip (separate process)
    w = RealtimeAffectWorker()
    if not w.start():
        print("! worker failed to start"); return 1
    try:
        t0 = time.perf_counter()
        w.submit("validate", 1, pcm.tolist(), sr)
        res = None
        while time.perf_counter() - t0 < 10:
            got = w.poll()
            if got:
                res = got[0]; break
            time.sleep(0.05)
        rt = (time.perf_counter() - t0) * 1000
        print(f"[worker]    round-trip={'ok' if res else 'TIMEOUT'} ({rt:.0f} ms)  result={res}")
    finally:
        w.stop()

    print("\n[SIP tap — run on a REAL Vobiz call] enable FAMIT_RESEARCH_REALTIME=1 and confirm in logs:")
    print("   research.agent_tap: tap loop receives frames AND tap.healthy() becomes True")
    print("   (if it stays False / 'no caller mic track' / silent → python-sdks #690; keep realtime OFF).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
