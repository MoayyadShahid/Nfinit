from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from agent.models import (
    ChatMessage,
    FaceSelection,
    ModelInspection,
    ModelUsage,
    TraceStep,
)


class GeometryExpectation(BaseModel):
    valid: bool = True
    solid_count: int | None = None
    bounding_box_mm: dict[Literal["x", "y", "z"], float] | None = None
    dimension_tolerance_mm: float = Field(default=0.1, ge=0)
    volume_mm3: float | None = None
    volume_tolerance_percent: float = Field(default=1.0, ge=0)
    max_repair_attempts: int | None = Field(default=3, ge=0)
    max_latency_ms: int | None = Field(default=None, gt=0)
    max_total_tokens: int | None = Field(default=None, gt=0)


class EvaluationCase(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$")
    category: str
    description: str
    messages: list[ChatMessage]
    current_code: str = ""
    selection: FaceSelection | None = None
    expected: GeometryExpectation
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_messages(self):
        if not self.messages or self.messages[-1].role != "user":
            raise ValueError("Evaluation messages must end with a user message.")
        return self


class ReplayRecord(BaseModel):
    case_id: str
    model_id: str
    code: str
    plan: str = ""
    trace: list[TraceStep] = Field(default_factory=list)
    usage: ModelUsage = Field(default_factory=ModelUsage)


class MetricScore(BaseModel):
    passed: bool
    value: Any = None
    expected: Any = None
    message: str


class EvaluationResult(BaseModel):
    case_id: str
    category: str
    model_id: str
    run_id: str | None = None
    passed: bool
    scores: dict[str, MetricScore]
    inspection: ModelInspection
    repair_attempts: int
    latency_ms: int
    usage: ModelUsage
    error: str | None = None


class ModelSummary(BaseModel):
    cases: int
    passed: int
    pass_rate: float
    mean_latency_ms: float
    mean_total_tokens: float
    repair_rate: float


class EvaluationReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    mode: Literal["replay", "live"]
    models: list[str]
    summary: dict[str, ModelSummary]
    results: list[EvaluationResult]


class LiveModelConfig(BaseModel):
    id: str
    label: str
    supports_structured_outputs: bool = True


class LiveEvaluationConfig(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    name: str
    description: str
    models: list[LiveModelConfig]
    langfuse_dataset: str

    @model_validator(mode="after")
    def validate_unique_models(self):
        ids = [model.id for model in self.models]
        if not ids:
            raise ValueError("Live evaluation config must include at least one model.")
        if len(ids) != len(set(ids)):
            raise ValueError("Live evaluation config contains duplicate model IDs.")
        return self
