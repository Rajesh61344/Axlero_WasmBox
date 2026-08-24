"""MALICIOUS PLUGIN — Unauthorized host function attempt.

This plugin attempts to call an unauthorized host function (delete_database).
Expected result: HOST_FUNCTION_NOT_ALLOWED during host function validation.
"""


def main(data):
    host.delete_database()
    return {"status": "deleted"}
