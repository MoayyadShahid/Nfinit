"use client";

import type { Demo } from "@/lib/demos";
import { ArrowRight, RotateCcw, X } from "lucide-react";

/** Controls for replaying a recorded demo, one prompt at a time. */
export function DemoReplay({
  demo,
  step,
  playing,
  onNext,
  onReplay,
  onExit,
}: {
  demo: Demo;
  /** The step shown (1-based). */
  step: number;
  playing: boolean;
  onNext: () => void;
  onReplay: () => void;
  onExit: () => void;
}) {
  const last = step >= demo.steps.length;
  return (
    <div className="theme-inset rounded-xl border px-3 py-2.5 text-[11px]">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-600">
          Demo · {demo.title} · Step {step} of {demo.steps.length}
        </p>
        <button
          type="button"
          onClick={onExit}
          aria-label="Exit the demo"
          className="rounded p-0.5 text-zinc-500 hover:text-[var(--ink)]"
        >
          <X className="size-3.5" />
        </button>
      </div>
      <p className="mt-1 text-xs leading-5 text-[var(--ink)]">
        “{demo.steps[step - 1]?.prompt}”
      </p>
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={last ? onReplay : onNext}
          disabled={playing}
          className="flex items-center gap-1.5 rounded-lg bg-[var(--ink)] px-2.5 py-1.5 text-[11px] font-medium text-[var(--paper)] disabled:opacity-50"
        >
          {last ? (
            <>
              <RotateCcw className="size-3" /> Watch again
            </>
          ) : (
            <>
              Next step <ArrowRight className="size-3" />
            </>
          )}
        </button>
        {!last && (
          <button
            type="button"
            onClick={onReplay}
            disabled={playing}
            className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[11px] text-[var(--ink-2)] hover:bg-[var(--control-hover)] disabled:opacity-50"
          >
            <RotateCcw className="size-3" /> Replay step
          </button>
        )}
        <span className="ml-auto text-[10px] text-zinc-500">
          {last ? "Your turn: describe a part below." : "Recorded with the real agent."}
        </span>
      </div>
    </div>
  );
}
