---
applyTo: "tests/**/*.py"
---

# Testing Guidelines

- Use `pytest` and `pytest-asyncio` for async test coverage
- Tests should mirror source file paths:
  - `tests/core_daemon/test_config.py` → `src/core_daemon/config.py`
- Mock CANbus, Modbus, or filesystem access in unit tests
- Add a brief docstring explaining each test's intent

## Example Test

```python
def test_canbus_command_send():
    """Test that CANbus commands are properly formatted and transmitted."""
    # Setup test fixtures
    mock_can_bus = MockCANBus()
    interface = CANInterface(bus=mock_can_bus)

    # Execute the function under test
    result = interface.send_command("1FEBD,1,255,0,0,0,0,0,0")

    # Verify the results
    assert result is True
    assert mock_can_bus.last_message.arbitration_id == 0x1FEBD
    assert mock_can_bus.last_message.data == bytes([1, 255, 0, 0, 0, 0, 0, 0])
```
