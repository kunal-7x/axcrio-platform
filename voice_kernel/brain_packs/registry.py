"""voice_kernel.brain_packs.registry — the VERSIONED, editable RenderBrain store.

The founder's standing rule: every backend capability ships with full CRUD +
versioning the operator can drive (draft -> test -> publish -> rollback) and a
clear record of WHICH CAMPAIGN USES WHICH VERSION. This module is that store as a
data model + an in-memory/JSON impl. (PG wiring lands later behind the same
interface — the provider depends only on `BrainPackStore`.)

Lifecycle of a pack version (per pack id, e.g. "sales"):
    DRAFT  -> (test) TESTED -> (publish) PUBLISHED -> (rollback) ARCHIVED
A pack id has at most ONE PUBLISHED version at a time; publishing a new version
archives the previously published one. Rollback re-publishes a prior version.

Campaign binding: a campaign may PIN a specific pack version (e.g. campaign C7
pins sales@3 while everyone else floats on the latest published). Unpinned
campaigns resolve to the current PUBLISHED version.

The store holds OVERRIDE packs (vendor/tenant edits). The provider falls back to
the shipped defaults (packs_data.py) when the store has no published override for
an id — so the kernel always resolves a pack, store or not.

Pure stdlib (json/dataclasses/enum). Imports ZERO droplet_work modules.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Optional


class VersionState(str, Enum):
    DRAFT = "draft"
    TESTED = "tested"
    PUBLISHED = "published"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class PackVersion:
    """One immutable version of an editable pack. `kind` is 'use_case' or
    'industry'. `body` is the editable, serialisable pack payload (a dict of the
    UseCasePack/IndustryPack fields) — kept as a plain dict so the store stays
    schema-agnostic and JSON-round-trippable. `id` is the pack family id (e.g.
    'sales'); `version` is the monotonically increasing integer."""

    id: str  # pack family id, e.g. "sales" / "real_estate"
    version: int
    kind: str  # "use_case" | "industry"
    body: dict
    state: VersionState = VersionState.DRAFT
    note: str = ""
    created_ts: float = field(default_factory=time.time)


class BrainPackStore:
    """In-memory versioned store. The JSON-backed subclass persists it.

    Thread-safety is intentionally NOT provided here (single-writer control-plane
    op; the live HOT path only READS the resolved published version, which the
    provider snapshots). Mutations raise on bad transitions (fail-loud)."""

    def __init__(self) -> None:
        # versions[(kind,id)] -> {version:int -> PackVersion}
        self._versions: dict[tuple[str, str], dict[int, PackVersion]] = {}
        # campaign pins: campaign_id -> {(kind,id) -> version}
        self._pins: dict[str, dict[tuple[str, str], int]] = {}

    # --------------------------------------------------------------- helpers #
    @staticmethod
    def _k(kind: str, pack_id: str) -> tuple[str, str]:
        return (kind, pack_id)

    def _family(self, kind: str, pack_id: str) -> dict[int, PackVersion]:
        return self._versions.setdefault(self._k(kind, pack_id), {})

    # ----------------------------------------------------------------- CRUD #
    def create_draft(self, kind: str, pack_id: str, body: dict, note: str = "") -> PackVersion:
        """Create a new DRAFT version (next integer) for a pack family."""
        if kind not in ("use_case", "industry"):
            raise ValueError(f"kind must be use_case|industry, got {kind!r}")
        if not (pack_id or "").strip():
            raise ValueError("pack_id is required")
        fam = self._family(kind, pack_id)
        ver = (max(fam) + 1) if fam else 1
        pv = PackVersion(id=pack_id, version=ver, kind=kind, body=dict(body or {}), state=VersionState.DRAFT, note=note)
        fam[ver] = pv
        return pv

    def update_draft(self, kind: str, pack_id: str, version: int, body: dict, note: str = "") -> PackVersion:
        """Edit a DRAFT in place (only DRAFTs are editable — published versions
        are immutable; create a new draft to change a published pack)."""
        pv = self.get(kind, pack_id, version)
        if pv.state != VersionState.DRAFT:
            raise ValueError(f"only DRAFT versions are editable; {pack_id}@{version} is {pv.state.value}")
        new = replace(pv, body=dict(body or {}), note=note or pv.note)
        self._family(kind, pack_id)[version] = new
        return new

    def get(self, kind: str, pack_id: str, version: int) -> PackVersion:
        fam = self._family(kind, pack_id)
        if version not in fam:
            raise KeyError(f"{kind}:{pack_id}@{version} not found")
        return fam[version]

    def list_versions(self, kind: str, pack_id: str) -> tuple[PackVersion, ...]:
        return tuple(self._family(kind, pack_id)[v] for v in sorted(self._family(kind, pack_id)))

    # ------------------------------------------------------- state machine #
    def mark_tested(self, kind: str, pack_id: str, version: int, note: str = "") -> PackVersion:
        pv = self.get(kind, pack_id, version)
        if pv.state not in (VersionState.DRAFT, VersionState.TESTED):
            raise ValueError(f"cannot mark_tested from {pv.state.value}")
        new = replace(pv, state=VersionState.TESTED, note=note or pv.note)
        self._family(kind, pack_id)[version] = new
        return new

    def publish(self, kind: str, pack_id: str, version: int, note: str = "") -> PackVersion:
        """Publish a version. Archives the currently-published one (at most one
        PUBLISHED per family). A version may be published from DRAFT or TESTED."""
        pv = self.get(kind, pack_id, version)
        if pv.state == VersionState.PUBLISHED:
            return pv
        fam = self._family(kind, pack_id)
        for v, other in list(fam.items()):
            if other.state == VersionState.PUBLISHED:
                fam[v] = replace(other, state=VersionState.ARCHIVED)
        new = replace(pv, state=VersionState.PUBLISHED, note=note or pv.note)
        fam[version] = new
        return new

    def published(self, kind: str, pack_id: str) -> Optional[PackVersion]:
        for pv in self._family(kind, pack_id).values():
            if pv.state == VersionState.PUBLISHED:
                return pv
        return None

    def rollback(self, kind: str, pack_id: str, to_version: int, note: str = "") -> PackVersion:
        """Re-publish a prior (archived/tested) version — the rollback. Archives
        whatever is currently published, then publishes `to_version`."""
        target = self.get(kind, pack_id, to_version)
        if target.state == VersionState.DRAFT:
            raise ValueError(f"cannot rollback to an unpublished DRAFT {pack_id}@{to_version}; test/publish it instead")
        return self.publish(kind, pack_id, to_version, note=note or f"rollback to v{to_version}")

    # ---------------------------------------------------- campaign binding #
    def pin_campaign(self, campaign_id: str, kind: str, pack_id: str, version: int) -> None:
        """Pin a campaign to a SPECIFIC pack version (must exist)."""
        self.get(kind, pack_id, version)  # validates existence
        self._pins.setdefault(campaign_id, {})[self._k(kind, pack_id)] = version

    def unpin_campaign(self, campaign_id: str, kind: str, pack_id: str) -> None:
        self._pins.get(campaign_id, {}).pop(self._k(kind, pack_id), None)

    def version_for_campaign(self, campaign_id: str, kind: str, pack_id: str) -> Optional[PackVersion]:
        """Resolve which version a campaign uses: its PIN if set, else the current
        PUBLISHED version, else None (provider falls back to the shipped default)."""
        pinned = self._pins.get(campaign_id or "", {}).get(self._k(kind, pack_id))
        if pinned is not None:
            return self.get(kind, pack_id, pinned)
        return self.published(kind, pack_id)

    def campaign_bindings(self, campaign_id: str) -> dict[str, int]:
        """Which-campaign-uses-which-version, for the control UI. Returns
        {'<kind>:<pack_id>': version} resolved (pin or published)."""
        out: dict[str, int] = {}
        seen: set[tuple[str, str]] = set(self._pins.get(campaign_id or "", {}).keys())
        for key in self._versions:
            seen.add(key)
        for kind, pack_id in seen:
            pv = self.version_for_campaign(campaign_id, kind, pack_id)
            if pv is not None:
                out[f"{kind}:{pack_id}"] = pv.version
        return out

    # ----------------------------------------------------- serialisation #
    def to_dict(self) -> dict:
        return {
            "versions": [asdict(pv) | {"state": pv.state.value} for fam in self._versions.values() for pv in fam.values()],
            "pins": {cid: {f"{k[0]}:{k[1]}": v for k, v in pins.items()} for cid, pins in self._pins.items()},
        }

    def load_dict(self, data: dict) -> None:
        self._versions.clear()
        self._pins.clear()
        for row in (data or {}).get("versions", []):
            pv = PackVersion(
                id=row["id"], version=int(row["version"]), kind=row["kind"],
                body=dict(row.get("body") or {}), state=VersionState(row.get("state", "draft")),
                note=row.get("note", ""), created_ts=float(row.get("created_ts", time.time())),
            )
            self._family(pv.kind, pv.id)[pv.version] = pv
        for cid, pins in (data or {}).get("pins", {}).items():
            for combo, ver in pins.items():
                kind, pack_id = combo.split(":", 1)
                self._pins.setdefault(cid, {})[self._k(kind, pack_id)] = int(ver)


class JsonBrainPackStore(BrainPackStore):
    """File-backed store — persists the in-memory state to a JSON file on every
    mutation. The interim persistence before PG; the provider doesn't care which
    BrainPackStore it gets."""

    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self._path = Path(path)
        if self._path.exists():
            try:
                self.load_dict(json.loads(self._path.read_text(encoding="utf-8")))
            except Exception:
                pass

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    # persist after each mutating op
    def create_draft(self, *a, **k):  # type: ignore[override]
        pv = super().create_draft(*a, **k); self._save(); return pv

    def update_draft(self, *a, **k):  # type: ignore[override]
        pv = super().update_draft(*a, **k); self._save(); return pv

    def mark_tested(self, *a, **k):  # type: ignore[override]
        pv = super().mark_tested(*a, **k); self._save(); return pv

    def publish(self, *a, **k):  # type: ignore[override]
        pv = super().publish(*a, **k); self._save(); return pv

    def rollback(self, *a, **k):  # type: ignore[override]
        pv = super().rollback(*a, **k); self._save(); return pv

    def pin_campaign(self, *a, **k):  # type: ignore[override]
        super().pin_campaign(*a, **k); self._save()

    def unpin_campaign(self, *a, **k):  # type: ignore[override]
        super().unpin_campaign(*a, **k); self._save()
