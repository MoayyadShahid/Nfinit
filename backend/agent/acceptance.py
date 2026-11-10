"""Requirements a local agent declares before building, and each build's check.

The agent calls ``declare_requirements`` before its first build: the overall
size, the solid count, one row per requested number or feature, and its
assumptions. Every build is then checked against that list by the backend,
not by the agent. A requirement passes only through a ``check_measurement``
named with its id that measures built geometry; a check that compares an
input with itself is rejected.
"""

import ast
import math
import re
from typing import Any, Literal, TypedDict

from .expectations import check_geometry

MAX_REQUIREMENTS = 32
MAX_ASSUMPTIONS = 5
MAX_TEXT = 200
MAX_SUMMARY = 300
REQUIREMENT_ID = re.compile(r"[a-z][a-z0-9_]{0,63}")
KINDS = ("dimension", "count", "feature", "relation", "visual")
UNITS = ("mm", "deg", "count", "mm2", "mm3")
AXES = ("x", "y", "z")

Status = Literal["passed", "failed", "review", "unverified", "not_measurable"]


class Requirement(TypedDict):
    id: str
    text: str
    kind: Literal["dimension", "count", "feature", "relation", "visual"]
    expected: float | None
    unit: str | None
    tolerance: float | None
    source: Literal["user", "assumed"]


class RequirementSet(TypedDict):
    summary: str
    bounding_box_mm: dict[str, float]
    solid_count: int | None
    requirements: list[Requirement]
    assumptions: list[str]


# The MCP input schema of declare_requirements. parse_requirements enforces
# the same rules, since a client may not validate against it.
DECLARE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "maxLength": MAX_SUMMARY,
                    "description": "One sentence giving the part's overall size."},
        "bounding_box_mm": {
            "type": "object",
            "properties": {axis: {"type": ["number", "null"]} for axis in AXES},
            "additionalProperties": False,
            "description": "Overall size; null for an axis the request leaves free.",
        },
        "solid_count": {"type": ["integer", "null"], "minimum": 1},
        "requirements": {
            "type": "array",
            "maxItems": MAX_REQUIREMENTS,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"},
                    "text": {"type": "string", "maxLength": MAX_TEXT},
                    "kind": {"enum": list(KINDS)},
                    "expected": {"type": ["number", "null"]},
                    "unit": {"enum": [*UNITS, None]},
                    "tolerance": {"type": ["number", "null"], "minimum": 0},
                    "source": {"enum": ["user", "assumed"]},
                },
                "required": ["id", "text", "kind"],
                "additionalProperties": False,
            },
        },
        "assumptions": {
            "type": "array",
            "maxItems": MAX_ASSUMPTIONS,
            "items": {"type": "string", "maxLength": 240},
        },
    },
    "required": ["summary", "requirements"],
    "additionalProperties": False,
}


def _finite(value: Any, name: str, positive: bool = False) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number or null.")
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0):
        raise ValueError(f"{name} must be a finite{' positive' if positive else ''} number.")
    return number


def _tolerance(value: Any, name: str) -> float | None:
    number = _finite(value, name)
    if number is not None and number < 0:
        raise ValueError(f"{name} must not be negative.")
    return number


def _text(value: Any, name: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    return " ".join(value.split())[:limit]


def parse_requirements(arguments: Any) -> RequirementSet:
    """Validate declare_requirements' arguments; raise ValueError when invalid."""
    if not isinstance(arguments, dict):
        raise ValueError("Arguments must be an object.")
    unknown = set(arguments) - set(DECLARE_SCHEMA["properties"])
    if unknown:
        raise ValueError(f"Unknown fields: {', '.join(sorted(unknown))}.")

    bounds = {}
    raw_bounds = arguments.get("bounding_box_mm") or {}
    if not isinstance(raw_bounds, dict) or set(raw_bounds) - set(AXES):
        raise ValueError("bounding_box_mm may only have x, y and z.")
    for axis in AXES:
        number = _finite(raw_bounds.get(axis), f"bounding_box_mm.{axis}", positive=True)
        if number is not None:
            bounds[axis] = number

    solid_count = arguments.get("solid_count")
    if solid_count is not None and (
        isinstance(solid_count, bool) or not isinstance(solid_count, int) or solid_count < 1
    ):
        raise ValueError("solid_count must be a positive integer or null.")

    raw_requirements = arguments.get("requirements")
    if not isinstance(raw_requirements, list) or len(raw_requirements) > MAX_REQUIREMENTS:
        raise ValueError(f"requirements must be a list of at most {MAX_REQUIREMENTS}.")
    requirements: list[Requirement] = []
    for index, raw in enumerate(raw_requirements):
        label = f"requirements[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{label} must be an object.")
        extra = set(raw) - set(DECLARE_SCHEMA["properties"]["requirements"]["items"]["properties"])
        if extra:
            raise ValueError(f"{label} has unknown fields: {', '.join(sorted(extra))}.")
        requirement_id = raw.get("id")
        if not isinstance(requirement_id, str) or not REQUIREMENT_ID.fullmatch(requirement_id):
            raise ValueError(f"{label}.id must be lowercase letters, digits and underscores.")
        if any(item["id"] == requirement_id for item in requirements):
            raise ValueError(f"Requirement id '{requirement_id}' is repeated.")
        if raw.get("kind") not in KINDS:
            raise ValueError(f"{label}.kind must be one of {', '.join(KINDS)}.")
        unit = raw.get("unit")
        if unit is not None and unit not in UNITS:
            raise ValueError(f"{label}.unit must be one of {', '.join(UNITS)} or null.")
        source = raw.get("source", "user")
        if source not in ("user", "assumed"):
            raise ValueError(f"{label}.source must be user or assumed.")
        requirements.append({
            "id": requirement_id,
            "text": _text(raw.get("text"), f"{label}.text", MAX_TEXT),
            "kind": raw["kind"],
            "expected": _finite(raw.get("expected"), f"{label}.expected"),
            "unit": unit,
            "tolerance": _tolerance(raw.get("tolerance"), f"{label}.tolerance"),
            "source": source,
        })

    assumptions = arguments.get("assumptions") or []
    if not isinstance(assumptions, list) or len(assumptions) > MAX_ASSUMPTIONS:
        raise ValueError(f"assumptions must be a list of at most {MAX_ASSUMPTIONS}.")
    return {
        "summary": _text(arguments.get("summary"), "summary", MAX_SUMMARY),
        "bounding_box_mm": bounds,
        "solid_count": solid_count,
        "requirements": requirements,
        "assumptions": [_text(item, "assumptions", 240) for item in assumptions],
    }


# "80x50" gives 80 and 50; "M4" gives nothing: a thread size is not a number.
_NUMBER = re.compile(r"(?<![\d.A-WYZa-wyz_])\d+(?:\.\d+)?")


def stated_numbers(text: str) -> list[float]:
    """Every number written with digits in the text, in order."""
    return [float(match) for match in _NUMBER.findall(text)]


def uncovered_numbers(text: str, requirements: RequirementSet) -> list[float]:
    """Numbers in the request that no requirement, bound or count mentions.

    Some numbers are not dimensions, so this is a warning, not an error.
    """
    covered = set(requirements["bounding_box_mm"].values())
    if requirements["solid_count"] is not None:
        covered.add(float(requirements["solid_count"]))
    for requirement in requirements["requirements"]:
        if requirement["expected"] is not None:
            covered.add(requirement["expected"])
        covered.update(stated_numbers(requirement["text"]))
    missing = []
    for number in stated_numbers(text):
        if not any(abs(number - value) <= 1e-9 for value in covered) and number not in missing:
            missing.append(number)
    return missing


def _constant_names(tree: ast.AST) -> set[str]:
    """Names assigned only from literals, arithmetic and other such names."""
    assignments: dict[str, list[ast.AST]] = {}
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = [(target, node.value) for target in node.targets]
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)) and node.value is not None:
            targets = [(node.target, node.value)]
        elif isinstance(node, (ast.For, ast.comprehension, ast.withitem)):
            target = getattr(node, "target", None) or getattr(node, "optional_vars", None)
            for name in ast.walk(target) if target is not None else ():
                if isinstance(name, ast.Name):
                    # Loop and with targets come from objects; never constant.
                    assignments.setdefault(name.id, []).append(ast.Call(func=name, args=[], keywords=[]))
            continue
        for target, value in targets:
            if isinstance(target, ast.Name):
                assignments.setdefault(target.id, []).append(value)
            elif isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)) \
                    and len(target.elts) == len(value.elts):
                for element, element_value in zip(target.elts, value.elts):
                    if isinstance(element, ast.Name):
                        assignments.setdefault(element.id, []).append(element_value)
            else:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        assignments.setdefault(name.id, []).append(ast.Call(func=name, args=[], keywords=[]))

    constant: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, values in assignments.items():
            if name not in constant and all(_is_constant(value, constant) for value in values):
                constant.add(name)
                changed = True
    return constant


def _is_constant(node: ast.AST, constant: set[str]) -> bool:
    for child in ast.walk(node):
        if isinstance(child, (ast.Call, ast.Attribute, ast.Subscript)):
            return False
        if isinstance(child, ast.Name) and child.id not in constant:
            return False
    return True


def self_checks(code: str) -> list[str]:
    """Names of check_measurement calls whose `actual` measures nothing built."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    constant = _constant_names(tree)
    names = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "check_measurement"):
            continue
        arguments = {keyword.arg: keyword.value for keyword in node.keywords}
        name = node.args[0] if node.args else arguments.get("name")
        actual = node.args[1] if len(node.args) > 1 else arguments.get("actual")
        if actual is not None and _is_constant(actual, constant):
            label = name.value if isinstance(name, ast.Constant) and isinstance(name.value, str) else "unnamed"
            names.append(label)
    return names


class AcceptanceRow(TypedDict):
    id: str
    text: str
    status: Status
    expected: Any
    measured: Any
    source: str
    detail: str


def _row(row_id, text, status, expected=None, measured=None, source="user", detail=""):
    return {"id": row_id, "text": text, "status": status, "expected": expected,
            "measured": measured, "source": source, "detail": detail}


def evaluate(requirements: RequirementSet, inspection: dict[str, Any], code: str = "") -> dict[str, Any]:
    """Each requirement's status for one build, and the verdict."""
    rows = []
    valid = bool(inspection.get("valid"))
    bounds = requirements["bounding_box_mm"]
    if bounds:
        problem = check_geometry(
            {"bounding_box_mm": bounds, "solid_count": None, "assumptions": []}, inspection
        )
        rows.append(_row(
            "overall_size", "Overall size", "failed" if problem or not valid else "passed",
            bounds, inspection.get("bounding_box_mm"), detail=problem or "",
        ))
    if requirements["solid_count"] is not None:
        expected = requirements["solid_count"]
        measured = inspection.get("solid_count")
        rows.append(_row(
            "solid_count", "Number of solids",
            "passed" if valid and measured == expected else "failed", expected, measured,
        ))

    rejected = set(self_checks(code))
    checks = {check["name"]: check for check in inspection.get("checks") or []}
    for requirement in requirements["requirements"]:
        check = checks.get(requirement["id"])
        common = {"expected": requirement["expected"], "source": requirement["source"]}
        if requirement["kind"] == "visual":
            rows.append(_row(requirement["id"], requirement["text"], "not_measurable", **common,
                             detail="Judged from images; no measurement."))
        elif check is None:
            rows.append(_row(requirement["id"], requirement["text"], "unverified", **common,
                             detail=f"No check_measurement named '{requirement['id']}'."))
        elif requirement["id"] in rejected:
            rows.append(_row(requirement["id"], requirement["text"], "unverified", **common,
                             measured=check["actual"],
                             detail="Its check compares an input with itself."))
        else:
            rows.append(_row(requirement["id"], requirement["text"],
                             "passed" if check["passed"] and valid else "failed", **common,
                             measured=check["actual"],
                             detail=f"Measured {check['actual']:g} against {check['expected']:g} "
                                    f"± {check['tolerance']:g}."))

    changes = inspection.get("changes")
    if changes and "error" not in changes:
        flags = changes.get("flags") or []
        rows.append(_row(
            "no_unrequested_changes", "Nothing changed that was not asked for",
            "review" if flags else "passed", detail=" ".join(flags),
        ))

    counts = {status: sum(row["status"] == status for row in rows)
              for status in ("passed", "failed", "review", "unverified", "not_measurable")}
    if counts["failed"] or not valid:
        verdict = "failed"
    elif counts["passed"] and not counts["unverified"] and not counts["review"]:
        verdict = "verified"
    else:
        verdict = "partial"
    return {
        "verdict": verdict,
        **counts,
        "rows": rows,
        "rejected_checks": sorted(rejected),
        "assumptions": requirements["assumptions"],
        "summary": requirements["summary"],
    }


def describe(acceptance: dict[str, Any]) -> str:
    """One line for the run trace."""
    measurable = acceptance["passed"] + acceptance["failed"] + acceptance["unverified"]
    parts = [f"{acceptance['passed']} of {measurable} requirements measured and passed"]
    if acceptance["failed"]:
        parts.append(f"{acceptance['failed']} failed")
    if acceptance["unverified"]:
        parts.append(f"{acceptance['unverified']} unverified")
    if acceptance.get("review"):
        parts.append("changes outside the request to review")
    if acceptance["not_measurable"]:
        parts.append(f"{acceptance['not_measurable']} judged from images")
    return ", ".join(parts) + "."


def _census_counts(census: dict[str, Any] | None) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not census or "error" in census:
        return counts
    for kind, label in (("holes", "Holes"), ("bosses", "Bosses")):
        for entry in census.get(kind) or []:
            key = f"{label} of {entry['diameter_mm']:g} mm"
            counts[key] = counts.get(key, 0) + entry["count"]
    for entry in census.get("rounded_edges") or []:
        key = f"Rounded edges of {entry['radius_mm']:g} mm"
        counts[key] = counts.get(key, 0) + entry["count"]
    return counts


def change_report(
    previous: dict[str, Any], current_topology: dict[str, Any], current_inspection: dict[str, Any]
) -> dict[str, Any]:
    """What an edit changed, with a flag for each change that may be unwanted.

    The bridge cannot know what the user meant, so a flag asks for review:
    the agent must either confirm the user asked for it or fix it.
    """
    from execution.rematching import compare_analyses
    from execution.topology import TopologyAnalysis

    comparison = compare_analyses(
        TopologyAnalysis.model_validate(previous["topology"]),
        TopologyAnalysis.model_validate(current_topology),
    )
    if not comparison.valid:
        return {"error": comparison.error}
    before, after = previous["inspection"], current_inspection
    bounds_before = before.get("bounding_box_mm") or {}
    bounds_after = after.get("bounding_box_mm") or {}
    counts_before = _census_counts(before.get("census"))
    counts_after = _census_counts(after.get("census"))
    census_delta = {
        key: f"{counts_before.get(key, 0)} → {counts_after.get(key, 0)}"
        for key in sorted(set(counts_before) | set(counts_after))
        if counts_before.get(key, 0) != counts_after.get(key, 0)
    }
    violated = [item.constraint_id for item in comparison.constraint_evaluations if item.status == "violated"]

    flags = [f"Feature '{feature_id}' was removed." for feature_id in comparison.removed_feature_ids]
    flags += [f"Constraint '{constraint_id}' is no longer met." for constraint_id in violated]
    # A resize moves features between sizes; only fewer of a kind is a loss.
    for kind in ("Holes", "Bosses", "Rounded edges"):
        before_total = sum(count for key, count in counts_before.items() if key.startswith(kind + " of"))
        after_total = sum(count for key, count in counts_after.items() if key.startswith(kind + " of"))
        if after_total < before_total:
            lost = ", ".join(
                f"{key[len(kind) + 4:]} {counts_before[key]} → {counts_after.get(key, 0)}"
                for key in sorted(counts_before)
                if key.startswith(kind + " of") and counts_after.get(key, 0) < counts_before[key]
            )
            flags.append(f"{kind} went from {before_total} to {after_total} ({lost}).")
    return {
        "bounds_delta_mm": {
            axis: round(bounds_after.get(axis, 0) - bounds_before.get(axis, 0), 3)
            for axis in AXES if axis in bounds_before or axis in bounds_after
        },
        "volume_delta_mm3": round((after.get("volume_mm3") or 0) - (before.get("volume_mm3") or 0), 3),
        "features": {
            "added": comparison.added_feature_ids,
            "removed": comparison.removed_feature_ids,
            "modified": [match.current_id for match in comparison.feature_matches if match.status == "modified"],
        },
        "constraints_violated": violated,
        "census_delta": census_delta,
        "flags": flags,
    }
