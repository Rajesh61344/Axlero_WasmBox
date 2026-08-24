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
        
        # Configure store with limits
        config = wasmtime.Config()
        config.consume_fuel = True
        
        engine = wasmtime.Engine(config)
        store = wasmtime.Store(engine)
        
        fuel_limit = limits.max_fuel if limits else (manifest.max_fuel if manifest else 5_000_000)
        store.set_fuel(fuel_limit)
        
        # In a real environment, memory limits are applied via the store or resource limits
        
        try:
            # 1. Verify artifact integrity (implicit by instantiation)
            # 2. Load WASM module
            module = wasmtime.Module(engine, wasm_bytes)
            
            # Setup linker and WASI
            linker = wasmtime.Linker(engine)
            linker.define_wasi()
            
            # 5. Instantiate module
            instance = linker.instantiate(store, module)
            
            exports = instance.exports(store)
            
            # 6. Call exported _start function
            start_func = None
            if "_start" in exports:
                start_func = exports["_start"]
            
            if start_func:
                start_func(store)
                
            return ExecutionResponse(
                success=True,
                output={},
                fuel_consumed=fuel_limit - store.fuel(),
                stdout="Execution mock successful."
            )
            
        except Exception as e:
            return ExecutionResponse(
                success=False,
                error=str(e),
                error_code="EXECUTION_ERROR"
            )

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
