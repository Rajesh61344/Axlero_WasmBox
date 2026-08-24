"""Tests for the WasmBox WASM validator."""

import pytest
import json
import hashlib

from backend.compiler.config import CompileConfig, CompilationLimits
from backend.compiler.wasm_validator import WasmValidator
from backend.compiler.wasm_builder import WasmModuleBuilder

def generate_valid_wasm_module() -> bytes:
    # Generates a minimal valid WASM using the real builder
    manifest_data = {"plugin_name": "test"}
    return WasmModuleBuilder.build_plugin_module(
        source="pass",
        manifest_json=json.dumps(manifest_data).encode("utf-8"),
        metadata_json=b"{}",
        min_memory_pages=1,
        max_memory_pages=10
    )

def test_validate_valid_module() -> None:
    validator = WasmValidator()
    config = CompileConfig()
    wasm_bytes = generate_valid_wasm_module()
    
    diagnostics = validator.validate(wasm_bytes, config)
    
    assert not diagnostics

def test_validate_invalid_header() -> None:
    validator = WasmValidator()
    config = CompileConfig()
    wasm_bytes = b"invalid_data"
    
    diagnostics = validator.validate(wasm_bytes, config)
    
    assert len(diagnostics) > 0
    assert any(d.code == "E600" for d in diagnostics)

def test_validate_empty() -> None:
    validator = WasmValidator()
    config = CompileConfig()
    wasm_bytes = b""
    
    diagnostics = validator.validate(wasm_bytes, config)
    
    assert len(diagnostics) > 0
    assert any(d.code == "E600" for d in diagnostics)

def test_validate_oversized() -> None:
    validator = WasmValidator()
    config = CompileConfig()
    config.compilation_limits = CompilationLimits(max_artifact_size_bytes=5)
    wasm_bytes = generate_valid_wasm_module()
    
    diagnostics = validator.validate(wasm_bytes, config)
    
    assert len(diagnostics) > 0
    assert any(d.code == "E601" for d in diagnostics)

def test_inspect_returns_info() -> None:
    validator = WasmValidator()
    wasm_bytes = generate_valid_wasm_module()
    
    info = validator.inspect(wasm_bytes)
    
    assert info["valid"] is True
    assert "size_bytes" in info
    assert "sha256" in info
    assert "manifest" in info
    assert info["manifest"]["plugin_name"] == "test"

def test_verify_integrity_correct() -> None:
    validator = WasmValidator()
    wasm_bytes = generate_valid_wasm_module()
    expected_hash = hashlib.sha256(wasm_bytes).hexdigest()
    
    assert validator.verify_integrity(wasm_bytes, expected_hash) is True

def test_verify_integrity_mismatch() -> None:
    validator = WasmValidator()
    wasm_bytes = generate_valid_wasm_module()
    
    assert validator.verify_integrity(wasm_bytes, "wrong_hash") is False
