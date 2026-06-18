"""voice_kernel.shadow.runner — compute-and-log the outbound packet, never substitute.

Under KERNEL_OUTBOUND_SHADOW, the dispatcher (out-of-band) can hand this runner
the dispatch metadata it ALREADY has (tenant/campaign/call/room + the campaign
`fields` dict). The runner computes the kernel packet prefix and logs its size /
byte-diff vs an optionally-provided legacy string — for observability ONLY.

It NEVER imports droplet_work, NEVER touches agent.py's process, and NEVER
returns a string that substitutes the live instructions. The live outbound path
keeps using its own legacy string regardless of this runner.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..config import KernelConfig
from ..contracts import CallContext, KernelSession
from ..kernel import build_kernel
from ..packet import PacketMeta

log = logging.getLogger("voice_kernel.shadow")


def shadow_compute(
    dispatch_meta: dict,
    fields: dict,
    *,
    cfg: Optional[KernelConfig] = None,
    legacy_string: Optional[str] = None,
) -> dict:
    """Compute the kernel packet from out-of-band dispatch metadata and return a
    small observability report (sizes + optional byte-match). Does NOT raise on
    a normal failure — shadow must never affect anything live.

    `dispatch_meta` keys (all the dispatcher already has):
        tenant_id, campaign_id, call_id, room, lead_phone (optional).
    """
    cfg = cfg or KernelConfig.from_env()
    report: dict = {"active": cfg.shadow_active(), "ok": False}
    if not cfg.shadow_active():
        return report
    try:
        tenant_id = str(dispatch_meta.get("tenant_id", ""))
        call_id = str(dispatch_meta.get("call_id", ""))
        meta = PacketMeta(
            tenant_id=tenant_id,
            campaign_id=str(dispatch_meta.get("campaign_id", "")),
            call_id=call_id,
            room=str(dispatch_meta.get("room", "")),
            lead_phone=str(dispatch_meta.get("lead_phone", "")),
            direction="outbound",
        )
        # C2: the dispatcher hands us SERVER-SIDE metadata it already resolved
        # (it is out-of-band, never a caller body) — so we stamp the KernelSession
        # here. A missing tenant_id/call_id raises (fail-closed) and the shadow
        # report records the error without ever touching the live path.
        session = KernelSession(tenant_id=tenant_id, call_id=call_id, direction="outbound")
        ctx = CallContext(meta=meta, fields=dict(fields or {}), session=session)
        prefix = build_kernel(cfg).assemble_prefix(ctx)
        report.update(
            ok=True,
            kernel_prefix_chars=len(prefix),
            legacy_chars=len(legacy_string) if legacy_string is not None else None,
            byte_identical=(prefix == legacy_string) if legacy_string is not None else None,
        )
        log.info(
            "shadow packet computed: kernel=%dch legacy=%s call=%s",
            len(prefix),
            report["legacy_chars"],
            meta.call_id,
        )
    except Exception as exc:  # shadow must never affect anything live
        log.warning("shadow_compute failed (non-fatal, observability only): %r", exc)
        report["error"] = repr(exc)
    return report
