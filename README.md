# RVC2API

Python-based API and WebSocket server for interacting with an RV-C (Recreational Vehicle Controller Area Network) bus. This project provides a backend daemon, a web UI for monitoring and control, and a console client for direct interaction.

## Overview

`rvc2api` is designed to bridge RV-C networks with modern applications by providing a structured API and real-time data streaming. It decodes RV-C messages, manages device states, and allows for sending commands to the RV-C bus.

## Key Components

- **Core Daemon (`src/core_daemon/`):**
  - `main.py`: Main application entry point using FastAPI.
  - `can_manager.py`: Manages CAN bus interfaces (e.g., `socketcan`).
  - `can_processing.py`: Handles incoming and outgoing CAN message processing and routing.
  - `websocket.py`: Manages WebSocket connections for real-time updates to clients.
  - `app_state.py`: Holds global application state, including entity states and configurations.
  - `config.py`: Loads and manages application configuration.
  - `metrics.py`: For collecting and exposing application metrics.
  - `api_routers/`: Contains FastAPI routers for different API endpoints (CAN, entities, config).
- **RV-C Decoder (`src/rvc_decoder/`):**
  - `decode.py`: Contains the logic for decoding RV-C messages based on PGNs and SPNs, using configuration files from `config/`.
  - `config/`: Contains `rvc.json` (RV-C specification details) and `device_mapping.yml` (custom device name mappings).
- **React Frontend (`web_ui/`):**
  - Modern React SPA built with Vite and Tailwind CSS
  - Communicates with the backend via REST API and WebSockets
  - See [Frontend Development Guide](docs/frontend-development.md) for details
- **Console Client (`src/console_client/`):**
  - `console.py`: A command-line tool for interacting with the `rvc2api` daemon.

## Documentation

- **Deployment & Integration**

  - [NixOS Integration Guide](docs/nixos-integration.md)
  - [NixOS Module Configuration Reference](docs/nixos-module.md)
  - [Environment Variable Integration](docs/environment-variable-integration.md)
  - [React Frontend Deployment](docs/react-deployment.md)

- **Development**

  - [Development Environments Setup](docs/development-environments.md)
  - [Frontend Development Guide](docs/frontend-development.md)
  - [VS Code Extensions](docs/vscode-extensions.md)
  - [Model Context Protocol Tools Setup](docs/mcp-tools-setup.md)
  - [Poetry2Nix Integration](docs/poetry2nix-integration.md)

- **Quality Tools**
  - [Code Quality Tools](docs/code-quality-tools.md)
  - [Pre-commit and GitHub Actions](docs/pre-commit-and-actions.md)

## Features

- **FastAPI Backend:** Robust and modern API framework.
- **WebSocket Streaming:** Real-time updates of RV-C data and entity states to connected clients.
- **RV-C Message Decoding:** Translates raw CAN bus messages into human-readable RV-C data.
- **Entity Management:** Represents RV-C devices and their states as controllable entities.
- **Web-based UI:** Provides a user-friendly interface for monitoring and interaction.
- **Configuration Driven:** Uses YAML and JSON files for RV-C specifications and device mappings.
- **Poetry for Dependency Management:** Ensures reproducible builds and development environments.

## Prerequisites

- Python 3.10+
- Poetry (for dependency management and running scripts)
- A configured CAN bus interface (e.g., `socketcan` on Linux).

## Installation & Setup

### Option 1: Using NixOS

If you're using NixOS, you can easily integrate `rvc2api` using the provided NixOS module:

- [NixOS Integration Guide](docs/nixos-integration.md)
- [NixOS Module Configuration Reference](docs/nixos-module.md)

### Option 2: Manual Setup

For detailed instructions on setting up development environments, see:

- [Development Environments Guide](docs/development-environments.md)

For quick start:

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/carpenike/rvc2api
    cd rvc2api
    ```

2.  **Install dependencies:**

    ```bash
    # Backend
    poetry install

    # Frontend
    cd web_ui && npm install
    ```

3.  **Running the application:**

    - **Core Daemon:**

      ```bash
      # Using the convenience script (recommended):
      poetry run python run_server.py

      # Direct module execution (for development):
      poetry run python src/core_daemon/main.py
      ```

      The API server will typically start on `http://localhost:8000` (or as configured).

    - **Frontend Development Server:**

      ```bash
      cd web_ui && npm run dev
      ```

      The frontend dev server will be accessible at `http://localhost:5173/`.

    - **Console Client:**
      ```bash
      poetry run python src/console_client/console.py --help
      ```
      Follow the client's help instructions to connect to the daemon.

## Development

- **Activate the virtual environment:**
  ```bash
  poetry shell
  ```
- **Running tests:**
  ```bash
  poetry run pytest
  ```
- **Linting/Formatting:** (See [Code Quality Tools](docs/code-quality-tools.md) for details)
  ```bash
  poetry run black .  # Formatting
  poetry run ruff check .  # Linting (replaces Flake8)
  ```

## API Endpoints

(Refer to the FastAPI Swagger UI, typically at `http://localhost:8000/docs`, for a detailed API specification once the server is running.)

Key endpoint groups might include:

- `/api/can/`: For CAN interface status and raw message sending (if enabled).
- `/api/entities/`: To list and control RV-C entities.
- `/api/config/`: To view or update parts of the configuration.
- `/ws`: WebSocket endpoint for real-time data.

## Development Tools & Resources

We have enhanced the development environment with several tools to streamline the workflow:

- **VS Code Integration**: Preconfigured settings, tasks, and recommended extensions

  - See [VS Code Extensions](docs/vscode-extensions.md) for recommended extensions
  - Use VS Code tasks for common operations (Run server, tests, format code, etc.)

- **MCP Tools**: AI-assisted development with Model Context Protocol

  - See [MCP Tools Setup](docs/mcp-tools-setup.md) for information on using @context7, @perplexity, and @github tools

- **Poetry2nix Integration**: Proposed integration between Poetry and Nix

  - See [Poetry2nix Integration](docs/poetry2nix-integration.md) for implementation details

- **Enhanced Development Environment**: Comprehensive development setup
  - See [Enhanced Development Environment](docs/enhanced-dev-environment.md) for overview
- **Pre-commit and CI/CD**: Quality assurance and automation
  - See [Pre-commit and GitHub Actions](docs/pre-commit-and-actions.md) for configuration details
  - See [Code Quality Tools](docs/code-quality-tools.md) for information about our Python linting and formatting tools
- **Custom Type Stubs**: Enhanced type checking and IDE support
  - Located in `typings/` directory
  - Includes custom type definitions for FastAPI WebSocket components
  - See `typings/fastapi/README.md` for details on organization and usage
- **NixOS Integration**: Using rvc2api in other NixOS systems
  - See [NixOS Integration](docs/nixos-integration.md) for how to include rvc2api in other flakes and NixOS configurations

## Contributing

Contributions are welcome! Please follow standard coding practices, ensure tests pass, and consider updating documentation for any new features or changes. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the terms of the [LICENSE](./LICENSE) file.
