import json
import re

from execution.policy import CodePolicyError, validate_cad_code


def validate_code(code: str) -> str | None:
    try:
        validate_cad_code(code)
        return None
    except CodePolicyError as error:
        return str(error)


def extract_code(raw: str, structured: bool) -> str:
    if not raw:
        return ""

    if structured:
        try:
            value = json.loads(raw)
            if isinstance(value.get("code"), str):
                return value["code"].strip()
        except (json.JSONDecodeError, AttributeError):
            pass

    fenced = re.search(r"```(?:python|py|json)?\s*\n?([\s\S]*?)```", raw)
    if fenced:
        inner = fenced.group(1).strip()
        if structured:
            try:
                value = json.loads(inner)
                if isinstance(value.get("code"), str):
                    return value["code"].strip()
            except (json.JSONDecodeError, AttributeError):
                pass
        return inner

    return raw.strip()
