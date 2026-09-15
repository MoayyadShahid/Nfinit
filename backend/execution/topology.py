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


class TopologyAnalysis(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    valid: bool
    topology_version: str | None = Field(default=None, alias="topologyVersion")
    faces: list[TopologyFace] = Field(default_factory=list)
    edges: list[TopologyEdge] = Field(default_factory=list)
    features: list[SemanticFeature] = Field(default_factory=list)
    unassigned_face_ids: list[str] = Field(
        default_factory=list, alias="unassignedFaceIds"
    )
    selected_face: ResolvedFaceSelection | None = Field(
        default=None, alias="selectedFace"
    )
    error: str | None = None
