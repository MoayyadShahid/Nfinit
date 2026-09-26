import { Wordmark } from "@/components/brand/Wordmark";
import { ThemeToggle } from "@/components/ThemeToggle";
import { FlowHook } from "@/components/landing/FlowHook";
import { HeroDrone } from "@/components/landing/HeroDrone";
import { Plate } from "@/components/landing/Plate";
import { PromptBar } from "@/components/landing/PromptBar";
import Link from "next/link";
import type { CSSProperties } from "react";

// Thin space before units (spec §3).
const T = " ";

function riseDelay(ms: number) {
  return { "--rise-delay": `${ms}ms` } as CSSProperties;
}

export default function LandingPage() {
  return (
    <div className="wb min-h-dvh overflow-x-clip">
      <header className="mx-auto flex h-16 max-w-[1264px] items-center justify-between gap-3 px-4 sm:px-8">
        <Wordmark />
        <nav className="flex items-center gap-1 sm:gap-2" aria-label="Main">
          <ThemeToggle />
          <Link href="/login?next=/studio" className="wb-btn wb-btn-ghost wb-btn-sm">
            Log in
          </Link>
          <Link href="/studio" className="wb-btn wb-btn-primary wb-btn-sm">
            Start a part
            <span className="wb-arrow" aria-hidden="true">
              →
            </span>
          </Link>
        </nav>
      </header>

      <main>
        {/* Hero (§7) */}
        <section className="mx-auto grid max-w-[1264px] grid-cols-1 items-center gap-x-8 gap-y-8 px-4 pb-16 pt-8 sm:px-8 lg:grid-cols-12 lg:pb-24 lg:pt-12">
          <div className="flex flex-col justify-center gap-6 lg:col-span-7">
            <p className="type-label">Describe → Refine → Print</p>
            <h1 className="type-display wb-hero-line mb-3">
              <span className="wb-rise-line">
                <span style={riseDelay(0)}>
                  Say it. <em>Hold it.</em>
                </span>
              </span>
            </h1>
            <PromptBar />
          </div>

          <Plate
            className="aspect-square w-full lg:col-span-5 lg:aspect-[4/5]"
            label="Plate 01 · 5-inch FPV frame"
            hint="Drag to spin"
            spec={
              <>
                PA-CF · 220{T}mm
                <br />
                3h 10m
              </>
            }
          >
            <HeroDrone />
          </Plate>
        </section>

        {/* Flow: one part tells the story (§7) */}
        <section
          aria-label="How it works"
          className="mx-auto max-w-[1264px] px-4 pb-24 sm:px-8 lg:pb-40"
        >
          <FlowHook />
        </section>

        {/* Close (§7): the only centred block */}
        <section className="mx-auto max-w-[1264px] px-4 pb-24 text-center sm:px-8 lg:pb-40">
          <h2 className="type-h1 mb-10">
            Your next part, <em>rev A.</em>
          </h2>
          <PromptBar centered className="text-left" />
        </section>
      </main>

      <footer className="mx-auto flex max-w-[1264px] flex-wrap items-center justify-between gap-4 border-t border-[var(--hairline)] px-4 py-6 sm:px-8">
        <Wordmark size={18} />
        <p className="type-label">Terms · Privacy</p>
        <p className="type-label">© 2026</p>
      </footer>
    </div>
  );
}
