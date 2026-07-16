"""ads_engine.creative_models.recraft — Recraft V3 (logos / badges / vectors, placed text).

Inline provider: the only model giving true SVG output + controllable text placement
(design §3, research §1). Used for offer badges / logos where text position matters.

Auth: header `Authorization: Bearer <key>` (blob field `api_key`). Flat per image: raster
$0.04 / vector $0.08. httpx lazy via base; no key -> not_configured.
"""

from __future__ import annotations

from .base import CreativeModelBase, GenRequest, SubmitResult


class RecraftModel(CreativeModelBase):
    channel = "recraft"
    base_url = "https://external.api.recraft.ai"
    capability = "image_gen"
    model_id = "recraft-v3"
    price_per_image_minor = 670        # ~$0.08 vector -> ~Rs6.70 (paise)
    secret_field = "api_key"
    async_provider = False

    def _auth_headers(self) -> dict:
        key = self._api_key()
        return {"Authorization": f"Bearer {key}"} if key else {}

    async def _submit_impl(self, req: GenRequest) -> SubmitResult:
        body = {
            "prompt": req.prompt or req.headline or "offer badge",
            "model": "recraftv3",
            "style": req.extra.get("style", "vector_illustration"),
            "n": max(1, int(req.n or 1)),
        }
        if req.extra.get("text_layout"):
            body["text_layout"] = req.extra["text_layout"]
        if req.extra.get("rgb_colors"):
            body["controls"] = {"colors": req.extra["rgb_colors"]}
        res = await self._request("POST", "/v1/images/generations", json=body)
        if not res.ok:
            return SubmitResult.fail(
                self.model_id,
                res.error.value if res.error else "upstream_error",
                res.detail,
            )
        url = self._first_url(res.data, "data", "images")
        return SubmitResult(
            ok=True, model=self.model_id, inline=True, url=url,
            cost_minor=self.cost_minor(req),
        )


def build(**kw) -> RecraftModel:
    return RecraftModel(**kw)
