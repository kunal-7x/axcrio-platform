"""voice_ops — TRACKED, droplet-free operational packages that WRAP (never edit)
the live voice boxes (agent.py / caller.py / aim_voice_agent.py).

This package is git-tracked (NOT inside the gitignored `droplet_work/`). It
imports ZERO droplet_work modules and ZERO heavy SDKs at module load — every
livekit / boto3 / redis import is LAZY (inside a function), exactly like
`voice_kernel.integrations.*`. So `import voice_ops...` is cheap and safe to load
on any host (CI included) without pulling the box runtime into sys.modules.

Sub-packages:
  - recording/  W9: real-time recording finalize + staged transcript/summary
                pipeline + object storage (R2/B2) + retention/cleanup/audit +
                the panel status API contract. Reuses voice_kernel.events.
"""
