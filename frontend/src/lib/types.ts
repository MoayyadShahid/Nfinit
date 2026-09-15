export type TextPart = { type: "text"; text: string };
export type ImagePart = {
  type: "image_url";
  image_url: { url: string; detail?: "auto" | "low" | "high" };
};
export type ContentPart = TextPart | ImagePart;

export type AgentTraceStep = {
  node: "plan" | "generate" | "inspect" | "repair";
  status: "complete" | "passed" | "failed";
  detail: string;
  duration_ms?: number;
};

export type ModelInspection = {
  valid: boolean;
  shape_type?: string;
  solid_count?: number;
  volume_mm3?: number;
  bounding_box_mm?: { x: number; y: number; z: number };
};

export type FaceSelection = {
  point: [number, number, number];
  normal: [number, number, number];
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string | ContentPart[];
  agent?: {
    runId?: string;
    plan: string;
    trace: AgentTraceStep[];
    inspection?: ModelInspection;
    usage?: {
      input_tokens: number;
      output_tokens: number;
      total_tokens: number;
    };
  };
};

export function getTextContent(content: string | ContentPart[]): string {
  if (typeof content === "string") return content;
  return content
    .filter((p): p is TextPart => p.type === "text")
    .map((p) => p.text)
    .join("\n");
}

export function getImageUrls(content: string | ContentPart[]): string[] {
  if (typeof content === "string") return [];
  return content
    .filter((p): p is ImagePart => p.type === "image_url")
    .map((p) => p.image_url.url);
}
