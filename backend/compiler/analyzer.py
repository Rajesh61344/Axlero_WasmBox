"""
WasmBox Compiler Analyzer.

Static analysis for Python plugins to extract metadata and resolve dependencies.
"""

from __future__ import annotations

import ast

from .config import CompileConfig
from .models import (
    AnalysisResult,
    ClassInfo,
    DependencyCategory,
    DependencyInfo,
    FunctionInfo,
    HostFunctionRef,
    ImportInfo,
)


class StaticAnalyzer(ast.NodeVisitor):
    """Static analyzer that walks the AST to extract plugin metadata."""

    def __init__(self) -> None:
        """Initialize the static analyzer."""
        self.source: str = ""
        self.config: CompileConfig | None = None
        self.result: AnalysisResult = AnalysisResult()
        self.current_class: str | None = None
        self.module_level: bool = True

    def analyze(
        self,
        tree: ast.Module,
        source: str,
        config: CompileConfig,
    ) -> AnalysisResult:
        """Analyze the AST and return the AnalysisResult.

        Args:
            tree: The parsed AST module.
            source: The original Python source code.
            config: The compilation configuration.

        Returns:
            AnalysisResult containing extracted metadata and dependencies.
        """
        self.source = source
        self.config = config
        self.result = AnalysisResult()

        self.result.max_nesting_depth = self._get_max_depth(tree)
        self.result.node_count = sum(1 for _ in ast.walk(tree))

        self.module_level = True
        self.current_class = None

        self.visit(tree)

        self._validate_compilation_limits()
        self._resolve_dependencies()

        return self.result

    def _get_max_depth(self, node: ast.AST) -> int:
        """Calculate the maximum nesting depth of an AST node."""
        max_depth = 0

        for child in ast.iter_child_nodes(node):
            max_depth = max(
                max_depth,
                1 + self._get_max_depth(child),
            )

        return max_depth

    def _validate_compilation_limits(self) -> None:
        """Validate analyzer results against configured compilation limits."""
        assert self.config is not None

        limits = self.config.compilation_limits

        if len(self.result.functions) > limits.max_functions:
            self.result.dangerous_operations.append(
                "Function count exceeds compilation limit: "
                f"{len(self.result.functions)} > {limits.max_functions}"
            )

        if len(self.result.classes) > limits.max_classes:
            self.result.dangerous_operations.append(
                "Class count exceeds compilation limit: "
                f"{len(self.result.classes)} > {limits.max_classes}"
            )

    def visit_Import(self, node: ast.Import) -> None:
        """Extract standard imports."""
        for alias in node.names:
            self.result.imports.append(
                ImportInfo(
                    module=alias.name,
                    names=[alias.name],
                    alias=alias.asname,
                    line=node.lineno,
                    is_from_import=False,
                    is_star_import=False,
                )
            )

        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Extract from-imports."""
        module_name = node.module or ""
        names = [alias.name for alias in node.names]
        is_star = any(name == "*" for name in names)

        self.result.imports.append(
            ImportInfo(
                module=module_name,
                names=names,
                alias=None,
                line=node.lineno,
                is_from_import=True,
                is_star_import=is_star,
            )
        )

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Extract sync function definitions."""
        self._handle_function(node, is_async=False)

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> None:
        """Extract async function definitions."""
        self._handle_function(node, is_async=True)

    def _handle_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        is_async: bool,
    ) -> None:
        """Extract information about a function."""
        args = [arg.arg for arg in node.args.args]

        decorators = [
            ast.unparse(d) if hasattr(ast, "unparse") else "decorator"
            for d in node.decorator_list
        ]

        assert self.config is not None

        is_entrypoint = node.name == self.config.entrypoint_function

        if is_entrypoint:
            self.result.entrypoints.append(node.name)

        func_info = FunctionInfo(
            name=node.name,
            line=node.lineno,
            args=args,
            decorators=decorators,
            is_async=is_async,
            is_entrypoint=is_entrypoint,
        )

        if self.current_class is None:
            self.result.functions.append(func_info)

        for child in ast.walk(node):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == node.name
            ):
                self.result.has_recursion = True

        was_module_level = self.module_level
        self.module_level = False

        self.generic_visit(node)

        self.module_level = was_module_level

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Extract class definitions."""
        self.result.has_class_definitions = True

        bases = [
            ast.unparse(b) if hasattr(ast, "unparse") else "base"
            for b in node.bases
        ]

        methods: list[str] = []

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(item.name)

        self.result.classes.append(
            ClassInfo(
                name=node.name,
                line=node.lineno,
                bases=bases,
                methods=methods,
            )
        )

        old_class = self.current_class
        was_module_level = self.module_level

        self.current_class = node.name
        self.module_level = False

        self.generic_visit(node)

        self.current_class = old_class
        self.module_level = was_module_level

    def visit_Assign(self, node: ast.Assign) -> None:
        """Extract global variable assignments."""
        if self.module_level:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.result.global_variables.append(target.id)

        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Extract annotated global variable assignments."""
        if (
            self.module_level
            and isinstance(node.target, ast.Name)
        ):
            self.result.global_variables.append(node.target.id)

        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        """Detect for loops."""
        self.result.has_loops = True
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        """Detect async for loops."""
        self.result.has_loops = True
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        """Detect while loops."""
        self.result.has_loops = True
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Detect host function references."""
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "host"
        ):
            self.result.host_function_refs.append(
                HostFunctionRef(
                    name=node.attr,
                    line=node.lineno,
                    permissions=[],
                )
            )

        self.generic_visit(node)

    def _resolve_dependencies(self) -> None:
        """Classify dependencies based on security policy."""
        assert self.config is not None

        policy = self.config.security_policy

        unique_deps: set[str] = set()

        for imp in self.result.imports:
            base_module = (
                imp.module.split(".")[0]
                if imp.module
                else ""
            )

            if not base_module or base_module in unique_deps:
                continue

            unique_deps.add(base_module)

            if base_module in policy.forbidden_modules:
                cat = DependencyCategory.FORBIDDEN

                self.result.dangerous_operations.append(
                    f"Forbidden module import: {base_module}"
                )

            elif base_module in policy.allowed_modules:
                cat = DependencyCategory.STDLIB

            else:
                cat = DependencyCategory.UNSUPPORTED

            self.result.dependencies.append(
                DependencyInfo(
                    name=base_module,
                    category=cat,
                    source="builtin",
                )
            )