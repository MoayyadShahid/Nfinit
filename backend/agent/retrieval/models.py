from pydantic import BaseModel, Field


class PatternRecord(BaseModel):
    id: str
    title: str
    summary: str
    code: str
    keywords: list[str] = Field(default_factory=list)
    source_url: str | None = None
    license: str | None = None


class RetrievedPattern(PatternRecord):
    score: float
    backend: str
