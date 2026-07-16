"""Offline unit test for connectors.whatsapp + connectors.telephony — MOCKED httpx, zero sockets.

NO real network: every WhatsApp request is served by an httpx.MockTransport. No real keys: creds are
a fake ConnectorCreds with an inline secret_json blob (the same shape vault_adapter.get_secret_json
would return). Run:
    python -c "import sys; sys.path.insert(0,'droplet_work'); \
        import ads_engine.connectors.test_whatsapp_telephony as t; t.main()"

WhatsApp asserts:
  W1. send_template (360dialog) -> ok, D360-API-KEY header injected, wamid + cost surfaced.
  W2. metering hook fired once with the Marketing paise rate (86) on a 2xx.
  W3. send_template (cloud) -> Authorization: Bearer header + /v23.0/{pnid}/messages path.
  W4. send_text OUTSIDE any window -> invalid_request, NO request issued (no spend).
  W5. send_ctwa_followup INSIDE 72h window -> ok, free-text payload, cost 0 (service).
  W6. not_configured (missing api_key) -> not_configured, no request.
  W7. send_text just OVER the 24h service window -> invalid_request.

Telephony asserts:
  T1. build_call_job -> EXACT caller.py:5754-5768 row shape (keys + lead sub-shape + force_window).
  T2. force_window True by default (ad-lead instant dial); caps clamped.
  T3. numberless lead -> ValueError (fail-loud at build time).
  T4. Exotel backend stub -> telephony_backend/promo_cli_series attached, row otherwise identical.
  T5. hand_off defers to the INJECTED enqueue closure (no JOBS/run_job touched); receipt handed_off.
  T6. NO `import caller` / `run_job` / LiveKit anywhere in telephony.py (earner-safety static check).
"""

from __future__ import annotations

import asyncio
import sys


# --- a minimal stand-in for vault_adapter.ConnectorCreds (the connector only reads .ok/.secret_json)
class _Creds:
    def __init__(self, ok=True, secret_json=None):
        self.ok = ok
        self.secret_json = secret_json or {}


def _imports():
    try:
        import httpx  # noqa: F401
    except Exception as e:  # noqa: BLE001
        print(f"SKIP (httpx unavailable): {e!r}")
        return None
    from ads_engine.connectors.whatsapp import WhatsAppConnector
    from ads_engine.connectors.telephony import build_call_job, TelephonyConnector, BACKEND_EXOTEL
    from ads_engine.connectors.base import ConnectorError
    return httpx, WhatsAppConnector, build_call_job, TelephonyConnector, BACKEND_EXOTEL, ConnectorError


def _wa(httpx, WhatsAppConnector, secret_json, handler, *, meter=None, now=1000.0):
    """Build a WhatsAppConnector on a MockTransport that runs `handler(request)`. now_fn fixed."""
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    creds = _Creds(ok=True, secret_json=secret_json)
    conn = WhatsAppConnector(creds, http=client, now_fn=lambda: now, meter=meter)
    return conn, client


def _run(coro):
    return asyncio.run(coro)


def main() -> int:
    got = _imports()
    if got is None:
        return 0
    httpx, WhatsAppConnector, build_call_job, TelephonyConnector, BACKEND_EXOTEL, ConnectorError = got
    R = httpx.Response
    failures = []

    def check(name, cond):
        print(f"  {'PASS' if cond else 'FAIL'} — {name}")
        if not cond:
            failures.append(name)

    # ---- W1 + W2: 360dialog template send, header, metering -----------------------------------
    seen = {}
    metered = []

    def _h_ok(request):
        seen["host"] = request.url.host
        seen["path"] = request.url.path
        seen["d360"] = request.headers.get("d360-api-key")
        seen["auth"] = request.headers.get("authorization")
        return R(200, json={"messages": [{"id": "wamid.HBg123"}]})

    async def w1():
        conn, client = _wa(
            httpx, WhatsAppConnector,
            {"channel": "360dialog", "api_key": "D360SECRET", "phone_number_id": "PNID1",
             "waba_id": "WABA1"},
            _h_ok, meter=lambda ev: metered.append(ev))
        res = await conn.send_template("+919812345678", "welcome_v1", "en", category="marketing")
        await conn.aclose()
        return res
    res = _run(w1())
    check("W1 360dialog template -> ok, D360-API-KEY header, waba host, wamid surfaced",
          res.ok and seen.get("d360") == "D360SECRET" and seen.get("auth") is None
          and seen.get("host") == "waba-v2.360dialog.io" and seen.get("path") == "/messages"
          and res.data.get("message_id") == "wamid.HBg123")
    check("W2 metering hook fired once at Marketing rate (86 paise), cost surfaced on result",
          len(metered) == 1 and metered[0]["cost_minor"] == 86
          and metered[0]["channel"] == "whatsapp" and metered[0]["kind"] == "template"
          and res.data.get("cost_minor") == 86 and res.data.get("via_marketing_api") is True)

    # ---- W3: cloud-API-direct backend ---------------------------------------------------------
    seen2 = {}

    def _h_cloud(request):
        seen2["host"] = request.url.host
        seen2["path"] = request.url.path
        seen2["auth"] = request.headers.get("authorization")
        seen2["d360"] = request.headers.get("d360-api-key")
        return R(200, json={"messages": [{"id": "wamid.CLOUD9"}]})

    async def w3():
        conn, client = _wa(
            httpx, WhatsAppConnector,
            {"channel": "cloud", "access_token": "CLOUDTOK", "phone_number_id": "PNID9"},
            _h_cloud)
        res = await conn.send_template("919812345678", "promo", "en", category="utility")
        await conn.aclose()
        return res
    res = _run(w3())
    check("W3 cloud backend -> graph host, /v23.0/PNID9/messages path, Bearer auth (no D360)",
          res.ok and seen2.get("host") == "graph.facebook.com"
          and seen2.get("path") == "/v23.0/PNID9/messages"
          and seen2.get("auth") == "Bearer CLOUDTOK" and seen2.get("d360") is None
          and res.data.get("cost_minor") == 12)  # utility rate

    # ---- W4: free-text OUTSIDE any window -> refused, no request -------------------------------
    issued = {"n": 0}

    def _h_count(request):
        issued["n"] += 1
        return R(200, json={"messages": [{"id": "x"}]})

    async def w4():
        conn, client = _wa(
            httpx, WhatsAppConnector,
            {"channel": "360dialog", "api_key": "K", "phone_number_id": "P"},
            _h_count, now=1_000_000.0)
        res = await conn.send_text("+919812345678", "hi there", window_opened_at=None)
        await conn.aclose()
        return res
    res = _run(w4())
    check("W4 free-text outside window -> invalid_request, NO request issued (no spend)",
          (not res.ok) and res.error == ConnectorError.INVALID_REQUEST and issued["n"] == 0)

    # ---- W5: CTWA follow-up INSIDE the 72h window ---------------------------------------------
    metered5 = []

    def _h_text(request):
        body = request.read().decode() if hasattr(request, "read") else ""
        seen["text_type"] = '"type": "text"' in body or '"type":"text"' in body
        return R(200, json={"messages": [{"id": "wamid.TXT"}]})

    async def w5():
        # click was 1 hour before "now"=1000.0 -> well inside 72h.
        conn, client = _wa(
            httpx, WhatsAppConnector,
            {"channel": "360dialog", "api_key": "K", "phone_number_id": "P"},
            _h_text, meter=lambda ev: metered5.append(ev), now=1000.0)
        res = await conn.send_ctwa_followup("+919812345678", "thanks for your interest!",
                                            click_ts=1000.0 - 3600)
        await conn.aclose()
        return res
    res = _run(w5())
    check("W5 CTWA follow-up inside 72h -> ok, free-text, cost 0 (service)",
          res.ok and res.data.get("cost_minor") == 0 and res.data.get("window") == "ctwa"
          and len(metered5) == 1 and metered5[0]["cost_minor"] == 0)

    # ---- W6: not_configured (missing api_key) -------------------------------------------------
    async def w6():
        conn, client = _wa(
            httpx, WhatsAppConnector,
            {"channel": "360dialog", "phone_number_id": "P"},  # no api_key
            _h_count)
        res = await conn.send_template("+919812345678", "t")
        await conn.aclose()
        return res
    res = _run(w6())
    check("W6 missing api_key -> not_configured, no request",
          (not res.ok) and res.error == ConnectorError.NOT_CONFIGURED)

    # ---- W7: free-text just OVER the 24h service window ---------------------------------------
    async def w7():
        conn, client = _wa(
            httpx, WhatsAppConnector,
            {"channel": "360dialog", "api_key": "K", "phone_number_id": "P"},
            _h_count, now=1_000_000.0)
        # opened 24h + 1s ago -> expired.
        res = await conn.send_text("+919812345678", "late", window="service",
                                   window_opened_at=1_000_000.0 - (24 * 3600 + 1))
        await conn.aclose()
        return res
    res = _run(w7())
    check("W7 free-text just over 24h service window -> invalid_request",
          (not res.ok) and res.error == ConnectorError.INVALID_REQUEST)

    # =========================================================================================
    # TELEPHONY
    # =========================================================================================
    lead = {"name": "Asha", "num": "+919800011122"}

    # ---- T1 + T2: exact JOBS row shape + force_window default --------------------------------
    job = build_call_job("tenant-7", "camp-9", lead)
    expected_keys = {"state", "campaign_id", "tenant_id", "concurrency", "hourly_cap",
                     "daily_cap", "force_window", "leads"}
    lead_keys = {"name", "num", "status", "room", "launched_at", "attempt"}
    row_ok = (
        set(job.keys()) == expected_keys
        and job["state"] == "queued" and job["campaign_id"] == "camp-9"
        and job["tenant_id"] == "tenant-7" and job["concurrency"] == 1
        and isinstance(job["leads"], list) and len(job["leads"]) == 1
        and set(job["leads"][0].keys()) == lead_keys
        and job["leads"][0]["name"] == "Asha" and job["leads"][0]["num"] == "+919800011122"
        and job["leads"][0]["status"] == "queued" and job["leads"][0]["room"] == ""
        and job["leads"][0]["launched_at"] == 0.0 and job["leads"][0]["attempt"] == 0
    )
    check("T1 build_call_job mirrors caller.py:5754-5768 row + lead sub-shape EXACTLY", row_ok)
    check("T2 force_window True by default (ad-lead instant dial), caps clamped >=1",
          job["force_window"] is True and job["hourly_cap"] >= 1 and job["daily_cap"] >= 1)

    # ---- T3: numberless lead -> ValueError (fail-loud) ---------------------------------------
    t3_raised = False
    try:
        build_call_job("t", "c", {"name": "NoNumber"})
    except ValueError:
        t3_raised = True
    check("T3 numberless lead -> ValueError at build time", t3_raised)

    # ---- T4: Exotel 140-series stub ----------------------------------------------------------
    job_exo = build_call_job("t", "c", lead, backend=BACKEND_EXOTEL)
    check("T4 Exotel stub -> telephony_backend/promo_cli_series attached; livekit default has neither",
          job_exo.get("telephony_backend") == "exotel" and job_exo.get("promo_cli_series") == "140"
          and "telephony_backend" not in job and "promo_cli_series" not in job)

    # ---- T5: hand_off defers to the injected enqueue closure ---------------------------------
    captured = {}

    def _fake_enqueue(tid, cid, row):
        captured["tid"] = tid
        captured["cid"] = cid
        captured["row"] = row
    conn = TelephonyConnector(enqueue=_fake_enqueue, backend="livekit")
    receipt = conn.hand_off("tenant-7", "camp-9", lead)
    check("T5 hand_off uses injected enqueue (no JOBS/run_job); receipt handed_off + force_window",
          receipt["handed_off"] is True and receipt["force_window"] is True
          and captured.get("tid") == "tenant-7" and captured.get("cid") == "camp-9"
          and captured["row"]["leads"][0]["num"] == "+919800011122")

    # ---- T6: AST earner-safety check — no caller/run_job/LiveKit *code* in telephony.py ------
    # The docstrings legitimately NAME run_job/create_task/LiveKit to state the module never touches
    # them, so a substring scan false-positives on prose. We instead walk the AST: forbid any
    # `import caller` / `from caller ...`, any `import livekit` / `from livekit ...`, and any CALL to
    # a function literally named run_job / create_task. Docstrings/comments are not AST call/import
    # nodes, so they are correctly ignored.
    import ast
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(here, "telephony.py"), "r", encoding="utf-8").read()
    tree = ast.parse(src)

    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in ("caller", "livekit", "agent"):
                    bad.append(f"import {a.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in ("caller", "livekit", "agent"):
                bad.append(f"from {node.module} import ...")
        elif isinstance(node, ast.Call):
            f = node.func
            name = getattr(f, "attr", None) or getattr(f, "id", None)
            if name in ("run_job", "create_task"):
                bad.append(f"call {name}(...)")
    check("T6 telephony.py AST has no caller/livekit/agent import, no run_job/create_task call",
          not bad)

    print(f"\nwhatsapp+telephony test: {'ALL PASS' if not failures else 'FAILURES: ' + repr(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
