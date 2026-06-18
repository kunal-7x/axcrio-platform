"""Test config for the integration tests: make the repo root importable and
expose the SAME isolated legacy-prompt loader used by the core kernel tests, so
the OFF byte-identity test runs against the REAL droplet_work/prompt.py
build_system_prompt (never importing droplet_work.agent)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]  # voice_kernel/integrations/tests/ -> repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def load_legacy_prompt_module():
    """Load droplet_work/prompt.py as an isolated module (stdlib-only imports).

    Returns None if the file is absent (CI checkout without droplet_work). Mirrors
    voice_kernel/tests/conftest.py — we do NOT import droplet_work.agent and do NOT
    register a 'droplet_work' package.
    """
    p = _REPO_ROOT / "droplet_work" / "prompt.py"
    if not p.exists():
        return None
    spec = importlib.util.spec_from_file_location("_legacy_prompt_for_integ_tests", str(p))
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
