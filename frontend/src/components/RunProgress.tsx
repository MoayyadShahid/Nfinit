"use client";

import type { RunEvent } from "@/lib/types";
import { AlertTriangle, Check, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

const STAGE_LABELS: Record<string, string> = {
  retrieve: "Patterns",
  plan: "Plan",
  generate: "Code",
  inspect: "Check",
  repair: "Fix",
  mesh: "3D view",
};

type Step = {
  key: string;
  stage: string;
  status: "running" | "done" | "failed";
  message: string;
  durationMs: number | null;
};

/** Fold started/finished events into one row per step. */
function stepsOf(events: RunEvent[]): Step[] {
  const steps: Step[] = [];
  for (const event of events) {
    if (event.status === "started") {
      steps.push({
        key: `${event.seq}`,
        stage: event.stage,
        status: "running",
        message: event.message,
        durationMs: null,
      });
      continue;
    }
    const open = [...steps]
      .reverse()
      .find((step) => step.stage === event.stage && step.status === "running");
    const finished: Step = {
      key: open?.key ?? `${event.seq}`,
      stage: event.stage,
      status: event.status === "failed" ? "failed" : "done",
      message: event.message || open?.message || "",
      durationMs: event.durationMs,
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
    <div
      className="theme-inset rounded-xl border px-3 py-2.5 text-[11px]"
      aria-live="polite"
    >
      <div className="mb-1.5 flex items-center justify-between text-xs font-medium text-[var(--ink)]">
        <span>Building your part</span>
        {startedAt !== null && (
          <span className="font-mono text-[10px] text-zinc-500">
            {elapsed(now - startedAt)}
          </span>
        )}
      </div>
      {steps.length === 0 ? (
        <div className="flex items-center gap-2 text-zinc-500">
          <Loader2 className="size-3 shrink-0 animate-spin" />
          Starting the agent…
        </div>
      ) : (
        <ol className="space-y-1">
          {steps.map((step) => (
            <li key={step.key} className="flex items-start gap-2 text-zinc-500">
              {step.status === "running" ? (
                <Loader2 className="mt-0.5 size-3 shrink-0 animate-spin text-[var(--accent)]" />
              ) : step.status === "failed" ? (
                <AlertTriangle className="mt-0.5 size-3 shrink-0 text-amber-400" />
              ) : (
                <Check className="mt-0.5 size-3 shrink-0 text-emerald-400" />
              )}
              <span className="min-w-0">
                <span className="text-zinc-400">
                  {STAGE_LABELS[step.stage] ?? step.stage}
                </span>
                {" · "}
                <span className={step.status === "running" ? "text-[var(--ink-2)]" : ""}>
                  {step.message}
                </span>
                {step.durationMs !== null && (
                  <span className="ml-1 text-zinc-600">
                    ({(step.durationMs / 1000).toFixed(1)} s)
                  </span>
                )}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
