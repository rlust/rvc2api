# GitHub Copilot Instructions for rvc2api

This document provides key information for GitHub Copilot to understand the `rvc2api` project architecture and coding patterns. Detailed domain-specific instructions are organized in `.github/instructions/*.instructions.md` files.

## Project Summary

`rvc2api` is a Python-based API and WebSocket service for RV-C (Recreational Vehicle Controller Area Network) systems:
- **FastAPI backend daemon** with WebSocket support
- **RV-C decoder** for CANbus messages
- **Modular architecture** with clear separation of concerns
- **Typed code** with Pydantic models and full type hints

## Core Architecture

- `src/common/`: Shared models and utilities
- `src/core_daemon/`: FastAPI app, WebSockets, state management
- `src/rvc_decoder/`: DGN decoding, mappings, instance management

## Code Patterns

- **FastAPI routes**: Organized by domain in `api_routers/` using APIRouter
- **WebSockets**: Used for real-time updates in `websocket.py`
- **State management**: Centralized in `app_state.py`
- **Configuration**: Environment variables with Pydantic Settings
- **Error handling**: Structured exceptions with proper logging
- **Testing**: pytest with mocked CANbus interfaces
