# Code Quality Tools

This document outlines the code quality tools used in the `rvc2api` project.

## Python Code Quality Tools

### Ruff

[Ruff](https://github.com/astral-sh/ruff) is our primary Python linting tool. It's a fast, comprehensive linter written in Rust that replaces Flake8 and many of its plugins.

#### Key features

- 10-100x faster than Flake8
- Includes functionality from multiple Flake8 plugins
- Can automatically fix many issues
- Import sorting (replacing isort)
- Configurable through `pyproject.toml`

#### Usage

```bash
# Check your code
poetry run ruff check .

# Apply auto-fixes
poetry run ruff check --fix .
```

### Black

[Black](https://github.com/psf/black) is our Python code formatter. It enforces a consistent style by reformatting your code to conform to its rules.

#### Key features

- Deterministic formatting
- Minimal configuration
- Compatible with Ruff

#### Usage

```bash
# Format your code
poetry run black src tests
```

### Pyright/Pylance

[Pyright](https://github.com/microsoft/pyright) is our static type checker for Python, used in VS Code via the Pylance extension.

#### Key features

- Fast, incremental type checking
- Excellent IDE integration
- Strong support for modern Python typing features
- Better performance for larger codebases
- Native support for FastAPI and Pydantic type annotations

#### Usage

```bash
# Type check your code
npx pyright src

# Or in VS Code:
# Use the built-in type checking with Pylance
```

## Pre-commit Integration

These tools are integrated into our [pre-commit](https://pre-commit.com/) configuration, ensuring code quality checks run automatically before each commit.

To set up pre-commit:

```bash
# Install pre-commit hooks
poetry run pre-commit install
```

## Custom Type Stubs

The project includes custom type stubs in the `typings/` directory to enhance type checking and IDE support, particularly for third-party libraries.

### FastAPI Type Stubs

We maintain custom type stubs for FastAPI to provide better typing for WebSocket components and other FastAPI features.

#### Organization

- `typings/fastapi/__init__.py` - Implementation file with detailed docstrings
- `typings/fastapi/__init__.pyi` - Type stub file with concise type definitions

#### Special Configuration

These files have specific lint exceptions in `pyproject.toml`:

```toml
[tool.ruff.lint.per-file-ignores]
# Allow function names that don't follow snake_case for FastAPI compatibility
# Also allow exception names without Error suffix to match FastAPI's conventions
"typings/fastapi/__init__.py" = ["N802", "N818"]
"typings/fastapi/__init__.pyi" = ["N802", "N818"]
# Allow relative imports in the typings directory for proper type stub organization
"typings/**/*.py" = ["TID252"]
"typings/**/*.pyi" = ["TID252"]
```

These exceptions allow:

- Non-snake_case function names (like `Body()`) to match FastAPI's API
- Exception names without the "Error" suffix (like `WebSocketDisconnect`) to match FastAPI's conventions
- Relative imports in type stub files for proper organization

For more details, see `typings/fastapi/README.md`.

## Why We Chose These Tools

- **Ruff over Flake8**: Ruff is significantly faster and includes all the functionality of Flake8 plus much more. It also has better integration with modern Python tooling.
- **Black for formatting**: Black is the industry standard for Python code formatting, offering consistent results with minimal configuration.
- **Pyright for type checking**: Pyright offers excellent performance, strong IDE integration via VS Code's Pylance extension, and better support for modern Python typing features, especially with FastAPI and Pydantic.
- **Custom Type Stubs**: For better IDE support and type checking with libraries like FastAPI.

## VS Code Integration

VS Code tasks are configured for these tools:

- **Format Code (Black)**: Formats Python code
- **Lint (Ruff)**: Runs Ruff linting with fix capability
