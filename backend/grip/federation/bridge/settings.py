"""Settings of the bridge that are instance policy rather than transport."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class BridgeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Staffing goes to the parent instance as head counts per role. With this
    # switched on by the beheerder of this instance it goes with names.
    HANDOVER_STAFFING_WITH_NAMES: bool = False


@lru_cache
def get_bridge_settings() -> BridgeSettings:
    return BridgeSettings()
