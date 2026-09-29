/**
 * Base URLs for the FastAPI CAD backend, normalised once.
 *
 * Env values are often pasted with a trailing slash (Railway shows the domain
 * as `https://…up.railway.app/`). Joined as `${base}/cad/run`, that becomes
 * `…app//cad/run`, which FastAPI answers with 404, so every studio request
 * failed in production while working locally. Strip whitespace and slashes.
 */
function normalise(url: string | undefined): string | undefined {
  const trimmed = url?.trim().replace(/\/+$/, "");
  return trimmed || undefined;
}

const LOCAL_BACKEND = "http://localhost:8000";

/** For code that runs in the browser (inlined at build time). */
export const PUBLIC_BACKEND_URL =
  normalise(process.env.NEXT_PUBLIC_BACKEND_URL) ?? LOCAL_BACKEND;

/** For route handlers. Prefers the server-only BACKEND_URL. */
export function serverBackendUrl(): string {
  return (
    normalise(process.env.BACKEND_URL) ??
    normalise(process.env.NEXT_PUBLIC_BACKEND_URL) ??
    LOCAL_BACKEND
  );
}
