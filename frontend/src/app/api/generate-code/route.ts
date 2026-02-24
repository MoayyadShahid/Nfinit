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
  currentCode: string | undefined
): string | ContentPart[] {
  const codeSnippet =
    currentCode && String(currentCode).trim()
      ? `\n\nCurrent code:\n${currentCode}`
      : "";

  if (typeof lastMsg.content === "string") {
    return lastMsg.content + codeSnippet;
  }

  const textParts = lastMsg.content.filter(
    (p): p is TextPart => p.type === "text"
  );
  const imageParts = lastMsg.content.filter(
    (p): p is ImagePart => p.type === "image_url"
  );

  const combinedText =
    textParts.map((p) => p.text).join("\n") + codeSnippet;

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
/*  Route handler                                                      */
/* ------------------------------------------------------------------ */

export async function POST(request: Request) {
  try {
    const {
      messages,
      code: currentCode,
      modelId,
      supportsStructuredOutputs = false,
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

    const lastUserContent = buildLastUserContent(lastMsg, currentCode);

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const apiMessages: any[] = [
      { role: "system", content: SYSTEM_PROMPT },
      ...chatMessages.slice(0, -1).map((m: ChatMessage) => ({
        role: m.role,
        content: textOf(m.content),
      })),
      { role: "user", content: lastUserContent },
    ];

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const completionParams: any = {
      model: modelId,
      messages: apiMessages,
      temperature: 0,
      top_p: 0.95,
      max_tokens: 4096,
      seed: 42,
    };

    if (supportsStructuredOutputs) {
      completionParams.response_format = CAD_CODE_SCHEMA;
    }

    const completion = await openai.chat.completions.create(completionParams);

    const raw =
      completion.choices[0]?.message?.content?.trim() ?? "";

    if (!raw) {
      return NextResponse.json(
        { error: "Model returned empty content. Try rephrasing your request." },
        { status: 502 }
      );
    }

    let code = extractCode(raw, supportsStructuredOutputs);
    let validationError = validateCode(code);

    /* ---------- one auto-repair retry if validation failed ---------- */
    if (validationError) {
      try {
        const repairMessages = [
          ...apiMessages,
          { role: "assistant", content: code },
          {
            role: "user",
            content: `The previous code had a validation error: ${validationError}\n\nFix the code. Remember: no imports, no markdown fences. Assign the final part to result.`,
          },
        ];

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const retryParams: any = { ...completionParams, messages: repairMessages };
        const retry = await openai.chat.completions.create(retryParams);
        const retryRaw =
          retry.choices[0]?.message?.content?.trim() ?? "";

        if (retryRaw) {
          const retryCode = extractCode(retryRaw, supportsStructuredOutputs);
          const retryValidation = validateCode(retryCode);
          if (!retryValidation) {
            code = retryCode;
            validationError = null;
          }
        }
      } catch {
        /* retry failed — fall through with original error */
      }
    }

    if (validationError) {
      return NextResponse.json(
        { error: `Code validation failed: ${validationError}` },
        { status: 422 }
      );
    }

    return NextResponse.json({ code });
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
