import type { AgentTraceStep, ModelInspection, RunEvent } from "@/lib/types";

/**
 * Demo parts: short build stories built by `backend/demos/build.py` and
 * served as static files, so anyone can replay them without the backend or a
 * subscription. Each step is one version of the part, like a point on a CAD
 * timeline.
 */
export const DEMO_ROOT = "/demos";
export const FIRST_DEMO = "fpv-drone";

export type DemoSummary = {
  slug: string;
  title: string;
  summary: string;
  steps: number;
};

export type DemoEvent = {
  stage: string;
  status: string;
  message: string;
  attempt?: number | null;
  duration_ms?: number | null;
  /** When the agent recorded the event, from the start of the step. */
  at_ms: number;
};

export type DemoStep = {
  prompt: string;
  summary: string;
  code: string;
  glb: string;
  previews: { file: string; name: string }[];
  events: DemoEvent[];
  agent: { plan: string; trace: AgentTraceStep[]; inspection: ModelInspection };
};

export type Demo = Omit<DemoSummary, "steps"> & {
  /**
   * "example": written by the Nfinit team and built in the sandbox.
   * "recorded": a recorded run of the agent (older demos, with `model_id`).
   */
  source?: "example" | "recorded";
  model_id?: string;
  steps: DemoStep[];
};

/** A short name for a step: the features it adds, e.g. "Standoffs + Top plate". */
export function stepTitle(step: DemoStep): string {
  return step.previews.map((preview) => preview.name).join(" + ") || step.summary;
}

export async function listDemos(): Promise<DemoSummary[]> {
  const response = await fetch(`${DEMO_ROOT}/index.json`);
  if (!response.ok) return [];
  const payload = (await response.json()) as { demos?: DemoSummary[] };
  return payload.demos ?? [];
}

export async function getDemo(slug: string): Promise<Demo> {
  const response = await fetch(`${DEMO_ROOT}/${encodeURIComponent(slug)}/demo.json`);
  if (!response.ok) throw new Error("This demo is not available.");
  return (await response.json()) as Demo;
}

export function demoFile(slug: string, file: string): string {
  return `${DEMO_ROOT}/${encodeURIComponent(slug)}/${encodeURIComponent(file)}`;
}

/** A recorded event in the shape the progress list shows. */
export function toRunEvent(event: DemoEvent, seq: number, startedAt: number): RunEvent {
  return {
    seq,
    stage: event.stage,
    status: event.status,
    message: event.message,
    attempt: event.attempt ?? null,
    durationMs: event.duration_ms ?? null,
    createdAt: new Date(startedAt + event.at_ms).toISOString(),
  };
}
