import ast
import pytest

from backend.compiler.analyzer import StaticAnalyzer
from backend.compiler.config import CompileConfig
from backend.compiler.models import DependencyCategory


def get_ast(source):
    return ast.parse(source)


def test_analyze_simple(simple_plugin_source, default_config):
    tree = get_ast(simple_plugin_source)
    analyzer = StaticAnalyzer()
    result = analyzer.analyze(tree, simple_plugin_source, default_config)

    assert len(result.functions) == 1
    assert result.functions[0].name == "main"
    assert result.node_count > 0
    assert result.max_nesting_depth > 0


def test_analyze_imports(default_config):
    source = "import json\nimport math as m\ndef main(): pass"
    tree = get_ast(source)
    analyzer = StaticAnalyzer()
    result = analyzer.analyze(tree, source, default_config)

    assert len(result.imports) == 2
    assert result.imports[0].module == "json"
    assert result.imports[1].module == "math"
    assert result.imports[1].alias == "m"


def test_analyze_from_imports(default_config):
    source = "from collections import defaultdict, Counter\ndef main(): pass"
    tree = get_ast(source)
    analyzer = StaticAnalyzer()
    result = analyzer.analyze(tree, source, default_config)

    assert len(result.imports) == 1
    assert result.imports[0].module == "collections"
    assert result.imports[0].names == ["defaultdict", "Counter"]
    assert result.imports[0].is_from_import is True


def test_analyze_functions(calculator_plugin_source, default_config):
    tree = get_ast(calculator_plugin_source)
    analyzer = StaticAnalyzer()
    result = analyzer.analyze(tree, calculator_plugin_source, default_config)

    assert len(result.functions) == 2

    names = [f.name for f in result.functions]
    assert "add" in names
    assert "main" in names

    add_func = next(f for f in result.functions if f.name == "add")
    assert add_func.args == ["a", "b"]


def test_analyze_classes(default_config):
    source = """
class MyPlugin:
    def __init__(self):
        self.state = 0

    def process(self):
        pass

def main():
    pass
"""
    tree = get_ast(source)
    analyzer = StaticAnalyzer()
    result = analyzer.analyze(tree, source, default_config)

    assert result.has_class_definitions is True
    assert len(result.classes) == 1
    assert result.classes[0].name == "MyPlugin"
    assert set(result.classes[0].methods) == {"__init__", "process"}


def test_analyze_entrypoint(simple_plugin_source, default_config):
    tree = get_ast(simple_plugin_source)
    analyzer = StaticAnalyzer()
    result = analyzer.analyze(tree, simple_plugin_source, default_config)

    assert "main" in result.entrypoints

    main_func = next(
        f for f in result.functions
        if f.name == "main"
    )

    assert main_func.is_entrypoint is True


def test_analyze_host_functions(host_function_source, default_config):
    tree = get_ast(host_function_source)
    analyzer = StaticAnalyzer()
    result = analyzer.analyze(
        tree,
        host_function_source,
        default_config
    )

    assert len(result.host_function_refs) == 1
    assert result.host_function_refs[0].name == "log"


def test_analyze_global_variables(default_config):
    source = """
counter = 0
API_KEY: str = "123"

def main():
    pass
"""
    tree = get_ast(source)
    analyzer = StaticAnalyzer()
    result = analyzer.analyze(tree, source, default_config)

    assert set(result.global_variables) == {
        "counter",
        "API_KEY",
    }


def test_analyze_loops(infinite_loop_source, default_config):
    tree = get_ast(infinite_loop_source)
    analyzer = StaticAnalyzer()
    result = analyzer.analyze(
        tree,
        infinite_loop_source,
        default_config
    )

    assert result.has_loops is True


def test_analyze_nesting_depth(default_config):
    source = """
def main():
    if True:
        if True:
            pass
"""
    tree = get_ast(source)
    analyzer = StaticAnalyzer()
    result = analyzer.analyze(tree, source, default_config)

    # Module -> FunctionDef -> If -> If -> Pass
    assert result.max_nesting_depth >= 3


def test_analyze_node_count(simple_plugin_source, default_config):
    tree = get_ast(simple_plugin_source)
    analyzer = StaticAnalyzer()
    result = analyzer.analyze(
        tree,
        simple_plugin_source,
        default_config
    )

    assert result.node_count > 5


def test_analyze_dependencies(default_config):
    source = """
import os
import json
import yaml
"""
    tree = get_ast(source)
    analyzer = StaticAnalyzer()
    result = analyzer.analyze(tree, source, default_config)

    deps = {
        d.name: d.category
        for d in result.dependencies
    }

    assert deps.get("os") == DependencyCategory.FORBIDDEN
    assert deps.get("json") == DependencyCategory.STDLIB
    assert deps.get("yaml") == DependencyCategory.UNSUPPORTED


def test_analyze_nested_dependency_classification(default_config):
    source = """
import os.path
import json
import yaml.safe_load

def main():
    pass
"""
    tree = get_ast(source)
    analyzer = StaticAnalyzer()
    result = analyzer.analyze(tree, source, default_config)

    deps = {
        d.name: d.category
        for d in result.dependencies
    }

    assert deps.get("os") == DependencyCategory.FORBIDDEN
    assert deps.get("json") == DependencyCategory.STDLIB
    assert deps.get("yaml") == DependencyCategory.UNSUPPORTED