// Custom proxy for the SLOW Script Studio endpoints (script/generate + script/generate-block).
//
// WHY THIS EXISTS: the panel's /api/* calls normally go through next.config.ts `rewrites()`, but
// Next.js's built-in rewrite proxy resets the upstream connection after ~30s. AI script drafting
// (Claude Sonnet 4.6 via OpenRouter) legitimately takes ~30-40s, so the rewrite path returned
// http_500 ("socket hang up" / ECONNRESET) mid-generation. next.config.ts uses `fallback` rewrites
// so this filesystem route wins for these two paths; it proxies with `fetch` — Node 20's undici
// tolerates long responses (verified: a 38s upstream completes cleanly).
//
// AUTH: it MUST forward the request as transparently as the built-in rewrite, or the backend 401s
// and the panel logs the operator out. So we forward ALL incoming headers (minus hop-by-hop) incl.
// the session cookie, and relay the backend's Set-Cookie(s) + content-type back.
import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_ORIGIN || "http://127.0.0.1:8091";
const REQ_DROP = new Set(["host", "connection", "content-length", "transfer-encoding", "accept-encoding"]);

async function proxy(req: NextRequest, cid: string, action: string): Promise<Response> {
  const url =
    `${BACKEND}/campaigns/${encodeURIComponent(cid)}/script/${encodeURIComponent(action)}` +
    (req.nextUrl.search || "");

  // forward ALL request headers (cookie/auth/etc.) except hop-by-hop — mirrors the rewrite proxy
  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!REQ_DROP.has(key.toLowerCase())) headers.set(key, value);
  });
  // belt-and-suspenders: ensure the session cookie is present even if it wasn't on the raw header
  if (!headers.has("cookie")) {
    const c = req.cookies.toString();
    if (c) headers.set("cookie", c);
  }

  const init: RequestInit = { method: req.method, headers, redirect: "manual" };
  if (req.method !== "GET" && req.method !== "HEAD") init.body = await req.text();

  try {
    const res = await fetch(url, init); // undici: no ~30s cap, unlike the Next rewrite proxy
    const buf = await res.arrayBuffer();
    const out = new Headers();
    const ct = res.headers.get("content-type");
    if (ct) out.set("content-type", ct);
    // relay session refresh cookies faithfully (getSetCookie keeps them un-collapsed)
    const setCookies = (res.headers as { getSetCookie?: () => string[] }).getSetCookie?.() ?? [];
    for (const c of setCookies) out.append("set-cookie", c);
    out.set("x-haptica-proxy", "fetch");
    // eslint-disable-next-line no-console
    console.log(`[script-proxy] ${action} cid=${cid} cookie=${headers.has("cookie")} -> ${res.status}`);
    return new Response(buf, { status: res.status, headers: out });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    // eslint-disable-next-line no-console
    console.log(`[script-proxy] ${action} cid=${cid} ERROR ${msg}`);
    return new Response(JSON.stringify({ ok: false, error: "proxy_failed", message: msg }), {
      status: 502,
      headers: { "content-type": "application/json" },
    });
  }
}

type Ctx = { params: Promise<{ cid: string; action: string }> };

export async function POST(req: NextRequest, ctx: Ctx): Promise<Response> {
  const { cid, action } = await ctx.params;
  return proxy(req, cid, action);
}

export async function GET(req: NextRequest, ctx: Ctx): Promise<Response> {
  const { cid, action } = await ctx.params;
  return proxy(req, cid, action);
}
