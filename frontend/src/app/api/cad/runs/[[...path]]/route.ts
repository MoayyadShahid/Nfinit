import { proxyToBackend } from "@/lib/backend-proxy";

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

async function proxy(request: Request, context: RouteContext) {
  const { path = [] } = await context.params;
  return proxyToBackend(request, ["cad", "runs", ...path]);
}

export const GET = proxy;
export const POST = proxy;
