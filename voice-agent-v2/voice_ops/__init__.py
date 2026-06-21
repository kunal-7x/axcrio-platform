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
  - booking/    W11: AI `book_site_visit` tool + full appointment lifecycle
                (manual + AI) over the booking engine (lazy-wrapped, no double-book
                inherited) + W8 site_visit_booked emit, AND the warm-transfer
                hardening brain (one-line ack + dial/exit plan + state log).
  - gcal/       W11: Google Calendar OAuth (server-side flow + self-contained
                AAD AES-256-GCM refresh-token vault) + ASYNC event create/
                update/cancel on booking changes (never blocks the call).
"""
