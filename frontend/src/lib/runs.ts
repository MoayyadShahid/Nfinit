import type { AgentTraceStep, ChatMessage, FaceSelection, ModelInspection } from "@/lib/types";
import { jsonRequest, requestJson } from "@/lib/projects";

export type CadRunStatus = "running" | "succeeded" | "failed";

export type CadRun = {
  runId: string;
  projectId: string | null;
  status: CadRunStatus;
  prompt: string;
  modelId: string;
  result: {
    code: string;
    plan: string;
    inspection: ModelInspection | null;
    trace: AgentTraceStep[];
    usage: { input_tokens: number; output_tokens: number; total_tokens: number };
    revisionNumber: number | null;
  } | null;
  error: string | null;
  createdAt: string;
  completedAt: string | null;
};

export type StartRunRequest = {
  messages: ChatMessage[];
  code: string;
  modelId: string;
  selection: FaceSelection | null;
  supportsStructuredOutputs: boolean;
  projectId: string | null;
};

const POLL_INTERVAL_MS = 2_000;
// The backend gives a run 300s; past this the run is still saved server-side,
// the studio just stops waiting on it.
const MAX_WAIT_MS = 7 * 60_000;

export function startRun(request: StartRunRequest): Promise<CadRun> {
  return requestJson("/cad/runs", jsonRequest("POST", request));
}

export function getRun(runId: string): Promise<CadRun> {
  return requestJson(`/cad/runs/${runId}`);
}

export class RunStillWorkingError extends Error {
  constructor() {
    super(
      "This part is taking longer than usual. It will be saved to your parts when it finishes."
    );
  }
}

/** Poll until the run finishes. Transient network errors are retried. */
export async function waitForRun(
  runId: string,
  isCancelled: () => boolean = () => false
): Promise<CadRun> {
  const deadline = Date.now() + MAX_WAIT_MS;
  let failures = 0;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    if (isCancelled()) throw new DOMException("Stopped waiting", "AbortError");
    try {
      const run = await getRun(runId);
      failures = 0;
      if (run.status !== "running") return run;
    } catch (error) {
      if (++failures >= 5) throw error;
    }
  }
  throw new RunStillWorkingError();
}
