import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent.models import FaceSelection, ModelInspection, ModelUsage, TraceStep

MAX_PROJECT_STATE_BYTES = 20_000_000


class ProjectState(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    code: str = Field(default="", max_length=500_000)
    messages: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    model_id: str = Field(default="", alias="modelId", max_length=200)
    selection: FaceSelection | None = None
    last_run_id: str | None = Field(default=None, alias="lastRunId", max_length=100)

    @model_validator(mode="after")
    def validate_serialized_size(self):
        size = len(
            json.dumps(
                self.model_dump(mode="json", by_alias=True),
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if size > MAX_PROJECT_STATE_BYTES:
            raise ValueError(
                "Project state exceeds the 20 MB persisted snapshot limit."
            )
        return self


class ProjectCreate(BaseModel):
    name: str = Field(default="Untitled project", min_length=1, max_length=120)
    state: ProjectState = Field(default_factory=ProjectState)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Project name cannot be blank.")
        return value


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Project name cannot be blank.")
        return value


class RevisionCreate(BaseModel):
    state: ProjectState


class RevisionSummary(BaseModel):
    """A revision without its state: what a version list needs."""

    model_config = ConfigDict(serialize_by_alias=True)

    id: str
    project_id: str = Field(serialization_alias="projectId")
    revision_number: int = Field(serialization_alias="revisionNumber")
    created_at: datetime = Field(serialization_alias="createdAt")


class ProjectRevision(RevisionSummary):
    state: ProjectState


class ProjectSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    name: str
    revision_count: int = Field(serialization_alias="revisionCount")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")
    thumbnail_updated_at: datetime | None = Field(
        default=None, serialization_alias="thumbnailUpdatedAt"
    )


class ProjectDetail(ProjectSummary):
    latest_revision: ProjectRevision | None = Field(
        serialization_alias="latestRevision"
    )


RunStatus = Literal["running", "succeeded", "failed"]


class CadRunResult(BaseModel):
    """What a run produced. On failure this is the last attempt, kept so the
    tokens spent on it are not thrown away."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    code: str = ""
    plan: str = ""
    inspection: ModelInspection | None = None
    trace: list[TraceStep] = Field(default_factory=list)
    usage: ModelUsage = Field(default_factory=ModelUsage)
    revision_number: int | None = Field(default=None, alias="revisionNumber")


class RunEvent(BaseModel):
    """One progress step of a run: a stage that started or finished."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    seq: int
    stage: str = Field(max_length=100)
    status: str = Field(max_length=100)
    message: str = Field(default="", max_length=10_000)
    attempt: int | None = None
    duration_ms: int | None = Field(default=None, alias="durationMs")
    created_at: datetime = Field(alias="createdAt")


class CadRunRecord(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    id: str = Field(serialization_alias="runId")
    project_id: str | None = Field(serialization_alias="projectId")
    status: RunStatus
    prompt: str
    model_id: str = Field(serialization_alias="modelId")
    result: CadRunResult | None = None
    error: str | None = None
    created_at: datetime = Field(serialization_alias="createdAt")
    completed_at: datetime | None = Field(serialization_alias="completedAt")
    # Filled by GET /cad/runs/{id}: the events after the caller's cursor.
    events: list[RunEvent] = Field(default_factory=list)


# Stripe keeps retrying a past_due card, so access continues until it gives up
# and the subscription becomes unpaid or canceled.
ACTIVE_SUBSCRIPTION_STATUSES = frozenset({"active", "trialing", "past_due"})


class SubscriptionRecord(BaseModel):
    """The user's Stripe subscription as last reported by Stripe. A customer
    created for Checkout but never subscribed has status "none"."""

    stripe_customer_id: str
    stripe_subscription_id: str | None = None
    status: str = "none"
    current_period_end: datetime | None = None
    cancel_at_period_end: bool = False

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_SUBSCRIPTION_STATUSES


class RevisionMesh(BaseModel):
    """A short-lived link to a revision's GLB, plus its geometry facts."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    url: str
    expires_at: datetime = Field(alias="expiresAt")
    bytes: int
    inspection: ModelInspection


class RunStreamLink(BaseModel):
    """A signed link to a run's server-sent event stream."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    url: str
    expires_at: datetime = Field(alias="expiresAt")
