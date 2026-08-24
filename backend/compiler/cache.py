"""
WasmBox Compiler Cache.

Implements a disk-backed caching layer for compilation results to speed up
repeated compilations of the same source code with the same configuration.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .config import CompileConfig
from .errors import CompilerError, CompilerStage
from .models import CompilationResult


class CompilationCache:
    """Compilation cache."""

    def __init__(self, cache_dir: str | Path = '.wasmbox_cache') -> None:
        self.cache_dir = Path(cache_dir)

    def _sanitize_tenant_id(self, tenant_id: str) -> str:
        if not tenant_id:
            raise CompilerError("cache_error", CompilerStage.CACHE, "Tenant ID cannot be empty")
        if '..' in tenant_id or '/' in tenant_id or '\\' in tenant_id or '\0' in tenant_id:
            raise CompilerError("cache_error", CompilerStage.CACHE, "Invalid characters in tenant ID")
        if not re.match(r'^[\w\-]+$', tenant_id):
            raise CompilerError("cache_error", CompilerStage.CACHE, "Invalid format in tenant ID")
        return tenant_id

    def _cache_path(self, cache_key: str, tenant_id: str) -> Path:
        t_id = self._sanitize_tenant_id(tenant_id)
        if not re.match(r'^[a-f0-9]{64}$', cache_key):
            raise CompilerError("cache_error", CompilerStage.CACHE, "Invalid cache key format")
            
        return self.cache_dir / t_id / f"{cache_key}.json"

    def compute_cache_key(self, source: str, dependencies: list[str], config: CompileConfig) -> str:
        """Compute the cache key for a compilation request."""
        hasher = hashlib.sha256()
        hasher.update(source.encode('utf-8'))
        
        for dep in sorted(dependencies):
            hasher.update(dep.encode('utf-8'))
            
        config_parts = config.to_cache_key_parts()
        config_json = json.dumps(config_parts, sort_keys=True)
        hasher.update(config_json.encode('utf-8'))
        
        return hasher.hexdigest()

    def get(self, cache_key: str, tenant_id: str) -> CompilationResult | None:
        """Get a cached compilation result."""
        try:
            path = self._cache_path(cache_key, tenant_id)
            if not path.exists():
                return None
                
            data = json.loads(path.read_text('utf-8'))
            return CompilationResult.model_validate(data)
        except Exception:
            return None

    def put(self, cache_key: str, tenant_id: str, result: CompilationResult) -> None:
        """Cache a compilation result."""
        try:
            path = self._cache_path(cache_key, tenant_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create a copy and remove raw bytes before caching
            result_copy = result.model_copy()
            result_copy.artifact_bytes = None
            
            data = result_copy.model_dump_json()
            path.write_text(data, 'utf-8')
        except Exception as e:
            raise CompilerError("cache_error", CompilerStage.CACHE, f"Failed to cache result: {e}")

    def invalidate(self, cache_key: str, tenant_id: str) -> bool:
        """Invalidate a specific cache entry."""
        try:
            path = self._cache_path(cache_key, tenant_id)
            if path.exists():
                path.unlink()
                return True
            return False
        except Exception:
            return False

    def clear(self, tenant_id: str | None = None) -> int:
        """Clear the cache, optionally for a specific tenant."""
        cleared = 0
        try:
            if tenant_id:
                t_id = self._sanitize_tenant_id(tenant_id)
                target_dir = self.cache_dir / t_id
                if target_dir.exists() and target_dir.is_dir():
                    for file in target_dir.glob('*.json'):
                        file.unlink()
                        cleared += 1
            else:
                if self.cache_dir.exists() and self.cache_dir.is_dir():
                    for tenant_dir in self.cache_dir.iterdir():
                        if tenant_dir.is_dir():
                            for file in tenant_dir.glob('*.json'):
                                file.unlink()
                                cleared += 1
        except Exception as e:
            raise CompilerError("cache_error", CompilerStage.CACHE, f"Failed to clear cache: {e}")
            
        return cleared
