import ast

MAX_CODE_BYTES = 100_000
MAX_AST_NODES = 5_000
MAX_STRING_BYTES = 20_000

BLOCKED_NODES = (
    ast.AsyncFor,
    ast.AsyncFunctionDef,
    ast.AsyncWith,
    ast.Await,
    ast.ClassDef,
    ast.Delete,
    ast.FunctionDef,
    ast.Global,
    ast.Import,
    ast.ImportFrom,
    ast.Lambda,
    # Pattern matching stores requested attribute names as plain strings in
    # MatchClass.kwd_attrs.  They never pass through visit_Attribute or
    # visit_Constant, so a class pattern can otherwise recover blocked methods
    # such as str.format and use them to walk generator frames.
    ast.Match,
    ast.Nonlocal,
    ast.Raise,
    ast.Try,
    getattr(ast, "TryStar", ast.Try),
    ast.While,
    ast.Yield,
    ast.YieldFrom,
)

BLOCKED_NAMES = {
    "__builtins__",
    "__import__",
    "breakpoint",
    "compile",
    "delattr",
    "dir",
    "eval",
    "exec",
    "exit",
    "getattr",
    "globals",
    "help",
    "input",
    "locals",
    "memoryview",
    "open",
    "os",
    "pathlib",
    "quit",
    "requests",
    "setattr",
    "shutil",
    "socket",
    "subprocess",
    "sys",
    "vars",
}

BLOCKED_ATTRIBUTES = {
    "connect",
    "download",
    "fromkeys",
    "open",
    "popen",
    "read",
    "read_bytes",
    "read_text",
    "recv",
    "remove",
    "rename",
    "replace",
    "rmdir",
    "send",
    "spawn",
    "system",
    "unlink",
    "upload",
    "write",
    "write_bytes",
    "write_text",
}

BLOCKED_PREFIXES = ("export", "import", "load", "read", "save", "write")

# Interpreter internals: a generator, coroutine, frame, traceback or code
# object leads to frames, and a frame leads to the real built-ins (f_builtins),
# which is a full escape. CAD code never needs them.
BLOCKED_ATTRIBUTE_PREFIXES = ("gi_", "cr_", "ag_", "f_", "tb_", "co_")
# str.format() and format_map() follow attribute paths inside a string
# ("{0.gi_frame}"), which this check cannot see.
BLOCKED_ATTRIBUTES_EXTRA = {"format", "format_map", "mro", "func_globals"}


class CodePolicyError(ValueError):
    pass


class CadCodePolicy(ast.NodeVisitor):
    def __init__(self):
        self.node_count = 0

    def generic_visit(self, node):
        self.node_count += 1
        if self.node_count > MAX_AST_NODES:
            raise CodePolicyError(
                f"Code exceeds the {MAX_AST_NODES}-node complexity limit."
            )
        if isinstance(node, BLOCKED_NODES):
            raise CodePolicyError(f"{type(node).__name__} is not allowed.")
        super().generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if (
            node.id in BLOCKED_NAMES
            or node.id.startswith("__")
            or node.id.lower().startswith(BLOCKED_PREFIXES)
        ):
            raise CodePolicyError(f"Name '{node.id}' is not allowed.")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        if (
            node.attr.startswith("_")
            or node.attr in BLOCKED_ATTRIBUTES
            or node.attr in BLOCKED_ATTRIBUTES_EXTRA
            or node.attr.startswith(BLOCKED_ATTRIBUTE_PREFIXES)
            or node.attr.lower().startswith(BLOCKED_PREFIXES)
        ):
            raise CodePolicyError(f"Attribute '{node.attr}' is not allowed.")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, (str, bytes)) and len(node.value) > MAX_STRING_BYTES:
            raise CodePolicyError(
                f"String literals may not exceed {MAX_STRING_BYTES} bytes."
            )
        # A dunder name in a string reaches the same internals by subscript
        # (f_builtins["__import__"]) or by a later lookup.
        if isinstance(node.value, str) and "__" in node.value:
            raise CodePolicyError("Strings may not contain '__'.")
        if isinstance(node.value, bytes) and b"__" in node.value:
            raise CodePolicyError("Strings may not contain '__'.")
        self.generic_visit(node)


def validate_cad_code(code: str) -> ast.Module:
    if not code.strip():
        raise CodePolicyError("Generated code is empty.")
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise CodePolicyError(f"Code may not exceed {MAX_CODE_BYTES} bytes.")

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as error:
        raise CodePolicyError(f"Invalid Python syntax: {error.msg}.") from error

    CadCodePolicy().visit(tree)

    has_result = any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "result"
            for target in (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
        )
        for node in ast.walk(tree)
    )
    has_build_part = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "BuildPart"
        for node in ast.walk(tree)
    )
    if not has_result and not has_build_part:
        raise CodePolicyError(
            "Code must assign the final shape to 'result' or use BuildPart()."
        )

    return tree
