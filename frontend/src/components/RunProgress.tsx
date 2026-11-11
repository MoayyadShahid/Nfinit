"use client";

import type { RunEvent } from "@/lib/types";
import AILoadingState from "@/components/kokonutui/ai-loading";
import { useEffect, useMemo, useState } from "react";

const STAGE_LABELS: Record<string, string> = {
  retrieve: "Finding useful patterns",
  plan: "Planning your part",
  generate: "Building the geometry",
  inspect: "Checking the geometry",
  repair: "Refining the geometry",
  mesh: "Preparing the 3D view",
  // A local agent's steps, reported by its CAD tools as they happen.
  requirements: "Setting requirements",
  build: "Building and measuring",
  measure: "Measuring the part",
  view: "Looking at the part",
  printability: "Checking printability",
};

type Step = {
  key: string;
  stage: string;
  status: "running" | "done" | "failed";
  message: string;
  durationMs: number | null;
  attempt: number | null;
};

/** Fold started/finished events into one row per step. */
function stepsOf(events: RunEvent[]): Step[] {
  const steps: Step[] = [];
  const seen = new Set<number>();
  for (const event of events) {
    if (seen.has(event.seq)) continue;
    seen.add(event.seq);
    // Build previews are shown in the viewport, not as steps.
    if (event.stage === "snapshot") continue;
    if (event.status === "started") {
      steps.push({
        key: `${event.seq}`,
        stage: event.stage,
        status: "running",
        message: event.message,
        durationMs: null,
        attempt: event.attempt,
      });
      continue;
    }
    if (!["complete", "passed", "failed"].includes(event.status)) continue;
    const open = [...steps]
      .reverse()
      .find((step) =>
        step.stage === event.stage &&
        step.status === "running" &&
        // Finished trace events omit attempt; pair those with the latest
        // open occurrence, including numbered repair starts.
        (event.attempt === null || step.attempt === event.attempt)
      );
    const finished: Step = {
      key: open?.key ?? `${event.seq}`,
      stage: event.stage,
      status: event.status === "failed" ? "failed" : "done",
      message: event.message || open?.message || "",
      durationMs: event.durationMs,
      attempt: event.attempt,
    };
    if (open) steps[steps.indexOf(open)] = finished;
    else steps.push(finished);
  }
  return steps;
}

function elapsed(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function RunProgress({
  events,
  startedAt,
}: {
  events: RunEvent[];
  startedAt: number | null;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const steps = useMemo(() => stepsOf(events), [events]);

  return (
    <AILoadingState
      elapsed={startedAt === null ? null : elapsed(now - startedAt)}
      steps={steps.map((step) => ({
        id: step.key,
        label: STAGE_LABELS[step.stage] ?? step.stage,
        status: step.status === "failed" ? "error" : step.status,
        detail: step.message,
        durationMs: step.durationMs,
      }))}
    />
  );
}
