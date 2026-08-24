"""Security tests for the WasmBox compiler."""

import pytest
from backend.compiler import compile, CompileConfig


@pytest.fixture
def config() -> CompileConfig:
    return CompileConfig(enable_cache=False)


def _compile(source: str, config: CompileConfig):
    """Helper to compile with default plugin_name and tenant_id."""
    return compile(
        source=source,
        plugin_name="test_plugin",
        tenant_id="test_tenant",
        config=config,
    )


@pytest.mark.security
def test_filesystem_access_rejected(config: CompileConfig) -> None:
    source = "def main(data):\n    f = open('/etc/passwd')\n"
    result = _compile(source, config)
    assert not result.success
    assert any(
        "open" in d.message.lower() or "file" in d.message.lower()
        for d in result.errors
    )


@pytest.mark.security
def test_network_access_rejected(config: CompileConfig) -> None:
    source = "import socket\ndef main(data):\n    pass\n"
    result = _compile(source, config)
    assert not result.success
    assert any("socket" in d.message.lower() for d in result.errors)


@pytest.mark.security
def test_subprocess_rejected(config: CompileConfig) -> None:
    source = "import subprocess\ndef main(data):\n    pass\n"
    result = _compile(source, config)
    assert not result.success
    assert any("subprocess" in d.message.lower() for d in result.errors)


@pytest.mark.security
def test_eval_rejected(config: CompileConfig) -> None:
    source = "def main(data):\n    eval('print(1)')\n"
    result = _compile(source, config)
    assert not result.success
    assert any("eval" in d.message.lower() for d in result.errors)


@pytest.mark.security
def test_exec_rejected(config: CompileConfig) -> None:
    source = "def main(data):\n    exec('print(1)')\n"
    result = _compile(source, config)
    assert not result.success
    assert any("exec" in d.message.lower() for d in result.errors)


@pytest.mark.security
def test_dynamic_import_rejected(config: CompileConfig) -> None:
    source = "def main(data):\n    os_module = __import__('os')\n"
    result = _compile(source, config)
    assert not result.success
    assert any("__import__" in d.message for d in result.errors)


@pytest.mark.security
def test_reflection_abuse_rejected(config: CompileConfig) -> None:
    source = "def main(data):\n    globals()['open']('file')\n"
    result = _compile(source, config)
    assert not result.success


@pytest.mark.security
def test_ctypes_rejected(config: CompileConfig) -> None:
    source = "import ctypes\ndef main(data):\n    pass\n"
    result = _compile(source, config)
    assert not result.success
    assert any("ctypes" in d.message.lower() for d in result.errors)


@pytest.mark.security
def test_safe_plugin_accepted(config: CompileConfig) -> None:
    source = "import json\nimport math\ndef main(data):\n    return math.pi\n"
    result = _compile(source, config)
    assert result.success


@pytest.mark.security
def test_multiple_violations_all_reported(config: CompileConfig) -> None:
    source = "import os\ndef main(data):\n    eval('1')\n    open('f')\n"
    result = _compile(source, config)
    assert not result.success
    errors = [d for d in result.errors]
    assert len(errors) >= 2  # At least forbidden import + forbidden builtin
