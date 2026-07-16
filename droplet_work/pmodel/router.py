"""pmodel.router — FastAPI surface for the 2D->3D Property Studio.

Mounted from caller.py via build_router(...), which injects the shared auth
helpers (resolve_tenant / can / need_auth / forbidden) plus the Spaces client and
presigner. NEVER trusts tenant_id from the request body — every owner check uses
the token-derived tenant. The only un-authenticated routes are the dormancy probe
and the public share-by-token read.
"""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse

from . import analyzer, assets3d, builder, hdrender, schema, store


def build_router(resolve_tenant, can, need_auth, forbidden, *,
                 s3_client=None, spaces_bucket: str = "", presign=None, audit=None):
    r = APIRouter(prefix="/pmodel", tags=["pmodel"])
    bucket = (spaces_bucket or "").strip()

    # -- helpers ------------------------------------------------------------
    def _owned(rec: dict | None, t: dict) -> bool:
        return bool(rec) and (t.get("is_admin") or rec.get("tenant_id") == t["tenant_id"])

    def _put(key: str, body: bytes, ctype: str) -> str:
        """Best-effort Spaces upload; returns the key on success, '' on failure
        (an empty/misconfigured bucket must NOT break model generation)."""
        if not (s3_client and bucket and key):
            return ""
        try:
            s3_client.put_object(Bucket=bucket, Key=key, Body=body, ContentType=ctype)
            return key
        except Exception:
            return ""

    def _audit(request, t, action, target):
        if audit:
            try:
                audit(request, t, action, "pmodel", target, channel="control")
            except Exception:
                pass

    def _attach_glb(scene: dict | None) -> dict | None:
        """Attach presigned generated-furniture GLB urls (no-op when dormant). Done
        on the OUTGOING copy only — presigned urls are never persisted."""
        try:
            return assets3d.resolve_urls(scene, presign, bucket)
        except Exception:
            return scene

    def _finalize(request, t, rec: dict, raw_layout: dict, source: str, img: bytes | None,
                  mime: str) -> JSONResponse:
        """Normalize -> build -> persist (record + Spaces) -> respond."""
        norm = schema.normalize_layout(raw_layout)
        if not norm["rooms"]:
            rec["state"] = "failed"
            store.save(rec)
            return JSONResponse({"error": "no_rooms_detected"}, status_code=422)
        scene = builder.build_scene(norm)
        if img is not None:
            ext = (mime.split("/")[-1] or "jpg")[:5]
            rec["plan_key"] = _put(f"pmodel/{rec['id']}/plan.{ext}", img, mime) or rec.get("plan_key", "")
        rec["scene_key"] = _put(f"pmodel/{rec['id']}/scene.json",
                                json.dumps(scene).encode("utf-8"), "application/json") or rec.get("scene_key", "")
        rec.update({"schema": norm, "scene": scene, "source": source, "state": "ready"})
        store.save(rec)
        _audit(request, t, "pmodel.build", rec["id"])
        return JSONResponse({"id": rec["id"], "state": "ready", "scene": _attach_glb(scene),
                             "name": rec["name"], "share_token": rec["share_token"]})

    # -- dormancy probe (un-gated) ------------------------------------------
    @r.get("/status")
    async def status(request: Request):
        return JSONResponse({
            "enabled": True,
            "vision": analyzer.vision_configured(),
            "vision_provider": analyzer._vp.label(),
            "assets3d": assets3d.enabled(),
            "hdrender": hdrender.enabled(),
        })

    @r.get("/samples")
    async def samples(request: Request):
        return JSONResponse({"samples": schema.demo_catalog()})

    # -- project CRUD -------------------------------------------------------
    @r.get("/projects")
    async def projects(request: Request):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        return JSONResponse({"projects": store.list_for(t["tenant_id"], t.get("is_admin", False))})

    @r.post("/projects")
    async def create(request: Request, name: str = Form("")):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot create projects")
        rec = store.new_project(t["tenant_id"], name)
        return JSONResponse(store._summary(rec))

    @r.get("/projects/{pid}")
    async def get_project(request: Request, pid: str):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        rec = store.get(pid)
        if not _owned(rec, t):
            return JSONResponse({"error": "not_found"}, status_code=404)
        if rec.get("scene"):
            _attach_glb(rec["scene"])
        return JSONResponse(rec)

    @r.delete("/projects/{pid}")
    async def delete_project(request: Request, pid: str):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot delete")
        rec = store.get(pid)
        if not _owned(rec, t):
            return JSONResponse({"error": "not_found"}, status_code=404)
        store.delete(pid)
        _audit(request, t, "pmodel.delete", pid)
        return JSONResponse({"ok": True})

    @r.post("/projects/{pid}/rename")
    async def rename(request: Request, pid: str, name: str = Form("")):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot rename")
        rec = store.get(pid)
        if not _owned(rec, t):
            return JSONResponse({"error": "not_found"}, status_code=404)
        rec["name"] = (name or rec["name"]).strip()[:80]
        store.save(rec)
        return JSONResponse(store._summary(rec))

    # -- model generation (3 input modes) -----------------------------------
    @r.post("/projects/{pid}/analyze")
    async def analyze(request: Request, pid: str, plan: UploadFile | None = File(None)):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot generate")
        rec = store.get(pid)
        if not _owned(rec, t):
            return JSONResponse({"error": "not_found"}, status_code=404)
        if plan is None:
            return JSONResponse({"error": "plan image required"}, status_code=422)
        img = await plan.read()
        if not img:
            return JSONResponse({"error": "empty file"}, status_code=422)
        mime = (getattr(plan, "content_type", "") or "image/jpeg")
        try:
            raw = await analyzer.analyze_floorplan(img, mime)
        except RuntimeError as e:
            code = str(e)
            if "not_configured" in code:
                return JSONResponse({"error": "vision_not_configured"}, status_code=503)
            return JSONResponse({"error": "analyze_failed"}, status_code=502)
        except Exception:
            return JSONResponse({"error": "analyze_failed"}, status_code=502)
        return _finalize(request, t, rec, raw, "image", img, mime)

    @r.post("/projects/{pid}/from-text")
    async def from_text(request: Request, pid: str, prompt: str = Form("")):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot generate")
        rec = store.get(pid)
        if not _owned(rec, t):
            return JSONResponse({"error": "not_found"}, status_code=404)
        if not (prompt or "").strip():
            return JSONResponse({"error": "prompt required"}, status_code=422)
        try:
            raw = await analyzer.layout_from_text(prompt)
        except RuntimeError as e:
            if "not_configured" in str(e):
                return JSONResponse({"error": "llm_not_configured"}, status_code=503)
            return JSONResponse({"error": "analyze_failed"}, status_code=502)
        except Exception:
            return JSONResponse({"error": "analyze_failed"}, status_code=502)
        return _finalize(request, t, rec, raw, "text", None, "")

    @r.post("/projects/{pid}/sample")
    async def sample(request: Request, pid: str, kind: str = Form("apartment_2bhk")):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot generate")
        rec = store.get(pid)
        if not _owned(rec, t):
            return JSONResponse({"error": "not_found"}, status_code=404)
        raw = schema.demo_layout(kind)
        # name the project after the sample if still default
        cat = {c["kind"]: c["title"] for c in schema.demo_catalog()}
        if rec.get("name", "").startswith("Untitled") and kind in cat:
            rec["name"] = cat[kind]
        return _finalize(request, t, rec, raw, "sample", None, "")

    # -- sharing ------------------------------------------------------------
    @r.post("/projects/{pid}/share")
    async def share_toggle(request: Request, pid: str, public: str = Form("true")):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot change sharing")
        rec = store.get(pid)
        if not _owned(rec, t):
            return JSONResponse({"error": "not_found"}, status_code=404)
        rec["public"] = str(public).strip().lower() in ("1", "true", "yes", "on")
        store.save(rec)
        _audit(request, t, "pmodel.share", pid)
        return JSONResponse({"public": rec["public"], "share_token": rec["share_token"],
                             "path": f"/share/property/{rec['share_token']}"})

    @r.get("/share/{token}")
    async def share_get(request: Request, token: str):
        """PUBLIC — customer-facing read. Presigns the plan image fresh; never leaks
        S3 creds. Only serves projects explicitly marked public."""
        rec = store.get_by_token(token)
        if not rec or not rec.get("public") or not rec.get("scene"):
            return JSONResponse({"error": "not_found"}, status_code=404)
        plan_url = ""
        if presign and bucket and rec.get("plan_key"):
            try:
                plan_url = presign(bucket, rec["plan_key"], 86400) or ""
            except Exception:
                plan_url = ""
        return JSONResponse({
            "name": rec.get("name", "Property Model"),
            "scene": _attach_glb(rec["scene"]),
            "plan_url": plan_url,
            "branding": _branding(),
        })

    # -- generative furniture (optional; dormant unless FEATURE_PMODEL_ASSETS3D) ----
    @r.post("/projects/{pid}/furniture/generate")
    async def gen_furniture(request: Request, pid: str):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot generate assets")
        if not assets3d.enabled():
            return JSONResponse({"error": "assets3d_not_configured"}, status_code=503)
        rec = store.get(pid)
        if not _owned(rec, t):
            return JSONResponse({"error": "not_found"}, status_code=404)
        result = await assets3d.generate_for_scene(rec.get("scene"), _put)
        _audit(request, t, "pmodel.furniture.generate", pid)
        return JSONResponse(result)

    # -- HD render (optional; enqueues to a separate GPU Blender worker) ----
    @r.post("/projects/{pid}/render")
    async def enqueue_render(request: Request, pid: str):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        if not can(t, "write"):
            return forbidden("read-only role cannot render")
        if not hdrender.enabled():
            return JSONResponse({"error": "hdrender_not_configured"}, status_code=503)
        rec = store.get(pid)
        if not _owned(rec, t) or not rec.get("scene"):
            return JSONResponse({"error": "not_found"}, status_code=404)
        job = hdrender.enqueue(rec["scene"])
        if not job:
            return JSONResponse({"error": "enqueue_failed"}, status_code=502)
        _audit(request, t, "pmodel.render", pid)
        return JSONResponse(job)

    @r.get("/render/{job_id}")
    async def render_status(request: Request, job_id: str):
        t = resolve_tenant(request)
        if not t:
            return need_auth()
        st = hdrender.status(job_id)
        if st.get("state") == "done" and st.get("result_key") and presign and bucket:
            try:
                st["url"] = presign(bucket, st["result_key"], 86400) or ""
            except Exception:
                st["url"] = ""
        return JSONResponse(st)

    return r


def _branding() -> dict:
    """Customer-facing branding + CTA on the public share page; env-tunable so each
    deployment can point the call-to-action at its own booking flow."""
    return {
        "brand": os.getenv("PMODEL_BRAND", "Haptica"),
        "cta_label": os.getenv("PMODEL_CTA_LABEL", "Book a site visit"),
        "cta_href": os.getenv("PMODEL_CTA_HREF", ""),
        "tagline": os.getenv("PMODEL_TAGLINE", "Explore this home in interactive 3D"),
    }
