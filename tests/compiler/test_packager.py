"""Tests for the WasmBox compiler packager."""

import json
import pytest

from backend.compiler.config import CompileConfig, CompilationLimits
from backend.compiler.models import PluginManifest
from backend.compiler.packager import WasmPackager
from backend.compiler.errors import ArtifactError

def test_package_creates_valid_wasm() -> None:
    packager = WasmPackager()
    config = CompileConfig()
    manifest = PluginManifest(plugin_name="test_plugin")
    source = "def main():\n    return 42\n"
    
    artifact = packager.package(source, manifest, config)
    
    # Valid WASM header \0asm
    assert artifact.wasm_bytes.startswith(b'\x00asm')
    assert artifact.size_bytes == len(artifact.wasm_bytes)

def test_package_hash_computed() -> None:
    packager = WasmPackager()
    config = CompileConfig()
    manifest = PluginManifest(plugin_name="test_plugin")
    source = "def main():\n    return 42\n"
    
    artifact = packager.package(source, manifest, config)
    
    assert artifact.sha256 is not None
    assert len(artifact.sha256) == 64

def test_package_contains_source() -> None:
    packager = WasmPackager()
    config = CompileConfig()
    manifest = PluginManifest(plugin_name="test_plugin")
    source = "def main():\n    return 42\n"
    
    artifact = packager.package(source, manifest, config)
    
    assert "wasmbox_source" in artifact.custom_sections

def test_package_contains_manifest() -> None:
    packager = WasmPackager()
    config = CompileConfig()
    manifest = PluginManifest(plugin_name="test_plugin")
    source = "def main():\n    return 42\n"
    
    artifact = packager.package(source, manifest, config)
    
    assert "wasmbox_manifest" in artifact.custom_sections

def test_package_size_within_limits() -> None:
    packager = WasmPackager()
    config = CompileConfig()
    manifest = PluginManifest(plugin_name="test_plugin")
    source = "def main():\n    return 42\n"
    
    artifact = packager.package(source, manifest, config)
    
    assert artifact.size_bytes <= config.compilation_limits.max_artifact_size_bytes

def test_package_oversized_rejected() -> None:
    packager = WasmPackager()
    config = CompileConfig()
    config.compilation_limits = CompilationLimits(max_artifact_size_bytes=10)
    manifest = PluginManifest(plugin_name="test_plugin")
    source = "def main():\n    return 42\n"
    
    with pytest.raises(ArtifactError):
        packager.package(source, manifest, config)
