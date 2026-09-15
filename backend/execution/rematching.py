import math
from collections.abc import Iterable

from .runner import analyze_code
from .topology import (
    ConstraintRevisionMatch,
    FaceRevisionMatch,
    FeatureRevisionMatch,
    RevisionComparison,
    SemanticFeature,
    TopologyAnalysis,
    TopologyBounds,
    TopologyFace,
)

AMBIGUITY_MARGIN = 0.02
MAX_FACE_DISTANCE_SCORE = 0.75


def _changed_fields(previous, current, fields: Iterable[str]) -> list[str]:
    return [
        field
        for field in fields
        if getattr(previous, field) != getattr(current, field)
    ]


def _feature_owner_map(
    features: list[SemanticFeature],
) -> dict[str, str]:
    return {
        face_id: feature.id
        for feature in features
        for face_id in feature.owned_face_ids
    }


def _bounds_size(bounds: TopologyBounds) -> tuple[float, float, float]:
    return tuple(
        bounds.maximum[index] - bounds.minimum[index] for index in range(3)
    )


def _model_diagonal(faces: list[TopologyFace]) -> float:
    if not faces:
        return 1.0
    minimum = tuple(
        min(face.bounds_mm.minimum[index] for face in faces)
        for index in range(3)
    )
    maximum = tuple(
        max(face.bounds_mm.maximum[index] for face in faces)
        for index in range(3)
    )
    return max(math.dist(minimum, maximum), 1.0)


def _relative_difference(previous: float, current: float) -> float:
    return abs(previous - current) / max(abs(previous), abs(current), 1e-6)


def _face_distance(
    previous: TopologyFace,
    current: TopologyFace,
    model_scale: float,
) -> float:
    center = math.dist(previous.center_mm, current.center_mm) / model_scale
    area = _relative_difference(previous.area_mm2, current.area_mm2)
    previous_size = _bounds_size(previous.bounds_mm)
    current_size = _bounds_size(current.bounds_mm)
    bounds = sum(
        _relative_difference(previous_size[index], current_size[index])
        for index in range(3)
    ) / 3
    normal_dot = max(
        -1.0,
        min(
            1.0,
            sum(
                previous.normal[index] * current.normal[index]
                for index in range(3)
            ),
        ),
    )
    normal = (1.0 - normal_dot) / 2
    edges = abs(len(previous.edge_ids) - len(current.edge_ids)) / max(
        len(previous.edge_ids), len(current.edge_ids), 1
    )
    return (
        0.35 * center
        + 0.30 * area
        + 0.20 * bounds
        + 0.10 * normal
        + 0.05 * edges
    )


def _face_matches(
    previous: TopologyAnalysis,
    current: TopologyAnalysis,
) -> tuple[list[FaceRevisionMatch], list[str], list[str]]:
    previous_faces = {face.id: face for face in previous.faces}
    current_faces = {face.id: face for face in current.faces}
    previous_owners = _feature_owner_map(previous.features)
    current_owners = _feature_owner_map(current.features)
    matches: list[FaceRevisionMatch] = []

    exact_ids = sorted(set(previous_faces) & set(current_faces))
    for face_id in exact_ids:
        previous_owner = previous_owners.get(face_id)
        current_owner = current_owners.get(face_id)
        matches.append(
            FaceRevisionMatch(
                previous_face_id=face_id,
                current_face_id=face_id,
                previous_feature_id=previous_owner,
                current_feature_id=current_owner,
                status=(
                    "unchanged"
                    if previous_owner == current_owner
                    else "modified"
                ),
                confidence=1.0,
                reason="exact_geometry",
            )
        )

    remaining_previous = {
        face_id: face
        for face_id, face in previous_faces.items()
        if face_id not in exact_ids
    }
    remaining_current = {
        face_id: face
        for face_id, face in current_faces.items()
        if face_id not in exact_ids
    }
    model_scale = max(
        _model_diagonal(previous.faces),
        _model_diagonal(current.faces),
    )
    candidates: list[tuple[float, str, str]] = []
    by_previous: dict[str, list[tuple[float, str]]] = {}
    by_current: dict[str, list[tuple[float, str]]] = {}
    for previous_id, previous_face in remaining_previous.items():
        previous_owner = previous_owners.get(previous_id)
        for current_id, current_face in remaining_current.items():
            current_owner = current_owners.get(current_id)
            if previous_face.surface_type != current_face.surface_type:
                continue
            if previous_owner != current_owner:
                continue
            score = _face_distance(previous_face, current_face, model_scale)
            if score > MAX_FACE_DISTANCE_SCORE:
                continue
            candidates.append((score, previous_id, current_id))
            by_previous.setdefault(previous_id, []).append((score, current_id))
            by_current.setdefault(current_id, []).append((score, previous_id))

    def ambiguous(values: list[tuple[float, str]]) -> bool:
        ordered = sorted(values)
        return (
            len(ordered) > 1
            and ordered[1][0] - ordered[0][0] < AMBIGUITY_MARGIN
        )

    ambiguous_previous = {
        face_id for face_id, values in by_previous.items() if ambiguous(values)
    }
    ambiguous_current = {
        face_id for face_id, values in by_current.items() if ambiguous(values)
    }
    used_previous: set[str] = set()
    used_current: set[str] = set()
    for score, previous_id, current_id in sorted(
        candidates, key=lambda item: (item[0], item[1], item[2])
    ):
        if (
            previous_id in ambiguous_previous
            or current_id in ambiguous_current
            or previous_id in used_previous
            or current_id in used_current
        ):
            continue
        previous_owner = previous_owners.get(previous_id)
        current_owner = current_owners.get(current_id)
        matches.append(
            FaceRevisionMatch(
                previous_face_id=previous_id,
                current_face_id=current_id,
                previous_feature_id=previous_owner,
                current_feature_id=current_owner,
                status="modified",
                confidence=round(max(0.0, 1.0 - score), 4),
                reason=(
                    "same_feature_geometry"
                    if previous_owner is not None
                    else "legacy_geometry"
                ),
            )
        )
        used_previous.add(previous_id)
        used_current.add(current_id)

    matched_previous = {
        match.previous_face_id for match in matches
    }
    matched_current = {match.current_face_id for match in matches}
    return (
        sorted(matches, key=lambda match: match.previous_face_id),
        sorted(set(previous_faces) - matched_previous),
        sorted(set(current_faces) - matched_current),
    )


def compare_analyses(
    previous: TopologyAnalysis,
    current: TopologyAnalysis,
) -> RevisionComparison:
    if not previous.valid or not current.valid:
        errors = []
        if not previous.valid:
            errors.append(f"Previous revision: {previous.error}")
        if not current.valid:
            errors.append(f"Current revision: {current.error}")
        return RevisionComparison(valid=False, error="; ".join(errors))

    previous_features = {feature.id: feature for feature in previous.features}
    current_features = {feature.id: feature for feature in current.features}
    feature_matches = []
    for feature_id in sorted(set(previous_features) & set(current_features)):
        before = previous_features[feature_id]
        after = current_features[feature_id]
        changes = _changed_fields(
            before,
            after,
            ("name", "operation", "parent_id", "parameters", "sequence"),
        )
        if set(before.owned_face_ids) != set(after.owned_face_ids):
            changes.append("geometry")
        feature_matches.append(
            FeatureRevisionMatch(
                previous_id=feature_id,
                current_id=feature_id,
                status="modified" if changes else "unchanged",
                confidence=1.0,
                reason="authored_id",
                changes=changes,
            )
        )

    previous_constraints = {
        constraint.id: constraint for constraint in previous.constraints
    }
    current_constraints = {
        constraint.id: constraint for constraint in current.constraints
    }
    constraint_matches = []
    for constraint_id in sorted(
        set(previous_constraints) & set(current_constraints)
    ):
        before = previous_constraints[constraint_id]
        after = current_constraints[constraint_id]
        changes = _changed_fields(
            before, after, ("kind", "feature_ids", "parameters", "sequence")
        )
        constraint_matches.append(
            ConstraintRevisionMatch(
                previous_id=constraint_id,
                current_id=constraint_id,
                status="modified" if changes else "unchanged",
                changes=changes,
            )
        )

    face_matches, unmatched_previous, unmatched_current = _face_matches(
        previous, current
    )
    return RevisionComparison(
        valid=True,
        previous_topology_version=previous.topology_version,
        current_topology_version=current.topology_version,
        feature_matches=feature_matches,
        added_feature_ids=sorted(set(current_features) - set(previous_features)),
        removed_feature_ids=sorted(
            set(previous_features) - set(current_features)
        ),
        constraint_matches=constraint_matches,
        added_constraint_ids=sorted(
            set(current_constraints) - set(previous_constraints)
        ),
        removed_constraint_ids=sorted(
            set(previous_constraints) - set(current_constraints)
        ),
        face_matches=face_matches,
        unmatched_previous_face_ids=unmatched_previous,
        unmatched_current_face_ids=unmatched_current,
    )


def compare_code(previous_code: str, current_code: str) -> RevisionComparison:
    return compare_analyses(
        analyze_code(previous_code),
        analyze_code(current_code),
    )
