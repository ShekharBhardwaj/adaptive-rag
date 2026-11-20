"""Static source symbols and identifier features; repository code is never executed."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

_WORD = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[0-9]+")
_STOP_WORDS = frozenset(
    "a an and are as at be by can do does for from how i in is it of on or that the "
    "their this to use uses what when where which with would explain find file files "
    "function functions method methods class classes code repository".split()
)
# The fallback identifies declarations textually. It does not parse a language or establish scope.
_DECLARATION = re.compile(
    r"^\s*(?:(?:export|default|public|private|protected|static|async|abstract|pub)\s+)*"
    r"(?:(?P<kind>class|interface|struct|trait|enum|function|fn|def)\s+"
    r"(?P<name>[A-Za-z_$][\w$]*)|"
    r"(?P<variable>const|let|var)\s+(?P<variable_name>[A-Za-z_$][\w$]*)\s*=|"
    r"func\s+(?:\([^)]*\)\s*)?(?P<go_name>[A-Za-z_]\w*)\s*\()"
)


def identifier_terms(text: str, *, drop_stop_words: bool = False) -> tuple[str, ...]:
    """Stable case-insensitive features, retaining whole snake/camel identifiers."""
    terms: set[str] = set()
    for identifier in _WORD.findall(text):
        terms.add(identifier.casefold())
        for section in identifier.split("_"):
            terms.update(part.casefold() for part in _CAMEL.findall(section))
    if drop_stop_words:
        terms.difference_update(_STOP_WORDS)
    return tuple(sorted(terms))


@dataclass(frozen=True)
class SymbolLocation:
    path: str
    name: str
    qualified_name: str
    kind: str
    start_line: int
    end_line: int
    extraction: str


class _PythonSymbols(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.scope: list[str] = []
        self.symbols: list[SymbolLocation] = []

    def _definition(self, node: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.symbols.append(
            SymbolLocation(
                self.path,
                node.name,
                ".".join((*self.scope, node.name)),
                "class" if isinstance(node, ast.ClassDef) else "function",
                node.lineno,
                node.end_lineno or node.lineno,
                "python_ast",
            )
        )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_ClassDef = _definition
    visit_FunctionDef = _definition
    visit_AsyncFunctionDef = _definition


def extract_symbols(path: str, text: str) -> tuple[SymbolLocation, ...]:
    """Extract Python definitions with AST; other declarations are approximate regex matches."""
    if path.endswith((".py", ".pyi")):
        try:
            tree = ast.parse(text, filename=path)
        except (SyntaxError, ValueError, RecursionError):
            pass
        else:
            visitor = _PythonSymbols(path)
            try:
                visitor.visit(tree)
            except RecursionError:
                pass
            else:
                return tuple(sorted(visitor.symbols, key=lambda item: (item.start_line, item.name)))
    symbols = []
    for number, line in enumerate(text.splitlines(), 1):
        match = _DECLARATION.match(line)
        if match is None:
            continue
        name = match.group("name") or match.group("variable_name") or match.group("go_name")
        kind = match.group("kind") or match.group("variable") or "function"
        symbols.append(SymbolLocation(path, name, name, kind, number, number, "regex_approximate"))
    return tuple(symbols)
