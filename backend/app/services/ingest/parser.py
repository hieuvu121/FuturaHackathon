"""tree-sitter extraction. Owner: Track A.

Runs over kept files for the target language, extracting every function and
class with its file and line range. No metrics here -- that is metrics.py.
"""

from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Language, Node, Parser, Tree
import tree_sitter_python

from ...schemas.repo_map import FunctionNode

PYTHON_LANGUAGE = Language(tree_sitter_python.language())


@dataclass(frozen=True)
class Definition:
    """A definition plus its stable API-facing name and decorated range."""

    name: str
    node: Node
    start_line: int
    end_line: int


def _source_path(root: Path, rel_path: str) -> Path:
    root = root.resolve()
    path = (root / rel_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Source path escapes repository root: {rel_path}")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _parse(root: Path, rel_path: str) -> tuple[bytes, Tree]:
    source = _source_path(root, rel_path).read_bytes()
    return source, Parser(PYTHON_LANGUAGE).parse(source)


def _node_name(node: Node, source: bytes) -> str:
    name = node.child_by_field_name("name")
    if name is None:
        raise ValueError(f"Definition at line {node.start_point.row + 1} has no name")
    return source[name.start_byte : name.end_byte].decode("utf-8", errors="replace")


def definitions(source: bytes, tree: Tree) -> list[Definition]:
    """Return classes/functions in source order with qualified nested names."""
    found: list[Definition] = []

    def visit(node: Node, scope: tuple[str, ...], decorated_start: int | None = None) -> None:
        if node.type == "decorated_definition":
            target = node.child_by_field_name("definition")
            if target is not None:
                visit(target, scope, node.start_point.row + 1)
            return

        if node.type in {"class_definition", "function_definition"}:
            local_name = _node_name(node, source)
            qualified_name = ".".join((*scope, local_name))
            found.append(
                Definition(
                    name=qualified_name,
                    node=node,
                    start_line=decorated_start or node.start_point.row + 1,
                    end_line=node.end_point.row + 1,
                )
            )
            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.named_children:
                    visit(child, (*scope, local_name))
            return

        for child in node.named_children:
            visit(child, scope)

    visit(tree.root_node, ())
    return found


def parse_file(root: Path, rel_path: str) -> list[FunctionNode]:
    """One file -> its functions, with name/file/lines/loc filled in."""
    source, tree = _parse(root, rel_path)
    normalised_path = Path(rel_path).as_posix()
    return [
        FunctionNode(
            name=definition.name,
            file=normalised_path,
            lines=(definition.start_line, definition.end_line),
            complexity=1,
            loc=definition.end_line - definition.start_line + 1,
        )
        for definition in definitions(source, tree)
    ]
