"""Tests for the WasmBox compiler cache."""

import pytest
from pathlib import Path

from backend.compiler.config import CompileConfig
from backend.compiler.cache import CompilationCache
from backend.compiler.models import CompilationResult, PluginManifest

def test_cache_miss(tmp_path: Path) -> None:
    cache = CompilationCache(cache_dir=tmp_path)
    config = CompileConfig()
    
    key = cache.compute_cache_key("source", [], config)
    result = cache.get(key, "tenant1")
    
    assert result is None

def test_cache_hit(tmp_path: Path) -> None:
    cache = CompilationCache(cache_dir=tmp_path)
    config = CompileConfig()
    
    key = cache.compute_cache_key("source", [], config)
    
    # Store a mock result
    res = CompilationResult(success=True, plugin_name="test")
    cache.put(key, "tenant1", res)
    
    hit = cache.get(key, "tenant1")
    assert hit is not None
    assert hit.success is True
    assert hit.plugin_name == "test"

def test_cache_invalidate(tmp_path: Path) -> None:
    cache = CompilationCache(cache_dir=tmp_path)
    config = CompileConfig()
    
    key = cache.compute_cache_key("source", [], config)
    res = CompilationResult(success=True, plugin_name="test")
    cache.put(key, "tenant1", res)
    
    cache.invalidate(key, "tenant1")
    
    assert cache.get(key, "tenant1") is None

def test_cache_tenant_isolation(tmp_path: Path) -> None:
    cache = CompilationCache(cache_dir=tmp_path)
    config = CompileConfig()
    
    key = cache.compute_cache_key("source", [], config)
    res = CompilationResult(success=True, plugin_name="test")
    cache.put(key, "tenant1", res)
    
    # Different tenant should not hit
    assert cache.get(key, "tenant2") is None

def test_cache_key_changes_with_source(tmp_path: Path) -> None:
    cache = CompilationCache(cache_dir=tmp_path)
    config = CompileConfig()
    
    key1 = cache.compute_cache_key("source1", [], config)
    key2 = cache.compute_cache_key("source2", [], config)
    
    assert key1 != key2

def test_cache_clear(tmp_path: Path) -> None:
    cache = CompilationCache(cache_dir=tmp_path)
    config = CompileConfig()
    
    key1 = cache.compute_cache_key("source1", [], config)
    key2 = cache.compute_cache_key("source2", [], config)
    
    cache.put(key1, "tenant1", CompilationResult(success=True))
    cache.put(key2, "tenant2", CompilationResult(success=True))
    
    cache.clear()
    
    assert cache.get(key1, "tenant1") is None
    assert cache.get(key2, "tenant2") is None
