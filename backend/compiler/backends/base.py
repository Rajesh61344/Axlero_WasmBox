"""
WasmBox Compiler Backend Base.

Defines the abstract interface for all WASM compiler backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..config import CompileConfig
from ..models import PluginManifest, WasmArtifact


class WasmCompilerBackend(ABC):
    """Abstract base class for all WASM compilation backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the backend."""
        pass

    @abstractmethod
    def compile(self, source: str, manifest: PluginManifest, config: CompileConfig) -> WasmArtifact:
        """Compile Python source code to a WASM artifact.
        
        Args:
            source: Validated and transformed Python source code.
            manifest: The plugin manifest to embed in the artifact.
            config: The compilation configuration.
            
        Returns:
            A WasmArtifact containing the compiled WASM and metadata.
            
        Raises:
            BackendCompilationError: If compilation fails.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend's dependencies are available."""
        pass

    def get_info(self) -> dict[str, Any]:
        """Get information about this backend."""
        return {
            "name": self.name,
            "version": "1.0.0",
            "available": self.is_available()
        }
