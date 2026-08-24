"""
WasmBox Runtime Contract.

Defines the exact interface between Role 3 (Compiler Pipeline) and
Role 2 (Wasmtime Runtime). These Protocol classes specify what the
runtime expects to receive from the compiler and what the compiler
can expect from the runtime.

Role 3 provides:
    - WasmArtifact (WASM bytes, hash, manifest)
    - PluginManifest (metadata, limits, permissions)
    - ExecutionLimits (timeout, memory, fuel)

Role 2 consumes:
    - RuntimeArtifact protocol
    - Executes with resource limits
    - Enforces host function permissions
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from backend.compiler.config import ExecutionLimits
from backend.compiler.models import PluginManifest


@runtime_checkable
class RuntimeArtifact(Protocol):
    """Protocol defining what the runtime needs from a compiled artifact.

    Any object implementing this protocol can be passed to the runtime
    for execution.
    """

    @property
    def artifact_bytes(self) -> bytes:
        """Raw WASM binary bytes."""
        ...

    @property
    def manifest(self) -> PluginManifest:
        """Plugin manifest with metadata and limits."""
        ...

    @property
    def artifact_hash(self) -> str:
        """SHA-256 hash of the artifact bytes."""
        ...


@runtime_checkable
class RuntimeExecutor(Protocol):
    """Protocol for the Role 2 runtime executor.

    This protocol defines what the compiler expects the runtime to support.
    Role 2 implements this; Role 3 only references it.
    """

    def execute(
        self,
        artifact: RuntimeArtifact,
        input_data: dict[str, Any],
        limits: ExecutionLimits | None = None,
    ) -> ExecutionResponse:
        """Execute a plugin artifact with the given input data.

        Args:
            artifact: The compiled plugin artifact.
            input_data: Input data to pass to the plugin's entrypoint.
            limits: Optional execution limits (overrides manifest defaults).

        Returns:
            ExecutionResponse with output or error information.
        """
        ...

    def validate_artifact(self, artifact: RuntimeArtifact) -> bool:
        """Validate that an artifact can be safely executed.

        Args:
            artifact: The artifact to validate.

        Returns:
            True if the artifact is valid for execution.
        """
        ...


@dataclass(frozen=True)
class ExecutionResponse:
    """Response from the runtime after executing a plugin.

    Contains execution results, timing, and resource usage.
    """

    success: bool
    output: Any = None
    error: str | None = None
    error_code: str | None = None
    execution_time_ms: float = 0.0
    fuel_consumed: int | None = None
    memory_used_bytes: int | None = None
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        result: dict[str, Any] = {
            "success": self.success,
            "execution_time_ms": self.execution_time_ms,
        }
        if self.output is not None:
            result["output"] = self.output
        if self.error:
            result["error"] = self.error
        if self.error_code:
            result["error_code"] = self.error_code
        if self.fuel_consumed is not None:
            result["fuel_consumed"] = self.fuel_consumed
        if self.memory_used_bytes is not None:
            result["memory_used_bytes"] = self.memory_used_bytes
        if self.stdout:
            result["stdout"] = self.stdout
        if self.stderr:
            result["stderr"] = self.stderr
        return result


@dataclass
class HostFunctionSpec:
    """Specification for a host function available to plugins.

    Defines the name, required permissions, and type signature
    for a function that plugins can call through the host bridge.
    """

    name: str
    permissions: list[str] = field(default_factory=list)
    description: str = ""
    param_types: list[str] = field(default_factory=list)
    return_type: str = "any"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return {
            "name": self.name,
            "permissions": self.permissions,
            "description": self.description,
            "param_types": self.param_types,
            "return_type": self.return_type,
        }


@dataclass
class TenantPolicy:
    """Security policy for a specific tenant.

    Defines which host functions a tenant's plugins are allowed to use.
    """

    tenant_id: str
    allowed_host_functions: set[str] = field(default_factory=set)
    max_plugins: int = 100
    max_artifact_size_bytes: int = 50 * 1024 * 1024
    max_execution_time_ms: int = 5000
    max_memory_bytes: int = 64 * 1024 * 1024
    custom_limits: dict[str, Any] = field(default_factory=dict)

    def is_host_function_allowed(self, function_name: str) -> bool:
        """Check if a host function is allowed for this tenant.

        Args:
            function_name: Name of the host function to check.

        Returns:
            True if the function is in the allowed set.
        """
        return function_name in self.allowed_host_functions

    def validate_host_functions(
        self, requested: list[str]
    ) -> tuple[list[str], list[str]]:
        """Validate a list of requested host functions against tenant policy.

        Args:
            requested: List of host function names requested by the plugin.

        Returns:
            Tuple of (allowed_functions, rejected_functions).
        """
        allowed = [f for f in requested if self.is_host_function_allowed(f)]
        rejected = [f for f in requested if not self.is_host_function_allowed(f)]
        return allowed, rejected


@dataclass(frozen=True)
class RuntimeCapabilities:
    """Describes the capabilities of the Wasmtime runtime.

    Used by the compiler to generate compatible artifacts.
    """

    supports_fuel: bool = True
    supports_epochs: bool = True
    supports_memory_limits: bool = True
    supports_wasi: bool = True
    supports_component_model: bool = False
    max_memory_pages: int = 65536  # 4 GiB
    max_table_elements: int = 100_000
    wasm_version: int = 1
