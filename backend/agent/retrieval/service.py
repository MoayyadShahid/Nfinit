import json
import logging
import math
import os
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from pinecone import Pinecone

from .models import PatternRecord, RetrievedPattern

logger = logging.getLogger(__name__)

TOKEN_PATTERN = re.compile(r"[a-z][a-z0-9_]+")
SYNONYMS = {
    "holes": "hole",
    "bores": "hole",
    "cutout": "subtract",
    "cutouts": "subtract",
    "rounded": "fillet",
    "roundover": "fillet",
    "array": "pattern",
    "arrays": "pattern",
    "circular": "polar",
    "bracket": "mount",
    "mounting": "mount",
}


class PatternRetriever(Protocol):
    backend: str

    def retrieve(self, query: str, limit: int = 4) -> list[RetrievedPattern]: ...


class NullPatternRetriever:
    backend = "disabled"

    def retrieve(self, query: str, limit: int = 4) -> list[RetrievedPattern]:
        return []


def _tokens(value: str) -> list[str]:
    return [
        SYNONYMS.get(token, token)
        for token in TOKEN_PATTERN.findall(value.lower())
    ]


class LocalPatternRetriever:
    backend = "local"

    def __init__(self, patterns: list[PatternRecord]):
        self.patterns = patterns
        self.documents = [
            _tokens(
                " ".join(
                    [
                        pattern.title,
                        pattern.summary,
                        " ".join(pattern.keywords),
                        pattern.code,
                    ]
                )
            )
            for pattern in patterns
        ]
        document_frequency = Counter(
            token for document in self.documents for token in set(document)
        )
        count = max(len(patterns), 1)
        self.idf = {
            token: math.log((count + 1) / (frequency + 1)) + 1
            for token, frequency in document_frequency.items()
        }

    @classmethod
    def from_path(cls, path: Path) -> "LocalPatternRetriever":
        raw = path.read_text(encoding="utf-8").strip()
        if path.suffix == ".jsonl":
            values = [
                json.loads(line) for line in raw.splitlines() if line.strip()
            ]
        else:
            payload = json.loads(raw)
            values = (
                payload.get("patterns")
                if isinstance(payload, dict)
                else payload
            )
        if not isinstance(values, list):
            raise ValueError(f"{path} must contain a pattern list.")
        return cls([PatternRecord.model_validate(value) for value in values])

    def retrieve(self, query: str, limit: int = 4) -> list[RetrievedPattern]:
        query_tokens = _tokens(query)
        if not query_tokens or limit <= 0:
            return []
        query_counts = Counter(query_tokens)
        scored = []
        for pattern, document in zip(self.patterns, self.documents, strict=True):
            document_counts = Counter(document)
            score = sum(
                self.idf.get(token, 1.0)
                * min(query_count, document_counts.get(token, 0))
                * (1 + math.log1p(document_counts.get(token, 0)))
                for token, query_count in query_counts.items()
            )
            keyword_tokens = set(_tokens(" ".join(pattern.keywords)))
            score += 2.0 * len(set(query_tokens) & keyword_tokens)
            if score > 0:
                scored.append(
                    RetrievedPattern(
                        **pattern.model_dump(),
                        score=round(score, 6),
                        backend=self.backend,
                    )
                )
        return sorted(scored, key=lambda item: (-item.score, item.id))[:limit]


class PineconePatternRetriever:
    backend = "pinecone"

    def __init__(self, index: Any, namespace: str):
        self.index = index
        self.namespace = namespace

    def retrieve(self, query: str, limit: int = 4) -> list[RetrievedPattern]:
        if not query.strip() or limit <= 0:
            return []
        response = self.index.search(
            namespace=self.namespace,
            top_k=limit,
            inputs={"text": query[:4_000]},
            fields=[
                "title",
                "summary",
                "code",
                "keywords",
                "source_url",
                "license",
            ],
        )
        hits = getattr(getattr(response, "result", None), "hits", None)
        if hits is None and isinstance(response, dict):
            hits = response.get("result", {}).get("hits", [])
        results = []
        for hit in hits or []:
            fields = getattr(hit, "fields", None)
            if fields is None and isinstance(hit, dict):
                fields = hit.get("fields", {})
            hit_id = getattr(hit, "id", None)
            score = getattr(hit, "score", None)
            if isinstance(hit, dict):
                hit_id = hit_id or hit.get("_id") or hit.get("id")
                score = score if score is not None else hit.get("_score", 0)
            fields = dict(fields or {})
            results.append(
                RetrievedPattern(
                    id=str(hit_id),
                    title=str(fields.get("title", hit_id)),
                    summary=str(fields.get("summary", "")),
                    code=str(fields.get("code", "")),
                    keywords=list(fields.get("keywords") or []),
                    source_url=fields.get("source_url"),
                    license=fields.get("license"),
                    score=float(score or 0),
                    backend=self.backend,
                )
            )
        return results


class FallbackPatternRetriever:
    @property
    def backend(self) -> str:
        return self.primary.backend

    def __init__(
        self, primary: PatternRetriever, fallback: PatternRetriever
    ):
        self.primary = primary
        self.fallback = fallback

    def retrieve(self, query: str, limit: int = 4) -> list[RetrievedPattern]:
        try:
            return self.primary.retrieve(query, limit)
        except Exception:
            logger.warning(
                "Pinecone pattern retrieval failed; using local corpus.",
                exc_info=True,
            )
            return self.fallback.retrieve(query, limit)


@lru_cache(maxsize=1)
def get_pattern_retriever() -> PatternRetriever:
    corpus_path = Path(
        os.getenv(
            "PATTERN_RAG_LOCAL_CORPUS",
            Path(__file__).with_name("patterns.json"),
        )
    )
    local = LocalPatternRetriever.from_path(corpus_path)
    if os.getenv("PATTERN_RAG_ENABLED", "true").lower() in {"0", "false", "no"}:
        return NullPatternRetriever()

    api_key = os.getenv("PINECONE_API_KEY")
    index_host = os.getenv("PINECONE_INDEX_HOST")
    index_name = os.getenv("PINECONE_INDEX_NAME")
    if not api_key or not (index_host or index_name):
        return local

    client = Pinecone(api_key=api_key)
    index = (
        client.Index(host=index_host)
        if index_host
        else client.Index(index_name)
    )
    pinecone = PineconePatternRetriever(
        index,
        os.getenv("PINECONE_NAMESPACE", "build123d-patterns-v1"),
    )
    return FallbackPatternRetriever(pinecone, local)


def format_pattern_context(
    patterns: list[RetrievedPattern], max_characters: int = 6_000
) -> str:
    if not patterns:
        return ""
    sections = [
        "Retrieved build123d reference patterns. Adapt them to the design; "
        "do not copy imports, exporters, viewers, or file operations."
    ]
    for pattern in patterns:
        source = f"\nSource: {pattern.source_url}" if pattern.source_url else ""
        section = (
            f"\n<pattern id=\"{pattern.id}\" title=\"{pattern.title}\">\n"
            f"{pattern.summary}{source}\n"
            f"```python\n{pattern.code.strip()}\n```\n"
            "</pattern>"
        )
        if len("\n".join([*sections, section])) > max_characters:
            break
        sections.append(section)
    return "\n".join(sections)
