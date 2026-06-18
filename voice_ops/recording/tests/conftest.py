"""Test config for voice_ops.recording: make the repo root importable so
`import voice_ops...` and `import voice_kernel...` work when pytest runs from
anywhere. Plus shared fakes for LiveKit egress, S3 storage, and the W8 bus."""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[3]  # voice_ops/recording/tests/ -> repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# --------------------------------------------------------------------------- #
# Fake LiveKit egress (mirrors livekit.api EgressInfo attrs the wrapper reads)
# --------------------------------------------------------------------------- #
@dataclass
class FakeFileResult:
    duration: int = 0        # NANOSECONDS (as LiveKit reports)
    size: int = 0
    filename: str = ""


@dataclass
class FakeEgressInfo:
    egress_id: str = ""
    room_name: str = ""
    status: int = 0          # 0 STARTING .. 3 COMPLETE .. 4 FAILED
    file_results: list = field(default_factory=list)


@dataclass
class _FakeResp:
    items: list = field(default_factory=list)


class FakeEgressApi:
    def __init__(self, scripted: List[List[FakeEgressInfo]]):
        # scripted[i] = the items list returned on the i-th list_egress call.
        self._scripted = scripted
        self._i = 0
        self.calls = 0

    async def list_egress(self, req):  # req is a plain dict in fake mode
        self.calls += 1
        idx = min(self._i, len(self._scripted) - 1) if self._scripted else 0
        items = self._scripted[idx] if self._scripted else []
        self._i += 1
        return _FakeResp(items=list(items))


class FakeLiveKitClient:
    """Has an `.egress` with `list_egress` — what EgressClient(client=...) expects."""

    def __init__(self, scripted: List[List[FakeEgressInfo]]):
        self.egress = FakeEgressApi(scripted)


# --------------------------------------------------------------------------- #
# Fake object storage (conforms to ObjectStorage's public surface)
# --------------------------------------------------------------------------- #
class FakeStorage:
    def __init__(self, *, objects: Optional[dict] = None, archive_ok: bool = True):
        # objects: key -> size (bytes). Presence == exists.
        self.objects = dict(objects or {})
        self.archived: list = []
        self.deleted: list = []
        self.archive_ok = archive_ok

    def head(self, key: str, *, tier: str = "primary") -> dict:
        if key in self.objects:
            return {"exists": True, "size": self.objects[key], "content_type": "audio/ogg"}
        return {"exists": False, "size": 0, "content_type": ""}

    def playable(self, key: str, *, tier: str = "primary", min_bytes: int = 2048) -> bool:
        h = self.head(key, tier=tier)
        return bool(h["exists"] and h["size"] >= min_bytes)

    def presign_get(self, key: str, *, tier: str = "primary", expires_s: int = 3600) -> str:
        return f"https://fake.r2/{key}?sig=abc" if key in self.objects else ""

    def delete(self, key: str, *, tier: str = "primary") -> bool:
        if key in self.objects:
            self.deleted.append(key)
            del self.objects[key]
            return True
        return False

    def copy_to_archive(self, key: str, *, archive_key: Optional[str] = None) -> bool:
        if self.archive_ok and key in self.objects:
            self.archived.append(key)
            return True
        return False

    def usage(self, *, tier: str = "primary", prefix: str = "") -> dict:
        objs = [(k, v) for k, v in self.objects.items() if k.startswith(prefix or "")]
        return {"objects": len(objs), "bytes": sum(v for _k, v in objs)}
