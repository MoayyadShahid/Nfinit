import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createSupabaseServerClient } from "@/lib/supabase/server";

const BACKEND_URL =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "http://localhost:8000";

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

function localAuthBypassEnabled() {
  const explicit = process.env.NFNIT_ALLOW_LOCAL_AUTH_BYPASS;
  if (explicit !== undefined) {
    return ["1", "true", "yes", "on"].includes(explicit.trim().toLowerCase());
  }
  return process.env.NODE_ENV !== "production";
}

async function proxy(request: Request, context: RouteContext) {
  const { path = [] } = await context.params;
  const backendPath = ["projects", ...path.map(encodeURIComponent)].join("/");
  const target = new URL(backendPath, `${BACKEND_URL.replace(/\/$/, "")}/`);
  target.search = new URL(request.url).search;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);

  if (!isSupabaseConfigured() && !localAuthBypassEnabled()) {
    return Response.json(
      { detail: "Production project authentication is not configured." },
      { status: 503 }
    );
  }

  if (isSupabaseConfigured()) {
    const supabase = await createSupabaseServerClient();
    if (!supabase) {
      return Response.json({ detail: "Authentication required." }, { status: 401 });
    }
    const { data: userData } = await supabase.auth.getUser();
    const { data: sessionData } = await supabase.auth.getSession();
    const accessToken = sessionData.session?.access_token;
    if (!userData.user || !accessToken) {
      return Response.json({ detail: "Authentication required." }, { status: 401 });
    }
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  try {
    const response = await fetch(target, {
      method: request.method,
      headers,
      body:
        request.method === "GET" || request.method === "HEAD"
          ? undefined
          : await request.arrayBuffer(),
      cache: "no-store",
      signal: AbortSignal.timeout(180_000),
    });
    const responseHeaders = new Headers();
    const responseType = response.headers.get("content-type");
    if (responseType) responseHeaders.set("Content-Type", responseType);
    return new Response(await response.arrayBuffer(), {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (error) {
    return Response.json(
      {
        detail:
          error instanceof Error
            ? `Could not reach the project backend: ${error.message}`
            : "Could not reach the project backend.",
      },
      { status: 502 }
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
