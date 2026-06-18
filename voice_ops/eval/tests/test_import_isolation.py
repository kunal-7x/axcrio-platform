"""W17 — IMPORT ISOLATION. Importing the eval harness (and running a full gate
batch) must pull ZERO droplet_work modules and ZERO heavy SDKs at module load —
the same guarantee voice_kernel.integrations and voice_ops.* enforce, so the
harness can run in CI on any host without dragging the box runtime into
sys.modules (which could break the sacred earner's OFF path)."""
from __future__ import annotations

import importlib
import sys


_EVAL_MODULES = (
    "voice_ops.eval",
    "voice_ops.eval.verticals",
    "voice_ops.eval.regression_gates",
    "voice_ops.eval.replay",
    "voice_ops.eval.metrics",
)


def test_importing_eval_pulls_zero_droplet_modules():
    for name in _EVAL_MODULES:
        importlib.import_module(name)
    leaked = [m for m in sys.modules if m.startswith("droplet_work")]
    assert leaked == [], f"droplet_work leaked at import: {leaked}"


def test_no_heavy_sdk_at_eval_import():
    """No livekit / boto3 / redis / qdrant pulled merely by importing the harness
    (every such import is lazy inside the wrapped services)."""
    for name in _EVAL_MODULES:
        importlib.import_module(name)
    heavy = [m for m in sys.modules if m.split(".")[0] in {"livekit", "boto3", "botocore", "redis", "qdrant_client"}]
    assert heavy == [], f"heavy SDK pulled at eval import: {heavy}"


def test_running_gates_stays_droplet_free():
    """Even after driving the kernel ON through a full gate batch, no droplet_work
    module is imported (the kernel façade is droplet-free by construction)."""
    from voice_ops.eval.regression_gates import run_all_gates

    run_all_gates()
    leaked = [m for m in sys.modules if m.startswith("droplet_work")]
    assert leaked == [], f"droplet_work leaked while running gates: {leaked}"
