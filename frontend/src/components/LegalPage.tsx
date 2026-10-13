import { Wordmark } from "@/components/brand/Wordmark";
import { ThemeToggle } from "@/components/ThemeToggle";
import { LEGAL, LEGAL_IS_COMPLETE } from "@/lib/legal";
import Link from "next/link";
import type { ReactNode } from "react";

/** One numbered section of a legal document. */
export function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-20">
      <h2>{title}</h2>
      {children}
    </section>
  );
}

export function LegalPage({
  title,
  summary,
  children,
}: {
  title: string;
  /** Plain-language summary shown above the full text. */
  summary: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="wb min-h-dvh">
      <header className="mx-auto flex h-16 max-w-[1264px] items-center justify-between gap-3 px-4 sm:px-8">
        <Wordmark />
        <nav className="flex items-center gap-1 sm:gap-2" aria-label="Legal">
          <ThemeToggle />
          <Link href="/terms" className="wb-btn wb-btn-ghost wb-btn-sm">
            Terms
          </Link>
          <Link href="/privacy" className="wb-btn wb-btn-ghost wb-btn-sm">
            Privacy
          </Link>
        </nav>
      </header>

      <main className="mx-auto max-w-[760px] px-4 pb-24 pt-10 sm:px-8">
        {!LEGAL_IS_COMPLETE && (
          <p
            role="note"
            className="mb-8 rounded-xl border border-[var(--danger)] px-4 py-3 text-sm text-[var(--danger)]"
          >
            Draft: the operator name, contact email or governing state is not
            filled in yet (frontend/src/lib/legal.ts).
          </p>
        )}
        <p className="type-label">Effective {LEGAL.effectiveDate}</p>
        <h1 className="type-h1 mt-3">{title}</h1>
        <div className="legal-summary mt-8 rounded-2xl border border-[var(--hairline)] p-5 sm:p-6">
          <p className="type-label mb-3">In short</p>
          {summary}
        </div>
        <article className="legal-prose mt-12">{children}</article>
      </main>

      <footer className="mx-auto flex max-w-[1264px] flex-wrap items-center justify-between gap-4 border-t border-[var(--hairline)] px-4 py-6 sm:px-8">
        <Wordmark size={18} />
        <LegalLinks />
        <p className="type-label">© 2026 {LEGAL.operator}</p>
      </footer>
    </div>
  );
}

/** "Terms · Privacy" as links, for page footers. */
export function LegalLinks({ className = "type-label" }: { className?: string }) {
  return (
    <p className={className}>
      <Link href="/terms" className="underline-offset-4 hover:underline">
        Terms
      </Link>
      {" · "}
      <Link href="/privacy" className="underline-offset-4 hover:underline">
        Privacy
      </Link>
    </p>
  );
}
