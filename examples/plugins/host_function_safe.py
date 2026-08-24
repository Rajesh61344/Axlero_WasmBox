"""Host function usage plugin — demonstrates safe host API calls.

This plugin calls approved host functions (log).
Expected result: COMPILED SUCCESSFULLY, host_functions: ["log"] in manifest.
"""


def main(data):
    host.log("Processing data in plugin")
    result = data.get("value", 0) * 3
    host.log(f"Computed result: {result}")
    return {"result": result, "status": "ok"}
