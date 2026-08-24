# WasmBox Compiler Pipeline

## Overview

The WasmBox compiler pipeline transforms untrusted Python source code into verified WebAssembly (WASM) artifacts for execution in a sandboxed environment. The pipeline implements rigorous validation, analysis, and packaging to ensure that only safe, well-formed plugins reach the runtime.

## Quick Start

### Installation

```bash
pip install -e ".[all]"
```

### Compile a Plugin

```bash
# CLI
python -m backend.compiler.cli compile examples/plugins/hello.py

# Python API
from backend.compiler import compile

result = compile(
    source='def main(data): return {"value": data["x"] * 2}',
    plugin_name="my_plugin",
    tenant_id="tenant_123",
)
assert result.success
print(f"Artifact: {result.artifact_hash} ({result.artifact_size_bytes} bytes)")
```

### Validate Source Only

```bash
python -m backend.compiler.cli validate source.py
```

```python
from backend.compiler import validate

result = validate(source='import os\ndef main(data): os.system("rm -rf /")')
assert not result.success
for diag in result.diagnostics:
    print(diag)
```

### Inspect a WASM Artifact

```bash
python -m backend.compiler.cli inspect plugin.wasm
```

## Pipeline Stages

### 1. Parser (`parser.py`)

Parses Python source into an AST using `ast.parse()`.

**Validates:**
- Source size (max 256 KiB by default)
- Line count (max 10,000 lines)
- AST node count (max 50,000 nodes)
- Nesting depth (max 20 levels)
- Syntax correctness

**Reports:** `ParseError` with line/column on syntax failures.

### 2. Security Validator (`validator.py`)

Walks the AST checking for security policy violations.

**Detects:**
- Forbidden module imports (`os`, `socket`, `subprocess`, `ctypes`, etc.)
- Forbidden builtins (`eval`, `exec`, `open`, `__import__`, etc.)
- Dynamic import patterns (`__import__('os')`, `importlib.import_module()`)
- Dangerous attribute access (`__builtins__`, `__subclasses__`, `__globals__`)
- Indirect access patterns (`getattr(mod, 'system')`, `globals()['open']`)
- Star imports (`from os import *`)

**Configurable** via `SecurityPolicy` — each check can be enabled/disabled.

### 3. Static Analyzer (`analyzer.py`)

Extracts structured information from the AST.

**Produces `AnalysisResult` with:**
- All imports (module, names, aliases)
- Function definitions (name, args, decorators, is_async)
- Class definitions (name, bases, methods)
- Entrypoint detection
- Host function references (`host.log`, `host.get_data`)
- Global variables
- Complexity metrics (node count, nesting depth, loops)
- Dependency classification

### 4. Transformer (`transformer.py`)

Applies deterministic transformations to the source.

**Transformations:**
1. Strip shebang and encoding declarations
2. Inject plugin metadata (`__wasmbox_plugin__`, `__wasmbox_version__`)
3. Inject host API bridge (when host functions are used)
4. Wrap entrypoint with error handling
5. Normalize newlines

The transformed source remains valid Python.

### 5. Dependency Manager (`dependencies.py`)

Classifies and resolves plugin dependencies.

**Categories:**
- **STDLIB**: Standard library modules safe for sandboxed use
- **ALLOWED**: Explicitly approved modules from security policy
- **FORBIDDEN**: Modules that violate security policy
- **UNSUPPORTED**: Unknown modules not in any category

**Generates** a dependency lock structure for reproducibility.

### 6. WASM Backend (`backends/`)

Generates the actual WASM binary.

**Available backends:**
- `WasiPythonBackend` (default) — Packages source by appending custom sections to a real, pre-compiled CPython WASI engine (`python.wasm`). This produces a 25MB artifact that Wasmtime can genuinely instantiate and execute using WASI.
- `EmbeddedPythonBackend` — Legacy fallback. Produces a dummy WASM module containing only custom sections.

**Produces** a genuinely executable WASM artifact containing:
- The full CPython runtime compiled to WASM.
- Custom section `wasmbox_source` (Python source)
- Custom section `wasmbox_manifest` (JSON manifest)
- Custom section `wasmbox_metadata` (build info)

### 7. WASM Validator (`wasm_validator.py`)

Validates the generated WASM artifact.

**Checks:**
- WASM header (magic number + version)
- Module size limits
- Structural validity (via `wasmtime.Module.validate()` when available)
- Import policy compliance
- Export requirements
- Manifest extraction and schema validation
- SHA-256 integrity

### 8. Artifact Manager (`artifacts.py`)

Content-addressable storage for compiled artifacts.

**Storage structure:**
```
artifacts/
  <tenant_id>/
    <plugin_id>/
      <artifact_hash>/
        plugin.wasm
        manifest.json
```

**Security:** Path traversal prevention, ID sanitization, tenant isolation.

## Compilation Cache

The compiler supports optional caching.

**Cache key** = SHA-256 of:
- Source code
- Dependencies
- Compiler version
- Security policy
- Runtime configuration

**Tenant-isolated:** One tenant cannot access another's cache.

## Configuration

### CompileConfig

```python
from backend.compiler.config import CompileConfig, SecurityPolicy, ExecutionLimits

config = CompileConfig(
    security_policy=SecurityPolicy(
        allow_eval=False,         # Deny eval()
        allow_file_io=False,      # Deny open()
        allow_network=False,      # Deny socket
    ),
    execution_limits=ExecutionLimits(
        timeout_ms=50,            # Runtime timeout
        memory_limit_bytes=10*1024*1024,  # 10 MiB
        max_fuel=5_000_000,       # Wasmtime fuel
    ),
    backend=WasmBackendType.EMBEDDED,
    entrypoint_function="main",
    enable_cache=True,
    deterministic_builds=True,
)
```

## Error Handling

Every error is structured and serializable:

```python
CompilerError(
    code="ESEC003",
    stage="validation",
    message="Filesystem access is not permitted",
    line=8,
    column=10,
    suggestion="Use an approved WasmBox host function instead.",
)
```

**Error code ranges:**
| Range | Stage |
|-------|-------|
| E001–E099 | Parse errors |
| E100–E199 | Validation errors |
| E200–E299 | Security violations |
| E300–E399 | Dependency errors |
| E400–E499 | Transformation errors |
| E500–E599 | Backend compilation errors |
| E600–E699 | WASM validation errors |
| E700–E799 | Artifact errors |
| E800–E899 | Runtime contract errors |

## Diagnostics

Three severity levels:

```text
ERROR ESEC003: Filesystem access is not permitted
  at line 8, column 10
  Suggestion: Use an approved WasmBox host function instead.

WARNING WDEP001: Package 'json' will increase artifact size
INFO ICMP001: Plugin compiled successfully in 42ms
```

## Deterministic Builds

When `deterministic_builds=True` (default):
- Plugin IDs are derived from hashing (name + tenant + source)
- Timestamps are omitted from artifacts
- JSON is serialized with sorted keys
- Same input → same output
