# WasmBox — Secure Multi-Tenant Plugin Sandbox

> A Python-to-WASM compilation pipeline for secure, isolated plugin execution.

## Architecture

WasmBox allows enterprise SaaS customers to write custom Python plugins that execute safely within WebAssembly (WASM) sandboxes. The system provides:

- **Compiler Pipeline** — Validates, analyzes, transforms, and packages Python source into WASM artifacts
- **Wasmtime Runtime** — Executes WASM artifacts with strict resource limits and capability isolation
- **Host Functions** — Explicitly whitelisted functions that plugins can call through the sandbox boundary
- **Tenant Isolation** — Every artifact, cache entry, and permission is scoped to a tenant

```text
User Python Code → Compiler Pipeline → plugin.wasm → Wasmtime Sandbox → Isolated Execution
```

## Quick Start

```bash
# Install
pip install -e ".[all]"

# Compile a plugin
python -m backend.compiler.cli compile examples/plugins/hello.py

# Check environment
python -m backend.compiler.cli env

# Run tests
make test
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — System overview, component diagram, data flow
- [Compiler](docs/COMPILER.md) — Pipeline stages, configuration, error handling
- [Security](docs/SECURITY.md) — Threat model, defense in depth, capability isolation
- [Runtime Contract](docs/RUNTIME_CONTRACT.md) — Interface between compiler and runtime

## Project Structure

```
backend/
├── compiler/          # Core compilation pipeline
│   ├── parser.py      # Python AST parsing
│   ├── validator.py   # Security validation
│   ├── analyzer.py    # Static analysis
│   ├── transformer.py # Source transformation
│   ├── dependencies.py # Dependency resolution
│   ├── pipeline.py    # Pipeline orchestrator
│   ├── wasm_builder.py # WASM binary construction
│   ├── packager.py    # Artifact packaging
│   └── backends/      # Pluggable WASM backends
├── integration/       # Runtime interface
│   ├── runtime_contract.py
│   ├── runtime_adapter.py
│   └── host_functions.py
└── api/               # REST API endpoints
    └── compiler_routes.py

tests/                 # Comprehensive test suite
examples/plugins/      # Example plugins (safe + malicious)
docs/                  # Documentation
```

## License

MIT
