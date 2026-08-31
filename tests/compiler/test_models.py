"""Tests for WasmBox compiler data models."""

from backend.compiler.models import (
    AnalysisResult,
    CompilationMetrics,
    CompilationResult,
    DependencyCategory,
    DependencyInfo,
    DiagnosticModel,
    DiagnosticSeverity,
    PluginManifest,
    WasmArtifact,
)


def test_dependency_info_defaults():
    dep = DependencyInfo(name="json")

    assert dep.name == "json"
    assert dep.category == DependencyCategory.UNKNOWN
    assert dep.source == "builtin"


def test_dependency_info_category():
    dep = DependencyInfo(
        name="os",
        category=DependencyCategory.FORBIDDEN,
        reason="Forbidden by security policy",
    )

    assert dep.category == DependencyCategory.FORBIDDEN
    assert dep.reason == "Forbidden by security policy"


def test_analysis_result_defaults():
    result = AnalysisResult()

    assert result.imports == []
    assert result.functions == []
    assert result.classes == []
    assert result.node_count == 0
    assert result.has_loops is False
    assert result.has_recursion is False


def test_plugin_manifest_defaults():
    manifest = PluginManifest(plugin_name="test_plugin")

    assert manifest.plugin_name == "test_plugin"
    assert manifest.runtime == "wasm"
    assert manifest.python_runtime == "embedded"
    assert manifest.entrypoint == "main"
    assert manifest.memory_limit_bytes == 10 * 1024 * 1024


def test_wasm_artifact_model():
    artifact = WasmArtifact(
        wasm_bytes=b"wasm",
        sha256="abc123",
        size_bytes=4,
    )

    assert artifact.wasm_bytes == b"wasm"
    assert artifact.sha256 == "abc123"
    assert artifact.size_bytes == 4
    assert artifact.exports == []
    assert artifact.imports == []


def test_compilation_metrics_defaults():
    metrics = CompilationMetrics()

    assert metrics.parse_time_ms == 0.0
    assert metrics.total_time_ms == 0.0
    assert metrics.artifact_size_bytes == 0
    assert metrics.cache_hit is False


def test_compilation_result_api_response():
    result = CompilationResult(
        success=True,
        plugin_name="test_plugin",
        plugin_id="plugin-1",
        tenant_id="tenant-1",
        artifact_hash="abc123",
        artifact_size_bytes=100,
    )

    response = result.to_api_response()

    assert response["success"] is True
    assert response["plugin_name"] == "test_plugin"
    assert response["plugin_id"] == "plugin-1"
    assert response["tenant_id"] == "tenant-1"
    assert response["artifact_hash"] == "abc123"
    assert "artifact_bytes" not in response


def test_compilation_result_error_flags():
    diagnostic = DiagnosticModel(
        code="E200",
        severity=DiagnosticSeverity.ERROR,
        stage="validator",
        message="Forbidden import",
    )

    result = CompilationResult(
        success=False,
        diagnostics=[diagnostic],
    )

    assert result.has_errors is True
    assert result.has_warnings is False
