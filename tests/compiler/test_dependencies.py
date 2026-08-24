"""Tests for the WasmBox compiler dependency management."""

import pytest

from backend.compiler.config import CompileConfig
from backend.compiler.models import AnalysisResult, ImportInfo, DependencyCategory
from backend.compiler.dependencies import DependencyManager

def test_resolve_stdlib_allowed() -> None:
    manager = DependencyManager()
    config = CompileConfig()
    analysis = AnalysisResult(
        imports=[
            ImportInfo(module="json"),
            ImportInfo(module="math")
        ]
    )
    
    result = manager.resolve(analysis, config)
    
    assert len(result.resolved) == 2
    assert result.resolved[0].category == DependencyCategory.STDLIB
    assert result.resolved[1].category == DependencyCategory.STDLIB
    assert len(result.forbidden) == 0
    assert len(result.missing) == 0
    assert not result.diagnostics

def test_resolve_forbidden_os() -> None:
    manager = DependencyManager()
    config = CompileConfig()
    analysis = AnalysisResult(
        imports=[ImportInfo(module="os")]
    )
    
    result = manager.resolve(analysis, config)
    
    assert len(result.resolved) == 0
    assert len(result.forbidden) == 1
    assert result.forbidden[0].name == "os"
    assert result.forbidden[0].category == DependencyCategory.FORBIDDEN
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "E300"

def test_resolve_forbidden_socket() -> None:
    manager = DependencyManager()
    config = CompileConfig()
    analysis = AnalysisResult(
        imports=[ImportInfo(module="socket")]
    )
    
    result = manager.resolve(analysis, config)
    
    assert len(result.resolved) == 0
    assert len(result.forbidden) == 1
    assert result.forbidden[0].name == "socket"
    assert result.forbidden[0].category == DependencyCategory.FORBIDDEN

def test_resolve_unknown_package() -> None:
    manager = DependencyManager()
    config = CompileConfig()
    analysis = AnalysisResult(
        imports=[ImportInfo(module="unknown_magic_pkg")]
    )
    
    result = manager.resolve(analysis, config)
    
    assert len(result.resolved) == 0
    assert len(result.forbidden) == 1
    assert result.forbidden[0].name == "unknown_magic_pkg"
    assert result.forbidden[0].category == DependencyCategory.UNSUPPORTED
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "E301"

def test_resolve_lock_data_generated() -> None:
    manager = DependencyManager()
    config = CompileConfig()
    analysis = AnalysisResult(
        imports=[ImportInfo(module="json")]
    )
    
    result = manager.resolve(analysis, config)
    
    assert "dependencies" in result.lock_data
    assert len(result.lock_data["dependencies"]) == 1
    assert result.lock_data["dependencies"][0]["name"] == "json"

def test_resolve_too_many_deps() -> None:
    manager = DependencyManager()
    config = CompileConfig()
    # Mock compilation limits so we hit the cap
    # We create a new CompileConfig object since limits is frozen if it's a dataclass, but CompilationLimits is passed as default_factory
    # Let's just modify it if possible or create a new config. Wait, compilation_limits is a frozen dataclass instance
    from backend.compiler.config import CompilationLimits
    config.compilation_limits = CompilationLimits(max_dependencies=1)
    
    analysis = AnalysisResult(
        imports=[
            ImportInfo(module="json"),
            ImportInfo(module="math")
        ]
    )
    
    result = manager.resolve(analysis, config)
    
    # It resolves them but adds a diagnostic error
    assert len(result.resolved) == 2
    assert any(d.code == "E302" for d in result.diagnostics)

def test_resolve_empty() -> None:
    manager = DependencyManager()
    config = CompileConfig()
    analysis = AnalysisResult(imports=[])
    
    result = manager.resolve(analysis, config)
    
    assert len(result.resolved) == 0
    assert len(result.forbidden) == 0
    assert len(result.missing) == 0
    assert not result.diagnostics
