"""
WasmBox Compiler Artifact Storage Manager.

Manages storing, retrieving, and listing compiled WASM artifacts and
their metadata manifests. Enforces tenant isolation and sanitizes paths.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .errors import ArtifactError
from .models import PluginManifest, WasmArtifact


class ArtifactManager:
    """Artifact storage manager."""

    def __init__(self, base_dir: str | Path = 'artifacts') -> None:
        self.base_dir = Path(base_dir)

    def _sanitize_path_component(self, component: str) -> str:
        """Sanitize a path component to prevent traversal."""
        if not component:
            raise ArtifactError("Path component cannot be empty")
        if '..' in component or '/' in component or '\\' in component or '\0' in component:
            raise ArtifactError(f"Invalid characters in path component: {component}")
        if not re.match(r'^[\w\-]+$', component):
            raise ArtifactError(f"Invalid format in path component: {component}")
        return component

    def _validate_tenant_id(self, tenant_id: str) -> str:
        """Validate and sanitize a tenant ID."""
        return self._sanitize_path_component(tenant_id)

    def _validate_plugin_id(self, plugin_id: str) -> str:
        """Validate and sanitize a plugin ID."""
        return self._sanitize_path_component(plugin_id)

    def store(self, artifact: WasmArtifact, manifest: PluginManifest, tenant_id: str, plugin_id: str) -> Path:
        """Store an artifact and manifest to disk."""
        t_id = self._validate_tenant_id(tenant_id)
        p_id = self._validate_plugin_id(plugin_id)
        a_hash = self._sanitize_path_component(artifact.sha256)
        
        target_dir = self.base_dir / t_id / p_id / a_hash
        target_dir.mkdir(parents=True, exist_ok=True)
        
        wasm_path = target_dir / "plugin.wasm"
        manifest_path = target_dir / "manifest.json"
        
        try:
            wasm_path.write_bytes(artifact.wasm_bytes)
            manifest_path.write_text(manifest.model_dump_json(indent=2))
        except OSError as e:
            raise ArtifactError(f"Failed to write artifact: {e}")
            
        return wasm_path

    def retrieve(self, tenant_id: str, plugin_id: str, artifact_hash: str) -> tuple[bytes, PluginManifest] | None:
        """Retrieve an artifact and manifest from disk."""
        t_id = self._validate_tenant_id(tenant_id)
        p_id = self._validate_plugin_id(plugin_id)
        a_hash = self._sanitize_path_component(artifact_hash)
        
        target_dir = self.base_dir / t_id / p_id / a_hash
        wasm_path = target_dir / "plugin.wasm"
        manifest_path = target_dir / "manifest.json"
        
        if not wasm_path.exists() or not manifest_path.exists():
            return None
            
        try:
            wasm_bytes = wasm_path.read_bytes()
            manifest_data = json.loads(manifest_path.read_text())
            manifest = PluginManifest.model_validate(manifest_data)
            return wasm_bytes, manifest
        except (OSError, ValueError) as e:
            raise ArtifactError(f"Failed to read artifact: {e}")

    def list_plugins(self, tenant_id: str) -> list[dict]:
        """List all plugins for a tenant."""
        t_id = self._validate_tenant_id(tenant_id)
        tenant_dir = self.base_dir / t_id
        
        if not tenant_dir.exists() or not tenant_dir.is_dir():
            return []
            
        plugins = []
        try:
            for p_id in tenant_dir.iterdir():
                if not p_id.is_dir():
                    continue
                plugin_id = p_id.name
                
                for a_hash_dir in p_id.iterdir():
                    if not a_hash_dir.is_dir():
                        continue
                    manifest_path = a_hash_dir / "manifest.json"
                    if manifest_path.exists():
                        try:
                            manifest_data = json.loads(manifest_path.read_text())
                            plugins.append({
                                "plugin_id": plugin_id,
                                "artifact_hash": a_hash_dir.name,
                                "manifest": manifest_data
                            })
                        except (OSError, ValueError):
                            pass
        except OSError as e:
            raise ArtifactError(f"Failed to list plugins: {e}")
            
        return plugins

    def delete(self, tenant_id: str, plugin_id: str, artifact_hash: str) -> bool:
        """Delete an artifact and manifest from disk."""
        t_id = self._validate_tenant_id(tenant_id)
        p_id = self._validate_plugin_id(plugin_id)
        a_hash = self._sanitize_path_component(artifact_hash)
        
        target_dir = self.base_dir / t_id / p_id / a_hash
        
        if not target_dir.exists():
            return False
            
        try:
            for file in target_dir.iterdir():
                file.unlink()
            target_dir.rmdir()
            
            # Cleanup parent directories if empty
            plugin_dir = self.base_dir / t_id / p_id
            if not any(plugin_dir.iterdir()):
                plugin_dir.rmdir()
                
            tenant_dir = self.base_dir / t_id
            if not any(tenant_dir.iterdir()):
                tenant_dir.rmdir()
                
            return True
        except OSError as e:
            raise ArtifactError(f"Failed to delete artifact: {e}")
