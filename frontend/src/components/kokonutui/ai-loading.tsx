"use client";

/** Adapted from Kokonut UI AI State Loading (MIT). See LICENSE.md. */
import { Check, ChevronDown, CircleAlert, LoaderCircle } from "lucide-react";
import { AnimatePresence, MotionConfig, motion, useReducedMotion } from "motion/react";
import { useId, useState } from "react";
import { cn } from "@/lib/utils";

export interface AgentStep {
  id: string;
  label: string;
  status: "running" | "done" | "error";
  detail: string;
  durationMs: number | null;
}

/** Controlled by recorded run events; never simulates work or completion. */
export default function AILoadingState({ steps, elapsed }: {
  steps: AgentStep[];
  elapsed: string | null;
}) {
  const [open, setOpen] = useState(true);
  const listId = useId();
  const reduceMotion = useReducedMotion();
  const running = steps.findLast((step) => step.status === "running");
  const title = running?.label ?? (steps.length ? "Preparing the next step" : "Starting your build");

  return (
    <MotionConfig reducedMotion="user">
      <section aria-label="Build progress" className="rounded-xl border bg-background px-3 py-2">
        <button
          type="button"
          aria-controls={listId}
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          className="flex min-h-8 w-full items-center gap-2 rounded-md text-left text-xs font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <LoaderCircle aria-hidden="true" className="size-3.5 shrink-0 text-[var(--accent-text)] motion-safe:animate-spin" />
          <span role="status" className="min-w-0 flex-1 truncate">{title}</span>
          {elapsed && <span aria-label="Elapsed time" className="font-mono text-[10px] tabular-nums text-muted-foreground">{elapsed}</span>}
          <ChevronDown aria-hidden="true" className={cn("size-3.5 text-muted-foreground motion-safe:transition-transform", open && "rotate-180")} />
        </button>
        <AnimatePresence initial={false}>
          {open && (
            <motion.div
              id={listId}
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: reduceMotion ? 0 : 0.18 }}
              className="overflow-hidden"
            >
              {steps.length === 0 ? (
                <p className="pb-2 pl-5.5 text-[11px] text-muted-foreground">Waiting for build updates…</p>
              ) : (
                <ol aria-label="Build steps" tabIndex={0} className="flex max-h-[min(25dvh,200px)] flex-col overflow-y-auto overscroll-contain rounded-md pb-1 outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  {steps.map((step, index) => (
                    <li key={step.id} className="relative flex gap-2.5 py-2">
                      {index < steps.length - 1 && <span aria-hidden="true" className="absolute bottom-0 left-[7px] top-6 w-px bg-border" />}
                      <span className="mt-0.5 size-3.5 shrink-0">
                        {step.status === "running" ? <LoaderCircle aria-hidden="true" className="size-3.5 text-[var(--accent-text)] motion-safe:animate-spin" /> : step.status === "error" ? <CircleAlert aria-hidden="true" className="size-3.5 text-destructive" /> : <Check aria-hidden="true" className="size-3.5 text-[var(--success)]" />}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-baseline gap-2 text-[11px]">
                          <span className={cn("font-medium", step.status === "done" && "text-muted-foreground", step.status === "error" && "text-destructive")}>{step.label}</span>
                          <span className="sr-only">{step.status === "error" ? "Failed" : step.status}</span>
                          {step.durationMs !== null && <span className="ml-auto shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground">{(step.durationMs / 1000).toFixed(1)} s</span>}
                        </div>
                        <p className="mt-0.5 break-words text-[11px] leading-4 text-muted-foreground">{step.detail}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </section>
    </MotionConfig>
  );
}
