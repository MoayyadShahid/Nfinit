"""Small stdio MCP bridge for installed agents; all CAD runs in the sandbox.

No arbitrary paths, shell commands or network tools are exposed. This process
serves one temporary design workspace and is killed with its owning agent.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from execution import inspect_code  # noqa: E402
from execution.references import compare_reference, model_views  # noqa: E402

TOOLS = [
    {"name": "current_design", "description": "Read the current CAD source and request context.",
     "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "build_model", "description": (
        "Build complete build123d source in the CAD sandbox. Returns measured geometry, "
        "acceptance checks, and top/front/isometric images. Review these and repair failures. "
        "Use check_measurement on actual geometry. A successful build alone does not establish design correctness."),
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
     "inputSchema": {"type": "object", "properties": {"code": {"type": "string", "maxLength": 100000}},
                     "required": ["code"], "additionalProperties": False}},
]


class CadTools:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.builds = 0

    def call(self, name, arguments):
        if name == "current_design":
            return {"content": [{"type": "text", "text": (self.workspace / "context.txt").read_text()
                                 + "\nCurrent code:\n" + (self.workspace / "model.py").read_text()}]}
        if name != "build_model":
            raise ValueError("Unknown CAD tool.")
        code = arguments.get("code")
        if not isinstance(code, str) or len(code.encode()) > 100000:
            raise ValueError("Supply at most 100 KB of CAD code.")
        if self.builds >= 8:
            raise ValueError("The eight-build budget is exhausted. Report remaining failures.")
        self.builds += 1
        inspection = inspect_code(code)
        if (self.workspace / "reference.json").exists() and inspection.valid:
            inspection.reference_comparison = compare_reference(inspection, json.loads((self.workspace / "reference.json").read_text()))
        (self.workspace / "model.py").write_text(code)
        (self.workspace / "inspection.json").write_text(inspection.model_dump_json())
        # The census is for scoring until the agent's prompt explains it.
        content = [{"type": "text", "text": inspection.model_dump_json(exclude={"census"})}]
        if inspection.valid:
            try:
                for view in model_views(code):
                    content.append({"type": "image", "mimeType": "image/png", "data": view.split(",", 1)[1]})
            except Exception:
                content.append({"type": "text", "text": "Rendered views unavailable; visual verification remains incomplete."})
        return {"content": content, "isError": not inspection.valid}


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
