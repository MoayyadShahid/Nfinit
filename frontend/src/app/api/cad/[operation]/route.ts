import { proxyToBackend } from "@/lib/backend-proxy";

// The sandbox endpoints run CAD code, so they go through the proxy like
// everything else: the backend needs the user's token to check their plan.
const OPERATIONS = new Set([
  "generate-mesh",
  "inspect-model",
  "analyze-model",
  "export-model",
  "import-stl",
]);
const SANDBOX_TIMEOUT_MS = 110_000;

export const maxDuration = 120;

type RouteContext = {
  params: Promise<{ operation: string }>;
};

export async function POST(request: Request, context: RouteContext) {
  const { operation } = await context.params;
  if (!OPERATIONS.has(operation)) {
    return Response.json({ detail: "Not found." }, { status: 404 });
  }
  return proxyToBackend(request, [operation], SANDBOX_TIMEOUT_MS);
}

export async function GET(request: Request, context: RouteContext) {
  const { operation } = await context.params;
  if (operation !== "local-agents") return Response.json({ detail: "Not found." }, { status: 404 });
  return proxyToBackend(request, [operation]);
}
