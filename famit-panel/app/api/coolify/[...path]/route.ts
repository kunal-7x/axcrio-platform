// Server-side proxy for the self-hosted Coolify PaaS API.
// Reads COOLIFY_URL and COOLIFY_API_KEY from env — never exposed to the browser.
// Returns 503 when not configured so the Studio page renders a calm setup card
// (dormant-safe, matching the platform-wide pattern).
export const runtime = "nodejs";

const COOLIFY_URL = process.env.COOLIFY_URL ?? "";
const COOLIFY_KEY = process.env.COOLIFY_API_KEY ?? "";

function notConfigured() {
    return Response.json(
        { error: "not_configured", message: "Set COOLIFY_URL and COOLIFY_API_KEY in your server env." },
        { status: 503 }
    );
}

async function proxy(req: Request, segments: string[], method: string): Promise<Response> {
    if (!COOLIFY_URL || !COOLIFY_KEY) return notConfigured();
    const path = segments.join("/");
    const search = new URL(req.url).search;
    const target = `${COOLIFY_URL.replace(/\/$/, "")}/api/v1/${path}${search}`;
    let body: string | undefined;
    if (method !== "GET" && method !== "HEAD") {
        body = await req.text().catch(() => "");
    }
    try {
        const res = await fetch(target, {
            method,
            headers: {
                Authorization: `Bearer ${COOLIFY_KEY}`,
                "Content-Type": "application/json",
                Accept: "application/json",
            },
            ...(body ? { body } : {}),
        });
        const text = await res.text();
        return new Response(text, {
            status: res.status,
            headers: { "Content-Type": "application/json" },
        });
    } catch {
        return Response.json({ error: "gateway_error", message: "Could not reach Coolify." }, { status: 502 });
    }
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: Request, { params }: Ctx) {
    return proxy(req, (await params).path, "GET");
}
export async function POST(req: Request, { params }: Ctx) {
    return proxy(req, (await params).path, "POST");
}
export async function PUT(req: Request, { params }: Ctx) {
    return proxy(req, (await params).path, "PUT");
}
export async function DELETE(req: Request, { params }: Ctx) {
    return proxy(req, (await params).path, "DELETE");
}
