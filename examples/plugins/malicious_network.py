"""MALICIOUS PLUGIN — Network access attempt.

This plugin intentionally attempts to create a network socket.
The WasmBox compiler MUST reject this plugin during validation.

Expected result: REJECTED — network access is forbidden.
"""

import socket


def main(data):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("example.com", 80))
    s.send(b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n")
    return s.recv(4096).decode()
