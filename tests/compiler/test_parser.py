import pytest
from backend.compiler.parser import PluginParser
from backend.compiler.errors import ParseError
from backend.compiler.config import CompilationLimits

def test_parse_valid_simple(simple_plugin_source):
    parser = PluginParser()
    result = parser.parse(simple_plugin_source)
    assert result is not None
    assert result.source == simple_plugin_source
    
    entrypoint_info = next((d for d in result.diagnostics if "Entrypoint" in d.message), None)
    assert entrypoint_info is not None

def test_parse_valid_with_imports():
    source = """
import json
import math

def main(data):
    return json.dumps({"pi": math.pi})
"""
    parser = PluginParser()
    result = parser.parse(source)
    assert result is not None

def test_parse_syntax_error():
    source = """
def main(data)
    return True
"""
    parser = PluginParser()
    with pytest.raises(ParseError) as exc_info:
        parser.parse(source)
    
    assert exc_info.value.code == "E005"
    assert exc_info.value.line == 2
    assert "expected ':'" in exc_info.value.message or "invalid syntax" in exc_info.value.message

def test_parse_empty_source():
    parser = PluginParser()
    with pytest.raises(ParseError) as exc_info:
        parser.parse("")
    
    assert exc_info.value.code == "E001"
    assert "empty" in exc_info.value.message

def test_parse_unicode_source():
    source = """
def main(data):
    return "안녕하세요, 🌍"
"""
    parser = PluginParser()
    result = parser.parse(source)
    assert result is not None

def test_parse_large_source():
    limits = CompilationLimits(max_source_bytes=10)
    parser = PluginParser(limits=limits)
    source = "def main(): pass\n" * 10
    
    with pytest.raises(ParseError) as exc_info:
        parser.parse(source)
    
    assert exc_info.value.code == "E003"
    assert "exceeds maximum allowed" in exc_info.value.message

def test_parse_too_many_lines():
    limits = CompilationLimits(max_source_lines=5)
    parser = PluginParser(limits=limits)
    source = "def main():\n    pass\n\n\n\n\n\n"
    
    with pytest.raises(ParseError) as exc_info:
        parser.parse(source)
    
    assert exc_info.value.code == "E004"
    assert "length" in exc_info.value.message

def test_parse_entrypoint_detected(simple_plugin_source):
    parser = PluginParser(entrypoint_name="main")
    result = parser.parse(simple_plugin_source)
    
    has_entrypoint = any("Entrypoint function 'main' found" in d.message for d in result.diagnostics)
    assert has_entrypoint is True

def test_parse_missing_entrypoint():
    source = """
def other_func():
    pass
"""
    parser = PluginParser(entrypoint_name="main")
    result = parser.parse(source)
    
    has_entrypoint = any("Entrypoint function 'main' found" in d.message for d in result.diagnostics)
    assert has_entrypoint is False

def test_parse_multiple_functions(calculator_plugin_source):
    parser = PluginParser()
    result = parser.parse(calculator_plugin_source)
    
    diag = next((d for d in result.diagnostics if "Parsed" in d.message), None)
    assert diag is not None
    assert "2 functions" in diag.message

def test_parse_deeply_nested():
    limits = CompilationLimits(max_nesting_depth=3)
    parser = PluginParser(limits=limits)
    
    source = """
def main():
    if True:
        if True:
            if True:
                pass
"""
    with pytest.raises(ParseError) as exc_info:
        parser.parse(source)
    
    assert exc_info.value.code == "E007"
    assert "nesting depth" in exc_info.value.message
