import { Annotation, END, START, StateGraph } from "@langchain/langgraph";
import OpenAI from "openai";
import { NextResponse } from "next/server";

const SYSTEM_PROMPT = `
<role>
You are a production build123d CAD code generator for an AI CAD IDE.
Your job is to return ONLY executable Python code that runs in a restricted backend scope.
</role>

<output_rules>
- Return only Python code (no markdown fences)
- No explanations
- Use short section comments to label major construction steps
  (e.g. # parameters, # base plate, # mounting holes)
- Do NOT write explanatory prose, docstrings, or line-by-line narration
- No import statements
- Use millimeters for all dimensions
- Prefer readable dimension variables (e.g. width = 80.0, thickness = 6.0)
- Prefer a single main context: with BuildPart() as part:
- End with a final assignment to result
- Preferred final line: result = part.part
</output_rules>

<editing_rules>
- If "Current code" is provided, edit that code to satisfy the user request instead of rewriting from scratch, unless rewriting is necessary.
- Preserve existing parameter names and style where possible.
- Make minimal changes when the user asks for a small modification.
</editing_rules>

<image_rules>
- If an image is attached, use it as a geometry reference.
- Match topology, symmetry, feature placement, and proportions from the image.
- Use explicit dimensions from the user text when provided.
- If dimensions are missing, choose reasonable defaults in mm and keep them parameterized.
</image_rules>

<geometry_rules>
- Build robust solids first, then apply fillets/chamfers last.
- Avoid self-intersections and fragile constructions.
- Prefer simple, predictable constructions over clever one-liners.
- Use subtraction mode for holes/cutouts when appropriate.
- Keep the script executable in one pass.
</geometry_rules>

<api_reference>
All names below are pre-loaded in the execution scope. Use ONLY these.

CONTEXTS:
  BuildPart()  BuildSketch()  BuildLine()

LOCATIONS (context managers for placing features):
  Locations(*pts)                        — explicit (x,y) or (x,y,z) positions
  GridLocations(x_spacing, y_spacing, x_count, y_count)
  PolarLocations(radius, count, start_angle=0, angular_range=360)
  HexLocations(apothem, x_count, y_count)

GEOMETRY HELPERS:
  Pos(x, y, z)        — translate
  Rotation(x, y, z)   — rotate (degrees)
  Rot(x, y, z)        — alias for Rotation
  Plane.XY  Plane.XZ  Plane.YZ  Plane.front  Plane.back  Plane.top  Plane.bottom
  Axis.X  Axis.Y  Axis.Z
  Vector(x, y, z)
  Location

2D SKETCH OBJECTS (inside BuildSketch):
  Circle(radius)
  Ellipse(x_radius, y_radius)
  Rectangle(width, height)
  RectangleRounded(width, height, radius)
  RegularPolygon(radius, side_count)     — regular polygons ONLY
  Polygon(*pts)                          — explicit point list ONLY
  Triangle(a, b, c, ...)
  Trapezoid(width, height, left_side_angle, right_side_angle)
  SlotOverall(width, height)
  SlotCenterToCenter(center_separation, height)
  SlotCenterPoint(center, point, height)
  SlotArc(arc, height)
  Text(txt, font_size)

1D LINE OBJECTS (inside BuildLine):
  Line(*pts)  Polyline(*pts)  Spline(*pts)
  CenterArc(center, radius, start_angle, arc_size)
  RadiusArc(start_pt, end_pt, radius)
  SagittaArc(start_pt, end_pt, sag)
  TangentArc(*pts)  ThreePointArc(*pts)
  Helix(pitch, height, radius)
  Bezier(*pts)  PolarLine(start, length, angle)
  FilletPolyline(*pts, radius=)

3D PART OBJECTS (inside BuildPart):
  Box(length, width, height)
  Cylinder(radius, height)
  Sphere(radius)
  Cone(bottom_radius, top_radius, height)
  Torus(major_radius, minor_radius)
  Wedge(xsize, ysize, zsize, xmin, zmin, xmax, zmax)
  Hole(radius, depth)
  CounterBoreHole(radius, counter_bore_radius, counter_bore_depth, depth)
  CounterSinkHole(radius, counter_sink_radius, depth)

OPERATIONS BY CONTEXT:
  BuildLine:   add  mirror  offset  scale  split
  BuildSketch: add  fillet  chamfer  full_round  make_face  make_hull
               mirror  offset  scale  split  sweep  trace
  BuildPart:   add  extrude(amount=, both=False)  revolve(axis=, revolution_arc=360)
               loft  sweep  fillet  chamfer  mirror  offset  split
               section  scale  draft

ENUMS:
  Mode:       ADD, SUBTRACT, INTERSECT, REPLACE
  Align:      MIN, CENTER, MAX
  GeomType:   LINE, CIRCLE, PLANE, CYLINDER, CONE, SPHERE, TORUS, BEZIER, BSPLINE, ELLIPSE
  Until:      FIRST, LAST, NEXT, PREVIOUS
  Keep:       ALL, TOP, BOTTOM, BOTH, INSIDE, OUTSIDE
  Kind:       ARC, INTERSECTION, TANGENT
  SortBy:     LENGTH, RADIUS, AREA, VOLUME, DISTANCE
  Transition: RIGHT, ROUND, TRANSFORMED
  Select:     ALL, LAST, NEW

SELECTORS (on Builder: .vertices() .edges() .faces() .wires() .solids()):
  |  — filter_by(Axis, Plane, or GeomType)
  >  — sort_by ascending       <  — sort_by descending
  >> — group_by last            << — group_by first
  [] — python indexing/slicing
  Examples:
    part.edges() | Axis.Z                   — edges parallel to Z
    part.edges().filter_by(GeomType.LINE)   — only straight edges
    (part.faces() >> Axis.Z)[0]             — topmost face
    fillet(part.edges() | Axis.Z, radius=1) — fillet vertical edges
</api_reference>

<examples>
<example title="simple box">
width, depth, height = 80.0, 50.0, 12.0
with BuildPart() as part:
    Box(width, depth, height)
result = part.part
</example>

<example title="box with central hole">
width, depth, height = 80.0, 50.0, 10.0
hole_d = 12.0
with BuildPart() as part:
    Box(width, depth, height)
    Cylinder(radius=hole_d / 2, height=height, mode=Mode.SUBTRACT)
result = part.part
</example>

<example title="plate with slot cutout">
plate_w, plate_h, thickness = 100.0, 60.0, 6.0
slot_w, slot_h = 30.0, 10.0
with BuildPart() as part:
    with BuildSketch():
        Rectangle(plate_w, plate_h)
        Rectangle(slot_w, slot_h, mode=Mode.SUBTRACT)
    extrude(amount=thickness)
result = part.part
</example>

<example title="extruded hex">
hex_r, thickness = 20.0, 8.0
with BuildPart() as part:
    with BuildSketch():
        RegularPolygon(radius=hex_r, side_count=6)
    extrude(amount=thickness)
result = part.part
</example>

<example title="motor mount plate — polar holes, fillets, selectors">
# parameters
plate_r = 40.0
plate_t = 3.0
center_hole_r = 5.0
mount_r = 30.0
mount_hole_r = 1.6
bolt_count = 6
fillet_r = 1.0

with BuildPart() as part:
    # base plate
    with BuildSketch():
        Circle(plate_r)
        Circle(center_hole_r, mode=Mode.SUBTRACT)
    extrude(amount=plate_t)

    # polar bolt holes
    with BuildSketch(part.faces() >> Axis.Z):
        with PolarLocations(mount_r, bolt_count):
            Circle(mount_hole_r, mode=Mode.SUBTRACT)
    extrude(amount=-plate_t, mode=Mode.SUBTRACT)

    # fillet top edges
    fillet(part.edges() >> Axis.Z, radius=fillet_r)

result = part.part
</example>

<example title="bracket with rounded rect, multiple features">
# parameters
body_w, body_h, body_t = 60.0, 30.0, 5.0
corner_r = 4.0
hole_spacing = 40.0
hole_r = 2.5
slot_w, slot_h = 20.0, 6.0

with BuildPart() as part:
    # body
    with BuildSketch():
        RectangleRounded(body_w, body_h, corner_r)
    extrude(amount=body_t)

    # mounting holes
    with BuildSketch(part.faces() >> Axis.Z):
        with GridLocations(hole_spacing, 0, 2, 1):
            Circle(hole_r, mode=Mode.SUBTRACT)
    extrude(amount=-body_t, mode=Mode.SUBTRACT)

    # center slot
    with BuildSketch(part.faces() >> Axis.Z):
        SlotOverall(slot_w, slot_h, mode=Mode.SUBTRACT)
    extrude(amount=-body_t, mode=Mode.SUBTRACT)

result = part.part
</example>
</examples>
`.trim();

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type TextPart = { type: "text"; text: string };
type ImagePart = {
  type: "image_url";
  image_url: { url: string; detail?: "auto" | "low" | "high" };
};
type ContentPart = TextPart | ImagePart;

type ChatMessage = {
  role: "user" | "assistant";
  content: string | ContentPart[];
};

/* ------------------------------------------------------------------ */
/*  Validation                                                         */
/* ------------------------------------------------------------------ */

const BLOCKED_PATTERNS: { re: RegExp; label: string }[] = [
  { re: /^\s*(import\s|from\s+\S+\s+import)/m, label: "import statement" },
  { re: /\bexec\s*\(/, label: "exec()" },
  { re: /\beval\s*\(/, label: "eval()" },
  { re: /\bopen\s*\(/, label: "open()" },
  { re: /__\w+__/, label: "dunder attribute" },
];

function validateCode(code: string): string | null {
  if (!code.trim()) return "Generated code is empty.";

  for (const { re, label } of BLOCKED_PATTERNS) {
    if (re.test(code)) {
      return `Generated code contains forbidden pattern: ${label}`;
    }
  }

  const hasResult = /\bresult\s*=/.test(code);
  const hasBuildPart = /with\s+BuildPart\s*\(/.test(code);

  if (!hasResult && !hasBuildPart) {
    return "Generated code must contain 'result = ...' or 'with BuildPart() as part:'.";
  }

  return null;
}

/* ------------------------------------------------------------------ */
/*  Code extraction (structured JSON → markdown fence → raw)           */
/* ------------------------------------------------------------------ */

function extractCode(raw: string, useStructured: boolean): string {
  if (!raw) return "";

  if (useStructured) {
    try {
      const parsed = JSON.parse(raw);
      if (typeof parsed.code === "string") return parsed.code.trim();
    } catch {
      /* fall through to fence extraction */
    }
  }

  const fenceMatch = raw.match(/```(?:python|py|json)?\s*\n?([\s\S]*?)```/);
  if (fenceMatch) {
    const inner = fenceMatch[1].trim();
    if (useStructured) {
      try {
        const parsed = JSON.parse(inner);
        if (typeof parsed.code === "string") return parsed.code.trim();
      } catch {
        /* not JSON inside fence — use as raw code */
      }
    }
    return inner;
  }

  return raw.trim();
}

/* ------------------------------------------------------------------ */
/*  Content helpers                                                    */
/* ------------------------------------------------------------------ */

function textOf(content: string | ContentPart[]): string {
  if (typeof content === "string") return content;
  return content
    .filter((p): p is TextPart => p.type === "text")
    .map((p) => p.text)
    .join("\n");
}

function buildLastUserContent(
  lastMsg: ChatMessage,
  currentCode: string | undefined,
  selection?: SelectionContext | null
): string | ContentPart[] {
  const codeSnippet =
    currentCode && String(currentCode).trim()
      ? `\n\nCurrent code:\n${currentCode}`
      : "";
  const selectionSnippet = selection
    ? `\n\nSelected face in the current model:\n- point (mm): ${selection.point.join(", ")}\n- outward normal: ${selection.normal.join(", ")}\nApply spatial references such as "this face", "here", or "selected area" to this face.`
    : "";

  if (typeof lastMsg.content === "string") {
    return lastMsg.content + selectionSnippet + codeSnippet;
  }

  const textParts = lastMsg.content.filter(
    (p): p is TextPart => p.type === "text"
  );
  const imageParts = lastMsg.content.filter(
    (p): p is ImagePart => p.type === "image_url"
  );

  const combinedText =
    textParts.map((p) => p.text).join("\n") + selectionSnippet + codeSnippet;

  return [
    { type: "text", text: combinedText } as TextPart,
    ...imageParts,
  ];
}

/* ------------------------------------------------------------------ */
/*  Structured-output response_format (json_schema)                    */
/* ------------------------------------------------------------------ */

const CAD_CODE_SCHEMA = {
  type: "json_schema" as const,
  json_schema: {
    name: "cad_code",
    strict: true,
    schema: {
      type: "object",
      properties: {
        code: { type: "string" },
      },
      required: ["code"],
      additionalProperties: false,
    },
  },
};

/* ------------------------------------------------------------------ */
/*  LangGraph CAD agent                                                */
/* ------------------------------------------------------------------ */

type SelectionContext = {
  point: [number, number, number];
  normal: [number, number, number];
};

type ModelInspection = {
  valid: boolean;
  shape_type?: string;
  solid_count?: number;
  volume_mm3?: number;
  bounding_box_mm?: { x: number; y: number; z: number };
  error?: string;
};

type TraceStep = {
  node: "plan" | "generate" | "inspect" | "repair";
  status: "complete" | "passed" | "failed";
  detail: string;
};

const MAX_REPAIR_ATTEMPTS = 3;

const AgentState = Annotation.Root({
  messages: Annotation<ChatMessage[]>(),
  currentCode: Annotation<string>(),
  modelId: Annotation<string>(),
  supportsStructuredOutputs: Annotation<boolean>(),
  selection: Annotation<SelectionContext | null>(),
  plan: Annotation<string>(),
  code: Annotation<string>(),
  inspection: Annotation<ModelInspection | null>(),
  validationError: Annotation<string | null>(),
  repairAttempts: Annotation<number>(),
  trace: Annotation<TraceStep[]>(),
});

type AgentStateType = typeof AgentState.State;

function conversationMessages(state: AgentStateType) {
  const lastMsg = state.messages[state.messages.length - 1];
  return [
    ...state.messages.slice(0, -1).map((message) => ({
      role: message.role,
      content: textOf(message.content),
    })),
    {
      role: "user" as const,
      content: buildLastUserContent(
        lastMsg,
        state.currentCode,
        state.selection
      ),
    },
  ];
}

async function complete(
  openai: OpenAI,
  state: AgentStateType,
  messages: unknown[],
  structured = false
) {
  // OpenRouter accepts OpenAI-compatible payloads, including its reasoning extension.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const params: any = {
    model: state.modelId,
    messages,
    max_tokens: 8192,
    reasoning: { effort: "high" },
  };
  if (structured && state.supportsStructuredOutputs) {
    params.response_format = CAD_CODE_SCHEMA;
  }

  const completion = await openai.chat.completions.create(params);
  return completion.choices[0]?.message?.content?.trim() ?? "";
}

function appendTrace(state: AgentStateType, step: TraceStep): TraceStep[] {
  return [...state.trace, step];
}

function createCadGraph(openai: OpenAI) {
  const plan = async (state: AgentStateType) => {
    const raw = await complete(openai, state, [
      {
        role: "system",
        content: `You are the lead mechanical product designer in an AI CAD IDE.
Turn the request into a concise implementation plan for a build123d coding agent.
Specify intent, parameterized dimensions, feature order, symmetry/constraints, and likely manufacturing process.
When current code exists, identify the smallest robust edit. Respect the selected-face coordinates.
Do not produce Python code.`,
      },
      ...conversationMessages(state),
    ]);
    if (!raw) throw new Error("The planning model returned an empty response.");

    return {
      plan: raw,
      trace: appendTrace(state, {
        node: "plan",
        status: "complete",
        detail: "Translated the request into geometry and manufacturing constraints.",
      }),
    };
  };

  const generate = async (state: AgentStateType) => {
    const raw = await complete(
      openai,
      state,
      [
        { role: "system", content: SYSTEM_PROMPT },
        ...conversationMessages(state),
        {
          role: "user",
          content: `Implement this approved design plan:\n\n${state.plan}`,
        },
      ],
      true
    );
    if (!raw) throw new Error("The CAD model returned an empty response.");

    const code = extractCode(raw, state.supportsStructuredOutputs);
    return {
      code,
      trace: appendTrace(state, {
        node: "generate",
        status: "complete",
        detail: "Generated parameterized build123d geometry.",
      }),
    };
  };

  const inspect = async (state: AgentStateType) => {
    const staticError = validateCode(state.code);
    if (staticError) {
      return {
        validationError: staticError,
        inspection: { valid: false, error: staticError },
        trace: appendTrace(state, {
          node: "inspect",
          status: "failed",
          detail: staticError,
        }),
      };
    }

    const backendUrl =
      process.env.BACKEND_URL ||
      process.env.NEXT_PUBLIC_BACKEND_URL ||
      "http://localhost:8000";
    try {
      const response = await fetch(`${backendUrl}/inspect-model`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: state.code }),
        signal: AbortSignal.timeout(30_000),
      });
      if (!response.ok) {
        throw new Error(`Geometry engine returned HTTP ${response.status}`);
      }

      const inspection = (await response.json()) as ModelInspection;
      const validationError = inspection.valid
        ? null
        : inspection.error || "Geometry execution failed.";
      const dimensions = inspection.bounding_box_mm;
      return {
        inspection,
        validationError,
        trace: appendTrace(state, {
          node: "inspect",
          status: inspection.valid ? "passed" : "failed",
          detail: inspection.valid
            ? `Built ${inspection.solid_count ?? 0} solid(s); bounds ${dimensions?.x ?? "?"} × ${dimensions?.y ?? "?"} × ${dimensions?.z ?? "?"} mm.`
            : validationError!,
        }),
      };
    } catch (error) {
      const validationError =
        error instanceof Error ? error.message : "Geometry inspection failed.";
      return {
        inspection: { valid: false, error: validationError },
        validationError,
        trace: appendTrace(state, {
          node: "inspect",
          status: "failed",
          detail: validationError,
        }),
      };
    }
  };

  const repair = async (state: AgentStateType) => {
    const raw = await complete(
      openai,
      state,
      [
        { role: "system", content: SYSTEM_PROMPT },
        {
          role: "user",
          content: `Design plan:\n${state.plan}\n\nThe following build123d code failed execution or validation:\n\n${state.code}\n\nFailure:\n${state.validationError}\n\nRepair the code while preserving the design intent. Return only the complete corrected code.`,
        },
      ],
      true
    );
    if (!raw) throw new Error("The repair model returned an empty response.");

    return {
      code: extractCode(raw, state.supportsStructuredOutputs),
      repairAttempts: state.repairAttempts + 1,
      trace: appendTrace(state, {
        node: "repair",
        status: "complete",
        detail: `Repaired geometry after validation failure (attempt ${state.repairAttempts + 1}/${MAX_REPAIR_ATTEMPTS}).`,
      }),
    };
  };

  return new StateGraph(AgentState)
    .addNode("plan", plan)
    .addNode("generate", generate)
    .addNode("inspect", inspect)
    .addNode("repair", repair)
    .addEdge(START, "plan")
    .addEdge("plan", "generate")
    .addEdge("generate", "inspect")
    .addConditionalEdges("inspect", (state) => {
      if (!state.validationError) return END;
      return state.repairAttempts < MAX_REPAIR_ATTEMPTS ? "repair" : END;
    })
    .addEdge("repair", "inspect")
    .compile();
}

/* ------------------------------------------------------------------ */
/*  Route handler                                                      */
/* ------------------------------------------------------------------ */

export async function POST(request: Request) {
  try {
    const {
      messages,
      code: currentCode,
      modelId,
      supportsStructuredOutputs = false,
      selection = null,
    } = await request.json();

    if (
      !messages ||
      !Array.isArray(messages) ||
      messages.length === 0 ||
      !modelId
    ) {
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

    const graph = createCadGraph(openai);
    const result = await graph.invoke({
      messages: chatMessages,
      currentCode: typeof currentCode === "string" ? currentCode : "",
      modelId,
      supportsStructuredOutputs: Boolean(supportsStructuredOutputs),
      selection: selection as SelectionContext | null,
      plan: "",
      code: "",
      inspection: null,
      validationError: null,
      repairAttempts: 0,
      trace: [],
    });

    if (result.validationError) {
      return NextResponse.json(
        {
          error: `The CAD agent could not produce valid geometry after ${MAX_REPAIR_ATTEMPTS} repairs: ${result.validationError}`,
          plan: result.plan,
          trace: result.trace,
        },
        { status: 422 }
      );
    }

    return NextResponse.json({
      code: result.code,
      plan: result.plan,
      inspection: result.inspection,
      trace: result.trace,
    });
  } catch (error) {
    console.error("Generate code error:", error);
    return NextResponse.json(
      {
        error:
          error instanceof Error ? error.message : "Failed to generate code",
      },
      { status: 500 }
    );
  }
}
