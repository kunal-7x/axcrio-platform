"""Put the repo root on sys.path so `import voice_ops` / `import voice_kernel`
resolve under pytest. Mirrors voice_ops/tests/conftest.py."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
