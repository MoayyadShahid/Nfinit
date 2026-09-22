"use client";

import { useRef } from "react";
import { useInView } from "./useInView";

/** Section divider drawn like a dimension line: `|—— 02 REFINE ——|` (spec §5). */
export function DimensionRule({
  label,
  className = "",
}: {
  label: string;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { threshold: 0.6 });

  return (
    <div
      ref={ref}
      className={`wb-rule ${className}`}
      data-inview={inView}
      role="separator"
      aria-label={label}
    >
      <span className="wb-rule-line" aria-hidden="true" />
      <span className="type-label" aria-hidden="true">
        — {label} —
      </span>
      <span className="wb-rule-line" aria-hidden="true" />
    </div>
  );
}
