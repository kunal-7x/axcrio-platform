# AIM Voice — DATA SURFACE & HALLUCINATION GAP (DIAGNOSE-1)

Box: famit@168.144.153.145 · files: `aim_voice_agent.py` (ManagerAgent + @function_tools),
`ai_manager/voice_tools.py` (loopback bridge to caller.py:8209, X-Auth `FamitCall2026`).
Founder = **admin tenant** (campaign c17e55e9f3 "Codename Joy 3.0" has `tenant_id: "admin"`).
All loopback calls below are REAL responses captured 2026-06-12.

## 1. EXISTING voice tools (what the agent can call today)
`aim_voice_agent.py` ManagerAgent exposes exactly 7 @function_tools:
`verify_pin`, `manager_status` (→`_quick_status`), `check_leads` (→`vt.lead_counts`),
`recent_calls` (→`vt.recent_calls`), `analytics` (→`vt.analytics`), `wallet_status`
(→`vt.wallet_status`), `run_campaign` (→`vt.run_campaign`).
`voice_tools.py` backs these + has UNUSED helpers `list_campaigns()`, `resolve_campaign()`,
`resolve_audience()` (only reachable INSIDE run_campaign — NOT exposed as tools).

## 2. What each tool ACTUALLY returns (verified over loopback)
- `/campaigns` → **8 campaigns** (Codename Joy 3.0, DLF The Crest, Jabalpur Property, 3×Premium 2/3BHK, QA Widget). `list_campaigns()` parses them fine.
- `/leads` → **5 rows tenant-WIDE** (admin + 2 other tenants), keys incl `id,phone,score,status,tenant_id`. `/stats` → total 135, answered 42, vm 76, 8 campaigns. `/wallet` → admin INR 4942.34.
- `/campaigns/{id}` → wrapped `{"campaign":{id,name,tenant_id,status,fields{27 keys}}}` — voice has NO tool to read this; would need `.campaign` unwrap.

## 3. ROOT CAUSES of "invents info / can't list campaigns / won't dial"
- **HALLUCINATION / can't-list:** there is **NO `list_campaigns` voice tool and NO `campaign_detail` voice tool**. The agent has zero way to enumerate the 8 campaigns or read one — so "how many campaigns" / "my other campaigns" → it MAKES IT UP. Instructions only mention the 7 tools above; they do NOT forbid answering from memory.
- **"Codename Joy works":** that name is in its prompt context → lucky, not fetched.
- **WON'T DIAL = founder is not a lead:** run path IS functional — `/run/preview … source_mode=manual lead_ids=…` → `count:2 callable:2`; manual lead_ids round-trip correctly through `_resolve_audience`. BUT founder phone **+917861019021 is NOT in the 5-lead pool** (pool = +916375…/+917987…/+918839…, one `opted_out`). "Run, call all corporates, yes" → agent dials ≤3 OTHER numbers (or the LLM never re-called run_campaign with confirmed=true); the founder's own phone NEVER rings → he thinks "nothing happened." Leads are flat tenant-wide, NOT linked per-campaign, so "all corporates" has no segment → falls to `all` over the tiny pool.

## 4. FULL caller.py data surface the panel uses — MISSING as voice tools
| Surface (panel route) | Voice tool today | Action |
|---|---|---|
| GET `/campaigns` (list ALL) | **MISSING** | ADD `list_all_campaigns()` (name/status/id, count) |
| GET `/campaigns/{id}` (detail) | **MISSING** | ADD `campaign_detail(name)` → resolve+unwrap `.campaign` |
| GET `/leads` (counts) | ✅ check_leads | keep; add per-campaign phrasing only |
| GET `/calls?limit` (recent/outcomes) | ✅ recent_calls | keep; add outcome/campaign filter |
| GET `/stats` (analytics) | ✅ analytics | keep |
| GET `/analytics?campaign_id` (per-camp) | **MISSING** | ADD `campaign_analytics(name)` |
| GET `/wallet` (+ `/wallet/ledger`) | ✅ wallet_status | keep |
| GET `/billing` `/billing/overview` | **MISSING** | OPTIONAL ADD `billing_summary()` |
| POST `/run` (execute) | ✅ run_campaign | keep; FIX audience (see 5) |

## 5. EXACT fixes to make it adaptive + non-hallucinating + actually dial
1. **ADD 2 read tools** (highest impact): `list_all_campaigns` (→ speaks all 8 names+status) and `campaign_detail(campaign)` (resolve_campaign + unwrap `.campaign`, speak status/goal/language/window). Add `campaign_analytics(campaign)` for per-campaign numbers.
2. **NO-HALLUCINATION instruction block** (add to `_build_instructions` manager branch): "You have FULL read access to this account. For ANY fact, number, name, status, count or list — campaigns, leads, calls, analytics, wallet — you MUST call a tool and read back ONLY what it returns. NEVER invent or guess a campaign name, count, or result. If a tool returns nothing or errors, SAY SO plainly ('I don't see any campaigns by that name / I couldn't pull that'). If asked something with no tool, say you can't fetch that yet — do not fabricate."
3. **Enumerate-before-resolve:** when caller names a campaign, prefer `list_all_campaigns` then match, so it never confuses the 3 identical "Premium 2/3BHK" entries.
4. **EXECUTION fix:** the dial mechanism works; the real miss is (a) founder isn't a lead so he never feels it, and (b) "corporates"/free-text segment isn't mapped. Map unknown segments → `all`/`source_mode=all use_stored=1` (preview proved count:3), and on a confirmed run RETURN the actual `count` + the leads' numbers so the agent can say "I'm dialing 3 leads: …" honestly (set expectation it dials the LEADS, not the caller). Optionally add a `test_call_me` action that dials the verified caller_id for the "did it work" check.

## 6. Tenant note (secondary, not blocking)
Voice auths as admin `FamitCall2026` → `/campaigns` & `/leads` are tenant-WIDE (founder==admin here so it's correct for him, but it would leak other tenants for a non-admin manager). For now founder=admin so data is right; keep on the radar for multi-tenant managers (scope by token act-as, not the global admin cred).
