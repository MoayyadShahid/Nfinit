import { NextResponse } from "next/server";

const BACKEND_URL =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "http://localhost:8000";

export async function POST(request: Request) {
  try {
    const payload = await request.json();
    const response = await fetch(`${BACKEND_URL}/cad/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(180_000),
      cache: "no-store",
    });

    const data = await response.json().catch(() => ({
      error: `CAD backend returned HTTP ${response.status}.`,
    }));

    if (!response.ok) {
      return NextResponse.json(
        {
          ...data,
          error: data.error || data.detail || "CAD generation failed.",
        },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error
            ? `Could not reach the CAD backend: ${error.message}`
            : "Could not reach the CAD backend.",
      },
      { status: 502 }
    );
  }
}
