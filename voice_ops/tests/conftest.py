"""Test config for voice_ops: put the repo root on sys.path so `import voice_ops`
and `import voice_kernel` resolve when pytest runs from anywhere. Mirrors
voice_kernel/tests/conftest.py. Async tests use the repo convention:
asyncio.run() inside a sync test (no asyncio_mode config needed)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
