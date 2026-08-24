import os
import tempfile
from wasmtime import Store, WasiConfig, Module, Linker, Engine

engine = Engine()
store = Store(engine)
linker = Linker(engine)
linker.define_wasi()

with tempfile.NamedTemporaryFile("w", delete=False) as f:
    f.write('{"value": 42}')
    temp_stdin = f.name

wasi = WasiConfig()
wasi.inherit_stdout()
wasi.inherit_stderr()
wasi.stdin_file = temp_stdin

script = """
import sys, json
data = json.load(sys.stdin)
print(json.dumps({"result": data["value"] * 2}))
"""
wasi.argv = ["python", "-c", script]
store.set_wasi(wasi)

module = Module.from_file(engine, "python.wasm")
instance = linker.instantiate(store, module)
start = instance.exports(store)["_start"]
start(store)
os.unlink(temp_stdin)
