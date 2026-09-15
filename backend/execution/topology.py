from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TopologyBounds(BaseModel):
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]


class TopologyEdge(BaseModel):
    id: str
    curve_type: str
    length_mm: float
    center_mm: tuple[float, float, float]
    bounds_mm: TopologyBounds


class TopologyFace(BaseModel):
    id: str
    surface_type: str
    area_mm2: float
    center_mm: tuple[float, float, float]
    normal: tuple[float, float, float]
    bounds_mm: TopologyBounds
    edge_ids: list[str]


class ResolvedFaceSelection(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    face_id: str = Field(alias="faceId")
    surface_type: str = Field(alias="surfaceType")
    distance_mm: float = Field(alias="distanceMm")
    normal_alignment: float = Field(alias="normalAlignment")
    confidence: float


class SemanticFeature(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    name: str
    operation: Literal[
        "additive",
        "subtractive",
        "pattern",
        "fillet",
        "chamfer",
        "transform",
        "reference",
        "other",
    ]
    parent_id: str | None = Field(default=None, alias="parentId")
    parameters: dict[str, Any] = Field(default_factory=dict)
    sequence: int
    owned_face_ids: list[str] = Field(default_factory=list, alias="ownedFaceIds")


ConstraintKind = Literal[
    "distance",
    "angle",
    "radius",
    "diameter",
    "thickness",
    "count",
    "equal",
    "symmetry",
    "concentric",
    "coincident",
    "parallel",
    "perpendicular",
    "fixed",
    "other",
]


class SemanticConstraint(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    kind: ConstraintKind
    feature_ids: list[str] = Field(alias="featureIds")
    parameters: dict[str, Any] = Field(default_factory=dict)
    sequence: int


class TopologyAnalysis(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    valid: bool
    topology_version: str | None = Field(default=None, alias="topologyVersion")
    faces: list[TopologyFace] = Field(default_factory=list)
    edges: list[TopologyEdge] = Field(default_factory=list)
    features: list[SemanticFeature] = Field(default_factory=list)
    constraints: list[SemanticConstraint] = Field(default_factory=list)
    unassigned_face_ids: list[str] = Field(
        default_factory=list, alias="unassignedFaceIds"
    )
    selected_face: ResolvedFaceSelection | None = Field(
        default=None, alias="selectedFace"
    )
    error: str | None = None


class FeatureRevisionMatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    previous_id: str = Field(alias="previousId")
    current_id: str = Field(alias="currentId")
    status: Literal["unchanged", "modified"]
    confidence: float
    reason: Literal["authored_id"]
    changes: list[str] = Field(default_factory=list)


class ConstraintRevisionMatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    previous_id: str = Field(alias="previousId")
    current_id: str = Field(alias="currentId")
    status: Literal["unchanged", "modified"]
    changes: list[str] = Field(default_factory=list)


class ConstraintEvaluation(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    constraint_id: str = Field(alias="constraintId")
    status: Literal["satisfied", "violated", "unevaluated"]
    expected: Any = None
    actual: Any = None
    message: str


class FaceRevisionMatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    previous_face_id: str = Field(alias="previousFaceId")
    current_face_id: str = Field(alias="currentFaceId")
    previous_feature_id: str | None = Field(
        default=None, alias="previousFeatureId"
    )
    current_feature_id: str | None = Field(
        default=None, alias="currentFeatureId"
    )
    status: Literal["unchanged", "modified"]
    confidence: float
    reason: Literal["exact_geometry", "same_feature_geometry", "legacy_geometry"]


class SelectionRemap(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    previous_face_id: str = Field(alias="previousFaceId")
    current_face_id: str | None = Field(default=None, alias="currentFaceId")
    status: Literal["matched", "ambiguous", "unmatched", "stale"]
    confidence: float


class RevisionComparison(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    valid: bool
    previous_topology_version: str | None = Field(
        default=None, alias="previousTopologyVersion"
    )
    current_topology_version: str | None = Field(
        default=None, alias="currentTopologyVersion"
    )
    feature_matches: list[FeatureRevisionMatch] = Field(
        default_factory=list, alias="featureMatches"
    )
    added_feature_ids: list[str] = Field(
        default_factory=list, alias="addedFeatureIds"
    )
    removed_feature_ids: list[str] = Field(
        default_factory=list, alias="removedFeatureIds"
    )
    constraint_matches: list[ConstraintRevisionMatch] = Field(
        default_factory=list, alias="constraintMatches"
    )
    added_constraint_ids: list[str] = Field(
        default_factory=list, alias="addedConstraintIds"
    )
    removed_constraint_ids: list[str] = Field(
        default_factory=list, alias="removedConstraintIds"
    )
    constraint_evaluations: list[ConstraintEvaluation] = Field(
        default_factory=list, alias="constraintEvaluations"
    )
    face_matches: list[FaceRevisionMatch] = Field(
        default_factory=list, alias="faceMatches"
    )
    unmatched_previous_face_ids: list[str] = Field(
        default_factory=list, alias="unmatchedPreviousFaceIds"
    )
    unmatched_current_face_ids: list[str] = Field(
        default_factory=list, alias="unmatchedCurrentFaceIds"
    )
    ambiguous_previous_face_ids: list[str] = Field(
        default_factory=list, alias="ambiguousPreviousFaceIds"
    )
    ambiguous_current_face_ids: list[str] = Field(
        default_factory=list, alias="ambiguousCurrentFaceIds"
    )
    selection_remap: SelectionRemap | None = Field(
        default=None, alias="selectionRemap"
    )
    error: str | None = None
