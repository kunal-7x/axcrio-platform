"""obs_query — read-only ClickHouse analytics for Haptica's native, white-labeled observability
dashboards (System Logs traces/requests + Performance APM panels).

The voice/telemetry data lives in the observability droplet's ClickHouse (fed by the OTel
collector). The backend queries it over HTTP (CLICKHOUSE_URL, restricted to haptica-prod by the
obs DOCKER-USER firewall). ALL queries are READ-ONLY and parameterized — string inputs (service,
trace_id, search) are bound via ClickHouse HTTP params ({name:String}); numeric inputs are
clamped to ints server-side. There is NO raw-SQL-from-client path. Every function degrades to
{"error": "...", "rows": []} and never raises, so a metrics hiccup can't break the panel.
"""
from __future__ import annotations

import json
import os

import httpx

# Performance (APM) source — self-hosted HTTP request telemetry written by the backend's
# http_metrics.py into the default db. Replaces the SigNoz signoz_traces.* source (not deployed).
HTTP = "haptica_http_requests"

# P1 Voice Performance Analytics tables (default db; written by the agent's voice_analytics.py).
VOICE_TURNS = "haptica_voice_turns"
VOICE_CALLS = "haptica_voice_calls"
VOICE_KEY_USAGE = "haptica_provider_key_usage"  # P2.2: per-key provider usage (cross-process)


def _url() -> str:
    return (os.getenv("CLICKHOUSE_URL", "") or "").strip().rstrip("/")


def _clamp(v, lo, hi, default) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except Exception:  # noqa: BLE001
        return default


def _step_for(minutes: int) -> int:
    """A sensible time-bucket (seconds) for the requested window — ~60-120 points."""
    if minutes <= 60:
        return 60
    if minutes <= 360:
        return 300
    if minutes <= 1440:
        return 900
    if minutes <= 10080:
        return 3600
    return 21600


async def _ch(sql: str, params: dict | None = None) -> dict:
    base = _url()
    if not base:
        return {"error": "metrics backend not configured", "rows": []}
    try:
        async with httpx.AsyncClient(timeout=20.0) as c:
            # readonly=2 forbids DDL/DML at the SESSION level (defense-in-depth: even if a query
            # string were ever wrong, the connection cannot write/drop), + hard execution/row caps.
            r = await c.post(base + "/", content=sql.encode("utf-8"),
                             params={**(params or {}), "default_format": "JSONEachRow",
                                     "readonly": "2", "max_execution_time": "30",
                                     "max_result_rows": "200000", "result_overflow_mode": "break"})
        if r.status_code != 200:
            return {"error": (r.text or "")[:300].strip(), "rows": []}
        rows = []
        for ln in r.text.splitlines():
            ln = ln.strip()
            if ln:
                try:
                    rows.append(json.loads(ln))
                except Exception:  # noqa: BLE001
                    pass
        return {"rows": rows}
    except Exception:  # noqa: BLE001
        return {"error": "metrics backend unreachable", "rows": []}


# WHERE fragment shared by most queries: time window + optional service filter (bound param).
def _scope(minutes: int) -> str:
    return (f"ts > now() - INTERVAL {minutes} MINUTE "
            f"AND ({{svc:String}} = '' OR service = {{svc:String}})")


async def services(minutes: int = 1440) -> dict:
    m = _clamp(minutes, 1, 43200, 1440)
    return await _ch(
        f"SELECT service, count() AS calls FROM {HTTP} "
        f"WHERE ts > now() - INTERVAL {m} MINUTE AND service != '' "
        f"GROUP BY service ORDER BY calls DESC LIMIT 100")


async def summary(minutes: int = 60, service: str = "") -> dict:
    m = _clamp(minutes, 1, 43200, 60)
    r = await _ch(
        f"SELECT count() AS calls, countIf(has_error) AS errors, "
        f"round(countIf(has_error)/greatest(count(),1)*100, 2) AS err_pct, "
        f"round(count()/({m}*60), 3) AS rps, "
        f"round(quantile(0.50)(duration_ms), 2) AS p50, "
        f"round(quantile(0.95)(duration_ms), 2) AS p95, "
        f"round(quantile(0.99)(duration_ms), 2) AS p99 "
        f"FROM {HTTP} WHERE {_scope(m)}",
        {"param_svc": service})
    r["row"] = (r.get("rows") or [{}])[0]
    return r


async def red_timeseries(minutes: int = 60, service: str = "") -> dict:
    m = _clamp(minutes, 1, 43200, 60)
    step = _step_for(m)
    return await _ch(
        f"SELECT toUnixTimestamp(toStartOfInterval(ts, INTERVAL {step} SECOND)) AS t, "
        f"count() AS calls, countIf(has_error) AS errors, "
        f"round(quantile(0.50)(duration_ms), 2) AS p50, "
        f"round(quantile(0.95)(duration_ms), 2) AS p95, "
        f"round(quantile(0.99)(duration_ms), 2) AS p99 "
        f"FROM {HTTP} WHERE {_scope(m)} GROUP BY t ORDER BY t",
        {"param_svc": service})


async def top_routes(minutes: int = 60, service: str = "", limit: int = 50) -> dict:
    m = _clamp(minutes, 1, 43200, 60)
    lim = _clamp(limit, 1, 500, 50)
    return await _ch(
        f"SELECT method, route, count() AS calls, "
        f"round(countIf(has_error)/greatest(count(),1)*100, 2) AS err_pct, "
        f"round(quantile(0.50)(duration_ms), 2) AS p50, "
        f"round(quantile(0.95)(duration_ms), 2) AS p95, "
        f"round(quantile(0.99)(duration_ms), 2) AS p99 "
        f"FROM {HTTP} WHERE {_scope(m)} AND route != '' "
        f"GROUP BY method, route ORDER BY calls DESC LIMIT {lim}",
        {"param_svc": service})


async def status_dist(minutes: int = 60, service: str = "") -> dict:
    m = _clamp(minutes, 1, 43200, 60)
    return await _ch(
        f"SELECT toString(status_code) AS code, count() AS calls FROM {HTTP} "
        f"WHERE {_scope(m)} AND status_code != 0 "
        f"GROUP BY code ORDER BY calls DESC LIMIT 30",
        {"param_svc": service})


async def service_dist(minutes: int = 60) -> dict:
    m = _clamp(minutes, 1, 43200, 60)
    return await _ch(
        f"SELECT service, count() AS calls, countIf(has_error) AS errors "
        f"FROM {HTTP} WHERE ts > now() - INTERVAL {m} MINUTE AND service != '' "
        f"GROUP BY service ORDER BY calls DESC LIMIT 30")


async def error_ops(minutes: int = 60, service: str = "", limit: int = 20) -> dict:
    m = _clamp(minutes, 1, 43200, 60)
    lim = _clamp(limit, 1, 100, 20)
    return await _ch(
        f"SELECT concat(method, ' ', route) AS op, service, count() AS calls, "
        f"toUnixTimestamp64Milli(max(ts)) AS last_ms "
        f"FROM {HTTP} WHERE {_scope(m)} AND has_error = 1 "
        f"GROUP BY op, service ORDER BY calls DESC LIMIT {lim}",
        {"param_svc": service})


async def traces(minutes: int = 60, service: str = "", errors_only: int = 0,
                 q: str = "", limit: int = 60) -> dict:
    # Each HTTP request is one row (trace_id unique), modelled as a single-span trace so the panel's
    # trace list works without a full distributed-tracing backend.
    m = _clamp(minutes, 1, 43200, 60)
    lim = _clamp(limit, 1, 200, 60)
    eo = 1 if str(errors_only) in ("1", "true", "True", "yes") else 0
    return await _ch(
        f"SELECT trace_id, "
        f"any(service) AS root_service, "
        f"any(concat(method, ' ', route)) AS root_name, "
        f"round(max(duration_ms), 2) AS duration_ms, "
        f"count() AS span_count, countIf(has_error) AS error_count, "
        f"toUnixTimestamp64Milli(max(ts)) AS ts_ms "
        f"FROM {HTTP} WHERE {_scope(m)} AND trace_id != '' "
        f"GROUP BY trace_id "
        f"HAVING ({eo} = 0 OR error_count > 0) "
        f"AND ({{q:String}} = '' OR root_name ILIKE concat('%', {{q:String}}, '%') "
        f"OR trace_id LIKE concat({{q:String}}, '%')) "
        f"ORDER BY ts_ms DESC LIMIT {lim}",
        {"param_svc": service, "param_q": q})


async def trace_detail(trace_id: str) -> dict:
    # Single-span "trace": the one request row, shaped like a span so the waterfall panel renders it.
    # start_us (microseconds) stays within JS safe-integer range; duration in nanoseconds for the panel.
    return await _ch(
        f"SELECT trace_id AS span_id, '' AS parent_span_id, concat(method, ' ', route) AS name, "
        f"service, toUnixTimestamp64Micro(ts) AS start_us, "
        f"toUInt64(duration_ms * 1000000) AS duration_nano, "
        f"has_error, 'server' AS kind, method AS http_method, route AS http_route, "
        f"toString(status_code) AS status_code, '' AS status_message "
        f"FROM {HTTP} WHERE trace_id = {{tid:String}} ORDER BY ts ASC LIMIT 1000",
        {"param_tid": (trace_id or "").strip()})


# ════════════════════════════════════════════════════════════════════════════════════════════════
# P1 VOICE PERFORMANCE ANALYTICS — reads over the agent-written haptica_voice_* tables. Same laws
# as the trace queries: READ-ONLY, every string filter bound as a ClickHouse param, numbers clamped,
# and every fn degrades to {"error": ..., "rows": []} (via _ch) so a metrics gap never breaks the page.
# ════════════════════════════════════════════════════════════════════════════════════════════════

def _vwhere(minutes: int, f: dict | None, table: str) -> tuple[int, str, dict]:
    """Shared WHERE + bound-params for the voice tables. Only adds a clause (and binds its param)
    when a filter value is actually present, so we never reference an unbound param."""
    m = _clamp(minutes, 1, 43200, 60)
    f = f if isinstance(f, dict) else {}
    parts = [f"ts > now() - INTERVAL {m} MINUTE"]
    params: dict = {}

    def add(key: str, expr: str) -> None:
        val = str(f.get(key, "") or "").strip()
        if val:
            parts.append(expr.format(p=key))
            params[f"param_{key}"] = val

    add("tenant_id", "tenant_id = {{{p}:String}}")
    add("campaign_id", "campaign_id = {{{p}:String}}")
    add("agent_name", "agent_name = {{{p}:String}}")
    add("phone", "phone = {{{p}:String}}")
    add("provider", "{{{p}:String}} IN (stt_provider, llm_provider, tts_provider)")
    add("model", "{{{p}:String}} IN (stt_model, llm_model, tts_model)")
    if table == "calls":
        add("status", "status = {{{p}:String}}")
    return m, " AND ".join(parts), params


async def voice_summary(minutes: int = 60, filters: dict | None = None) -> dict:
    """Live-dashboard KPIs: call volume, avg duration, success/error rate, token + 429 totals, and
    the P50/P95/P99 latency per stage (eou/stt/llm/tts)."""
    f = filters or {}
    _m, where, params = _vwhere(minutes, f, "calls")
    r = await _ch(
        f"SELECT count() AS calls, round(avg(duration_ms) / 1000, 1) AS avg_dur_s, "
        f"sum(turns) AS total_turns, countIf(status != 'completed') AS failed, "
        f"round(countIf(status = 'completed') / greatest(count(), 1) * 100, 1) AS success_pct, "
        f"round(countIf(status != 'completed') / greatest(count(), 1) * 100, 2) AS error_pct, "
        f"sum(rate_limit_429) AS rate_limits, sum(errors) AS errors, "
        f"sum(in_tokens) AS in_tokens, sum(out_tokens) AS out_tokens "
        f"FROM {VOICE_CALLS} WHERE {where}", params)
    r["row"] = (r.get("rows") or [{}])[0]
    _mt, wheret, pt = _vwhere(minutes, f, "turns")
    lat = await _ch(
        f"SELECT stage, count() AS n, round(avg(latency_ms), 0) AS avg, "
        f"round(quantile(0.50)(latency_ms), 0) AS p50, "
        f"round(quantile(0.95)(latency_ms), 0) AS p95, "
        f"round(quantile(0.99)(latency_ms), 0) AS p99 "
        f"FROM {VOICE_TURNS} WHERE {wheret} GROUP BY stage", pt)
    r["latency_by_stage"] = lat.get("rows", [])
    return r


async def voice_red_timeseries(minutes: int = 60, filters: dict | None = None) -> dict:
    """Bucketed P50/P95/P99 of ONE stage's latency (default 'llm' = the user-perceived response
    latency; set filters['stage'] to chart stt/tts/eou) + event volume per bucket."""
    f = filters or {}
    m, where, params = _vwhere(minutes, f, "turns")
    step = _step_for(m)
    params["param_stage_pin"] = (str(f.get("stage", "") or "").strip() or "llm")
    return await _ch(
        f"SELECT toUnixTimestamp(toStartOfInterval(ts, INTERVAL {step} SECOND)) AS t, "
        f"count() AS events, round(quantile(0.50)(latency_ms), 0) AS p50, "
        f"round(quantile(0.95)(latency_ms), 0) AS p95, round(quantile(0.99)(latency_ms), 0) AS p99 "
        f"FROM {VOICE_TURNS} WHERE {where} AND stage = {{stage_pin:String}} "
        f"GROUP BY t ORDER BY t", params)


async def voice_calls(minutes: int = 60, filters: dict | None = None, limit: int = 100) -> dict:
    """The filterable call list (header rows), newest first."""
    f = filters or {}
    _m, where, params = _vwhere(minutes, f, "calls")
    lim = _clamp(limit, 1, 1000, 100)
    return await _ch(
        f"SELECT call_id, toUnixTimestamp64Milli(ts) AS ts_ms, tenant_id, campaign_id, agent_name, "
        f"phone, lead_name, stt_provider, llm_provider, tts_provider, stt_model, llm_model, tts_model, "
        f"voice_id, voice_name, language, duration_ms, status, outcome, turns, rate_limit_429, errors, "
        f"in_tokens, out_tokens, net_quality "
        f"FROM {VOICE_CALLS} WHERE {where} ORDER BY ts DESC LIMIT {lim}", params)


async def voice_call_detail(call_id: str, tenant_id: str = "") -> dict:
    """One call's header row — full pipeline picture (who we called + every provider+version + net).
    Scoped to tenant_id when non-empty (full tenant isolation); '' = unscoped (legacy)."""
    return await _ch(
        f"SELECT call_id, toUnixTimestamp64Milli(ts) AS ts_ms, toUnixTimestamp64Milli(ended_at) AS ended_ms, "
        f"tenant_id, campaign_id, agent_name, phone, lead_name, stt_provider, llm_provider, tts_provider, "
        f"stt_model, llm_model, tts_model, voice_id, voice_name, language, duration_ms, status, outcome, turns, "
        f"llm_calls, tts_calls, stt_calls, rate_limit_429, errors, in_tokens, out_tokens, "
        f"speech_ms, characters, net_quality, net_rtt_ms, net_packet_loss "
        f"FROM {VOICE_CALLS} WHERE call_id = {{cid:String}} "
        f"AND ({{tid:String}} = '' OR tenant_id = {{tid:String}}) ORDER BY ts DESC LIMIT 1",
        {"param_cid": (call_id or "").strip(), "param_tid": (tenant_id or "").strip()})


async def voice_call_latency(call_id: str, tenant_id: str = "") -> dict:
    """Per-call RESPONSE-latency rollup the operator asked for: each turn's response latency = SUM of
    its stage latencies (eou+stt+llm+tts); returns AVG / MEDIAN / TOTAL / P95 / MAX across turns."""
    r = await _ch(
        f"SELECT count() AS turns, round(avg(turn_total), 0) AS avg_ms, "
        f"round(quantile(0.5)(turn_total), 0) AS median_ms, round(sum(turn_total), 0) AS total_ms, "
        f"round(quantile(0.95)(turn_total), 0) AS p95_ms, round(max(turn_total), 0) AS max_ms "
        f"FROM (SELECT turn_index, sum(latency_ms) AS turn_total FROM {VOICE_TURNS} "
        f"WHERE call_id = {{cid:String}} AND ({{tid:String}} = '' OR tenant_id = {{tid:String}}) "
        f"AND stage IN ('eou','stt','llm','tts') GROUP BY turn_index)",
        {"param_cid": (call_id or "").strip(), "param_tid": (tenant_id or "").strip()})
    r["row"] = (r.get("rows") or [{}])[0]
    return r


async def voice_turn_timeline(call_id: str, limit: int = 2000, tenant_id: str = "") -> dict:
    """All per-stage events for ONE call, time-ordered — drives the stage timeline + sentence list.
    Scoped to tenant_id when non-empty (full tenant isolation); '' = unscoped (legacy)."""
    lim = _clamp(limit, 1, 5000, 2000)
    return await _ch(
        f"SELECT toUnixTimestamp64Milli(ts) AS ts_ms, turn_index, stage, speech_id, latency_ms, "
        f"prompt_tokens, completion_tokens, tokens_per_second, characters "
        f"FROM {VOICE_TURNS} WHERE call_id = {{cid:String}} "
        f"AND ({{tid:String}} = '' OR tenant_id = {{tid:String}}) ORDER BY ts ASC LIMIT {lim}",
        {"param_cid": (call_id or "").strip(), "param_tid": (tenant_id or "").strip()})


async def voice_stack(minutes: int = 1440, filters: dict | None = None) -> dict:
    """The AI STACK actually in use over the window: distinct STT/LLM/TTS provider+model(+voice) combos
    with call counts + last-seen, PLUS each pipeline stage's avg/p50/p95 latency, tps, chars and token
    totals. Feeds the 'Stack & Versions' panel — the complete picture of what's running and how it does."""
    f = filters or {}
    _m, where, params = _vwhere(minutes, f, "calls")
    combos = await _ch(
        f"SELECT stt_provider, stt_model, llm_provider, llm_model, tts_provider, tts_model, "
        f"voice_id, voice_name, count() AS calls, toUnixTimestamp64Milli(max(ts)) AS last_ms "
        f"FROM {VOICE_CALLS} WHERE {where} "
        f"GROUP BY stt_provider, stt_model, llm_provider, llm_model, tts_provider, tts_model, voice_id, voice_name "
        f"ORDER BY calls DESC LIMIT 50", params)
    _mt, wheret, pt = _vwhere(minutes, f, "turns")
    stages = await _ch(
        f"SELECT stage, count() AS n, round(avg(latency_ms), 0) AS avg, round(quantile(0.5)(latency_ms), 0) AS p50, "
        f"round(quantile(0.95)(latency_ms), 0) AS p95, round(avg(nullIf(tokens_per_second, 0)), 1) AS tps, "
        f"sum(characters) AS chars, sum(prompt_tokens) AS in_tok, sum(completion_tokens) AS out_tok "
        f"FROM {VOICE_TURNS} WHERE {wheret} GROUP BY stage", pt)
    return {"combos": combos.get("rows", []), "stages": stages.get("rows", []),
            "error": combos.get("error") or stages.get("error", "")}


async def voice_filter_options(minutes: int = 1440, tenant_id: str = "") -> dict:
    """Distinct values for the filter dropdowns (bounded), over the window. Scoped to tenant_id when
    non-empty (full tenant isolation) so a scoped caller's `tenants` array only ever contains its OWN
    tenant_id (no cross-tenant roster enumeration); '' = unscoped (legacy)."""
    m = _clamp(minutes, 1, 43200, 1440)
    r = await _ch(
        f"SELECT groupUniqArray(100)(agent_name) AS agents, "
        f"groupUniqArray(200)(campaign_id) AS campaigns, "
        f"groupUniqArray(50)(llm_provider) AS llm_providers, "
        f"groupUniqArray(50)(tts_provider) AS tts_providers, "
        f"groupUniqArray(50)(stt_provider) AS stt_providers, "
        f"groupUniqArray(50)(llm_model) AS models, "
        f"groupUniqArray(50)(status) AS statuses, "
        f"groupUniqArray(100)(tenant_id) AS tenants "
        f"FROM {VOICE_CALLS} WHERE ts > now() - INTERVAL {m} MINUTE "
        f"AND ({{tid:String}} = '' OR tenant_id = {{tid:String}})",
        {"param_tid": (tenant_id or "").strip()})
    r["row"] = (r.get("rows") or [{}])[0]
    return r


async def provider_key_usage(minutes: int = 1440, provider: str = "") -> dict:
    """P2.2: aggregate per-(provider, key) usage over the window — the CROSS-PROCESS truth flushed by
    the agent worker(s). Latest score/status via argMax over ts; last_used = max ts. No secrets
    (fingerprints only). Degrades to empty rows when the table/CH is absent."""
    m = _clamp(minutes, 1, 43200, 1440)
    return await _ch(
        f"SELECT provider, fingerprint, sum(calls) AS calls, sum(success) AS success, "
        f"sum(failures) AS failures, sum(rate_limits) AS rate_limits, "
        f"round(avg(latency_ms_avg), 0) AS latency_ms_avg, "
        f"round(argMax(score, ts), 3) AS score, argMax(status, ts) AS status, "
        f"round(sum(success) / greatest(sum(success) + sum(failures), 1) * 100, 1) AS success_pct, "
        f"toUnixTimestamp64Milli(max(ts)) AS last_used_ms "
        f"FROM {VOICE_KEY_USAGE} "
        f"WHERE ts > now() - INTERVAL {m} MINUTE AND ({{prov:String}} = '' OR provider = {{prov:String}}) "
        f"GROUP BY provider, fingerprint ORDER BY calls DESC LIMIT 500",
        {"param_prov": (provider or "").strip().lower()})
