export type TextPart = { type: "text"; text: string };
export type ImagePart = {
  type: "image_url";
  image_url: { url: string; detail?: "auto" | "low" | "high" };
};
export type ContentPart = TextPart | ImagePart;

export type AgentTraceStep = {
  node: "retrieve" | "plan" | "generate" | "inspect" | "repair";
  status: "complete" | "passed" | "failed";
  detail: string;
  duration_ms?: number;
};

/** One progress step of a CAD run, as the backend records it. */
export type RunEvent = {
  seq: number;
  stage: AgentTraceStep["node"] | "mesh" | string;
  status: "started" | AgentTraceStep["status"] | string;
  message: string;
  attempt: number | null;
  durationMs: number | null;
  createdAt: string;
};

export type ModelInspection = {
  valid: boolean;
  shape_type?: string;
  solid_count?: number;
  volume_mm3?: number;
  bounding_box_mm?: { x: number; y: number; z: number };
  verification?: "unverified" | "measured" | "failed";
  checks?: { name: string; actual: number; expected: number; tolerance: number; passed: boolean }[];
  /** Holes, bosses and rounded edges counted from the faces. */
  census?: GeometryCensus | { error: string };
  solids?: {
    volume_mm3: number;
    bounding_box_mm: { x: number; y: number; z: number };
    min_mm: [number, number, number];
    manifold: boolean;
    inverted: boolean;
  }[];
  /** Things that built but are probably wrong, such as a floating feature. */
  warnings?: string[];
};

export type CensusCylinder = {
  diameter_mm: number;
  count: number;
  axis: [number, number, number];
  length_mm: number;
  centers_mm: [number, number, number][];
};

export type GeometryCensus = {
  holes: CensusCylinder[];
  bosses: CensusCylinder[];
  rounded_edges: { radius_mm: number; count: number; surface: "cylinder" | "torus" | "sphere" }[];
  partial_cylinders: number;
  face_counts: Record<string, number>;
  features?: { id: string; operation: string; owned_faces: number }[];
};

export type MeshReference = {
  name: string;
  data: string;
  units: "mm" | "in";
  mode: "preserve" | "reconstruct";
  facts: { triangles: number; closed: boolean; oriented: boolean; bounds: { x: number; y: number; z: number } };
};

export type FaceSelection = {
  point: [number, number, number];
  normal: [number, number, number];
  entityId?: string;
  topologyVersion?: string;
  surfaceType?: string;
  confidence?: number;
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
