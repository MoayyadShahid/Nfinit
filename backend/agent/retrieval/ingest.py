import argparse
import ast
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from pinecone import Pinecone

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
    return records


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
    parser.add_argument("--pinecone", action="store_true")
    parser.add_argument(
        "--namespace",
        default=os.getenv("PINECONE_NAMESPACE", "build123d-patterns-v1"),
    )
    parser.add_argument("--minimum-patterns", type=int, default=200)
    args = parser.parse_args()

    patterns = extract_patterns(
        args.source_root,
        repository_url=args.repository_url,
        revision=args.revision,
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
                "submitted": submitted,
                "namespace": args.namespace if args.pinecone else None,
                "revision": args.revision,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
