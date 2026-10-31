const FALLBACK = "/studio";
const BASE = "https://nfinit.invalid";

/**
 * A same-site path to return to after sign-in, or "/studio".
 *
 * Browsers treat "\" like "/", so "/\evil.example" leaves the site; the path
 * is resolved like a browser would and kept only if it stays on this origin.
 */
export function safeNextPath(value: string | string[] | null | undefined): string {
  const path = Array.isArray(value) ? value[0] : value;
  if (!path || !path.startsWith("/") || /[\\\u0000-\u001f\u007f]/.test(path)) {
    return FALLBACK;
  }
  try {
    const resolved = new URL(path, BASE);
    if (resolved.origin !== BASE) return FALLBACK;
    return `${resolved.pathname}${resolved.search}${resolved.hash}`;
  } catch {
    return FALLBACK;
  }
}
