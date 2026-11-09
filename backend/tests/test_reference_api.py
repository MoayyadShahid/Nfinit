import base64
import struct
import time

from fastapi.testclient import TestClient

import main
from agent import local
from agent.models import CadRunRequest, ModelInspection
from projects import runs
from projects.store import ProjectStore, get_project_store


def tetra_stl():
    a, b, c, d = (0, 0, 0), (10, 0, 0), (0, 10, 0), (0, 0, 10)
    return b"tetra".ljust(80, b" ") + struct.pack("<I", 4) + b"".join(
        struct.pack("<12fH", 0, 0, 0, *(v for p in tri for v in p), 0)
        for tri in [[a, c, b], [a, b, d], [a, d, c], [b, c, d]])


def test_import_original_survives_new_revision(tmp_path):
    store = ProjectStore(tmp_path / "projects.db")
    main.app.dependency_overrides[get_project_store] = lambda: store
    try:
        with TestClient(main.app) as client:
            original = base64.b64encode(tetra_stl()).decode()
            response = client.post("/import-stl", json={"data": original, "units": "mm", "mode": "preserve"})
            assert response.status_code == 200, response.text
            imported = response.json()
            assert imported["inspection"]["valid"]
            assert len(imported["views"]) == 3
            source = {"name": "part.stl", "data": original, "units": "mm", "mode": "preserve", "facts": imported["facts"]}
            state = {"code": imported["code"], "meshReference": source}
            project = client.post("/projects", json={"name": "Imported part", "state": state}).json()
            state["code"] += "\nresult = source_mesh - Pos(1, 1, 0) * Cylinder(0.3, 30)\n"
            revised = client.post(f"/projects/{project['id']}/revisions", json={"state": state})
            assert revised.status_code == 201, revised.text
            first = client.get(f"/projects/{project['id']}/revisions/1").json()
            assert first["state"]["code"] == imported["code"]
            assert first["state"]["meshReference"]["data"] == original
            assert revised.json()["state"]["meshReference"]["data"] == original
    finally:
        main.app.dependency_overrides.clear()


def test_local_run_uses_agent_without_openrouter_key(tmp_path, monkeypatch):
    for name, value in {"NFNIT_LOCAL_AGENTS": "true", "NFNIT_LOCAL_TOKEN": "a"*40,
                        "NFNIT_ALLOW_LOCAL_AUTH_BYPASS": "true", "OPENROUTER_API_KEY": ""}.items():
        monkeypatch.setenv(name, value)
    store = ProjectStore(tmp_path / "projects.db")
    main.app.dependency_overrides[get_project_store] = lambda: store
    monkeypatch.setattr(runs, "store_mesh_for_code", lambda *args, **kwargs: None)
    called = []
    async def fake_agent(request: CadRunRequest, _inspector, **kwargs):
        called.append(request.model_id)
        return {"code": "result = Box(10, 10, 10)", "plan": "Built a cube", "trace": [], "usage": {},
                "inspection": ModelInspection(valid=True).model_dump(), "validation_error": None}
    monkeypatch.setattr(local, "run_local_agent", fake_agent)
    payload = {"modelId": "local/codex", "messages": [{"role": "user", "content": "Make a cube"}]}
    try:
        with TestClient(main.app) as client:
            assert client.post("/cad/runs", json=payload).status_code == 403
            response = client.post("/cad/runs", json=payload, headers={"x-nfinit-local-token": "a"*40})
            assert response.status_code == 202, response.text
            for _ in range(100):
                run = client.get("/cad/runs/" + response.json()["runId"]).json()
                if run["status"] != "running":
                    break
                time.sleep(.01)
            assert run["status"] == "succeeded", run
            assert called == ["local/codex"]
    finally:
        main.app.dependency_overrides.clear()
