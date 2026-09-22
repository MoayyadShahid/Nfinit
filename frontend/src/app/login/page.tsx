import { Wordmark } from "@/components/brand/Wordmark";
import { AuthPlate } from "@/components/landing/AuthPlate";
import { LoginButtons } from "@/components/LoginButtons";
import { ThemeToggle } from "@/components/ThemeToggle";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { getAuthenticatedUser } from "@/lib/supabase/server";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Log in — nfinit",
};
export const dynamic = "force-dynamic";

// Thin space before units (spec §3).
const T = " ";

// One of six parts prints in on each visit (spec §8).
const AUTH_PLATES = [
  { label: "Plate 02 · Cable clip", spec: `Cable clip · PETG · 4${T}min` },
  { label: "Plate 03 · Lid hinge", spec: `Lid hinge · PLA · 22${T}min` },
  { label: "Plate 04 · Pi 5 case", spec: `Pi 5 case · PLA · 1h 04` },
  { label: "Plate 05 · Fan mount", spec: `40${T}mm fan mount · PETG · 26${T}min` },
  { label: "Plate 06 · Pipe hook", spec: `Pipe hook · PETG · 38${T}min` },
  { label: "Plate 07 · M6 knob", spec: `M6 knob · PLA · 9${T}min` },
];

function pickPlate() {
  return AUTH_PLATES[Math.floor(Math.random() * AUTH_PLATES.length)];
}

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
  const plate = pickPlate();

  return (
    <div className="wb wb-grain grid min-h-dvh grid-cols-1 lg:grid-cols-12">
      <AuthPlate
        className="h-[180px] rounded-none lg:col-span-7 lg:h-auto"
        label={plate.label}
        spec={plate.spec}
        halted={Boolean(error)}
      />

      <main className="flex min-w-0 flex-col px-4 pb-6 pt-5 sm:px-8 lg:col-span-5 lg:px-12">
        <header className="flex items-center justify-between">
          <Wordmark />
          <ThemeToggle variant="ghost" />
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
