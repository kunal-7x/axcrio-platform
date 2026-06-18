"""voice_ops.concurrency.config — ConcurrencyConfig: the W24 admission knobs.

Default OFF / safe everywhere (mirrors voice_ops.telephony.config +
voice_kernel.events.config). The whole package is inert until a founder-signed seam
wave flips `CONCURRENCY_ENABLED`; until then the dial loop never calls through the
admission gate and the live path is byte-identical.

Flag pattern is the codebase-native one (agent.py:451 OPENER_ALREADY_SAID style):
    os.getenv("NAME", "0") in ("1","true","True","yes","on")
No new config framework.

The numbers below are the researched defaults (design/W24-CONCURRENCY-SEAM.md):
  worker_slot_cap         per-WORKER active-call ceiling. A single LiveKit worker
                          saturates ~10-25 concurrent jobs on a 2 vCPU box; 20 is the
                          conservative physical wall. Multiply by N workers for fleet.
  global_call_cap         hard ceiling across ALL tenants/workers (0 = worker_slot_cap
                          * worker_count). The cross-tenant guard the dial loop lacks.
  tenant_call_cap         per-tenant concurrent-call ceiling (mirrors ACTIVE_CALLS).
  llm_rpm / llm_burst     per-tenant LLM token-bucket: refill rate (req/min) + burst.
                          Groq free tier ~30 RPM/key; this is the denial-of-wallet cap.
  tts_slots_per_key       per-provider-KEY concurrent TTS channel cap (ElevenLabs/Sarvam).
  reserve_ttl_s           a reservation lease auto-expires after this (self-heals a
                          crashed worker that never released — mirrors lead_lock TTL).
  pace_backoff_s          how long the pacing queue waits before re-offering a queued
                          lead when saturated (the dial loop's own 4s tick still applies).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

_TRUE = ("1", "true", "True", "yes", "on")


def _flag(name: str, default: str = "0") -> bool:
    v = os.getenv(name, default)
    return (v or "").strip() in _TRUE


def _int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default))).strip() or default)
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, str(default))).strip() or default)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class ConcurrencyConfig:
    """Immutable snapshot of the W24 admission knobs. Build with `from_env()` in
    production; construct directly in tests."""

    enabled: bool = False              # CONCURRENCY_ENABLED — master OFF default
    # worker / call ceilings
    worker_slot_cap: int = 20          # per-worker active-call ceiling (physical wall)
    worker_count: int = 1              # registered LiveKit workers in the fleet
    global_call_cap: int = 0           # 0 -> worker_slot_cap * worker_count
    tenant_call_cap: int = 3           # per-tenant concurrent calls (default tier)
    # provider budgets (denial-of-wallet)
    llm_rpm: int = 30                  # per-tenant LLM requests/minute (Groq free ~30)
    llm_burst: int = 10                # per-tenant LLM token-bucket burst capacity
    tts_slots_per_key: int = 5         # per-provider-KEY concurrent TTS channels
    # lease + pacing
    reserve_ttl_s: float = 300.0       # reservation lease TTL (self-heals crashed worker)
    pace_backoff_s: float = 4.0        # pacing-queue re-offer backoff when saturated
    # autoscale signal targets
    scale_up_cpu: float = 0.55         # add a worker above this CPU (below load_threshold 0.70)
    scale_down_cpu: float = 0.30       # remove a worker below this for the cool-down window
    warm_pool_min: int = 2             # never drop below this many warm workers

    def effective_global_cap(self) -> int:
        """The hard global ceiling: explicit `global_call_cap` if set, else
        worker_slot_cap * worker_count (the physical fleet wall)."""
        if self.global_call_cap and self.global_call_cap > 0:
            return self.global_call_cap
        return max(1, self.worker_slot_cap) * max(1, self.worker_count)

    @classmethod
    def from_env(cls) -> "ConcurrencyConfig":
        return cls(
            enabled=_flag("CONCURRENCY_ENABLED"),
            worker_slot_cap=_int("CONCURRENCY_WORKER_SLOT_CAP", 20),
            worker_count=_int("CONCURRENCY_WORKER_COUNT", 1),
            global_call_cap=_int("CONCURRENCY_GLOBAL_CALL_CAP", 0),
            tenant_call_cap=_int("CONCURRENCY_TENANT_CALL_CAP", 3),
            llm_rpm=_int("CONCURRENCY_LLM_RPM", 30),
            llm_burst=_int("CONCURRENCY_LLM_BURST", 10),
            tts_slots_per_key=_int("CONCURRENCY_TTS_SLOTS_PER_KEY", 5),
            reserve_ttl_s=_float("CONCURRENCY_RESERVE_TTL_S", 300.0),
            pace_backoff_s=_float("CONCURRENCY_PACE_BACKOFF_S", 4.0),
            scale_up_cpu=_float("CONCURRENCY_SCALE_UP_CPU", 0.55),
            scale_down_cpu=_float("CONCURRENCY_SCALE_DOWN_CPU", 0.30),
            warm_pool_min=_int("CONCURRENCY_WARM_POOL_MIN", 2),
        )
