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
  path: string,
  init?: RequestInit
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    cache: "no-store",
  });
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

export function listProjects(): Promise<ProjectSummary[]> {
  return requestJson("/projects");
}

export function getProject(projectId: string): Promise<ProjectDetail> {
  return requestJson(`/projects/${projectId}`);
}

export function listRevisions(projectId: string): Promise<ProjectRevision[]> {
  return requestJson(`/projects/${projectId}/revisions`);
}

export function createProject(
  name: string,
  state: ProjectState
): Promise<ProjectDetail> {
  return requestJson(
    "/projects",
    jsonRequest("POST", { name, state })
  );
}

export function addRevision(
  projectId: string,
  state: ProjectState
): Promise<ProjectRevision> {
  return requestJson(
    `/projects/${projectId}/revisions`,
    jsonRequest("POST", { state })
  );
}
