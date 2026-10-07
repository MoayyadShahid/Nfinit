import { proxyToBackend } from "@/lib/backend-proxy";

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

async function proxy(request: Request, context: RouteContext) {
  const { path = [] } = await context.params;
  if (path[0] === "webhook") {
    // Stripe calls the backend directly; the proxy would drop its signature.
    return Response.json({ detail: "Not found." }, { status: 404 });
  }
  return proxyToBackend(request, ["billing", ...path]);
}

export const GET = proxy;
export const POST = proxy;
