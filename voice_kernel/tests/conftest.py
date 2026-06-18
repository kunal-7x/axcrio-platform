"""Test config: make the repo root importable so `import voice_kernel` works
when pytest is run from anywhere, and expose a helper to load the REAL legacy
prompt builder from droplet_work/prompt.py WITHOUT importing droplet as a package
(it is gitignored / not a package) and WITHOUT touching agent.py."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def load_legacy_prompt_module():
    """Load droplet_work/prompt.py as an isolated module object.

    prompt.py imports only stdlib (os, re, unicodedata) — verified import-safe.
    We DO NOT import droplet_work.agent (forbidden) and we DO NOT register a
    'droplet_work' package; this loads the single file under a private name.
    Returns None if the file is absent (CI checkout without droplet_work).
    """
    p = _REPO_ROOT / "droplet_work" / "prompt.py"
    if not p.exists():
        return None
    spec = importlib.util.spec_from_file_location("_legacy_prompt_for_tests", str(p))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod
