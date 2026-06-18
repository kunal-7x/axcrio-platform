"""Test config for voice_ops.deploy: put the repo root on sys.path so
`import voice_ops` resolves when pytest runs from anywhere. Mirrors
voice_ops/tests/conftest.py. No droplet imports, no box, no PSTN — every box
interaction is driven through transport.FakeTransport."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
