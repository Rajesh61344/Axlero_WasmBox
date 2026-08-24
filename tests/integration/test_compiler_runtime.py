"""Integration tests for the WasmBox compiler pipeline.

Golden end-to-end tests that exercise the full compilation pipeline
from source to verified WASM artifact.
"""

import hashlib

import pytest
from pathlib import Path

from backend.compiler import compile, CompileConfig


@pytest.fixture
def config() -> CompileConfig:
    """Compilation config with cache disabled for test isolation."""
    return CompileConfig(enable_cache=False)


def read_example(filename: str) -> str:
    """Read an example plugin file."""
    examples_dir = Path(__file__).parent.parent.parent / "examples" / "plugins"
    path = examples_dir / filename
    return path.read_text("utf-8")


def _compile(source: str, config: CompileConfig, plugin_name: str = "test_plugin"):
    """Helper to compile with default arguments."""
    return compile(
        source=source,
        plugin_name=plugin_name,
        tenant_id="test_tenant",
        config=config,
    )


@pytest.mark.integration
def test_golden_hello_plugin(config: CompileConfig) -> None:
    """Golden test: compile hello.py, verify valid WASM, manifest, and hash."""
    source = read_example("hello.py")
    result = _compile(source, config, plugin_name="hello")

    assert result.success is True, f"Compilation failed: {[d.message for d in result.diagnostics if d.severity == 'error']}"
    assert result.artifact_bytes is not None
    assert result.artifact_bytes[:4] == b'\x00asm', "Artifact must be valid WASM"

    # Manifest checks
    assert result.manifest is not None
    assert result.manifest.plugin_name == "hello"
    assert result.manifest.entrypoint == "main"

    # Hash integrity
    assert result.artifact_hash is not None
    actual_hash = hashlib.sha256(result.artifact_bytes).hexdigest()
    assert result.artifact_hash == actual_hash, "Artifact hash must match"

    # Size
    assert result.artifact_size_bytes is not None
    assert result.artifact_size_bytes == len(result.artifact_bytes)


@pytest.mark.integration
def test_golden_filesystem_attack(config: CompileConfig) -> None:
    """Golden test: malicious_filesystem.py must be REJECTED."""
    source = read_example("malicious_filesystem.py")
    result = _compile(source, config)

    assert result.success is False, "Filesystem access must be rejected"
    error_messages = " ".join(d.message.lower() for d in result.errors)
    assert "open" in error_messages or "file" in error_messages, f"Should mention file/open: {error_messages}"


@pytest.mark.integration
def test_golden_network_attack(config: CompileConfig) -> None:
    """Golden test: malicious_network.py must be REJECTED."""
    source = read_example("malicious_network.py")
    result = _compile(source, config)

    assert result.success is False, "Network access must be rejected"
    error_messages = " ".join(d.message.lower() for d in result.errors)
    assert "socket" in error_messages, f"Should mention socket: {error_messages}"


@pytest.mark.integration
def test_golden_infinite_loop_compiles(config: CompileConfig) -> None:
    """Golden test: infinite_loop.py MAY compile (not a syntax error).

    The runtime must enforce execution limits — this is NOT a compiler error.
    """
    source = read_example("infinite_loop.py")
    result = _compile(source, config)

    # An infinite loop is valid Python — it should compile successfully
    assert result.success is True, f"Infinite loop should compile: {[d.message for d in result.diagnostics if d.severity == 'error']}"
    assert result.artifact_bytes is not None
    assert result.artifact_bytes[:4] == b'\x00asm'

    # Manifest should include execution limits
    assert result.manifest is not None
    assert result.manifest.max_fuel > 0
    assert result.manifest.execution_timeout_ms > 0


@pytest.mark.integration
def test_golden_host_function(config: CompileConfig) -> None:
    """Golden test: host_function_safe.py should compile with host functions in manifest."""
    source = read_example("host_function_safe.py")
    result = _compile(source, config)

    assert result.success is True, f"Host function plugin should compile: {[d.message for d in result.diagnostics if d.severity == 'error']}"
    assert result.manifest is not None
    # The manifest should list requested host functions
    assert "log" in result.manifest.requested_host_functions


@pytest.mark.integration
def test_golden_calculator(config: CompileConfig) -> None:
    """Golden test: calculator.py should compile successfully."""
    source = read_example("calculator.py")
    result = _compile(source, config)

    assert result.success is True, f"Calculator should compile: {[d.message for d in result.diagnostics if d.severity == 'error']}"
    assert result.artifact_bytes is not None
    assert result.artifact_size_bytes is not None
    assert result.artifact_size_bytes > 0


@pytest.mark.integration
def test_golden_formatter(config: CompileConfig) -> None:
    """Golden test: formatter.py should compile (json and re are allowed)."""
    source = read_example("formatter.py")
    result = _compile(source, config)

    assert result.success is True, f"Formatter should compile: {[d.message for d in result.diagnostics if d.severity == 'error']}"
    assert result.artifact_bytes is not None


@pytest.mark.integration
def test_artifact_determinism(config: CompileConfig) -> None:
    """Verify that compiling the same source twice produces identical artifacts."""
    config_det = CompileConfig(enable_cache=False, deterministic_builds=True)
    source = "def main(data):\n    return {'value': data['x'] * 2}\n"

    result1 = _compile(source, config_det, plugin_name="determinism_test")
    result2 = _compile(source, config_det, plugin_name="determinism_test")

    assert result1.success and result2.success
    assert result1.artifact_hash == result2.artifact_hash, "Deterministic builds must produce identical hashes"


@pytest.mark.integration
def test_wasm_custom_sections_present(config: CompileConfig) -> None:
    """Verify that the WASM artifact contains expected custom sections."""
    source = "def main(data):\n    return {'ok': True}\n"
    result = _compile(source, config)

    assert result.success
    assert result.artifact_bytes is not None

    from backend.compiler.wasm_builder import extract_custom_section

    # Extract custom sections
    source_section = extract_custom_section(result.artifact_bytes, "wasmbox_source")
    manifest_section = extract_custom_section(result.artifact_bytes, "wasmbox_manifest")

    assert source_section is not None, "wasmbox_source section must exist"
    assert manifest_section is not None, "wasmbox_manifest section must exist"

    # Verify manifest is valid JSON
    import json
    manifest_data = json.loads(manifest_section.decode("utf-8"))
    assert "plugin_name" in manifest_data
    assert "entrypoint" in manifest_data
