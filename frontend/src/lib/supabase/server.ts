import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { getSupabaseConfig, isSupabaseConfigured } from "./config";

export async function createSupabaseServerClient() {
  if (!isSupabaseConfigured()) return null;

  const config = getSupabaseConfig();
  const cookieStore = await cookies();

  return createServerClient(config.url, config.anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => {
            cookieStore.set(name, value, options);
          });
        } catch {
          // Server Components cannot write cookies. Route handlers can.
        }
      },
    },
  });
}

/** The signed-in user, as the pages need it: identity and display details. */
export type AuthenticatedUser = {
  id: string;
  email: string | null;
  user_metadata: Record<string, string | undefined>;
};

/**
 * The signed-in user, from the access token in the session cookie.
 *
 * `getClaims()` checks the token's signature and expiry locally, with
 * Supabase's public signing keys (cached across requests), so rendering a
 * page no longer waits for a call to Supabase Auth. It refreshes an expired
 * session first. A token signed with a shared secret (HS256) cannot be
 * checked locally, and then `getClaims()` asks Supabase Auth, as before.
 * Data access is still checked by the backend on every request.
 */
export async function getAuthenticatedUser(): Promise<AuthenticatedUser | null> {
  const supabase = await createSupabaseServerClient();
  if (!supabase) return null;

  try {
    const { data, error } = await supabase.auth.getClaims();
    const claims = data?.claims;
    if (error || !claims?.sub) return null;
    return {
      id: claims.sub,
      email: typeof claims.email === "string" ? claims.email : null,
      user_metadata: (claims.user_metadata ?? {}) as Record<string, string | undefined>,
    };
  } catch {
    return null;
  }
}
