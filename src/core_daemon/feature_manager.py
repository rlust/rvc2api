"""
Feature manager for optional backend integrations in rvc2api.

This module allows optional features (e.g., notifications, monitoring) to be registered,
enabled/disabled via config, and initialized at startup.
"""

import logging
import os
from typing import Dict, Optional

from .uptimerobot import UptimeRobotFeature

logger = logging.getLogger(__name__)


class Feature:
    """
    Base class for backend features (core or optional).
    Subclass this and implement startup/shutdown as needed.
    """

    name: str
    enabled: bool
    core: bool
    config: dict

    def __init__(
        self, name: str, enabled: bool = False, core: bool = False, config: Optional[dict] = None
    ):
        self.name = name
        self.enabled = enabled
        self.core = core
        self.config = config or {}

    async def startup(self):
        """Called on FastAPI startup if feature is enabled."""
        pass

    async def shutdown(self):
        """Called on FastAPI shutdown if feature is enabled."""
        pass

    @property
    def health(self) -> str:
        """
        Returns the health status of the feature.
        Override in subclasses for real checks.
        """
        if not self.enabled:
            return "disabled"
        return "unknown"  # Default; subclasses can override with real health logic


# Registry of features by name
_registered_features: Dict[str, Feature] = {}


def register_feature(feature: Feature):
    """Register a feature instance."""
    _registered_features[feature.name] = feature
    logger.info(f"Registered feature: {feature.name} (enabled={feature.enabled})")


def get_feature(name: str) -> Optional[Feature]:
    return _registered_features.get(name)


def get_enabled_features() -> Dict[str, Feature]:
    return {k: v for k, v in _registered_features.items() if v.enabled}


def get_all_features() -> Dict[str, Feature]:
    return dict(_registered_features)


def get_core_features() -> Dict[str, Feature]:
    return {k: v for k, v in _registered_features.items() if v.core}


def get_optional_features() -> Dict[str, Feature]:
    return {k: v for k, v in _registered_features.items() if not v.core}


async def startup_all():
    for feature in get_enabled_features().values():
        logger.info(f"Starting feature: {feature.name}")
        await feature.startup()


async def shutdown_all():
    for feature in get_enabled_features().values():
        logger.info(f"Shutting down feature: {feature.name}")
        await feature.shutdown()


# --- Feature Registration Section ---
# Register core and optional features here.
# Core features (always enabled):
register_feature(Feature(name="canbus", enabled=True, core=True))
register_feature(Feature(name="web_ui", enabled=True, core=True))

# Optional features (enabled via environment variable or config):
register_feature(
    Feature(
        name="pushover",
        enabled=os.getenv("ENABLE_PUSHOVER", "0") == "1",
        core=False,
        config={
            "user_key": os.getenv("PUSHOVER_USER_KEY"),
            "api_token": os.getenv("PUSHOVER_API_TOKEN"),
        },
    )
)
register_feature(
    UptimeRobotFeature(
        name="uptimerobot",
        enabled=os.getenv("ENABLE_UPTIMEROBOT", "0") == "1",
        core=False,
        config={
            "api_key": os.getenv("UPTIMEROBOT_API_KEY"),
        },
    )
)
# Add more features as needed following this pattern.
