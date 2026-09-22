import { Wordmark } from "@/components/brand/Wordmark";
import { AuthPlate } from "@/components/landing/AuthPlate";
import { ForceLightTheme } from "@/components/landing/ForceLightTheme";
import { HeroDrone } from "@/components/landing/HeroDrone";
import { LoginButtons } from "@/components/LoginButtons";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { getAuthenticatedUser } from "@/lib/supabase/server";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Log in — nfinit",
};
export const dynamic = "force-dynamic";

// Thin space before units (spec §3).
const T = "\u2009";

function safeNextPath(value: string | string[] | undefined): string {
  const path = Array.isArray(value) ? value[0] : value;
  return path?.startsWith("/") && !path.startsWith("//") ? path : "/studio";
}

/** The prompt a visitor typed on the landing page, carried through `next`. */
function carriedPrompt(nextPath: string): string | null {
  try {
    const prompt = new URL(nextPath, "http://nfinit.local").searchParams.get(
      "prompt",
    );
    return prompt?.trim() ? prompt.trim().slice(0, 200) : null;
  } catch {
    return null;
  }
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{
    next?: string | string[];
    error?: string | string[];
  }>;
}) {
  const params = await searchParams;
  const nextPath = safeNextPath(params.next);

  if (!isSupabaseConfigured()) {
    redirect(nextPath);
  }

  const user = await getAuthenticatedUser();
  if (user) {
    redirect(nextPath);
  }

  const error = Array.isArray(params.error) ? params.error[0] : params.error;
  const prompt = carriedPrompt(nextPath);

  return (
    <div className="wb grid min-h-dvh grid-cols-1 lg:grid-cols-12">
      <ForceLightTheme />
      <AuthPlate
        className="h-[220px] rounded-none lg:col-span-7 lg:h-auto"
        label="Plate 01 · 5-inch quad frame"
        hint="Drag to spin"
        spec={`PETG · 220${T}mm · 2h 40m`}
        halted={Boolean(error)}
      >
        <HeroDrone />
      </AuthPlate>

      <main className="flex min-w-0 flex-col px-4 pb-6 pt-5 sm:px-8 lg:col-span-5 lg:px-12">
        <header className="flex h-8 items-center">
          <Wordmark />
        </header>

        <section className="my-auto flex w-full max-w-[360px] flex-col gap-7 py-12">
          <h1
            className="type-h1"
            style={{ fontSize: "clamp(40px, 4.4vw, 56px)" }}
          >
            Come make <em>something.</em>
          </h1>

          {prompt && (
            <blockquote className="type-quote line-clamp-2 border-l border-[var(--hairline-strong)] pl-4 text-[24px] text-[var(--ink-2)]">
              “{prompt}”
            </blockquote>
          )}

          <LoginButtons nextPath={nextPath} initialError={error ?? null} />

          <p className="type-caption">New here? Same buttons.</p>
        </section>

        <footer>
          <p className="type-label">Terms · Privacy</p>
        </footer>
      </main>
    </div>
  );
}
