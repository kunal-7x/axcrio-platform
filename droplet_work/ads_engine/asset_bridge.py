"""ads_engine.asset_bridge — the W1-deferred ASSET BRIDGE between the ad engine and the gallery.

The `CreativeService` takes an `asset_bridge` with two methods (creative.py:208/727/742):
  * mirror_asset(tenant_id, payload) -> row   — push an approved ad variant INTO the gallery.
  * get_asset(tenant_id, asset_id)   -> dict|None — read a gallery asset (tenant-scoped) so the
                                                    ad engine can ADOPT it as a moderated variant.

In the live box the gallery is the in-tree `creative_engine` (importable Python: jobs + store, no
HTTP, no token). This bridge tries that in-process path FIRST; if creative_engine is not present
(e.g. this worktree, or the BYOK engine disabled) it DEGRADES to a tenant-scoped mirror inside the
ads store (`ad_gallery` collection) so the bridge is ALWAYS functional and OFFLINE-testable, never
a silent no-op. Either way it is best-effort + crash-proof: a bridge failure must NEVER block a
variant reaching `ready` or crash the mount.

EARNER-SAFE: in-process only, no `from caller import ...`, tenant_id is always passed by the
service (token-derived upstream) and every read/write is tenant-scoped (cross-tenant get -> None).
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Optional

from . import store

_log = logging.getLogger("ads_engine.asset_bridge")

# Tenant-scoped collection the fallback gallery mirror lives in (file/PG-agnostic via store).
_GALLERY_COLLECTION = "ad_gallery"


def _now() -> int:
    return int(time.time())


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{hashlib.sha1(str(time.time_ns()).encode()).hexdigest()[:10]}"


class AssetBridge:
    """In-process bridge to the creative gallery, degrade-safe to the ads store.

    Construct ONCE at mount and inject into CreativeService(asset_bridge=AssetBridge()). The
    optional `creative_engine` arg lets the mount pass the imported in-tree module explicitly;
    otherwise the bridge lazily attempts `import creative_engine` and falls back to the local
    mirror if absent.
    """

    def __init__(self, creative_engine: Any = None) -> None:
        self._ce = creative_engine
        self._ce_tried = creative_engine is not None

    # -- creative_engine discovery (lazy, crash-proof) ------------------------------------------
    def _engine(self):
        if self._ce is not None:
            return self._ce
        if self._ce_tried:
            return None
        self._ce_tried = True
        try:
            import importlib
            self._ce = importlib.import_module("creative_engine")
        except Exception:  # noqa: BLE001 — gallery service absent -> use the store mirror
            self._ce = None
        return self._ce

    # -- mirror_asset: approved ad variant -> gallery -------------------------------------------
    def mirror_asset(self, tenant_id: str, payload: dict) -> Optional[dict]:
        """Push an approved variant into the gallery. Returns the stored row (or None on miss).

        Tries the in-process creative_engine first; falls back to a tenant-scoped row in the ads
        store so the mirror is durable + listable even without the BYOK engine. Best-effort."""
        if not tenant_id or not isinstance(payload, dict):
            return None
        ce = self._engine()
        if ce is not None:
            try:
                fn = getattr(getattr(ce, "store", None), "mirror_external_asset", None) \
                    or getattr(ce, "mirror_asset", None)
                if fn is not None:
                    row = fn(tenant_id, payload)
                    if row is not None:
                        return row
            except Exception:  # noqa: BLE001 — engine error -> fall through to the store mirror
                _log.warning("asset_bridge.mirror_asset engine path failed: %r",
                             type(__import__("sys").exc_info()[1]).__name__)
        return self._mirror_to_store(tenant_id, payload)

    def _mirror_to_store(self, tenant_id: str, payload: dict) -> Optional[dict]:
        try:
            asset_id = str(payload.get("variant_id") or _gen_id("ga"))
            row = {
                "asset_id": asset_id,
                "tenant_id": tenant_id,
                "source": payload.get("source", "generated"),
                "channel": payload.get("platform", "meta_ads"),
                "kind": payload.get("kind", ""),
                "campaign_id": payload.get("campaign_id", ""),
                "plan_id": payload.get("campaign_id", ""),
                "headline": payload.get("headline", ""),
                "moderation_status": payload.get("moderation_status", ""),
                "outputs": payload.get("outputs", []),
                "variant_id": payload.get("variant_id", ""),
                "created_at": _now(),
            }
            store.put_row(tenant_id, _GALLERY_COLLECTION, asset_id, row)
            return row
        except Exception:  # noqa: BLE001 — mirror is best-effort, never blocks ready
            return None

    # -- get_asset: gallery asset -> ad engine (tenant-scoped) ----------------------------------
    def get_asset(self, tenant_id: str, asset_id: str) -> Optional[dict]:
        """Read a gallery asset for this tenant (cross-tenant -> None). Tries creative_engine then
        the store mirror. Returns a normalized {url, headline, ...} dict the ad engine can adopt."""
        if not tenant_id or not asset_id:
            return None
        ce = self._engine()
        if ce is not None:
            try:
                fn = getattr(getattr(ce, "store", None), "get_asset", None) \
                    or getattr(ce, "get_asset", None)
                if fn is not None:
                    row = fn(tenant_id, asset_id)
                    if row is not None:
                        return _normalize_asset(row)
            except Exception:  # noqa: BLE001
                pass
        try:
            row = store.get_row(tenant_id, _GALLERY_COLLECTION, asset_id)
        except Exception:  # noqa: BLE001
            row = None
        return _normalize_asset(row) if row else None

    def list_assets(self, tenant_id: str, *, channel: str = "meta_ads",
                    limit: int = 100) -> list:
        """Tenant-scoped gallery list (store mirror), newest-first, optionally channel-filtered.
        Used by the Creative-page 'Library' curate view (read-only)."""
        try:
            rows = list(store.get_collection(tenant_id, _GALLERY_COLLECTION).values())
        except Exception:  # noqa: BLE001
            return []
        if channel:
            rows = [r for r in rows if (r.get("channel") or "meta_ads") == channel]
        rows.sort(key=lambda r: int(r.get("created_at") or 0), reverse=True)
        return rows[: max(1, int(limit))]


def _normalize_asset(row: Any) -> Optional[dict]:
    """Coerce a gallery row (engine or store shape) to the {url, headline, ...} the ad engine reads."""
    if not isinstance(row, dict):
        return None
    url = (row.get("url") or row.get("output_url") or "")
    if not url:
        outs = row.get("outputs") or []
        if isinstance(outs, list) and outs and isinstance(outs[0], dict):
            url = outs[0].get("url", "")
    return {
        "asset_id": row.get("asset_id") or row.get("id") or "",
        "url": url,
        "output_url": url,
        "headline": row.get("headline", ""),
        "kind": row.get("kind", ""),
        "channel": row.get("channel", "meta_ads"),
        "moderation_status": row.get("moderation_status", ""),
    }


__all__ = ["AssetBridge"]
