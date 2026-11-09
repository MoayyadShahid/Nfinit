import type { ChatMessage, FaceSelection, ModelInspection, MeshReference } from "@/lib/types";

export type ProjectState = {
  code: string;
  messages: ChatMessage[];
  modelId: string;
  selection: FaceSelection | null;
  lastRunId: string | null;
  meshReference?: MeshReference | null;
};

/** A version in a list: enough to show and pick it, without its state. */
export type RevisionSummary = {
  id: string;
  projectId: string;
  revisionNumber: number;
  createdAt: string;
};

export type ProjectRevision = RevisionSummary & {
  state: ProjectState;
};

export function toRevisionSummary(revision: RevisionSummary): RevisionSummary {
  const { id, projectId, revisionNumber, createdAt } = revision;
  return { id, projectId, revisionNumber, createdAt };
}

export type ProjectSummary = {
  id: string;
  name: string;
  revisionCount: number;
  createdAt: string;
  updatedAt: string;
  thumbnailUpdatedAt: string | null;
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

export async function requestJson<T>(
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

async function requestEmpty(path: string, init: RequestInit): Promise<void> {
  const response = await fetch(`/api${path}`, { ...init, cache: "no-store" });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(errorMessage(payload, `Request failed (${response.status})`));
  }
}

export function jsonRequest(
  method: "POST" | "PATCH",
  body: unknown
): RequestInit {
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

/** The project's versions, newest first, without their (large) states. */
export function listRevisions(projectId: string): Promise<RevisionSummary[]> {
  return requestJson(`/projects/${projectId}/revisions?state=false`);
}

/** One version with its state: its code and the chat up to it. */
export function getRevision(
  projectId: string,
  revisionNumber: number
): Promise<ProjectRevision> {
  return requestJson(`/projects/${projectId}/revisions/${revisionNumber}`);
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

export function renameProject(
  projectId: string,
  name: string
): Promise<ProjectDetail> {
  return requestJson(`/projects/${projectId}`, jsonRequest("PATCH", { name }));
}

export function deleteProject(projectId: string): Promise<void> {
  return requestEmpty(`/projects/${projectId}`, { method: "DELETE" });
}

// Meshes download and run events stream straight from the backend: a GLB
// can exceed what the Next.js proxy may return, and a stream outlasts it.
export const BACKEND_ORIGIN = (
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000"
).replace(/\/$/, "");

export type RevisionMesh = {
  /** Signed, short-lived link to the GLB. */
  url: string;
  expiresAt: string;
  bytes: number;
  inspection: ModelInspection;
};

/** The revision's built mesh, built on the backend only if it is not stored. */
export async function getRevisionMesh(
  projectId: string,
  revisionNumber: number
): Promise<RevisionMesh> {
  const mesh = await requestJson<RevisionMesh>(
    `/projects/${projectId}/revisions/${revisionNumber}/mesh`
  );
  return { ...mesh, url: `${BACKEND_ORIGIN}${mesh.url}` };
}

export function uploadThumbnail(projectId: string, image: Blob): Promise<void> {
  return requestEmpty(`/projects/${projectId}/thumbnail`, {
    method: "PUT",
    headers: { "Content-Type": image.type },
    body: image,
  });
}

/** Versioned so a new capture busts the browser's immutable cache entry. */
export function thumbnailUrl(project: ProjectSummary): string | null {
  return project.thumbnailUpdatedAt
    ? `/api/projects/${project.id}/thumbnail?v=${encodeURIComponent(
        project.thumbnailUpdatedAt
      )}`
    : null;
}
