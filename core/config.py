from __future__ import annotations
"""Configuration loader for Retep bot."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Centralized configuration from environment variables."""

    # Discord
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
    BOT_NAME: str = os.getenv("BOT_NAME", "Retep")

    # Scheduling
    MESSAGES_PER_DAY: int = int(os.getenv("MESSAGES_PER_DAY", "1"))
    ACTIVE_HOURS_START: int = int(os.getenv("ACTIVE_HOURS_START", "10"))
    ACTIVE_HOURS_END: int = int(os.getenv("ACTIVE_HOURS_END", "23"))

    # History
    HISTORY_DEPTH: int = int(os.getenv("HISTORY_DEPTH", "10000"))

    # Database
    DB_PATH: str = os.getenv("DB_PATH", "retep.db")

    @classmethod
    def validate(cls) -> list[str]:
        """Return a list of missing required config keys."""
        errors = []
        if not cls.DISCORD_TOKEN:
            errors.append("DISCORD_TOKEN is not set")
        if cls.ACTIVE_HOURS_START >= cls.ACTIVE_HOURS_END:
            errors.append("ACTIVE_HOURS_START must be before ACTIVE_HOURS_END")
        return errors
