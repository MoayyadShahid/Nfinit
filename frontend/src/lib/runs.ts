import type {
  AgentTraceStep,
  ChatMessage,
  FaceSelection,
  ModelInspection,
  RunEvent,
  MeshReference,
} from "@/lib/types";
import { BACKEND_ORIGIN, jsonRequest, requestJson } from "@/lib/projects";

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
  /** Progress events after the cursor passed to getRun. */
  events: RunEvent[];
};

export type StartRunRequest = {
  messages: ChatMessage[];
  code: string;
  modelId: string;
  selection: FaceSelection | null;
  supportsStructuredOutputs: boolean;
  projectId: string | null;
  meshReference?: MeshReference | null;
  /** The printer the printability check measures against. */
  printProfile?: { printer: string };
};

// Each poll is one small database read; a short interval keeps the step list
// close to what the agent is doing.
const POLL_INTERVAL_MS = 1_000;
// The backend gives an API run 300s and a local agent run 900s; past this the
// run is still saved server-side, the studio just stops waiting on it.
const MAX_WAIT_MS = 17 * 60_000;

export function startRun(request: StartRunRequest): Promise<CadRun> {
  return requestJson("/cad/runs", jsonRequest("POST", request));
}

/** The run, with the progress events after sequence number `after`. */
export function getRun(runId: string, after = 0): Promise<CadRun> {
  return requestJson(`/cad/runs/${runId}?after=${after}`);
}

export class RunStillWorkingError extends Error {
  constructor() {
    super(
      "This part is taking longer than usual. It will be saved to your parts when it finishes."
    );
  }
}

type StreamLink = { url: string; expiresAt: string };

// A stream that worked reconnects by itself; after this many errors in a row
// the studio polls instead. A stream that never opened is dropped at once.
const STREAM_MAX_ERRORS = 3;

/**
 * Follow the run's event stream until it reports "done". Resolves false if the
 * stream cannot be used, so the caller can poll instead.
 */
async function streamRun(
  runId: string,
  after: number,
  deliver: (events: RunEvent[]) => void,
  isCancelled: () => boolean,
  deadline: number
): Promise<boolean> {
  if (typeof EventSource === "undefined") return false;
  let link: StreamLink;
  try {
    link = await requestJson<StreamLink>(
      `/cad/runs/${runId}/stream`,
      jsonRequest("POST", {})
    );
  } catch {
    return false;
  }

  return new Promise<boolean>((resolve, reject) => {
    const source = new EventSource(`${BACKEND_ORIGIN}${link.url}&after=${after}`);
    let errors = 0;
    let opened = false;
    const finish = (outcome: boolean | Error) => {
      window.clearInterval(watch);
      source.close();
      if (outcome instanceof Error) reject(outcome);
      else resolve(outcome);
    };
    const watch = window.setInterval(() => {
      if (isCancelled()) finish(new DOMException("Stopped waiting", "AbortError"));
      else if (Date.now() > deadline) finish(false);
    }, 1_000);

    source.addEventListener("open", () => {
      opened = true;
      errors = 0;
    });
    source.addEventListener("progress", (message) => {
      errors = 0;
      try {
        deliver([JSON.parse((message as MessageEvent<string>).data) as RunEvent]);
      } catch {
        /* skip a malformed event; the final run carries the full result */
      }
    });
    source.addEventListener("done", () => finish(true));
    source.addEventListener("error", () => {
      // CLOSED means the browser gave up (for example, the link expired).
      if (
        !opened ||
        source.readyState === EventSource.CLOSED ||
        ++errors >= STREAM_MAX_ERRORS
      ) {
        finish(false);
      }
    });
  });
}

/**
 * Wait until the run finishes, passing new progress events to `onEvents` as
 * they happen. Uses the run's event stream, and polls when the stream is
 * unavailable. Transient network errors are retried.
 */
export async function waitForRun(
  runId: string,
  isCancelled: () => boolean = () => false,
  onEvents: (events: RunEvent[]) => void = () => {}
): Promise<CadRun> {
  const deadline = Date.now() + MAX_WAIT_MS;
  let lastSeq = 0;
  // The stream and the poll can both report an event; pass each on once.
  const deliver = (events: RunEvent[]) => {
    const fresh = events.filter((event) => event.seq > lastSeq);
    if (fresh.length === 0) return;
    lastSeq = fresh[fresh.length - 1].seq;
    onEvents(fresh);
  };

  if (await streamRun(runId, lastSeq, deliver, isCancelled, deadline)) {
    try {
      const run = await getRun(runId, lastSeq);
      deliver(run.events ?? []);
      if (run.status !== "running") return run;
    } catch {
      /* fall through to polling */
    }
  }

  let failures = 0;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    if (isCancelled()) throw new DOMException("Stopped waiting", "AbortError");
    try {
      const run = await getRun(runId, lastSeq);
      failures = 0;
      deliver(run.events ?? []);
      if (run.status !== "running") return run;
    } catch (error) {
      if (++failures >= 5) throw error;
    }
  }
  throw new RunStillWorkingError();
}
