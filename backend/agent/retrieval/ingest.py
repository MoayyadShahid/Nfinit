import argparse
import ast
import hashlib
import json
import os
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from pinecone import Pinecone

from execution.policy import CodePolicyError, validate_cad_code

from .models import PatternRecord

LOWERCASE_CAD_CALLS = {
    "add",
    "chamfer",
    "extrude",
    "fillet",
    "loft",
    "make_brake_formed",
    "make_face",
    "mirror",
    "offset",
    "project",
    "revolve",
    "scale",
    "split",
    "sweep",
}
EXCLUDED_CALLS = {
    "print",
    "show",
    "show_all",
    "show_object",
    "show_object_options",
}
CAMEL_WORD = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+")


def _call_name(call: ast.Call) -> str | None:
    value = call.func
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return None


def _is_cad_call(name: str) -> bool:
    if name in EXCLUDED_CALLS or name.startswith("_"):
        return False
    return name in LOWERCASE_CAD_CALLS or name[:1].isupper()


def _keywords(path: Path, symbols: list[str]) -> list[str]:
    values = [path.stem.replace("_", " ")]
    values.extend(" ".join(CAMEL_WORD.findall(symbol)) for symbol in symbols)
    return sorted(
        {
            token.lower()
            for value in values
            for token in re.findall(r"[a-zA-Z][a-zA-Z0-9]+", value)
            if len(token) > 2
        }
    )


def extract_patterns(
    source_root: Path,
    *,
    repository_url: str = "https://github.com/gumyr/build123d",
    revision: str = "dev",
) -> list[PatternRecord]:
    source_root = source_root.resolve()
    license_path = source_root / "LICENSE"
    if not license_path.exists() or "Apache License" not in license_path.read_text(
        encoding="utf-8"
    ):
        raise ValueError(
            "The source root must be an Apache-2.0 build123d checkout "
            "containing LICENSE."
        )

    candidates = sorted(
        {
            *source_root.glob("examples/**/*.py"),
            *source_root.glob("docs/**/*.py"),
        }
    )
    records: list[PatternRecord] = []
    seen_snippets: set[str] = set()
    for path in candidates:
        relative = path.relative_to(source_root)
        if path.name in {"conf.py", "build123d_lexer.py"}:
            continue
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        lines = source.splitlines()
        calls = [
            (node, name)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (name := _call_name(node)) is not None
            and _is_cad_call(name)
        ]
        for node, primary_symbol in calls:
            start = max(0, node.lineno - 6)
            end = min(len(lines), (node.end_lineno or node.lineno) + 7)
            snippet = "\n".join(lines[start:end]).strip()
            normalized = "\n".join(
                line.rstrip() for line in snippet.splitlines()
            )
            if (
                normalized in seen_snippets
                or len(normalized.splitlines()) < 3
                or len(normalized) > 4_000
            ):
                continue
            seen_snippets.add(normalized)
            symbols = sorted(
                {
                    name
                    for child in ast.walk(node)
                    if isinstance(child, ast.Call)
                    and (name := _call_name(child)) is not None
                    and _is_cad_call(name)
                }
            )
            digest = hashlib.sha256(
                f"{relative}:{normalized}".encode()
            ).hexdigest()[:20]
            source_url = (
                f"{repository_url.rstrip('/')}/blob/{revision}/"
                f"{relative.as_posix()}#L{start + 1}-L{end}"
            )
            records.append(
                PatternRecord(
                    id=f"build123d-{digest}",
                    title=(
                        f"{relative.stem.replace('_', ' ').title()}: "
                        f"{primary_symbol}"
                    ),
                    summary=(
                        f"Official build123d {primary_symbol} usage pattern "
                        f"from {relative.as_posix()}."
                    ),
                    code=normalized,
                    keywords=_keywords(relative, symbols or [primary_symbol]),
                    source_url=source_url,
                    license="Apache-2.0",
                )
            )
    candidates_by_position = []
    for record in records:
        source, line_range = (record.source_url or "").rsplit("#L", maxsplit=1)
        start_line = int(line_range.split("-", maxsplit=1)[0])
        candidates_by_position.append((source, start_line, record))

    safe_records = []
    last_line_by_source: dict[str, int] = {}
    for source, start_line, record in sorted(
        candidates_by_position, key=lambda item: (item[0], item[1], item[2].id)
    ):
        try:
            validate_cad_code(record.code)
        except CodePolicyError:
            continue
        if start_line - last_line_by_source.get(source, -10_000) < 12:
            continue
        last_line_by_source[source] = start_line
        safe_records.append(record)
    return safe_records


# Assertions in upstream tests become comments stating the checked result.
_COMPARISONS = {
    "assertAlmostEqual": "≈",
    "assertAlmostEquals": "≈",
    "assertTupleAlmostEquals": "≈",
    "assertVectorAlmostEquals": "≈",
    "assertEqual": "==",
    "assertEquals": "==",
    "assertNotEqual": "!=",
    "assertGreater": ">",
    "assertGreaterEqual": ">=",
    "assertLess": "<",
    "assertLessEqual": "<=",
    "assertIs": "is",
    "assertIn": "in",
}
_CHECK = "_nfinit_check_"
_BUILDER_RESULTS = {"BuildPart": "part", "BuildSketch": "sketch", "BuildLine": "line"}


def _self_call(node: ast.AST) -> str | None:
    """The method name of a ``self.method(...)`` call, if node is one."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
    ):
        return node.func.attr
    return None


def _check_text(name: str, args: list[ast.expr]) -> str | None:
    if name in _COMPARISONS and len(args) >= 2:
        return f"{ast.unparse(args[0])} {_COMPARISONS[name]} {ast.unparse(args[1])}"
    if name == "assertTrue" and args:
        return ast.unparse(args[0])
    if name == "assertFalse" and args:
        return f"not {ast.unparse(args[0])}"
    if name == "assertIsNone" and args:
        return f"{ast.unparse(args[0])} is None"
    if name == "assertIsNotNone" and args:
        return f"{ast.unparse(args[0])} is not None"
    return None


def _is_check(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == _CHECK
    )


def _strip_test_statements(body: list[ast.stmt]) -> list[ast.stmt]:
    """Replace assertions with check markers and drop expected failures."""
    kept: list[ast.stmt] = []
    for statement in body:
        if isinstance(statement, ast.With) and any(
            (_self_call(item.context_expr) or "").startswith("assert")
            for item in statement.items
        ):
            continue  # e.g. `with self.assertRaises(...)`: a failing example
        name = _self_call(statement.value) if isinstance(statement, ast.Expr) else None
        if name is not None:
            text = _check_text(name, statement.value.args)
            if text is not None:
                marker = ast.Expr(
                    ast.Call(ast.Name(_CHECK, ast.Load()), [ast.Constant(text)], [])
                )
                kept.append(ast.copy_location(marker, statement))
            continue
        for field in ("body", "orelse", "finalbody"):
            inner = getattr(statement, field, None)
            if isinstance(inner, list) and inner:
                stripped = _strip_test_statements(inner)
                # Check markers become comments, so a block needs code too.
                if all(_is_check(item) for item in stripped):
                    stripped.append(ast.Pass())
                setattr(statement, field, stripped)
        kept.append(statement)
    return kept


def _result_line(body: list[ast.stmt]) -> str | None:
    """The `result = ...` line that names the shape the test built."""
    for statement in reversed(body):
        if isinstance(statement, ast.With):
            for item in statement.items:
                call = item.context_expr
                name = _call_name(call) if isinstance(call, ast.Call) else None
                if name in _BUILDER_RESULTS and isinstance(item.optional_vars, ast.Name):
                    return f"result = {item.optional_vars.id}.{_BUILDER_RESULTS[name]}"
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, (ast.Call, ast.BinOp))
        ):
            return f"result = {statement.targets[0].id}"
    return None


def _render(body: list[ast.stmt]) -> str:
    code = ast.unparse(ast.Module(body=body, type_ignores=[]))
    lines = []
    for line in code.splitlines():
        match = re.fullmatch(rf"(\s*){_CHECK}\((.*)\)", line)
        if match:
            lines.append(f"{match.group(1)}# check: {ast.literal_eval(match.group(2))}")
        else:
            lines.append(line)
    return "\n".join(lines)


def extract_test_patterns(
    source_root: Path,
    *,
    repository_url: str = "https://github.com/gumyr/build123d",
    revision: str = "dev",
    builds: Callable[[str], bool] | None = None,
    workers: int = 4,
) -> list[PatternRecord]:
    """Turn upstream unit tests into verified, runnable usage patterns.

    Each test function becomes one snippet: its assertions become comments
    stating the checked result, expected failures are dropped, and a
    `result = ...` line names the built shape. A snippet is kept only when it
    passes the CAD code policy and, when `builds` is given, builds in the
    sandbox, so every pattern uses names and calls that really work here.
    """
    source_root = source_root.resolve()
    candidates = []
    for path in sorted(source_root.glob("tests/test_*.py")):
        relative = path.relative_to(source_root)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.FunctionDef) and node.name.startswith("test_")):
                continue
            body = _strip_test_statements(list(node.body))
            result = _result_line(body)
            if result is None:
                continue
            code = f"{_render(body)}\n{result}"
            uses_self = any(
                isinstance(child, ast.Name) and child.id == "self"
                for child in ast.walk(ast.parse(code))
            )
            if uses_self or not 3 <= len(code.splitlines()) <= 60 or len(code) > 4_000:
                continue
            try:
                validate_cad_code(code)
            except CodePolicyError:
                continue
            candidates.append((relative, node, code))

    if builds is not None:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            verdicts = list(pool.map(lambda item: builds(item[2]), candidates))
        candidates = [item for item, ok in zip(candidates, verdicts) if ok]

    records = []
    for relative, node, code in candidates:
        test_name = node.name.removeprefix("test_").replace("_", " ")
        symbols = sorted(
            {
                name
                for child in ast.walk(node)
                if isinstance(child, ast.Call)
                and (name := _call_name(child)) is not None
                and _is_cad_call(name)
            }
        )
        stem = relative.stem.removeprefix("test_")
        digest = hashlib.sha256(f"{relative}:{code}".encode()).hexdigest()[:20]
        records.append(
            PatternRecord(
                id=f"build123d-test-{digest}",
                title=f"{stem.replace('_', ' ').title()}: {test_name}",
                summary=(
                    f"Verified build123d unit test from {relative.as_posix()}; "
                    "the check comments state the results the test asserts."
                ),
                code=code,
                keywords=[
                    keyword
                    for keyword in _keywords(Path(stem), symbols + [test_name])
                    if keyword != "test"
                ],
                source_url=(
                    f"{repository_url.rstrip('/')}/blob/{revision}/"
                    f"{relative.as_posix()}#L{node.lineno}-L{node.end_lineno}"
                ),
                license="Apache-2.0",
            )
        )
    return records


def sandbox_builds(code: str) -> bool:
    """True when the code builds valid geometry in the CAD sandbox."""
    from execution import inspect_code

    return inspect_code(code).valid


def load_replay_patterns(path: Path) -> list[PatternRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("replays", [])
    patterns = []
    for value in values:
        code = str(value["code"]).strip()
        validate_cad_code(code)
        case_id = str(value["case_id"])
        patterns.append(
            PatternRecord(
                id=f"cad50-{case_id}",
                title=case_id.replace("_", " ").title(),
                summary=(
                    "Policy-validated deterministic CAD50 reference pattern."
                ),
                code=code,
                keywords=case_id.split("_"),
                source_url=(
                    "https://github.com/MoayyadShahid/Nfinit/blob/main/"
                    "backend/evaluation/replays/cad50.json"
                ),
            )
        )
    return patterns


def load_seed_patterns(path: Path) -> list[PatternRecord]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("patterns", [])
    patterns = [PatternRecord.model_validate(value) for value in values]
    for pattern in patterns:
        validate_cad_code(pattern.code)
    return patterns


def deduplicate_patterns(patterns: list[PatternRecord]) -> list[PatternRecord]:
    unique: dict[str, PatternRecord] = {}
    for pattern in patterns:
        digest = hashlib.sha256(pattern.code.encode()).hexdigest()
        unique.setdefault(digest, pattern)
    return list(unique.values())


def write_jsonl(patterns: list[PatternRecord], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(
            json.dumps(pattern.model_dump(), sort_keys=True) + "\n"
            for pattern in patterns
        ),
        encoding="utf-8",
    )


def _pinecone_index():
    api_key = os.getenv("PINECONE_API_KEY")
    index_host = os.getenv("PINECONE_INDEX_HOST")
    index_name = os.getenv("PINECONE_INDEX_NAME")
    if not api_key or not (index_host or index_name):
        raise ValueError(
            "PINECONE_API_KEY and either PINECONE_INDEX_HOST or "
            "PINECONE_INDEX_NAME are required."
        )
    client = Pinecone(api_key=api_key)
    return (
        client.index(host=index_host)
        if index_host
        else client.index(index_name)
    )


def upsert_patterns(
    patterns: list[PatternRecord],
    *,
    namespace: str,
    batch_size: int = 90,
) -> int:
    index = _pinecone_index()
    submitted = 0
    for offset in range(0, len(patterns), batch_size):
        batch = patterns[offset : offset + batch_size]
        records: list[dict[str, Any]] = [
            {
                "_id": pattern.id,
                "chunk_text": (
                    f"{pattern.title}\n{pattern.summary}\n"
                    f"Keywords: {', '.join(pattern.keywords)}\n"
                    f"{pattern.code}"
                ),
                **pattern.model_dump(exclude={"id"}),
            }
            for pattern in batch
        ]
        index.upsert_records(namespace=namespace, records=records)
        submitted += len(records)
    return submitted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract real patterns from an official build123d checkout."
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument(
        "--repository-url", default="https://github.com/gumyr/build123d"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replays", type=Path)
    parser.add_argument("--seed-corpus", type=Path)
    parser.add_argument("--pinecone", action="store_true")
    parser.add_argument(
        "--namespace",
        default=os.getenv("PINECONE_NAMESPACE", "build123d-patterns-v1"),
    )
    parser.add_argument("--minimum-patterns", type=int, default=100)
    parser.add_argument(
        "--no-tests",
        action="store_true",
        help="Skip the upstream unit tests.",
    )
    parser.add_argument(
        "--skip-sandbox",
        action="store_true",
        help="Keep test patterns that pass the policy without building them.",
    )
    args = parser.parse_args()

    upstream_patterns = extract_patterns(
        args.source_root,
        repository_url=args.repository_url,
        revision=args.revision,
    )
    test_patterns = (
        []
        if args.no_tests
        else extract_test_patterns(
            args.source_root,
            repository_url=args.repository_url,
            revision=args.revision,
            builds=None if args.skip_sandbox else sandbox_builds,
        )
    )
    replay_patterns = (
        load_replay_patterns(args.replays) if args.replays else []
    )
    seed_patterns = (
        load_seed_patterns(args.seed_corpus) if args.seed_corpus else []
    )
    patterns = deduplicate_patterns(
        [*upstream_patterns, *test_patterns, *replay_patterns, *seed_patterns]
    )
    if len(patterns) < args.minimum_patterns:
        raise SystemExit(
            f"Extracted {len(patterns)} patterns; refusing to continue below "
            f"the required minimum of {args.minimum_patterns}."
        )
    if args.output:
        write_jsonl(patterns, args.output)
    submitted = (
        upsert_patterns(patterns, namespace=args.namespace)
        if args.pinecone
        else 0
    )
    print(
        json.dumps(
            {
                "extracted": len(patterns),
                "upstream": len(upstream_patterns),
                "tests": len(test_patterns),
                "replays": len(replay_patterns),
                "curated": len(seed_patterns),
                "submitted": submitted,
                "namespace": args.namespace if args.pinecone else None,
                "revision": args.revision,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
