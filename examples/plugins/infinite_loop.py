"""MALICIOUS PLUGIN — Infinite loop.

This plugin intentionally enters an infinite loop.
The WasmBox compiler MAY accept this (infinite loops are not syntax errors),
but the Wasmtime runtime MUST terminate execution via fuel/epoch limits.

Expected result: COMPILATION MAY SUCCEED, RUNTIME MUST TERMINATE.
"""


def main(data):
    while True:
        pass
