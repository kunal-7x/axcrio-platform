"""voice_ops.whatsapp.store — tenant-scoped, FORCE-RLS persistence for media + delivery.

Two stores, same posture as voice_ops.config.store / voice_ops.reporting.store:

  * default backend = a dependency-free, thread-safe InMemory dict (CI + resting
    build + a perfectly-good cache when Postgres is absent — degrade, never crash);
  * a lazy `_PostgresBackend` rides the P1 `db.engine` spine with RLS GUCs set per
    session, exactly like config.store — this module imports ZERO sqlalchemy at load.

Every method is TENANT-SCOPED and fail-closed on an empty tenant_id — never a
cross-tenant read/write. The DDL lives in voice_ops/db/ddl_whatsapp_media.sql.
"""
from __future__ import annotations

import json
import logging
import threading
from typing import Iterable, Optional

from .model import MediaAsset, MediaKind, DeliveryRow, DeliveryStatus, status_order

log = logging.getLogger("voice_ops.whatsapp.store")


# =========================================================================== #
# MEDIA
# =========================================================================== #
class InMemoryMediaBackend:
    """Thread-safe dict backend: (tenant_id, id) -> MediaAsset."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], MediaAsset] = {}
        self._lock = threading.RLock()

    def upsert(self, a: MediaAsset) -> None:
        with self._lock:
            self._rows[(a.tenant_id, a.id)] = a.copy()

    def get(self, tenant_id: str, asset_id: str) -> Optional[MediaAsset]:
        with self._lock:
            a = self._rows.get((tenant_id, asset_id))
            return a.copy() if a else None

    def scan(self, tenant_id: str) -> list[MediaAsset]:
        with self._lock:
            return [a.copy() for (t, _i), a in self._rows.items() if t == tenant_id]

    def delete(self, tenant_id: str, asset_id: str) -> bool:
        with self._lock:
            return self._rows.pop((tenant_id, asset_id), None) is not None


class _PgMediaBackend:
    """Lazy, RLS-honoring Postgres backend (mirrors config.store._PostgresBackend)."""

    def _engine(self):
        try:
            from db import engine as eng  # type: ignore
            return eng if eng.available() else None
        except Exception:  # noqa: BLE001
            return None

    def _text(self, sql: str):
        from sqlalchemy import text
        return text(sql)

    def upsert(self, a: MediaAsset) -> None:
        eng = self._engine()
        if eng is None:
            return
        try:
            with eng.session(tenant_id=a.tenant_id, is_admin=False) as s:
                s.execute(self._text(
                    "INSERT INTO wa_media (org_id,id,kind,media_type,title,storage_key,content_type,"
                    " size_bytes,width,height,duration_s,page_count,source,tags,used_count,status,"
                    " created_by,created_at,updated_at) VALUES (:org,:id,:kind,:mt,:title,:key,:ct,"
                    " :sz,:w,:h,:dur,:pc,:src,CAST(:tags AS jsonb),:uc,:st,:by,now(),now()) "
                    "ON CONFLICT (org_id,id) DO UPDATE SET kind=:kind,media_type=:mt,title=:title,"
                    " storage_key=:key,content_type=:ct,size_bytes=:sz,width=:w,height=:h,"
                    " duration_s=:dur,page_count=:pc,source=:src,tags=CAST(:tags AS jsonb),"
                    " used_count=:uc,status=:st,updated_at=now()"
                ), {"org": a.tenant_id, "id": a.id, "kind": a.kind.value, "mt": a.media_type,
                    "title": a.title, "key": a.storage_key, "ct": a.content_type, "sz": a.size_bytes,
                    "w": a.width, "h": a.height, "dur": a.duration_s, "pc": a.page_count,
                    "src": a.source, "tags": json.dumps(a.tags or []), "uc": a.used_count,
                    "st": a.status, "by": a.created_by})
        except Exception as exc:  # noqa: BLE001
            log.info("wa_media upsert failed: %r", exc)

    def _row_to_asset(self, tenant_id: str, r) -> MediaAsset:
        tags = r[12]
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = []
        return MediaAsset(
            tenant_id=tenant_id, id=r[0], kind=MediaKind.coerce(r[1]), title=r[2] or "",
            storage_key=r[3] or "", content_type=r[4] or "", size_bytes=int(r[5] or 0),
            width=int(r[6] or 0), height=int(r[7] or 0), duration_s=int(r[8] or 0),
            page_count=int(r[9] or 0), source=r[10] or "uploaded", used_count=int(r[11] or 0),
            tags=tags or [], status=r[13] or "ready", created_by=r[14] or "")

    _SELECT = ("SELECT id,kind,title,storage_key,content_type,size_bytes,width,height,duration_s,"
               "page_count,source,used_count,tags,status,created_by FROM wa_media WHERE org_id=:org")

    def get(self, tenant_id: str, asset_id: str) -> Optional[MediaAsset]:
        eng = self._engine()
        if eng is None:
            return None
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                r = s.execute(self._text(self._SELECT + " AND id=:id"),
                              {"org": tenant_id, "id": asset_id}).fetchone()
                return self._row_to_asset(tenant_id, r) if r else None
        except Exception as exc:  # noqa: BLE001
            log.info("wa_media get failed: %r", exc)
            return None

    def scan(self, tenant_id: str) -> list[MediaAsset]:
        eng = self._engine()
        if eng is None:
            return []
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                rows = s.execute(self._text(self._SELECT + " ORDER BY created_at DESC"),
                                 {"org": tenant_id}).fetchall()
                return [self._row_to_asset(tenant_id, r) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.info("wa_media scan failed: %r", exc)
            return []

    def delete(self, tenant_id: str, asset_id: str) -> bool:
        eng = self._engine()
        if eng is None:
            return False
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                res = s.execute(self._text("DELETE FROM wa_media WHERE org_id=:org AND id=:id"),
                                {"org": tenant_id, "id": asset_id})
                return bool(getattr(res, "rowcount", 0))
        except Exception as exc:  # noqa: BLE001
            log.info("wa_media delete failed: %r", exc)
            return False


class MediaStore:
    """Tenant-scoped facade over a media backend. Fail-closed on empty tenant."""

    def __init__(self, backend=None) -> None:
        self.backend = backend or InMemoryMediaBackend()

    @staticmethod
    def _ok(tenant_id: str) -> bool:
        return bool((tenant_id or "").strip())

    def upsert(self, a: MediaAsset) -> bool:
        if not self._ok(a.tenant_id) or not (a.id or "").strip():
            log.warning("MediaStore.upsert dropped: missing tenant/id")
            return False
        self.backend.upsert(a)
        return True

    def get(self, tenant_id: str, asset_id: str) -> Optional[MediaAsset]:
        if not self._ok(tenant_id):
            return None
        return self.backend.get(tenant_id, asset_id)

    def list(self, tenant_id: str, *, kind: Optional[str] = None,
             include_archived: bool = False) -> list[MediaAsset]:
        if not self._ok(tenant_id):
            return []
        rows = self.backend.scan(tenant_id)
        if not include_archived:
            rows = [a for a in rows if a.status != "archived"]
        if kind:
            k = MediaKind.coerce(kind)
            rows = [a for a in rows if a.kind == k]
        rows.sort(key=lambda a: a.created_at, reverse=True)
        return rows

    def delete(self, tenant_id: str, asset_id: str) -> bool:
        if not self._ok(tenant_id):
            return False
        return self.backend.delete(tenant_id, asset_id)


# =========================================================================== #
# DELIVERY
# =========================================================================== #
class InMemoryDeliveryBackend:
    """Thread-safe dict backend: (tenant_id, message_id) -> DeliveryRow."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], DeliveryRow] = {}
        self._lock = threading.RLock()

    def get(self, tenant_id: str, message_id: str) -> Optional[DeliveryRow]:
        with self._lock:
            r = self._rows.get((tenant_id, message_id))
            return r.copy() if r else None

    def upsert(self, r: DeliveryRow) -> None:
        with self._lock:
            self._rows[(r.tenant_id, r.message_id)] = r.copy()

    def scan(self, tenant_id: str) -> list[DeliveryRow]:
        with self._lock:
            return [r.copy() for (t, _m), r in self._rows.items() if t == tenant_id]


class _PgDeliveryBackend:
    """Lazy RLS Postgres delivery backend."""

    def _engine(self):
        try:
            from db import engine as eng  # type: ignore
            return eng if eng.available() else None
        except Exception:  # noqa: BLE001
            return None

    def _text(self, sql: str):
        from sqlalchemy import text
        return text(sql)

    def get(self, tenant_id: str, message_id: str) -> Optional[DeliveryRow]:
        eng = self._engine()
        if eng is None:
            return None
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                r = s.execute(self._text(
                    "SELECT message_id,campaign_id,template,phone_masked,lead_id,status,reason,"
                    "media_count FROM wa_delivery WHERE org_id=:org AND message_id=:mid"
                ), {"org": tenant_id, "mid": message_id}).fetchone()
                if not r:
                    return None
                return DeliveryRow(tenant_id=tenant_id, message_id=r[0], campaign_id=r[1] or "",
                                   template=r[2] or "", phone_masked=r[3] or "", lead_id=r[4] or "",
                                   status=DeliveryStatus.coerce(r[5]), reason=r[6] or "",
                                   media_count=int(r[7] or 0))
        except Exception as exc:  # noqa: BLE001
            log.info("wa_delivery get failed: %r", exc)
            return None

    def upsert(self, row: DeliveryRow) -> None:
        eng = self._engine()
        if eng is None:
            return
        try:
            with eng.session(tenant_id=row.tenant_id, is_admin=False) as s:
                s.execute(self._text(
                    "INSERT INTO wa_delivery (org_id,message_id,campaign_id,template,phone_masked,"
                    " lead_id,status,reason,media_count,updated_at) VALUES (:org,:mid,:cid,:tpl,:ph,"
                    " :lid,:st,:rs,:mc,now()) "
                    "ON CONFLICT (org_id,message_id) DO UPDATE SET campaign_id=:cid,template=:tpl,"
                    " phone_masked=:ph,lead_id=:lid,status=:st,reason=:rs,media_count=:mc,"
                    " updated_at=now()"
                ), {"org": row.tenant_id, "mid": row.message_id, "cid": row.campaign_id,
                    "tpl": row.template, "ph": row.phone_masked, "lid": row.lead_id,
                    "st": row.status.value, "rs": row.reason, "mc": row.media_count})
        except Exception as exc:  # noqa: BLE001
            log.info("wa_delivery upsert failed: %r", exc)

    def scan(self, tenant_id: str) -> list[DeliveryRow]:
        eng = self._engine()
        if eng is None:
            return []
        try:
            with eng.session(tenant_id=tenant_id, is_admin=False) as s:
                rows = s.execute(self._text(
                    "SELECT message_id,campaign_id,template,phone_masked,lead_id,status,reason,"
                    "media_count FROM wa_delivery WHERE org_id=:org ORDER BY updated_at DESC"
                ), {"org": tenant_id}).fetchall()
                return [DeliveryRow(tenant_id=tenant_id, message_id=r[0], campaign_id=r[1] or "",
                                    template=r[2] or "", phone_masked=r[3] or "", lead_id=r[4] or "",
                                    status=DeliveryStatus.coerce(r[5]), reason=r[6] or "",
                                    media_count=int(r[7] or 0)) for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.info("wa_delivery scan failed: %r", exc)
            return []


class DeliveryStore:
    """Tenant-scoped facade over a delivery backend. Status advances FORWARD only —
    a late/duplicate webhook (delivered after read) never regresses the funnel."""

    def __init__(self, backend=None) -> None:
        self.backend = backend or InMemoryDeliveryBackend()

    @staticmethod
    def _ok(tenant_id: str) -> bool:
        return bool((tenant_id or "").strip())

    def upsert(self, row: DeliveryRow) -> bool:
        """Insert or monotonically advance a delivery row. Returns True if stored.
        Forward-only: a status with a LOWER ordinal than the stored one is ignored
        (idempotent webhook re-delivery / out-of-order events)."""
        if not self._ok(row.tenant_id) or not (row.message_id or "").strip():
            log.warning("DeliveryStore.upsert dropped: missing tenant/message_id")
            return False
        cur = self.backend.get(row.tenant_id, row.message_id)
        if cur is not None and status_order(row.status) < status_order(cur.status):
            return False  # don't regress the funnel
        self.backend.upsert(row)
        return True

    def get(self, tenant_id: str, message_id: str) -> Optional[DeliveryRow]:
        if not self._ok(tenant_id):
            return None
        return self.backend.get(tenant_id, message_id)

    def list(self, tenant_id: str, *, campaign_id: str = "") -> list[DeliveryRow]:
        if not self._ok(tenant_id):
            return []
        rows = self.backend.scan(tenant_id)
        if campaign_id:
            rows = [r for r in rows if r.campaign_id == campaign_id]
        rows.sort(key=lambda r: r.updated_at, reverse=True)
        return rows

    def summary(self, tenant_id: str, *, campaign_id: str = "") -> dict:
        """The delivery KPI strip: sent/delivered/read/failed/opted_out counts +
        read_rate. `sent` = every row that left queued (sent or further)."""
        rows = self.list(tenant_id, campaign_id=campaign_id)
        out = {"total": len(rows), "queued": 0, "sent": 0, "delivered": 0, "read": 0,
               "failed": 0, "opted_out": 0, "skipped_no_config": 0, "read_rate": 0.0}
        for r in rows:
            out[r.status.value] = out.get(r.status.value, 0) + 1
        # 'sent' is the funnel floor: anything that actually went out (sent/delivered/read).
        went_out = out["sent"] + out["delivered"] + out["read"]
        out["sent_total"] = went_out
        out["read_rate"] = round(out["read"] / went_out, 4) if went_out else 0.0
        out["delivered_rate"] = round((out["delivered"] + out["read"]) / went_out, 4) if went_out else 0.0
        return out
