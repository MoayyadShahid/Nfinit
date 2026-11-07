"use client";

import { type Demo } from "@/lib/demos";
import { ArrowRight, Play, RotateCcw } from "lucide-react";

/**
 * The controls of a demo replay, shown under its versions: "Next" builds the
 * next version, as a live run would.
 */
export function DemoControls({
  demo,
  step,
  reached,
  playing,
  onNext,
  onReplay,
}: {
  demo: Demo;
  /** The version shown (1-based). */
  step: number;
  /** The furthest version built so far in this replay. */
  reached: number;
  playing: boolean;
  onNext: () => void;
  onReplay: () => void;
}) {
  const last = step >= demo.steps.length;
  return (
    <div className="flex flex-col gap-1.5 text-[11px]">
      <button
        type="button"
        onClick={last ? onReplay : onNext}
        disabled={playing}
        className="flex items-center justify-center gap-1.5 rounded-lg bg-[var(--ink)] px-2.5 py-2 font-medium text-[var(--paper)] disabled:opacity-50"
      >
        {last ? (
          <>
            <RotateCcw className="size-3" /> Watch again
          </>
        ) : (
          <>
            {step < reached ? "Next version" : "Build next version"}
            <ArrowRight className="size-3" />
          </>
        )}
      </button>
      {!last && (
        <button
          type="button"
          onClick={onReplay}
          disabled={playing}
          className="flex items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-[var(--ink-2)] hover:bg-[var(--control-hover)] disabled:opacity-50"
        >
          <Play className="size-3" /> Replay this version
        </button>
      )}
      <p className="px-1 text-center text-[10px] leading-4 text-zinc-500">
        {playing
          ? "Building…"
          : last
            ? "Your turn. Describe a part below."
            : demo.source === "example"
              ? "Example build. Click a version to see it."
              : "Recorded with the real agent."}
      </p>
    </div>
  );
}
