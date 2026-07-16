# VERIFY-2 — AI Manager "run campaign" → does it actually dial? (READ-ONLY trace, 2026-06-11)

**Box:** famit@168.144.153.145 · `/opt/famit-agent/`
**Method:** static code trace of the full chain (NLU → delegate → role/scope → workforce tool → caller.py `/run`). No test call placed — the trace is conclusive and the bug would make any call a 0‑lead no‑op anyway. Live earner untouched (read-only).

## VERDICT: NO — instructing the AI Manager "run campaign <name>" does NOT dial.

Two independent defects, either one alone is fatal:

### Defect A — there is NO intent that "runs a named existing campaign"
`ai_manager/intent/driver.py` closed `COMMAND_INTENTS` (lines 41–61) has no "run/dial existing campaign" intent. The two near-matches both miss:
- `"run|launch|create|start" + "campaign"` → **`campaigns.create`** (driver.py:276–278). That tool (`workforce/tools/catalog.py:_campaigns_create`) hits `POST /campaigns` = **create a DRAFT only, no dial** (`risk_class="safe"`). The LLM NLU (active: `AIM_LLM_PROVIDER=groq`) is told *"Prefer a DRAFT over direct execution for campaigns"* (system prompt), so "run campaign X" classifies to `campaigns.create` → a draft, not a run.
- The ONLY tool that reaches the dial endpoint is **`leads.enqueue_calls`** (catalog.py:318 → `_leads_enqueue_calls` → `POST /run`), but its trigger phrase is *"call (all/hot) leads"* (driver.py:289–291), NOT "run campaign". Its slots are `{"segment":"hot"|"all"}` — it carries **no `campaign_id`**.

So "run campaign Diwali" routes to a DRAFT-create. It never reaches `/run`.

### Defect B — even the dial tool (`leads.enqueue_calls`) is wired wrong and would dial 0 leads
`caller.py:3071 POST /run` reads **`Form(...)`** fields: `campaign_id`, `leads`, `use_stored`, `lead_ids`, `source_mode`, etc. But `catalog.py:96`:
```python
return _result(_t.call("POST", "/run", run_token=_tok(ctx), json=args or {}))
```
sends a **JSON body** (`json=`), not form (`data=`). FastAPI Form params ignore a JSON body → every field defaults empty → `parsed=[]`, `use_stored=""`, no audience → `uniq=[]`. `/run` happily creates a job with **0 leads → no dial** (returns `{job_id, count:0}`, HTTP 200, looks "successful"). The args passed are only `{"segment":...}`, which `/run` has no parameter for, so even that is silently dropped. (Note: the sibling `campaigns.create` tool was fixed to use `data=`/form in the B2 wave; **`leads.enqueue_calls` was NOT** — still `json=`.)

## The exact tool/route it SHOULD hit
- Tool: **`leads.enqueue_calls`** (scope held by role `telecaller`, delegate.py:`_INTENT_ROLE`; runner invokes `tool.fn(args, ctx)` at runner.py:224 after the risky-gate/PIN passes).
- Route: **`POST /run`** with **form** body `data={"campaign_id": <resolved id>, "use_stored": "1", "force": "1"}` (or `leads=`/`lead_ids=`), carrying the per-run Bearer `run_token` (RLS-scoped). This is the same path the panel "Run a Campaign" button uses — and **the panel works** because it POSTs proper multipart/form data with a real `campaign_id`. The AIM path is the only broken caller.

## Trace summary (chain)
NLU(groq) → intent `campaigns.create` (wrong; should be a run intent) → delegate `role_for`→ `strategist` → tool `campaigns.create` → `POST /campaigns` = **DRAFT, no dial.**
Even forcing the right intent: `leads.enqueue_calls` → role `telecaller` → tool → `POST /run` with **`json=` (ignored by Form endpoint) + no `campaign_id`** → **job with 0 leads, no dial.**

## THE FIX (minimal, additive, does NOT touch agent.py / the live voice worker)
1. **Add a "run existing campaign" command intent** `campaigns.run` (or reuse `leads.enqueue_calls` with a `campaign` slot). In `driver.py`: a deterministic matcher for `run|start|launch + campaign` that resolves the named campaign from `business_context.active_campaigns` into slot `campaign_id`, AND steer the LLM prompt: "run/start an EXISTING named campaign → that run intent (not a draft)". Keep "create a NEW campaign" → `campaigns.create`.
2. **Fix `_leads_enqueue_calls` to use form + pass the audience** (catalog.py:94–96):
   ```python
   def _leads_enqueue_calls(args, ctx):
       a = dict(args or {})
       body = {"campaign_id": a.get("campaign_id") or a.get("campaign") or ""}
       # map segment -> stored-leads selector; default to all stored if a campaign is named
       if a.get("use_stored") or a.get("campaign_id") or a.get("campaign"):
           body["use_stored"] = "1"
       if a.get("lead_ids"): body["lead_ids"] = a["lead_ids"]
       if a.get("force"):    body["force"] = "1"
       return _result(_t.call("POST", "/run", run_token=_tok(ctx), data=body))  # data= (form), NOT json=
   ```
   (`transport.call` already supports `data=` form-encoding — used by `campaigns.create`.)
3. **Map the new intent** in `delegate._INTENT_ROLE` → `telecaller`, and in `identity.classify_risk` → risky (PIN step-up; bulk dial = paid). Add `campaigns.run` to telecaller `default_scopes` in `roles.py` (else `policy.resolve` blocks it).
4. Regression-gate: workforce `test_offline.py` (10/10), NLU mock smoke, then ONE real test call to the founder's own number **+91 78610 19021** (`TESTE_PHONE_NO`) via a tiny seeded campaign. Restart only `famit-caller` (the `/run` + tool registry live there); do NOT restart `famit-agent` (voice worker `agent.py` is unchanged). Backup `caller.py`/`catalog.py`/`driver.py` first; rollback `*.bak` on any doubt.

## Note on the panel "Run a Campaign" button (the founder's part (a))
The panel button is a **separate, working path** — it POSTs real form data with a `campaign_id` to `/run`. The 96 real calls came through this. The founder CAN reliably run a campaign that dials **via the panel today**. Only the **AI Manager voice/chat "run campaign" command** (part (b)) is broken, for the reasons above.
