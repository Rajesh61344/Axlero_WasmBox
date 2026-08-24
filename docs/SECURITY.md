# WasmBox Security Model

## Threat Model

WasmBox allows enterprise customers to submit arbitrary Python code for execution on the platform backend. This introduces the following threats:

| Threat | Description | Mitigation |
|--------|-------------|------------|
| **Filesystem Access** | Plugin reads/writes host filesystem | Compiler rejects `open()`, WASM sandbox has no FS capability |
| **Network Access** | Plugin opens network connections | Compiler rejects `socket`, WASM sandbox has no network |
| **Process Execution** | Plugin spawns subprocesses | Compiler rejects `subprocess`, WASM sandbox cannot exec |
| **Code Injection** | Plugin uses `eval`/`exec` to run arbitrary code | Compiler rejects `eval`/`exec`, WASM isolates execution |
| **Resource Exhaustion** | Plugin runs infinite loop or allocates excessive memory | Wasmtime fuel limits terminate execution; memory page limits enforced |
| **Data Exfiltration** | Plugin extracts secrets from environment | No env access in WASM; host functions are explicitly gated |
| **Privilege Escalation** | Plugin accesses unauthorized host functions | Host function permissions validated per tenant |
| **Tenant Isolation Breach** | One tenant accesses another's data | Artifact storage, cache, and permissions are tenant-isolated |
| **Compiler DoS** | Malicious source exhausts compiler resources | Source size, AST depth, compile time limits |

## Defense in Depth

> **Static validation is defense in depth. The WASM runtime is the primary execution isolation boundary.**

```text
┌─────────────────────────────────────────────┐
│ Layer 4: Tenant & Permission Policy         │  Organizational
│   • Host function allowlisting per tenant   │
│   • Artifact isolation per tenant           │
├─────────────────────────────────────────────┤
│ Layer 3: Wasmtime Sandbox (PRIMARY)         │  Runtime
│   • No filesystem capability                │
│   • No network capability                   │
│   • Fuel-based CPU limits                   │
│   • Memory page limits                      │
│   • Epoch-based timeouts                    │
├─────────────────────────────────────────────┤
│ Layer 2: WASM Module Validation             │  Binary
│   • Import/export policy enforcement        │
│   • Structural integrity checks             │
│   • SHA-256 artifact hashing                │
├─────────────────────────────────────────────┤
│ Layer 1: Compiler AST Validation            │  Source
│   • Forbidden import detection              │
│   • Dangerous builtin detection             │
│   • Dynamic import pattern detection        │
│   • Dependency allowlisting                 │
└─────────────────────────────────────────────┘
```

## Layer 1: AST Validation

### Forbidden Imports

The following modules are rejected by default:

```python
# Operating System
os, sys, platform, resource, signal

# Process Execution
subprocess, multiprocessing, threading, _thread, concurrent

# Networking
socket, http, urllib, requests, ftplib, smtplib, ssl

# Low-level / Unsafe
ctypes, pickle, marshal, shelve, mmap, fcntl

# Code Execution
importlib, runpy, code, codeop, compile, compileall

# File System
shutil, tempfile, glob, fnmatch, pathlib

# Database
sqlite3, dbm
```

Import forms detected:
```python
import os                      # Direct import
from os import system          # From-import
from socket import *           # Star import
__import__("os")               # Dynamic import
importlib.import_module("os")  # importlib
```

### Forbidden Builtins

```python
eval(...)          # Arbitrary code execution
exec(...)          # Arbitrary code execution
compile(...)       # Code compilation
__import__(...)    # Dynamic module loading
open(...)          # Filesystem access
input(...)         # stdin access
breakpoint()       # Debugger
exit() / quit()    # Process termination
```

### Dangerous Patterns

The validator detects indirect access patterns:

```python
globals()["open"]           # Accessing builtins via globals
getattr(module, "system")   # Dynamic attribute access
builtins.open(...)          # Direct builtins access
obj.__builtins__            # Dunder access to builtins
obj.__subclasses__()        # Class hierarchy traversal
obj.__globals__             # Function globals access
```

### Configurable Policy

All checks are configurable via `SecurityPolicy`:

```python
SecurityPolicy(
    allow_eval=False,            # Never allow eval()
    allow_exec=False,            # Never allow exec()
    allow_file_io=False,         # Never allow open()
    allow_network=False,         # Never allow socket
    allow_subprocess=False,      # Never allow subprocess
    allow_dynamic_imports=False, # Never allow __import__
    allow_star_imports=False,    # Prevent star imports
    allow_dunder_access=False,   # Prevent __dunder__ access
)
```

## Layer 2: WASM Module Validation

### Import Policy

WASM modules may only import from approved modules/names:

```python
AllowedImports = {
    "env": {
        "host_log",
        "host_get_input",
        "host_set_output",
    }
}
```

Any unexpected import causes rejection.

### Export Validation

Required exports are verified (e.g., `_start`, `memory`).

### Artifact Integrity

Every artifact has a SHA-256 hash. At runtime:

```text
artifact → hash verification → WASM validation → execution
```

If the hash doesn't match: `ARTIFACT_INTEGRITY_ERROR`.

## Layer 3: Runtime Sandbox

The Wasmtime runtime enforces hard security boundaries:

### CPU Limits (Fuel)

```python
store.set_fuel(5_000_000)  # Max WASM instructions
```

Infinite loops terminate with: `Execution trapped: fuel exhausted`

### Memory Limits

```python
store.set_limits(memory_size=10 * 1024 * 1024)  # 10 MiB max
```

Memory bombs are terminated with: `Execution trapped: memory limit exceeded`

### Capability Isolation

By default, the WASM sandbox has:
- ❌ No filesystem access
- ❌ No network access
- ❌ No process spawning
- ❌ No environment variables
- ❌ No system clock (unless explicitly provided)
- ✅ Only explicitly provided host functions

## Layer 4: Host Function Permissions

### Declaration

```python
@host_function(name="log", permissions=["logging"])
def host_log(message: str) -> None:
    ...

@host_function(name="get_customer_data", permissions=["customer:read"])
def get_customer_data(customer_id: str) -> dict:
    ...
```

### Tenant Policy

```python
TenantPolicy(
    tenant_id="tenant_123",
    allowed_host_functions={"log", "get_customer_data"},
)
```

### Validation

```text
Plugin requests: log, get_customer_data, delete_database
Tenant allows:   log, get_customer_data
Result:          delete_database → REJECTED (E802)
```

## Compiler Self-Protection

The compiler itself processes untrusted source and protects against:

| Attack | Limit |
|--------|-------|
| Enormous source files | `max_source_bytes` = 256 KiB |
| Deeply nested ASTs | `max_nesting_depth` = 20 |
| Too many imports | `max_imports` = 50 |
| Excessive dependencies | `max_dependencies` = 20 |
| Huge artifacts | `max_artifact_size_bytes` = 50 MiB |
| Slow compilation | `max_compile_time_seconds` = 30s |

## What This Security Model Does NOT Guarantee

1. **The AST validator cannot catch all malicious code.** It is defense in depth, not the primary security boundary.
2. **Obfuscated code may bypass static analysis.** The WASM runtime is the real security guarantee.
3. **Native CPython extensions are not supported.** Only pure-Python code works in the sandbox.
4. **Network access is intentionally unavailable.** Plugins communicate only through host functions.
5. **Full CPython compatibility is not guaranteed.** The sandbox runtime (MicroPython) has a reduced standard library.

## Security Incident Response

If a security bypass is discovered:

1. Immediately disable the affected tenant's plugins
2. Audit artifact storage for compromised artifacts
3. Invalidate the compilation cache
4. Update the security policy
5. Re-compile all affected plugins with updated validation
6. Review Wasmtime configuration for capability leaks
