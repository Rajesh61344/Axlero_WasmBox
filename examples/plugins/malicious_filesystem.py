"""MALICIOUS PLUGIN — Filesystem access attempt.

This plugin intentionally attempts to read /etc/passwd.
The WasmBox compiler MUST reject this plugin during validation.

Expected result: REJECTED — filesystem access is forbidden.
"""


def main(data):
    with open("/etc/passwd") as f:
        return f.read()
