import { safeNextPath } from "@/lib/safe-path";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const origin = request.headers.get("origin");
  if (origin && origin !== new URL(request.url).origin) {
    return NextResponse.json({ detail: "Cross-site request refused." }, { status: 403 });
  }

  let value: unknown;
  try {
    value = (await request.json()) as { next?: unknown };
  } catch {
    return NextResponse.json({ detail: "Invalid request." }, { status: 400 });
  }
  const candidate =
    typeof value === "object" && value !== null && "next" in value
      ? (value as { next?: unknown }).next
      : null;
  const next = safeNextPath(typeof candidate === "string" ? candidate : null);
  const response = NextResponse.json({ saved: true });
  response.cookies.set("nfinit-auth-next", next, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 600,
  });
  return response;
}
