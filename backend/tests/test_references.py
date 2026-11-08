import base64
import struct
import zlib

import pytest

from execution.references import faceted_code, mesh_facts, parse_stl, render_views
from execution import export_code, inspect_code


def tetrahedron():
    a, b, c, d = (0, 0, 0), (10, 0, 0), (0, 10, 0), (0, 0, 10)
    return [[a, c, b], [a, b, d], [a, d, c], [b, c, d]]


def binary_stl(triangles):
    return b"test".ljust(80, b" ") + struct.pack("<I", len(triangles)) + b"".join(
        struct.pack("<12fH", 0, 0, 0, *(v for p in tri for v in p), 0) for tri in triangles)


def test_binary_and_ascii_stl_units():
    triangles = tetrahedron()
    binary = parse_stl(binary_stl(triangles), 25.4)
    ascii_stl = "solid part\n" + "\n".join(
        "facet normal 0 0 0\nouter loop\n" + "\n".join("vertex " + " ".join(map(str, p)) for p in tri)
        + "\nendloop\nendfacet" for tri in triangles) + "\nendsolid part"
    assert parse_stl(ascii_stl.encode()) == triangles
    facts = mesh_facts(binary)
    assert facts["closed"] and facts["oriented"]
    assert facts["bounds"] == {"x": 254, "y": 254, "z": 254}


@pytest.mark.parametrize("data", [b"", b"not an stl", b"solid x\nvertex nan 1 2\nendsolid", binary_stl([[(0,0,0)]*3])])
def test_rejects_malformed_mesh(data):
    with pytest.raises(ValueError):
        parse_stl(data)


def test_open_mesh_is_reference_only():
    triangles = tetrahedron()[:3]
    assert not mesh_facts(triangles)["closed"]
    with pytest.raises(ValueError, match="closed"):
        faceted_code(triangles)
    assert len(render_views(triangles)) == 3


def test_faceted_import_can_be_edited_and_exported():
    code = faceted_code(tetrahedron())
    imported = inspect_code(code)
    assert imported.valid, imported.error
    assert imported.volume_mm3 == pytest.approx(1000/6, abs=.01)
    edited = code + "\nresult = source_mesh - Pos(1, 1, 0) * Cylinder(0.3, 30)\n"
    inspection = inspect_code(edited)
    assert inspection.valid, inspection.error
    assert inspection.volume_mm3 < imported.volume_mm3
    artifact = export_code(edited, "stl")
    try:
        assert parse_stl(artifact.path.read_bytes())
    finally:
        artifact.cleanup()


def test_mesh_decoder_rejects_decompression_bomb():
    payload = base64.b64encode(zlib.compress(b"0" * 200000)).decode()
    inspection = inspect_code(f"result = mesh_solid([{payload!r}])")
    assert not inspection.valid


def test_inward_oriented_mesh_becomes_positive_volume_solid():
    inspection = inspect_code(faceted_code([list(reversed(tri)) for tri in tetrahedron()]))
    assert inspection.valid, inspection.error
    assert inspection.volume_mm3 > 0


def test_geometry_measurement_failure_prevents_success():
    result = inspect_code("result = Box(10, 20, 30)\ncheck_measurement('width', result.bounding_box().size.X, 12, 0.01)")
    assert not result.valid
    assert result.verification == "failed"
    assert result.checks[0]["actual"] == 10
    assert "width" in result.error


def test_geometry_measurement_pass_is_recorded():
    result = inspect_code("result = Box(10, 20, 30)\ncheck_measurement('width', result.bounding_box().size.X, 10)")
    assert result.valid, result.error
    assert result.verification == "measured"


def test_unmeasured_shape_is_explicitly_unverified():
    result = inspect_code("result = Box(10, 20, 30)")
    assert result.valid
    assert result.verification == "unverified"
