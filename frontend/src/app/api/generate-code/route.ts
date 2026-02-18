import OpenAI from "openai";
import { NextResponse } from "next/server";

const SYSTEM_PROMPT = `You are an expert mechanical engineer. Generate ONLY clean Python code using the build123d library.

API reference (use these exact names):
- 2D sketch objects: Polygon(radius=, side_count=), Circle(), Rectangle()
- 3D primitives: Box(), Cylinder(), Sphere(), Torus()
- Operations: extrude(), revolve(), loft(), fillet(), chamfer()
- Contexts: BuildPart(), BuildSketch(), BuildLine()
- Use Polygon (not regular_polygon) for regular polygons

Every script must end by assigning the final 3D part to a variable named result. Do not provide explanations, markdown blocks, or comments.`;

type ChatMessage = { role: "user" | "assistant"; content: string };

export async function POST(request: Request) {
  try {
    const { messages, code: currentCode, modelId } = await request.json();

    if (!messages || !Array.isArray(messages) || messages.length === 0 || !modelId) {
      return NextResponse.json(
        { error: "messages (non-empty array) and modelId are required" },
        { status: 400 }
      );
    }

    const apiKey = process.env.OPENROUTER_API_KEY;
    if (!apiKey) {
      return NextResponse.json(
        { error: "OPENROUTER_API_KEY is not configured" },
        { status: 500 }
      );
    }

    const openai = new OpenAI({
      baseURL: "https://openrouter.ai/api/v1",
      apiKey,
    });

    const chatMessages = messages as ChatMessage[];
    const lastMsg = chatMessages[chatMessages.length - 1];
    if (lastMsg.role !== "user") {
      return NextResponse.json(
        { error: "Last message must be from user" },
        { status: 400 }
      );
    }

    const codeBlock =
      currentCode && String(currentCode).trim()
        ? `\n\nCurrent code:\n\`\`\`python\n${currentCode}\n\`\`\``
        : "";
    const lastUserContent = lastMsg.content + codeBlock;

    const apiMessages: { role: "system" | "user" | "assistant"; content: string }[] = [
      { role: "system", content: SYSTEM_PROMPT },
      ...chatMessages.slice(0, -1).map((m: ChatMessage) => ({
        role: m.role,
        content: m.content,
      })),
      { role: "user", content: lastUserContent },
    ];

    const completion = await openai.chat.completions.create({
      model: modelId,
      messages: apiMessages,
    });

    let code = completion.choices[0]?.message?.content?.trim() ?? "";

    const markdownMatch = code.match(/```(?:python)?\s*([\s\S]*?)```/);
    if (markdownMatch) {
      code = markdownMatch[1].trim();
    }

    return NextResponse.json({ code });
  } catch (error) {
    console.error("Generate code error:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to generate code" },
      { status: 500 }
    );
  }
}
