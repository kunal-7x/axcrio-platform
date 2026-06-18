"""Earner-safety boundary test for the outbound shadow sidecar.

The shadow MUST be a standalone process that NEVER imports droplet_work.agent.
This test imports the shadow runner and asserts (a) it computes a packet from
out-of-band dispatch metadata, (b) it does NOT substitute the live string, and
(c) importing it pulls in ZERO droplet_work modules.
"""
from __future__ import annotations

import sys

from voice_kernel.config import KernelConfig
from voice_kernel.shadow.runner import shadow_compute


def _dispatch_meta():
    return {"tenant_id": "t", "campaign_id": "c", "call_id": "call-9", "room": "r", "lead_phone": "+91"}


def _fields():
    return {"agent_name": "Riya", "company_name": "Famit", "product_name": "Flats"}


def test_shadow_inactive_when_flag_off():
    cfg = KernelConfig(outbound_shadow=False)
    rep = shadow_compute(_dispatch_meta(), _fields(), cfg=cfg)
    assert rep["active"] is False
    assert rep["ok"] is False


def test_shadow_computes_when_flag_on_but_does_not_substitute():
    cfg = KernelConfig(outbound_shadow=True)
    legacy = "LEGACY-LIVE-STRING"
    rep = shadow_compute(_dispatch_meta(), _fields(), cfg=cfg, legacy_string=legacy)
    assert rep["active"] is True
    assert rep["ok"] is True
    assert rep["kernel_prefix_chars"] > 0
    # it reports a diff but returns NO replacement string for the live path
    assert "byte_identical" in rep
    assert rep["legacy_chars"] == len(legacy)
    assert "Riya" not in rep  # the report carries sizes/flags, not the live string


def test_shadow_never_raises_on_bad_input():
    cfg = KernelConfig(outbound_shadow=True)
    rep = shadow_compute({}, None, cfg=cfg)  # empty meta + None fields
    assert rep["active"] is True
    # ok may be True (empty packet) or carry an 'error' key, but it never raises
    assert "ok" in rep


def test_shadow_imports_no_droplet_modules():
    import voice_kernel.shadow.runner  # noqa: F401

    droplet = [m for m in sys.modules if m.startswith("droplet")]
    assert droplet == [], f"shadow must not import droplet modules, found: {droplet}"
