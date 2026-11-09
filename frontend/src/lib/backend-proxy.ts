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

/**
 * Nfinit is a local, single-user app: the API is only for the person on this
 * machine. Never on a Vercel deployment, whatever the variable says: every
 * visitor would share one user and run code on the backend.
 */
function localAuthBypassEnabled() {
  const explicit = process.env.NFNIT_ALLOW_LOCAL_AUTH_BYPASS;
  if (process.env.VERCEL) return false;
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

/** Binary types that Vercel's CDN leaves uncompressed. */
const COMPRESSIBLE_TYPES = [
  "model/gltf-binary",
  "model/stl",
  "application/step",
  "application/octet-stream",
];

function shouldCompress(request: Request, response: globalThis.Response): boolean {
  const accepts = request.headers.get("accept-encoding") ?? "";
  const type = (response.headers.get("content-type") ?? "").split(";")[0].trim();
  const length = Number(response.headers.get("content-length") ?? "0");
  return (
    /\bgzip\b/.test(accepts) &&
    COMPRESSIBLE_TYPES.includes(type) &&
    !response.headers.has("content-encoding") &&
    // Tiny bodies gain nothing; an unknown length is worth compressing.
    (length === 0 || length >= 1024)
  );
}

/** Forward a request to the local backend. */
export async function proxyToBackend(
  request: Request,
  segments: string[],
  // Runs are started and polled, never held open, so 30s is generous. The
  // sandbox routes pass more: a cold OpenCASCADE import alone can take 90s.
  timeoutMs = 30_000
): Promise<Response> {
  // Another website open in the same browser can send requests to this local
  // server, so a request that changes data must come from this origin (CSRF).
  if (!["GET", "HEAD"].includes(request.method) && !isSameOrigin(request)) {
    return Response.json({ detail: "Cross-site request refused." }, { status: 403 });
  }

  const backendPath = segments.map(encodeURIComponent).join("/");
  const target = new URL(backendPath, `${BACKEND_URL}/`);
  target.search = new URL(request.url).search;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  // Ask the backend for plain bytes. Node's fetch would decode a gzipped body
  // but keep its compressed Content-Length; this proxy compresses for the
  // browser itself (below), and Vercel compresses JSON.
  headers.set("Accept-Encoding", "identity");
  // Private launcher token never reaches browser JavaScript or a public build.
  if (process.env.NFNIT_LOCAL_AGENTS === "true" && process.env.NFNIT_LOCAL_TOKEN) {
    headers.set("X-Nfinit-Local-Token", process.env.NFNIT_LOCAL_TOKEN);
  }

  if (!localAuthBypassEnabled()) {
    return Response.json(
      { detail: "The Nfinit API runs only in the local workspace (npm run local)." },
      { status: 503 }
    );
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
    for (const name of [
      "content-type",
      "content-length",
      "cache-control",
      "content-disposition",
    ]) {
      const value = response.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    // Stream model files instead of copying up to hundreds of megabytes into
    // the Vercel function's heap. 204/304 must not carry a body.
    let responseBody =
      response.status === 204 || response.status === 304
        ? null
        : response.body;
    // Vercel's CDN compresses JSON and text but not models or exports, which
    // shrink to about 30%. Compress those here, as a stream.
    if (responseBody && shouldCompress(request, response)) {
      responseBody = responseBody.pipeThrough(new CompressionStream("gzip"));
      responseHeaders.delete("content-length");
      responseHeaders.set("content-encoding", "gzip");
      responseHeaders.set("vary", "Accept-Encoding");
    }
    return new Response(responseBody, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (error) {
    if (error instanceof RangeError && error.message === "request_body_too_large") {
      return Response.json({ detail: "The request is too large." }, { status: 413 });
    }
    console.error(
      "Backend proxy request failed:",
      error instanceof Error ? error.name : "unknown error"
    );
    return Response.json({ detail: "Could not reach the backend." }, { status: 502 });
  }
}
