"""
Self-hosted HTTP request telemetry for the super-admin Performance page.

The backend records ONE row per HTTP request (service / method / route / status / duration) into the
default-db ClickHouse table `haptica_http_requests`; obs_query reads it for the Performance dashboard
(RED metrics, top routes, status codes, error ops, request "traces"). This REPLACES the SigNoz APM
source (signoz_traces.*) which isn't deployed — same dashboard, self-hosted on the box's ClickHouse.

LAWS (house style): FLAG-GATED (HTTP_METRICS_ENABLED, default OFF) + DORMANT-SAFE + BEST-EFFORT.
Recording is a cheap in-memory append on the request hot path; the single network write is a BATCHED
INSERT on a background asyncio task every few seconds. A missing/broken ClickHouse NEVER affects a
request — record() and the flush loop swallow everything and never raise into the app.

Auth: CLICKHOUSE_WRITE_URL (falls back to CLICKHOUSE_URL). When the URL carries userinfo
(http://user:pass@host) httpx sends the basic-auth header; otherwise CLICKHOUSE_USER/PASSWORD params
are added (NEVER both — ClickHouse rejects that with Code 516). The table auto-creates on first flush.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

logger = logging.getLogger("http_metrics")

TABLE = "haptica_http_requests"
SERVICE = os.getenv("HTTP_METRICS_SERVICE", "backend")
_MAX_BUFFER = 20000

_buf: list = []
_started = False
_ensured = False

_DDL = (
    f"CREATE TABLE IF NOT EXISTS {TABLE} ("
    "ts DateTime64(3), service LowCardinality(String), method LowCardinality(String), "
    "route String, status_code UInt16, duration_ms Float32, has_error UInt8, "
    "tenant_id LowCardinality(String), trace_id String"
    ") ENGINE = MergeTree PARTITION BY toYYYYMMDD(ts) ORDER BY (service, ts) "
    "TTL toDateTime(ts) + INTERVAL 30 DAY SETTINGS index_granularity = 8192"
)


def _truthy(v: str) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def _enabled() -> bool:
    return _truthy(os.getenv("HTTP_METRICS_ENABLED", "0"))


def _ch_url() -> str:
    return (os.getenv("CLICKHOUSE_WRITE_URL") or os.getenv("CLICKHOUSE_URL") or "").strip().rstrip("/")


def _active() -> bool:
    return _enabled() and bool(_ch_url())


def _ch_ts(epoch: float) -> str:
    """ClickHouse DateTime64(3) literal (UTC, millisecond precision)."""
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def record(*, method: str, route: str, status_code: int, duration_ms: float,
           tenant_id: str = "", trace_id: str = "") -> None:
    """Cheap in-memory append on the request hot path. Never raises; drops when the buffer is full."""
    if not _active():
        return
    try:
        if len(_buf) >= _MAX_BUFFER:
            return
        sc = int(status_code)
        _buf.append({
            "ts": _ch_ts(time.time()),
            "service": SERVICE,
            "method": (method or "")[:16],
            "route": (route or "")[:200],
            "status_code": sc if 0 <= sc <= 65535 else 0,
            "duration_ms": round(float(duration_ms), 2),
            "has_error": 1 if sc >= 500 else 0,
            "tenant_id": (tenant_id or "")[:80],
            "trace_id": (trace_id or "")[:64],
        })
    except Exception:  # noqa: BLE001
        pass


def ensure_started() -> None:
    """Start the background flush loop once, on the running event loop. Idempotent; never raises."""
    global _started
    if _started or not _active():
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_flush_loop())
        _started = True
    except Exception:  # noqa: BLE001
        pass


async def _flush_loop() -> None:
    interval = float(os.getenv("HTTP_METRICS_FLUSH_S", "5"))
    while True:
        try:
            await asyncio.sleep(interval)
            await _flush_once()
        except asyncio.CancelledError:
            break
        except Exception:  # noqa: BLE001
            pass


async def _flush_once() -> None:
    global _ensured
    if not _active() or not _buf:
        return
    batch = _buf[:]
    del _buf[:len(batch)]
    if not batch:
        return
    try:
        import httpx
        url = _ch_url()
        async with httpx.AsyncClient(timeout=float(os.getenv("HTTP_METRICS_TIMEOUT", "8"))) as c:
            if not _ensured:
                try:
                    await _post(c, url, _DDL)
                    _ensured = True
                except Exception:  # noqa: BLE001
                    pass
            body = "\n".join(json.dumps(o, ensure_ascii=False) for o in batch)
            r = await _post(c, url, f"INSERT INTO {TABLE} FORMAT JSONEachRow", body)
            if r is not None and r.status_code >= 400:
                logger.warning("http_metrics insert failed: HTTP %s %s", r.status_code, (r.text or "")[:200])
            else:
                logger.info("http_metrics insert ok (%d rows)", len(batch))
    except Exception as exc:  # noqa: BLE001
        logger.warning("http_metrics flush error: %r", exc)


async def _post(c, url: str, query: str, body: str = ""):
    """POST a query (+ optional body) to ClickHouse HTTP. Auth: URL userinfo OR env params, never both."""
    params = {"query": query}
    if "@" not in (urlsplit(url).netloc or ""):
        user = (os.getenv("CLICKHOUSE_USER") or "").strip()
        pw = (os.getenv("CLICKHOUSE_PASSWORD") or "").strip()
        if user:
            params["user"] = user
        if pw:
            params["password"] = pw
    return await c.post(url + "/", params=params, content=(body.encode("utf-8") if body else b""))
