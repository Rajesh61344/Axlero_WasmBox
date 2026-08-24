import ast
import pytest
from backend.compiler.validator import SecurityValidator
from backend.compiler.config import SecurityPolicy

def get_ast(source):
    return ast.parse(source)

def test_validate_safe_plugin(simple_plugin_source, default_policy):
    tree = get_ast(simple_plugin_source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, simple_plugin_source, default_policy)
    
    assert len(diagnostics) == 0

def test_validate_forbidden_import_os(default_policy):
    source = "import os\ndef main(): pass"
    tree = get_ast(source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, source, default_policy)
    
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "E200"
    assert "os" in diagnostics[0].message

def test_validate_forbidden_import_socket(malicious_network_source, default_policy):
    tree = get_ast(malicious_network_source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, malicious_network_source, default_policy)
    
    assert len(diagnostics) > 0
    assert diagnostics[0].code == "E200"
    assert "socket" in diagnostics[0].message

def test_validate_forbidden_import_subprocess(default_policy):
    source = "import subprocess\ndef main(): pass"
    tree = get_ast(source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, source, default_policy)
    
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "E200"

def test_validate_from_import(default_policy):
    source = "from os import system"
    tree = get_ast(source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, source, default_policy)
    
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "E200"

def test_validate_forbidden_builtin_eval(default_policy):
    source = "def main(): eval('1 + 1')"
    tree = get_ast(source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, source, default_policy)
    
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "E201"
    assert "eval" in diagnostics[0].message

def test_validate_forbidden_builtin_exec(default_policy):
    source = "def main(): exec('x = 1')"
    tree = get_ast(source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, source, default_policy)
    
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "E201"
    assert "exec" in diagnostics[0].message

def test_validate_forbidden_builtin_open(malicious_filesystem_source, default_policy):
    tree = get_ast(malicious_filesystem_source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, malicious_filesystem_source, default_policy)
    
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "E201"
    assert "open" in diagnostics[0].message

def test_validate_forbidden_builtin_import(default_policy):
    source = "def main(): __import__('os')"
    tree = get_ast(source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, source, default_policy)
    
    # __import__ can be caught by builtin check (E201) or dynamic import check (E203)
    assert len(diagnostics) >= 1
    assert any(d.code in ["E201", "E203"] for d in diagnostics)

def test_validate_dynamic_import(default_policy):
    source = "import importlib\ndef main(): importlib.import_module('os')"
    tree = get_ast(source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, source, default_policy)
    
    # E200 for importlib (if forbidden) and E203 for importlib.import_module
    assert len(diagnostics) >= 1
    assert any(d.code == "E203" for d in diagnostics)

def test_validate_star_import(default_policy):
    source = "from math import *"
    tree = get_ast(source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, source, default_policy)
    
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "E202"

def test_validate_dunder_access(default_policy):
    source = "def main(): return obj.__builtins__"
    tree = get_ast(source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, source, default_policy)
    
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "E205"

def test_validate_globals_access(default_policy):
    source = "def main(): return globals()['open']"
    tree = get_ast(source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, source, default_policy)
    
    # Accessing restricted builtin 'globals' (E207) and dict access on globals (E208)
    assert any(d.code == "E208" for d in diagnostics)

def test_validate_getattr_danger(default_policy):
    source = "def main(): getattr(os, 'system')"
    tree = get_ast(source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, source, default_policy)
    
    # E207 for getattr
    assert len(diagnostics) >= 1
    assert any(d.code == "E207" for d in diagnostics)

def test_validate_allowed_import_json(default_policy):
    source = "import json\ndef main(): pass"
    tree = get_ast(source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, source, default_policy)
    
    assert len(diagnostics) == 0

def test_validate_allowed_import_math(default_policy):
    source = "import math\ndef main(): pass"
    tree = get_ast(source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, source, default_policy)
    
    assert len(diagnostics) == 0

def test_validate_configurable_policy(permissive_policy):
    source = "import os\ndef main():\n    eval('1')\n    importlib.import_module('sys')"
    tree = get_ast(source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, source, permissive_policy)
    
    assert len(diagnostics) == 0

def test_validate_multiple_violations(default_policy):
    source = """
import os
def main():
    eval('1')
    return obj.__class__
"""
    tree = get_ast(source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, source, default_policy)
    
    codes = [d.code for d in diagnostics]
    assert "E200" in codes  # os
    assert "E201" in codes  # eval
    assert "E205" in codes  # __class__

def test_validate_indirect_builtins_access(default_policy):
    source = "def main(): builtins.open('foo')"
    tree = get_ast(source)
    validator = SecurityValidator()
    diagnostics = validator.validate(tree, source, default_policy)
    
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "E208"
