"""Syntax-tree metrics. Owner: Track A.

Computes cyclomatic complexity, nesting depth, LOC and the call graph.
Detects test files and maps tests back to the functions they cover.
Flags empty catch blocks, swallowed exceptions, hardcoded secrets.
"""

import re
from collections import defaultdict
from pathlib import Path

from tree_sitter import Node

from ...schemas.repo_map import FunctionNode
from .parser import Definition, _parse, definitions

COMPLEXITY_NODES = {
    "if_statement",
    "elif_clause",
    "for_statement",
    "while_statement",
    "except_clause",
    "conditional_expression",
    "for_in_clause",
    "if_clause",
    "case_clause",
}
NESTING_NODES = {
    "if_statement",
    "for_statement",
    "while_statement",
    "try_statement",
    "with_statement",
    "match_statement",
}
SECRET_NAME = re.compile(r"(?:password|passwd|secret|api_?key|access_?token|private_?key)", re.I)


def _walk_body(root: Node):
    """Yield descendants while excluding nested class/function definitions."""
    stack = list(reversed(root.named_children))
    while stack:
        node = stack.pop()
        if node.type in {"class_definition", "function_definition", "decorated_definition"}:
            continue
        yield node
        stack.extend(reversed(node.named_children))


def _walk_all(root: Node):
    stack = list(reversed(root.named_children))
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.named_children))


def _complexity(definition: Definition) -> int:
    score = 1
    for node in _walk_body(definition.node):
        if node.type in COMPLEXITY_NODES:
            score += 1
        elif node.type == "boolean_operator":
            score += 1
    return score


def _nesting_depth(definition: Definition) -> int:
    maximum = 0

    def visit(node: Node, depth: int) -> None:
        nonlocal maximum
        for child in node.named_children:
            if child.type in {"class_definition", "function_definition", "decorated_definition"}:
                continue
            child_depth = depth + 1 if child.type in NESTING_NODES else depth
            maximum = max(maximum, child_depth)
            visit(child, child_depth)

    visit(definition.node, 0)
    return maximum


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _call_name(node: Node, source: bytes) -> str | None:
    function = node.child_by_field_name("function")
    if function is None:
        return None
    if function.type == "identifier":
        return _text(function, source)
    if function.type == "attribute":
        attribute = function.child_by_field_name("attribute")
        return _text(attribute, source) if attribute is not None else None
    return None


def _calls(definition: Definition, source: bytes) -> list[str]:
    names = {
        name
        for node in _walk_body(definition.node)
        if node.type == "call" and (name := _call_name(node, source)) is not None
    }
    return sorted(names)


def _is_test_path(path: str) -> bool:
    rel = Path(path)
    return rel.name.startswith("test_") or rel.name.endswith("_test.py") or "tests" in rel.parts


def enrich(root: Path, functions: list[FunctionNode]) -> list[FunctionNode]:
    """Fills complexity, nesting_depth, calls and has_test in place."""
    by_file: dict[str, list[FunctionNode]] = defaultdict(list)
    for function in functions:
        by_file[function.file].append(function)

    test_calls: set[str] = set()
    for rel_path, file_functions in by_file.items():
        source, tree = _parse(root, rel_path)
        parsed = definitions(source, tree)
        parsed_by_key = {
            (definition.name, definition.start_line, definition.end_line): definition
            for definition in parsed
        }

        for function in file_functions:
            definition = parsed_by_key.get((function.name, function.lines[0], function.lines[1]))
            if definition is None:
                continue
            function.complexity = _complexity(definition)
            function.nesting_depth = _nesting_depth(definition)
            function.calls = _calls(definition, source)
            function.has_test = _is_test_path(rel_path)
            if function.has_test:
                test_calls.update(function.calls)

    for function in functions:
        simple_name = function.name.rsplit(".", 1)[-1]
        if simple_name in test_calls:
            function.has_test = True
    return functions


def _except_body(node: Node) -> Node | None:
    return next((child for child in node.named_children if child.type == "block"), None)


def _is_pass_only(body: Node | None) -> bool:
    return body is not None and len(body.named_children) == 1 and body.named_children[0].type == "pass_statement"


def _swallows_exception(body: Node | None, source: bytes) -> bool:
    if body is None:
        return True
    descendants = [body, *_walk_body(body)]
    if any(node.type == "raise_statement" for node in descendants):
        return False
    if _is_pass_only(body):
        return True
    return any(
        node.type == "return_statement" and _text(node, source).strip() in {"return", "return None"}
        for node in descendants
    )


def _secret_assignment(node: Node, source: bytes) -> bool:
    if node.type not in {"assignment", "augmented_assignment"}:
        return False
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    if left is None or right is None or right.type not in {"string", "concatenated_string"}:
        return False
    name = _text(left, source)
    value = _text(right, source).strip("\"'").strip()
    return bool(SECRET_NAME.search(name) and value)


def smell_flags(root: Path, rel_path: str) -> list[dict]:
    """Empty catches, swallowed exceptions, hardcoded secrets -- with line numbers."""
    source, tree = _parse(root, rel_path)
    flags: list[dict] = []
    for node in [tree.root_node, *_walk_all(tree.root_node)]:
        line = node.start_point.row + 1
        if node.type == "except_clause":
            body = _except_body(node)
            if _is_pass_only(body):
                flags.append({
                    "type": "empty_catch",
                    "file": Path(rel_path).as_posix(),
                    "line": line,
                    "detail": "Exception handler contains only pass",
                })
            if _swallows_exception(body, source):
                flags.append({
                    "type": "swallowed_exception",
                    "file": Path(rel_path).as_posix(),
                    "line": line,
                    "detail": "Exception handler exits without re-raising",
                })
        elif _secret_assignment(node, source):
            flags.append({
                "type": "hardcoded_secret",
                "file": Path(rel_path).as_posix(),
                "line": line,
                "detail": "Secret-like variable is assigned a string literal",
            })
    return flags
