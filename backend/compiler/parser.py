"""
WasmBox Compiler Parser.

Parses Python source code into an AST and enforces structural and size limits.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from .config import CompilationLimits
from .errors import Diagnostic, ErrorSeverity, ParseError, CompilerStage


@dataclass
class ParseResult:
    """Result of parsing Python source code."""

    tree: ast.Module
    source: str
    filename: str
    lines: list[str]
    diagnostics: list[Diagnostic] = field(default_factory=list)


class PluginParser:
    """Parses plugin source code and applies size limits."""

    def __init__(
        self,
        limits: CompilationLimits | None = None,
        entrypoint_name: str = "main",
    ) -> None:
        """Initialize the parser with compilation limits and entrypoint name."""
        self.limits = limits or CompilationLimits()
        self.entrypoint_name = entrypoint_name

    def parse(self, source: str, filename: str = "<plugin>") -> ParseResult:
        """Parse source code into an AST and check limits.

        Args:
            source: The Python source code to parse.
            filename: The filename to use in error messages.

        Returns:
            ParseResult containing the AST tree and extracted info.

        Raises:
            ParseError: If syntax is invalid or limits are exceeded.
        """
        diagnostics: list[Diagnostic] = []

        if not source:
            raise ParseError("Source code cannot be empty", code="E001")

        try:
            if isinstance(source, bytes):
                source = source.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ParseError(
                f"Source code must be valid UTF-8: {e}",
                code="E002",
            ) from e

        # ---------------------------------------------------------
        # Source size limit
        # ---------------------------------------------------------
        source_bytes = len(source.encode("utf-8"))

        if source_bytes > self.limits.max_source_bytes:
            raise ParseError(
                f"Source size ({source_bytes} bytes) exceeds maximum allowed "
                f"({self.limits.max_source_bytes} bytes)",
                code="E003",
            )

        # ---------------------------------------------------------
        # Source line limit
        # ---------------------------------------------------------
        lines = source.splitlines()

        if len(lines) > self.limits.max_source_lines:
            raise ParseError(
                f"Source length ({len(lines)} lines) exceeds maximum allowed "
                f"({self.limits.max_source_lines} lines)",
                code="E004",
            )

        # ---------------------------------------------------------
        # Python syntax parsing
        # ---------------------------------------------------------
        try:
            tree = ast.parse(source, filename=filename)
        except SyntaxError as e:
            raise ParseError(
                message=str(e.msg),
                line=e.lineno,
                column=e.offset,
                code="E005",
            ) from e

        # ---------------------------------------------------------
        # AST node limit
        # ---------------------------------------------------------
        node_count = sum(1 for _ in ast.walk(tree))

        if node_count > self.limits.max_ast_nodes:
            raise ParseError(
                f"AST node count ({node_count}) exceeds maximum allowed "
                f"({self.limits.max_ast_nodes})",
                code="E006",
            )

        # ---------------------------------------------------------
        # AST nesting depth limit
        # ---------------------------------------------------------
        nesting_depth = self._get_max_depth(tree)

        if nesting_depth > self.limits.max_nesting_depth:
            raise ParseError(
                f"AST nesting depth ({nesting_depth}) exceeds maximum allowed "
                f"({self.limits.max_nesting_depth})",
                code="E007",
            )

        # ---------------------------------------------------------
        # Top-level function and import counts
        # ---------------------------------------------------------
        function_count = sum(
            1
            for node in tree.body
            if isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
        )

        import_count = sum(
            1
            for node in tree.body
            if isinstance(
                node,
                (ast.Import, ast.ImportFrom),
            )
        )

        # ---------------------------------------------------------
        # Import limit
        # ---------------------------------------------------------
        if import_count > self.limits.max_imports:
            raise ParseError(
                f"Import count ({import_count}) exceeds maximum allowed "
                f"({self.limits.max_imports})",
                code="E008",
            )

        # ---------------------------------------------------------
        # Entrypoint detection
        # ---------------------------------------------------------
        has_entrypoint = any(
            isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
            and node.name == self.entrypoint_name
            for node in tree.body
        )

        # ---------------------------------------------------------
        # Parser diagnostics
        # ---------------------------------------------------------
        diagnostics.append(
            Diagnostic(
                code="I001",
                severity=ErrorSeverity.INFO,
                stage=CompilerStage.PARSER,
                message=(
                    f"Parsed {node_count} nodes, "
                    f"{function_count} functions, "
                    f"{import_count} imports."
                ),
            )
        )

        if has_entrypoint:
            diagnostics.append(
                Diagnostic(
                    code="I002",
                    severity=ErrorSeverity.INFO,
                    stage=CompilerStage.PARSER,
                    message=(
                        f"Entrypoint function "
                        f"'{self.entrypoint_name}' found."
                    ),
                )
            )

        return ParseResult(
            tree=tree,
            source=source,
            filename=filename,
            lines=lines,
            diagnostics=diagnostics,
        )

    def _get_max_depth(self, node: ast.AST) -> int:
        """Calculate the maximum nesting depth of an AST node."""
        max_depth = 0

        for child in ast.iter_child_nodes(node):
            max_depth = max(
                max_depth,
                1 + self._get_max_depth(child),
            )

        return max_depth