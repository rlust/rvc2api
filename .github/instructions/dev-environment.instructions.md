---
applyTo: "**"
---

# Development Environment

## Dependency Management
- poetry (Python dependencies in pyproject.toml)
- nix (reproducible environments via flake)
- Version-locked dependencies

## Dev Commands
```bash
poetry run python src/core_daemon/main.py  # Run server
poetry run pytest  # Tests
poetry run black src  # Format
poetry run ruff check .  # Lint
poetry run djlint src/core_daemon/web_ui/templates --reformat  # Format templates
```

## Setup
```bash
git clone https://github.com/USERNAME/rvc2api.git && cd rvc2api
nix develop  # Or: poetry install
cp .env.example .env
```
