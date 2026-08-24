# WasmBox Runtime Contract

## Overview

This document defines the exact interface between **Role 3 (Compiler Pipeline)** and **Role 2 (Wasmtime Runtime)**. It specifies what the compiler provides and what the runtime consumes.

## Contract Summary

```text
Role 3 Provides                    Role 2 Consumes
─────────────────                   ─────────────────
WasmArtifact                        artifact_bytes (validated WASM)
  ├── wasm_bytes                    manifest (PluginManifest)
  ├── sha256                        artifact_hash (for integrity check)
  └── size_bytes                    execution_limits (from manifest)
                                    requested_host_functions (from manifest)
PluginManifest
  ├── plugin_name
  ├── plugin_id
  ├── tenant_id
  ├── entrypoint
  ├── dependencies
  ├── requested_host_functions
  ├── memory_limit_bytes
  ├── execution_timeout_ms
  ├── max_fuel
  ├── artifact_hash
  └── compiler_version
```

## Protocol Definitions

### RuntimeArtifact

```python
@runtime_checkable
class RuntimeArtifact(Protocol):
    @property
    def artifact_bytes(self) -> bytes: ...

    @property
    def manifest(self) -> PluginManifest: ...

    @property
    def artifact_hash(self) -> str: ...
```

### RuntimeExecutor

```python
@runtime_checkable
class RuntimeExecutor(Protocol):
    def execute(
        self,
        artifact: RuntimeArtifact,
        input_data: dict[str, Any],
        limits: ExecutionLimits | None = None,
    ) -> ExecutionResponse: ...

    def validate_artifact(self, artifact: RuntimeArtifact) -> bool: ...
```

### ExecutionResponse

```python
@dataclass(frozen=True)
class ExecutionResponse:
    success: bool
    output: Any = None
    error: str | None = None
    error_code: str | None = None
    execution_time_ms: float = 0.0
    fuel_consumed: int | None = None
    memory_used_bytes: int | None = None
    stdout: str = ""
    stderr: str = ""
```

## WASM Artifact Format

The compiler produces WASM modules with three custom sections:

| Section Name | Content Type | Description |
|-------------|-------------|-------------|
| `wasmbox_source` | UTF-8 text | Transformed Python source code |
| `wasmbox_manifest` | JSON bytes | Plugin manifest (see below) |
| `wasmbox_metadata` | JSON bytes | Build metadata (compiler version, etc.) |

### Extracting Custom Sections

```python
from backend.compiler.wasm_builder import WasmModuleBuilder

source = WasmModuleBuilder.extract_custom_section(wasm_bytes, "wasmbox_source")
manifest_json = WasmModuleBuilder.extract_custom_section(wasm_bytes, "wasmbox_manifest")
```

## Manifest Schema

```json
{
  "format_version": 1,
  "plugin_name": "customer_formatter",
  "plugin_id": "a1b2c3d4",
  "tenant_id": "tenant_123",
  "runtime": "wasm",
  "python_runtime": "embedded",
  "entrypoint": "main",
  "dependencies": [
    {"name": "json", "category": "stdlib"}
  ],
  "requested_host_functions": ["log", "get_customer_data"],
  "memory_limit_bytes": 10485760,
  "execution_timeout_ms": 50,
  "max_fuel": 5000000,
  "artifact_hash": "sha256:...",
  "artifact_size_bytes": 12345,
  "compiler_version": "0.1.0",
  "created_at": "2024-01-01T00:00:00Z"
}
```

## Runtime Execution Flow

```text
1. Receive WasmArtifact from compiler
2. Verify artifact_hash matches sha256(artifact_bytes)
3. Validate WASM module with wasmtime.Module.validate()
4. Extract wasmbox_manifest custom section
5. Parse PluginManifest from JSON
6. Validate host function permissions against tenant policy
7. Configure Wasmtime Store:
   a. Set fuel: store.set_fuel(manifest.max_fuel)
   b. Set memory limit: store.set_limits(memory_size=manifest.memory_limit_bytes)
8. Load MicroPython WASM runtime
9. Extract wasmbox_source custom section
10. Pass source to MicroPython for execution
11. Capture output and return ExecutionResponse
12. On timeout/fuel exhaustion: return error response
```

## Resource Limits

The manifest specifies default resource limits. The runtime MAY override these with stricter limits but MUST NOT exceed them.

| Limit | Default | Enforcement |
|-------|---------|-------------|
| `execution_timeout_ms` | 50 | Wasmtime epoch interruption |
| `memory_limit_bytes` | 10 MiB | Wasmtime store.set_limits() |
| `max_fuel` | 5,000,000 | Wasmtime store.set_fuel() |
| `max_memory_pages` | 160 | WASM memory section |
| `max_instances` | 1 | Wasmtime store.set_limits() |

## Host Function Integration

### Compiler Side (Role 3)

The compiler extracts host function references from plugin source:

```python
# Plugin source
def main(data):
    host.log("hello")
    customer = host.get_customer_data("123")
```

The manifest includes:
```json
{
  "requested_host_functions": ["log", "get_customer_data"]
}
```

### Runtime Side (Role 2)

The runtime must:
1. Check each requested function against the tenant's policy
2. Reject the plugin if unauthorized functions are requested
3. Bind approved functions as WASM host imports
4. Execute the plugin with the bound functions

```python
# Runtime pseudocode
for func_name in manifest.requested_host_functions:
    if not tenant_policy.is_allowed(func_name):
        return ExecutionResponse(success=False, error=f"HOST_FUNCTION_NOT_ALLOWED: {func_name}")
    linker.define("env", func_name, host_implementations[func_name])
```

## Error Handling

The runtime should catch and report these error categories:

| Error | Cause | Response |
|-------|-------|----------|
| `ARTIFACT_INTEGRITY_ERROR` | Hash mismatch | Reject execution |
| `WASM_VALIDATION_ERROR` | Invalid WASM module | Reject execution |
| `HOST_FUNCTION_NOT_ALLOWED` | Unauthorized host function | Reject execution |
| `FUEL_EXHAUSTED` | Infinite loop / excessive computation | Terminate, return error |
| `MEMORY_LIMIT_EXCEEDED` | Excessive allocation | Terminate, return error |
| `TIMEOUT_EXCEEDED` | Execution too slow | Terminate, return error |
| `RUNTIME_ERROR` | Plugin raised exception | Return error with message |
