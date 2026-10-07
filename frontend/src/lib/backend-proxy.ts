import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createSupabaseServerClient } from "@/lib/supabase/server";

const BACKEND_URL = (
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "http://localhost:8000"
).replace(/\/$/, "");

function localAuthBypassEnabled() {
  const explicit = process.env.NFNIT_ALLOW_LOCAL_AUTH_BYPASS;
  if (explicit !== undefined) {
    return ["1", "true", "yes", "on"].includes(explicit.trim().toLowerCase());
  }
  return process.env.NODE_ENV !== "production";
}

/** Forward a request to the backend as the signed-in Supabase user. */
export async function proxyToBackend(
  request: Request,
  segments: string[],
  // Runs are started and polled, never held open, so 30s is generous. The
  // sandbox routes pass more: a cold OpenCASCADE import alone can take 90s.
  timeoutMs = 30_000
): Promise<Response> {
  const backendPath = segments.map(encodeURIComponent).join("/");
  const target = new URL(backendPath, `${BACKEND_URL}/`);
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
      signal: AbortSignal.timeout(timeoutMs),
    });
    const responseHeaders = new Headers();
    for (const name of ["content-type", "cache-control", "content-disposition"]) {
      const value = response.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    // 204/304 must not carry a body, or the Response constructor throws.
    const body =
      response.status === 204 || response.status === 304
        ? null
        : await response.arrayBuffer();
    return new Response(body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (error) {
    return Response.json(
      {
        detail:
          error instanceof Error
            ? `Could not reach the backend: ${error.message}`
            : "Could not reach the backend.",
      },
      { status: 502 }
    );
  }
}
