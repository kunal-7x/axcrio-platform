"""ai_manager.intent — provider-agnostic NLU package (the AIManagerNLU lives in .driver)."""
from __future__ import annotations

# Consumers import the submodule explicitly (`from .intent import driver`), so we keep this marker
# light and do NOT eagerly re-export `driver`. The guarded import below is a best-effort convenience
# only — a broken/heavy `driver` can NEVER break `import ai_manager.intent` (degrades to absent).
try:  # pragma: no cover - convenience only; absence is non-fatal.
    from . import driver  # noqa: F401
except Exception:  # noqa: BLE001
    driver = None  # type: ignore
