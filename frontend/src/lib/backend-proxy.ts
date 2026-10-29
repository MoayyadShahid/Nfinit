import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createSupabaseServerClient } from "@/lib/supabase/server";

const BACKEND_URL = (
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "http://localhost:8000"
).replace(/\/$/, "");

const DEFAULT_MAX_REQUEST_BYTES = 20 * 1024 * 1024;

function maxRequestBytes(): number {
  const configured = Number.parseInt(process.env.CAD_MAX_REQUEST_BYTES ?? "", 10);
  return Number.isFinite(configured) && configured >= 1024
    ? configured
    : DEFAULT_MAX_REQUEST_BYTES;
}

async function readLimitedBody(request: Request): Promise<ArrayBuffer> {
  const limit = maxRequestBytes();
  const declared = request.headers.get("content-length");
  if (declared !== null) {
    const parsed = Number(declared);
    if (!Number.isFinite(parsed) || parsed < 0 || parsed > limit) {
      throw new RangeError("request_body_too_large");
    }
  }
  if (!request.body) return new ArrayBuffer(0);

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > limit) {
        await reader.cancel();
        throw new RangeError("request_body_too_large");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }

  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body.buffer;
}

function localAuthBypassEnabled() {
  const explicit = process.env.NFNIT_ALLOW_LOCAL_AUTH_BYPASS;
  // Never on the production deployment, whatever the variable says: the
  // bypass would sign every visitor in as one shared user.
  if (process.env.VERCEL_ENV === "production") return false;
  if (explicit !== undefined) {
    return ["1", "true", "yes", "on"].includes(explicit.trim().toLowerCase());
  }
  return process.env.NODE_ENV !== "production";
}

/** True when the browser says the request came from this site. */
function isSameOrigin(request: Request): boolean {
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite) return fetchSite === "same-origin";
  const origin = request.headers.get("origin");
  // Requests without either header come from non-browser clients, which do
  // not carry a victim's cookies.
  if (!origin) return true;
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

/** Forward a request to the backend as the signed-in Supabase user. */
export async function proxyToBackend(
  request: Request,
  segments: string[],
  // Runs are started and polled, never held open, so 30s is generous. The
  // sandbox routes pass more: a cold OpenCASCADE import alone can take 90s.
  timeoutMs = 30_000
): Promise<Response> {
  // Session cookies ride along on every request to this origin, so a request
  // that changes data must also come from this origin (CSRF protection).
  if (!["GET", "HEAD"].includes(request.method) && !isSameOrigin(request)) {
    return Response.json({ detail: "Cross-site request refused." }, { status: 403 });
  }

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
    const requestBody =
      request.method === "GET" || request.method === "HEAD"
        ? undefined
        : await readLimitedBody(request);
    const response = await fetch(target, {
      method: request.method,
      headers,
      body: requestBody,
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    const responseHeaders = new Headers();
    for (const name of ["content-type", "cache-control", "content-disposition"]) {
      const value = response.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    // 204/304 must not carry a body, or the Response constructor throws.
    const responseBody =
      response.status === 204 || response.status === 304
        ? null
        : await response.arrayBuffer();
    return new Response(responseBody, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (error) {
    if (error instanceof RangeError && error.message === "request_body_too_large") {
      return Response.json({ detail: "The request is too large." }, { status: 413 });
    }
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
