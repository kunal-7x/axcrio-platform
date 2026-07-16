"""ads_engine.creative_models.bannerbear — multi-size compose/resize to ALL placements.

ASYNC provider: `POST /v2/collections` with a template_set + one modifications array renders
EVERY placement size from one call; poll `GET /v2/collections/:uid` until all sizes render
(design §2 composing stage / §9, research §3). This is the "one design -> all placements" primitive.

Auth: header `Authorization: Bearer <project key>` (blob field `api_key`). httpx lazy via base;
no key -> not_configured.
"""

from __future__ import annotations

from typing import Optional

from .base import CreativeModelBase, GenRequest, PollResult, SubmitResult

# Default placement matrix -> (template-size label, WxH). All four aspect families (design brief).
DEFAULT_PLACEMENTS = {
    "meta_feed_1x1": "1080x1080",
    "meta_portrait_4x5": "1080x1350",
    "meta_story_9x16": "1080x1920",
    "google_landscape_16x9": "1200x675",
}


class BannerbearModel(CreativeModelBase):
    channel = "bannerbear"
    base_url = "https://api.bannerbear.com"
    capability = "image_compose"
    model_id = "bannerbear"
    # composition is template-render priced ($49/1k renders ~Rs4/render); flat per placement.
    price_per_image_minor = 400
    secret_field = "api_key"
    async_provider = True

    def _auth_headers(self) -> dict:
        key = self._api_key()
        return {"Authorization": f"Bearer {key}"} if key else {}

    async def _submit_impl(self, req: GenRequest) -> SubmitResult:
        template_set = req.template_set or req.extra.get("template_set") or "ts_real_estate_v1"
        mods = req.modifications or [
            {"name": "image", "image_url": req.source_url},
            {"name": "headline", "text": req.headline},
        ]
        body = {"template_set": template_set, "modifications": mods}
        res = await self._request("POST", "/v2/collections", json=body)
        if not res.ok:
            return SubmitResult.fail(
                self.model_id,
                res.error.value if res.error else "upstream_error",
                res.detail,
            )
        data = res.data if isinstance(res.data, dict) else {}
        uid = str(data.get("uid") or "")
        if not uid:
            return SubmitResult.fail(self.model_id, "invalid_request", "no collection uid")
        sizes = req.sizes or list(DEFAULT_PLACEMENTS.values())
        return SubmitResult(ok=True, model=self.model_id, job_ref=uid,
                            cost_minor=self.price_per_image_minor * max(1, len(sizes)))

    async def _poll_impl(self, job_ref: str, req: Optional[GenRequest]) -> PollResult:
        res = await self._request("GET", f"/v2/collections/{job_ref}")
        if not res.ok:
            return PollResult.failed(
                res.error.value if res.error else "upstream_error", res.detail)
        data = res.data if isinstance(res.data, dict) else {}
        status = str(data.get("status", "")).lower()
        if status and status != "completed":
            if status in ("failed", "error"):
                return PollResult.failed("upstream_error", status)
            return PollResult.pending()
        # completed: image_urls maps a per-template name -> url.
        sizes = {}
        urls = data.get("image_urls") or {}
        if isinstance(urls, dict):
            for name, url in urls.items():
                if isinstance(url, str) and url:
                    sizes[name] = url
        images = data.get("images") or []
        if isinstance(images, list):
            for img in images:
                if isinstance(img, dict):
                    nm = img.get("template") or img.get("name") or f"img{len(sizes)}"
                    u = img.get("image_url") or img.get("url")
                    if isinstance(u, str) and u:
                        sizes[str(nm)] = u
        if not sizes:
            return PollResult.pending()
        cost = self.price_per_image_minor * max(1, len(sizes))
        return PollResult.done(sizes=sizes, cost_minor=cost)


def build(**kw) -> BannerbearModel:
    return BannerbearModel(**kw)
