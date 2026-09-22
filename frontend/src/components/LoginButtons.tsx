"use client";

import { getSupabaseBrowserClient } from "@/lib/supabase/browser";
import type { Provider } from "@supabase/supabase-js";
import { Github, Loader2 } from "lucide-react";
import { useState } from "react";

function safeNextPath(value: string): string {
  return value.startsWith("/") && !value.startsWith("//") ? value : "/studio";
}

export function LoginButtons({ nextPath }: { nextPath: string }) {
  const [pendingProvider, setPendingProvider] = useState<Provider | null>(null);
  const [error, setError] = useState<string | null>(null);

  const signIn = async (provider: Provider) => {
    const supabase = getSupabaseBrowserClient();
    if (!supabase) {
      window.location.assign("/studio");
      return;
    }

    setPendingProvider(provider);
    setError(null);
    const redirectTo = new URL("/auth/callback", window.location.origin);
    redirectTo.searchParams.set("next", safeNextPath(nextPath));

    const { error: signInError } = await supabase.auth.signInWithOAuth({
      provider,
      options: { redirectTo: redirectTo.toString() },
    });

    if (signInError) {
      setError(signInError.message);
      setPendingProvider(null);
    }
  };

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={() => signIn("google")}
        disabled={pendingProvider !== null}
        className="theme-primary-button flex h-12 w-full items-center justify-center gap-3 rounded-full text-sm font-semibold transition-transform hover:scale-[1.01] disabled:cursor-wait disabled:opacity-60"
      >
        {pendingProvider === "google" ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <span className="flex size-5 items-center justify-center text-base font-semibold">
            G
          </span>
        )}
        Continue with Google
      </button>
      <button
        type="button"
        onClick={() => signIn("github")}
        disabled={pendingProvider !== null}
        className="theme-floating flex h-12 w-full items-center justify-center gap-3 rounded-full border text-sm font-semibold transition-transform hover:scale-[1.01] disabled:cursor-wait disabled:opacity-60"
      >
        {pendingProvider === "github" ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <Github className="size-4" />
        )}
        Continue with GitHub
      </button>
      {error && (
        <p role="alert" className="text-center text-xs text-red-500">
          {error}
        </p>
      )}
    </div>
  );
}
