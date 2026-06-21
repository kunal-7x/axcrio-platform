"""ai_manager.endpoints — additive FastAPI APIRouter for the dashboard to manage registered numbers and
review voice/chat sessions (spec §7). DEFINED-NOT-MOUNTED — caller.py wiring ships as an un-applied diff
(wiring/caller_endpoints.diff). The COMMAND CALL itself is LiveKit/chat, not HTTP; these are management.

IMPORT-SAFE: FastAPI is imported defensively. If FastAPI is absent, `router` is None and importing the
package still works (the offline test never needs HTTP). Auth reuses caller.resolve_tenant + caller.can
(lazy import) so we don't duplicate the auth model. Risky mutations require a firewall step-up.

Endpoint map (spec §7):
  POST /ai-manager/numbers              register a manager phone (sends ownership OTP)       manager+
  POST /ai-manager/numbers/{id}/verify  confirm ownership OTP -> verified                    manager+
  GET  /ai-manager/numbers              list registered numbers + grants + status            manager+
  GET  /ai-manager/numbers/lookup       caller-ID resolution hop (voice worker)              service token
  POST /ai-manager/numbers/{id}/grants  set per-number capability allow-list                 admin + step-up
  POST /ai-manager/numbers/{id}/revoke  revoke / lock a number                               admin + step-up
  POST /ai-manager/sessions             voice worker ships a completed session (PIN-masked)  service token
  GET  /ai-manager/sessions             list recent sessions (transcripts, PIN masked)       manager+
  GET  /ai-manager/status               dormancy/config snapshot                             manager+

TENANT SCOPING (P1): tenant_id is pinned from the AUTHENTICATED request (caller.resolve_tenant), NEVER a
body field. Every registry read is tenant-scoped in-code. /numbers/lookup and POST /sessions are
SERVICE-TOKEN endpoints (the voice worker acts cross-tenant under a service identity).
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

try:
    from fastapi import APIRouter, Request, HTTPException, Query, Body
except Exception:  # noqa: BLE001 — FastAPI absent (e.g. offline test env): router stays None.
    APIRouter = None  # type: ignore

from . import config as _config
from . import registry as _registry
from . import audit_bridge as _audit
from . import firewall_bridge as _firewall


# ---------------- lazy auth bridges into caller.py (never duplicate the auth model) ----------------
def _resolve_tenant(request: Any) -> Optional[dict]:
    try:
        import caller as _c
        return _c.resolve_tenant(request)
    except Exception:  # noqa: BLE001
        return None


def _can(tenant: dict, action: str) -> bool:
    try:
        import caller as _c
        if hasattr(_c, "can"):
            return bool(_c.can(tenant, action))
    except Exception:  # noqa: BLE001
        pass
    # conservative fallback (never widens beyond caller.can semantics)
    role = (tenant or {}).get("role") or ("admin" if (tenant or {}).get("is_admin") else "")
    if action == "manage_tenants":
        return role == "admin"
    if action == "write":
        return role in ("admin", "manager")
    return True


def _service_token_ok(request: Any) -> bool:
    """The voice worker authenticates with AIM_SERVICE_TOKEN (bearer). DORMANT-until-set => always False
    (the live registry/lookup hop is part of the deferred cross-plane voice wire). NEVER raises."""
    expected = os.environ.get("AIM_SERVICE_TOKEN", "").strip()
    if not expected:
        return False
    import secrets as _secrets
    try:
        auth = request.headers.get("authorization", "") or request.headers.get("Authorization", "")
        presented = auth.split(" ", 1)[1].strip() if " " in auth else auth.strip()
    except Exception:  # noqa: BLE001
        presented = ""
    return bool(presented) and _secrets.compare_digest(presented, expected)


# ---------------- the router (None when FastAPI absent) ----------------
if APIRouter is not None:
    router = APIRouter(prefix="/ai-manager", tags=["ai-manager"])

    def _require_tenant(request: Request, action: str = "read") -> dict:
        t = _resolve_tenant(request)
        if not t:
            raise HTTPException(status_code=401, detail="unauthenticated")
        if not _can(t, action):
            raise HTTPException(status_code=403, detail="forbidden")
        return t

    def _require_step_up(request: Request, tenant: dict, scope: str) -> None:
        """Reuse the firewall guard. Pass-through when the firewall is OFF / tenant has no PIN (mirrors
        firewall.require_step_up). Raises 403 when a gated action lacks a valid step-up."""
        try:
            import firewall as _fw
            _fw.require_step_up(request, scope, tenant)  # returns None or raises StepUpDenied
        except Exception as exc:  # noqa: BLE001
            body = getattr(exc, "body", None)
            status = getattr(exc, "status", None)
            if body is not None and status is not None:
                raise HTTPException(status_code=status, detail=body)
            # firewall absent => pass-through (do not block when the gate isn't available)

    @router.get("/status")
    def status(request: Request) -> dict:
        _require_tenant(request, "read")
        from . import status as _pkg_status
        return _pkg_status()

    @router.get("/live")
    def live_calls(request: Request) -> dict:
        """ACTIVE inbound voice calls right now (cross-process, read off the file-backed
        live_registry the voice worker writes). Tenant-scoped from the TOKEN (admin sees all). Each
        item: {room, caller, mode(manager/customer), started, state, handoff(none/Requested/Dialing/
        Bridged/Failed), handoff_target}. Degrade-safe: returns [] if the registry module is absent.
        manager+ read role."""
        t = _require_tenant(request, "read")
        try:
            from . import live_registry as _live
        except Exception:  # noqa: BLE001 — module absent -> no live visibility, never an error.
            return {"calls": [], "count": 0}
        try:
            calls = _live.list_active(
                tenant_id=t.get("tenant_id", ""), is_admin=bool(t.get("is_admin")))
        except Exception:  # noqa: BLE001
            calls = []
        # don't leak the internal tenant_id key to non-admins (room/caller are enough for the panel).
        if not t.get("is_admin"):
            for c in calls:
                c.pop("tenant_id", None)
        return {"calls": calls, "count": len(calls)}

    @router.post("/numbers")
    def register_number(request: Request, body: dict = Body(...)) -> dict:
        t = _require_tenant(request, "write")
        res = _registry.register(
            tenant_id=t["tenant_id"], phone=(body or {}).get("phone", ""),
            label=(body or {}).get("label", ""), role=(body or {}).get("role", "manager"),
            verify_mode=(body or {}).get("verify_mode", "voice_pin"),
            grants=(body or {}).get("grants"), registered_by=t.get("tenant_id", ""))
        if not res.get("ok"):
            raise HTTPException(status_code=400, detail=res.get("reason", "bad_request"))
        # ownership OTP send is DORMANT (otp.sender) — number stays verified=False until /verify.
        from .otp import sender as _otp
        res["otp"] = _otp.send(res["phone"])
        return res

    @router.post("/numbers/{number_id}/verify")
    def verify_number(request: Request, number_id: str, body: dict = Body(default={})) -> dict:
        t = _require_tenant(request, "write")
        # OTP verification is DORMANT (firewall/otp). When live, verify the code BEFORE marking verified.
        res = _registry.mark_verified(number_id, tenant_id=t["tenant_id"])
        if not res.get("ok"):
            raise HTTPException(status_code=404, detail="not_found")
        return res

    @router.get("/numbers")
    def list_numbers(request: Request) -> dict:
        t = _require_tenant(request, "read")
        return {"numbers": _registry.list_numbers(t["tenant_id"])}

    @router.get("/numbers/lookup")
    def lookup_number(request: Request, phone: str = Query(...)) -> dict:
        # SERVICE-TOKEN endpoint (the voice worker). DORMANT until AIM_SERVICE_TOKEN is set.
        if not _service_token_ok(request):
            raise HTTPException(status_code=401, detail="service token required")
        row = _registry.lookup(phone)
        if not row:
            raise HTTPException(status_code=404, detail="not_registered")
        return row

    @router.post("/numbers/{number_id}/grants")
    def set_grants(request: Request, number_id: str, body: dict = Body(...)) -> dict:
        t = _require_tenant(request, "manage_tenants")
        _require_step_up(request, t, "destructive")
        res = _registry.set_grants(number_id, tenant_id=t["tenant_id"],
                                   grants=(body or {}).get("grants", []))
        if not res.get("ok"):
            raise HTTPException(status_code=404, detail="not_found")
        return res

    @router.post("/numbers/{number_id}/revoke")
    def revoke_number(request: Request, number_id: str) -> dict:
        t = _require_tenant(request, "manage_tenants")
        _require_step_up(request, t, "destructive")
        res = _registry.revoke(number_id, tenant_id=t["tenant_id"])
        if not res.get("ok"):
            raise HTTPException(status_code=404, detail="not_found")
        return res

    # ───────────────────────── PIN management (R5P4-4) ─────────────────────────
    # The panel AI-Manager calls POST /ai-manager/pin/set {user_id, pin, admin} to set the action PIN
    # that gates risky (money/destructive/bulk) AI-Manager commands. Before this route existed the panel
    # got a 404 (FastAPI then surfaced a generic error / the FE saw a 422). The PIN is the firewall's
    # TENANT-scoped step-up PIN (per-tenant salted hash, the same secret require_step_up checks); the
    # `user_id`/`admin` fields are accepted (so no 422) and recorded for audit. Writers only (manager+).
    # The raw PIN is consumed in-memory and NEVER echoed/logged.
    @router.post("/pin/set")
    def pin_set(request: Request, body: dict = Body(...)) -> dict:
        t = _require_tenant(request, "write")
        tid = t["tenant_id"]
        pin = str((body or {}).get("pin", "") or "").strip()
        user_id = str((body or {}).get("user_id", "") or "")
        if not pin:
            raise HTTPException(status_code=400, detail="pin required")
        try:
            import firewall as _fw
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=503, detail="firewall unavailable")
        res = _fw.set_pin(tid, pin)
        if not res.get("ok"):
            raise HTTPException(status_code=400, detail=res.get("reason", "bad_pin"))
        try:
            _audit.execute(actor=tid, tenant_id=tid, session_id="pin_set",
                           action="ai_manager.pin.set", meta={"user_id": user_id})
        except Exception:  # noqa: BLE001
            pass
        import datetime as _dt
        return {"ok": True, "pin_set_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}

    @router.post("/pin/verify")
    def pin_verify(request: Request, body: dict = Body(...)) -> dict:
        """Verify a PIN against the tenant store (never echoes the raw PIN). manager+ read role."""
        t = _require_tenant(request, "read")
        tid = t["tenant_id"]
        pin = str((body or {}).get("pin", "") or "").strip()
        try:
            import firewall as _fw
            ok = bool(_fw.check_pin(tid, pin))
        except Exception:  # noqa: BLE001
            ok = False
        return {"ok": ok}

    @router.post("/sessions")
    def ship_session(request: Request, body: dict = Body(...)) -> dict:
        # SERVICE-TOKEN endpoint (the voice worker ships a completed, PIN-masked session). DORMANT.
        if not _service_token_ok(request):
            raise HTTPException(status_code=401, detail="service token required")
        rec = _sanitize_session(body or {})
        _append_session(rec)
        return {"ok": True, "session_id": rec.get("session_id", "")}

    @router.get("/sessions")
    def list_sessions(request: Request, limit: int = Query(default=50),
                      offset: int = Query(default=0), channel: str = Query(default=""),
                      status: str = Query(default="")) -> dict:
        """List recent AI-Manager call/chat sessions for the AUTHENTICATED tenant (token-scoped, RLS).
        Source of truth = the PG ai_manager_sessions table; falls back to the JSONL mirror only when PG
        is unavailable (degrade). PIN/OTP digits are never present (masked upstream)."""
        t = _require_tenant(request, "read")
        tid = t["tenant_id"]
        try:
            from . import store as _store
            if _store.available():
                rows = _store.list_sessions(tid, limit=limit, offset=offset,
                                            channel=channel, status=status)
                return {"sessions": [_jsonify(r) for r in rows], "source": "pg"}
        except Exception:  # noqa: BLE001
            pass
        # degrade: JSONL mirror (older sessions / PG-down)
        return {"sessions": _read_sessions(tid, limit=limit), "source": "jsonl"}

    @router.get("/sessions/{session_id}")
    def get_session(request: Request, session_id: str) -> dict:
        """Full detail for one session: header + ordered transcript turns + the commands executed +
        a freshly-minted presigned recording URL (when a recording exists). Token-scoped + RLS — a
        tenant can only read its OWN sessions (a cross-tenant id 404s under the policy). NEVER leaks
        secrets (none are stored)."""
        t = _require_tenant(request, "read")
        tid = t["tenant_id"]
        row = None
        try:
            from . import store as _store
            if _store.available():
                row = _store.get_session(tid, session_id)
        except Exception:  # noqa: BLE001
            row = None
        if not row:
            # degrade: try the JSONL mirror by session_id
            for r in _read_sessions(tid, limit=500):
                if r.get("session_id") == session_id or r.get("id") == session_id:
                    return {"session": r, "source": "jsonl"}
            raise HTTPException(status_code=404, detail="session not found")
        # FINALIZE-ON-READ (self-heal): the agent's hangup-time stop()->set_recording write is a
        # fire-and-forget coroutine that often loses the race vs worker teardown, leaving the row stuck at
        # status='recording'/duration_s=0 even though the egress COMPLETED and the full OGG is in Spaces.
        # When the row still looks un-finalized but carries an egress id, ask LiveKit ListEgress for the
        # authoritative terminal state + real duration/key and persist it. Best-effort; NEVER raises.
        try:
            eg = (row.get("recording_egress_id", "") or "").strip()
            rstat = (row.get("recording_status", "") or "").strip()
            rdur = int(row.get("recording_duration_s", 0) or 0)
            if eg and (rstat not in ("uploaded", "failed", "disabled") or rdur <= 0):
                from . import recorder as _recorder
                fin = _recorder.finalize(eg)
                if fin.get("complete"):
                    new_key = (fin.get("key", "") or "") or (row.get("recording_key", "") or "")
                    new_dur = int(fin.get("duration_s", 0) or 0)
                    try:
                        from . import store as _store2
                        _store2.set_recording(
                            tid, session_id, status="uploaded",
                            key=new_key, duration_s=new_dur)
                    except Exception:  # noqa: BLE001
                        pass
                    # reflect the reconciled values on the row returned to the panel this request
                    row["recording_status"] = "uploaded"
                    if new_key:
                        row["recording_key"] = new_key
                    if new_dur > 0:
                        row["recording_duration_s"] = new_dur
                elif fin.get("status") == "failed":
                    try:
                        from . import store as _store2
                        _store2.set_recording(tid, session_id, status="failed")
                    except Exception:  # noqa: BLE001
                        pass
                    row["recording_status"] = "failed"
        except Exception:  # noqa: BLE001
            pass
        # mint a short-lived presigned URL for the recording object (if any). Falls back to '' when boto3
        # is absent — the panel then shows "recorded, link unavailable" instead of a broken player.
        rec_url = ""
        try:
            bucket = row.get("recording_bucket", "") or ""
            key = row.get("recording_key", "") or ""
            if bucket and key:
                from . import recorder as _recorder
                rec_url = _recorder.presign(bucket, key, expires_s=3600)
        except Exception:  # noqa: BLE001
            rec_url = ""
        out = _jsonify(row)
        out["recording_presigned_url"] = rec_url
        # never expose the raw Spaces creds-derived snapshot URL if it was a public one we don't want cached
        return {"session": out, "source": "pg"}

    _TEST_CMDS: dict = {}

    def _aim_risk_to_int(risk: str) -> int:
        return {"safe": 0, "bulk": 3, "money": 3, "destructive": 3}.get(risk or "safe", 0)

    def _aim_action_type(tool: str, risk: str) -> str:
        if risk in ("money",):
            return "money"
        if risk in ("destructive",):
            return "destructive"
        if risk in ("bulk",):
            return "write"
        if (tool or "").endswith(".read") or ".read" in (tool or ""):
            return "read"
        return "write"

    # Friendly, business-tone labels per tool so the success/failure line reads like a human assistant,
    # NEVER raw JSON or a bare tool-scope string (founder ask: Hinglish-friendly business tone).
    _TOOL_LABEL = {
        "analytics.read": "aaj ka performance report", "leads.read": "leads ki list",
        "wallet.read": "wallet balance", "billing.read": "billing summary",
        "leads.enqueue_calls": "calls", "whatsapp.send": "WhatsApp message",
        "ads.set_budget": "ad budget update", "ads.create_campaign": "ad campaign",
        "ads.pause": "ads pause", "campaigns.create": "campaign",
        "creative.generate_banner": "ad banner", "creative.generate_brochure": "brochure",
        "creative.generate_video": "video creative", "booking.create": "booking",
        "booking.reschedule": "booking reschedule", "booking.cancel": "booking cancel",
        "workflow.create_draft": "workflow draft", "workflow.activate": "workflow",
        "workflow.run_now": "workflow run",
    }
    # human reason for an honest no-op (a module that isn't switched on yet, etc.)
    _REASON_HUMAN = {
        "not_configured": "yeh module abhi aapke account par on nahi hai",
        "unknown_tool": "yeh action abhi available nahi hai",
        "insufficient_credits": "wallet me credits kam hai",
        "no_funds": "wallet me credits kam hai",
        "campaign_id_required": "pehle ek campaign select karna hoga",
        "exec_error": "ek technical dikkat aa gayi",
        "transport_dormant": "service abhi reachable nahi hai",
        "transport_error": "service abhi reachable nahi hai",
        "spend": "is spend ke liye extra approval pending hai",
        "bulk": "itne bade batch ke liye approval pending hai",
        "destructive": "is action ke liye extra approval pending hai",
        "tool_failed": "yeh action complete nahi ho paaya",
    }

    def _aim_human_outcome(tool: str, effective: bool, reason: str) -> str:
        """Build the human, Hinglish-friendly success/failure sentence the chat renders verbatim."""
        label = _TOOL_LABEL.get(tool, tool or "yeh action")
        if effective:
            if (tool or "").endswith(".read") or ".read" in (tool or ""):
                return f"Ho gaya — {label} ready hai, neeche dekh lijiye."
            return f"Done! {label} successfully ho gaya."
        # normalize reasons like "transport_error:ConnectionError" -> "transport_error"
        rkey = (reason or "").split(":", 1)[0].strip()
        why = _REASON_HUMAN.get(rkey, "")
        if why:
            return f"Abhi {label} nahi ho paaya — {why}. Main ise fix hone par bata dungi."
        return f"Abhi {label} nahi ho paaya. Thodi der baad try karein ya support se poochein."

    def _scrub_read_data(data: dict) -> dict:
        """Drop internal/transport keys from a read payload before returning it to the chat UI."""
        if not isinstance(data, dict):
            return {}
        drop = {"ok", "actual_spend_minor", "outcome", "tools_ok", "tools_failed", "last_reason"}
        return {k: v for k, v in data.items() if k not in drop}

    # ───────────────────── R5P4-4: LLM-DRIVEN free-form "Try it" answerer ─────────────────────
    # The panel "Try it" box must answer ANY natural question (not just the closed command schema) with a
    # natural sentence — NEVER leaking tool jargon ("analytics.read" / "channel.target"). We ground the
    # LLM in the SAME live numbers the dashboard shows (caller._AIM_LIVE: report totals + hot leads +
    # campaign rollup) so the answer is REAL, never hallucinated, and can't diverge from the KPIs. Falls
    # back cleanly (returns None) when the LLM/key/data is unavailable -> the deterministic card still runs.
    _AIM_TRYIT_LLM = (os.environ.get("AIM_TRYIT_LLM", "1") or "1").strip().lower() in ("1", "true", "yes", "on")

    def _aim_live_snapshot(tid: str) -> dict:
        """Pull the tenant's live data the SAME way /report does (token-scoped). Best-effort -> {}.

        Reads caller._REPSVC (the ReportingService that backs /report) directly — NOT _AIM_LIVE, which
        only exposes handle()/daily_summary(), not report()/hot_leads(). The shared read-model is already
        hydrated by the async caller (commands_test awaits _w14_hydrate on the MAIN loop before this runs).
        """
        snap: dict = {}
        try:
            import caller as _c
            svc = getattr(_c, "_REPSVC", None)
            if svc is None:
                return {}
            try:
                rep = svc.report(tid, "today") or {}
                if isinstance(rep, dict):
                    snap["today_totals"] = rep.get("totals", {})
            except Exception:  # noqa: BLE001
                pass
            try:
                rows = svc.hot_leads(tid, "today", limit=10) or []
                snap["hot_leads"] = [
                    {k: r.get(k) for k in ("name", "phone_masked", "campaign_id", "summary",
                                           "next_action", "conversion_prob", "booked")}
                    for r in rows[:10] if isinstance(r, dict)
                ]
            except Exception:  # noqa: BLE001
                snap["hot_leads"] = []
            try:
                rep7 = svc.report(tid, "7d") or {}
                if isinstance(rep7, dict):
                    snap["week_totals"] = rep7.get("totals", {})
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            return {}
        return snap

    def _aim_llm_answer(tenant: dict, text: str) -> Optional[dict]:
        """Answer a free-form question with the LLM, grounded in live data. Returns a §22-shaped read
        card with a NATURAL user_facing_summary (no jargon), or None to defer to the deterministic path.
        Reuses the intent driver's Groq client (round-robin key + configured model). NEVER raises."""
        if not _AIM_TRYIT_LLM:
            return None
        try:
            from .intent import driver as _intent
            # only when a real LLM provider+key is live (AIM_LLM_PROVIDER=groq is set on the box).
            if not getattr(_intent, "is_configured", lambda: False)():
                return None
            call_groq = getattr(_intent, "_call_groq", None)
            if call_groq is None:
                return None
        except Exception:  # noqa: BLE001
            return None
        tid = tenant.get("tenant_id", "")
        snap = _aim_live_snapshot(tid)
        sys_prompt = (
            "You are the Famit AI Manager assistant for a business owner. Answer the owner's question in "
            "ONE or two short, natural sentences (Hinglish is fine, like a helpful Indian operations "
            "manager). Use ONLY the numbers in LIVE_DATA — never invent figures. If LIVE_DATA does not "
            "contain the answer, say so plainly and suggest what they can ask. NEVER mention internal "
            "tool names, intents, code, scopes, or words like 'analytics.read' or 'channel.target'. "
            "Return STRICT JSON: {\"answer\": \"<natural reply>\"}."
        )
        user_prompt = ("LIVE_DATA (this tenant, real-time):\n" + json.dumps(snap, ensure_ascii=False,
                                                                            default=str)[:4000]
                       + "\n\nOWNER'S QUESTION:\n" + (text or "")[:600])
        try:
            out = call_groq([{"role": "system", "content": sys_prompt},
                             {"role": "user", "content": user_prompt}])
        except Exception:  # noqa: BLE001
            out = None
        if not isinstance(out, dict):
            return None
        answer = str(out.get("answer", "") or "").strip()
        if not answer:
            return None
        return {
            "command_id": "tc_" + os.urandom(6).hex(), "intent": "", "action_type": "read",
            "confidence": 0.9, "risk_level": 0, "requires_confirmation": False,
            "requires_pin": False, "entities": {}, "missing_fields": [], "assumptions": [],
            "user_facing_summary": answer, "data": _scrub_read_data(snap),
            "executed": True, "safe_to_execute": True, "block_reason": None, "status": "executed",
        }

    def _aim_parse_card(tenant: dict, text: str, channel: str = "dashboard") -> dict:
        """Run ONE turn through the deterministic brain and build the §22 parse card. Pure
        classification + extraction — NEVER executes a side effect. NEVER raises."""
        from .intent import driver as _intent
        from . import delegate as _delegate
        from . import identity as _identity
        tid = tenant.get("tenant_id", "")
        role = tenant.get("role") or ("admin" if tenant.get("is_admin") else "operator")
        try:
            ctx = _delegate.read_context(tid)
        except Exception:  # noqa: BLE001
            ctx = {}
        match = _intent.parse_intent(text or "", ctx) or {}
        kind = match.get("kind", "clarify")
        intent_name = match.get("intent", "") or ""
        reason = match.get("reason", "") or ""
        conf = float(match.get("confidence", 0.0) or 0.0)
        cmd_id = "tc_" + os.urandom(6).hex()

        # ALWAYS-BLOCK (secrets / compliance-bypass) — the keyword brain flagged it; the policy
        # engine is final authority and refuses. NEVER executes.
        if reason.startswith("blocked:"):
            br = reason.split(":", 1)[1]
            card = {
                "command_id": cmd_id, "intent": "", "action_type": "blocked",
                "confidence": conf, "risk_level": 4, "requires_confirmation": False,
                "requires_pin": False, "entities": {}, "missing_fields": [], "assumptions": [],
                "user_facing_summary": ("I can't reveal credentials." if br == "reveal_secret"
                                        else "I can't bypass DND/consent/compliance — that's never allowed."),
                "safe_to_execute": False, "block_reason": br, "status": "blocked",
            }
            try:
                _audit.permission_denied(actor=tid, tenant_id=tid, session_id=cmd_id, action="blocked:" + br)
            except Exception:  # noqa: BLE001
                pass
            return card

        # R5P4-4: LLM-DRIVEN natural answer for ANY read/ambiguous question (NOT a concrete write command).
        # This replaces the jargon-leaking "Read-only query (analytics.read)" / "couldn't catch that" reply
        # with a real, natural sentence grounded in the tenant's live numbers. Write commands (kind ==
        # 'command') are NOT intercepted -> they keep the deterministic confirm/PIN/execute safety flow.
        if kind in ("query", "clarify"):
            _llm_card = _aim_llm_answer(tenant, text)
            if _llm_card is not None:
                return _llm_card

        if kind == "clarify":
            return {
                "command_id": cmd_id, "intent": "", "action_type": "read", "confidence": conf,
                "risk_level": 0, "requires_confirmation": False, "requires_pin": False,
                "entities": dict(match.get("slots", {}) or {}), "missing_fields": ["intent"],
                "assumptions": [], "user_facing_summary": "I didn't quite catch a clear action — could you rephrase?",
                "safe_to_execute": False, "block_reason": None, "status": "needs_clarification",
            }

        if kind == "goodbye":
            return {
                "command_id": cmd_id, "intent": "", "action_type": "read", "confidence": 1.0,
                "risk_level": 0, "requires_confirmation": False, "requires_pin": False,
                "entities": {}, "missing_fields": [], "assumptions": [],
                "user_facing_summary": "Okay — anything else?", "safe_to_execute": True,
                "block_reason": None, "status": "ok",
            }

        if kind == "query":
            # READ-ONLY analytics/wallet/booking query. Reads are safe (no PIN, no spend, idempotent),
            # so we EXECUTE the read inline and return REAL data + a human summary. The workforce runner
            # hits the live GET route (/analytics, /wallet, /leads, ...) under the per-run RLS token.
            read_action = _delegate.map_intent_to_action(match)
            read_tool = read_action.get("tool", "") or intent_name
            data: dict = {}
            ran = False
            try:
                tenant_dict = {"tenant_id": tid, "role": role, "is_admin": bool(tenant.get("is_admin"))}
                res = _delegate.execute(tid, read_action, tenant_dict=tenant_dict, actor=tid,
                                        is_admin=bool(tenant.get("is_admin")))
                ran = bool(res.get("effective"))
                data = res.get("data", {}) or {}
                read_reason = res.get("last_reason", "") or ""
            except Exception:  # noqa: BLE001
                read_reason = "exec_error"
            # R5P4-4: never leak the tool/intent jargon to the user. A natural, human fallback line.
            summary = (_aim_human_outcome(read_tool, ran, read_reason) if (ran or read_tool) else
                       "Let me check that for you — could you say it a little differently?")
            return {
                "command_id": cmd_id, "intent": "", "action_type": "read",
                "confidence": conf, "risk_level": 0, "requires_confirmation": False,
                "requires_pin": False, "entities": dict(match.get("slots", {}) or {}),
                "missing_fields": [], "assumptions": [],
                "user_facing_summary": summary, "data": _scrub_read_data(data),
                "executed": ran, "safe_to_execute": True, "block_reason": None,
                "status": ("executed" if ran else "ready"),
            }

        # kind == "command": map to a concrete action + DETERMINISTIC risk (model's risk ignored).
        action = _delegate.map_intent_to_action(match)
        tool = action.get("tool", "") or intent_name
        risk = action.get("risk", "safe")
        risky = _identity.is_risky(tool)

        # ---- S4.5 ELICIT (multi-turn slot-filling, chat path) ----
        # If the command arrived HALF-SPECIFIED (missing required slots), DON'T fail/clarify — hold it as
        # a PendingCommand in _TEST_CMDS and ask the single most-important missing slot. The follow-up
        # POST /commands/{id}/slot merges the reply and loops until complete, then the SAME command_id
        # becomes a normal needs_confirmation/needs_pin card. (Voice gets this via state_machine S4.5.)
        outstanding = list(match.get("missing_fields")
                           or _intent.missing_required(tool, action.get("args", {})))
        if outstanding:
            nxt = outstanding[0]
            if len(_TEST_CMDS) > 500:
                _TEST_CMDS.clear()
            _TEST_CMDS[cmd_id] = {"tenant_id": tid, "role": role, "action": action, "tool": tool,
                                  "risk": risk, "risky": risky, "permitted": None,
                                  "pending": True, "outstanding": outstanding,
                                  "ask_count": 0, "ctx": ctx}
            return {
                "command_id": cmd_id, "intent": tool,
                "action_type": _aim_action_type(tool, risk), "confidence": conf,
                "risk_level": _aim_risk_to_int(risk), "requires_confirmation": False,
                "requires_pin": False, "entities": dict(action.get("args", {}) or {}),
                "missing_fields": outstanding, "assumptions": [],
                "user_facing_summary": _intent.slot_question(nxt),
                "prompt": _intent.slot_question(nxt), "next_slot": nxt,
                "safe_to_execute": False, "block_reason": None, "status": "eliciting",
            }
        return _finalize_command_card(tid, role, tenant, cmd_id, action, tool, risk, risky, conf)

    def _finalize_command_card(tid, role, tenant, cmd_id, action, tool, risk, risky, conf):
        """Build the terminal command card (needs_confirmation / needs_pin / denied) once every required
        slot is filled, and cache the executable command under cmd_id for the follow-up confirm/execute.
        Shared by the single-shot parse AND the end of the multi-turn ELICIT loop. NEVER raises."""
        from . import identity as _identity
        # read-back summary now NAMES the filled slots (campaign/segment/budget) so the user confirms a
        # concrete action, not a bare tool string.
        permitted = _identity.permits(role, tenant.get("grants", []) or
                                      ["analytics", "leads", "campaigns", "ads", "workflow",
                                       "booking", "creative", "wallet"], tool)
        readback = _aim_readback(tool, action.get("args", {}) or {}, risk, risky)
        card = {
            "command_id": cmd_id, "intent": tool, "action_type": _aim_action_type(tool, risk),
            "confidence": conf, "risk_level": _aim_risk_to_int(risk),
            "requires_confirmation": True, "requires_pin": bool(risky),
            "entities": dict(action.get("args", {}) or {}), "missing_fields": [], "assumptions": [],
            "user_facing_summary": readback,
            "safe_to_execute": bool(permitted), "block_reason": None,
            "status": ("needs_pin" if risky else "needs_confirmation"),
        }
        if not permitted:
            card["safe_to_execute"] = False
            card["status"] = "denied"
            card["block_reason"] = "permission_denied"
            card["user_facing_summary"] = f"You're not permitted to run {tool}."
        # cache for the follow-up confirm/execute (replaces any pending entry under this id)
        if len(_TEST_CMDS) > 500:
            _TEST_CMDS.clear()
        _TEST_CMDS[cmd_id] = {"tenant_id": tid, "role": role, "action": action, "tool": tool,
                              "risk": risk, "risky": risky, "permitted": permitted, "pending": False}
        return card

    def _aim_readback(tool, args, risk, risky):
        """A concrete, slot-naming confirm read-back ('Confirm: call the hot leads in Codename Joy?')."""
        label = _TOOL_LABEL.get(tool, tool)
        camp = args.get("campaign") or args.get("campaign_id") or ""
        seg = args.get("segment") or ""
        bits = []
        if camp:
            bits.append(f"campaign \"{camp}\"")
        if seg:
            bits.append(f"{seg} leads")
        if args.get("budget_minor"):
            try:
                bits.append(f"₹{int(args['budget_minor'])/100:,.0f}/day")
            except Exception:  # noqa: BLE001
                pass
        detail = (" — " + ", ".join(bits)) if bits else ""
        tail = (" Aapka PIN chahiye hoga." if risky else " Confirm karein?")
        return f"Confirm: {label}{detail}.{tail}"

    @router.post("/commands/test")
    async def commands_test(request: Request, body: dict = Body(...)) -> dict:
        t = _require_tenant(request, "write")
        text = (body or {}).get("text", "") or ""
        channel = (body or {}).get("channel", "dashboard") or "dashboard"
        # R5P4-4: hydrate the SHARED reporting read-model on the MAIN loop FIRST (same as /report + the
        # W14b /ai-manager/report route) so the LLM-driven answer below reads REAL live numbers, never the
        # empty split-brain copy. Best-effort — a hydrate miss just yields a leaner snapshot. Never raises.
        try:
            import caller as _c
            _hyd = getattr(_c, "_w14_hydrate", None)
            if _hyd is not None:
                await _hyd(t.get("tenant_id", ""))
        except Exception:  # noqa: BLE001
            pass
        return _aim_parse_card(t, text, channel)

    @router.post("/commands/{command_id}/slot")
    def commands_slot(request: Request, command_id: str, body: dict = Body(...)) -> dict:
        """S4.5 ELICIT (chat path): supply the user's answer to the slot we asked. Merge it into the held
        PendingCommand (re-parse JUST that slot, never the whole command), re-check the outstanding list,
        and either ask the NEXT slot or finalize into a needs_confirmation/needs_pin card. Bounded by
        MAX_CLARIFY. The held command keeps its intent + accumulated slots across HTTP turns."""
        from .intent import driver as _intent
        from . import delegate as _delegate
        from . import identity as _identity
        t = _require_tenant(request, "write")
        tid = t.get("tenant_id", "")
        c = _TEST_CMDS.get(command_id)
        if not c or c.get("tenant_id") != tid or not c.get("pending"):
            raise HTTPException(status_code=404, detail="no pending command")
        reply = (body or {}).get("text", "") or (body or {}).get("value", "") or ""
        action = c.get("action", {})
        tool = c.get("tool", "")
        args = dict(action.get("args", {}) or {})
        outstanding = list(c.get("outstanding") or _intent.missing_required(tool, args))
        ctx = c.get("ctx", {}) or {}
        role = c.get("role", "operator")

        # the user may PIVOT to a new command mid-elicit; a confident new command intent wins.
        re_match = _intent.parse_intent(reply, ctx) or {}
        if (re_match.get("kind") == "command" and (re_match.get("intent") or "") != tool
                and float(re_match.get("confidence", 0) or 0) >= 0.75):
            _TEST_CMDS.pop(command_id, None)
            return _aim_parse_card(t, reply, "dashboard")

        nxt = outstanding[0] if outstanding else None
        if nxt is not None:
            ok, val = _intent.parse_slot_value(tool, nxt, reply, ctx)
            c["ask_count"] = int(c.get("ask_count", 0)) + 1
            if ok:
                args[nxt] = val
                action = dict(action)
                action["args"] = args
                c["action"] = action
                outstanding = _intent.missing_required(tool, args)
                c["outstanding"] = outstanding
            else:
                # bad answer -> re-ask the SAME slot (bounded)
                if int(c.get("ask_count", 0)) >= 6:
                    _TEST_CMDS.pop(command_id, None)
                    return {"command_id": command_id, "status": "abandoned", "safe_to_execute": False,
                            "user_facing_summary": "Theek hai, abhi ke liye chhod dete hain. Aur kuch?"}
                return {"command_id": command_id, "intent": tool, "status": "eliciting",
                        "missing_fields": outstanding, "next_slot": nxt,
                        "prompt": _intent.slot_question(nxt), "safe_to_execute": False,
                        "user_facing_summary": "Sorry, samajh nahi aaya. " + _intent.slot_question(nxt)}

        if outstanding:
            nxt = outstanding[0]
            return {"command_id": command_id, "intent": tool, "status": "eliciting",
                    "missing_fields": outstanding, "next_slot": nxt,
                    "prompt": _intent.slot_question(nxt), "safe_to_execute": False,
                    "user_facing_summary": _intent.slot_question(nxt),
                    "entities": dict(args)}

        # COMPLETE -> finalize into the normal confirm/PIN card under the SAME command_id.
        risk = _identity.classify_risk(tool)
        risky = _identity.is_risky(tool)
        return _finalize_command_card(tid, role, t, command_id, action, tool, risk, risky,
                                      float(c.get("conf", 0.8) or 0.8))

    @router.post("/commands/{command_id}/confirm")
    def commands_confirm(request: Request, command_id: str) -> dict:
        t = _require_tenant(request, "write")
        c = _TEST_CMDS.get(command_id)
        if not c or c.get("tenant_id") != t.get("tenant_id"):
            raise HTTPException(status_code=404, detail="command not found")
        c["confirmed"] = True
        status = "needs_pin" if c.get("risky") else "ready"
        return {"command_id": command_id, "intent": c.get("tool", ""), "status": status,
                "requires_pin": bool(c.get("risky")), "requires_confirmation": False,
                "risk_level": _aim_risk_to_int(c.get("risk", "safe")), "safe_to_execute": True}

    @router.post("/commands/{command_id}/cancel")
    def commands_cancel(request: Request, command_id: str) -> dict:
        t = _require_tenant(request, "write")
        c = _TEST_CMDS.pop(command_id, None)
        if c and c.get("tenant_id") == t.get("tenant_id"):
            try:
                _audit.cancelled(actor=t.get("tenant_id", ""), tenant_id=t.get("tenant_id", ""),
                                 session_id=command_id, action=c.get("tool", ""))
            except Exception:  # noqa: BLE001
                pass
        return {"command_id": command_id, "status": "cancelled", "safe_to_execute": False}

    @router.post("/commands/{command_id}/execute")
    def commands_execute(request: Request, command_id: str, body: dict = Body(default={})) -> dict:
        t = _require_tenant(request, "write")
        c = _TEST_CMDS.get(command_id)
        if not c or c.get("tenant_id") != t.get("tenant_id"):
            raise HTTPException(status_code=404, detail="command not found")
        tid = t.get("tenant_id", "")
        tool = c.get("tool", "")
        risk = c.get("risk", "safe")
        if not c.get("permitted"):
            try:
                _audit.permission_denied(actor=tid, tenant_id=tid, session_id=command_id, action=tool)
            except Exception:  # noqa: BLE001
                pass
            return {"command_id": command_id, "status": "denied", "safe_to_execute": False,
                    "block_reason": "permission_denied", "error": "not permitted",
                    "user_facing_summary": f"You're not permitted to run {tool}."}

        pin = (body or {}).get("pin", "") or ""
        step_up_token = ""
        if c.get("risky"):
            if not pin:
                return {"command_id": command_id, "status": "needs_pin", "requires_pin": True,
                        "safe_to_execute": True, "user_facing_summary": "This action needs your PIN."}
            # VERIFY PIN via the firewall (salted hash). Wrong PIN -> deny + audit, NEVER execute.
            if _firewall.available() and _firewall.has_pin(tid):
                if not _firewall.check_pin(tid, pin):
                    try:
                        _audit.permission_denied(actor=tid, tenant_id=tid, session_id=command_id,
                                                 action="pin_failed:" + tool)
                    except Exception:  # noqa: BLE001
                        pass
                    return {"command_id": command_id, "status": "denied", "requires_pin": True,
                            "safe_to_execute": False, "block_reason": "pin_failed",
                            "error": "PIN verification failed",
                            "user_facing_summary": "That PIN was incorrect. Cancelling that action."}
                from . import identity as _identity2
                scope = _identity2.stepup_scope(tool)
                mint = _firewall.mint_step_up(tid, scope) if scope else None
                step_up_token = (mint or {}).get("token", "") if isinstance(mint, dict) else ""
            else:
                # No firewall PIN enrolled -> a risky action MUST NOT proceed unauthenticated.
                return {"command_id": command_id, "status": "needs_pin", "requires_pin": True,
                        "safe_to_execute": False, "block_reason": "no_pin_enrolled",
                        "user_facing_summary": "No PIN is enrolled for this tenant — risky actions are blocked."}

        # EXECUTE via the workforce runner (it re-enforces its OWN caps/DND/kill-switch and parks
        # when the target module is unconfigured -> graceful, no paid call in tests).
        from . import delegate as _delegate
        from . import identity as _identity3
        tenant_dict = {"tenant_id": tid, "role": c.get("role", "operator"),
                       "is_admin": bool(t.get("is_admin"))}
        result = _delegate.execute(tid, c.get("action", {}), tenant_dict=tenant_dict,
                                   step_up_token=step_up_token, actor=tid,
                                   is_admin=bool(t.get("is_admin")))
        status = result.get("status", "")
        # TRUTH-IN-REPORTING (FIX-B / A2): a run is only "executed" when the runner reached done AND a
        # tool actually landed a side effect (delegate sets effective=True). A run that finalized "done"
        # but whose only tool PARKED (module off -> not_configured) is an honest no-op, NOT a success.
        effective = bool(result.get("effective"))
        reason = (result.get("last_reason") or result.get("reason") or
                  (result.get("parked", {}) or {}).get("scope", "") or status)
        try:
            _audit.call_end(actor=tid, tenant_id=tid, session_id=command_id,
                            outcome=("execute:" + ("effective" if effective else (status or "noop"))),
                            n_actions=(1 if effective else 0))
        except Exception:  # noqa: BLE001
            pass
        _TEST_CMDS.pop(command_id, None)
        return {"command_id": command_id, "intent": tool,
                "status": ("executed" if effective else (status or "failed")),
                "executed": effective,
                "risk_level": _aim_risk_to_int(risk), "safe_to_execute": True,
                "execution_result": {"status": status, "run_id": result.get("run_id", ""),
                                     "outcome": result.get("outcome"),
                                     "parked": result.get("parked"), "reason": reason},
                "action_run_id": result.get("run_id", ""),
                "error": (None if effective else (reason or status)),
                "user_facing_summary": _aim_human_outcome(tool, effective, reason)}

else:  # FastAPI absent
    router = None  # type: ignore


# ---------------- JSON-safety (PG rows carry datetime/Decimal/jsonb-as-str) ----------------
def _jsonify(row: Any) -> Any:
    """Make a PG row dict JSON-serializable: datetimes -> ISO strings, Decimal -> number, jsonb text ->
    parsed object. Recurses into nested dicts/lists (turns/commands). NEVER raises."""
    try:
        import datetime as _dt
        import decimal as _dec
        if isinstance(row, dict):
            return {k: _jsonify(v) for k, v in row.items()}
        if isinstance(row, list):
            return [_jsonify(v) for v in row]
        if isinstance(row, (_dt.datetime, _dt.date)):
            return row.isoformat()
        if isinstance(row, _dec.Decimal):
            f = float(row)
            return int(f) if f == int(f) else f
        if isinstance(row, str):
            s = row.strip()
            # parse jsonb columns that the driver returned as a JSON string (execution_result/metadata)
            if s.startswith("{") or s.startswith("["):
                try:
                    return json.loads(s)
                except Exception:  # noqa: BLE001
                    return row
            return row
        return row
    except Exception:  # noqa: BLE001
        return row


# ---------------- session persistence (JSONL on the control plane; PIN ALWAYS masked) ----------------
_SECRET_KEYS = {"pin", "otp", "secret", "code", "step_up_token", "token"}


def _sanitize_session(body: dict) -> dict:
    """Defense-in-depth: strip/mask any secret-shaped field before persisting a shipped session. The voice
    worker should already mask, but the API box NEVER trusts the client to have done so."""
    def scrub(obj):
        if isinstance(obj, dict):
            return {k: ("****" if str(k).lower() in _SECRET_KEYS else scrub(v)) for k, v in obj.items()}
        if isinstance(obj, list):
            return [scrub(x) for x in obj]
        return obj
    return scrub(dict(body))


def _append_session(rec: dict) -> None:
    f = _config.sessions_file()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _read_sessions(tenant_id: str, *, limit: int = 50) -> list[dict]:
    f = _config.sessions_file()
    rows: list[dict] = []
    try:
        if f.exists():
            with open(f, "r", encoding="utf-8") as fh:
                for ln in fh:
                    ln = ln.strip()
                    if not ln:
                        continue
                    try:
                        r = json.loads(ln)
                    except Exception:  # noqa: BLE001
                        continue
                    if r.get("tenant_id") == tenant_id:
                        rows.append(r)
    except Exception:  # noqa: BLE001
        pass
    rows.reverse()
    try:
        limit = max(1, min(int(limit), 500))
    except Exception:  # noqa: BLE001
        limit = 50
    return rows[:limit]
