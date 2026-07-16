#!/usr/bin/env python3
"""Idempotent, validate-before-write patcher that adds the Property Studio (pmodel)
integration to an ALREADY-DEPLOYED Haptica tree — WITHOUT overwriting/reverting any
other code on the box (grow, ai_manager, …). It only inserts at 4 stable anchors:

  1. droplet_work/caller.py            -> the FEATURE_PMODEL router mount (after media_gen)
  2. famit-panel/contstants/navigation.tsx -> the "Property Studio" sidebar entry
  3. famit-panel/app/providers.tsx     -> exempt /share/* from the login redirect
  4. famit-panel/package.json          -> the three/r3f/zustand deps

Each patch is SKIPPED if already applied (safe to re-run). caller.py is byte-compiled
after patching; if that fails the original is restored and the run aborts non-zero, so
a bad patch can never leave a broken backend. Usage:  python3 pmodel_patch.py /opt/haptica
"""
import json
import os
import re
import sys
import tempfile

APP = sys.argv[1] if len(sys.argv) > 1 else "."


def _read(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def _write(p, s):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p) or ".")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(s)
    os.replace(tmp, p)


CALLER_BLOCK = '''

# ==============================================================================================
# MODULE MOUNT — pmodel (2D -> 3D Property Studio, prefix /pmodel). FLAG-GATED, default OFF.
# ----------------------------------------------------------------------------------------------
# Additive: a missing module or disabled FEATURE_PMODEL flag is byte-identical to before.
try:
    from pmodel.router import build_router as _build_pmodel_router  # noqa: E402
except Exception:  # noqa: BLE001
    _build_pmodel_router = None

FEATURE_PMODEL = (cfg_get("FEATURE_PMODEL", "0") or "0").strip().lower() in ("1", "true", "yes", "on")

if FEATURE_PMODEL and _build_pmodel_router is not None:
    try:
        try:
            _pmodel_s3 = _aim_s3()
        except Exception:  # noqa: BLE001
            _pmodel_s3 = None
        _pmodel_router = _build_pmodel_router(
            resolve_tenant, can, need_auth, _forbidden,
            s3_client=_pmodel_s3,
            spaces_bucket=(cfg_get("AIM_SPACES_BUCKET", "") or "").strip(),
            presign=_rec_presign,
            audit=_audit,
        )
        if _pmodel_router is not None:
            app.include_router(_pmodel_router)
    except Exception:  # noqa: BLE001
        import logging as _lg_pmodel
        _lg_pmodel.getLogger("famit-caller").warning("pmodel router mount failed", exc_info=True)
'''

NAV_ENTRY = '''
    {
        // PROPERTY STUDIO — 2D floor plan -> interactive 3D property model + public share link.
        // UNKEYED (self-gates via the backend FEATURE_PMODEL flag → calm DormantCard when off).
        title: "Property Studio",
        icon: "cube",
        href: "/property-studio",
    },'''


def patch_caller(path):
    s = _read(path)
    if "FEATURE_PMODEL" in s:
        return "caller.py: already patched"
    anchor = '_lg_media.getLogger("famit-caller").warning("media_gen router mount failed", exc_info=True)'
    if anchor not in s:
        return "caller.py: SKIPPED — media_gen anchor not found (patch manually)"
    new = s.replace(anchor, anchor + CALLER_BLOCK, 1)
    # validate before writing — never leave a broken backend
    fd, tmp = tempfile.mkstemp(suffix=".py")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(new)
    import py_compile
    try:
        py_compile.compile(tmp, doraise=True)
    except Exception as e:  # noqa: BLE001
        os.unlink(tmp)
        raise SystemExit(f"caller.py: ABORT — patched file fails to compile ({e}); original untouched")
    os.unlink(tmp)
    _write(path, new)
    return "caller.py: PATCHED (pmodel mount added)"


def patch_nav(path):
    s = _read(path)
    if "Property Studio" in s:
        return "navigation.tsx: already patched"
    rx = re.compile(
        r'(\{\s*title:\s*"Brand Kit",\s*href:\s*"/creative/brand"\s*\},\s*\],\s*\},)'
    )
    if not rx.search(s):
        return "navigation.tsx: SKIPPED — Creative Studio anchor not found (add nav entry manually)"
    _write(path, rx.sub(lambda m: m.group(1) + NAV_ENTRY, s, count=1))
    return "navigation.tsx: PATCHED (Property Studio entry added)"


def patch_providers(path):
    s = _read(path)
    if 'startsWith("/share")' in s:
        return "providers.tsx: already patched"
    a1 = 'if (pathname === "/login" || pathname === "/signup") return;'
    a2 = 'const authed = pathname !== "/login" && pathname !== "/signup";'
    if a1 not in s or a2 not in s:
        return "providers.tsx: SKIPPED — AuthGuard anchors not found (add /share exemption manually)"
    s = s.replace(
        a1,
        'if (\n            pathname === "/login" ||\n            pathname === "/signup" ||\n'
        '            pathname.startsWith("/share")\n        )\n            return;',
        1,
    )
    s = s.replace(
        a2,
        'const authed =\n        pathname !== "/login" && pathname !== "/signup" && !pathname.startsWith("/share");',
        1,
    )
    _write(path, s)
    return "providers.tsx: PATCHED (/share exempted from auth)"


def patch_pkg(path):
    deps = {
        "@react-three/drei": "^10.7.7", "@react-three/fiber": "^9.6.1",
        "rc-slider": "^11.1.8", "react-hot-toast": "^2.5.2", "react-plock": "^3.5.1",
        "react-rnd": "^10.5.2", "three": "^0.171.0", "zustand": "^5.0.5",
    }
    pkg = json.loads(_read(path))
    d = pkg.setdefault("dependencies", {})
    added = [k for k in deps if k not in d]
    if not added:
        return "package.json: already has all deps"
    for k, v in deps.items():
        d.setdefault(k, v)
    pkg["dependencies"] = dict(sorted(d.items()))
    _write(path, json.dumps(pkg, indent=2) + "\n")
    return f"package.json: PATCHED (added {', '.join(added)})"


def main():
    jobs = [
        ("droplet_work/caller.py", patch_caller),
        ("famit-panel/contstants/navigation.tsx", patch_nav),
        ("famit-panel/app/providers.tsx", patch_providers),
        ("famit-panel/package.json", patch_pkg),
    ]
    for rel, fn in jobs:
        p = os.path.join(APP, rel)
        if not os.path.exists(p):
            print(f"  ! {rel}: NOT FOUND on box — skipped")
            continue
        print("  " + fn(p))
    print("pmodel patch complete.")


if __name__ == "__main__":
    main()
