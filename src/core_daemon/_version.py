import importlib.metadata

try:
    VERSION = importlib.metadata.version("rvc2api")
except importlib.metadata.PackageNotFoundError:
    # Fallback for when the package is not installed (e.g., during development tests)
    # You might want to read from pyproject.toml directly here if needed,
    # or set a placeholder version. For now, let's set a placeholder.
    VERSION = "0.0.0-dev"
