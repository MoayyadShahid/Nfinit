from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent.models import FaceSelection


class ProjectState(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    code: str = Field(default="", max_length=500_000)
    messages: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    model_id: str = Field(default="", alias="modelId", max_length=200)
    selection: FaceSelection | None = None
    last_run_id: str | None = Field(default=None, alias="lastRunId", max_length=100)


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


class ProjectRevision(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    id: str
    project_id: str = Field(serialization_alias="projectId")
    revision_number: int = Field(serialization_alias="revisionNumber")
    state: ProjectState
    created_at: datetime = Field(serialization_alias="createdAt")


class ProjectSummary(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True)

    id: str
    name: str
    revision_count: int = Field(serialization_alias="revisionCount")
    created_at: datetime = Field(serialization_alias="createdAt")
    updated_at: datetime = Field(serialization_alias="updatedAt")


class ProjectDetail(ProjectSummary):
    latest_revision: ProjectRevision | None = Field(
        serialization_alias="latestRevision"
    )
