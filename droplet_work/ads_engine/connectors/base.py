"""ads_engine.connectors.base — the shared async HTTP substrate every connector inherits.

This is the ONLY code in ads_engine that talks to an ad platform over the network. Design:
vault-connectors.md §2 (the BaseConnector + the ConnectorResult/ConnectorError vocabulary).

HARD invariants (binding):
  * Errors are RETURNED as a structured `ConnectorResult(ok=False, error=...)` — NEVER raised into
    the tick / the live spine. A connector method that hits a network/timeout/HTTP error gets a
    typed result back; `tick.py` swallows nothing because nothing is thrown.
  * Per-request auth header injection: the subclass supplies the auth header(s); the base never
    persists or logs the token. Auth is applied per request, not stored on the client.
  * Exponential backoff + full jitter on 429 / 5xx, honoring Retry-After. Cap + max-attempts from
    config. 4xx (except 429) is terminal — no retry (it won't fix itself).
  * SSRF-safe host allowlist: a request may only go to the connector's pinned base_url host.
  * Timeouts: 20s connect / 60s read (configurable).

NO real network in tests: the base accepts an injected `http` (an httpx.AsyncClient built on a
mock transport) — the retry/backoff unit test drives it with a scripted MockTransport, zero sockets.
httpx is imported LAZILY (inside __init__/_request) so importing this module on an httpx-less build
never crashes the package (the mount import-guard stays intact).
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlparse

_log = logging.getLogger("ads_engine.connectors.base")

# Backoff knobs (vault-connectors.md §2.1: base 0.5s, cap 60s, max 5 attempts, full jitter).
_BACKOFF_BASE_S = 0.5
_BACKOFF_CAP_S = 60.0
_MAX_ATTEMPTS_DEFAULT = 5
_RETRY_AFTER_CAP_S = 120.0  # never honor an absurd Retry-After

# Timeouts.
_CONNECT_TIMEOUT_S = 20.0
_READ_TIMEOUT_S = 60.0

_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class ConnectorError(str, Enum):
    """The surfacing vocabulary — maps 1:1 onto _lib.ts AdsStatus blocked_*/provider.error."""
    NOT_CONFIGURED = "not_configured"
    CRED_EXPIRED = "cred_expired"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "blocked_quota"
    PERMISSION = "permission_denied"
    INVALID_REQUEST = "invalid_request"
    HOUSING_REQUIRED = "housing_required"
    WEBHOOK_TLS = "webhook_tls"
    UPSTREAM = "upstream_error"
    TIMEOUT = "timeout"
    TRANSPORT = "transport_error"
    SSRF_BLOCKED = "ssrf_blocked"
    BLOCKED_GOOGLE_LEGACY = "blocked_google_legacy_offline"


@dataclass
class ConnectorResult:
    """The structured result EVERY connector method returns. `ok` is the only branch."""
    ok: bool
    status: int = 0
    data: Any = None
    error: Optional[ConnectorError] = None
    detail: str = ""            # short, NON-secret diagnostic (never a token / never a body dump)
    rate: dict = field(default_factory=dict)  # parsed usage headers (for the breaker / analytics)
    attempts: int = 0

    @classmethod
    def fail(cls, error: ConnectorError, *, status: int = 0, detail: str = "",
             attempts: int = 0, rate: Optional[dict] = None) -> "ConnectorResult":
        return cls(ok=False, status=status, error=error, detail=detail,
                   attempts=attempts, rate=rate or {})


def _backoff_delay(attempt: int, retry_after: Optional[float]) -> float:
    """Exponential backoff with FULL jitter, honoring a sane Retry-After. `attempt` is 0-based."""
    if retry_after is not None and retry_after >= 0:
        return min(retry_after, _RETRY_AFTER_CAP_S)
    ceil = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2 ** attempt))
    return random.uniform(0.0, ceil)  # full jitter


def _parse_retry_after(headers: Any) -> Optional[float]:
    """Retry-After in seconds (numeric form only — HTTP-date form is rare here). None if absent."""
    try:
        raw = headers.get("retry-after") if headers is not None else None
    except Exception:  # noqa: BLE001
        raw = None
    if not raw:
        return None
    try:
        return float(str(raw).strip())
    except Exception:  # noqa: BLE001
        return None


class BaseConnector:
    """Async httpx base. Subclasses set `channel`, `base_url`, and `_auth_headers()`.

    Construction is cheap + crash-proof: httpx is imported lazily; if it is missing, the connector
    is still constructible and every `_request` returns a structured TRANSPORT error (never raises).
    """

    channel: str = "base"
    base_url: str = ""

    def __init__(
        self,
        creds: Any = None,
        *,
        version: str = "",
        base_url: str = "",
        http: Any = None,
        now_fn: Optional[Callable[[], float]] = None,
        sleep_fn: Optional[Callable[[float], Awaitable[None]]] = None,
        max_attempts: int = _MAX_ATTEMPTS_DEFAULT,
    ) -> None:
        self.creds = creds
        self.version = version
        if base_url:
            self.base_url = base_url
        self._http = http  # injected httpx.AsyncClient (or mock-transport client) — preferred in tests
        self._owns_http = False
        self._now = now_fn or __import__("time").time
        self._sleep = sleep_fn or asyncio.sleep
        self._max_attempts = max(1, int(max_attempts))

    # -- auth: subclasses override to inject per-request headers (token NEVER stored/logged) -----
    def _auth_headers(self) -> dict:
        """Return the per-request auth header(s). Default: none. Subclasses inject Bearer/D360 here."""
        return {}

    # -- host allowlist (SSRF guard) ------------------------------------------------------------
    def _allowed_host(self) -> str:
        try:
            return (urlparse(self.base_url).hostname or "").lower()
        except Exception:  # noqa: BLE001
            return ""

    def _build_url(self, path: str) -> Optional[str]:
        """Join base_url + path; reject anything that escapes the pinned host (SSRF). None => blocked."""
        if path.startswith("http://") or path.startswith("https://"):
            url = path
        else:
            url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:  # noqa: BLE001
            return None
        allow = self._allowed_host()
        if not host or not allow or host != allow:
            return None
        return url

    def _client(self):
        """The httpx.AsyncClient to use. Injected one wins (tests); else lazily build one we own."""
        if self._http is not None:
            return self._http
        try:
            import httpx  # lazy: an httpx-less build still constructs the connector
        except Exception:  # noqa: BLE001
            return None
        timeout = httpx.Timeout(_READ_TIMEOUT_S, connect=_CONNECT_TIMEOUT_S)
        self._http = httpx.AsyncClient(timeout=timeout)
        self._owns_http = True
        return self._http

    async def aclose(self) -> None:
        """Close a client we own (never close an injected one)."""
        if self._owns_http and self._http is not None:
            try:
                await self._http.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._http = None
            self._owns_http = False

    # -- the one request primitive every method calls -------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Any = None,
        data: Any = None,
        headers: Optional[dict] = None,
        retries: Optional[int] = None,
    ) -> ConnectorResult:
        """Issue an auth'd, SSRF-checked, backoff-retried request. Returns a structured result.

        NEVER raises. NEVER logs a token / a request body / a response body. Retries 429 + 5xx
        with exponential full-jitter backoff (honoring Retry-After); 4xx (except 429) is terminal.
        """
        url = self._build_url(path)
        if url is None:
            return ConnectorResult.fail(
                ConnectorError.SSRF_BLOCKED,
                detail=f"{self.channel}: path escapes pinned host",
            )

        client = self._client()
        if client is None:
            return ConnectorResult.fail(
                ConnectorError.TRANSPORT, detail=f"{self.channel}: httpx unavailable")

        try:
            import httpx
            _TransportError = httpx.TransportError
            _TimeoutException = httpx.TimeoutException
        except Exception:  # noqa: BLE001
            _TransportError = Exception
            _TimeoutException = Exception

        max_attempts = self._max_attempts if retries is None else max(1, int(retries) + 1)
        req_headers = dict(self._auth_headers())
        if headers:
            req_headers.update(headers)

        last_status = 0
        last_rate: dict = {}
        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            try:
                resp = await client.request(
                    method, url, params=params, json=json, data=data, headers=req_headers)
            except _TimeoutException:
                # network timeout: retry with backoff (it may be transient).
                if attempt < max_attempts:
                    await self._sleep(_backoff_delay(attempt - 1, None))
                    continue
                return ConnectorResult.fail(
                    ConnectorError.TIMEOUT, detail=f"{self.channel}: request timed out",
                    attempts=attempt)
            except _TransportError:
                if attempt < max_attempts:
                    await self._sleep(_backoff_delay(attempt - 1, None))
                    continue
                return ConnectorResult.fail(
                    ConnectorError.TRANSPORT, detail=f"{self.channel}: transport error",
                    attempts=attempt)
            except Exception:  # noqa: BLE001 — any other client error -> structured, never raised
                return ConnectorResult.fail(
                    ConnectorError.TRANSPORT, detail=f"{self.channel}: client error",
                    attempts=attempt)

            status = getattr(resp, "status_code", 0)
            last_status = status
            last_rate = self._parse_rate(resp)

            # success
            if 200 <= status < 300:
                return ConnectorResult(ok=True, status=status, data=self._body(resp),
                                       rate=last_rate, attempts=attempt)

            # retryable: 429 / 5xx -> backoff (honor Retry-After) and retry while attempts remain.
            if status in _RETRYABLE_STATUS and attempt < max_attempts:
                retry_after = _parse_retry_after(getattr(resp, "headers", None))
                await self._sleep(_backoff_delay(attempt - 1, retry_after))
                continue

            # terminal: prefer the platform-specific body mapping (_surface) — e.g. a Graph
            # error code 190 -> cred_expired even on an HTTP 400 — then fall back to the generic
            # status map. _surface is best-effort and never raises (subclass-guarded).
            mapped = None
            try:
                mapped = self._surface(self._body(resp))
            except Exception:  # noqa: BLE001 — surfacing is best-effort, never fails the request
                mapped = None
            return ConnectorResult.fail(
                mapped or self._map_status(status), status=status, rate=last_rate,
                attempts=attempt, detail=f"{self.channel}: http {status}")

        # attempts exhausted on a retryable status.
        return ConnectorResult.fail(
            self._map_status(last_status), status=last_status, rate=last_rate,
            attempts=attempt, detail=f"{self.channel}: retries exhausted")

    # -- helpers --------------------------------------------------------------------------------
    @staticmethod
    def _body(resp: Any) -> Any:
        try:
            return resp.json()
        except Exception:  # noqa: BLE001 — non-JSON body -> raw text (bounded by httpx)
            try:
                return {"_text": resp.text}
            except Exception:  # noqa: BLE001
                return None

    def _map_status(self, status: int) -> ConnectorError:
        """Map a terminal HTTP status to the error vocabulary. Subclasses override `_surface` for
        platform-specific error-code mapping (e.g. Meta 190 -> cred_expired)."""
        if status == 429:
            return ConnectorError.RATE_LIMITED
        if status in (401, 403):
            return ConnectorError.PERMISSION
        if status == 400 or status == 422:
            return ConnectorError.INVALID_REQUEST
        if 500 <= status < 600:
            return ConnectorError.UPSTREAM
        return ConnectorError.UPSTREAM

    def _parse_rate(self, resp: Any) -> dict:
        """Parse rate/usage headers (subclasses override for X-Business-Use-Case-Usage etc.).
        Default: surface Retry-After if present. NEVER includes secrets."""
        out: dict = {}
        ra = _parse_retry_after(getattr(resp, "headers", None))
        if ra is not None:
            out["retry_after"] = ra
        return out

    def _surface(self, raw: Any) -> Optional[ConnectorError]:
        """Map a parsed platform error body -> ConnectorError (subclass hook). Default: None."""
        return None
