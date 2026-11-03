"""Measurable results that the plan promises, and the check against them.

The planner ends its plan with a fenced ``expectations`` block, for example::

    ```expectations
    {"bounding_box_mm": {"x": 80, "y": 50, "z": 20},
     "solid_count": 1,
     "assumptions": ["The walls rise 18 mm above the 2 mm base."]}
    ```

The block is removed from the plan that the user sees. Its values let the
inspect step find a part that builds but has the wrong size, which an
execution check alone cannot find.
"""

import json
import math
import re
from typing import Any, TypedDict

AXES = ("x", "y", "z")
# The CAD50 benchmark uses 0.1 mm. A small relative term keeps large parts
# from failing on kernel rounding.
ABSOLUTE_TOLERANCE_MM = 0.1
RELATIVE_TOLERANCE = 0.001
MAX_ASSUMPTIONS = 3
MAX_ASSUMPTION_LENGTH = 240

_BLOCK = re.compile(r"```expectations[ \t]*\n([\s\S]*?)```", re.IGNORECASE)


class PlanExpectations(TypedDict):
    bounding_box_mm: dict[str, float]
    solid_count: int | None
    assumptions: list[str]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number > 0 else None


def _parse(block: str) -> PlanExpectations | None:
    try:
        value = json.loads(block)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None

    bounds: dict[str, float] = {}
    raw_bounds = value.get("bounding_box_mm")
    if isinstance(raw_bounds, dict):
        for axis in AXES:
            number = _number(raw_bounds.get(axis))
            if number is not None:
                bounds[axis] = number

    solid_count = value.get("solid_count")
    if isinstance(solid_count, bool) or not isinstance(solid_count, int) or solid_count < 1:
        solid_count = None

    assumptions = [
        " ".join(item.split())[:MAX_ASSUMPTION_LENGTH]
        for item in value.get("assumptions") or []
        if isinstance(item, str) and item.strip()
    ][:MAX_ASSUMPTIONS]

    if not bounds and solid_count is None and not assumptions:
        return None
    return {
        "bounding_box_mm": bounds,
        "solid_count": solid_count,
        "assumptions": assumptions,
    }


def split_plan(raw: str) -> tuple[str, PlanExpectations | None]:
    """Return the plan for people and the expectations it declares.

    The last valid block wins. When the plan states assumptions, they become
    its first line, so the chat summary shows how the request was read.
    """
    expectations = None
    for match in _BLOCK.finditer(raw):
        expectations = _parse(match.group(1)) or expectations
    plan = _BLOCK.sub("", raw).strip()
    if expectations and expectations["assumptions"]:
        assumed = "Assumed: " + " ".join(
            item if item.endswith((".", "!", "?")) else item + "."
            for item in expectations["assumptions"]
        )
        plan = f"{assumed}\n\n{plan}" if plan else assumed
    return plan, expectations


def describe(expectations: PlanExpectations) -> str:
    """One line for the code model that names what the check will measure."""
    parts = []
    bounds = expectations["bounding_box_mm"]
    if bounds:
        parts.append(
            "overall bounds "
            + ", ".join(f"{axis.upper()} {bounds[axis]:g} mm" for axis in AXES if axis in bounds)
        )
    if expectations["solid_count"] is not None:
        count = expectations["solid_count"]
        parts.append(f"{count} solid{'s' if count != 1 else ''}")
    return "; ".join(parts)


def _tolerance(target: float) -> float:
    return max(ABSOLUTE_TOLERANCE_MM, target * RELATIVE_TOLERANCE)


def check_geometry(
    expectations: PlanExpectations | None, inspection: dict[str, Any]
) -> str | None:
    """Describe how a part that built differs from the plan, or return None."""
    if not expectations or not inspection.get("valid"):
        return None

    problems = []
    expected_count = expectations["solid_count"]
    actual_count = inspection.get("solid_count")
    if expected_count is not None and actual_count is not None and actual_count != expected_count:
        problems.append(
            f"it has {actual_count} solids, but the plan expects {expected_count}"
        )

    measured = inspection.get("bounding_box_mm") or {}
    for axis, target in expectations["bounding_box_mm"].items():
        value = measured.get(axis)
        if not isinstance(value, (int, float)):
            continue
        difference = value - target
        if abs(difference) > _tolerance(target):
            direction = "too long" if difference > 0 else "too short"
            problems.append(
                f"{axis.upper()} is {value:g} mm, but the plan expects {target:g} mm "
                f"({abs(difference):g} mm {direction})"
            )

    if not problems:
        return None
    return (
        "The part built, but its geometry does not match the plan: "
        + "; ".join(problems)
        + ". Change the code so the part matches the dimensions in the plan."
    )
