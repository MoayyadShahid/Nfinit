"use client";

import dynamic from "next/dynamic";
import { useRef } from "react";
import { useInView, usePrefersReducedMotion } from "./useInView";

// three.js loads only on the client, after the headline has painted.
const DroneScene = dynamic(() => import("./DroneScene"), { ssr: false });

/** The interactive hero part. Renders only while on screen. */
export function HeroDrone() {
  const ref = useRef<HTMLDivElement>(null);
  const seen = useInView(ref, { threshold: 0 });
  const onScreen = useInView(ref, { threshold: 0, once: false });
  const reducedMotion = usePrefersReducedMotion();

  return (
    <div ref={ref} className="absolute inset-0">
      {seen && <DroneScene active={onScreen} reducedMotion={reducedMotion} />}
    </div>
  );
}
