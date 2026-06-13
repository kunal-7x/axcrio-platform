"""memory.py — lightweight cross-call memory for the Famit voice agent.

Every LLM turn is stateless, and a LiveKit room is fresh per call, so without this
the agent forgets a lead between calls. This module gives durable per-lead memory:
a small JSON file keyed by phone number, holding the prior call's dialog and a recap
string that gets injected into the next call's campaign_context as `previous_context`.

Design goals:
  * Zero extra dependencies (stdlib json/os only) so it cannot break the live service.
  * Every function is wrapped so a memory failure NEVER crashes a call — memory is
    additive; if it errors we just behave like a first-time call.

Keyed by phone, which we recover from the LiveKit room name. Outbound rooms are named
`famit-<digits>-<rand>` by the dialer (scripts/make_call), so parse_phone() pulls the
longest digit run out of the room name.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_MEM_DIR = Path(os.getenv("MEMORY_DIR", "/opt/famit-agent/var/memory"))
_MAX_TURNS_SAVED = 16          # cap stored history so files stay tiny
_MAX_RECAP_TURNS = 8           # how many recent turns feed the recap


def parse_phone(room_name: str | None) -> str:
    """Best-effort extract a phone-ish key from a LiveKit room name.

    Returns the longest digit run (>= 6 digits) found, else "". Never raises.
    """
    try:
        if not room_name:
            return ""
        runs = re.findall(r"\d{6,}", room_name)
        return max(runs, key=len) if runs else ""
    except Exception:  # noqa: BLE001
        return ""


def _safe_tenant(tenant_id: str | None) -> str:
    """Filesystem-safe single path segment for a tenant id. No '/', '..', or
    leading dots (can't escape _MEM_DIR). Empty/None -> '' (caller uses legacy)."""
    t = re.sub(r"[^A-Za-z0-9_-]", "", str(tenant_id or "")).strip("-_")
    return t


def _path_for(phone: str, tenant_id: str | None = None) -> Path:
    """Memory file path for a phone.

    P0-LEAK fix: when a tenant_id is supplied the file is namespaced under a
    per-tenant subdir -> ``{tenant}/{phone}.json`` so tenant A can never read
    tenant B's memory. With NO tenant_id (the un-migrated earner's old call
    sites) it stays the LEGACY flat ``{phone}.json`` — keeping the contract the
    un-restarted earner still writes/reads, so this change is fully additive.
    """
    safe = re.sub(r"[^0-9]", "", phone or "") or "unknown"
    tdir = _safe_tenant(tenant_id)
    if tdir:
        return _MEM_DIR / tdir / f"{safe}.json"
    return _MEM_DIR / f"{safe}.json"


def _legacy_path_for(phone: str) -> Path:
    safe = re.sub(r"[^0-9]", "", phone or "") or "unknown"
    return _MEM_DIR / f"{safe}.json"


def load_memory(phone: str, tenant_id: str | None = None) -> dict | None:
    """Load prior memory for a phone, or None if absent/unreadable.

    Tenant-scoped read with a TENANT-CHECKED legacy fallback + migrate-on-read:
      1. Prefer the per-tenant file ``{tenant}/{phone}.json``.
      2. If absent, fall back to the LEGACY flat ``{phone}.json`` (which the
         un-restarted earner still writes) ONLY IF it is attributable to THIS
         tenant — its stored ``tenant_id`` matches, OR it has none (we claim it).
         A legacy file owned by a DIFFERENT tenant is NEVER returned (returning
         it blindly would re-open the cross-tenant leak).
      3. On a successful legacy hit, migrate the record into the tenant path
         (stamp its tenant_id) so the next read is clean and tenant-scoped.
    With no tenant_id, behaves exactly as before (legacy flat read) — the
    earner's old call sites keep working unchanged.
    """
    try:
        if not phone:
            return None
        tdir = _safe_tenant(tenant_id)
        # No tenant context (legacy/earner caller): legacy flat read, unchanged.
        if not tdir:
            p = _legacy_path_for(phone)
            if not p.exists():
                return None
            return json.loads(p.read_text(encoding="utf-8"))
        # Tenant context: prefer the namespaced file.
        tp = _path_for(phone, tenant_id)
        if tp.exists():
            return json.loads(tp.read_text(encoding="utf-8"))
        # Tenant-checked legacy fallback (earner-written or pre-migration files).
        lp = _legacy_path_for(phone)
        if not lp.exists():
            return None
        rec = json.loads(lp.read_text(encoding="utf-8"))
        owner = _safe_tenant(rec.get("tenant_id") if isinstance(rec, dict) else None)
        if owner and owner != tdir:
            # Legacy file belongs to a DIFFERENT tenant -> do NOT return it.
            return None
        # Same tenant, or unowned/unclaimed -> claim + migrate into the tenant path.
        if isinstance(rec, dict):
            rec["tenant_id"] = tenant_id
            try:
                tp.parent.mkdir(parents=True, exist_ok=True)
                tp.write_text(json.dumps(rec, ensure_ascii=False, indent=2),
                              encoding="utf-8")
            except Exception:  # noqa: BLE001 — migration is best-effort
                pass
        return rec
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory load failed phone=%s tenant=%s err=%r",
                       phone, tenant_id, exc)
        return None


def build_recap(mem: dict | None, agent_name: str | None = None) -> str:
    """Turn a stored memory record into a short text recap for previous_context.

    Prefers an explicit saved summary; otherwise stitches the last few turns.
    Returns "" if there is nothing useful. Never raises.

    ``agent_name`` labels the assistant turns in the stitched transcript; with
    no value it keeps the legacy "Riya" label so existing callers are unchanged.
    """
    try:
        if not mem:
            return ""
        agent_label = (agent_name or "").strip() or "Riya"
        parts: list[str] = []
        if mem.get("summary"):
            parts.append(str(mem["summary"]).strip())
        history = mem.get("history") or []
        if history and not parts:
            recent = history[-_MAX_RECAP_TURNS:]
            for turn in recent:
                role = "Caller" if turn.get("role") == "user" else agent_label
                content = (turn.get("content") or "").strip()
                if content and not content.startswith("["):
                    parts.append(f"{role}: {content}")
        when = mem.get("last_call_at")
        head = f"(pichhli call: {when}) " if when else ""
        recap = head + " | ".join(p for p in parts if p)
        return recap[:600].strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory recap failed err=%r", exc)
        return ""


def save_memory(phone: str, history: list[dict] | None, summary: str = "",
                tenant_id: str | None = None) -> None:
    """Persist this call's dialog + optional summary for the phone. Never raises.

    P0-LEAK: when a tenant_id is given the record is stamped with it and written
    to the per-tenant path ``{tenant}/{phone}.json``. With no tenant_id (the
    un-restarted earner) it writes the LEGACY flat ``{phone}.json`` exactly as
    before — additive, so the earner is unaffected and its files remain
    readable by a tenant-aware reader for the SAME tenant via the fallback.
    """
    try:
        if not phone:
            return
        history = [
            t for t in (history or [])
            if (t.get("content") or "").strip() and not (t.get("content") or "").startswith("[")
        ]
        if not history and not summary:
            return
        record = {
            "phone": phone,
            "tenant_id": tenant_id or "",
            "last_call_at": time.strftime("%Y-%m-%d %H:%M", time.localtime()),
            "summary": (summary or "").strip(),
            "history": history[-_MAX_TURNS_SAVED:],
        }
        p = _path_for(phone, tenant_id)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info("memory saved phone=%s tenant=%s turns=%d",
                    phone, tenant_id or "-", len(record["history"]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("memory save failed phone=%s tenant=%s err=%r",
                       phone, tenant_id, exc)
