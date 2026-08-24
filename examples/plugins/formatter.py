"""Formatter plugin — demonstrates string processing."""

import json
import re


def main(data):
    """Format input data according to the specified template.

    Args:
        data: Dictionary with 'template' and 'values' keys.

    Returns:
        Dictionary with formatted output.
    """
    template = data.get("template", "Hello, {name}!")
    values = data.get("values", {})

    try:
        formatted = template.format(**values)
    except KeyError as e:
        return {"error": f"Missing template variable: {e}"}

    # Count words
    words = re.findall(r'\w+', formatted)

    return {
        "formatted": formatted,
        "word_count": len(words),
        "char_count": len(formatted),
        "original_template": template,
    }
