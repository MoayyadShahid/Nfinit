import { proxyToBackend } from "@/lib/backend-proxy";

// Deleting an account cancels its subscription and removes all its data.
export async function DELETE(request: Request) {
  return proxyToBackend(request, ["account"]);
}
