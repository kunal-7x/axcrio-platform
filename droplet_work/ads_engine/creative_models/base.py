"""ads_engine.creative_models.base — the shared async model-adapter substrate.

Every creative model adapter (Nano Banana, Ideogram, Recraft, FLUX.2, Bannerbear) inherits
this. It is a THIN wrapper over `connectors.base.BaseConnector` (the same SSRF-safe, backoff-
retried, structured-result HTTP base the ad-platform connectors use) plus the three-verb
generation contract the creative job state-machine drives:

    submit(req)  -> SubmitResult(ok, job_ref|inline_bytes|url, ...)   # fire one 202 POST (or inline)
    poll(job_ref)-> PollResult(state in {pending, done, failed}, ...) # advance an async provider job
    cost_minor(req) -> int                                            # paise estimate (budget-by-MP)

HARD invariants (binding — design/creative.md §1, §9):
  * Keys come ONLY via the injected `get_secret_json(tenant_id, provider_def_id)` seam
    (vault_adapter). NO key in .env, NO `_key` constant, NEVER logged.
  * httpx is LAZY (inherited from BaseConnector) — an httpx-less build still imports.
  * NEVER raises into the tick: every method returns a structured result; a failure is a
    state, not an exception. (BaseConnector already returns ConnectorResult.fail.)
  * EOL guard: a model whose pinned id is on `config.MODEL_PINS['..._eol_blocklist']` is
    REFUSED at submit (returns SubmitResult(ok=False, error='eol_model')) — never calls out.
  * OFFLINE/mocked: the connector accepts an injected `http` (httpx.AsyncClient on a
    MockTransport). With no key + no http, submit returns not_configured cleanly.

The adapter is constructed per (tenant, model) with a `get_secret_json` closure already bound
to the tenant, so the adapter never sees a tenant_id beyond what it needs and never holds a key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Reuse the ad-connector HTTP substrate (SSRF allowlist + backoff + structured result).
from ..connectors.base import BaseConnector, ConnectorError, ConnectorResult


# ---------------------------------------------------------------------------
# The generation request + the two result value objects the job machine consumes.
# ---------------------------------------------------------------------------
@dataclass
class GenRequest:
    """One creative-generation ask. Built by creative.py from the brief + brand-kit."""
    kind: str                      # headline_image | bulk_image | vector_badge | property_shot | multi_size
    prompt: str = ""               # the composed text prompt (headline + scene)
    headline: str = ""             # the literal headline text (for text-in-image models)
    width: int = 1080
    height: int = 1080
    n: int = 1
    aspect: str = "1:1"
    # multi_size (Bannerbear) specifics:
    template_set: str = ""
    sizes: list = field(default_factory=list)   # ["1080x1080","1080x1920",...]
    source_url: str = ""           # the design to compose into all sizes
    modifications: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class SubmitResult:
    """Returned by submit(): either an async job_ref to poll, OR an inline finished asset."""
    ok: bool
    model: str = ""
    job_ref: str = ""              # provider job id to poll (async path)
    inline: bool = False           # True => done immediately; url/bytes already present
    url: str = ""                  # finished asset url (inline path)
    bytes_b64: str = ""            # finished asset bytes (inline path, base64)
    cost_minor: int = 0
    error: str = ""                # eol_model | not_configured | <ConnectorError value>
    detail: str = ""

    @classmethod
    def fail(cls, model: str, error: str, detail: str = "") -> "SubmitResult":
        return cls(ok=False, model=model, error=error, detail=detail)


@dataclass
class PollResult:
    """Returned by poll(): the live state of an async provider job."""
    state: str = "pending"         # pending | done | failed
    url: str = ""
    bytes_b64: str = ""
    sizes: dict = field(default_factory=dict)   # multi_size: {"1080x1080": url, ...}
    cost_minor: int = 0
    error: str = ""
    detail: str = ""

    @classmethod
    def pending(cls) -> "PollResult":
        return cls(state="pending")

    @classmethod
    def done(cls, *, url: str = "", bytes_b64: str = "", sizes: Optional[dict] = None,
             cost_minor: int = 0) -> "PollResult":
        return cls(state="done", url=url, bytes_b64=bytes_b64, sizes=sizes or {},
                   cost_minor=cost_minor)

    @classmethod
    def failed(cls, error: str, detail: str = "") -> "PollResult":
        return cls(state="failed", error=error, detail=detail)


# ---------------------------------------------------------------------------
# The adapter base.
# ---------------------------------------------------------------------------
class CreativeModelBase(BaseConnector):
    """Base for one creative model. Subclasses set `model_id`, `base_url`, `channel`,
    a `capability` slug, and implement `_submit_impl` / `_poll_impl` / `_auth_headers`.

    The `get_secret_json` closure (already tenant-bound) yields the blob whose fields hold the
    api key. `provider_def_id` is the vault def to read; if unset, `_blob()` returns None and
    every submit degrades to not_configured (the OFFLINE/no-key path).
    """

    model_id: str = "base"
    capability: str = "image_gen"
    # The price model: per-image flat (paise) OR per-megapixel first/subsequent (paise).
    price_per_image_minor: int = 0
    price_first_mp_minor: int = 0
    price_sub_mp_minor: int = 0
    secret_field: str = "api_key"          # which blob field holds the key
    async_provider: bool = False           # True => submit returns a job_ref to poll

    def __init__(
        self,
        *,
        get_secret_json: Optional[Callable[[], Optional[dict]]] = None,
        provider_def_id: str = "",
        http: Any = None,
        base_url: str = "",
        sleep_fn: Any = None,
        now_fn: Any = None,
    ) -> None:
        super().__init__(base_url=base_url, http=http, sleep_fn=sleep_fn, now_fn=now_fn)
        self._get_secret_json = get_secret_json
        self.provider_def_id = provider_def_id

    # -- secret access (vault-only) -------------------------------------------------------------
    def _blob(self) -> Optional[dict]:
        """The decrypted secret blob (dict) for this adapter, or None (no key => not_configured)."""
        if self._get_secret_json is None:
            return None
        try:
            return self._get_secret_json()
        except Exception:  # noqa: BLE001 — vault errors degrade to not_configured, never raise
            return None

    def _api_key(self) -> Optional[str]:
        blob = self._blob()
        if not isinstance(blob, dict):
            return None
        v = blob.get(self.secret_field)
        return str(v) if v else None

    def _auth_headers(self) -> dict:
        """Default: no header (subclass injects its provider's auth scheme via _api_key())."""
        return {}

    # -- cost (budget-by-megapixel, design §4) --------------------------------------------------
    def cost_minor(self, req: GenRequest) -> int:
        """Paise estimate for one generation. Per-image flat, else per-MP first+subsequent."""
        n = max(1, int(req.n or 1))
        if self.price_per_image_minor:
            return self.price_per_image_minor * n
        mp = max(1.0, (int(req.width or 1024) * int(req.height or 1024)) / 1_000_000.0)
        per = self.price_first_mp_minor + self.price_sub_mp_minor * max(0.0, mp - 1.0)
        return int(round(per)) * n

    # -- the three-verb contract ----------------------------------------------------------------
    async def submit(self, req: GenRequest) -> SubmitResult:
        """Fire ONE generation. Returns a job_ref (async) or an inline finished asset.

        EOL + key guards run FIRST so no call goes out for a blocked/unconfigured model.
        Never raises — all transport failures come back as SubmitResult(ok=False).
        """
        if self.model_id in _eol_blocklist():
            return SubmitResult.fail(self.model_id, "eol_model",
                                     f"{self.model_id} is on the EOL blocklist")
        if self._api_key() is None:
            return SubmitResult.fail(self.model_id, "not_configured", "no vault key")
        try:
            return await self._submit_impl(req)
        except Exception as exc:  # noqa: BLE001 — defensive: never raise into the job machine
            return SubmitResult.fail(self.model_id, "transport_error", type(exc).__name__)

    async def poll(self, job_ref: str, req: Optional[GenRequest] = None) -> PollResult:
        """Advance one async provider job. Inline providers should never be polled."""
        try:
            return await self._poll_impl(job_ref, req)
        except Exception as exc:  # noqa: BLE001
            return PollResult.failed("transport_error", type(exc).__name__)

    # -- subclass hooks -------------------------------------------------------------------------
    async def _submit_impl(self, req: GenRequest) -> SubmitResult:  # pragma: no cover - abstract
        raise NotImplementedError

    async def _poll_impl(self, job_ref: str, req: Optional[GenRequest]) -> PollResult:
        """Default: inline providers have nothing to poll -> treat any poll as done-unknown."""
        return PollResult.failed("not_pollable", f"{self.model_id} is inline-only")

    # -- small shared helpers for subclasses ----------------------------------------------------
    @staticmethod
    def _first_url(data: Any, *keys: str) -> str:
        """Pluck the first image url from a provider response, trying common shapes."""
        if not isinstance(data, dict):
            return ""
        for k in keys:
            v = data.get(k)
            if isinstance(v, str) and v:
                return v
            if isinstance(v, list) and v:
                first = v[0]
                if isinstance(first, str) and first:
                    return first
                if isinstance(first, dict):
                    for kk in ("url", "image_url", "uri"):
                        if isinstance(first.get(kk), str) and first[kk]:
                            return first[kk]
        return ""


def _eol_blocklist() -> list:
    """The EOL/blocked model ids (config single-source). Degrade-safe to a hard-pinned list."""
    try:
        from .. import config
        bl = getattr(config, "MODEL_PINS", {}).get("_eol_blocklist")
        if isinstance(bl, list):
            return [str(x) for x in bl]
    except Exception:  # noqa: BLE001
        pass
    # Hard fallback (research/creative-gen-apis.md "Hard constraints").
    return ["gpt-image-1", "veo-3.0", "veo-3.0-fast", "veo-3.0-generate-001"]


__all__ = [
    "CreativeModelBase", "GenRequest", "SubmitResult", "PollResult",
    "ConnectorError", "ConnectorResult",
]
