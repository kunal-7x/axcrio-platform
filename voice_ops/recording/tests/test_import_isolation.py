"""Prove the earner-law isolation: importing voice_ops.recording pulls ZERO
droplet_work, ZERO livekit, ZERO boto3, ZERO redis at module load. Every heavy
import is lazy inside a function. This is the test that guards the whole posture.
"""
from __future__ import annotations

import importlib
import sys


def test_import_pulls_no_heavy_or_droplet_modules():
    # Drop any pre-imported heavy modules so we measure THIS import's footprint.
    forbidden = ("droplet_work", "livekit", "boto3", "botocore", "redis")
    for name in list(sys.modules):
        if name == "droplet_work" or name.startswith("droplet_work."):
            del sys.modules[name]

    before = set(sys.modules)
    # Fresh import of the package + every submodule.
    for mod in (
        "voice_ops.recording",
        "voice_ops.recording.config",
        "voice_ops.recording.storage",
        "voice_ops.recording.egress",
        "voice_ops.recording.poller",
        "voice_ops.recording.pipeline",
        "voice_ops.recording.retention",
        "voice_ops.recording.api",
    ):
        importlib.import_module(mod)
    newly = set(sys.modules) - before

    leaked = [m for m in newly if any(m == f or m.startswith(f + ".") for f in forbidden)]
    assert leaked == [], f"voice_ops.recording leaked heavy/droplet imports at load: {leaked}"


def test_no_droplet_or_sdk_in_source_top_level():
    """Static guard: no top-level `import livekit/boto3/redis/droplet_work` lines.
    They must all be lazy (inside a function)."""
    import pathlib

    pkg = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for py in pkg.glob("*.py"):
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if s.startswith("#") or not s:
                continue
            # only flag MODULE-LEVEL (column 0) imports
            if line[:1] not in (" ", "\t") and (s.startswith("import ") or s.startswith("from ")):
                for bad in ("livekit", "boto3", "botocore", "redis", "droplet_work"):
                    if bad in s:
                        offenders.append(f"{py.name}:{i}: {s}")
    assert offenders == [], f"top-level heavy imports must be lazy: {offenders}"
