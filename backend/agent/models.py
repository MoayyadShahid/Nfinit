from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str | list[dict[str, Any]]


class FaceSelection(BaseModel):
    point: tuple[float, float, float]
    normal: tuple[float, float, float]


class CadRunRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    messages: list[ChatMessage]
    code: str = ""
    model_id: str = Field(alias="modelId")
    supports_structured_outputs: bool = Field(
        default=False, alias="supportsStructuredOutputs"
    )
    selection: FaceSelection | None = None


class ModelInspection(BaseModel):
    valid: bool
    shape_type: str | None = None
    solid_count: int | None = None
    volume_mm3: float | None = None
    bounding_box_mm: dict[str, float] | None = None
    error: str | None = None


class TraceStep(BaseModel):
    node: Literal["plan", "generate", "inspect", "repair"]
    status: Literal["complete", "passed", "failed"]
    detail: str
    duration_ms: int = 0


class ModelUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class CadRunResponse(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    run_id: str = Field(serialization_alias="runId")
    code: str
    plan: str
    inspection: ModelInspection
    trace: list[TraceStep]
    usage: ModelUsage
