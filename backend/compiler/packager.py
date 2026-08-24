"""
WasmBox Compiler Packager.

Packages compiled resources into a final WASM artifact and verifies size limits.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .config import CompileConfig
from .errors import ArtifactError
from .models import PluginManifest, WasmArtifact
from .wasm_builder import WasmModuleBuilder, extract_custom_section, list_custom_sections


class WasmPackager:
    """WASM artifact packager. Constructs final artifacts."""

    def package(self, source: str, manifest: PluginManifest, config: CompileConfig) -> WasmArtifact:
        """Package a WASM module from source and manifest."""
        
        # Prepare metadata
        metadata = {
            "compiler_version": config.compiler_version,
            "build_timestamp": "" if config.deterministic_builds else datetime.now(timezone.utc).isoformat(),
            "source_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "python_version": manifest.python_runtime,
        }
        
        metadata_json = json.dumps(metadata, separators=(',', ':')).encode("utf-8")
        manifest_json = json.dumps(manifest.model_dump(), separators=(',', ':')).encode("utf-8")
        
        min_pages = manifest.memory_limit_bytes // 65536
        if min_pages < 1:
            min_pages = 1
        max_pages = config.execution_limits.max_memory_pages
        
        # Build module
        wasm_bytes = WasmModuleBuilder.build_plugin_module(
            source=source,
            manifest_json=manifest_json,
            metadata_json=metadata_json,
            min_memory_pages=min_pages,
            max_memory_pages=max_pages
        )
        
        size_bytes = len(wasm_bytes)
        
        if size_bytes > config.compilation_limits.max_artifact_size_bytes:
            raise ArtifactError(
                f"Generated artifact size ({size_bytes} bytes) exceeds limit "
                f"({config.compilation_limits.max_artifact_size_bytes} bytes)."
            )
            
        sha256_hash = hashlib.sha256(wasm_bytes).hexdigest()
        
        custom_sections = list_custom_sections(wasm_bytes)
        
        return WasmArtifact(
            wasm_bytes=wasm_bytes,
            sha256=sha256_hash,
            size_bytes=size_bytes,
            runtime="embedded",
            exports=["memory", "_start"],
            imports=[],
            custom_sections=custom_sections
        )
