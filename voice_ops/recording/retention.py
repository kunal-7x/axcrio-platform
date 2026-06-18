"""voice_ops.recording.retention — TTL cleanup + storage accounting + deletion audit.

Recordings are the heaviest, most-regulated artifact. This module enforces the
lifecycle the founder needs without ever destroying business intelligence:

  RAW AUDIO is ephemeral. After `retention_days` (default 30) the hot-tier (R2)
  object is ARCHIVED to the cold tier (B2, ~2.5x cheaper) and then deleted from
  R2 — OR deleted outright if archiving is off / unavailable.

  THE SUMMARY + LEAD INTELLIGENCE ARE FOREVER. Retention NEVER touches the
  transcript summary, lifecycle, conversion signals, or any lead-memory row — only
  the raw media object. A `deletion_audit` record is produced for EVERY raw delete
  (immutable, append-only, tenant-scoped) so "who deleted what, when, and was the
  intel preserved" is always answerable. This mirrors the platform's immutable
  audit posture (the erasure-audit pattern in voice_kernel.memory.erasure).

It operates on a list of RetentionCandidate rows (the caller / a cron supplies
them from the recordings table — this module owns NO database). Each candidate
declares whether its summary/lead intel is preserved; retention REFUSES to delete
raw media for a candidate that has not preserved its intel UNLESS `force=True`
(fail-safe default: never lose the only copy of the business signal).

NEVER raises; a storage hiccup on one object is logged and the sweep continues.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, List, Optional

from .config import RecordingConfig

log = logging.getLogger("voice_ops.recording.retention")


@dataclass(frozen=True)
class RetentionCandidate:
    """One recording the caller is considering for retention action."""

    call_id: str
    tenant_id: str
    key: str                       # the raw-media object key (hot tier)
    created_iso: str               # when the recording was created (UTC ISO)
    summary_preserved: bool = True  # is the durable summary/lead intel saved?
    direction: str = "outbound"


@dataclass(frozen=True)
class DeletionAuditRecord:
    """Immutable audit line for one raw-media deletion. Append-only; tenant-scoped.
    NOTE: `intel_preserved` records that the business signal survived the delete."""

    call_id: str
    tenant_id: str
    key: str
    action: str                    # "archived_then_deleted" | "deleted" | "skipped_no_intel" | "skipped_not_expired"
    archived: bool
    deleted: bool
    intel_preserved: bool
    ts_iso: str
    reason: str = ""


@dataclass
class RetentionReport:
    examined: int = 0
    archived: int = 0
    deleted: int = 0
    skipped: int = 0
    bytes_reclaimed: int = 0
    audit: List[DeletionAuditRecord] = field(default_factory=list)


class RetentionManager:
    """TTL cleanup + accounting + audit. Construct with the config + an
    ObjectStorage. `archive_first` (default True) copies R2 -> B2 before deleting
    the hot copy. `emit_audit` (optional W8 bus) fires nothing by default — the
    audit lives in the returned RetentionReport; a seam may persist/emit it."""

    def __init__(
        self,
        cfg: Optional[RecordingConfig] = None,
        *,
        storage: Any = None,
        archive_first: bool = True,
    ):
        self.cfg = cfg or RecordingConfig.from_env()
        self.storage = storage
        self.archive_first = archive_first

    # ------------------------------------------------------ expiry test #
    def is_expired(self, created_iso: str, *, now_iso: Optional[str] = None) -> bool:
        """True when `created_iso` is older than retention_days. Uses the canonical
        UTC parser (voice_kernel.events.timeutil) so a naive/Z-suffixed timestamp is
        handled the same everywhere — no off-by-one. NEVER raises (a bad timestamp
        is treated as NOT expired: fail-safe, never delete on a parse error)."""
        try:
            from voice_kernel.events.timeutil import parse_iso, now_utc

            created = parse_iso(created_iso)
            now = parse_iso(now_iso) if now_iso else now_utc()
            return (now - created) > timedelta(days=int(self.cfg.retention_days))
        except Exception as exc:  # noqa: BLE001
            log.info("is_expired parse failed (-> not expired) %s: %r", created_iso, exc)
            return False

    # ----------------------------------------------------------- sweep #
    def sweep(
        self,
        candidates: List[RetentionCandidate],
        *,
        now_iso: Optional[str] = None,
        force: bool = False,
    ) -> RetentionReport:
        """Process candidates: expired raw media is archived (if enabled) then
        deleted; the summary/lead intel is NEVER touched. Returns a RetentionReport
        with an audit line per delete. `force=True` overrides the intel-preserved
        guard (admin purge). NEVER raises."""
        from voice_kernel.events.timeutil import now_utc_iso

        report = RetentionReport()
        ts = now_iso or now_utc_iso()
        for cand in candidates or []:
            report.examined += 1
            try:
                self._process_one(cand, report, ts, force)
            except Exception as exc:  # noqa: BLE001
                log.warning("retention process failed call=%s: %r", cand.call_id, exc)
                report.skipped += 1
        return report

    def _process_one(self, cand: RetentionCandidate, report: RetentionReport, ts: str, force: bool) -> None:
        if not self.is_expired(cand.created_iso, now_iso=ts):
            report.skipped += 1
            report.audit.append(self._audit(cand, "skipped_not_expired", False, False, ts, "within retention window"))
            return

        # FAIL-SAFE: never delete the only copy of the business signal.
        if not cand.summary_preserved and not force:
            report.skipped += 1
            report.audit.append(
                self._audit(cand, "skipped_no_intel", False, False, ts, "summary/lead intel NOT preserved — refusing raw delete")
            )
            return

        size = 0
        if self.storage is not None and cand.key:
            try:
                size = int(self.storage.head(cand.key).get("size", 0) or 0)
            except Exception:  # noqa: BLE001
                size = 0

        archived = False
        if self.archive_first and self.storage is not None and self.cfg.archive.complete:
            try:
                archived = bool(self.storage.copy_to_archive(cand.key))
            except Exception as exc:  # noqa: BLE001
                log.info("archive copy failed call=%s: %r", cand.call_id, exc)
                archived = False

        deleted = False
        if self.storage is not None and cand.key:
            try:
                deleted = bool(self.storage.delete(cand.key))
            except Exception as exc:  # noqa: BLE001
                log.info("delete failed call=%s: %r", cand.call_id, exc)
                deleted = False

        if archived:
            report.archived += 1
        if deleted:
            report.deleted += 1
            report.bytes_reclaimed += size
        action = "archived_then_deleted" if (archived and deleted) else ("deleted" if deleted else "skipped")
        if action == "skipped":
            report.skipped += 1
        report.audit.append(
            self._audit(cand, action, archived, deleted, ts, "raw media expired; summary preserved")
        )

    def _audit(self, cand: RetentionCandidate, action: str, archived: bool, deleted: bool, ts: str, reason: str) -> DeletionAuditRecord:
        # intel_preserved reflects reality: True when the summary is preserved (the
        # invariant the whole module protects).
        return DeletionAuditRecord(
            call_id=cand.call_id,
            tenant_id=cand.tenant_id,
            key=cand.key,
            action=action,
            archived=archived,
            deleted=deleted,
            intel_preserved=bool(cand.summary_preserved),
            ts_iso=ts,
            reason=reason,
        )

    # ------------------------------------------------------- accounting #
    def storage_usage(self, tenant_id: str, *, tier: str = "primary") -> dict:
        """Tenant-scoped storage usage figure {"objects","bytes","tenant_id","tier"}.
        Lists under the per-tenant key prefix (recordings/<tenant>/) so the number
        is hard-isolated per tenant. Benign zeros without storage. NEVER raises."""
        out = {"tenant_id": tenant_id, "tier": tier, "objects": 0, "bytes": 0}
        if self.storage is None or not (tenant_id or "").strip():
            return out
        prefix = f"{self.cfg.key_prefix}/{tenant_id.replace('/', '_')}/"
        try:
            u = self.storage.usage(tier=tier, prefix=prefix)
            out["objects"] = int(u.get("objects", 0) or 0)
            out["bytes"] = int(u.get("bytes", 0) or 0)
        except Exception as exc:  # noqa: BLE001
            log.info("storage_usage failed tenant=%s: %r", tenant_id, exc)
        return out
