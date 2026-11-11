"""Small stdio MCP bridge for installed agents; all CAD runs in the sandbox.

No arbitrary paths, shell commands or network tools are exposed. This process
serves one temporary design workspace and is killed with its owning agent.
"""
import base64
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.acceptance import (  # noqa: E402
    DECLARE_SCHEMA,
    change_report,
    evaluate,
    parse_requirements,
    uncovered_numbers,
)
from execution import printability_code, query_code, render_code, review_code  # noqa: E402
from execution.references import compare_reference  # noqa: E402
from agent.feedback import agent_view, printability_view  # noqa: E402

# What one run may spend, reported back to the agent in every tool result.
BUDGETS = {"builds": 8, "declarations": 4, "questions": 20, "views": 12, "print_checks": 3}

VIEW_SCHEMA = {
    "type": "object",
    "properties": {"views": {
        "type": "array",
        "minItems": 1,
        "maxItems": 4,
        "items": {
            "type": "object",
            "properties": {
                "camera": {"description": (
                    "iso, iso_back, front, back, right, left, top or bottom; or "
                    "{\"azimuth\": degrees, \"elevation\": degrees}")},
                "mode": {"enum": ["shaded", "hidden_line", "xray"]},
                "section": {"type": "object", "description": (
                    "Cut the part with a plane: {\"axis\": \"x\"|\"y\"|\"z\", \"at\": mm, "
                    "\"keep\": \"below\"|\"above\"}. Cut faces are drawn red.")},
                "focus": {"type": "string", "description": "A face id or feature id to centre and zoom on."},
                "highlight": {"type": "array", "items": {"type": "string"}, "maxItems": 20,
                              "description": "Face ids or feature ids drawn in orange."},
                "size": {"enum": ["normal", "large"]},
            },
            "additionalProperties": False,
        },
    }},
    "required": ["views"],
    "additionalProperties": False,
}

QUERY_SCHEMA = {
    "type": "object",
    "properties": {"query": {
        "type": "object",
        "description": (
            "kind is one of: summary; faces (optional surface_type, feature_id, normal [x, y, z], "
            "min_area_mm2, limit); face (face_id); edges (optional curve_type, feature_id, limit); "
            "distance (a, b: each a face id, edge id, feature id or [x, y, z]); "
            "section (axis x|y|z, at in mm)."),
        "properties": {
            "kind": {"enum": ["summary", "faces", "face", "edges", "distance", "section"]},
            "surface_type": {"type": "string"},
            "curve_type": {"type": "string"},
            "feature_id": {"type": "string"},
            "face_id": {"type": "string"},
            "normal": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3},
            "min_area_mm2": {"type": "number", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            "a": {"type": ["string", "array"]},
            "b": {"type": ["string", "array"]},
            "axis": {"enum": ["x", "y", "z"]},
            "at": {"type": "number"},
        },
        "required": ["kind"],
        "additionalProperties": False,
    }},
    "required": ["query"],
    "additionalProperties": False,
}

TOOLS = [
    {"name": "current_design", "description": "Read the current CAD source and request context.",
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "declare_requirements", "description": (
        "Declare what the part must measure before the first build: the overall size, the number "
        "of solids, one requirement per requested number, count or feature, and your assumptions. "
        "Every build is checked against this list. Call again to revise it."),
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
     "inputSchema": DECLARE_SCHEMA},
    {"name": "build_model", "description": (
        "Build complete build123d source in the CAD sandbox. Returns measured geometry, the "
        "acceptance table for the declared requirements, and two shaded views from opposite "
        "corners that together show every side. Review "
        "these and repair failures. Name each check_measurement with the requirement id it proves. "
        "A successful build alone does not establish design correctness."),
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
     "inputSchema": {"type": "object", "properties": {"code": {"type": "string", "maxLength": 100000}},
                     "required": ["code"], "additionalProperties": False}},
    {"name": "view_model", "description": (
        "Draw up to four more views of the current part to answer a specific question: a top "
        "view for a hole pattern, a section for a bore, pocket or wall, a focused or highlighted "
        "view of the changed feature. Images show arrangement only; measure dimensions with "
        "inspect_model. Does not use the build budget."),
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
     "inputSchema": VIEW_SCHEMA},
    {"name": "check_printability", "description": (
        "Check whether the current part prints with the user's print profile: bed fit, wall "
        "thickness, overhangs that need support, support volume, the best of six orientations, "
        "small holes and sealed cavities. Returns measured facts and findings with locations."),
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "inspect_model", "description": (
        "Ask about the current part (the last one that built, or the starting design), without "
        "rebuilding: its faces, one face and its "
        "edges, its edges, the distance between two faces, edges, features or points, or a "
        "plane section. Face ids are the ones the studio's selection uses. Does not use the "
        "build budget."),
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
     "inputSchema": QUERY_SCHEMA},
]


class CadTools:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.spent = dict.fromkeys(BUDGETS, 0)

    @property
    def builds(self):
        return self.spent["builds"]

    def left(self):
        return {name: BUDGETS[name] - used for name, used in self.spent.items()}

    def spend(self, kind, amount=1, message=None):
        if self.spent[kind] + amount > BUDGETS[kind]:
            raise ValueError(message or f"The {kind.replace('_', ' ')} budget of {BUDGETS[kind]} is used up.")
        self.spent[kind] += amount

    def progress(self, stage, status, message, attempt=None, glb=None):
        """One line for the studio's progress list, which the runner relays."""
        line = {"stage": stage, "status": status, "message": " ".join(str(message).split())[:480],
                "attempt": attempt}
        if glb:
            line["glb"] = glb
        with (self.workspace / "progress.jsonl").open("a") as handle:
            handle.write(json.dumps(line) + "\n")

    def reply(self, payload, started, extra=(), is_error=False):
        payload = {**payload, "budget_left": self.left(), "ms": round((perf_counter() - started) * 1000)}
        result = {"content": [{"type": "text", "text": json.dumps(payload, separators=(",", ":"))}, *extra]}
        if is_error:
            result["isError"] = True
        return result

    def call(self, name, arguments):
        if name == "current_design":
            return {"content": [{"type": "text", "text": (self.workspace / "context.txt").read_text()
                                 + "\nCurrent code:\n" + (self.workspace / "model.py").read_text()}]}
        handlers = {
            "declare_requirements": self.declare,
            "inspect_model": self.inspect,
            "view_model": self.view,
            "check_printability": lambda _arguments: self.printability(),
            "build_model": self.build,
        }
        if name not in handlers:
            raise ValueError("Unknown CAD tool.")
        return handlers[name](arguments)

    def starting_point(self):
        """The starting design's topology and inspection, for an edit."""
        cached = self.workspace / "previous.json"
        if cached.exists():
            return json.loads(cached.read_text()) or None
        start = self.workspace / "start.py"
        previous = None
        if start.exists() and start.read_text().strip():
            inspection, _, topology = review_code(start.read_text(), topology=True, draw=False)
            if inspection.valid and topology is not None:
                previous = {"topology": topology, "inspection": inspection.model_dump()}
        # Measured once per run; an empty object records "no usable start".
        cached.write_text(json.dumps(previous or {}))
        return previous

    def requirements(self):
        path = self.workspace / "requirements.json"
        return json.loads(path.read_text()) if path.exists() else None

    def built(self):
        built = self.workspace / "built.py"
        if not built.exists():
            raise ValueError("There is no part yet. Call build_model first.")
        return built.read_text()

    def declare(self, arguments):
        started = perf_counter()
        requirements = parse_requirements(arguments)
        self.spend("declarations", message="Requirements were already declared four times. Build with the current list.")
        (self.workspace / "requirements.json").write_text(json.dumps(requirements))
        count = len(requirements["requirements"])
        self.progress("requirements", "complete",
                      f"{count} requirement{'s' if count != 1 else ''}: {requirements['summary']}")
        request = self.workspace / "request.txt"
        missing = uncovered_numbers(request.read_text(), requirements) if request.exists() else []
        # The agent wrote the list; echoing it back would only cost tokens.
        result = {"declared": len(requirements["requirements"]),
                  "ids": [item["id"] for item in requirements["requirements"]]}
        if missing:
            result["warning"] = (
                "These numbers in the request appear in no requirement, bound or count: "
                + ", ".join(f"{value:g}" for value in missing)
                + ". Add a requirement for each one that is a dimension or a count."
            )
        return self.reply(result, started)

    def inspect(self, arguments):
        started = perf_counter()
        code = self.built()
        self.spend("questions", message="The 20-question budget is exhausted. Use the build results you have.")
        query = arguments.get("query")
        answer = query_code(code, query)
        self.progress("measure", "complete", _describe_answer(query, answer))
        return self.reply({"answer": answer}, started)

    def view(self, arguments):
        started = perf_counter()
        code = self.built()
        views = arguments.get("views")
        count = len(views) if isinstance(views, list) else 0
        self.spend("views", count, f"Only {BUDGETS['views'] - self.spent['views']} more views are left in this run.")
        rendered = render_code(code, views)
        self.progress("view", "complete", "Looked at " + ", ".join(view.name for view in rendered))
        return self.reply({"views": [view.name for view in rendered]}, started, _view_content(rendered))

    def printability(self):
        started = perf_counter()
        code = self.built()
        self.spend("print_checks", message="Printability was already checked three times in this run.")
        profile = self.workspace / "profile.json"
        report = printability_code(code, json.loads(profile.read_text()) if profile.exists() else None)
        (self.workspace / "printability.json").write_text(json.dumps(report))
        problems = [row["rule"].replace("_", " ") for row in report["findings"] if row["status"] in ("fail", "review")]
        self.progress("printability", "complete",
                      f"{len(problems)} to look at: {', '.join(problems)}" if problems else "No printing problems found")
        return self.reply(printability_view(report), started)

    def build(self, arguments):
        started = perf_counter()
        code = arguments.get("code")
        if not isinstance(code, str) or len(code.encode()) > 100000:
            raise ValueError("Supply at most 100 KB of CAD code.")
        requirements = self.requirements()
        if requirements is None:
            raise ValueError("Call declare_requirements first.")
        self.spend("builds", message="The eight-build budget is exhausted. Report remaining failures.")
        number = self.builds
        self.progress("build", "started", f"Build {number}", attempt=number)
        previous = self.starting_point()
        preview = self.workspace / f"build-{number}.glb"
        inspection, views, topology = review_code(code, topology=previous is not None, glb_to=preview)
        if previous is not None and topology is not None:
            inspection.changes = change_report(previous, topology, inspection.model_dump())
        if (self.workspace / "reference.json").exists() and inspection.valid:
            inspection.reference_comparison = compare_reference(inspection, json.loads((self.workspace / "reference.json").read_text()))
        inspection.acceptance = evaluate(requirements, inspection.model_dump(), code)
        (self.workspace / "model.py").write_text(code)
        if inspection.valid:
            # inspect_model answers about the last part that built.
            (self.workspace / "built.py").write_text(code)
        (self.workspace / "inspection.json").write_text(inspection.model_dump_json())
        failed = not inspection.valid or inspection.acceptance["verdict"] == "failed"
        self.progress("build", "failed" if failed else "complete",
                      _describe_build(number, inspection), attempt=number)
        if preview.exists():
            self.progress("snapshot", "ready", f"build {number}", glb=preview.name)
        return self.reply(agent_view(inspection.model_dump()), started, _view_content(views), failed)


def _describe_build(number, inspection):
    if not inspection.valid:
        return f"Build {number} failed: {(inspection.error or 'invalid geometry')[:200]}"
    acceptance = inspection.acceptance or {}
    measurable = sum(acceptance.get(key, 0) for key in ("passed", "failed", "unverified", "review"))
    text = f"Build {number}: {acceptance.get('passed', 0)} of {measurable} requirements pass"
    box = inspection.bounding_box_mm or {}
    if box:
        text += f", {box.get('x', 0):g} × {box.get('y', 0):g} × {box.get('z', 0):g} mm"
    if inspection.warnings:
        text += f", {len(inspection.warnings)} warning{'s' if len(inspection.warnings) != 1 else ''}"
    if (inspection.changes or {}).get("flags"):
        text += ", changes to review"
    return text


def _describe_answer(query, answer):
    kind = (query or {}).get("kind", "")
    if kind == "distance":
        return f"Distance: {answer.get('distance_mm', 0):.2f} mm"
    if kind == "section":
        return f"Section at {(query or {}).get('axis')} = {(query or {}).get('at')} mm: {answer.get('area_mm2', 0):g} mm²"
    if kind in ("faces", "edges"):
        filters = ", ".join(f"{key} {value}" for key, value in query.items() if key not in ("kind", "limit"))
        return f"Found {answer.get('count', 0)} {kind}" + (f" ({filters})" if filters else "")
    if kind == "face":
        radius = answer.get("radius_mm")
        return f"Looked up a {answer.get('surface_type', '')} face" + (f" of radius {radius:g} mm" if radius else "")
    return "Read the part's measurements"


def _view_content(views):
    content = []
    for view in views:
        if view.png:
            content.append({"type": "text", "text": f"View: {view.name}"})
            content.append({"type": "image", "mimeType": "image/png",
                            "data": base64.b64encode(view.png).decode("ascii")})
        else:
            content.append({"type": "text", "text": f"View {view.name} could not be drawn: {view.error}"})
    return content


def main():
    bridge = CadTools(Path(sys.argv[1]).resolve())
    for line in sys.stdin.buffer:
        request = None
        try:
            if len(line) > 1_000_000:
                raise ValueError("MCP message too large.")
            request = json.loads(line)
            if "id" not in request:
                continue
            method = request.get("method")
            if method == "initialize":
                result = {"protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"),
                          "capabilities": {"tools": {}}, "serverInfo": {"name": "nfinit", "version": "0.1.0"}}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = request["params"]
                try:
                    result = bridge.call(params["name"], params.get("arguments", {}))
                except Exception as error:
                    result = {"isError": True, "content": [{"type": "text", "text": str(error)[:2000]}]}
            elif method == "ping":
                result = {}
            else:
                raise ValueError("Unsupported MCP method.")
            response = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        except Exception as error:
            response = {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None,
                        "error": {"code": -32600, "message": str(error)[:300]}}
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
