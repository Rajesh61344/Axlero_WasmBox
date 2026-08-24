"""Tests for the WasmBox compiler source transformer."""

import ast
import pytest

from backend.compiler.config import CompileConfig
from backend.compiler.models import AnalysisResult, HostFunctionRef
from backend.compiler.transformer import SourceTransformer
from backend.compiler.errors import TransformationError

def test_transform_simple() -> None:
    transformer = SourceTransformer()
    config = CompileConfig(compiler_version="1.0.0")
    analysis = AnalysisResult()
    source = "def main():\n    return 42\n"
    
    result = transformer.transform(source, analysis, config)
    
    assert "def main():" in result.source
    assert result.original_source == source
    assert not result.diagnostics

def test_transform_strips_shebang() -> None:
    transformer = SourceTransformer()
    config = CompileConfig()
    analysis = AnalysisResult()
    source = "#!/usr/bin/env python\ndef main():\n    pass\n"
    
    result = transformer.transform(source, analysis, config)
    
    assert "#!/usr/bin/env python" not in result.source
    assert "def main():" in result.source
    assert "\n" in result.source # The shebang line is replaced by empty newline

def test_transform_injects_metadata() -> None:
    transformer = SourceTransformer()
    config = CompileConfig(compiler_version="1.0.0")
    analysis = AnalysisResult()
    source = "def main():\n    pass\n"
    
    result = transformer.transform(source, analysis, config)
    
    assert "__wasmbox_plugin__ = True" in result.source
    assert "__wasmbox_version__ = '1.0.0'" in result.source

def test_transform_injects_host_bridge() -> None:
    transformer = SourceTransformer()
    config = CompileConfig()
    analysis = AnalysisResult(host_function_refs=[HostFunctionRef(name="fetch", line=2)])
    source = "def main():\n    fetch()\n"
    
    result = transformer.transform(source, analysis, config)
    
    assert "class _WasmBoxHost:" in result.source
    assert "host = _WasmBoxHost()" in result.source

def test_transform_no_host_bridge_when_not_needed() -> None:
    transformer = SourceTransformer()
    config = CompileConfig()
    analysis = AnalysisResult(host_function_refs=[])
    source = "def main():\n    pass\n"
    
    result = transformer.transform(source, analysis, config)
    
    assert "class _WasmBoxHost:" not in result.source

def test_transform_wraps_entrypoint() -> None:
    transformer = SourceTransformer()
    config = CompileConfig(entrypoint_function="main")
    analysis = AnalysisResult()
    source = "def main():\n    pass\n"
    
    result = transformer.transform(source, analysis, config)
    
    assert "def __wasmbox_wrapped_main(*args, **kwargs):" in result.source
    assert "return main(*args, **kwargs)" in result.source

def test_transform_normalizes_newlines() -> None:
    transformer = SourceTransformer()
    config = CompileConfig()
    analysis = AnalysisResult()
    source = "def main():\r\n    pass\r\n"
    
    result = transformer.transform(source, analysis, config)
    
    assert "\r\n" not in result.source
    assert "\n" in result.source

def test_transform_deterministic() -> None:
    transformer = SourceTransformer()
    config = CompileConfig()
    analysis = AnalysisResult()
    source = "def main():\n    pass\n"
    
    result1 = transformer.transform(source, analysis, config)
    result2 = transformer.transform(source, analysis, config)
    
    assert result1.source == result2.source

def test_transform_result_is_valid_python() -> None:
    transformer = SourceTransformer()
    config = CompileConfig()
    analysis = AnalysisResult()
    source = "def main():\n    pass\n"
    
    result = transformer.transform(source, analysis, config)
    
    # Should not raise SyntaxError
    ast.parse(result.source)
