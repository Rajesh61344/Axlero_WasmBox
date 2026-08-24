import tempfile, os
from wasmtime import Store, WasiConfig, Module, Linker, Engine
engine = Engine()
store = Store(engine)
linker = Linker(engine)
linker.define_wasi()

wasi = WasiConfig()
wasi.inherit_stdout()
wasi.inherit_stderr()

# 100KB script
script = "print('Hello ' * 1000)\n" + "#" * 100000

wasi.argv = ["python", "-c", script]
store.set_wasi(wasi)
module = Module.from_file(engine, "python.wasm")
instance = linker.instantiate(store, module)
start = instance.exports(store)["_start"]
try:
    start(store)
    print("Success")
except Exception as e:
    print("Failed:", e)
