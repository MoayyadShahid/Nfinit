from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str | list[dict[str, Any]]


class FaceSelection(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    point: tuple[float, float, float]
    normal: tuple[float, float, float]
    entity_id: str | None = Field(default=None, alias="entityId")
    topology_version: str | None = Field(default=None, alias="topologyVersion")
    surface_type: str | None = Field(default=None, alias="surfaceType")
    confidence: float | None = Field(default=None, ge=0, le=1)


class MeshReference(BaseModel):
    name: str = Field(max_length=200)
    data: str = Field(max_length=14_000_000)
    units: Literal["mm", "in"]
    mode: Literal["preserve", "reconstruct"]
    facts: dict[str, Any] = Field(default_factory=dict)


class CadRunRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    messages: list[ChatMessage]
    code: str = ""
    model_id: str = Field(alias="modelId")
    # Optional cheaper model for the plan step; code and repairs use model_id.
    plan_model_id: str | None = Field(default=None, alias="planModelId")
    supports_structured_outputs: bool = Field(
        default=False, alias="supportsStructuredOutputs"
    )
    selection: FaceSelection | None = None
    mesh_reference: MeshReference | None = Field(default=None, alias="meshReference")


class ModelInspection(BaseModel):
    valid: bool
    shape_type: str | None = None
    solid_count: int | None = None
    volume_mm3: float | None = None
    bounding_box_mm: dict[str, float] | None = None
    error: str | None = None
    checks: list[dict[str, Any]] = Field(default_factory=list)
    verification: Literal["unverified", "measured", "failed"] = "unverified"
    reference_comparison: dict[str, Any] | None = None
    # Holes, bosses and rounded edges counted from the faces. Older saved
    # inspections have none.
    census: dict[str, Any] | None = None


class TraceStep(BaseModel):
    node: Literal["retrieve", "plan", "generate", "inspect", "repair"]
    status: Literal["complete", "passed", "failed"]
    detail: str
    duration_ms: int = 0


class ModelUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    # As reported by OpenRouter for each call, reasoning tokens included.
    cost_usd: float = 0.0
