# RVC2API

Python-based API and WebSocket server for interacting with an RV-C (Recreational Vehicle Controller Area Network) bus. This project provides a backend daemon, a web UI for monitoring and control, and a console client for direct interaction.

## Overview

`rvc2api` is designed to bridge RV-C networks with modern applications by providing a structured API and real-time data streaming. It decodes RV-C messages, manages device states, and allows for sending commands to the RV-C bus.

## Key Components

*   **Core Daemon (`src/core_daemon/`):**
    *   `main.py`: Main application entry point using FastAPI.
    *   `can_manager.py`: Manages CAN bus interfaces (e.g., `socketcan`).
    *   `can_processing.py`: Handles incoming and outgoing CAN message processing and routing.
    *   `websocket.py`: Manages WebSocket connections for real-time updates to clients.
    *   `app_state.py`: Holds global application state, including entity states and configurations.
    *   `config.py`: Loads and manages application configuration.
    *   `metrics.py`: (If implemented) For collecting and exposing application metrics.
    *   `api_routers/`: Contains FastAPI routers for different API endpoints (CAN, entities, config).
*   **RV-C Decoder (`src/rvc_decoder/`):**
    *   `decode.py`: Contains the logic for decoding RV-C messages based on PGNs and SPNs, using configuration files from `config/`.
    *   `config/`: Contains `rvc.json` (RV-C specification details) and `device_mapping.yml` (custom device name mappings).
*   **Web UI (`src/core_daemon/web_ui/`):**
    *   `templates/index.html`: A single-page web application for displaying RV-C data, system status, and controlling entities.
    *   `static/`: CSS and potentially JavaScript assets for the web UI.
*   **Console Client (`src/console_client/`):**
    *   `console.py`: A command-line tool for interacting with the `rvc2api` daemon.

## Features

*   **FastAPI Backend:** Robust and modern API framework.
*   **WebSocket Streaming:** Real-time updates of RV-C data and entity states to connected clients.
*   **RV-C Message Decoding:** Translates raw CAN bus messages into human-readable RV-C data.
*   **Entity Management:** Represents RV-C devices and their states as controllable entities.
*   **Web-based UI:** Provides a user-friendly interface for monitoring and interaction.
*   **Configuration Driven:** Uses YAML and JSON files for RV-C specifications and device mappings.
*   **Poetry for Dependency Management:** Ensures reproducible builds and development environments.

## Prerequisites

*   Python 3.10+
*   Poetry (for dependency management and running scripts)
*   A configured CAN bus interface (e.g., `socketcan` on Linux).

## Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/carpenike/rvc2api
    cd rvc2api
    ```

2.  **Install dependencies using Poetry:**
    ```bash
    poetry install
    ```

3.  **Configuration:**
    *   The main application configuration is typically handled via environment variables or a `.env` file (not included in the repo, create one if needed).
    *   RV-C decoder configurations are in `src/rvc_decoder/config/`:
        *   `rvc.json`: Based on the RV-C specification.
        *   `device_mapping.yml`: Customize device names and interpretations here.
    *   The CAN interface used by the daemon is usually configured within the application settings (e.g., environment variables for `CAN_INTERFACE`).

4.  **Running the application:**
    *   **Core Daemon:**
        ```bash
        poetry run python src/core_daemon/main.py
        ```
        Or, if you have a run script defined in `pyproject.toml` (e.g., `poetry run start`):
        ```bash
        poetry run start
        ```
        The API server will typically start on `http://localhost:8000` (or as configured).
        The Web UI will be accessible at `http://localhost:8000/`.

    *   **Console Client:**
        ```bash
        poetry run python src/console_client/console.py --help
        ```
        Follow the client's help instructions to connect to the daemon.

## Development

*   **Activate the virtual environment:**
    ```bash
    poetry shell
    ```
*   **Running tests:**
    ```bash
    poetry run pytest
    ```
*   **Linting/Formatting:** (Assuming tools like Black, Flake8, or Ruff are configured in `pyproject.toml`)
    ```bash
    poetry run black .
    poetry run ruff check .
    ```

## API Endpoints

(Refer to the FastAPI Swagger UI, typically at `http://localhost:8000/docs`, for a detailed API specification once the server is running.)

Key endpoint groups might include:
*   `/api/can/`: For CAN interface status and raw message sending (if enabled).
*   `/api/entities/`: To list and control RV-C entities.
*   `/api/config/`: To view or update parts of the configuration.
*   `/ws`: WebSocket endpoint for real-time data.

## Contributing

Contributions are welcome! Please follow standard coding practices, ensure tests pass, and consider updating documentation for any new features or changes.

## License

This project is licensed under the terms of the [LICENSE](./LICENSE) file.
