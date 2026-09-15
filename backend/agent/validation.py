import json
import re


BLOCKED_PATTERNS = (
    (re.compile(r"^\s*(import\s|from\s+\S+\s+import)", re.MULTILINE), "import statement"),
    (re.compile(r"\bexec\s*\("), "exec()"),
    (re.compile(r"\beval\s*\("), "eval()"),
    (re.compile(r"\bopen\s*\("), "open()"),
    (re.compile(r"__\w+__"), "dunder attribute"),
)


def validate_code(code: str) -> str | None:
    if not code.strip():
        return "Generated code is empty."

    for pattern, label in BLOCKED_PATTERNS:
        if pattern.search(code):
            return f"Generated code contains forbidden pattern: {label}"

    if not re.search(r"\bresult\s*=", code) and not re.search(
        r"with\s+BuildPart\s*\(", code
    ):
        return "Generated code must contain 'result = ...' or 'with BuildPart() as part:'."

    return None


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
