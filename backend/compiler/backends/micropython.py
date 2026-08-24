"""
WasmBox Compiler MicroPython Backend.

Compiles Python source targeting the MicroPython WASM runtime.
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


class MicroPythonBackend(WasmCompilerBackend):
    """MicroPython WASM compiler backend."""

    @property
    def name(self) -> str:
        return "micropython"

    def compile(self, source: str, manifest: PluginManifest, config: CompileConfig) -> WasmArtifact:
        """Compile Python source code using the MicroPython backend."""
        try:
            source_bytes = source.encode('utf-8')
            
            manifest.python_runtime = "micropython"
            manifest_bytes = manifest.model_dump_json().encode('utf-8')
            
            source_hash = hashlib.sha256(source_bytes).hexdigest()
            
            build_time = "" if config.deterministic_builds else datetime.now(timezone.utc).isoformat()
            metadata = {
                "compiler": "wasmbox",
                "version": config.compiler_version,
                "build_time": build_time,
                "source_hash": source_hash,
                "runtime": "micropython"
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
                runtime="micropython",
                exports=["memory", "allocate", "deallocate", "invoke"],
                imports=[],
                custom_sections=[".wasmbox.source", ".wasmbox.manifest", ".wasmbox.metadata"]
            )
        except Exception as e:
            raise BackendCompilationError(f"MicroPython compilation failed: {e}")

    def is_available(self) -> bool:
        """Check if MicroPython backend is available."""
        try:
            import micropython_wasm  # noqa: F401
            return True
        except ImportError:
            return False

    def get_runtime_path(self) -> Path | None:
        """Get the path to the MicroPython WASM binary."""
        try:
            import micropython_wasm
            base_dir = Path(micropython_wasm.__file__).parent
            wasm_path = base_dir / "micropython.wasm"
            if wasm_path.exists():
                return wasm_path
        except ImportError:
            pass
        return None
