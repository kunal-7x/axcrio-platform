"""V2-W6 router convergence check (offline): build the FULL ads surface (main /ads router with
autorun+llm+optimize sub-routers + the /ads/connect sibling), include into one FastAPI app, assert
a healthy route count and ZERO duplicate (method, path) pairs. Stub auth seams (no caller import)."""
import os
import sys

os.environ.setdefault("FEATURE_ADS", "1")

from fastapi import FastAPI, Response  # noqa: E402


def resolve_tenant(request):
    return {"tenant_id": "t_demo", "role": "manager", "is_admin": False}


def can(t, action):
    return True


def need_auth():
    return Response(status_code=401)


def forbidden(msg="forbidden"):
    return Response(content=msg, status_code=403)


def require_super_admin(request):
    return {"tenant_id": "t_admin", "is_admin": True}


def audit(request, t, action, object_type="campaign", object_id="", meta=None):
    return None


def auth_method(request):
    return "jwt"


def main():
    from ads_engine.endpoints import build_router
    from ads_engine.connect_routes import build_connect_router

    ads = build_router(resolve_tenant, can, need_auth, forbidden,
                       require_super_admin=require_super_admin, firewall=None,
                       audit=audit, auth_method=auth_method)
    assert ads is not None, "build_router returned None (FastAPI missing?)"
    connect = build_connect_router(resolve_tenant, can, need_auth, forbidden)

    app = FastAPI()
    app.include_router(ads)
    if connect is not None:
        app.include_router(connect)

    # Collect (method, path) pairs across every mounted route.
    seen = {}
    dupes = []
    pairs = 0
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None) or set()
        if not path or not path.startswith("/ads"):
            continue
        for m in methods:
            if m in ("HEAD", "OPTIONS"):
                continue
            pairs += 1
            key = (m, path)
            if key in seen:
                dupes.append(key)
            seen[key] = seen.get(key, 0) + 1

    # Prove every sub-router actually mounted by sampling a known path-prefix from each.
    paths = {p for (_m, p) in seen}
    have_autorun = any("/ads/autorun" in p or "/ads/autopilot" in p or "/ads/orchestr" in p for p in paths)
    have_llm = any("/ads/reasoning" in p or "/ads/llm" in p or "/ads/copy" in p or "/ads/brief" in p
                   or "/ads/adapt" in p or "/ads/slideshow" in p for p in paths)
    have_optimize = any("/ads/events" in p or "/ads/optimize" in p or "/ads/learning" in p
                        or "/ads/fatigue" in p or "/ads/audience" in p for p in paths)
    have_connect = any(p.startswith("/ads/connect") for p in paths)

    print(f"total /ads (method,path) pairs: {pairs}")
    print(f"unique paths: {len(paths)}")
    print(f"sub-router presence: autorun={have_autorun} llm={have_llm} "
          f"optimize={have_optimize} connect={have_connect}")
    if dupes:
        print("DUPLICATE (method,path) PAIRS:")
        for d in sorted(set(dupes)):
            print("  ", d)

    ok = (not dupes) and pairs > 0 and have_autorun and have_llm and have_optimize and have_connect
    print("RESULT:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
