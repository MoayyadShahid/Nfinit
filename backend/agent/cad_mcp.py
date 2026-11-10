"""Small stdio MCP bridge for installed agents; all CAD runs in the sandbox.

No arbitrary paths, shell commands or network tools are exposed. This process
serves one temporary design workspace and is killed with its owning agent.
"""
import base64
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.acceptance import (  # noqa: E402
    DECLARE_SCHEMA,
    evaluate,
    parse_requirements,
    uncovered_numbers,
)
from execution import printability_code, query_code, render_code, review_code  # noqa: E402
from execution.references import compare_reference  # noqa: E402

MAX_BUILDS = 8
MAX_DECLARATIONS = 4
MAX_QUERIES = 20
MAX_EXTRA_IMAGES = 12
MAX_PRINT_CHECKS = 3

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
        self.builds = 0
        self.declarations = 0
        self.queries = 0
        self.images = 0
        self.print_checks = 0

    def call(self, name, arguments):
        if name == "current_design":
            return {"content": [{"type": "text", "text": (self.workspace / "context.txt").read_text()
                                 + "\nCurrent code:\n" + (self.workspace / "model.py").read_text()}]}
        if name == "declare_requirements":
            return self.declare(arguments)
        if name == "inspect_model":
            return self.inspect(arguments)
        if name == "view_model":
            return self.view(arguments)
        if name == "check_printability":
            return self.printability()
        if name != "build_model":
            raise ValueError("Unknown CAD tool.")
        return self.build(arguments)

    def requirements(self):
        path = self.workspace / "requirements.json"
        return json.loads(path.read_text()) if path.exists() else None

    def declare(self, arguments):
        if self.declarations >= MAX_DECLARATIONS:
            raise ValueError("Requirements were already declared four times. Build with the current list.")
        requirements = parse_requirements(arguments)
        self.declarations += 1
        (self.workspace / "requirements.json").write_text(json.dumps(requirements))
        request = self.workspace / "request.txt"
        missing = uncovered_numbers(request.read_text(), requirements) if request.exists() else []
        result = {"declared": requirements}
        if missing:
            result["warning"] = (
                "These numbers in the request appear in no requirement, bound or count: "
                + ", ".join(f"{value:g}" for value in missing)
                + ". Add a requirement for each one that is a dimension or a count."
            )
        return {"content": [{"type": "text", "text": json.dumps(result)}]}

    def inspect(self, arguments):
        built = self.workspace / "built.py"
        if not built.exists():
            raise ValueError("There is no part yet. Call build_model first.")
        if self.queries >= MAX_QUERIES:
            raise ValueError("The 20-question budget is exhausted. Use the build results you have.")
        self.queries += 1
        answer = query_code(built.read_text(), arguments.get("query"))
        return {"content": [{"type": "text", "text": json.dumps(answer)}]}

    def view(self, arguments):
        built = self.workspace / "built.py"
        if not built.exists():
            raise ValueError("There is no part yet. Call build_model first.")
        views = arguments.get("views")
        count = len(views) if isinstance(views, list) else 0
        if self.images + count > MAX_EXTRA_IMAGES:
            raise ValueError(f"Only {MAX_EXTRA_IMAGES - self.images} more views are left in this run.")
        rendered = render_code(built.read_text(), views)
        self.images += count
        return {"content": _view_content(rendered)}

    def printability(self):
        built = self.workspace / "built.py"
        if not built.exists():
            raise ValueError("There is no part yet. Call build_model first.")
        if self.print_checks >= MAX_PRINT_CHECKS:
            raise ValueError("Printability was already checked three times in this run.")
        self.print_checks += 1
        profile = self.workspace / "profile.json"
        report = printability_code(
            built.read_text(), json.loads(profile.read_text()) if profile.exists() else None
        )
        return {"content": [{"type": "text", "text": json.dumps(report)}]}

    def build(self, arguments):
        code = arguments.get("code")
        if not isinstance(code, str) or len(code.encode()) > 100000:
            raise ValueError("Supply at most 100 KB of CAD code.")
        requirements = self.requirements()
        if requirements is None:
            raise ValueError("Call declare_requirements first.")
        if self.builds >= MAX_BUILDS:
            raise ValueError("The eight-build budget is exhausted. Report remaining failures.")
        self.builds += 1
        inspection, views = review_code(code)
        if (self.workspace / "reference.json").exists() and inspection.valid:
            inspection.reference_comparison = compare_reference(inspection, json.loads((self.workspace / "reference.json").read_text()))
        inspection.acceptance = evaluate(requirements, inspection.model_dump(), code)
        (self.workspace / "model.py").write_text(code)
        if inspection.valid:
            # inspect_model answers about the last part that built.
            (self.workspace / "built.py").write_text(code)
        (self.workspace / "inspection.json").write_text(inspection.model_dump_json())
        content = [{"type": "text", "text": inspection.model_dump_json()}, *_view_content(views)]
        failed = not inspection.valid or inspection.acceptance["verdict"] == "failed"
        return {"content": content, "isError": failed}


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
