"""
twenty_crm.store — per-tenant Twenty connection settings.

Each Haptica tenant connects *their own* Twenty workspace (URL + API key), so the
connection is stored per-tenant in a single JSON file under the runtime VAR dir
(same convention as the rest of caller.py's small stores). The API key is a
secret: it is stored server-side and NEVER returned to the browser — reads hand
back a masked tail only.

Resolution order used by the router:
  1. the tenant's saved connection (set via POST /twenty/connect)
  2. an env-level fallback (TWENTY_API_URL / TWENTY_API_KEY) so a single-tenant /
     dev deploy works with zero clicks.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

_LOCK = threading.Lock()


class TwentyStore:
    def __init__(self, var_dir: Path, *, env_url: str = "", env_key: str = ""):
        self.path = Path(var_dir) / "twenty_connections.json"
        self.env_url = (env_url or "").strip()
        self.env_key = (env_key or "").strip()

    # ── raw file IO ──────────────────────────────────────────────────────────
    def _read_all(self) -> dict:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            pass
        return {}

    def _write_all(self, data: dict) -> None:
        # Atomic-ish: write a temp sibling then os.replace (never leaves a torn file).
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    # ── connection resolution ────────────────────────────────────────────────
    def resolve(self, tenant_id: str) -> dict | None:
        """The live {base_url, api_key, source} for a tenant, or None if neither a
        saved connection nor an env fallback exists. ``source`` ∈ {tenant, self_host, env}."""
        with _LOCK:
            rec = self._read_all().get(tenant_id)
        if rec and rec.get("base_url") and rec.get("api_key"):
            return {"base_url": rec["base_url"], "api_key": rec["api_key"],
                    "source": rec.get("source") or "tenant"}
        if self.env_url and self.env_key:
            return {"base_url": self.env_url, "api_key": self.env_key, "source": "env"}
        return None

    def status(self, tenant_id: str) -> dict:
        """Browser-safe status: connected flag + masked key tail, NO secret."""
        with _LOCK:
            rec = self._read_all().get(tenant_id)
        if rec and rec.get("base_url") and rec.get("api_key"):
            return {
                "connected": True,
                "source": rec.get("source") or "tenant",
                "base_url": rec["base_url"],
                "key_masked": _mask(rec["api_key"]),
                "connected_at": rec.get("connected_at"),
                "workspace_id": rec.get("workspace_id"),
            }
        if self.env_url and self.env_key:
            return {
                "connected": True,
                "source": "env",
                "base_url": self.env_url,
                "key_masked": _mask(self.env_key),
                "connected_at": None,
                "workspace_id": None,
            }
        return {"connected": False, "source": None, "base_url": "", "key_masked": "",
                "connected_at": None, "workspace_id": None}

    def set(self, tenant_id: str, base_url: str, api_key: str, *, when: str | None = None,
            source: str = "tenant", workspace_id: str | None = None,
            email: str | None = None) -> None:
        with _LOCK:
            data = self._read_all()
            data[tenant_id] = {
                "base_url": (base_url or "").strip(),
                "api_key": (api_key or "").strip(),
                "connected_at": when,
                "source": source,
                "workspace_id": workspace_id,
                "email": email,
            }
            self._write_all(data)

    def delete(self, tenant_id: str) -> None:
        with _LOCK:
            data = self._read_all()
            if tenant_id in data:
                data.pop(tenant_id, None)
                self._write_all(data)


def _mask(key: str) -> str:
    k = (key or "").strip()
    if len(k) <= 4:
        return "••••"
    return "••••" + k[-4:]
