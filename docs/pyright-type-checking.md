# Pyright Type Checking Guide

This document provides guidance on working with Pyright, our standardized Python type checker.

## Basic Usage

Run type checking across the entire codebase:

```bash
npx pyright src
```

## Configuration

Pyright is configured in two places:

1. **pyrightconfig.json**: Primary configuration file at the project root
2. **pyproject.toml**: Contains additional Pyright settings under the `[tool.pyright]` section

### Key Configuration Settings

- `typeCheckingMode`: Set to "basic" for reasonable type checking without being overly strict
- `reportMissingImports`: Flags imports that can't be resolved
- `reportMissingTypeStubs`: Disabled to avoid noise from third-party packages without type stubs
- `pythonVersion`: Set to match our minimum supported Python version
- `stubPath`: Points to our custom type stubs directory

## Custom Type Stubs

For third-party libraries with missing or incomplete type information, we maintain custom type stubs in the `typings/` directory:

- **FastAPI stubs**: Enhanced WebSocket type definitions
- **httpx stubs**: Additional typing for HTTP client functions

## Common Type Issues and Solutions

### Union Types

Use Python's built-in `|` operator for union types (Python 3.10+):

```python
# Preferred
def process_input(value: str | int | None) -> str:
    ...

# Instead of
from typing import Union
def process_input(value: Union[str, int, None]) -> str:
    ...
```

### TypedDict for Dictionary Structure

Use TypedDict for dictionaries with specific key/value structures:

```python
from typing import TypedDict

class UserData(TypedDict):
    name: str
    age: int
    active: bool

def process_user(user: UserData) -> None:
    ...
```

### Protocol for Duck Typing

Use Protocol for structural subtyping (duck typing):

```python
from typing import Protocol

class CanProcess(Protocol):
    def process(self, data: bytes) -> None: ...

def run_processor(processor: CanProcess, data: bytes) -> None:
    processor.process(data)
```

### Type Narrowing

Use type guards for narrowing types:

```python
def is_string_dict(obj: dict[str, object]) -> bool:
    return all(isinstance(v, str) for v in obj.values())

data: dict[str, object] = {"a": "1", "b": 2}
if is_string_dict(data):  # Pyright understands this narrows the type
    process_strings(data)  # Error avoided
```

### Literal Types

Use Literal for constraining string/number values:

```python
from typing import Literal

def set_log_level(level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]) -> None:
    ...
```

## Working with FastAPI and Pydantic

### Pydantic Models

Pyright works well with Pydantic v2 models:

```python
from pydantic import BaseModel, Field

class Item(BaseModel):
    name: str
    price: float = Field(gt=0)
    is_offer: bool = False
```

### FastAPI Route Parameters

Type annotations for FastAPI routes should use the appropriate types:

```python
from fastapi import FastAPI, Path, Query

app = FastAPI()

@app.get("/items/{item_id}")
async def read_item(
    item_id: int = Path(..., gt=0),
    q: str | None = Query(None, max_length=50),
):
    ...
```

## VS Code Integration

For the best experience in VS Code:

1. Install the Pylance extension
2. Set the default Python type checker to Pyright in settings.json:

```json
{
  "python.analysis.typeCheckingMode": "basic",
  "python.analysis.diagnosticMode": "workspace"
}
```

## CI Integration

In CI pipelines, we run Pyright to check types:

```bash
npx pyright src
```

This ensures all PRs maintain type safety throughout the codebase.
