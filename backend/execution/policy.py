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
    ast.Nonlocal,
    ast.Raise,
    ast.Try,
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
            or node.attr.lower().startswith(BLOCKED_PREFIXES)
        ):
            raise CodePolicyError(f"Attribute '{node.attr}' is not allowed.")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, (str, bytes)) and len(node.value) > MAX_STRING_BYTES:
            raise CodePolicyError(
                f"String literals may not exceed {MAX_STRING_BYTES} bytes."
            )
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
