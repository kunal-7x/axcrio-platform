"""Earner-law isolation: importing voice_ops.concurrency pulls ZERO droplet_work,
livekit, boto3, redis, psutil at module load. Every heavy import is lazy inside a
function. This is the test that guards the disjoint-from-the-earner posture."""
from __future__ import annotations

import importlib
import sys


def test_import_pulls_no_heavy_or_droplet_modules():
    forbidden = ("droplet_work", "livekit", "boto3", "botocore", "redis", "psutil")
    for name in list(sys.modules):
        if name == "droplet_work" or name.startswith("droplet_work."):
            del sys.modules[name]

    before = set(sys.modules)
    for mod in (
        "voice_ops.concurrency",
        "voice_ops.concurrency.config",
        "voice_ops.concurrency.budget",
        "voice_ops.concurrency.slots",
        "voice_ops.concurrency.admission",
        "voice_ops.concurrency.autoscale",
        "voice_ops.concurrency.load_harness",
    ):
        importlib.import_module(mod)
    newly = set(sys.modules) - before

    leaked = [m for m in newly if any(m == f or m.startswith(f + ".") for f in forbidden)]
    assert leaked == [], f"voice_ops.concurrency leaked heavy/droplet imports at load: {leaked}"


def test_no_droplet_or_sdk_in_source_top_level():
    """Static guard: no MODULE-LEVEL `import livekit/boto3/redis/psutil/droplet_work`.
    They must all be lazy (inside a function)."""
    import pathlib

    pkg = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for py in pkg.glob("*.py"):
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if s.startswith("#") or not s:
                continue
            if line[:1] not in (" ", "\t") and (s.startswith("import ") or s.startswith("from ")):
                for bad in ("livekit", "boto3", "botocore", "redis", "psutil", "droplet_work"):
                    if bad in s:
                        offenders.append(f"{py.name}:{i}: {s}")
    assert offenders == [], f"top-level heavy imports must be lazy: {offenders}"
