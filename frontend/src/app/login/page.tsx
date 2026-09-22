import { LoginButtons } from "@/components/LoginButtons";
import { ThemeToggle } from "@/components/ThemeToggle";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { getAuthenticatedUser } from "@/lib/supabase/server";
import { Sparkles } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Log in — nfinit",
};
export const dynamic = "force-dynamic";

function safeNextPath(value: string | string[] | undefined): string {
  const path = Array.isArray(value) ? value[0] : value;
  return path?.startsWith("/") && !path.startsWith("//") ? path : "/studio";
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

  return (
    <main className="theme-page relative flex min-h-dvh items-center justify-center overflow-hidden px-5">
      <div
        className="pointer-events-none absolute left-1/2 top-[-22rem] h-[44rem] w-[64rem] -translate-x-1/2 rounded-full"
        style={{
          background:
            "radial-gradient(circle, var(--ambient-glow), transparent 68%)",
        }}
      />
      <Link
        href="/"
        aria-label="nfinit home"
        className="absolute left-5 top-5 flex items-center gap-2.5 sm:left-8 sm:top-7"
      >
        <span className="theme-primary-button flex size-8 items-center justify-center rounded-xl">
          <Sparkles className="size-3.5" />
        </span>
        <span className="text-sm font-semibold tracking-[-0.025em]">nfinit</span>
      </Link>
      <ThemeToggle className="absolute right-5 top-5 sm:right-8 sm:top-7" />

      <section className="relative w-full max-w-sm text-center">
        <div className="mx-auto mb-7 flex size-12 items-center justify-center rounded-2xl border border-violet-400/15 bg-violet-400/8 text-violet-500">
          <Sparkles className="size-5" />
        </div>
        <h1 className="text-3xl font-semibold tracking-[-0.04em]">
          Continue to nfinit
        </h1>
        <p className="theme-muted mt-3 text-sm">
          Your designs, revisions, and exports in one place.
        </p>
        <div className="mt-8">
          <LoginButtons nextPath={nextPath} />
        </div>
        {params.error && (
          <p role="alert" className="mt-4 text-xs text-red-500">
            Sign-in could not be completed. Please try again.
          </p>
        )}
        <p className="theme-faint mt-7 text-[10px]">
          By continuing, you agree to keep building interesting things.
        </p>
      </section>
    </main>
  );
}
