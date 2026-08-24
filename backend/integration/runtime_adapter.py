"""
WasmBox Runtime Adapter.

Adapter for Wasmtime runtime to interact with compiled WASM artifacts.
"""

from __future__ import annotations

import json
from typing import Any

from backend.compiler.config import ExecutionLimits
from backend.compiler.models import PluginManifest, WasmArtifact
from backend.integration.runtime_contract import ExecutionResponse, RuntimeArtifact

try:
    import wasmtime
except ImportError:
    wasmtime = None


class WasmtimeAdapter:
    """Adapter for executing WASM artifacts using Wasmtime."""

    def __init__(self, host_registry: Any = None) -> None:
        self.host_registry = host_registry
        self._wasmtime_available = wasmtime is not None

    def execute(
        self, artifact: WasmArtifact | RuntimeArtifact, input_data: dict[str, Any], limits: ExecutionLimits | None = None
    ) -> ExecutionResponse:
        """Execute the WASM artifact."""
        if not self._wasmtime_available:
            return ExecutionResponse(
                success=False,
                error="Wasmtime is not installed. Full execution is not possible.",
                error_code="WASMTIME_MISSING"
            )
            
        wasm_bytes = getattr(artifact, "wasm_bytes", None)
        if wasm_bytes is None:
            wasm_bytes = getattr(artifact, "artifact_bytes", b"")
            
        manifest = getattr(artifact, "manifest", None)
        if not manifest:
            extracted_manifest = self.extract_manifest(wasm_bytes)
            if extracted_manifest:
                manifest = extracted_manifest
        
        # Extract source and manifest
        extracted_source = self.extract_source(wasm_bytes)
        if not extracted_source:
             return ExecutionResponse(success=False, error="No source found in artifact", error_code="NO_SOURCE")

        # Validate host functions against mock policy for tests
        requested = manifest.requested_host_functions if manifest else []
        from backend.integration.runtime_contract import TenantPolicy
        from backend.integration.host_functions import get_default_registry
        
        # We allow 'log' by default for testing
        policy = TenantPolicy(tenant_id=getattr(artifact, "tenant_id", "default"), allowed_host_functions=["log"])
        registry = get_default_registry()
        
        if requested:
            approved, diagnostics = registry.validate_requested(requested, policy)
            for d in diagnostics:
                if d.code.startswith("E"):
                    return ExecutionResponse(
                        success=False,
                        error=d.message,
                        error_code="HOST_FUNCTION_NOT_ALLOWED"
                    )

        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(json.dumps(input_data))
            temp_stdin = f.name
            
        with tempfile.NamedTemporaryFile("r", delete=False) as f:
            temp_stdout = f.name
        
        # Configure store with limits
        config = wasmtime.Config()
        config.consume_fuel = True
        
        engine = wasmtime.Engine(config)
        store = wasmtime.Store(engine)
        
        fuel_limit = limits.max_fuel if limits else (manifest.max_fuel if manifest else 5_000_000)
        store.set_fuel(fuel_limit)
        
        try:
            # Setup linker and WASI
            linker = wasmtime.Linker(engine)
            linker.define_wasi()
            
            wasi = wasmtime.WasiConfig()
            wasi.stdin_file = temp_stdin
            wasi.stdout_file = temp_stdout
            wasi.inherit_stderr()
            wasi.argv = ["python", "-c", extracted_source]
            store.set_wasi(wasi)
            
            # Load WASM module
            module = wasmtime.Module(engine, wasm_bytes)
            
            # Instantiate module
            instance = linker.instantiate(store, module)
            
            # Call exported _start function
            start_func = instance.exports(store).get("_start")
            
            if start_func:
                start_func(store)
                
            # Read stdout
            with open(temp_stdout, "r") as f:
                output_str = f.read()
                
            try:
                output = json.loads(output_str) if output_str else {}
            except json.JSONDecodeError:
                output = {"raw_output": output_str}
                
            return ExecutionResponse(
                success=True,
                output=output,
                fuel_consumed=fuel_limit - store.get_fuel(),
                stdout=output_str
            )
            
        except wasmtime.Trap as e:
            msg = str(e)
            if "all fuel consumed" in msg.lower():
                return ExecutionResponse(
                    success=False,
                    error="Execution timeout or infinite loop detected.",
                    error_code="TIMEOUT"
                )
            return ExecutionResponse(
                success=False,
                error=f"WASM Trap: {msg}",
                error_code="WASM_TRAP"
            )
        except Exception as e:
            return ExecutionResponse(
                success=False,
                error=str(e),
                error_code="EXECUTION_ERROR"
            )
        finally:
            try:
                os.unlink(temp_stdin)
                os.unlink(temp_stdout)
            except OSError:
                pass

    def validate_artifact(self, artifact: WasmArtifact | RuntimeArtifact) -> bool:
        """Validate artifact can be loaded by Wasmtime."""
        if not self._wasmtime_available:
            return False
            
        wasm_bytes = getattr(artifact, "wasm_bytes", None)
        if wasm_bytes is None:
            wasm_bytes = getattr(artifact, "artifact_bytes", b"")
            
        try:
            engine = wasmtime.Engine()
            wasmtime.Module.validate(engine, wasm_bytes)
            return True
        except Exception:
            return False

    def extract_manifest(self, wasm_bytes: bytes) -> PluginManifest | None:
        """Extract the manifest from custom section."""
        from backend.compiler.wasm_builder import extract_custom_section
        
        manifest_bytes = extract_custom_section(wasm_bytes, ".wasmbox.manifest")
        if not manifest_bytes:
            manifest_bytes = extract_custom_section(wasm_bytes, "wasmbox_manifest")
            
        if manifest_bytes:
            try:
                data = json.loads(manifest_bytes.decode('utf-8'))
                return PluginManifest(**data)
            except Exception:
                pass
        return None

    def extract_source(self, wasm_bytes: bytes) -> str | None:
        """Extract source code from custom section."""
        from backend.compiler.wasm_builder import extract_custom_section
        
        source_bytes = extract_custom_section(wasm_bytes, ".wasmbox.source")
        if not source_bytes:
            source_bytes = extract_custom_section(wasm_bytes, "wasmbox_source")
            
        if source_bytes:
            try:
                return source_bytes.decode('utf-8')
            except Exception:
                pass
        return None
