import logging

import pytest

from agent.tracing import RunTracer, summarize_messages, summarize_text


def test_message_summary_redacts_text_and_images():
    secret_text = "Design project falcon with customer-secret dimensions"
    secret_image = "data:image/png;base64,TOP_SECRET_BYTES"

    summary = summarize_messages(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": secret_text},
                    {"type": "image_url", "image_url": {"url": secret_image}},
                ],
            }
        ]
    )

    serialized = str(summary)
    assert secret_text not in serialized
    assert secret_image not in serialized
    assert summary["image_count"] == 1
    assert summary["images_redacted"] is True
    assert summary["text"]["characters"] == len(secret_text)


def test_text_summary_is_stable_without_retaining_content():
    first = summarize_text("same private prompt")
    second = summarize_text("same private prompt")

    assert first == second
    assert "same private prompt" not in str(first)


def test_local_observations_log_timing_without_private_payloads(caplog):
    tracer = RunTracer("local-run")
    with caplog.at_level(logging.DEBUG, logger="agent.tracing"):
        with tracer.observation("node.plan", input="private-prompt") as observation:
            observation.update(output="private-code", metadata={"image": "private-image"})
    assert "local-run" in caplog.text
    assert "node.plan" in caplog.text
    assert "duration_ms=" in caplog.text
    assert "private-" not in caplog.text


def test_failed_observation_preserves_error_without_logging_its_payload(caplog):
    with caplog.at_level(logging.DEBUG, logger="agent.tracing"):
        with pytest.raises(ValueError, match="private-code"):
            with RunTracer("local-run").observation("node.generate"):
                raise ValueError("private-code")
    assert "level=ERROR" in caplog.text
    assert "private-code" not in caplog.text
