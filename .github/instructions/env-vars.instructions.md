---
applyTo: "**/*.py"
---

# Environment Variables

## CANbus Config
- `CAN_CHANNELS`: e.g. `can0,can1`
- `CAN_BUSTYPE`: e.g. `socketcan`
- `CAN_BITRATE`: e.g. `500000`
- `CAN_SPEC_PATH`: Path to RV-C JSON spec
- `CAN_MAP_PATH`: Path to device mapping YAML

## Server Config
- `RVC2API_TITLE`: Swagger UI title
- `RVC2API_SERVER_DESCRIPTION`: Description for FastAPI docs
- `RVC2API_ROOT_PATH`: Mount point if reverse-proxied
- `RVC2API_USER_COACH_INFO_PATH`: Path to custom coach YAML

## Misc
- `LOG_LEVEL`: Logging verbosity

## Usage Example

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # CAN Bus settings
    can_channels: str = "can0"
    can_bustype: str = "socketcan"
    can_bitrate: int = 500000

    # Server settings
    api_title: str = "RV-C API"
    server_description: str = "API for RV-C protocol"

    model_config = SettingsConfigDict(
        env_prefix="RVC2API_",
        env_file=".env",
        env_file_encoding="utf-8",
    )
```
