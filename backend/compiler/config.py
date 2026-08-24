"""
WasmBox Compiler Configuration.

Provides all configurable parameters for the compilation pipeline,
security policy, execution limits, and compiler environment detection.

All security-sensitive defaults are restrictive (deny by default).
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WasmBackendType(str, Enum):
    """Available WASM compilation backends."""

    EMBEDDED = "embedded"
    MICROPYTHON = "micropython"
    WASI_PYTHON = "wasi_python"


# ---------------------------------------------------------------------------
# Standard library modules safe for plugin use in MicroPython / sandboxed env
# ---------------------------------------------------------------------------
DEFAULT_STDLIB_ALLOWLIST: frozenset[str] = frozenset({
    "json",
    "math",
    "re",
    "string",
    "collections",
    "functools",
    "itertools",
    "operator",
    "decimal",
    "fractions",
    "random",
    "hashlib",
    "hmac",
    "base64",
    "binascii",
    "struct",
    "copy",
    "enum",
    "dataclasses",
    "datetime",
    "calendar",
    "bisect",
    "heapq",
    "array",
    "types",
    "abc",
    "contextlib",
    "textwrap",
    "difflib",
    "pprint",
    "io",
    "uuid",
})

# ---------------------------------------------------------------------------
# Modules that are always forbidden (OS/network/process interaction)
# ---------------------------------------------------------------------------
DEFAULT_FORBIDDEN_MODULES: frozenset[str] = frozenset({
    "os",
    "sys",
    "subprocess",
    "socket",
    "http",
    "urllib",
    "requests",
    "ftplib",
    "smtplib",
    "poplib",
    "imaplib",
    "telnetlib",
    "xmlrpc",
    "ctypes",
    "multiprocessing",
    "threading",
    "signal",
    "resource",
    "shutil",
    "tempfile",
    "glob",
    "fnmatch",
    "pathlib",
    "importlib",
    "runpy",
    "code",
    "codeop",
    "compile",
    "compileall",
    "py_compile",
    "pickle",
    "shelve",
    "marshal",
    "dbm",
    "sqlite3",
    "ssl",
    "asyncio",
    "concurrent",
    "select",
    "selectors",
    "mmap",
    "fcntl",
    "termios",
    "tty",
    "pty",
    "pwd",
    "grp",
    "syslog",
    "platform",
    "webbrowser",
    "cmd",
    "readline",
    "rlcompleter",
    "builtins",
    "_thread",
    "_io",
    "_socket",
    "_ssl",
    "_subprocess",
})

# ---------------------------------------------------------------------------
# Built-in functions/names that are dangerous in a sandbox
# ---------------------------------------------------------------------------
DEFAULT_FORBIDDEN_BUILTINS: frozenset[str] = frozenset({
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "input",
    "breakpoint",
    "exit",
    "quit",
})

DEFAULT_RESTRICTED_BUILTINS: frozenset[str] = frozenset({
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
    "dir",
    "type",
    "isinstance",
    "issubclass",
    "super",
    "classmethod",
    "staticmethod",
    "property",
})

# ---------------------------------------------------------------------------
# Dangerous attribute access patterns
# ---------------------------------------------------------------------------
DEFAULT_FORBIDDEN_ATTRIBUTES: frozenset[str] = frozenset({
    "__import__",
    "__builtins__",
    "__subclasses__",
    "__bases__",
    "__mro__",
    "__class__",
    "__globals__",
    "__code__",
    "__func__",
    "__self__",
    "__dict__",
    "__module__",
    "__qualname__",
})


@dataclass(frozen=True)
class SecurityPolicy:
    """Configurable security policy for the compiler validator.

    Controls which Python features are allowed in plugin source code.
    Defaults are restrictive — everything dangerous is denied unless
    explicitly allowed.
    """

    # Module-level controls
    allowed_modules: frozenset[str] = DEFAULT_STDLIB_ALLOWLIST
    forbidden_modules: frozenset[str] = DEFAULT_FORBIDDEN_MODULES

    # Built-in function controls
    forbidden_builtins: frozenset[str] = DEFAULT_FORBIDDEN_BUILTINS
    restricted_builtins: frozenset[str] = DEFAULT_RESTRICTED_BUILTINS

    # Dangerous attribute access
    forbidden_attributes: frozenset[str] = DEFAULT_FORBIDDEN_ATTRIBUTES

    # Feature flags
    allow_eval: bool = False
    allow_exec: bool = False
    allow_compile: bool = False
    allow_file_io: bool = False
    allow_network: bool = False
    allow_subprocess: bool = False
    allow_dynamic_imports: bool = False
    allow_star_imports: bool = False
    allow_dunder_access: bool = False
    allow_class_definitions: bool = True
    allow_decorators: bool = True
    allow_async: bool = False
    allow_global_statement: bool = False

    # Severity for restricted builtins (warn vs reject)
    restricted_builtins_severity: str = "warning"


@dataclass(frozen=True)
class ExecutionLimits:
    """Resource limits for plugin execution.

    These limits are embedded in the plugin manifest and enforced
    by the Wasmtime runtime (Role 2).
    """

    timeout_ms: int = 50
    memory_limit_bytes: int = 10 * 1024 * 1024  # 10 MiB
    max_fuel: int = 2_000_000_000  # Wasmtime fuel units
    max_memory_pages: int = 160  # 160 × 64 KiB = 10 MiB
    max_tables: int = 1
    max_instances: int = 1
    max_table_elements: int = 1000


@dataclass(frozen=True)
class CompilationLimits:
    """Resource limits for the compiler itself to prevent DoS during compilation."""

    max_source_bytes: int = 256 * 1024  # 256 KiB
    max_source_lines: int = 10_000
    max_ast_nodes: int = 50_000
    max_imports: int = 50
    max_dependencies: int = 20
    max_functions: int = 200
    max_classes: int = 50
    max_nesting_depth: int = 20
    max_artifact_size_bytes: int = 50 * 1024 * 1024  # 50 MiB
    max_compile_time_seconds: float = 30.0


@dataclass
class CompileConfig:
    """Top-level compilation configuration.

    Aggregates security policy, execution limits, compilation limits,
    and backend selection.
    """

    # Backend selection
    backend: WasmBackendType = WasmBackendType.WASI_PYTHON

    # Sub-configs
    security_policy: SecurityPolicy = field(default_factory=SecurityPolicy)
    execution_limits: ExecutionLimits = field(default_factory=ExecutionLimits)
    compilation_limits: CompilationLimits = field(default_factory=CompilationLimits)

    # Entrypoint configuration
    entrypoint_function: str = "main"
    required_entrypoint: bool = True

    # Artifact settings
    artifact_dir: str = "artifacts"
    enable_cache: bool = True
    cache_dir: str = ".wasmbox_cache"

    # Debugging
    include_source_in_artifact: bool = True
    include_debug_info: bool = False
    deterministic_builds: bool = True

    # Compiler metadata
    compiler_version: str = "0.1.0"

    def to_cache_key_parts(self) -> dict[str, Any]:
        """Extract configuration values that affect compilation output.

        Used to compute the cache key — if any of these change,
        the cached artifact is invalidated.
        """
        return {
            "backend": self.backend.value,
            "compiler_version": self.compiler_version,
            "security_policy_hash": hash(self.security_policy),
            "execution_limits_hash": hash(self.execution_limits),
            "entrypoint_function": self.entrypoint_function,
            "include_source": self.include_source_in_artifact,
        }


@dataclass
class CompilerEnvironment:
    """Compiler environment detection and diagnostics.

    Detects available tooling, runtimes, and reports diagnostics.
    """

    python_version: str = ""
    wasmtime_available: bool = False
    wasmtime_version: str = ""
    micropython_wasm_available: bool = False
    wasm_backend: str = ""
    platform: str = ""

    @classmethod
    def detect(cls) -> CompilerEnvironment:
        """Detect the current compiler environment."""
        env = cls()

        # Python version
        env.python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        env.platform = sys.platform

        # Wasmtime Python package
        try:
            import wasmtime
            env.wasmtime_available = True
            env.wasmtime_version = getattr(wasmtime, "__version__", "unknown")
        except ImportError:
            env.wasmtime_available = False

        # MicroPython WASM runtime
        try:
            import micropython_wasm  # noqa: F401
            env.micropython_wasm_available = True
        except ImportError:
            env.micropython_wasm_available = False

        # Default backend
        env.wasm_backend = WasmBackendType.EMBEDDED.value

        return env

    def format_diagnostics(self) -> str:
        """Format environment diagnostics as a human-readable string."""
        lines = [
            "WasmBox Compiler Environment",
            "=" * 40,
            f"  Python:              {self.python_version}",
            f"  Platform:            {self.platform}",
            f"  Wasmtime:            {'available (' + self.wasmtime_version + ')' if self.wasmtime_available else 'NOT FOUND'}",
            f"  MicroPython WASM:    {'available' if self.micropython_wasm_available else 'not installed (optional)'}",
            f"  WASM Backend:        {self.wasm_backend}",
            f"  WASM Target:         wasm32",
        ]

        if not self.wasmtime_available:
            lines.extend([
                "",
                "WARNING: wasmtime Python package is not installed.",
                "  Install with: pip install wasmtime",
                "  WASM validation will use structural checks only.",
            ])

        return "\n".join(lines)

    def validate(self) -> list[str]:
        """Validate the environment and return a list of issues."""
        issues: list[str] = []

        if sys.version_info < (3, 11):
            issues.append(
                f"Python 3.11+ required, found {self.python_version}"
            )

        if not self.wasmtime_available:
            issues.append(
                "wasmtime package not installed. Install with: pip install wasmtime"
            )

        return issues
