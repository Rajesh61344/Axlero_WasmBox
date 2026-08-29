"""Security tests for the WasmBox compiler."""

import pytest

from backend.compiler import CompileConfig, compile


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
        "open" in diagnostic.message.lower()
        or "file" in diagnostic.message.lower()
        for diagnostic in result.errors
    )


@pytest.mark.security
def test_network_access_rejected(config: CompileConfig) -> None:
    source = "import socket\ndef main(data):\n    pass\n"

    result = _compile(source, config)

    assert not result.success
    assert any(
        "socket" in diagnostic.message.lower()
        for diagnostic in result.errors
    )


@pytest.mark.security
def test_subprocess_rejected(config: CompileConfig) -> None:
    source = "import subprocess\ndef main(data):\n    pass\n"

    result = _compile(source, config)

    assert not result.success
    assert any(
        "subprocess" in diagnostic.message.lower()
        for diagnostic in result.errors
    )


@pytest.mark.security
def test_eval_rejected(config: CompileConfig) -> None:
    source = "def main(data):\n    eval('print(1)')\n"

    result = _compile(source, config)

    assert not result.success
    assert any(
        "eval" in diagnostic.message.lower()
        for diagnostic in result.errors
    )


@pytest.mark.security
def test_exec_rejected(config: CompileConfig) -> None:
    source = "def main(data):\n    exec('print(1)')\n"

    result = _compile(source, config)

    assert not result.success
    assert any(
        "exec" in diagnostic.message.lower()
        for diagnostic in result.errors
    )


@pytest.mark.security
def test_dynamic_import_rejected(config: CompileConfig) -> None:
    source = "def main(data):\n    os_module = __import__('os')\n"

    result = _compile(source, config)

    assert not result.success
    assert any(
        "__import__" in diagnostic.message
        for diagnostic in result.errors
    )


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
    assert any(
        "ctypes" in diagnostic.message.lower()
        for diagnostic in result.errors
    )


@pytest.mark.security
def test_safe_plugin_accepted(config: CompileConfig) -> None:
    source = (
        "import json\n"
        "import math\n"
        "def main(data):\n"
        "    return math.pi\n"
    )

    result = _compile(source, config)

    assert result.success


@pytest.mark.security
def test_multiple_violations_all_reported(config: CompileConfig) -> None:
    source = (
        "import os\n"
        "def main(data):\n"
        "    eval('1')\n"
        "    open('f')\n"
    )

    result = _compile(source, config)

    assert not result.success

    errors = [diagnostic for diagnostic in result.errors]

    assert len(errors) >= 2

    messages = [
        diagnostic.message.lower()
        for diagnostic in errors
    ]

    assert any("os" in message for message in messages)
    assert any("eval" in message for message in messages)
    assert any(
        "open" in message or "file" in message
        for message in messages
    )


@pytest.mark.security
def test_multiple_security_violation_codes_reported(
    config: CompileConfig,
) -> None:
    """Ensure multiple security violations produce their expected codes."""

    source = """
import os

def main(data):
    eval("1")
    __import__("json")
"""

    result = _compile(source, config)

    assert not result.success

    codes = {diagnostic.code for diagnostic in result.errors}

    assert "E200" in codes
    assert "E201" in codes
    assert "E203" in codes