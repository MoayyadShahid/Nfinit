import type { ChatMessage, FaceSelection } from "@/lib/types";

export type ProjectState = {
  code: string;
  messages: ChatMessage[];
  modelId: string;
  selection: FaceSelection | null;
  lastRunId: string | null;
};

export type ProjectRevision = {
  id: string;
  projectId: string;
  revisionNumber: number;
  state: ProjectState;
  createdAt: string;
};

export type ProjectSummary = {
  id: string;
  name: string;
  revisionCount: number;
  createdAt: string;
  updatedAt: string;
};

export type ProjectDetail = ProjectSummary & {
  latestRevision: ProjectRevision | null;
};

function errorMessage(payload: unknown, fallback: string): string {
  if (
    payload &&
    typeof payload === "object" &&
    "detail" in payload &&
    typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return fallback;
}

async function requestJson<T>(
  backendUrl: string,
  path: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(`${backendUrl}${path}`, init);
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(errorMessage(payload, `Request failed (${response.status})`));
  }
  return payload as T;
}

function jsonRequest(method: "POST" | "PATCH", body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function listProjects(backendUrl: string): Promise<ProjectSummary[]> {
  return requestJson(backendUrl, "/projects");
}

export function getProject(
  backendUrl: string,
  projectId: string
): Promise<ProjectDetail> {
  return requestJson(backendUrl, `/projects/${projectId}`);
}

export function listRevisions(
  backendUrl: string,
  projectId: string
): Promise<ProjectRevision[]> {
  return requestJson(backendUrl, `/projects/${projectId}/revisions`);
}

export function createProject(
  backendUrl: string,
  name: string,
  state: ProjectState
): Promise<ProjectDetail> {
  return requestJson(
    backendUrl,
    "/projects",
    jsonRequest("POST", { name, state })
  );
}

export function addRevision(
  backendUrl: string,
  projectId: string,
  state: ProjectState
): Promise<ProjectRevision> {
  return requestJson(
    backendUrl,
    `/projects/${projectId}/revisions`,
    jsonRequest("POST", { state })
  );
}
