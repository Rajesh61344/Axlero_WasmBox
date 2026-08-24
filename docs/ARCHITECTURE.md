# WasmBox Compiler Architecture

## System Overview

WasmBox is a secure multi-tenant plugin sandbox that allows enterprise customers to write custom Python plugins executed safely within WebAssembly (WASM) isolation.

```text
                      ┌───────────────────────────────────┐
                      │        SaaS Application           │
                      │   (Role 4: React Frontend)        │
                      └────────────────┬──────────────────┘
                                       │ API
                                       ▼
                      ┌───────────────────────────────────┐
                      │        Backend API Layer           │
                      │   POST /api/plugins/compile        │
                      │   POST /api/plugins/validate       │
                      └────────────────┬──────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     ROLE 3: COMPILER PIPELINE                        │
│                                                                      │
│  Python Source ──► Parser ──► Validator ──► Analyzer ──►             │
│  Transformer ──► Dependencies ──► WASM Backend ──► WASM Validator    │
│                                                                      │
│  Output: Verified WASM Artifact + Manifest                          │
└────────────────────────────────────┬─────────────────────────────────┘
                                     │
                                     ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     ROLE 2: WASMTIME RUNTIME                         │
│                                                                      │
│  WASM Artifact ──► Validation ──► Instantiation ──► Execution       │
│                                                                      │
│  Enforces: Fuel limits, Memory limits, Capability isolation          │
└──────────────────────────────────────────────────────────────────────┘
```

## Component Diagram

```text
backend/
├── compiler/                    # Core compiler pipeline
│   ├── __init__.py              # Public API: compile(), validate(), inspect_module()
│   ├── config.py                # SecurityPolicy, ExecutionLimits, CompileConfig
│   ├── models.py                # Pydantic models: CompilationResult, PluginManifest, etc.
│   ├── errors.py                # Error hierarchy with structured diagnostics
│   ├── parser.py                # Python AST parsing with source validation
│   ├── validator.py             # Security validation (forbidden imports, builtins, etc.)
│   ├── analyzer.py              # Static analysis (imports, functions, host calls)
│   ├── transformer.py           # Source transformation (metadata injection, host bridge)
│   ├── dependencies.py          # Dependency classification and resolution
│   ├── packager.py              # WASM artifact packaging
│   ├── wasm_builder.py          # Low-level WASM binary construction (pure Python)
│   ├── wasm_validator.py        # WASM structural and policy validation
│   ├── manifest.py              # Plugin manifest generation and validation
│   ├── artifacts.py             # Content-addressable artifact storage
│   ├── cache.py                 # Compilation cache with tenant isolation
│   ├── pipeline.py              # Main orchestrator chaining all stages
│   ├── cli.py                   # Command-line interface
│   └── backends/                # Pluggable WASM generation backends
│       ├── base.py              # Abstract WasmCompilerBackend
│       ├── embedded.py          # Primary: packages Python in WASM custom sections
│       └── micropython.py       # MicroPython WASI runtime backend
├── integration/                 # Role 2/3 interface
│   ├── runtime_contract.py      # Protocol definitions for runtime interaction
│   ├── runtime_adapter.py       # Wasmtime adapter for integration testing
│   └── host_functions.py        # Host function registry and declaration
└── api/                         # FastAPI endpoints
    └── compiler_routes.py       # REST API for compilation and validation
```

## Data Flow

```text
                         User Python Source Code
                                  │
                    ┌─────────────▼─────────────┐
                    │         Parser             │
                    │  ast.parse() + validation  │
                    │  Source size / depth limits │
                    └─────────────┬─────────────┘
                                  │ ParseResult (AST + diagnostics)
                    ┌─────────────▼─────────────┐
                    │    Security Validator       │
                    │  Forbidden imports check    │
                    │  Dangerous builtins check   │
                    │  Dynamic import detection   │
                    │  Dunder access detection    │
                    └─────────────┬─────────────┘
                                  │ list[Diagnostic]
                    ┌─────────────▼─────────────┐
                    │     Static Analyzer        │
                    │  Import extraction          │
                    │  Function/class detection   │
                    │  Entrypoint validation       │
                    │  Host function refs          │
                    │  Complexity metrics          │
                    └─────────────┬─────────────┘
                                  │ AnalysisResult
                    ┌─────────────▼─────────────┐
                    │      Transformer           │
                    │  Metadata injection         │
                    │  Host bridge injection      │
                    │  Entrypoint wrapping        │
                    │  Source normalization        │
                    └─────────────┬─────────────┘
                                  │ TransformResult
                    ┌─────────────▼─────────────┐
                    │  Dependency Manager         │
                    │  Classify: stdlib/allowed/  │
                    │    forbidden/unsupported    │
                    │  Generate dependency lock   │
                    └─────────────┬─────────────┘
                                  │ DependencyResult
                    ┌─────────────▼─────────────┐
                    │     WASM Backend            │
                    │  Build valid WASM binary    │
                    │  Embed source in custom     │
                    │    sections                 │
                    │  Embed manifest JSON        │
                    └─────────────┬─────────────┘
                                  │ WasmArtifact
                    ┌─────────────▼─────────────┐
                    │     WASM Validator          │
                    │  Header validation          │
                    │  Structural validation      │
                    │  Import/export policy       │
                    │  wasmtime.Module.validate() │
                    └─────────────┬─────────────┘
                                  │ Verified WasmArtifact
                    ┌─────────────▼─────────────┐
                    │    Artifact Manager         │
                    │  Content-addressed storage  │
                    │  Tenant-isolated paths      │
                    │  SHA-256 integrity          │
                    └─────────────┬─────────────┘
                                  │
                                  ▼
                          plugin.wasm + manifest.json
                                  │
                                  ▼
                    ┌─────────────────────────────┐
                    │   Role 2: Wasmtime Runtime   │
                    └─────────────────────────────┘
```

## WASM Artifact Format

Each compiled plugin is a **genuinely valid WebAssembly module** that can be loaded, validated, and inspected by any WASM-compliant runtime.

### Binary Structure

```text
┌──────────────────────────────────┐
│  WASM Magic: \x00asm             │  4 bytes
│  WASM Version: 1                 │  4 bytes
├──────────────────────────────────┤
│  Type Section (ID 1)             │  Function signatures
│  Function Section (ID 3)         │  Function declarations
│  Memory Section (ID 5)           │  Linear memory config
│  Export Section (ID 7)           │  _start, memory
│  Code Section (ID 10)            │  Minimal function body
├──────────────────────────────────┤
│  Custom Section: wasmbox_source  │  UTF-8 Python source
│  Custom Section: wasmbox_manifest│  JSON manifest
│  Custom Section: wasmbox_metadata│  Build metadata
└──────────────────────────────────┘
```

### Execution Model

> **Important Technical Reality**: Python source code is NOT compiled directly into native WASM instructions. The compiler pipeline **validates, analyzes, transforms, and packages** Python source into a WASM artifact that embeds the source alongside metadata. A pre-compiled Python WASM runtime (e.g., MicroPython compiled to WASI) executes the embedded source at runtime.

The execution flow is:

1. Wasmtime loads the plugin `.wasm` module
2. Runtime extracts the `wasmbox_source` and `wasmbox_manifest` custom sections
3. A pre-compiled MicroPython WASM runtime is loaded
4. The plugin source is passed to MicroPython for execution
5. Resource limits (fuel, memory, time) are enforced by Wasmtime

## Security Architecture

Security is implemented as **defense in depth** — multiple independent layers:

```text
Layer 1: Compiler Validation (Role 3)
  ├── AST-level security checks
  ├── Forbidden import detection
  ├── Dangerous builtin detection
  └── Dependency allowlisting

Layer 2: WASM Module Validation (Role 3)
  ├── Import/export policy enforcement
  ├── Memory configuration limits
  └── Structural integrity checks

Layer 3: Wasmtime Sandbox (Role 2)
  ├── No filesystem capability
  ├── No network capability
  ├── Fuel-based CPU limits
  ├── Memory page limits
  └── Epoch-based timeouts

Layer 4: Host Function Permissions
  ├── Explicit allowlisting per tenant
  ├── Permission-based access control
  └── No dynamic function discovery
```

> **Static validation is defense in depth. The WASM runtime is the primary execution isolation boundary.**

## Tenant Isolation

Every artifact carries tenant identity through metadata:

- Artifact storage is tenant-isolated: `artifacts/<tenant_id>/<plugin_id>/`
- Compilation cache is tenant-isolated: `.wasmbox_cache/<tenant_id>/`
- Host function permissions are per-tenant
- Tenant ID is never trusted from plugin source
- Path traversal is prevented on all filesystem operations
