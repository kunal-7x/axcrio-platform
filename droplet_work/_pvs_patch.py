#!/usr/bin/env python3
"""PVS Phase-1 patch — applies additive routes + field persistence to caller.py.

Idempotent: re-running is a no-op. NEVER touches agent.py/trunks/firewall/SIP. Edits ONLY caller.py.
Usage:  python3 _pvs_patch.py /opt/famit-agent/caller.py
"""
import sys, re

path = sys.argv[1]
src = open(path, encoding="utf-8").read()
orig = src

MARKER = "# === PVS PHASE-1 (provider+voice switcher) ==="
if MARKER in src:
    print("ALREADY_PATCHED")
    sys.exit(0)

# ───────────────────────────────────────────────────────────────────────────
# 1) Replace the /voices route (un-strip preview_url + accent/gender; ?provider=sarvam static)
#    and append B2 /voice-preview, B3 /providers, B6 /tiers right after it.
# ───────────────────────────────────────────────────────────────────────────
OLD_VOICES = '''@app.get("/voices")
async def voices(request: Request):
    if not authed(request):
        return need_auth()
    try:
        r = httpx.get("https://api.elevenlabs.io/v1/voices",
                      headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}, timeout=15)
        vs = [{"voice_id": v["voice_id"], "name": v["name"]} for v in r.json().get("voices", [])]
        return JSONResponse({"voices": vs})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"voices": [], "error": repr(exc)[:140]})'''

NEW_VOICES = '''# === PVS PHASE-1 (provider+voice switcher) === ADDITIVE; agent.py/trunks/firewall/SIP untouched.
# Sarvam Bulbul v2 fixed speaker catalogue (NO per-voice preview URL via API -> we pre-host a tiny
# one-time sample set under var/voice_samples/sarvam/<speaker>.mp3, served by /voice-preview).
_SARVAM_VOICES = [
    {"voice_id": "anushka", "name": "Anushka", "gender": "female", "accent": "Indian", "language": "Hindi/multi"},
    {"voice_id": "manisha", "name": "Manisha", "gender": "female", "accent": "Indian", "language": "Hindi/multi"},
    {"voice_id": "vidya",   "name": "Vidya",   "gender": "female", "accent": "Indian", "language": "Hindi/multi"},
    {"voice_id": "arya",    "name": "Arya",    "gender": "female", "accent": "Indian", "language": "Hindi/multi"},
    {"voice_id": "abhilash","name": "Abhilash","gender": "male",   "accent": "Indian", "language": "Hindi/multi"},
    {"voice_id": "karun",   "name": "Karun",   "gender": "male",   "accent": "Indian", "language": "Hindi/multi"},
    {"voice_id": "hitesh",  "name": "Hitesh",  "gender": "male",   "accent": "Indian", "language": "Hindi/multi"},
]
_VOICE_SAMPLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "var", "voice_samples")


def _sarvam_voice_list():
    out = []
    for v in _SARVAM_VOICES:
        d = dict(v)
        d["preview_url"] = ""  # served via the proxy below (pre-hosted local clip)
        d["sample_url"] = f"/voice-preview?provider=sarvam&id={v['voice_id']}"
        out.append(d)
    return out


@app.get("/voices")
async def voices(request: Request, provider: str = ""):
    """Voice catalogue per provider. ElevenLabs = live /v1/voices WITH the free public preview_url
    (un-stripped) + accent/gender. Sarvam = the fixed Bulbul v2 speaker catalogue + a sample_url that
    points at the pre-hosted clip proxy. FREE — no synthesis here."""
    if not authed(request):
        return need_auth()
    p = (provider or "").strip().lower()
    if p == "sarvam":
        return JSONResponse({"provider": "sarvam", "voices": _sarvam_voice_list()})
    # default + p in ("", "elevenlabs"): ElevenLabs live catalogue
    try:
        r = httpx.get("https://api.elevenlabs.io/v1/voices",
                      headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}, timeout=15)
        vs = []
        for v in r.json().get("voices", []):
            labels = v.get("labels") or {}
            vs.append({
                "voice_id": v.get("voice_id"),
                "name": v.get("name"),
                "preview_url": v.get("preview_url", ""),  # public GCS MP3, FREE (un-stripped)
                "accent": labels.get("accent", ""),
                "gender": labels.get("gender", ""),
                "language": labels.get("language", ""),
                "sample_url": f"/voice-preview?provider=elevenlabs&id={v.get('voice_id')}",
            })
        return JSONResponse({"provider": "elevenlabs", "voices": vs})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"provider": "elevenlabs", "voices": [], "error": repr(exc)[:140]})


@app.get("/voice-preview")
async def voice_preview(request: Request, provider: str = "", id: str = ""):
    """FREE play-preview proxy. ElevenLabs -> redirect to the voice's public preview_url (no key, no
    synthesis, no burn). Sarvam -> stream the pre-hosted one-time sample clip from
    var/voice_samples/sarvam/<id>.mp3. Used by the panel <audio> Play button."""
    if not authed(request):
        return need_auth()
    from fastapi.responses import RedirectResponse, FileResponse
    p = (provider or "").strip().lower()
    vid = (id or "").strip()
    if not vid:
        return JSONResponse({"error": "id required"}, status_code=400)
    if p == "sarvam":
        safe = "".join(ch for ch in vid if ch.isalnum() or ch in "-_")
        fp = os.path.join(_VOICE_SAMPLE_DIR, "sarvam", f"{safe}.wav")
        if os.path.isfile(fp):
            return FileResponse(fp, media_type="audio/wav", filename=f"sarvam-{safe}.wav")
        return JSONResponse({"error": "sample not available", "voice_id": vid}, status_code=404)
    # elevenlabs (default): look up the voice's public preview_url and 302 to it (FREE GCS MP3).
    try:
        r = httpx.get("https://api.elevenlabs.io/v1/voices",
                      headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]}, timeout=15)
        for v in r.json().get("voices", []):
            if v.get("voice_id") == vid:
                pu = (v.get("preview_url") or "").strip()
                if pu:
                    return RedirectResponse(pu)
                break
        return JSONResponse({"error": "no preview for this voice", "voice_id": vid}, status_code=404)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": repr(exc)[:140]}, status_code=502)


@app.get("/providers")
async def providers_list(request: Request):
    """Usable providers per role (built-in + custom) with kind + available(>=1 live key).
    Built-ins: their available-ness comes from the provider_pool (>=1 non-cooling key) for groq/
    sarvam; elevenlabs is available iff ELEVENLABS_API_KEY is set. Custom providers append from the
    isolated custom-provider store. Reuses _pk_get_pool / key availability — no new pool."""
    if not authed(request):
        return need_auth()

    def _builtin_available(name):
        try:
            if name == "elevenlabs":
                return bool((os.environ.get("ELEVENLABS_API_KEY") or "").strip())
            if _pk_get_pool is not None:
                pool = _pk_get_pool(name)
                if pool is not None:
                    return pool.available_count() > 0
            # fall back to env presence
            return bool((os.environ.get((name or "").upper() + "_API_KEY") or "").strip())
        except Exception:  # noqa: BLE001
            return False

    builtin = [
        {"id": "sarvam",     "name": "Sarvam",      "builtin": True, "kinds": ["stt", "tts"],
         "available": _builtin_available("sarvam")},
        {"id": "groq",       "name": "Groq",        "builtin": True, "kinds": ["llm"],
         "available": _builtin_available("groq")},
        {"id": "elevenlabs", "name": "ElevenLabs",  "builtin": True, "kinds": ["tts"],
         "available": _builtin_available("elevenlabs")},
        {"id": "sambanova",  "name": "SambaNova",   "builtin": True, "kinds": ["llm"],
         "available": _builtin_available("sambanova")},
        {"id": "openrouter", "name": "OpenRouter",  "builtin": True, "kinds": ["llm"],
         "available": _builtin_available("openrouter")},
    ]
    custom = []
    try:
        from llm_router import custom_providers as _cp
        for c in _cp.list_masked():
            custom.append({
                "id": c["id"], "name": c["name"], "builtin": False, "kinds": [c["kind"]],
                "kind": c["kind"], "model": c["model"], "base_url": c["base_url"],
                "enabled": c["enabled"], "available": c["available"], "masked": c["masked"],
            })
    except Exception:  # noqa: BLE001
        pass
    # group by role for convenience (UI's 3 per-role selects)
    by_role = {"stt": [], "llm": [], "tts": []}
    for prov in builtin + custom:
        for k in prov.get("kinds", []):
            if k in by_role:
                by_role[k].append({"id": prov["id"], "name": prov["name"],
                                   "builtin": prov["builtin"], "available": prov["available"]})
    return JSONResponse({"providers": builtin + custom, "by_role": by_role})


@app.get("/tiers")
async def tiers_route(request: Request):
    """SINGLE SOURCE OF TRUTH for the Lean/Standard/Premium tier system: the 3 preset triples +
    the per-component rate card + the cost-math the frontend cost-meter uses (client-side, zero
    burn). Mirrors llm_router/tiers.py."""
    if not authed(request):
        return need_auth()
    try:
        from llm_router import tiers as _tiers
        return JSONResponse(_tiers.tiers_payload())
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": repr(exc)[:140], "tiers": []}, status_code=500)
# === /PVS PHASE-1 voices/preview/providers/tiers ==='''

assert OLD_VOICES in src, "OLD_VOICES anchor not found"
src = src.replace(OLD_VOICES, NEW_VOICES, 1)

# ───────────────────────────────────────────────────────────────────────────
# 2) _coerce_fields: persist tier + per-role *_provider + custom_provider_id + budget_cap_inr +
#    est_avg_call_min + the resolved triple snapshot. Inject right before `return out`.
# ───────────────────────────────────────────────────────────────────────────
COERCE_ANCHOR = '''    out["variants"] = norm_var
    return out'''
COERCE_NEW = '''    out["variants"] = norm_var
    # === PVS PHASE-1: per-campaign provider+voice tier persistence (additive) ===
    # tier in {lean,standard,premium,custom}; default lean (== today's pipeline on outbound).
    _tier = str(out.get("tier", "") or "").strip().lower()
    if _tier not in ("lean", "standard", "premium", "custom"):
        _tier = "lean"
    out["tier"] = _tier
    # explicit per-role provider overrides (used when tier == custom, or as the resolved snapshot)
    for k in ("stt_provider", "llm_provider", "tts_provider", "custom_provider_id"):
        v = out.get(k)
        out[k] = str(v).strip() if v is not None else ""
    # est avg call minutes (for projected campaign spend in the UI; clamp sane)
    try:
        _eac = float(out.get("est_avg_call_min", 1.5))
        out["est_avg_call_min"] = round(min(30.0, max(0.1, _eac)), 2)
    except Exception:  # noqa: BLE001
        out["est_avg_call_min"] = 1.5
    # optional per-campaign budget cap in ₹ (blank/0 -> no cap; UI warn/estimate only in Phase 1)
    _cap = out.get("budget_cap_inr")
    if _cap in (None, "", 0, "0"):
        out["budget_cap_inr"] = ""
    else:
        try:
            out["budget_cap_inr"] = max(0, int(float(_cap)))
        except Exception:  # noqa: BLE001
            out["budget_cap_inr"] = ""
    # snapshot the resolved {stt,llm,tts,voice} triple so a later tiers.py edit never silently
    # rewrites an in-flight campaign. For tier==custom we snapshot the explicit overrides.
    try:
        from llm_router import tiers as _tiers_mod
        if _tier == "custom":
            out["tier_resolved"] = {
                "tier": "custom",
                "stt": {"provider": out.get("stt_provider", "")},
                "llm": {"provider": out.get("llm_provider", "")},
                "tts": {"provider": out.get("tts_provider", "")},
                "voice": {"voice_id": out.get("voice_id", "")},
            }
        else:
            _trip = _tiers_mod.resolve_triple(_tier)
            # let an explicitly chosen voice_id override the tier default voice in the snapshot
            if _trip and out.get("voice_id"):
                _trip.setdefault("voice", {})["voice_id"] = out.get("voice_id")
            out["tier_resolved"] = _trip or {}
    except Exception:  # noqa: BLE001
        out["tier_resolved"] = out.get("tier_resolved") or {}
    # === /PVS PHASE-1 ===
    return out'''

assert COERCE_ANCHOR in src, "COERCE_ANCHOR not found"
src = src.replace(COERCE_ANCHOR, COERCE_NEW, 1)

# ───────────────────────────────────────────────────────────────────────────
# 3) Custom-provider CRUD routes — append after the provider-keys/status route (end of that block).
#    Anchor on the status route's return so we insert right after it.
# ───────────────────────────────────────────────────────────────────────────
STATUS_ANCHOR = '''    return JSONResponse({"status": out})'''
CUSTOM_CRUD = '''    return JSONResponse({"status": out})


# === PVS PHASE-1: CUSTOM PROVIDER CRUD (super-admin gated; isolated store) ===
# Separate from the live provider key-store (which feeds the earner pool) — registering a custom
# provider here NEVER changes the earner pipeline. Routing an outbound call through a custom
# provider is PHASE-2 / OB-PROV (gated). Phase 1 = persist + list + delete + surface in /providers.
def _cp_store():
    try:
        from llm_router import custom_providers as _cp
        return _cp
    except Exception:  # noqa: BLE001
        return None


@app.get("/admin/custom-providers")
async def admin_custom_providers_list(request: Request):
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    cp = _cp_store()
    if cp is None:
        return JSONResponse({"error": "custom-provider store unavailable"}, status_code=503)
    return JSONResponse({"custom_providers": cp.list_masked()})


@app.post("/admin/custom-providers")
async def admin_custom_providers_add(request: Request, name: str = Form(...), kind: str = Form(...),
                                     base_url: str = Form(...), model: str = Form(...),
                                     key: str = Form("")):
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    cp = _cp_store()
    if cp is None:
        return JSONResponse({"error": "custom-provider store unavailable"}, status_code=503)
    try:
        res = cp.add(name, kind, base_url, model, key=key)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": "add failed", "detail": type(exc).__name__}, status_code=400)
    _audit(request, t, "custom_provider.add", "custom_provider", res.get("id", ""),
           channel="control", meta={"name": res.get("name"), "kind": res.get("kind"),
                                    "model": res.get("model")})
    return JSONResponse({"ok": True, **res})


@app.put("/admin/custom-providers/{cid}")
async def admin_custom_providers_update(request: Request, cid: str, enabled: str = Form(""),
                                        name: str = Form(""), base_url: str = Form(""),
                                        model: str = Form(""), key: str = Form("")):
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    cp = _cp_store()
    if cp is None:
        return JSONResponse({"error": "custom-provider store unavailable"}, status_code=503)
    en = None
    if str(enabled).strip() != "":
        en = str(enabled).strip().lower() in ("1", "true", "yes", "on", "enabled")
    res = cp.update(cid, enabled=en,
                    label=(name if str(name).strip() else None),
                    base_url=(base_url if str(base_url).strip() else None),
                    model=(model if str(model).strip() else None),
                    key=(key if str(key).strip() else None))
    if not res.get("ok"):
        return JSONResponse({"error": "custom provider not found", "id": cid}, status_code=404)
    _audit(request, t, "custom_provider.update", "custom_provider", cid, channel="control")
    return JSONResponse(res)


@app.delete("/admin/custom-providers/{cid}")
async def admin_custom_providers_delete(request: Request, cid: str):
    t = require_super_admin(request)
    if isinstance(t, JSONResponse):
        return t
    cp = _cp_store()
    if cp is None:
        return JSONResponse({"error": "custom-provider store unavailable"}, status_code=503)
    res = cp.delete(cid)
    if not res.get("deleted"):
        return JSONResponse({"error": "custom provider not found", "id": cid}, status_code=404)
    _audit(request, t, "custom_provider.delete", "custom_provider", cid, channel="control")
    return JSONResponse(res)
# === /PVS PHASE-1 custom-provider CRUD ==='''

assert STATUS_ANCHOR in src, "STATUS_ANCHOR not found"
# replace only the LAST occurrence of the status return (the provider-keys/status route)
idx = src.rfind(STATUS_ANCHOR)
src = src[:idx] + CUSTOM_CRUD + src[idx + len(STATUS_ANCHOR):]

assert src != orig, "no changes applied"
open(path, "w", encoding="utf-8").write(src)
print("PATCHED_OK bytes_added=%d" % (len(src) - len(orig)))
