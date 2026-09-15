from pathlib import Path

from .models import LiveEvaluationConfig


def load_live_config(path: Path) -> LiveEvaluationConfig:
    return LiveEvaluationConfig.model_validate_json(path.read_text(encoding="utf-8"))
