from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from agent.tracing import get_langfuse_client, summarize_messages, summarize_text

from .models import EvaluationCase, EvaluationReport


@dataclass(frozen=True)
class PublishSummary:
    dataset_items: int
    traces_scored: int
    scores_created: int


def _trace_id(run_id: str) -> str:
    return run_id.replace("-", "")


def publish_live_evaluation(
    cases: list[EvaluationCase],
    report: EvaluationReport,
    dataset_name: str,
    *,
    client: Any | None = None,
) -> PublishSummary:
    if report.mode != "live":
        raise ValueError("Only live evaluation reports can be published to LangFuse.")

    client = client or get_langfuse_client()
    if client is None:
        raise ValueError(
            "LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required to publish."
        )

    client.create_dataset(
        name=dataset_name,
        description=(
            "Privacy-safe Nfinit CAD benchmark metadata and geometry expectations. "
            "Prompts, generated source, and images are not stored."
        ),
        metadata={
            "schema_version": report.schema_version,
            "case_count": len(cases),
            "privacy": "content-redacted",
        },
    )

    for case in cases:
        messages = [message.model_dump() for message in case.messages]
        client.create_dataset_item(
            dataset_name=dataset_name,
            id=str(uuid5(NAMESPACE_URL, f"{dataset_name}:{case.id}")),
            input={
                "case_id": case.id,
                "category": case.category,
                "messages": summarize_messages(messages),
                "current_code": summarize_text(case.current_code),
                "has_selection": case.selection is not None,
                "tags": case.tags,
            },
            expected_output=case.expected.model_dump(mode="json"),
            metadata={"content_redacted": True},
        )

    traces_scored = 0
    scores_created = 0
    for result in report.results:
        if not result.run_id:
            continue
        trace_id = _trace_id(result.run_id)
        score_metadata = {
            "case_id": result.case_id,
            "category": result.category,
            "model_id": result.model_id,
            "dataset": dataset_name,
        }
        client.create_score(
            name="cad.overall_pass",
            value=1.0 if result.passed else 0.0,
            data_type="BOOLEAN",
            trace_id=trace_id,
            metadata=score_metadata,
        )
        scores_created += 1
        for name, score in result.scores.items():
            client.create_score(
                name=f"cad.metric.{name}",
                value=1.0 if score.passed else 0.0,
                data_type="BOOLEAN",
                trace_id=trace_id,
                metadata=score_metadata,
            )
            scores_created += 1
        for name, value in (
            ("cad.repair_attempts", result.repair_attempts),
            ("cad.latency_ms", result.latency_ms),
            ("cad.total_tokens", result.usage.total_tokens),
        ):
            client.create_score(
                name=name,
                value=value,
                data_type="NUMERIC",
                trace_id=trace_id,
                metadata=score_metadata,
            )
            scores_created += 1
        traces_scored += 1

    client.flush()
    return PublishSummary(
        dataset_items=len(cases),
        traces_scored=traces_scored,
        scores_created=scores_created,
    )
