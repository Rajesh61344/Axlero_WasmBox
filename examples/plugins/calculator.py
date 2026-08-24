"""Calculator plugin — demonstrates math operations."""

import math


def main(data):
    """Perform a calculation based on the operation specified.

    Args:
        data: Dictionary with 'operation', 'a', and 'b' keys.

    Returns:
        Dictionary with the calculation result.
    """
    operation = data.get("operation", "add")
    a = data.get("a", 0)
    b = data.get("b", 0)

    operations = {
        "add": lambda: a + b,
        "subtract": lambda: a - b,
        "multiply": lambda: a * b,
        "divide": lambda: a / b if b != 0 else None,
        "power": lambda: math.pow(a, b),
        "sqrt": lambda: math.sqrt(a) if a >= 0 else None,
    }

    if operation not in operations:
        return {"error": f"Unknown operation: {operation}"}

    result = operations[operation]()
    return {
        "operation": operation,
        "a": a,
        "b": b,
        "result": result,
    }
