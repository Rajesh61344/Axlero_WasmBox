from wasmtime import Store, WasiConfig, Module, Linker, Engine

engine = Engine()
store = Store(engine)
linker = Linker(engine)
linker.define_wasi()

wasi = WasiConfig()
wasi.inherit_stdout()
wasi.inherit_stderr()
wasi.argv = ["python", "-c", "import sys; print('Hello from inside WASM!', sys.version)"]
store.set_wasi(wasi)

module = Module.from_file(engine, "python.wasm")
instance = linker.instantiate(store, module)
start = instance.exports(store)["_start"]
start(store)
