"""voice_ops.telephony — the self-managing OUTBOUND Sales-OS layer (W12).

TRACKED + droplet-free. Turns "dial a list" into a SAFE, self-throttling outbound
machine that can run 500–1000 calls/day inside a calling window without burning a
phone number's reputation or double-dialing a lead. Imports ZERO droplet_work and
ZERO heavy SDKs at module load (every redis / psycopg2 / livekit touch is lazy),
exactly like the rest of voice_ops — so `import voice_ops.telephony` is cheap and
safe on any host (CI included).

Sub-modules:
  - config.py            TelephonyOpsConfig — flags + knobs (master TELEPHONY_OPS_ENABLED, default OFF).
  - capacity_planner.py  CapacityPlanner — leads × numbers × window × concurrency × answer-rate
                         -> safe daily target + warn-if-insufficient (advisory, never blocks).
  - number_pool.py       NumberPool — add/distribute numbers, per-number cooldown + usage,
                         InMemory + PG-backed (FORCE-RLS phone_number_pool) behind one Protocol.
  - health.py            SpamReputation — rolling answer/reject/block scorer per number; auto-reduce
                         traffic to unhealthy numbers, auto-recover on improvement.
  - router.py            AdaptiveRouter — pick the next number by capacity + cooldown + health;
                         NEVER overloads a single number, NEVER violates a cooldown.
  - lead_lock.py         LeadLock — per-lead TTL mutex; a lead is NEVER double-dialed / dialed by 2 numbers.
  - window.py            CallingWindowScheduler — run only in window, pause/resume across days,
                         wired to the compliance LEGAL hard-floor (a tenant cannot widen past the law).

Earner-safety: this whole package is a LAYER that the live dial loop (caller.py) calls
through documented seams (design/W12-TELEPHONY-COMPLIANCE-SEAM.md). It NEVER imports
agent.py, NEVER originates a SIP call, and NEVER raises into the dial loop — every
public method is best-effort and fail-open on its own internal error (the call still
goes), while the COMPLIANCE layer (voice_ops.compliance) is the fail-CLOSED gate.
"""
