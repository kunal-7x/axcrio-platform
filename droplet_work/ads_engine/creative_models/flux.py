"""ads_engine.creative_models.flux — Black Forest Labs FLUX.2 (photoreal property/product).

ASYNC provider: `POST https://api.bfl.ai/v1/flux-2-max` returns a polling id; poll until the
result url lands (design §3/§9, research §1). Per-megapixel billed (max: $0.07 first MP).

Auth: header `x-key: <key>` (blob field `api_key`). httpx lazy via base; no key -> not_configured.
"""

from __future__ import annotations

from typing import Optional

from .base import CreativeModelBase, GenRequest, PollResult, SubmitResult


class FluxModel(CreativeModelBase):
    channel = "flux"
    base_url = "https://api.bfl.ai"
    capability = "image_gen"
    model_id = "flux-2-max"
    # per-megapixel: first MP $0.07 (~Rs5.85), subsequent $0.03 (~Rs2.50). paise.
    price_first_mp_minor = 585
    price_sub_mp_minor = 250
    secret_field = "api_key"
    async_provider = True

    def __init__(self, *, model_id: str = "", **kw) -> None:
        super().__init__(**kw)
        if model_id:
            self.model_id = model_id

    def _auth_headers(self) -> dict:
        key = self._api_key()
        return {"x-key": key} if key else {}

    async def _submit_impl(self, req: GenRequest) -> SubmitResult:
        body = {
            "prompt": req.prompt or "photoreal product shot",
            "width": int(req.width or 1024),
            "height": int(req.height or 1024),
        }
        res = await self._request("POST", f"/v1/{self.model_id}", json=body)
        if not res.ok:
            return SubmitResult.fail(
                self.model_id,
                res.error.value if res.error else "upstream_error",
                res.detail,
            )
        ref = ""
        if isinstance(res.data, dict):
            ref = str(res.data.get("id") or res.data.get("polling_url") or "")
        if not ref:
            return SubmitResult.fail(self.model_id, "invalid_request", "no polling id returned")
        return SubmitResult(ok=True, model=self.model_id, job_ref=ref,
                            cost_minor=self.cost_minor(req))

    async def _poll_impl(self, job_ref: str, req: Optional[GenRequest]) -> PollResult:
        # BFL get_result is keyed by the polling id.
        res = await self._request("GET", "/v1/get_result", params={"id": job_ref})
        if not res.ok:
            return PollResult.failed(
                res.error.value if res.error else "upstream_error", res.detail)
        data = res.data if isinstance(res.data, dict) else {}
        status = str(data.get("status", "")).lower()
        if status in ("ready", "completed", "succeeded"):
            url = ""
            result = data.get("result") or {}
            if isinstance(result, dict):
                url = result.get("sample") or result.get("url") or ""
            url = url or self._first_url(data, "result", "images")
            return PollResult.done(url=url, cost_minor=self.cost_minor(req) if req else 0)
        if status in ("error", "failed", "content_moderated"):
            return PollResult.failed("upstream_error", status)
        return PollResult.pending()


def build(*, model_id: str = "", **kw) -> FluxModel:
    return FluxModel(model_id=model_id, **kw)
