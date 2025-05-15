# GitHub Copilot Instructions for rvc2api

This document provides guidelines for GitHub Copilot Chat and contributors when working on the `rvc2api` project. It defines project architecture, coding conventions, documentation standards, and how to use integrated Model Context Protocol (MCP) tools such as `context7`, `perplexity`, and `github`.

---

## 🚐 Project Overview

`rvc2api` is a Python-based API and WebSocket service designed to interact with RV-C (Recreational Vehicle Controller Area Network) systems. It includes:

- A **FastAPI backend daemon**
- A **console-based client**
- A static **HTML web UI** (to be replaced with React)
- An RV-C decoder for CANbus messages

---

## 🗂️ Code Structure (Current)

This project uses a `src/` layout with these main packages:

- `src/common/`: Shared models and utilities
- `src/console_client/`: Command-line interface
- `src/core_daemon/`: FastAPI server, static frontend, settings
- `src/rvc_decoder/`: RV-C DGN decoding, mappings, and config

> 🛠️ This layout will migrate to a modular monolith (`backend/`, `webui/`, etc.) in a future refactor.

> 🔄 The backend will be refactored as follows:
>
> - `src/core_daemon/` → `backend/` (FastAPI app, API routes, service orchestrators)
> - `src/rvc_decoder/` → `backend/integrations/rvc/`
> - Shared business logic will move to `backend/services/`
> - Config parsing will consolidate under `backend/settings/`
>
> This change improves modularity, introduces runtime feature toggles, and prepares for future integrations like Victron Modbus.

---

## 🎨 Code Style & Documentation

- **Python**: Version 3.12+
- **Format**: `black` (line length: 100)
- **Linting**: `ruff` or `flake8`
- **Imports**: Group as `stdlib → third-party → local`
- **Typing**: Use full type hints and Pydantic models

### Docstring Style (PEP 257 or Google-style)

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

---

## ⚠️ Error Handling

- Catch and log expected exceptions with `logger.exception(...)`
- Avoid `except:` without re-raising or limiting scope
- Use custom error classes for integration-specific faults if needed

---

## 🧪 Testing

- Use `pytest` and `pytest-asyncio` for async test coverage
- Tests should mirror source file paths:
  - `tests/core_daemon/test_config.py` → `src/core_daemon/config.py`
- Mock CANbus, Modbus, or filesystem access in unit tests
- Add a brief docstring explaining each test’s intent

---

## 🌐 Web UI (Pre-Refactor)

- HTML templates: `src/core_daemon/web_ui/templates/`
- Static files: `src/core_daemon/web_ui/static/`
- Format templates with `djlint`
- Use ES6 and JSDoc in custom JavaScript

> This will later migrate to `webui/` with React + Vite.

---

## 🔧 Environment Variables

### CANbus Config
- `CAN_CHANNELS`: e.g. `can0,can1`
- `CAN_BUSTYPE`: e.g. `socketcan`
- `CAN_BITRATE`: e.g. `500000`
- `CAN_SPEC_PATH`: Path to RV-C JSON spec
- `CAN_MAP_PATH`: Path to device mapping YAML

### Server Config
- `RVC2API_TITLE`: Swagger UI title
- `RVC2API_SERVER_DESCRIPTION`: Description for FastAPI docs
- `RVC2API_ROOT_PATH`: Mount point if reverse-proxied
- `RVC2API_USER_COACH_INFO_PATH`: Path to custom coach YAML

### Misc
- `LOG_LEVEL`: Logging verbosity

---

## 📦 Dependency & Dev Environment

- Use `poetry` for Python dependencies
- All packages listed in `pyproject.toml`
- Use `nix` for reproducible local environments (flake-based)
- Version-lock all runtime-affecting dependencies

---

## 🧰 Common Dev Tasks

```bash
# Run the server
poetry run python src/core_daemon/main.py

# Run tests
poetry run pytest

# Format code
poetry run black src

# Lint code
poetry run ruff check .

# Format HTML templates
poetry run djlint src/core_daemon/web_ui/templates --reformat
```

---

## 🤖 MCP Tools in VS Code

This repo supports **GitHub Copilot Chat with custom tools** defined in `.vscode/mcp.json`.

These tools activate automatically when used in chat via `@toolname`:

### 🧠 `@context7`

Used for **project-aware lookups** from your actual source code.

✅ For Python:
- Understand FastAPI route patterns, WebSocket usage, settings layout
- Decode YAML file formats (e.g., `device_mapping.yml`)

✅ For Web UI:
- Show how components consume JSON from `/api/state`
- Look up WebSocket payload shapes
- Explain layout and Tailwind usage conventions

**Examples:**
```text
@context7 How is send_command() used in console_client?
@context7 What is the schema of /api/state?
@context7 What fields are in device_mapping.yml?
@context7 Show a WebSocket usage example in JavaScript
```

---

### 🌐 `@perplexity`

Use for **external research** about protocols, libraries, or practices.

✅ Examples:
```text
@perplexity What is PGN 0x1FEDA?
@perplexity How do I reconnect to a WebSocket in React?
@perplexity How does Victron Modbus framing work?
```

---

### 🧷 `@github`

Query repo info directly:
```text
@github Show open PRs with label 'enhancement'
@github What changed in rvc_interface.py recently?
```

---

## 🧠 Research Guidelines

When making design decisions or major changes:

1. Use **@context7** for internal code patterns and prior usage
2. Use **@perplexity** for protocol details, 3rd-party libraries, and integration patterns
3. Use **@github** for PRs/issues related to the change
4. Reference source URLs or findings in docstrings or PR descriptions

---

## ✅ Pull Request Expectations

- ✅ Tests for new logic
- ✅ Docs (inline or markdown) updated
- ✅ CI (lint, tests, format) passes
- ✅ Scoped, focused change
- ✅ Referenced design intent or MCP-backed research if applicable
