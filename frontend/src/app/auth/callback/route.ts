import { isSupabaseConfigured } from "@/lib/supabase/config";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

function safeNextPath(value: string | null): string {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/studio";
}

function nextPathFromCookie(request: Request): string | null {
  const cookie = request.headers.get("cookie") ?? "";
  const match = cookie.match(/(?:^|;\s*)nfinit-auth-next=([^;]+)/);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}

function redirectHome(requestUrl: URL, path: string) {
  const response = NextResponse.redirect(new URL(path, requestUrl.origin));
  response.cookies.set("nfinit-auth-next", "", { path: "/", maxAge: 0 });
  return response;
}

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  const nextPath = safeNextPath(
    requestUrl.searchParams.get("next") ?? nextPathFromCookie(request)
  );

  if (!isSupabaseConfigured()) {
    return redirectHome(requestUrl, nextPath);
  }

  const code = requestUrl.searchParams.get("code");
  const supabase = await createSupabaseServerClient();
  if (code && supabase) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) {
      return redirectHome(requestUrl, nextPath);
    }
  }

  const loginUrl = new URL("/login", requestUrl.origin);
  loginUrl.searchParams.set("error", "oauth_callback");
  loginUrl.searchParams.set("next", nextPath);
  return redirectHome(requestUrl, `${loginUrl.pathname}${loginUrl.search}`);
}
