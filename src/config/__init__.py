"""Configuration management via pydantic-settings."""

from src.config.settings import get_settings, Settings

__all__ = ["get_settings", "Settings"]
