"""voice_ops.concurrency — W24 admission control, autoscale signal, load harness.

The W18 / C1-NEW-W24 concurrency layer. The "replace 500 telecallers" thesis is a
CONCURRENCY claim the live dial loop never modeled: a single LiveKit worker handles
~10-25 concurrent jobs, so the box is perfect on call #1 and silently saturates
~call #20-50. This package adds the missing pre-dial ADMISSION CONTROL so a call is
only placed once every scarce resource is RESERVED:

  - a WORKER SLOT (one active-call slot on a worker; the outermost physical gate),
  - an LLM token (per-tenant + per-provider-key token-bucket budget — the
    denial-of-wallet guard), and
  - a TTS slot (per-provider-key concurrency).

If any is unavailable the call is NOT failed mid-stream — it is PACED/QUEUED and the
dial loop retries on the next tick. Reservations are released on call end (and lease
TTLs self-heal a crashed worker). Every admit/queue/release is emitted on the W8
EventBus so the dashboard/autoscaler react in real time.

Modules (ALL disjoint from live code — zero droplet_work/livekit/redis at import):
  - config.py       : ConcurrencyConfig (env knobs, default-OFF master flag)
  - budget.py       : TokenBucket — atomic per-tenant/per-key rate+burst budget
  - slots.py        : SlotPool — atomic worker/TTS slot counter (lease + release)
  - admission.py    : AdmissionController — the pre-dial reserve()/release() gate
  - autoscale.py    : AutoscaleSignal — active-jobs/CPU/warm-pool recommendation
  - load_harness.py : the 50/100/200-concurrent synthetic LOAD HARNESS (HARD gate)

Reuses: W8 EventBus (voice_kernel.events), W13 HealthScoredKeyPool
(voice_ops.config.keyhealth), W12 CapacityPlanner / NumberPool
(voice_ops.telephony), W5 ProviderRouter (voice_kernel.providers.router).

EARNER-SAFE: imports ZERO droplet_work / livekit / redis at module load (every
heavy import is lazy inside a function); the master flag CONCURRENCY_ENABLED is
default-OFF; the package is a TRACKED, disjoint wrapper that NEVER edits the live
agent.py / caller.py — the caller.py admission seam is a DOC
(design/W24-CONCURRENCY-SEAM.md), applied later by a founder-signed seam wave.
"""
from __future__ import annotations

from .admission import AdmissionController, AdmissionDecision, Reservation
from .autoscale import AutoscaleSignal, ScaleRecommendation
from .budget import TokenBucket
from .config import ConcurrencyConfig
from .slots import SlotPool

__all__ = [
    "ConcurrencyConfig",
    "TokenBucket",
    "SlotPool",
    "AdmissionController",
    "AdmissionDecision",
    "Reservation",
    "AutoscaleSignal",
    "ScaleRecommendation",
]
