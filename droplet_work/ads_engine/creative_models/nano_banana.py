"""ads_engine.creative_models.nano_banana — Google Gemini image (Nano Banana / Nano Banana Pro).

Inline (synchronous) provider: the generate call returns image bytes/url in the response — no
async job to poll. Models (design §3, research §1):
  * gemini-2.5-flash-image       — "Nano Banana", bulk/cheap variations (~$0.039/img).
  * gemini-3-pro-image-preview   — "Nano Banana Pro", headline hero (~$0.134/2K).

Auth: header `x-goog-api-key: <key>` (blob field `api_key`). NEVER veo-3.0 (video, EOL) — this
is image-only. httpx is lazy via the base; with no key -> not_configured.
"""

from __future__ import annotations

from typing import Optional

from .base import CreativeModelBase, GenRequest, SubmitResult


class NanoBananaModel(CreativeModelBase):
    channel = "nano_banana"
    base_url = "https://generativelanguage.googleapis.com"
    capability = "image_gen"
    model_id = "gemini-2.5-flash-image"
    price_per_image_minor = 325        # ~$0.039 -> ~Rs3.25 (paise)
    secret_field = "api_key"
    async_provider = False

    def __init__(self, *, model_id: str = "", **kw) -> None:
        super().__init__(**kw)
        if model_id:
            self.model_id = model_id
            if "pro" in model_id:
                self.price_per_image_minor = 1115  # ~$0.134 -> ~Rs11.15

    def _auth_headers(self) -> dict:
        key = self._api_key()
        return {"x-goog-api-key": key} if key else {}

    async def _submit_impl(self, req: GenRequest) -> SubmitResult:
        path = f"/v1beta/models/{self.model_id}:generateContent"
        prompt = req.prompt or req.headline or "advertisement creative"
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        res = await self._request("POST", path, json=body)
        if not res.ok:
            return SubmitResult.fail(
                self.model_id,
                res.error.value if res.error else "upstream_error",
                res.detail,
            )
        url = self._extract(res.data)
        b64 = self._extract_inline(res.data)
        return SubmitResult(
            ok=True, model=self.model_id, inline=True, url=url, bytes_b64=b64,
            cost_minor=self.cost_minor(req),
        )

    @staticmethod
    def _extract(data) -> str:
        # Gemini returns candidates[].content.parts[].fileData.fileUri or inlineData.
        try:
            cands = data.get("candidates") or []
            for c in cands:
                for p in (c.get("content", {}).get("parts") or []):
                    fd = p.get("fileData") or {}
                    if isinstance(fd.get("fileUri"), str) and fd["fileUri"]:
                        return fd["fileUri"]
        except Exception:  # noqa: BLE001
            pass
        return ""

    @staticmethod
    def _extract_inline(data) -> str:
        try:
            for c in (data.get("candidates") or []):
                for p in (c.get("content", {}).get("parts") or []):
                    idata = p.get("inlineData") or p.get("inline_data") or {}
                    if isinstance(idata.get("data"), str) and idata["data"]:
                        return idata["data"]
        except Exception:  # noqa: BLE001
            pass
        return ""


def build(*, model_id: str = "", **kw) -> NanoBananaModel:
    return NanoBananaModel(model_id=model_id, **kw)
