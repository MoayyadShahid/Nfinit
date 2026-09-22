"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useInView } from "./useInView";

type RevealState = "idle" | "printing" | "done" | "halted";

const PRINT_MS = 1400;
const FADE_MS = 300;

/**
 * The layer-print reveal (spec §9.1). The content is uncovered bottom-up in 16
 * steps while a 1px nozzle line rides the edge. Runs once, at 35% in view.
 * `halted` freezes it half-printed: the auth page's quiet failed-print joke.
 */
export function LayerReveal({
  children,
  halted = false,
}: {
  children: ReactNode;
  halted?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { threshold: 0.35 });
  const [state, setState] = useState<RevealState>("idle");

  useEffect(() => {
    if (!inView || halted) return;
    // Start on the next frame so the idle clip is painted first.
    const start = requestAnimationFrame(() => setState("printing"));
    const finish = window.setTimeout(
      () => setState("done"),
      PRINT_MS + FADE_MS,
    );
    return () => {
      cancelAnimationFrame(start);
      window.clearTimeout(finish);
    };
  }, [inView, halted]);

  return (
    <div ref={ref} className="wb-reveal" data-state={halted ? "halted" : state}>
      <div className="wb-reveal-content">{children}</div>
      <span className="wb-nozzle" aria-hidden="true" />
    </div>
  );
}
