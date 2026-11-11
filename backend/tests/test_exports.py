import re
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from execution import export_code, printability_code
from execution.runner import PRINTER_PRESETS, SandboxArtifact, validate_profile

TEE = (
    "with BuildPart() as part:\n"
    "    Box(10, 10, 30, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
    "    with Locations((0, 0, 30)):\n"
    "        Box(60, 10, 5, align=(Align.CENTER, Align.CENTER, Align.MIN))\n"
    "result = part.part"
)


def exported(fmt: str, print_ready: bool = False) -> bytes:
    artifact = export_code(TEE, fmt, print_ready=print_ready)
    try:
        return artifact.path.read_bytes()
    finally:
        artifact.cleanup()


def obj_vertices(data: bytes):
    return [tuple(float(value) for value in line.split()[1:]) for line in data.decode().splitlines()
            if line.startswith("v ")]


def test_3mf_is_a_package_with_a_model():
    with zipfile.ZipFile(BytesIO(exported("3mf"))) as package:
        names = package.namelist()
    assert any(name.endswith(".model") for name in names)


def test_obj_keeps_the_model_where_it_was():
    vertices = obj_vertices(exported("obj"))
    assert min(z for _, _, z in vertices) == pytest.approx(0)
    assert max(z for _, _, z in vertices) == pytest.approx(35)


def test_print_ready_lays_the_part_flat_on_the_bed():
    vertices = obj_vertices(exported("obj", print_ready=True))
    xs = [x for x, _, _ in vertices]
    zs = [z for _, _, z in vertices]

    # The T stands 35 mm tall with its arms overhanging; on its side it is
    # 10 mm tall with no overhang, centred on the bed.
    assert min(zs) == pytest.approx(0)
    assert max(zs) == pytest.approx(10)
    assert min(xs) == pytest.approx(-max(xs))


def test_export_endpoint_takes_new_formats_and_print_ready(monkeypatch, tmp_path):
    calls = []

    def fake_export(code, operation, print_ready=False):
        calls.append((operation, print_ready))
        path = tmp_path / f"model.{operation}"
        path.write_bytes(b"data")
        return SandboxArtifact(path=path, temp_dir=tmp_path / "unused")

    monkeypatch.setattr(main, "export_code", fake_export)
    client = TestClient(main.app)
    ok = client.post("/export-model", json={"code": "result = Box(1, 1, 1)", "format": "3mf", "printReady": True})
    refused = client.post("/export-model", json={"code": "result = Box(1, 1, 1)", "format": "dwg"})

    assert ok.status_code == 200 and ok.headers["content-type"] == "model/3mf"
    assert calls == [("3mf", True)]
    assert refused.status_code == 400


def test_printer_presets_set_the_bed_and_name():
    profile = validate_profile({"printer": "flashforge_adventurer_3"})

    assert profile["bed_mm"] == [150.0, 150.0, 150.0]
    assert profile["printer_name"] == "Flashforge Adventurer 3"
    with pytest.raises(ValueError, match="printer"):
        validate_profile({"printer": "makerbot_9000"})


def test_a_part_too_big_for_the_printer_names_it():
    report = printability_code("result = Box(200, 20, 20)", {"printer": "flashforge_adventurer_3"})
    bed = next(row for row in report["findings"] if row["rule"] == "bed_fit")

    assert bed["status"] == "fail"
    assert "150 × 150 × 150 mm build volume of Flashforge Adventurer 3" in bed["suggestion"]


def test_studio_printer_list_matches_the_presets():
    source = (Path(__file__).parents[2] / "frontend/src/lib/printers.ts").read_text()
    studio = re.findall(r'id: "([a-z0-9_]+)", label: "([^"]+)"', source)

    assert dict(studio) == {key: name for key, (name, _) in PRINTER_PRESETS.items()}


def test_measure_endpoint_answers_faces_and_distances_only():
    client = TestClient(main.app)
    code = "with BuildPart() as part:\n    Box(40, 40, 6)\n    Hole(radius=5)\nresult = part.part"
    faces = client.post("/measure-model", json={"code": code, "query": {"kind": "summary"}})
    assert faces.status_code == 400

    from execution import query_code
    hole = next(face for face in query_code(code, {"kind": "faces", "surface_type": "cylinder"})["faces"])
    answer = client.post("/measure-model", json={"code": code, "query": {"kind": "face", "face_id": hole["id"]}})
    assert answer.status_code == 200
    assert answer.json()["radius_mm"] == pytest.approx(5)

    unknown = client.post("/measure-model", json={"code": code, "query": {"kind": "face", "face_id": "face_0123456789abcdef0123"}})
    assert unknown.status_code == 400
