"""What the local agent reads back from each tool: the facts it acts on, short.

The backend keeps full inspections. Every turn of a CLI agent rereads the
whole conversation, so a long tool result is paid for again on each later
turn. These views keep what a decision needs and drop echoes of the agent's
own input, passing rows and lists the agent did not ask for.
"""

from typing import Any

MAX_CENTERS = 6


def _cylinders(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "diameter_mm": entry["diameter_mm"],
            "count": entry["count"],
            "length_mm": entry["length_mm"],
            "axis": entry["axis"],
            "centers_mm": entry["centers_mm"][:MAX_CENTERS],
        }
        for entry in entries
    ]


def _census(census: dict[str, Any] | None) -> dict[str, Any] | None:
    if not census:
        return None
    if "error" in census:
        return {"error": census["error"]}
    view = {}
    if census.get("holes"):
        view["holes"] = _cylinders(census["holes"])
    if census.get("bosses"):
        view["bosses"] = _cylinders(census["bosses"])
    if census.get("rounded_edges"):
        view["rounded_edges"] = [
            [entry["radius_mm"], entry["count"], entry["surface"]] for entry in census["rounded_edges"]
        ]
    return view


def _acceptance(acceptance: dict[str, Any] | None) -> dict[str, Any] | None:
    if not acceptance:
        return None
    rows = []
    for row in acceptance["rows"]:
        item = {"id": row["id"], "status": row["status"]}
        if row["measured"] is not None:
            item["measured"] = row["measured"]
        if row["status"] != "passed":
            item["expected"] = row["expected"]
            if row["detail"]:
                item["detail"] = row["detail"]
        rows.append(item)
    view = {"verdict": acceptance["verdict"], "rows": rows}
    if acceptance.get("rejected_checks"):
        view["rejected_checks"] = acceptance["rejected_checks"]
    return view


def agent_view(inspection: dict[str, Any]) -> dict[str, Any]:
    """A build's result as the agent sees it."""
    view: dict[str, Any] = {"valid": inspection["valid"]}
    if inspection.get("error"):
        view["error"] = inspection["error"]
    for key in ("solid_count", "volume_mm3", "bounding_box_mm"):
        if inspection.get(key) is not None:
            view[key] = inspection[key]
    if inspection.get("warnings"):
        view["warnings"] = inspection["warnings"]
    solids = inspection.get("solids") or []
    if len(solids) > 1 or any(solid["inverted"] or not solid["manifold"] for solid in solids):
        view["solids"] = [
            {key: solid[key] for key in ("volume_mm3", "bounding_box_mm", "min_mm")}
            | ({"inverted": True} if solid["inverted"] else {})
            | ({"open": True} if not solid["manifold"] else {})
            for solid in solids
        ]
    census = _census(inspection.get("census"))
    if census:
        view["census"] = census
    acceptance = _acceptance(inspection.get("acceptance"))
    if acceptance:
        view["acceptance"] = acceptance
        named = {row["id"] for row in inspection["acceptance"]["rows"]}
    else:
        named = set()
    # Checks no requirement names still matter when they fail.
    other_checks = [
        check for check in inspection.get("checks") or []
        if check["name"] not in named and (not check["passed"] or not acceptance)
    ]
    if other_checks:
        view["checks"] = [
            {key: check[key] for key in ("name", "actual", "expected", "passed")} for check in other_checks
        ]
    changes = inspection.get("changes")
    if changes:
        view["changes"] = (
            {"error": changes["error"]} if "error" in changes else {
                key: changes[key] for key in ("flags", "bounds_delta_mm", "volume_delta_mm3", "census_delta")
                if changes.get(key)
            }
        )
    if inspection.get("reference_comparison"):
        view["reference_comparison"] = inspection["reference_comparison"]
    return view


def printability_view(report: dict[str, Any]) -> dict[str, Any]:
    """Printability findings that need action, and a line of facts."""
    facts = report["facts"]
    walls = facts.get("wall_thickness") or {}
    best = facts["orientations"][0] if facts.get("orientations") else None
    return {
        "findings": [
            {key: row[key] for key in ("rule", "status", "measured", "limit", "where", "suggestion") if row[key]}
            for row in report["findings"]
            if row["status"] in ("fail", "review")
        ],
        "passed": [row["rule"] for row in report["findings"] if row["status"] == "pass"],
        "not_measured": facts.get("not_measured", []),
        "wall_mm": {key: walls[key] for key in ("min_mm", "p05_mm", "median_mm") if key in walls},
        "overhang_mm2": facts["overhangs"]["area_mm2"],
        "best_orientation": best,
        "profile": report["profile"],
    }
