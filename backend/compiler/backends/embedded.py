"""
WasmBox Compiler Embedded Backend.

Compiles Python source into a WASM module by embedding the source code
and manifest directly into the WASM module, which expects an embedded
Python runtime on the host side.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from ..config import CompileConfig
from ..errors import BackendCompilationError
from ..models import PluginManifest, WasmArtifact
from ..wasm_builder import WasmModuleBuilder
from .base import WasmCompilerBackend


class EmbeddedPythonBackend(WasmCompilerBackend):
    """Embedded Python WASM compiler backend."""

    @property
    def name(self) -> str:
        return "embedded"

    def compile(self, source: str, manifest: PluginManifest, config: CompileConfig) -> WasmArtifact:
        """Compile Python source code using the embedded backend."""
        try:
            source_bytes = source.encode('utf-8')
            manifest_bytes = manifest.model_dump_json().encode('utf-8')
            
            source_hash = hashlib.sha256(source_bytes).hexdigest()
            
            build_time = "" if config.deterministic_builds else datetime.now(timezone.utc).isoformat()
            metadata = {
                "compiler": "wasmbox",
                "version": config.compiler_version,
                "build_time": build_time,
                "source_hash": source_hash,
                "runtime": "embedded"
            }
            metadata_bytes = json.dumps(metadata, sort_keys=True).encode('utf-8')
            
            wasm_bytes = WasmModuleBuilder.build_plugin_module(
                source=source,
                manifest_json=manifest_bytes,
                metadata_json=metadata_bytes
            )
            
            artifact_hash = hashlib.sha256(wasm_bytes).hexdigest()
            
            return WasmArtifact(
                wasm_bytes=wasm_bytes,
                sha256=artifact_hash,
                size_bytes=len(wasm_bytes),
                runtime="embedded",
                exports=["memory", "allocate", "deallocate", "invoke"],
                imports=[],
                custom_sections=[".wasmbox.source", ".wasmbox.manifest", ".wasmbox.metadata"]
            )
        except Exception as e:
            raise BackendCompilationError(f"Embedded compilation failed: {e}")

    def is_available(self) -> bool:
        """Embedded backend is always available."""
        return True
