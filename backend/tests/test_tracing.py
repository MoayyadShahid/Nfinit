from contextlib import contextmanager

from agent.tracing import RunTracer, summarize_messages, summarize_text


class FakeObservation:
    def __init__(self):
        self.updates = []

    def update(self, **kwargs):
        self.updates.append(kwargs)
        return self


class FakeLangfuse:
    def __init__(self):
        self.observations = []

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        observation = FakeObservation()
        self.observations.append((kwargs, observation))
        yield observation


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


def test_run_tracer_creates_correlated_root_and_child_observations():
    client = FakeLangfuse()
    tracer = RunTracer("12345678-1234-1234-1234-123456789abc", client=client)

    with tracer.observation(
        "nfinit.cad.run",
        as_type="agent",
        input={"message_count": 1},
        root=True,
    ) as root:
        with tracer.observation(
            "node.plan",
            as_type="chain",
            input={"redacted": True},
        ) as child:
            child.update(output={"characters": 20})
        root.update(output={"valid": True})

    root_args, root_observation = client.observations[0]
    child_args, child_observation = client.observations[1]
    assert root_args["trace_context"]["trace_id"] == (
        "12345678123412341234123456789abc"
    )
    assert root_args["metadata"]["run_id"] == tracer.run_id
    assert child_args["metadata"]["run_id"] == tracer.run_id
    assert root_observation.updates == [{"output": {"valid": True}}]
    assert child_observation.updates == [{"output": {"characters": 20}}]
