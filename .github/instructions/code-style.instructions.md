---
applyTo: "**/*.py"
---

# Code Style & Documentation

- **Python**: Version 3.12+
- **Format**: `black` (line length: 100)
- **Linting**: `ruff` or `flake8`
- **Imports**: Group as `stdlib → third-party → local`
- **Typing**: Use full type hints and Pydantic models

## Docstring Style (PEP 257 or Google-style)

```python
def send_command(command: str) -> bool:
    """
    Sends a command to the CANbus.

    Args:
        command: The command to transmit.

    Returns:
        True if acknowledged, False otherwise.
    """
```

- Include **module-level docstrings** summarizing file purpose.
- Document YAML schemas in comments when used (e.g., `device_mapping.yml`).

## Error Handling

- Catch and log expected exceptions with `logger.exception(...)`
- Avoid `except:` without re-raising or limiting scope
- Use custom error classes for integration-specific faults if needed
