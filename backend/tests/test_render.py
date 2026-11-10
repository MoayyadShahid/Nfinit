import io

import pytest
from PIL import Image

from execution import render_code, review_code
from execution.runner import validate_views

PLATE = (
    "with BuildPart() as part:\n"
    "    Box(80, 50, 6)\n"
    "    register_feature('plate', 'Plate', 'additive', part.part)\n"
    "    Hole(radius=10)\n"
    "    register_feature('bore', 'Bore', 'subtractive', part.part, parent_id='plate')\n"
    "result = part.part"
)
TUBE = "with BuildPart() as part:\n    Cylinder(20, 30)\n    Hole(radius=12)\nresult = part.part"


def image(view) -> Image.Image:
    assert view.png, view.error
    return Image.open(io.BytesIO(view.png)).convert("RGB")


def dark(pixel) -> bool:
    return sum(pixel) < 200


def test_review_builds_once_and_returns_two_views(monkeypatch):
    from execution import runner

    calls = []
    original = runner._run_worker
    monkeypatch.setattr(runner, "_run_worker", lambda *args, **kwargs: calls.append(args[1]) or original(*args, **kwargs))

    inspection, views, topology = review_code(PLATE)

    assert inspection.valid and topology is None
    assert calls == ["review"]
    assert [view.name for view in views] == ["iso shaded", "iso_back shaded"]
    assert all(image(view).size == (800, 600) for view in views)


def test_top_view_draws_the_bore_outline_where_it_is():
    (view,) = render_code(PLATE, [{"camera": "top", "mode": "hidden_line"}])
    picture = image(view)

    # The plate fills the width less the margins; find its scale from the
    # outline, then look for the bore's circle 10 mm from the centre.
    row = picture.height // 2 + 17
    columns = [x for x in range(picture.width) if dark(picture.getpixel((x, row)))]
    left, right = columns[0], columns[-1]
    scale = (right - left) / 80
    centre = (left + right) / 2
    radius = 10 * scale
    assert any(dark(picture.getpixel((round(centre + radius + offset), row))) for offset in (-1, 0, 1))
    assert not dark(picture.getpixel((round(centre), row)))


def test_section_shows_the_cut_faces_in_red():
    (view,) = render_code(TUBE, [{"camera": "front", "section": {"axis": "y", "at": 0, "keep": "above"}}])
    colours = image(view).getcolors(1_000_000)

    assert any(r > 150 and g < 110 and b < 110 for count, (r, g, b) in colours if count > 500)


def test_highlight_and_xray_and_a_failed_view():
    views = render_code(PLATE, [
        {"camera": "iso", "highlight": ["bore"]},
        {"camera": "iso", "mode": "xray", "size": "large"},
        {"focus": "missing_feature"},
    ])

    # The accent is orange at any shade: red well above green, green above blue.
    assert any(r > 60 and r > 1.6 * g and g > 1.8 * b for _, (r, g, b) in image(views[0]).getcolors(1_000_000))
    assert image(views[1]).size == (1200, 900)
    assert views[2].png is None and "missing_feature" in views[2].error


@pytest.mark.parametrize(
    "views",
    [
        [],
        [{}] * 5,
        [{"camera": "underneath"}],
        [{"camera": {"azimuth": 10}}],
        [{"mode": "wireframe"}],
        [{"section": {"axis": "q", "at": 0}}],
        [{"focus": [1, 2, 3]}],
        [{"highlight": ["x"] * 21}],
        [{"colour": "red"}],
    ],
)
def test_bad_views_are_refused(views):
    with pytest.raises(ValueError):
        validate_views(views)
