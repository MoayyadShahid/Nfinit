"""Small stdio MCP bridge for installed agents; all CAD runs in the sandbox.

No arbitrary paths, shell commands or network tools are exposed. This process
serves one temporary design workspace and is killed with its owning agent.
"""
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
from execution import inspect_code  # noqa: E402
from execution.references import compare_reference, model_views  # noqa: E402

MAX_BUILDS = 8
MAX_DECLARATIONS = 4

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
        "acceptance table for the declared requirements, and top/front/isometric images. Review "
        "these and repair failures. Name each check_measurement with the requirement id it proves. "
        "A successful build alone does not establish design correctness."),
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
     "inputSchema": {"type": "object", "properties": {"code": {"type": "string", "maxLength": 100000}},
                     "required": ["code"], "additionalProperties": False}},
]


class CadTools:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.builds = 0
        self.declarations = 0

    def call(self, name, arguments):
        if name == "current_design":
            return {"content": [{"type": "text", "text": (self.workspace / "context.txt").read_text()
                                 + "\nCurrent code:\n" + (self.workspace / "model.py").read_text()}]}
        if name == "declare_requirements":
            return self.declare(arguments)
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
        inspection = inspect_code(code)
        if (self.workspace / "reference.json").exists() and inspection.valid:
            inspection.reference_comparison = compare_reference(inspection, json.loads((self.workspace / "reference.json").read_text()))
        inspection.acceptance = evaluate(requirements, inspection.model_dump(), code)
        (self.workspace / "model.py").write_text(code)
        (self.workspace / "inspection.json").write_text(inspection.model_dump_json())
        content = [{"type": "text", "text": inspection.model_dump_json()}]
        if inspection.valid:
            try:
                for view in model_views(code):
                    content.append({"type": "image", "mimeType": "image/png", "data": view.split(",", 1)[1]})
            except Exception:
                content.append({"type": "text", "text": "Rendered views unavailable; visual verification remains incomplete."})
        failed = not inspection.valid or inspection.acceptance["verdict"] == "failed"
        return {"content": content, "isError": failed}


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
