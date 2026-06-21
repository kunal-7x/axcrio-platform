
    # ═══════════════════ R6b — TEAM (authorized-users) + PROFILE + PIN-RESET ═══════════════════
    # The panel "Team" card + Settings read/write these. Before R6b they 404'd, so the Team card went
    # DORMANT and its "Add" button was disabled ("does nothing"). All additive; tenant-scoped from the
    # TOKEN; reuse the same firewall PIN primitives (per-member subject) so a member's PIN never collides
    # with the tenant-level step-up PIN. team store = ai_manager.team (var/aim_team.jsonl, registry posture).

    @router.get("/authorized-users")
    def list_authorized_users(request: Request) -> dict:
        t = _require_tenant(request, "read")
        from . import team as _team
        return {"users": _team.list_users(t["tenant_id"])}

    @router.post("/authorized-users")
    def create_authorized_user(request: Request, body: dict = Body(...)) -> dict:
        t = _require_tenant(request, "write")
        from . import team as _team
        b = body or {}
        res = _team.create_user(
            tenant_id=t["tenant_id"],
            name=str(b.get("name", "") or ""),
            phone_number=str(b.get("phone_number", "") or b.get("phone", "") or ""),
            role=str(b.get("role", "operator") or "operator"),
            permissions=b.get("permissions") or b.get("grants"),
        )
        if not res.get("ok"):
            raise HTTPException(status_code=400, detail=res.get("reason", "bad_request"))
        try:
            _audit.execute(actor=t["tenant_id"], tenant_id=t["tenant_id"], session_id="team",
                           action="ai_manager.team.create", meta={"user_id": res.get("id", "")})
        except Exception:  # noqa: BLE001
            pass
        return res

    @router.patch("/authorized-users/{user_id}")
    def patch_authorized_user(request: Request, user_id: str, body: dict = Body(...)) -> dict:
        t = _require_tenant(request, "write")
        from . import team as _team
        res = _team.patch_user(user_id, tenant_id=t["tenant_id"], fields=body or {})
        if not res.get("ok"):
            raise HTTPException(status_code=404, detail=res.get("reason", "not_found"))
        return res

    @router.delete("/authorized-users/{user_id}")
    def delete_authorized_user(request: Request, user_id: str) -> dict:
        t = _require_tenant(request, "write")
        # deleting a teammate is destructive -> firewall step-up (pass-through when firewall off / no PIN).
        _require_step_up(request, t, "destructive")
        from . import team as _team
        res = _team.delete_user(user_id, tenant_id=t["tenant_id"])
        if not res.get("ok"):
            raise HTTPException(status_code=404, detail=res.get("reason", "not_found"))
        try:
            _audit.execute(actor=t["tenant_id"], tenant_id=t["tenant_id"], session_id="team",
                           action="ai_manager.team.delete", meta={"user_id": user_id})
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True}

    @router.post("/pin/reset/request")
    def pin_reset_request(request: Request, body: dict = Body(default={})) -> dict:
        """Admin-initiated PIN reset request. The OTP sender is DORMANT, so for an authenticated admin we
        treat this as an immediate authorize-to-reset (the next /pin/set with admin=true lands the new PIN).
        Returns ok so the panel proceeds to the new-PIN entry. manager+ write role."""
        t = _require_tenant(request, "write")
        uid = str((body or {}).get("user_id", "") or "")
        try:
            _audit.execute(actor=t["tenant_id"], tenant_id=t["tenant_id"], session_id="pin_reset",
                           action="ai_manager.pin.reset.request", meta={"user_id": uid})
        except Exception:  # noqa: BLE001
            pass
        # otp_sent:false signals the FE to collect the new PIN directly (admin reset path).
        return {"ok": True, "otp_sent": False}

    @router.post("/pin/reset/confirm")
    def pin_reset_confirm(request: Request, body: dict = Body(...)) -> dict:
        """Confirm a PIN reset: set the member's NEW PIN (admin path). The OTP `code` is accepted but not
        enforced while the sender is dormant. Sets the per-member firewall PIN. manager+ write role."""
        t = _require_tenant(request, "write")
        tid = t["tenant_id"]
        uid = str((body or {}).get("user_id", "") or "")
        new_pin = str((body or {}).get("pin", "") or "").strip()
        if not new_pin:
            # no PIN supplied -> just clear the lockout marker so the user can re-enrol.
            from . import team as _team
            _team.mark_pin_set(uid, tenant_id=tid) if uid else None
            return {"ok": True, "pin_set_at": None}
        from . import team as _team
        member = _team.get(uid, tenant_id=tid) if uid else None
        subject = _team.pin_subject(tid, uid) if member else tid
        try:
            import firewall as _fw
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=503, detail="firewall unavailable")
        res = _fw.set_pin(subject, new_pin)
        if not res.get("ok"):
            raise HTTPException(status_code=400, detail=res.get("reason", "bad_pin"))
        if member:
            _team.mark_pin_set(uid, tenant_id=tid)
        import datetime as _dt
        return {"ok": True, "pin_set_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}

    @router.get("/profile")
    def get_profile(request: Request) -> dict:
        t = _require_tenant(request, "read")
        from . import team as _team
        return _team.get_profile(t["tenant_id"])

    @router.put("/profile")
    def put_profile(request: Request, body: dict = Body(...)) -> dict:
        t = _require_tenant(request, "write")
        from . import team as _team
        res = _team.put_profile(t["tenant_id"], body or {})
        if not res.get("ok"):
            raise HTTPException(status_code=400, detail=res.get("reason", "bad_request"))
        return res
