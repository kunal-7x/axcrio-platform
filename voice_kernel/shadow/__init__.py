"""voice_kernel.shadow — outbound shadow sidecar.

HARD RULE (red-team earner-safety boundary): this sidecar is a STANDALONE
process that NEVER imports droplet_work.agent and is NEVER added to the live
agent's process. It reads dispatch metadata OUT-OF-BAND (a dict / JSON the
dispatcher already emits) and computes the kernel packet for observability ONLY
— it never substitutes the live instructions string.

`test_shadow_isolation.py` mechanically asserts that importing voice_kernel (and
this sidecar) pulls in ZERO droplet_work modules.
"""
