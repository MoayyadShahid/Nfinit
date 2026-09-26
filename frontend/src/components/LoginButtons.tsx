"use client";

import { getSupabaseBrowserClient } from "@/lib/supabase/browser";
import type { Provider } from "@supabase/supabase-js";
import { useEffect, useRef, useState } from "react";

export const AUTH_ERROR_EVENT = "nfinit:auth-error";

function safeNextPath(value: string): string {
  return value.startsWith("/") && !value.startsWith("//") ? value : "/studio";
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 48 48" className="size-4 flex-none" aria-hidden="true">
      <path
        fill="#FFC107"
        d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.1 29.3 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.4-.4-3.5z"
      />
      <path
        fill="#FF3D00"
        d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"
      />
      <path
        fill="#1976D2"
        d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z"
      />
    </svg>
  );
}

const PROVIDERS: {
  id: Provider;
  name: string;
  variant: "primary" | "secondary";
  icon: React.ReactNode;
}[] = [
  { id: "google", name: "Google", variant: "primary", icon: <GoogleIcon /> },
];

export function LoginButtons({
  nextPath,
  initialError = null,
}: {
  nextPath: string;
  initialError?: string | null;
}) {
  const [pendingProvider, setPendingProvider] = useState<Provider | null>(null);
  const [error, setError] = useState<string | null>(initialError);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!error) return;
    errorRef.current?.focus();
    window.dispatchEvent(new CustomEvent(AUTH_ERROR_EVENT));
  }, [error]);

  const signIn = async (provider: Provider) => {
    if (pendingProvider) return;
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
    <div className="flex flex-col gap-4">
      {error && (
        <div
          ref={errorRef}
          role="alert"
          tabIndex={-1}
          className="wb-error"
        >
          <p>
            <strong className="font-semibold">That didn&apos;t go through.</strong>{" "}
            Try again.
          </p>
          <details>
            <summary>Details</summary>
            <code>{error}</code>
          </details>
        </div>
      )}
      <div className="flex flex-col gap-2.5" aria-busy={pendingProvider !== null}>
        {PROVIDERS.map((provider) => {
          const pending = pendingProvider === provider.id;
          const blocked = pendingProvider !== null && !pending;
          return (
            <button
              key={provider.id}
              type="button"
              onClick={() => signIn(provider.id)}
              aria-disabled={pendingProvider !== null}
              data-sunk={pending}
              className={`wb-btn wb-btn-${provider.variant} w-full justify-start ${
                pending ? "cursor-wait" : ""
              }`}
              style={blocked ? { opacity: 0.4 } : undefined}
            >
              {pending ? (
                <span className="grid size-4 place-items-center">
                  <span className="wb-dot wb-dot-breath" />
                </span>
              ) : (
                provider.icon
              )}
              <span>
                {pending
                  ? `Opening ${provider.name}…`
                  : `Continue with ${provider.name}`}
              </span>
              <span className="wb-arrow ml-auto" aria-hidden="true">
                →
              </span>
              {pending && <span className="wb-loadline" aria-hidden="true" />}
            </button>
          );
        })}
      </div>
    </div>
  );
}
