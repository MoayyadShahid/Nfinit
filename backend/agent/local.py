"""Run the user's official CLI with a CAD MCP tool loop and bounded lifetime."""
import asyncio
import base64
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
from time import perf_counter

from .acceptance import describe as describe_acceptance, evaluate
from .graph import CadRunTimeoutError, _emit, run_timeout_seconds
from .local_access import LOCAL_MODELS, local_agents_enabled
from .prompts import local_agent_prompt


def agent_command(provider: str, workspace: Path, images: list[Path]) -> list[str]:
    executable = shutil.which(LOCAL_MODELS[provider][0])
    if not executable:
        raise ValueError(f"Install {LOCAL_MODELS[provider][1]} and sign in before connecting it.")
    bridge = str(Path(__file__).with_name("cad_mcp.py"))
    if provider == "local/claude":
        config = {"mcpServers": {"nfinit": {"command": sys.executable, "args": [bridge, str(workspace)]}}}
        return [executable, "-p", "--input-format", "stream-json", "--output-format", "stream-json",
                "--verbose", "--tools", "", "--strict-mcp-config", "--mcp-config", json.dumps(config),
                "--setting-sources", "", "--allowedTools", "mcp__nfinit__current_design",
                "mcp__nfinit__declare_requirements", "mcp__nfinit__build_model"]
    command = [executable, "exec", "--json", "--ephemeral", "--ignore-user-config",
               "--skip-git-repo-check", "--sandbox", "read-only", "-C", str(workspace),
               "-c", f"mcp_servers.nfinit.command={json.dumps(sys.executable)}",
               "-c", f"mcp_servers.nfinit.args={json.dumps([bridge, str(workspace)])}",
               "-c", "mcp_servers.nfinit.tool_timeout_sec=110",
               "-c", 'mcp_servers.nfinit.tools.current_design.approval_mode="approve"',
               "-c", 'mcp_servers.nfinit.tools.declare_requirements.approval_mode="approve"',
               "-c", 'mcp_servers.nfinit.tools.build_model.approval_mode="approve"']
    for image in images:
        command.extend(["--image", str(image)])
    return [*command, "-"]


def prepare_input(request, workspace: Path):
    text, images, blocks = [], [], []
    for message in request.messages:
        # Historical assistant messages contain entire superseded CAD scripts.
        # The current source is available through current_design instead.
        if message.role == "assistant":
            continue
        if isinstance(message.content, str):
            text.append(f"{message.role}: {message.content}")
        else:
            for part in message.content:
                if part.get("type") == "text":
                    text.append(f"{message.role}: {part['text']}")
                elif part.get("type") == "image_url":
                    url = part["image_url"]["url"]
                    header, encoded = url.split(",", 1)
                    mime = header[5:].split(";", 1)[0]
                    suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}[mime]
                    path = workspace / f"reference-{len(images)+1}{suffix}"
                    path.write_bytes(base64.b64decode(encoded, validate=True))
                    images.append(path)
                    text.append(f"Reference image {len(images)} accompanies this {message.role} message.")
                    blocks.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": encoded}})
    context = "\n".join(text)
    if request.mesh_reference:
        from execution.references import mesh_facts, parse_stl
        source = request.mesh_reference
        facts = mesh_facts(parse_stl(base64.b64decode(source.data, validate=True), 25.4 if source.units == "in" else 1.0))
        (workspace / "reference.json").write_text(json.dumps(facts))
        context += "\nMeasured STL reference (mm): " + json.dumps(facts)
    if request.selection:
        context += "\nSelected geometry: " + request.selection.model_dump_json()
    (workspace / "context.txt").write_text(context)
    # The latest request, for warning about numbers no requirement covers.
    latest = request.messages[-1].content
    (workspace / "request.txt").write_text(latest if isinstance(latest, str) else "\n".join(
        part.get("text", "") for part in latest if part.get("type") == "text"))
    (workspace / "model.py").write_text(request.code)
    prompt = local_agent_prompt(context)
    if request.model_id == "local/claude":
        return images, json.dumps({"type": "user", "message": {"role": "user", "content": [
            {"type": "text", "text": prompt}, *blocks]}}) + "\n"
    return images, prompt


async def run_local_agent(request, inspect_code, *, run_id, on_event=None):
    if not local_agents_enabled():
        raise ValueError("Local agents are disabled.")
    state = {"run_id": run_id, "code": request.code, "plan": "", "trace": [],
             "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0},
             "inspection": None, "validation_error": None, "repair_attempts": 0}
    started = perf_counter()
    await _emit(on_event, {"stage": "generate", "status": "started",
                          "message": f"Connected to your {LOCAL_MODELS[request.model_id][1]}. Building and checking locally."})
    with tempfile.TemporaryDirectory(prefix="nfinit-agent-") as directory:
        workspace = Path(directory)
        images, prompt = await asyncio.to_thread(prepare_input, request, workspace)
        command = agent_command(request.model_id, workspace, images)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("STRIPE_", "SUPABASE_", "LANGFUSE_", "PINECONE_", "NFNIT_", "OPENROUTER_"))}
        # CAD sandbox settings may be customized by the local owner.
        process = await asyncio.create_subprocess_exec(
            *command, cwd=workspace, env=env, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True, limit=2_000_000)
        try:
            async with asyncio.timeout(run_timeout_seconds()):
                process.stdin.write(prompt.encode())
                await process.stdin.drain()
                process.stdin.close()
                size = 0
                async for line in process.stdout:
                    size += len(line)
                    if size > 20_000_000:
                        raise ValueError("Local agent exceeded the output limit.")
                    try:
                        event = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    kind = event.get("type", "")
                    item = event.get("item", {})
                    if kind in {"result", "turn.completed"}:
                        usage = event.get("usage") or {}
                        input_tokens = sum(int(usage.get(key, 0) or 0) for key in (
                            "input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
                        output_tokens = int(usage.get("output_tokens", 0) or 0)
                        state["usage"].update(input_tokens=input_tokens, output_tokens=output_tokens,
                                              total_tokens=input_tokens+output_tokens)
                    if kind == "result":
                        if event.get("is_error"):
                            raise ValueError("Claude Code could not finish. Check its login and usage allowance in your terminal.")
                        state["plan"] = str(event.get("result", ""))[:8000]
                    if kind == "item.completed" and item.get("type") == "agent_message":
                        state["plan"] = str(item.get("text", ""))[:8000]
                    if kind in {"item.started", "item.completed", "assistant"}:
                        await _emit(on_event, {"stage": "generate", "status": "started",
                                              "message": "Agent is editing, measuring, and reviewing the design."})
                status = await process.wait()
                if status:
                    raise ValueError("The local agent exited unsuccessfully. Check its login, version, and usage allowance in your terminal.")
                if not (workspace / "inspection.json").exists():
                    raise ValueError("The agent did not build with the CAD tool. " +
                                     (state["plan"][:350] or "Check the installed CLI version and retry."))
                state["code"] = (workspace / "model.py").read_text()
                inspection = await asyncio.to_thread(inspect_code, state["code"])
                if inspection.valid and (workspace / "reference.json").exists():
                    from execution.references import compare_reference
                    inspection.reference_comparison = compare_reference(inspection, json.loads((workspace / "reference.json").read_text()))
                # The backend's own rebuild decides the verdict, not the agent's last tool result.
                detail = "Final geometry checked in the CAD sandbox. "
                if (workspace / "requirements.json").exists():
                    inspection.acceptance = evaluate(
                        json.loads((workspace / "requirements.json").read_text()),
                        inspection.model_dump(), state["code"])
                    detail += describe_acceptance(inspection.acceptance)
                else:
                    detail += (f"{len(inspection.checks)} measurement checks." if inspection.checks
                               else "Design requirements remain unverified.")
                state["inspection"] = inspection.model_dump()
                state["validation_error"] = inspection.error if not inspection.valid else None
                failed = not inspection.valid or (inspection.acceptance or {}).get("verdict") == "failed"
                state["trace"] = [{"node": "inspect", "status": "failed" if failed else "passed",
                                   "detail": detail, "duration_ms": round((perf_counter()-started)*1000)}]
                await _emit(on_event, {"stage": "inspect", "status": state["trace"][0]["status"],
                                      "message": state["trace"][0]["detail"]})
                return state
        except TimeoutError as error:
            raise CadRunTimeoutError(run_timeout_seconds(), state) from error
        finally:
            # Include MCP children, including after the parent exits normally.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(process.wait(), 3)
            except TimeoutError:
                os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
