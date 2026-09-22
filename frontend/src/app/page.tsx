import { Wordmark } from "@/components/brand/Wordmark";
import { DimensionRule } from "@/components/landing/DimensionRule";
import { FlowHook } from "@/components/landing/FlowHook";
import { ForceLightTheme } from "@/components/landing/ForceLightTheme";
import { HeroDrone } from "@/components/landing/HeroDrone";
import { Plate } from "@/components/landing/Plate";
import { PromptBar } from "@/components/landing/PromptBar";
import Link from "next/link";
import type { CSSProperties } from "react";

// Thin space before units (spec §3).
const T = " ";

const GALLERY: {
  name: string;
  spec: string;
  prompt: string;
  sticker?: { text: string; tilt: number };
}[] = [
  {
    name: `Cable clip · 4${T}min`,
    spec: `PETG · 0.2${T}mm`,
    prompt: "a cable clip for a 6 mm desk edge",
  },
  {
    name: `Lid hinge · 22${T}min`,
    spec: `PLA · 0.2${T}mm`,
    prompt: "a print-in-place hinge for a 60 mm lid",
    sticker: { text: "Print-in-place", tilt: -3 },
  },
  {
    name: `Pi 5 case · 1h 04`,
    spec: `PLA · 0.2${T}mm`,
    prompt: "a snap-fit case for a Raspberry Pi 5",
  },
  {
    name: `40${T}mm fan mount · 26${T}min`,
    spec: `PETG · 0.2${T}mm`,
    prompt: "a wall mount for a 40 mm fan, M3 screws",
    sticker: { text: "No supports", tilt: 2 },
  },
  {
    name: `Pipe hook · 38${T}min`,
    spec: `PETG · 0.28${T}mm`,
    prompt: "a hook for a 25 mm pipe, two M4 screws",
  },
  {
    name: `M6 knob · 9${T}min`,
    spec: `PLA · 0.16${T}mm`,
    prompt: "a knurled knob for an M6 bolt",
    sticker: { text: "Knurled", tilt: 4 },
  },
];

function riseDelay(ms: number) {
  return { "--rise-delay": `${ms}ms` } as CSSProperties;
}

export default function LandingPage() {
  return (
    <div className="wb min-h-dvh overflow-x-clip">
      <ForceLightTheme />
      <header className="mx-auto flex h-16 max-w-[1264px] items-center justify-between gap-3 px-4 sm:px-8">
        <Wordmark />
        <nav className="flex items-center gap-1 sm:gap-2" aria-label="Main">
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
        <section className="mx-auto grid max-w-[1264px] grid-cols-1 gap-x-8 gap-y-10 px-4 pb-24 pt-10 sm:px-8 lg:grid-cols-12 lg:grid-rows-[1fr_auto] lg:pb-40 lg:pt-20">
          <div className="flex flex-col gap-6 lg:col-span-7 lg:row-start-1 lg:self-end">
            <p className="type-label">Describe → Refine → Print</p>
            <h1 className="type-display">
              <span className="wb-rise-line">
                <span style={riseDelay(0)}>Say it.</span>
              </span>
              <span className="wb-rise-line">
                <span style={riseDelay(160)}>
                  <em>Hold it.</em>
                </span>
              </span>
            </h1>
          </div>

          <Plate
            className="aspect-square w-full lg:col-span-5 lg:row-span-2 lg:row-start-1 lg:aspect-[4/5]"
            label="Plate 01 · 5-inch quad frame"
            hint="Drag to spin"
            spec={
              <>
                PETG · 220{T}mm
                <br />
                2h 40m
              </>
            }
          >
            <HeroDrone />
          </Plate>

          <PromptBar className="lg:col-span-7 lg:row-start-2 lg:self-end" />
        </section>

        {/* Flow: one part tells the story (§7) */}
        <section
          aria-label="How it works"
          className="mx-auto max-w-[1264px] px-4 pb-24 sm:px-8 lg:pb-40"
        >
          <FlowHook />
        </section>

        {/* Gallery (§7) */}
        <section className="mx-auto max-w-[1264px] px-4 pb-24 sm:px-8 lg:pb-40">
          <DimensionRule label="04 Plates" className="mb-12 lg:mb-16" />
          <h2 className="type-h2 mb-10 lg:mb-12">
            Things people actually <em>print.</em>
          </h2>
          <ul className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3">
            {GALLERY.map((part, i) => (
              <li key={part.name} className="relative">
                <Plate
                  className="aspect-square w-full"
                  label={`Plate ${String(i + 2).padStart(2, "0")}`}
                  slotLabel={part.name}
                  spec={part.spec}
                  prompt={part.prompt}
                />
                {part.sticker && (
                  <span
                    className="wb-sticker pointer-events-none absolute -right-1 -top-2 z-10 hidden sm:inline-block"
                    style={{ transform: `rotate(${part.sticker.tilt}deg)` }}
                  >
                    {part.sticker.text}
                  </span>
                )}
              </li>
            ))}
          </ul>
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
