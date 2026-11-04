"use client";

import { stepTitle, type Demo } from "@/lib/demos";
import { ArrowRight, Play, RotateCcw, X } from "lucide-react";

/**
 * The timeline of a demo: one point per version of the part. Clicking a point
 * shows that version; "Next" builds the next one, as a live run would.
 */
export function DemoReplay({
  demo,
  step,
  reached,
  playing,
  onSelect,
  onNext,
  onReplay,
  onExit,
}: {
  demo: Demo;
  /** The version shown (1-based). */
  step: number;
  /** The furthest version built so far in this replay. */
  reached: number;
  playing: boolean;
  onSelect: (step: number) => void;
  onNext: () => void;
  onReplay: () => void;
  onExit: () => void;
}) {
  const last = step >= demo.steps.length;
  const current = demo.steps[step - 1];
  const example = demo.source === "example";
  return (
    <div className="theme-inset rounded-xl border px-3 py-2.5 text-[11px]">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-600">
          {demo.title} · Version {step} of {demo.steps.length}
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

      <ol className="mt-2 flex items-center gap-1 overflow-x-auto pb-1" aria-label="Versions">
        {demo.steps.map((item, index) => {
          const number = index + 1;
          const active = number === step;
          const built = number <= reached;
          return (
            <li key={number} className="flex shrink-0 items-center gap-1">
              {index > 0 && (
                <span
                  aria-hidden
                  className={`h-px w-3 ${built ? "bg-[var(--ink-2)]" : "bg-[var(--hairline-strong)]"}`}
                />
              )}
              <button
                type="button"
                onClick={() => onSelect(number)}
                disabled={playing}
                aria-current={active ? "step" : undefined}
                title={`Version ${number}: ${stepTitle(item)}`}
                className={`flex h-7 max-w-[11rem] items-center gap-1.5 rounded-full border px-2 text-[10px] font-medium transition-colors disabled:cursor-default ${
                  active
                    ? "border-transparent bg-[var(--ink)] text-[var(--paper)]"
                    : built
                      ? "border-[var(--hairline-strong)] text-[var(--ink)] hover:bg-[var(--control-hover)]"
                      : "border-dashed border-[var(--hairline-strong)] text-zinc-500 hover:text-[var(--ink)]"
                }`}
              >
                <span className="tabular-nums">{number}</span>
                <span className="truncate">{stepTitle(item)}</span>
              </button>
            </li>
          );
        })}
      </ol>

      <p className="mt-1.5 text-xs leading-5 text-[var(--ink)]">“{current?.prompt}”</p>
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
              {step < reached ? "Next version" : "Build next version"} <ArrowRight className="size-3" />
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
            <Play className="size-3" /> Replay this version
          </button>
        )}
        <span className="ml-auto text-right text-[10px] text-zinc-500">
          {last
            ? "Your turn: describe a part below."
            : example
              ? "Example build. Click a version to see it."
              : "Recorded with the real agent."}
        </span>
      </div>
    </div>
  );
}
