

# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOMER (sales) MODE additions (BUILD #5). All read-only-over-HTTP against the
# SAME live caller.py the panel uses; never import/edit caller.py/agent.py. Every
# function NEVER raises — returns a safe value/spoken-friendly dict on any error.
# ═══════════════════════════════════════════════════════════════════════════════
def _norm_phone(phone: str) -> str:
    """Match caller.py norm(): digits-only -> +91XXXXXXXXXX (drop leading 0, add 91 for
    a bare 10-digit). Used to reconcile the SIP caller-id against stored call/lead phones."""
    import re as _re
    d = _re.sub(r"\D", "", phone or "")
    if d.startswith("0"):
        d = d[1:]
    if len(d) == 10:
        d = "91" + d
    return ("+" + d) if len(d) >= 11 else ""


def _digits(phone: str) -> str:
    import re as _re
    return _re.sub(r"\D", "", phone or "")


def resolve_contact_by_phone(phone: str) -> dict:
    """Returning-caller link over HTTP (mirrors caller._resolve_contact_by_phone, but read-only
    against /calls + /leads). Returns {name, campaign_id, campaign_name, tenant_id, is_known}.
    Most-recent CALL to this number wins (it carries campaign_id); falls back to a stored lead.
    NEVER raises."""
    out = {"name": "", "campaign_id": "", "campaign_name": "", "tenant_id": "", "is_known": False}
    key = _norm_phone(phone)
    if not key:
        return out
    # 1) most-recent call to this number (carries campaign_id + name)
    try:
        d = _get("/calls", {"limit": 1000})
        for c in (d.get("calls", []) or []):
            if _norm_phone(c.get("phone", "") or c.get("num", "")) == key:
                out["name"] = c.get("name", "") or out["name"]
                out["campaign_id"] = c.get("campaign_id", "") or out["campaign_id"]
                out["campaign_name"] = c.get("campaign_name", "") or out["campaign_name"]
                out["tenant_id"] = c.get("tenant_id", "") or out["tenant_id"]
                out["is_known"] = True
                break
    except Exception:  # noqa: BLE001
        pass
    # 2) fall back to a stored lead (name only; leads have no campaign in this data model)
    if not out["name"]:
        try:
            d = _get("/leads")
            for x in (d.get("leads", []) or []):
                if _norm_phone(x.get("phone", "")) == key:
                    out["name"] = x.get("name", "") or out["name"]
                    out["tenant_id"] = out["tenant_id"] or x.get("tenant_id", "")
                    out["is_known"] = True
                    break
        except Exception:  # noqa: BLE001
            pass
    return out


def campaign_fields(spoken_or_id: str) -> dict:
    """Resolve a spoken name / id to its FULL campaign `fields` dict (the same shape
    prompt.build_system_prompt expects) by reading GET /campaigns/{id}. Returns {} if it
    can't resolve. NEVER raises."""
    try:
        camp = resolve_campaign(spoken_or_id)
        if camp is None:
            return {}
        cid = str(camp.get("id", ""))
        if not cid:
            return {}
        d = _get(f"/campaigns/{cid}")
        full = (d.get("campaign") or d) if isinstance(d, dict) else {}
        f = dict(full.get("fields", {}) or {})
        # stamp id/name so the caller (customer agent) can attach the lead later
        f.setdefault("_campaign_id", cid)
        f.setdefault("_campaign_name", _camp_name(full) or _camp_name(camp))
        return f
    except Exception:  # noqa: BLE001
        return {}


def active_campaigns() -> list[dict]:
    """The campaigns a NEW inbound caller could be calling about — those that are 'active' OR
    'ready' (i.e. live enough to take inbound interest). Returns [{id, name, status}]. Falls back
    to ALL campaigns if none are flagged active/ready (never leave a caller with zero options).
    NEVER raises."""
    camps = list_campaigns()
    if not camps:
        return []
    act = []
    for c in camps:
        st = str(c.get("status") or "").strip().lower()
        if st in ("active", "running", "ready", "live", "on"):
            act.append({"id": str(c.get("id", "")), "name": _camp_name(c) or "(unnamed)", "status": st})
    if not act:  # nothing flagged -> offer the whole set so a new caller is never stranded
        act = [{"id": str(c.get("id", "")), "name": _camp_name(c) or "(unnamed)",
                "status": str(c.get("status") or "")} for c in camps]
    return act


def create_lead(name: str, phone: str, campaign_id: str = "") -> dict:
    """Create/refresh a lead for an inbound CUSTOMER caller so the sale is visible in the panel.
    POSTs to /leads (the same route the panel 'Add leads' uses) with a 'name,phone' line. Idempotent
    server-side (de-dups on phone within the tenant). Returns {ok, added}. NEVER raises.

    NOTE: caller.py's /leads stores tenant-wide leads (no campaign column), so campaign_id is recorded
    only for the spoken/audit context here; the lead row links to the tenant. The CALL record (written
    by the inbound run) is what carries campaign_id for the next returning-caller resolution."""
    ph = _norm_phone(phone)
    if not ph:
        return {"ok": False, "added": 0, "summary": "no_phone"}
    nm = (name or "").strip() or "Inbound caller"
    line = f"{nm},{ph}"
    try:
        res = _post_form("/leads", {"leads": line})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "added": 0, "error": type(exc).__name__}
    added = int(res.get("added", 0) or 0)
    return {"ok": True, "added": added, "phone": ph, "name": nm,
            "summary": ("saved as a new lead" if added else "already on file")}


def test_call(name: str, phone: str, campaign_id: str = "") -> dict:
    """Place ONE real outbound call to an explicit phone via the PROVEN /run dial path — used by the
    manager's `test_call_me` tool so the founder's own verified number RINGS. POSTs the phone as an
    ad-hoc lead line ('name,phone') + a campaign + force=1 (so it dials immediately, outside-window
    safe). Returns a spoken-friendly result. NEVER raises. SAFETY: this is the SAME /run route the
    panel Run button uses — no new dial code; it just dispatches one lead."""
    ph = _norm_phone(phone)
    if not ph:
        return {"ok": False, "summary": "I don't have a verified number on file to ring you back on."}
    cid = (campaign_id or "").strip()
    if not cid:
        # pick the first active/ready campaign so the test call has a brain
        acts = active_campaigns()
        cid = acts[0]["id"] if acts else ""
    if not cid:
        return {"ok": False, "summary": "I couldn't find a campaign to place the test call with."}
    nm = (name or "").strip() or "Manager"
    form = {"campaign_id": cid, "leads": f"{nm},{ph}", "force": "1"}
    try:
        res = _post_form("/run", form)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "summary": "I couldn't place the test call — the calling engine didn't respond.",
                "error": type(exc).__name__}
    st = res.get("_status", 0)
    if st == 402:
        return {"ok": False, "summary": "I couldn't place the test call — the prepaid balance is exhausted."}
    job = res.get("job_id", "")
    n = res.get("count", 0)
    if not job and st not in (200, 202):
        return {"ok": False, "summary": "I couldn't place the test call just now — please try again."}
    return {"ok": True, "job_id": job, "count": n, "phone": ph,
            "summary": "Done — I'm ringing your phone now. It should start ringing in a few seconds."}
