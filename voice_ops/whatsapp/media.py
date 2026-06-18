"""voice_ops.whatsapp.media — the WhatsApp Media Library (W16).

Upload / store / preview / reuse / replace / organize the founder's four media
kinds: banner, image, video, and PDF brochure. The brochure is FIRST-CLASS
(kind='brochure') — PDFs are critical in real estate, so a brochure is its own
asset and its own builder step, never lumped under 'image'.

Bytes live on the W9 ObjectStorage tier under `wa_media/<tenant>/<id>.<ext>` —
reused, not reinvented (presign for preview, head for the playable gate, delete on
remove, usage for the per-tenant storage figure). Metadata lives in the FORCE-RLS
`wa_media` table via MediaStore. A `MediaLibrary` wires the two.

Validation is per-kind (MIME prefix + size ceiling) and NEVER raises on a bad
upload — it returns a structured rejection so the panel shows a friendly error.
Importing this module pulls ZERO boto3 (storage is lazy inside ObjectStorage).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from .model import MediaAsset, MediaKind, ext_for, kind_rules
from .store import MediaStore

log = logging.getLogger("voice_ops.whatsapp.media")

_PDF_MAGIC = b"%PDF-"


def _mask_phone(p: str) -> str:
    s = re.sub(r"\D", "", p or "")
    return ("•" * max(0, len(s) - 4) + s[-4:]) if s else ""


@dataclass
class UploadResult:
    ok: bool
    asset: Optional[MediaAsset] = None
    error: str = ""
    preview_url: str = ""


class MediaLibrary:
    """Tenant-scoped media library. Construct with a MediaStore + (optionally) a W9
    ObjectStorage; both default to safe in-memory/lazy seams so this is importable
    and testable without Postgres or boto3."""

    # object-key prefix per tenant (mirrors recordings/<tenant>/ in W9).
    PREFIX = "wa_media"

    def __init__(self, store: Optional[MediaStore] = None, storage=None,
                 *, storage_tier: str = "primary") -> None:
        self.store = store or MediaStore()
        self._storage = storage             # voice_ops.recording.storage.ObjectStorage (lazy)
        self.tier = storage_tier

    # --------------------------------------------------------------- storage -- #
    def _get_storage(self):
        """Lazily build a W9 ObjectStorage if one was not injected. Returns None if
        unavailable (no boto3 / no creds) — uploads then store metadata only and the
        preview falls back to 'preparing' (never crashes)."""
        if self._storage is not None:
            return self._storage
        try:
            from voice_ops.recording.storage import ObjectStorage
            self._storage = ObjectStorage()
        except Exception as exc:  # noqa: BLE001
            log.info("ObjectStorage unavailable (metadata-only mode): %r", exc)
            self._storage = None
        return self._storage

    def _object_key(self, tenant_id: str, asset_id: str, content_type: str) -> str:
        return f"{self.PREFIX}/{tenant_id}/{asset_id}.{ext_for(content_type)}"

    # ---------------------------------------------------------------- validate -- #
    @staticmethod
    def validate(kind: MediaKind, content_type: str, data: bytes) -> str:
        """Return "" if valid, else a human error string. Per-kind MIME + size gate;
        a brochure additionally must carry the PDF magic bytes (defense in depth —
        a renamed .exe with content-type application/pdf is rejected)."""
        prefixes, max_bytes = kind_rules(kind)
        ct = (content_type or "").split(";")[0].strip().lower()
        # a rule prefix ending in "/" ("image/") matches any subtype; an exact MIME
        # ("application/pdf") matches that type only.
        if not any(ct.startswith(p) if p.endswith("/") else ct == p for p in prefixes):
            return f"{kind.value} must be one of {', '.join(prefixes)} (got '{ct or 'unknown'}')"
        if not data:
            return "empty file"
        if len(data) > max_bytes:
            return f"file too large ({len(data)//(1024*1024)}MB > {max_bytes//(1024*1024)}MB limit)"
        if kind == MediaKind.BROCHURE and not data[:5] == _PDF_MAGIC:
            return "brochure must be a valid PDF (bad magic bytes)"
        return ""

    # ------------------------------------------------------------------ upload -- #
    def upload(self, tenant_id: str, *, kind: str | MediaKind, filename: str, content_type: str,
               data: bytes, title: str = "", created_by: str = "", tags: Optional[list] = None,
               width: int = 0, height: int = 0, duration_s: int = 0, page_count: int = 0,
               replace_id: str = "") -> UploadResult:
        """Validate -> store bytes on W9 -> persist FORCE-RLS metadata. `replace_id`
        reuses an existing asset id (in-place replace, keeps references). NEVER raises
        — a failure returns ok=False with a friendly `error`. Fail-closed on empty
        tenant."""
        if not (tenant_id or "").strip():
            return UploadResult(ok=False, error="missing tenant")
        k = MediaKind.coerce(kind) if not isinstance(kind, MediaKind) else kind
        err = self.validate(k, content_type, data)
        if err:
            return UploadResult(ok=False, error=err)

        asset_id = (replace_id or "").strip() or MediaAsset.new_id()
        key = self._object_key(tenant_id, asset_id, content_type)

        # store bytes (best-effort; metadata persists regardless so the row exists).
        stored = self._put_bytes(key, content_type, data)
        if not stored:
            log.info("wa media bytes not stored (dormant storage) tenant=%s id=%s", tenant_id, asset_id)

        asset = MediaAsset(
            tenant_id=tenant_id, id=asset_id, kind=k,
            title=title or filename or k.value, storage_key=key, content_type=content_type,
            size_bytes=len(data), width=width, height=height, duration_s=duration_s,
            page_count=page_count, source="uploaded", tags=list(tags or []),
            created_by=created_by,
        )
        if not self.store.upsert(asset):
            return UploadResult(ok=False, error="could not persist media metadata")
        return UploadResult(ok=True, asset=asset, preview_url=self.preview_url(asset))

    def _put_bytes(self, key: str, content_type: str, data: bytes) -> bool:
        st = self._get_storage()
        if st is None:
            return False
        try:
            client = st._client(st.tier(self.tier))   # reuse W9's lazy client
            if client is None:
                return False
            tier = st.tier(self.tier)
            client.put_object(Bucket=tier.bucket, Key=key, Body=data, ContentType=content_type)
            return True
        except Exception as exc:  # noqa: BLE001
            log.info("wa media put_object failed key=%s: %r", key, exc)
            return False

    # ------------------------------------------------------------------- read -- #
    def get(self, tenant_id: str, asset_id: str) -> Optional[MediaAsset]:
        return self.store.get(tenant_id, asset_id)

    def list(self, tenant_id: str, *, kind: Optional[str] = None) -> list[MediaAsset]:
        """List a tenant's media, optionally filtered to one kind (banner/image/
        video/brochure) — the gallery + the per-step picker both call this."""
        return self.store.list(tenant_id, kind=kind)

    def preview_url(self, asset: MediaAsset, *, expires_s: int = 3600) -> str:
        """Short-lived presigned GET url for the panel preview (phone-mock thumb /
        brochure viewer). "" when storage is dormant -> panel shows 'preparing'."""
        if not asset or not (asset.storage_key or "").strip():
            return ""
        st = self._get_storage()
        if st is None:
            return ""
        return st.presign_get(asset.storage_key, tier=self.tier, expires_s=expires_s)

    def preview_url_for(self, tenant_id: str, asset_id: str, *, expires_s: int = 3600) -> str:
        a = self.get(tenant_id, asset_id)
        return self.preview_url(a, expires_s=expires_s) if a else ""

    # -------------------------------------------------------------- mutate -- #
    def rename(self, tenant_id: str, asset_id: str, title: str) -> bool:
        a = self.get(tenant_id, asset_id)
        if not a:
            return False
        a.title = title
        return self.store.upsert(a)

    def retag(self, tenant_id: str, asset_id: str, tags: list) -> bool:
        a = self.get(tenant_id, asset_id)
        if not a:
            return False
        a.tags = list(tags or [])
        return self.store.upsert(a)

    def mark_used(self, tenant_id: str, asset_ids) -> None:
        """Bump used_count for assets attached to a sent campaign ('used in N')."""
        for aid in asset_ids or []:
            a = self.get(tenant_id, aid)
            if a:
                a.used_count += 1
                self.store.upsert(a)

    def archive(self, tenant_id: str, asset_id: str) -> bool:
        a = self.get(tenant_id, asset_id)
        if not a:
            return False
        a.status = "archived"
        return self.store.upsert(a)

    def delete(self, tenant_id: str, asset_id: str) -> bool:
        """Remove an asset: delete the bytes from W9 (best-effort) then the row."""
        a = self.get(tenant_id, asset_id)
        if a and a.storage_key:
            st = self._get_storage()
            if st is not None:
                try:
                    st.delete(a.storage_key, tier=self.tier)
                except Exception as exc:  # noqa: BLE001
                    log.info("wa media byte delete failed: %r", exc)
        return self.store.delete(tenant_id, asset_id)

    # --------------------------------------------------------------- usage -- #
    def usage(self, tenant_id: str) -> dict:
        """Per-tenant storage accounting ({objects, bytes}) over the W9 tier prefix.
        Benign zeros when storage is dormant."""
        st = self._get_storage()
        if st is None:
            # fall back to summing metadata rows.
            rows = self.list(tenant_id)
            return {"objects": len(rows), "bytes": sum(a.size_bytes for a in rows)}
        return st.usage(tier=self.tier, prefix=f"{self.PREFIX}/{tenant_id}/")
