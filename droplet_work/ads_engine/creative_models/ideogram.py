"""ads_engine.creative_models.ideogram — Ideogram v3 (typographic headline hero).

Inline provider: `POST https://api.ideogram.ai/v1/ideogram-v3/generate` returns the rendered
image url(s) in the response. Best-in-class short-headline text fidelity (design §3, research §1).

Auth: header `Api-Key: <key>` (blob field `api_key`). Pricing per image by quality tier
(Quality ~$0.09). httpx lazy via base; no key -> not_configured.
"""

from __future__ import annotations

from .base import CreativeModelBase, GenRequest, SubmitResult


class IdeogramModel(CreativeModelBase):
    channel = "ideogram"
    base_url = "https://api.ideogram.ai"
    capability = "image_gen"
    model_id = "ideogram-v3"
    price_per_image_minor = 750        # ~$0.09 Quality -> ~Rs7.50 (paise)
    secret_field = "api_key"
    async_provider = False

    def _auth_headers(self) -> dict:
        key = self._api_key()
        return {"Api-Key": key} if key else {}

    async def _submit_impl(self, req: GenRequest) -> SubmitResult:
        body = {
            "prompt": req.prompt or req.headline or "advertisement headline creative",
            "rendering_speed": "QUALITY",
            "aspect_ratio": _aspect(req.aspect),
            "num_images": max(1, int(req.n or 1)),
        }
        res = await self._request("POST", "/v1/ideogram-v3/generate", json=body)
        if not res.ok:
            return SubmitResult.fail(
                self.model_id,
                res.error.value if res.error else "upstream_error",
                res.detail,
            )
        url = self._extract(res.data)
        return SubmitResult(
            ok=True, model=self.model_id, inline=True, url=url,
            cost_minor=self.cost_minor(req),
        )

    @staticmethod
    def _extract(data) -> str:
        try:
            items = data.get("data") or data.get("images") or []
            if items:
                first = items[0]
                if isinstance(first, dict):
                    return first.get("url") or first.get("image_url") or ""
                if isinstance(first, str):
                    return first
        except Exception:  # noqa: BLE001
            pass
        return ""


def _aspect(a: str) -> str:
    return {"1:1": "ASPECT_1_1", "4:5": "ASPECT_4_5", "9:16": "ASPECT_9_16",
            "16:9": "ASPECT_16_9"}.get(a, "ASPECT_1_1")


def build(**kw) -> IdeogramModel:
    return IdeogramModel(**kw)
