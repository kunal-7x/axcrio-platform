"""voice_ops.recording.storage — S3-compatible object storage adapter.

Two tiers (RESEARCH-DECISIONS §3): Cloudflare R2 = the HOT tier (0-30 days, $0
egress, same CDN edge as the panel) for live playback; Backblaze B2 = the COLD
archive tier (30+ days, ~2.5x cheaper storage, free egress via the Bandwidth
Alliance) for long-term retention. Both are plain S3 v4 endpoints, so ONE adapter
serves both — only the StorageTier creds differ.

What it does (all NEVER-raise, degrade-to-benign — a storage hiccup must never
break a call or a finalize sweep):
  - head(tier, key)              -> {"exists", "size", "content_type"}  (playable gate)
  - playable(tier, key, floor)   -> bool  (exists AND size >= floor)
  - presign_get(tier, key, ttl)  -> short-lived GET url ("" if unavailable)
  - copy_to_archive(key)         -> bool  (R2 -> B2 server-side-ish copy for retention)
  - delete(tier, key)            -> bool  (retention cleanup)
  - usage(tier, prefix)          -> {"objects", "bytes"}  (storage accounting)

IMPORT ISOLATION: boto3 is imported LAZILY inside each method. Importing this
module pulls ZERO heavy deps; a host without boto3 simply gets benign falsy
results (the read side then shows "preparing" instead of a broken link). This is
the exact posture of ai_manager.recorder.presign/head_object — reused, not
reinvented, and generalized to two tiers.
"""
from __future__ import annotations

import io
import logging
from typing import Optional

from .config import RecordingConfig, StorageTier

log = logging.getLogger("voice_ops.recording.storage")


class ObjectStorage:
    """Tiered S3-compatible storage facade. Construct with a RecordingConfig; the
    primary tier is R2, the archive tier is B2. Holds NO live client at import —
    a boto3 client is created lazily per call (cheap; mirrors the recorder)."""

    def __init__(self, cfg: Optional[RecordingConfig] = None):
        self.cfg = cfg or RecordingConfig.from_env()

    # ------------------------------------------------------------- tiers #
    def tier(self, name: str) -> StorageTier:
        """Resolve a tier by name ('primary'/'r2' -> R2, 'archive'/'b2' -> B2)."""
        n = (name or "primary").lower()
        if n in ("archive", "b2", "cold"):
            return self.cfg.archive
        return self.cfg.primary

    # ------------------------------------------------------------ client #
    def _client(self, tier: StorageTier):
        """Lazy boto3 S3 client for one tier. Returns None if boto3 is absent or
        the tier is not fully configured (NEVER raises)."""
        if not tier or not tier.complete:
            return None
        try:
            import boto3
            from botocore.config import Config as _BotoCfg

            style = "path" if tier.force_path_style else "virtual"
            return boto3.client(
                "s3",
                region_name=tier.region or "auto",
                endpoint_url=tier.endpoint,
                aws_access_key_id=tier.access_key,
                aws_secret_access_key=tier.secret_key,
                config=_BotoCfg(signature_version="s3v4", s3={"addressing_style": style}),
            )
        except Exception as exc:  # noqa: BLE001
            log.info("storage client unavailable (tier=%s): %r", tier.name, exc)
            return None

    # -------------------------------------------------------------- head #
    def head(self, key: str, *, tier: str = "primary") -> dict:
        """HEAD an object; {"exists","size","content_type"}. NEVER raises — any
        miss/404/absent-boto3 returns {exists:False}. Mirrors recorder.head_object
        so the playable gate is identical to the proven inbound read path."""
        out = {"exists": False, "size": 0, "content_type": ""}
        t = self.tier(tier)
        c = self._client(t)
        if c is None or not (key or "").strip():
            return out
        try:
            h = c.head_object(Bucket=t.bucket, Key=key)
            out["exists"] = True
            out["size"] = int(h.get("ContentLength", 0) or 0)
            out["content_type"] = str(h.get("ContentType", "") or "")
        except Exception as exc:  # noqa: BLE001
            log.info("storage head miss key=%s tier=%s: %r", key, t.name, exc)
        return out

    def playable(self, key: str, *, tier: str = "primary", min_bytes: Optional[int] = None) -> bool:
        """True only when the object EXISTS and is non-trivially sized (>= floor).
        The whole point of the HEAD gate (PERF UNIT-2 in the inbound path): a
        near-empty / 486-busy file has a duration field but no decodable bytes —
        the player would run a timer and play nothing. We refuse to call that
        playable."""
        floor = self.cfg.min_playable_bytes if min_bytes is None else int(min_bytes)
        h = self.head(key, tier=tier)
        return bool(h["exists"] and h["size"] >= floor)

    # ----------------------------------------------------------- presign #
    def presign_get(self, key: str, *, tier: str = "primary", expires_s: int = 3600) -> str:
        """Short-lived GET url so the panel plays without a public bucket. "" if
        unavailable (boto3 absent / creds missing) — the panel then shows
        'preparing' rather than a broken player. NEVER raises."""
        t = self.tier(tier)
        c = self._client(t)
        if c is None or not (key or "").strip():
            return ""
        try:
            return c.generate_presigned_url(
                "get_object", Params={"Bucket": t.bucket, "Key": key}, ExpiresIn=int(expires_s)
            )
        except Exception as exc:  # noqa: BLE001
            log.info("storage presign unavailable key=%s tier=%s: %r", key, t.name, exc)
            return ""

    # ------------------------------------------------------------ delete #
    def delete(self, key: str, *, tier: str = "primary") -> bool:
        """Delete one object (retention cleanup). Returns True on a clean delete,
        False on any error/absence. NEVER raises."""
        t = self.tier(tier)
        c = self._client(t)
        if c is None or not (key or "").strip():
            return False
        try:
            c.delete_object(Bucket=t.bucket, Key=key)
            return True
        except Exception as exc:  # noqa: BLE001
            log.info("storage delete failed key=%s tier=%s: %r", key, t.name, exc)
            return False

    # ----------------------------------------------- archive (R2 -> B2) #
    def copy_to_archive(self, key: str, *, archive_key: Optional[str] = None) -> bool:
        """Stream an object from the PRIMARY (R2) tier to the ARCHIVE (B2) tier
        under the SAME key (or `archive_key`). Used by the retention sweep to move
        cold recordings to the cheaper tier before deleting the hot copy. Returns
        True on success, False if either tier is unconfigured or any error occurs.
        NEVER raises. (A small download->upload because R2 and B2 are different
        accounts; for a voice OGG this is a few hundred KB.)"""
        src = self.cfg.primary
        dst = self.cfg.archive
        sc, dc = self._client(src), self._client(dst)
        if sc is None or dc is None or not (key or "").strip():
            return False
        dst_key = archive_key or key
        try:
            obj = sc.get_object(Bucket=src.bucket, Key=key)
            body = obj["Body"].read()
            ctype = str(obj.get("ContentType", "application/octet-stream") or "application/octet-stream")
            dc.upload_fileobj(
                io.BytesIO(body), dst.bucket, dst_key,
                ExtraArgs={"ContentType": ctype},
            )
            return True
        except Exception as exc:  # noqa: BLE001
            log.info("storage archive copy failed key=%s: %r", key, exc)
            return False

    # ------------------------------------------------------------- usage #
    def usage(self, *, tier: str = "primary", prefix: str = "") -> dict:
        """Sum object count + bytes under `prefix` on a tier (storage accounting).
        Paginates ListObjectsV2. {"objects","bytes"}; benign zeros on any error.
        NEVER raises. Pass a per-tenant prefix (recordings/<tenant>/) for a
        tenant-scoped usage figure."""
        out = {"objects": 0, "bytes": 0}
        t = self.tier(tier)
        c = self._client(t)
        if c is None:
            return out
        try:
            token = None
            while True:
                kw = {"Bucket": t.bucket, "Prefix": prefix or ""}
                if token:
                    kw["ContinuationToken"] = token
                resp = c.list_objects_v2(**kw)
                for o in resp.get("Contents", []) or []:
                    out["objects"] += 1
                    out["bytes"] += int(o.get("Size", 0) or 0)
                if not resp.get("IsTruncated"):
                    break
                token = resp.get("NextContinuationToken")
                if not token:
                    break
        except Exception as exc:  # noqa: BLE001
            log.info("storage usage failed tier=%s prefix=%s: %r", t.name, prefix, exc)
        return out
