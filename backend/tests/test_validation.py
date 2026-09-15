import pytest

from agent.validation import extract_code, validate_code


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("", "empty"),
        ("import os\nresult = Box(1, 1, 1)", "Import"),
        ("result = eval('1')", "eval"),
        ("Box(1, 1, 1)", "must assign"),
    ],
)
def test_validate_code_rejects_invalid_input(code: str, expected: str):
    assert expected in (validate_code(code) or "")


def test_validate_code_accepts_build123d_result():
    code = "with BuildPart() as part:\n    Box(10, 10, 10)\nresult = part.part"
    assert validate_code(code) is None


def test_extract_code_supports_structured_and_fenced_responses():
    assert extract_code('{"code":"result = Box(1, 2, 3)"}', True) == (
        "result = Box(1, 2, 3)"
    )
    assert extract_code("```python\nresult = Box(3, 2, 1)\n```", False) == (
        "result = Box(3, 2, 1)"
    )
