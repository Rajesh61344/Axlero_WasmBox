import time
from wasmtime import Engine, Module

t0 = time.time()
engine = Engine()
# Engine with cache
t1 = time.time()
module = Module.from_file(engine, "python.wasm")
t2 = time.time()
print(f"Engine: {t1-t0:.3f}, Module compile: {t2-t1:.3f}")
