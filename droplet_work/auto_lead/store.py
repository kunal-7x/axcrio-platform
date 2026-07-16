"""
auto_lead.store — per-tenant Auto-Lead config + activity, persisted as one JSON file
under the runtime VAR dir (same convention as twenty_crm / the rest of caller.py).

Shape: { tenant_id: { "sources": [Source...], "events": [Event...], "settings": {...} } }
Sources carry an unguessable `token` for their public ingest URL. Events are a capped
ring buffer (newest first) feeding the live feed. Lock-guarded for concurrent writes
from the public ingest endpoint + the poller.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.RLock()
_EVENTS_CAP = 400


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AutoLeadStore:
    def __init__(self, var_dir: Path):
        self.path = Path(var_dir) / "auto_lead.json"

    # ── raw file IO ──────────────────────────────────────────────────────────
    def _read_all(self) -> dict:
        try:
            if self.path.exists():
                d = json.loads(self.path.read_text(encoding="utf-8"))
                return d if isinstance(d, dict) else {}
        except Exception:  # noqa: BLE001
            pass
        return {}

    def _write_all(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def _tenant(self, data: dict, tid: str) -> dict:
        t = data.get(tid)
        if not isinstance(t, dict):
            t = {"sources": [], "events": [], "settings": {}}
            data[tid] = t
        t.setdefault("sources", [])
        t.setdefault("events", [])
        t.setdefault("settings", {})
        return t

    # ── sources ──────────────────────────────────────────────────────────────
    def list_sources(self, tid: str) -> list[dict]:
        with _LOCK:
            return list(self._tenant(self._read_all(), tid)["sources"])

    def get_source(self, tid: str, sid: str) -> dict | None:
        with _LOCK:
            for s in self._tenant(self._read_all(), tid)["sources"]:
                if s.get("id") == sid:
                    return dict(s)
        return None

    def find_by_token(self, token: str) -> tuple[str, dict] | None:
        """Resolve a public ingest token -> (tenant_id, source). O(sources)."""
        if not token:
            return None
        with _LOCK:
            data = self._read_all()
            for tid, t in data.items():
                if not isinstance(t, dict):
                    continue
                for s in t.get("sources", []):
                    if s.get("token") == token:
                        return tid, dict(s)
        return None

    def add_source(self, tid: str, src: dict) -> dict:
        with _LOCK:
            data = self._read_all()
            t = self._tenant(data, tid)
            sid = "als_" + uuid.uuid4().hex[:10]
            rec = {
                "id": sid,
                "type": src.get("type") or "custom",
                "name": (src.get("name") or "").strip() or "Untitled source",
                "enabled": bool(src.get("enabled", True)),
                "token": "alt_" + secrets.token_urlsafe(24),
                "config": src.get("config") or {},
                "mapping": src.get("mapping") or {},
                "validation": src.get("validation") or {},
                "routing": src.get("routing") or {},
                "honeypot": (src.get("honeypot") or "").strip(),
                "stats": {"ingested": 0, "accepted": 0, "rejected": 0,
                          "last_at": None, "last_status": None},
                "created_at": _now(),
                "updated_at": _now(),
            }
            t["sources"].append(rec)
            self._write_all(data)
            return dict(rec)

    def update_source(self, tid: str, sid: str, patch: dict) -> dict | None:
        with _LOCK:
            data = self._read_all()
            t = self._tenant(data, tid)
            for s in t["sources"]:
                if s.get("id") == sid:
                    for k in ("name", "enabled", "config", "mapping", "validation",
                              "routing", "honeypot"):
                        if k in patch and patch[k] is not None:
                            s[k] = patch[k]
                    s["updated_at"] = _now()
                    self._write_all(data)
                    return dict(s)
        return None

    def delete_source(self, tid: str, sid: str) -> bool:
        with _LOCK:
            data = self._read_all()
            t = self._tenant(data, tid)
            n = len(t["sources"])
            t["sources"] = [s for s in t["sources"] if s.get("id") != sid]
            if len(t["sources"]) != n:
                self._write_all(data)
                return True
        return False

    def bump_stats(self, tid: str, sid: str, *, accepted: bool, status: str) -> None:
        with _LOCK:
            data = self._read_all()
            t = self._tenant(data, tid)
            for s in t["sources"]:
                if s.get("id") == sid:
                    st = s.setdefault("stats", {})
                    st["ingested"] = int(st.get("ingested", 0)) + 1
                    key = "accepted" if accepted else "rejected"
                    st[key] = int(st.get(key, 0)) + 1
                    st["last_at"] = _now()
                    st["last_status"] = status
                    self._write_all(data)
                    return

    # ── events (activity feed) ────────────────────────────────────────────────
    def add_event(self, tid: str, ev: dict) -> dict:
        with _LOCK:
            data = self._read_all()
            t = self._tenant(data, tid)
            rec = {"id": "ale_" + uuid.uuid4().hex[:10], "at": _now(), **ev}
            t["events"].insert(0, rec)
            del t["events"][_EVENTS_CAP:]
            self._write_all(data)
            return rec

    def list_events(self, tid: str, *, source_id: str = "", status: str = "",
                    limit: int = 100) -> list[dict]:
        with _LOCK:
            evs = list(self._tenant(self._read_all(), tid)["events"])
        if source_id:
            evs = [e for e in evs if e.get("source_id") == source_id]
        if status == "accepted":
            evs = [e for e in evs if e.get("accepted")]
        elif status == "rejected":
            evs = [e for e in evs if not e.get("accepted")]
        return evs[: max(1, min(int(limit or 100), 400))]

    # ── settings ───────────────────────────────────────────────────────────────
    def get_settings(self, tid: str) -> dict:
        with _LOCK:
            return dict(self._tenant(self._read_all(), tid)["settings"])

    def set_settings(self, tid: str, patch: dict) -> dict:
        with _LOCK:
            data = self._read_all()
            t = self._tenant(data, tid)
            t["settings"].update({k: v for k, v in (patch or {}).items()})
            self._write_all(data)
            return dict(t["settings"])

    # ── all enabled sources across tenants (the poll loop filters pull-mode) ───
    def all_enabled_sources(self) -> list[tuple[str, dict]]:
        out: list[tuple[str, dict]] = []
        with _LOCK:
            data = self._read_all()
            for tid, t in data.items():
                if not isinstance(t, dict):
                    continue
                for s in t.get("sources", []):
                    if s.get("enabled"):
                        out.append((tid, dict(s)))
        return out
