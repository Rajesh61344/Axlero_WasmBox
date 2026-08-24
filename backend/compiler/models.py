"""
WasmBox Compiler Data Models.

Pydantic models for all structured data flowing through the
compilation pipeline: compilation results, plugin manifests,
WASM artifacts, analysis results, and dependency information.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DependencyCategory(str, Enum):
    """Classification of a Python dependency."""

    STDLIB = "stdlib"
    ALLOWED = "allowed"
    FORBIDDEN = "forbidden"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class DiagnosticSeverity(str, Enum):
    """Severity level for compilation diagnostics."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class DiagnosticModel(BaseModel):
    """Serializable diagnostic message for API responses."""

    code: str
    severity: DiagnosticSeverity
    stage: str
    message: str
    line: int | None = None
    column: int | None = None
    suggestion: str | None = None


class DependencyInfo(BaseModel):
    """Information about a resolved dependency."""

    name: str
    version: str | None = None
    category: DependencyCategory = DependencyCategory.UNKNOWN
    source: str = "builtin"
    hash: str | None = None
    reason: str | None = None


class FunctionInfo(BaseModel):
    """Information about a function found in plugin source."""

    name: str
    line: int
    args: list[str] = Field(default_factory=list)
    decorators: list[str] = Field(default_factory=list)
    is_async: bool = False
    is_entrypoint: bool = False


class ClassInfo(BaseModel):
    """Information about a class found in plugin source."""

    name: str
    line: int
    bases: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)


class ImportInfo(BaseModel):
    """Information about an import statement."""

    module: str
    names: list[str] = Field(default_factory=list)
    alias: str | None = None
    line: int | None = None
    is_from_import: bool = False
    is_star_import: bool = False


class HostFunctionRef(BaseModel):
    """Reference to a host function called in plugin code."""

    name: str
    line: int | None = None
    permissions: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Result of static analysis on plugin source code.

    Contains all information extracted from the source AST including
    imports, function definitions, entrypoints, host function references,
    and potentially dangerous operations.
    """

    imports: list[ImportInfo] = Field(default_factory=list)
    functions: list[FunctionInfo] = Field(default_factory=list)
    classes: list[ClassInfo] = Field(default_factory=list)
    entrypoints: list[str] = Field(default_factory=list)
    host_function_refs: list[HostFunctionRef] = Field(default_factory=list)
    global_variables: list[str] = Field(default_factory=list)
    dangerous_operations: list[str] = Field(default_factory=list)
    dependencies: list[DependencyInfo] = Field(default_factory=list)
    node_count: int = 0
    max_nesting_depth: int = 0
    has_loops: bool = False
    has_recursion: bool = False
    has_class_definitions: bool = False


class PluginManifest(BaseModel):
    """Plugin manifest embedded in every compiled WASM artifact.

    Contains all metadata required by the runtime to safely execute
    the plugin within the Wasmtime sandbox.
    """

    format_version: int = 1
    plugin_name: str
    plugin_id: str = ""
    tenant_id: str = ""
    runtime: str = "wasm"
    python_runtime: str = "embedded"
    entrypoint: str = "main"
    dependencies: list[DependencyInfo] = Field(default_factory=list)
    requested_host_functions: list[str] = Field(default_factory=list)
    memory_limit_bytes: int = 10 * 1024 * 1024
    execution_timeout_ms: int = 50
    max_fuel: int = 5_000_000
    artifact_hash: str = ""
    artifact_size_bytes: int = 0
    compiler_version: str = "0.1.0"
    created_at: str = ""

    # removed model_post_init to allow empty strings for deterministic builds


class WasmArtifact(BaseModel):
    """A compiled WASM artifact ready for runtime execution.

    Contains the raw WASM bytes, integrity hash, size, and metadata
    about the module's imports and exports.
    """

    wasm_bytes: bytes
    sha256: str
    size_bytes: int
    runtime: str = "embedded"
    exports: list[str] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    custom_sections: list[str] = Field(default_factory=list)

    class Config:
        """Pydantic config."""
        # Allow bytes fields
        arbitrary_types_allowed = True


class CompilationMetrics(BaseModel):
    """Timing and size metrics for a compilation run."""

    parse_time_ms: float = 0.0
    validation_time_ms: float = 0.0
    analysis_time_ms: float = 0.0
    transformation_time_ms: float = 0.0
    dependency_time_ms: float = 0.0
    backend_compile_time_ms: float = 0.0
    wasm_validation_time_ms: float = 0.0
    total_time_ms: float = 0.0
    artifact_size_bytes: int = 0
    source_size_bytes: int = 0
    source_lines: int = 0
    cache_hit: bool = False


class CompilationResult(BaseModel):
    """Complete result of a compilation pipeline run.

    Contains the compiled artifact (if successful), manifest,
    diagnostics, and performance metrics.
    """

    success: bool
    plugin_name: str = ""
    plugin_id: str = ""
    tenant_id: str = ""
    artifact_path: str | None = None
    artifact_bytes: bytes | None = None
    artifact_hash: str | None = None
    artifact_size_bytes: int | None = None
    manifest: PluginManifest | None = None
    diagnostics: list[DiagnosticModel] = Field(default_factory=list)
    warnings: list[DiagnosticModel] = Field(default_factory=list)
    errors: list[DiagnosticModel] = Field(default_factory=list)
    metrics: CompilationMetrics = Field(default_factory=CompilationMetrics)

    class Config:
        """Pydantic config."""
        arbitrary_types_allowed = True

    @property
    def has_errors(self) -> bool:
        """Check if there are any error-level diagnostics."""
        return len(self.errors) > 0 or any(d.severity == DiagnosticSeverity.ERROR for d in self.diagnostics)

    @property
    def has_warnings(self) -> bool:
        """Check if there are any warning-level diagnostics."""
        return any(d.severity == DiagnosticSeverity.WARNING for d in self.diagnostics)

    def to_api_response(self) -> dict[str, Any]:
        """Serialize to a JSON-safe API response.

        Excludes raw artifact bytes — those must be retrieved separately.
        """
        result: dict[str, Any] = {
            "success": self.success,
            "plugin_name": self.plugin_name,
            "plugin_id": self.plugin_id,
            "tenant_id": self.tenant_id,
            "artifact_hash": self.artifact_hash,
            "artifact_size_bytes": self.artifact_size_bytes,
            "diagnostics": [d.model_dump() for d in self.diagnostics],
            "metrics": self.metrics.model_dump(),
        }
        if self.manifest:
            result["manifest"] = self.manifest.model_dump(exclude={"artifact_hash"})
        return result


class ExecutionResult(BaseModel):
    """Result of executing a plugin through the runtime.

    Used by integration tests and the runtime adapter.
    """

    success: bool
    output: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0
    fuel_consumed: int | None = None
    memory_used_bytes: int | None = None
    stdout: str = ""
    stderr: str = ""
