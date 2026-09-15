from agent.models import ModelInspection, ModelUsage
from evaluation.langfuse import publish_live_evaluation
from evaluation.models import EvaluationCase
from evaluation.reporting import build_report
from evaluation.scoring import score_evaluation


class FakeLangfuse:
    def __init__(self):
        self.datasets = []
        self.items = []
        self.scores = []
        self.flushed = False

    def create_dataset(self, **kwargs):
        self.datasets.append(kwargs)

    def create_dataset_item(self, **kwargs):
        self.items.append(kwargs)

    def create_score(self, **kwargs):
        self.scores.append(kwargs)

    def flush(self):
        self.flushed = True


def test_live_results_publish_redacted_dataset_and_trace_scores():
    private_prompt = "Customer secret: make project Falcon 10 mm wide"
    private_code = "private_width = 10\nresult = Box(private_width, 20, 30)"
    case = EvaluationCase.model_validate(
        {
            "id": "private_box",
            "category": "primitive",
            "description": "Private box fixture",
            "messages": [{"role": "user", "content": private_prompt}],
            "current_code": private_code,
            "expected": {
                "solid_count": 1,
                "bounding_box_mm": {"x": 10, "y": 20, "z": 30},
            },
            "tags": ["private-fixture"],
        }
    )
    result = score_evaluation(
        case,
        "test/model",
        "result = Box(10, 20, 30)",
        ModelInspection(
            valid=True,
            solid_count=1,
            bounding_box_mm={"x": 10, "y": 20, "z": 30},
        ),
        [],
        ModelUsage(total_tokens=100),
        run_id="12345678-1234-1234-1234-123456789abc",
    )
    client = FakeLangfuse()

    published = publish_live_evaluation(
        [case],
        build_report("live", [result]),
        "test-dataset",
        client=client,
    )

    serialized_item = str(client.items[0])
    assert private_prompt not in serialized_item
    assert private_code not in serialized_item
    assert client.items[0]["input"]["messages"]["text"]["characters"] == len(
        private_prompt
    )
    assert client.items[0]["metadata"]["content_redacted"] is True
    assert {
        score["trace_id"] for score in client.scores
    } == {"12345678123412341234123456789abc"}
    assert any(score["name"] == "cad.overall_pass" for score in client.scores)
    assert any(score["name"] == "cad.metric.execution" for score in client.scores)
    assert any(score["name"] == "cad.total_tokens" for score in client.scores)
    assert published.dataset_items == 1
    assert published.traces_scored == 1
    assert published.scores_created == len(client.scores)
    assert client.flushed
