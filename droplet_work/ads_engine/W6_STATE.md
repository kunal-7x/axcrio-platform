# W6 — leads + consent/NCPR pre-dial gate + fail-closed webhook + lead->call enqueue

Branch worktree: feat/elevatex-ad-engine. FEATURE_ADS default OFF.

## Deliverables
- [ ] compliance.py — fail-CLOSED pre_dial_gate (dual consent DPDP+DCA; DCA voice = DLT/OTP only,
      reject method:form_checkbox; quiet-hours-computed force_window; NCPR scrub fail-closed;
      append-only hash-chained consent ledger + verify + retention/erasure/72h-breach hooks).
      PERMISSIVE DEFAULT UNSHIPPABLE: assert_fail_closed() at import/build.
- [ ] leads.py — ingest (meta_leadgen / form-token / ctwa / bulk_import) -> normalize -> server-mint
      lead_id -> pre_dial_gate -> enqueue (dry-run til 140-series). Tenant clamps from caller:5752.
- [ ] endpoints.py — inbound webhook (page_id->tenant->app_secret->HMAC raw body fail-closed->parse;
      reject unknown page_id; log type only) + consent capture/view/revoke + form-token route.
- [ ] store.py — page_tenant_map (uniqueness + ownership) + per-tenant append-only consent_ledger file.
- [ ] caller.py — MINIMIZE. Decision: tag JOBS row source=ad + skip ad-source in retry re-enqueue.
- [ ] offline tests + W1/W3/W4/W5 smokes still pass.

## Key code facts (verified on disk)
- caller.py:5754-5768 — /run JOBS shape; :5752 conc clamp = max(1,min(c,20,tenant.max_concurrency));
  tenant daily from rec daily_call_cap (8969). hourly_cap 200, concurrency 1 for single-lead jobs.
- caller.py:3268 run_job reads JOBS[jid]; force_window at :3306 sets in_win=True unconditionally.
- caller.py:3379-3391 rec (CALLS row) built inline; does NOT carry job provenance.
- RETRY BYPASS (redteam C1): ad-lead CALLS row -> reconciliation sweep (:9077-9114) re-enqueues
  retry via _enqueue_retry / _cb_enqueue_smart keyed on the CALLS row. The CALLS row has no ad tag.
  => minimal FEATURE_ADS guard: stamp rec["ads_source"] from job, and skip retry-enqueue when set.
- wire() already injects JOBS, run_job, _tenant_by_id, ACTIVE_CALLS (caller.py:9221-9229). GOOD.
- meta connector has verify_webhook_signature(app_secret, raw_body, sig) + parse_leadgen(payload).
- vault_adapter.get_secret_json(t, def) -> dict; field_aliased(blob, "app_secret") for HMAC key.

## Caller edit decision
PREFER: stamp rec["ads_source"]=job.get("ads_source") in run_job's record-build, then in the
reconcile sweep skip retry/callback enqueue when c.get("ads_source"). BOTH additive + FEATURE_ADS
gated. byte-identical when FEATURE_ADS=0 (guard reads ads_source only present when ads enqueued).
Actually: the cleanest is to make the guard read `_ADS_SKIP_RETRY = FEATURE_ADS and c.get("ads_source")`.
When FEATURE_ADS=0 no ads job exists so c never has ads_source -> byte-identical behavior anyway,
but gate on FEATURE_ADS too for a hard one-line revert.
</content>
