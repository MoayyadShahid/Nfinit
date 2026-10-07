import { SubscriptionRequiredError } from "@/lib/projects";

export type SandboxOperation =
  | "generate-mesh"
  | "inspect-model"
  | "analyze-model"
  | "export-model";

/** Run CAD code in the backend sandbox as the signed-in user. */
export async function sandboxRequest(
  operation: SandboxOperation,
  body: unknown,
  init: { signal?: AbortSignal } = {}
): Promise<Response> {
  const response = await fetch(`/api/cad/${operation}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: init.signal,
  });
  if (response.status === 402) throw new SubscriptionRequiredError();
  return response;
}
