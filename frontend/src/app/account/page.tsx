import { Wordmark } from "@/components/brand/Wordmark";
import { DeleteAccount } from "@/components/DeleteAccount";
import { LegalLinks } from "@/components/LegalPage";
import { ThemeToggle } from "@/components/ThemeToggle";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { getAuthenticatedUser } from "@/lib/supabase/server";
import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Account · nfinit",
  description: "Your Nfinit account.",
};
export const dynamic = "force-dynamic";

export default async function AccountPage() {
  const user = await getAuthenticatedUser();
  if (isSupabaseConfigured() && !user) {
    redirect(`/login?next=${encodeURIComponent("/account")}`);
  }

  return (
    <div className="wb min-h-dvh">
      <header className="mx-auto flex h-16 max-w-[1264px] items-center justify-between gap-3 px-4 sm:px-8">
        <Wordmark />
        <nav className="flex items-center gap-1 sm:gap-2" aria-label="Account">
          <ThemeToggle />
          <Link href="/studio" className="wb-btn wb-btn-ghost wb-btn-sm">
            Back to studio
          </Link>
        </nav>
      </header>

      <main className="mx-auto max-w-[760px] px-4 pb-24 pt-10 sm:px-8">
        <h1 className="type-h1">Account</h1>

        <section className="mt-10 space-y-2 text-[15px] leading-6 text-[var(--ink-2)]">
          <p>
            Signed in as{" "}
            <strong className="text-[var(--ink)]">
              {user?.email ?? "local development user"}
            </strong>
          </p>
          <p>
            To get a copy of your data, see the{" "}
            <Link href="/privacy#rights" className="underline underline-offset-4">
              Privacy Policy
            </Link>
            .
          </p>
        </section>

        <section className="mt-10">
          <DeleteAccount />
        </section>
      </main>

      <footer className="mx-auto flex max-w-[1264px] flex-wrap items-center justify-between gap-4 border-t border-[var(--hairline)] px-4 py-6 sm:px-8">
        <Wordmark size={18} />
        <LegalLinks />
      </footer>
    </div>
  );
}
