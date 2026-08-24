"""Hello World plugin — the simplest valid WasmBox plugin."""


def main(data):
    """Process input data and return a greeting.

    Args:
        data: Input dictionary from the host.

    Returns:
        Dictionary with greeting message and doubled value.
    """
    return {
        "message": "Hello from WasmBox",
        "value": data["value"] * 2,
    }
