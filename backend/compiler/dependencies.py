"""
WasmBox Compiler Dependency Management.

Resolves, validates, and locks dependencies for a plugin.
Classifies imports against security policies and runtime constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import CompileConfig
from .errors import CompilerStage, DependencyError, Diagnostic, ErrorSeverity
from .models import AnalysisResult, DependencyCategory, DependencyInfo

# Extensive list of Python standard library modules
PYTHON_STDLIB_MODULES: frozenset[str] = frozenset({
    "abc", "argparse", "array", "ast", "asyncio", "base64", "binascii", "bisect", "builtins",
    "calendar", "cmath", "collections", "concurrent", "contextlib", "copy", "csv", "ctypes",
    "dataclasses", "datetime", "decimal", "difflib", "dis", "email", "enum", "fractions",
    "functools", "glob", "hashlib", "heapq", "hmac", "html", "http", "importlib", "inspect",
    "io", "ipaddress", "itertools", "json", "logging", "math", "mmap", "multiprocessing",
    "numbers", "operator", "os", "pathlib", "pickle", "pprint", "queue", "random", "re",
    "secrets", "shutil", "socket", "sqlite3", "ssl", "stat", "string", "struct", "subprocess",
    "sys", "tempfile", "threading", "time", "timeit", "traceback", "types", "typing", "unittest",
    "urllib", "uuid", "warnings", "weakref", "xml", "zipfile", "zlib"
})

# MicroPython has a restricted standard library subset
MICROPYTHON_AVAILABLE_MODULES: frozenset[str] = frozenset({
    "array", "binascii", "builtins", "cmath", "collections", "errno", "gc", "hashlib",
    "heapq", "io", "json", "machine", "math", "micropython", "network", "os", "re", "select",
    "socket", "ssl", "struct", "sys", "time", "uasyncio", "zlib"
})


@dataclass
class DependencyResult:
    """Result of dependency resolution."""

    resolved: list[DependencyInfo] = field(default_factory=list)
    forbidden: list[DependencyInfo] = field(default_factory=list)
    missing: list[DependencyInfo] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    lock_data: dict = field(default_factory=dict)


class DependencyManager:
    """Manages plugin dependencies, checking against policies."""

    def resolve(self, analysis: AnalysisResult, config: CompileConfig) -> DependencyResult:
        """Resolve and validate dependencies found in analysis."""
        result = DependencyResult()

        seen = set()
        for imp in analysis.imports:
            mod_name = imp.module
            if mod_name in seen:
                continue
            seen.add(mod_name)
            
            base_module = mod_name.split(".")[0]

            dep_info = DependencyInfo(
                name=mod_name,
                category=DependencyCategory.UNKNOWN
            )

            # Classify
            if base_module in config.security_policy.forbidden_modules:
                dep_info.category = DependencyCategory.FORBIDDEN
                result.forbidden.append(dep_info)
                result.diagnostics.append(
                    Diagnostic(
                        code="E300",
                        severity=ErrorSeverity.ERROR,
                        stage=CompilerStage.DEPENDENCIES,
                        message=f"Forbidden dependency: '{mod_name}' is not allowed by security policy.",
                        location=None,
                    )
                )
            elif base_module in PYTHON_STDLIB_MODULES:
                dep_info.category = DependencyCategory.STDLIB
                
                # Check runtime availability
                if config.backend.value == "micropython" and base_module not in MICROPYTHON_AVAILABLE_MODULES:
                    dep_info.category = DependencyCategory.UNSUPPORTED
                    result.missing.append(dep_info)
                    result.diagnostics.append(
                        Diagnostic(
                            code="E301",
                            severity=ErrorSeverity.ERROR,
                            stage=CompilerStage.DEPENDENCIES,
                            message=f"Unsupported dependency: '{mod_name}' is not available in MicroPython.",
                        )
                    )
                else:
                    result.resolved.append(dep_info)
            elif base_module in config.security_policy.allowed_modules:
                dep_info.category = DependencyCategory.ALLOWED
                result.resolved.append(dep_info)
            else:
                dep_info.category = DependencyCategory.UNSUPPORTED
                result.forbidden.append(dep_info)
                result.diagnostics.append(
                    Diagnostic(
                        code="E301",
                        severity=ErrorSeverity.ERROR,
                        stage=CompilerStage.DEPENDENCIES,
                        message=f"Unsupported dependency: '{mod_name}' is not known or allowed.",
                    )
                )
                
            # Add size warnings
            if dep_info.category in (DependencyCategory.STDLIB, DependencyCategory.ALLOWED):
                # Simple heuristic warning
                if base_module in ["pandas", "numpy", "scipy"]:
                    result.diagnostics.append(
                        Diagnostic(
                            code="W304",
                            severity=ErrorSeverity.WARNING,
                            stage=CompilerStage.DEPENDENCIES,
                            message=f"Dependency '{mod_name}' may significantly increase artifact size.",
                        )
                    )

        # Check total limits
        if len(result.resolved) > config.compilation_limits.max_dependencies:
            result.diagnostics.append(
                Diagnostic(
                    code="E302",
                    severity=ErrorSeverity.ERROR,
                    stage=CompilerStage.DEPENDENCIES,
                    message=f"Too many dependencies: {len(result.resolved)} exceeds max {config.compilation_limits.max_dependencies}.",
                )
            )

        # Build lock data
        result.lock_data = {
            "dependencies": [
                {
                    "name": dep.name,
                    "category": dep.category.value,
                    "version": dep.version
                }
                for dep in result.resolved
            ],
            "lock_version": 1,
            "resolver_version": "0.1.0"
        }

        return result
