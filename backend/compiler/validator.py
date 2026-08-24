"""
WasmBox Compiler Validator.

AST security validator that enforces security policies on parsed source code.
"""

from __future__ import annotations

import ast

from .config import SecurityPolicy
from .errors import Diagnostic, ErrorSeverity, SourceLocation, CompilerStage


class SecurityValidator(ast.NodeVisitor):
    """Walks the AST to enforce the security policy."""

    def __init__(self) -> None:
        """Initialize the security validator."""
        self.source: str = ""
        self.policy: SecurityPolicy | None = None
        self.diagnostics: list[Diagnostic] = []

    def validate(self, tree: ast.Module, source: str, policy: SecurityPolicy) -> list[Diagnostic]:
        """Validate the AST against the given security policy.

        Args:
            tree: The parsed AST module.
            source: The original Python source code.
            policy: The security policy to enforce.

        Returns:
            A list of diagnostics representing security violations and warnings.
        """
        self.source = source
        self.policy = policy
        self.diagnostics.clear()
        
        self.visit(tree)
        return self.diagnostics

    def _add_diagnostic(self, node: ast.AST, code: str, message: str, suggestion: str | None = None, severity: ErrorSeverity = ErrorSeverity.ERROR) -> None:
        """Add a diagnostic message."""
        self.diagnostics.append(Diagnostic(
            code=code,
            severity=severity,
            stage=CompilerStage.VALIDATOR,
            message=message,
            location=SourceLocation(
                line=getattr(node, "lineno", None),
                column=getattr(node, "col_offset", None),
            ),
            suggestion=suggestion,
        ))

    def visit_Import(self, node: ast.Import) -> None:
        """Validate standard imports."""
        assert self.policy is not None
        for alias in node.names:
            base_module = alias.name.split('.')[0]
            if base_module in self.policy.forbidden_modules:
                self._add_diagnostic(
                    node,
                    code="E200",
                    message=f"ESEC: Forbidden module import '{alias.name}'",
                    suggestion="Remove this import. This module is restricted in the sandbox."
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Validate from-imports."""
        assert self.policy is not None
        if node.module:
            base_module = node.module.split('.')[0]
            if base_module in self.policy.forbidden_modules:
                self._add_diagnostic(
                    node,
                    code="E200",
                    message=f"ESEC: Forbidden module import '{node.module}'",
                    suggestion="Remove this import. This module is restricted in the sandbox."
                )
                
        for alias in node.names:
            if alias.name == '*':
                if not self.policy.allow_star_imports:
                    self._add_diagnostic(
                        node,
                        code="E202",
                        message="ESEC: Star imports are forbidden",
                        suggestion="Explicitly import the required names instead."
                    )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Validate function calls (builtins, dynamic imports)."""
        assert self.policy is not None
        
        if isinstance(node.func, ast.Name):
            if node.func.id == "__import__" and not self.policy.allow_dynamic_imports:
                self._add_diagnostic(
                    node,
                    code="E203",
                    message="ESEC: Dynamic import using __import__ is forbidden",
                    suggestion="Use static imports instead."
                )
            
            if node.func.id in self.policy.forbidden_builtins:
                self._add_diagnostic(
                    node,
                    code="E201",
                    message=f"ESEC: Forbidden builtin usage '{node.func.id}'",
                    suggestion="Remove this builtin call. It is unsafe in the sandbox."
                )
                
            if node.func.id in self.policy.restricted_builtins:
                sev = ErrorSeverity.WARNING if self.policy.restricted_builtins_severity == "warning" else ErrorSeverity.ERROR
                self._add_diagnostic(
                    node,
                    code="E207",
                    message=f"ESEC: Restricted builtin usage '{node.func.id}'",
                    suggestion="Avoid using this builtin if possible.",
                    severity=sev
                )
                
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "importlib" and node.func.attr == "import_module":
                if not self.policy.allow_dynamic_imports:
                    self._add_diagnostic(
                        node,
                        code="E203",
                        message="ESEC: Dynamic import using importlib is forbidden",
                        suggestion="Use static imports instead."
                    )
                    
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "builtins":
                self._add_diagnostic(
                    node,
                    code="E208",
                    message="ESEC: Indirect dangerous access pattern via builtins",
                    suggestion="Avoid accessing builtins directly."
                )

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Validate attribute accesses (dunders)."""
        assert self.policy is not None
        if node.attr in self.policy.forbidden_attributes:
            code = "E205" if node.attr.startswith("__") and node.attr.endswith("__") else "E204"
            self._add_diagnostic(
                node,
                code=code,
                message=f"ESEC: Dangerous attribute access '{node.attr}'",
                suggestion="Accessing this attribute is forbidden."
            )
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        """Validate global statements."""
        assert self.policy is not None
        if not self.policy.allow_global_statement:
            self._add_diagnostic(
                node,
                code="E206",
                message="ESEC: Global statement is forbidden",
                suggestion="Avoid using global variables to maintain stateless execution."
            )
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Validate globals()['open'] style indirect access."""
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            if node.value.func.id == "globals":
                self._add_diagnostic(
                    node,
                    code="E208",
                    message="ESEC: Indirect dangerous access pattern via globals()",
                    suggestion="Avoid dictionary access on globals()."
                )
        self.generic_visit(node)
