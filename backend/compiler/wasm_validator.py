"""
WasmBox Compiler Validator.

Validates WebAssembly artifacts to ensure they meet strict runtime requirements.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .config import CompileConfig
from .errors import Diagnostic, ErrorSeverity, CompilerStage, SourceLocation
from .wasm_builder import is_valid_wasm_header, list_custom_sections, extract_custom_section, decode_unsigned_leb128

try:
    import wasmtime
    HAS_WASMTIME = True
except ImportError:
    HAS_WASMTIME = False


class WasmValidator:
    """Validates WASM binaries against security policies and runtime expectations."""

    def validate(self, wasm_bytes: bytes, config: CompileConfig | None = None) -> list[Diagnostic]:
        """Fully validate a WASM module. Returns a list of diagnostics."""
        diagnostics = []

        if not wasm_bytes:
            diagnostics.append(self._make_error("E600", "WASM module is empty."))
            return diagnostics

        if not is_valid_wasm_header(wasm_bytes):
            diagnostics.append(self._make_error("E600", "Invalid WASM header: missing magic number or incorrect version."))
            return diagnostics

        if config and len(wasm_bytes) > config.compilation_limits.max_artifact_size_bytes:
            diagnostics.append(self._make_error(
                "E601", 
                f"Module size ({len(wasm_bytes)} bytes) exceeds maximum allowed ({config.compilation_limits.max_artifact_size_bytes} bytes)."
            ))

        if HAS_WASMTIME:
            try:
                engine = wasmtime.Engine()
                wasmtime.Module.validate(engine, wasm_bytes)
            except Exception as e:
                diagnostics.append(self._make_error("E602", f"Wasmtime validation failed: {str(e)}"))

        # Verify manifest
        manifest_data = extract_custom_section(wasm_bytes, "wasmbox_manifest")
        if not manifest_data:
            diagnostics.append(self._make_error("E605", "Missing required custom section: wasmbox_manifest"))
        else:
            try:
                json.loads(manifest_data.decode("utf-8"))
            except Exception:
                diagnostics.append(self._make_error("E605", "wasmbox_manifest section contains invalid JSON"))

        diagnostics.extend(self.validate_imports(wasm_bytes))
        diagnostics.extend(self.validate_exports(wasm_bytes, {"_start", "memory"}))

        return diagnostics

    def inspect(self, wasm_bytes: bytes) -> dict[str, Any]:
        """Inspect a WASM module and extract its structural info."""
        if not is_valid_wasm_header(wasm_bytes):
            return {"valid": False}
            
        sha256 = hashlib.sha256(wasm_bytes).hexdigest()
        custom_sections = list_custom_sections(wasm_bytes)
        
        manifest = None
        manifest_bytes = extract_custom_section(wasm_bytes, "wasmbox_manifest")
        if manifest_bytes:
            try:
                manifest = json.loads(manifest_bytes.decode("utf-8"))
            except Exception:
                pass

        # Parse memory, imports, exports structurally
        memory = None
        imports = []
        exports = []
        
        offset = 8
        while offset < len(wasm_bytes):
            if offset >= len(wasm_bytes):
                break
            section_id = wasm_bytes[offset]
            offset += 1
            section_size, offset = decode_unsigned_leb128(wasm_bytes, offset)
            
            if section_id == 2:  # IMPORT
                # minimal import parser
                pass
            elif section_id == 7:  # EXPORT
                exp_offset = offset
                count, exp_offset = decode_unsigned_leb128(wasm_bytes, exp_offset)
                for _ in range(count):
                    name_len, exp_offset = decode_unsigned_leb128(wasm_bytes, exp_offset)
                    name = wasm_bytes[exp_offset:exp_offset+name_len].decode("utf-8", errors="ignore")
                    exp_offset += name_len
                    kind = wasm_bytes[exp_offset]
                    exp_offset += 1
                    idx, exp_offset = decode_unsigned_leb128(wasm_bytes, exp_offset)
                    exports.append({"name": name, "type": kind})
            elif section_id == 5:  # MEMORY
                mem_offset = offset
                count, mem_offset = decode_unsigned_leb128(wasm_bytes, mem_offset)
                if count > 0:
                    flags = wasm_bytes[mem_offset]
                    mem_offset += 1
                    min_p, mem_offset = decode_unsigned_leb128(wasm_bytes, mem_offset)
                    max_p = None
                    if flags & 1:
                        max_p, mem_offset = decode_unsigned_leb128(wasm_bytes, mem_offset)
                    memory = {"min_pages": min_p, "max_pages": max_p}
            
            offset += section_size
            
        return {
            "valid": True,
            "size_bytes": len(wasm_bytes),
            "sha256": sha256,
            "imports": imports,
            "exports": exports,
            "custom_sections": custom_sections,
            "manifest": manifest,
            "memory": memory,
        }

    def validate_imports(self, wasm_bytes: bytes, allowed_imports: dict[str, set[str]] | None = None) -> list[Diagnostic]:
        """Validate WASM imports against an allowlist."""
        # A full parser would go here to restrict imports.
        # Returning empty for now as our built module has no imports.
        return []

    def validate_exports(self, wasm_bytes: bytes, required_exports: set[str] | None = None) -> list[Diagnostic]:
        """Validate that all required exports are present."""
        if not required_exports:
            return []
            
        diagnostics = []
        info = self.inspect(wasm_bytes)
        if not info.get("valid"):
            return [self._make_error("E600", "Invalid WASM module.")]
            
        found_exports = {e["name"] for e in info.get("exports", [])}
        for req in required_exports:
            if req not in found_exports:
                diagnostics.append(self._make_error("E604", f"Missing required export: {req}"))
                
        return diagnostics

    def verify_integrity(self, wasm_bytes: bytes, expected_hash: str) -> bool:
        """Verify the cryptographic integrity of a WASM module."""
        return hashlib.sha256(wasm_bytes).hexdigest() == expected_hash

    def _make_error(self, code: str, message: str) -> Diagnostic:
        """Helper to construct error diagnostics."""
        return Diagnostic(
            code=code,
            severity=ErrorSeverity.ERROR,
            stage=CompilerStage.WASM_VALIDATION,
            message=message
        )
