"""
WasmBox Compiler WASI Python Backend.

Packages the plugin source code by appending it as custom sections
to a real, pre-compiled CPython WASI engine (python.wasm).
This creates a self-contained, genuinely executable WASM artifact
that Wasmtime can instantiate directly.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from ..config import CompileConfig
from ..errors import BackendCompilationError
from ..models import PluginManifest, WasmArtifact
from ..wasm_builder import WasmModuleBuilder
from .base import WasmCompilerBackend


class WasiPythonBackend(WasmCompilerBackend):
    """WASI CPython WASM compiler backend."""

    def __init__(self):
        # Locate the pre-compiled python.wasm engine
        self.engine_path = Path(__file__).parent / "python.wasm"

    @property
    def name(self) -> str:
        return "wasi_python"

    def compile(self, source: str, manifest: PluginManifest, config: CompileConfig) -> WasmArtifact:
        """Package the Python source and manifest into the CPython WASM engine."""
        try:
            if not self.engine_path.exists():
                raise BackendCompilationError(
                    f"WASI Python engine not found at {self.engine_path}. "
                    "Please download the python.wasm binary."
                )

            # Read the base WASM engine
            engine_bytes = self.engine_path.read_bytes()
            
            source_bytes = source.encode('utf-8')
            manifest.python_runtime = "wasi_python"
            manifest_bytes = manifest.model_dump_json().encode('utf-8')
            
            source_hash = hashlib.sha256(source_bytes).hexdigest()
            build_time = "" if config.deterministic_builds else datetime.now(timezone.utc).isoformat()
            
            metadata = {
                "compiler": "wasmbox",
                "version": config.compiler_version,
                "build_time": build_time,
                "source_hash": source_hash,
                "runtime": "wasi_python"
            }
            metadata_bytes = json.dumps(metadata, sort_keys=True).encode('utf-8')
            
            module = bytearray(engine_bytes)
            
            # Append custom sections
            module.extend(WasmModuleBuilder._build_custom_section("wasmbox_source", source_bytes))
            module.extend(WasmModuleBuilder._build_custom_section("wasmbox_manifest", manifest_bytes))
            module.extend(WasmModuleBuilder._build_custom_section("wasmbox_metadata", metadata_bytes))
            
            wasm_bytes = bytes(module)
            artifact_hash = hashlib.sha256(wasm_bytes).hexdigest()
            
            return WasmArtifact(
                wasm_bytes=wasm_bytes,
                sha256=artifact_hash,
                size_bytes=len(wasm_bytes),
                runtime="wasi_python",
                exports=["_start", "memory"],
                imports=[],
                custom_sections=["wasmbox_source", "wasmbox_manifest", "wasmbox_metadata"]
            )
        except BackendCompilationError:
            raise
        except Exception as e:
            raise BackendCompilationError(f"WASI Python compilation failed: {e}")

    def is_available(self) -> bool:
        """Check if python.wasm is available."""
        return self.engine_path.exists()
