"""
WasmBox Compiler Manifest Management.

Generates, validates, and serializes the PluginManifest embedded within
WASM artifacts. Contains metadata and constraints for execution.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from .config import CompileConfig
from .errors import ArtifactError, CompilerStage, Diagnostic, ErrorSeverity
from .models import AnalysisResult, DependencyCategory, PluginManifest


class ManifestGenerator:
    """Generates plugin manifests."""

    def generate(
        self,
        plugin_name: str,
        tenant_id: str,
        analysis: AnalysisResult,
        artifact_hash: str,
        artifact_size: int,
        config: CompileConfig,
    ) -> PluginManifest:
        """Create a new PluginManifest based on analysis and config."""
        
        # Generate plugin ID deterministically if required
        if config.deterministic_builds:
            id_input = f"{tenant_id}:{plugin_name}:{artifact_hash}".encode()
            plugin_id = hashlib.sha256(id_input).hexdigest()[:16]
            created_at = ""
        else:
            plugin_id = str(uuid.uuid4())
            created_at = datetime.now(timezone.utc).isoformat()

        requested_host_functions = [ref.name for ref in analysis.host_function_refs]
        
        # Only include safe dependencies
        safe_deps = [
            dep for dep in analysis.dependencies
            if dep.category in (DependencyCategory.STDLIB, DependencyCategory.ALLOWED)
        ]

        return PluginManifest(
            plugin_name=plugin_name,
            plugin_id=plugin_id,
            tenant_id=tenant_id,
            entrypoint=config.entrypoint_function,
            requested_host_functions=requested_host_functions,
            dependencies=safe_deps,
            memory_limit_bytes=config.execution_limits.memory_limit_bytes,
            execution_timeout_ms=config.execution_limits.timeout_ms,
            max_fuel=config.execution_limits.max_fuel,
            artifact_hash=artifact_hash,
            artifact_size_bytes=artifact_size,
            compiler_version=config.compiler_version,
            created_at=created_at,
            python_runtime=config.backend.value,
        )


class ManifestValidator:
    """Validates plugin manifests."""

    def validate(self, manifest: PluginManifest) -> list[Diagnostic]:
        """Validate a manifest, returning diagnostics for any issues."""
        diagnostics = []

        if manifest.format_version != 1:
            diagnostics.append(self._make_diag("E701", f"Unsupported format_version: {manifest.format_version}"))

        if not manifest.plugin_name or not manifest.plugin_name.replace("-", "").replace("_", "").isalnum():
            diagnostics.append(self._make_diag("E702", "Invalid plugin_name"))
        
        if len(manifest.plugin_name) > 128:
            diagnostics.append(self._make_diag("E702", "plugin_name exceeds 128 characters"))

        if not manifest.tenant_id or not manifest.tenant_id.replace("-", "").isalnum():
            diagnostics.append(self._make_diag("E703", "Invalid tenant_id"))
            
        if not manifest.entrypoint.isidentifier():
            diagnostics.append(self._make_diag("E704", "Invalid entrypoint identifier"))

        if manifest.memory_limit_bytes <= 0:
            diagnostics.append(self._make_diag("E705", "memory_limit_bytes must be positive"))

        if manifest.execution_timeout_ms <= 0:
            diagnostics.append(self._make_diag("E706", "execution_timeout_ms must be positive"))

        return diagnostics

    def _make_diag(self, code: str, msg: str) -> Diagnostic:
        return Diagnostic(
            code=code,
            severity=ErrorSeverity.ERROR,
            stage=CompilerStage.ARTIFACT,
            message=msg
        )


class ManifestSerializer:
    """Serializes and deserializes plugin manifests."""

    def serialize(self, manifest: PluginManifest) -> bytes:
        """Serialize a manifest to JSON bytes deterministically."""
        # Dump model with sorted keys
        data = manifest.model_dump()
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def deserialize(self, data: bytes) -> PluginManifest:
        """Deserialize a manifest from JSON bytes."""
        try:
            parsed = json.loads(data.decode("utf-8"))
            return PluginManifest(**parsed)
        except json.JSONDecodeError as e:
            raise ArtifactError(message=f"Failed to decode manifest JSON: {e}", code="E710")
        except Exception as e:
            raise ArtifactError(message=f"Invalid manifest data: {e}", code="E711")
