"""
WasmBox Compiler Pipeline.

Provides the complete Python → WASM compilation pipeline for secure
multi-tenant plugin sandboxing. The pipeline validates, analyzes,
transforms, and packages Python source code into verified WASM artifacts.

Public API:
    compile()        — Compile Python source to a WASM artifact
    validate()       — Validate source without full compilation
    inspect_module() — Inspect an existing WASM artifact

Example:
    from backend.compiler import compile, CompileConfig

    result = compile(
        source='def main(data): return {"value": data["x"] * 2}',
        plugin_name="my_plugin",
        tenant_id="tenant_123",
        config=CompileConfig(),
    )
    assert result.success
"""

from backend.compiler.config import CompileConfig, ExecutionLimits, SecurityPolicy
from backend.compiler.models import CompilationResult, PluginManifest, WasmArtifact
from backend.compiler.pipeline import CompilerPipeline

__version__ = "0.1.0"


def compile(
    source: str,
    plugin_name: str,
    tenant_id: str,
    dependencies: list[str] | None = None,
    config: CompileConfig | None = None,
) -> CompilationResult:
    """Compile Python source code into a WASM plugin artifact.

    Args:
        source: Raw Python source code.
        plugin_name: Identifier for the plugin.
        tenant_id: Tenant identifier for isolation.
        dependencies: Optional list of requested dependencies.
        config: Optional compilation configuration.

    Returns:
        CompilationResult with artifact bytes, manifest, and diagnostics.
    """
    pipeline = CompilerPipeline(config=config or CompileConfig())
    return pipeline.compile(
        source=source,
        plugin_name=plugin_name,
        tenant_id=tenant_id,
        dependencies=dependencies or [],
    )


def validate(source: str, config: CompileConfig | None = None) -> CompilationResult:
    """Validate Python source without full compilation.

    Runs parsing, security validation, and analysis stages only.

    Args:
        source: Raw Python source code.
        config: Optional compilation configuration.

    Returns:
        CompilationResult with diagnostics (no artifact generated).
    """
    pipeline = CompilerPipeline(config=config or CompileConfig())
    return pipeline.validate_only(source=source)


def inspect_module(wasm_bytes: bytes) -> dict:
    """Inspect an existing WASM artifact.

    Args:
        wasm_bytes: Raw WASM binary bytes.

    Returns:
        Dictionary with module info (imports, exports, custom sections, etc.).
    """
    from backend.compiler.wasm_validator import WasmValidator

    validator = WasmValidator()
    return validator.inspect(wasm_bytes)


__all__ = [
    "__version__",
    "compile",
    "validate",
    "inspect_module",
    "CompileConfig",
    "CompilationResult",
    "ExecutionLimits",
    "PluginManifest",
    "SecurityPolicy",
    "WasmArtifact",
    "CompilerPipeline",
]
