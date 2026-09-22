"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { DimensionRule } from "./DimensionRule";
import { useInView, usePrefersReducedMotion } from "./useInView";

/*
 * One part tells the whole flow (spec §7): a pipe hook is sketched, refined by
 * clicking a face, then sliced into layers. This is a diagram of the flow,
 * not a product screenshot.
 */

type Step = 0 | 1 | 2;

const HOOK =
  "M110 58 V150 A50 50 0 0 0 210 150 V122 H194 V150 A34 34 0 0 1 126 150 V58 Z";
const PLATE = "M100 14 H136 V70 H100 Z";

function useCountUp(active: boolean, from: number, to: number, ms: number) {
  const reduced = usePrefersReducedMotion();
  const [value, setValue] = useState(from);

  useEffect(() => {
    if (!active) return;
    if (reduced) {
      const frame = requestAnimationFrame(() => setValue(to));
      return () => cancelAnimationFrame(frame);
    }
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      setValue(from + (to - from) * t);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [active, from, to, ms, reduced]);

  return value;
}

function SketchState({ active }: { active: boolean }) {
  const lines = [
    HOOK,
    PLATE,
    "M160 175 m-25 0 a25 25 0 1 0 50 0 a25 25 0 1 0 -50 0",
    "M60 175 H260",
    "M118 28 m-4 0 a4 4 0 1 0 8 0 a4 4 0 1 0 -8 0",
    "M118 54 m-4 0 a4 4 0 1 0 8 0 a4 4 0 1 0 -8 0",
    "M150 40 H230 M150 36 V44 M230 36 V44",
  ];
  return (
    <g data-active={active}>
      {lines.map((d, i) => (
        <path
          key={d}
          d={d}
          pathLength={1}
          className="wb-sketch"
          style={{ ["--draw-delay" as string]: `${i * 35}ms` }}
        />
      ))}
      <text className="wb-svg-label" x="236" y="44">
        Ø25
      </text>
      <text className="wb-svg-label" x="16" y="226">
        SKETCH · Ø25 PIPE · 2× M4
      </text>
    </g>
  );
}

function RefineState({ active }: { active: boolean }) {
  const value = useCountUp(active, 6, 9, 520);
  return (
    <g data-active={active}>
      <path d={HOOK} className="wb-part" />
      <path d={HOOK} className="wb-part-edge" />
      <path d={PLATE} className="wb-part" />
      <path d={PLATE} className="wb-part-edge" />
      <circle cx="118" cy="28" r="4" fill="var(--inset)" />
      <circle cx="118" cy="54" r="4" fill="var(--inset)" />
      <rect className="wb-face" x="110" y="74" width="16" height="72" />
      <path className="wb-dim" d="M104 74 H84 M104 146 H84 M90 74 V146" />
      <text className="wb-dim-text" x="16" y="114">
        {value.toFixed(1)} MM
      </text>
      <g className="wb-stamp">
        <rect
          x="226"
          y="24"
          width="64"
          height="24"
          rx="2"
          fill="none"
          stroke="var(--ink-2)"
          strokeOpacity=".6"
        />
        <text className="wb-svg-label" x="238" y="40" style={{ fill: "var(--ink-2)" }}>
          REV B
        </text>
      </g>
      <text className="wb-svg-label" x="16" y="226">
        FACE 7 · 6.0 → 9.0 MM
      </text>
    </g>
  );
}

function PrintState({ active, clipId }: { active: boolean; clipId: string }) {
  const layers = Array.from({ length: 18 }, (_, i) => 20 + i * 11);
  return (
    <g data-active={active}>
      <defs>
        <clipPath id={clipId}>
          <path d={HOOK} />
          <path d={PLATE} />
        </clipPath>
      </defs>
      <g clipPath={`url(#${clipId})`}>
        <rect x="90" y="10" width="140" height="200" className="wb-part" />
        <g className="wb-layers">
          {layers.map((y) => (
            <line key={y} x1="90" x2="230" y1={y} y2={y} />
          ))}
        </g>
      </g>
      <path d={HOOK} className="wb-part-edge" />
      <path d={PLATE} className="wb-part-edge" />
      <g className="wb-flow-nozzle">
        <line
          x1="92"
          x2="228"
          y1="200"
          y2="200"
          stroke="var(--accent)"
          strokeWidth="1.2"
        />
        <circle cx="160" cy="200" r="3" fill="var(--accent)" />
      </g>
      <text className="wb-svg-label" x="16" y="226">
        HOOK_V3.STL · 184 KB · 38 MIN
      </text>
    </g>
  );
}

function Diagram({ step, id }: { step: Step | null; id: string }) {
  const labels = [
    "Construct-blue sketch of a pipe hook",
    "The hook with one face selected and thickened from 6 to 9 millimetres",
    "The hook sliced into print layers",
  ];
  return (
    <svg
      viewBox="0 0 320 240"
      role="img"
      aria-label={labels[step ?? 0]}
      className="absolute inset-0 h-full w-full"
    >
      <g className="wb-flow-state" data-active={step === 0}>
        <SketchState active={step === 0} />
      </g>
      <g className="wb-flow-state" data-active={step === 1}>
        <RefineState active={step === 1} />
      </g>
      <g className="wb-flow-state" data-active={step === 2}>
        <PrintState active={step === 2} clipId={`${id}-clip`} />
      </g>
    </svg>
  );
}

function Frame({ children }: { children: ReactNode }) {
  return (
    <div className="relative aspect-[4/3] w-full overflow-hidden rounded-[2px] border border-[var(--hairline)] bg-[var(--inset)]">
      {children}
    </div>
  );
}

function StepBlock({
  index,
  label,
  onActive,
  children,
}: {
  index: Step;
  label: string;
  onActive: (step: Step) => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  // Active while the block crosses the middle band of the viewport.
  const inView = useInView(ref, {
    threshold: 0,
    once: false,
    rootMargin: "-45% 0px -45% 0px",
  });

  useEffect(() => {
    if (inView) onActive(index);
  }, [inView, index, onActive]);

  return (
    <div
      ref={ref}
      className="flex flex-col gap-8 lg:min-h-[64vh] lg:justify-center"
    >
      <DimensionRule label={label} />
      <div className="flex flex-col gap-5">{children}</div>
      <div className="lg:hidden">
        <Frame>
          <MobileDiagram step={index} />
        </Frame>
      </div>
    </div>
  );
}

function MobileDiagram({ step }: { step: Step }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { threshold: 0.35 });
  return (
    <div ref={ref} className="absolute inset-0">
      {inView && <Diagram step={step} id={`flow-m${step}`} />}
    </div>
  );
}

function Chip({ children, on = false }: { children: ReactNode; on?: boolean }) {
  return (
    <span
      className="wb-chip cursor-default font-mono text-[12px]"
      data-on={on}
    >
      {children}
    </span>
  );
}

export function FlowHook() {
  const [step, setStep] = useState<Step>(0);
  const stickyRef = useRef<HTMLDivElement>(null);
  const seen = useInView(stickyRef, { threshold: 0.35 });

  return (
    <div className="grid gap-16 lg:grid-cols-12 lg:gap-8">
      <div className="flex flex-col gap-24 lg:col-span-5 lg:gap-0">
        <StepBlock index={0} label="01 Describe" onActive={setStep}>
          <p className="type-quote max-w-[14ch] text-[var(--ink)]">
            “A hook for a 25&nbsp;mm pipe. Two M4 screws.”
          </p>
        </StepBlock>
        <StepBlock index={1} label="02 Refine" onActive={setStep}>
          <h3 className="type-h2">
            Click a face. <em>Change your mind.</em>
          </h3>
          <div className="flex gap-2">
            <Chip>v1</Chip>
            <Chip>v2</Chip>
            <Chip on>v3</Chip>
          </div>
        </StepBlock>
        <StepBlock index={2} label="03 Print" onActive={setStep}>
          <h3 className="type-h2">
            Print it <em>tonight.</em>
          </h3>
          <div className="flex flex-wrap items-center gap-2">
            <Chip>.STL</Chip>
            <Chip>.STEP</Chip>
            <span className="type-spec ml-1">hook_v3.stl · 184 KB · 38 MIN</span>
          </div>
        </StepBlock>
      </div>
      <div className="hidden lg:col-span-7 lg:block">
        <div ref={stickyRef} className="sticky top-[18vh]">
          <Frame>
            <Diagram step={seen ? step : null} id="flow-d" />
          </Frame>
        </div>
      </div>
    </div>
  );
}
