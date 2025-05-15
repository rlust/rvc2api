---
applyTo: "**"
---

# Project Overview

`rvc2api`: Python API/WebSocket service for RV-C CANbus systems:
- FastAPI backend daemon
- Console client
- HTML web UI (future: React)
- RV-C decoder

## Structure
- `src/common/`: Models, utilities
- `src/console_client/`: CLI
- `src/core_daemon/`: FastAPI, frontend, settings
- `src/rvc_decoder/`: DGN decoding, mappings

## Future Structure
- `src/core_daemon/` → `backend/` (FastAPI, API routes)
- `src/rvc_decoder/` → `backend/integrations/rvc/`
- Business logic → `backend/services/`
- Config → `backend/settings/`
- Prepares for Victron Modbus integration
