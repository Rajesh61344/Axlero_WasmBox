"""Tests for the WasmBox compiler artifact storage."""

import pytest
from pathlib import Path
import hashlib

from backend.compiler.artifacts import ArtifactManager
from backend.compiler.models import WasmArtifact, PluginManifest
from backend.compiler.errors import ArtifactError

def test_store_and_retrieve(tmp_path: Path) -> None:
    manager = ArtifactManager(base_dir=tmp_path)
    
    artifact = WasmArtifact(
        wasm_bytes=b"wasm_data",
        sha256=hashlib.sha256(b"wasm_data").hexdigest(),
        size_bytes=9,
        runtime="embedded"
    )
    manifest = PluginManifest(plugin_name="test_plugin")
    
    manager.store(artifact, manifest, "tenant1", "plugin1")
    
    retrieved = manager.retrieve("tenant1", "plugin1", artifact.sha256)
    
    assert retrieved is not None
    r_bytes, r_manifest = retrieved
    
    assert r_bytes == b"wasm_data"
    assert r_manifest.plugin_name == "test_plugin"

def test_retrieve_nonexistent(tmp_path: Path) -> None:
    manager = ArtifactManager(base_dir=tmp_path)
    
    assert manager.retrieve("t1", "p1", "nonexistent_hash") is None

def test_path_traversal_prevented(tmp_path: Path) -> None:
    manager = ArtifactManager(base_dir=tmp_path)
    
    artifact = WasmArtifact(
        wasm_bytes=b"",
        sha256="abc",
        size_bytes=0
    )
    manifest = PluginManifest(plugin_name="test")
    
    with pytest.raises(ArtifactError):
        manager.store(artifact, manifest, "../tenant", "plugin")
        
    with pytest.raises(ArtifactError):
        manager.store(artifact, manifest, "tenant", "/plugin")

def test_list_plugins(tmp_path: Path) -> None:
    manager = ArtifactManager(base_dir=tmp_path)
    
    artifact1 = WasmArtifact(
        wasm_bytes=b"w1",
        sha256=hashlib.sha256(b"w1").hexdigest(),
        size_bytes=2
    )
    artifact2 = WasmArtifact(
        wasm_bytes=b"w2",
        sha256=hashlib.sha256(b"w2").hexdigest(),
        size_bytes=2
    )
    
    manager.store(artifact1, PluginManifest(plugin_name="p1"), "t1", "plugin1")
    manager.store(artifact2, PluginManifest(plugin_name="p2"), "t1", "plugin2")
    
    plugins = manager.list_plugins("t1")
    
    assert len(plugins) == 2
    p_ids = [p["plugin_id"] for p in plugins]
    assert "plugin1" in p_ids
    assert "plugin2" in p_ids

def test_delete(tmp_path: Path) -> None:
    manager = ArtifactManager(base_dir=tmp_path)
    
    artifact = WasmArtifact(
        wasm_bytes=b"w",
        sha256=hashlib.sha256(b"w").hexdigest(),
        size_bytes=1
    )
    manifest = PluginManifest(plugin_name="p")
    
    manager.store(artifact, manifest, "t1", "p1")
    assert manager.retrieve("t1", "p1", artifact.sha256) is not None
    
    assert manager.delete("t1", "p1", artifact.sha256) is True
    
    assert manager.retrieve("t1", "p1", artifact.sha256) is None
    
    # Deleting non-existent artifact returns False
    assert manager.delete("t1", "p1", artifact.sha256) is False
