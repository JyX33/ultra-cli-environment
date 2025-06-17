# ABOUTME: Configuration management for environment variables with validation
# ABOUTME: Provides centralized config access with runtime validation of required settings

import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

class EnvVar:
    """Descriptor for environment variables that are dynamically loaded."""
    def __init__(self, env_name: str) -> None:
        self.env_name = env_name

    def __get__(self, instance: Any, owner: Any) -> str | None:
        return os.getenv(self.env_name)

class Config:
    """Configuration class that loads environment variables for the application."""

    REDDIT_CLIENT_ID = EnvVar("REDDIT_CLIENT_ID")
    REDDIT_CLIENT_SECRET = EnvVar("REDDIT_CLIENT_SECRET")
    REDDIT_USER_AGENT = EnvVar("REDDIT_USER_AGENT")
    OPENAI_API_KEY = EnvVar("OPENAI_API_KEY")

    # Database configuration
    DATABASE_URL = EnvVar("DATABASE_URL")

    # Connection pool settings for production
    DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "10"))
    DATABASE_MAX_OVERFLOW = int(os.getenv("DATABASE_MAX_OVERFLOW", "20"))
    DATABASE_POOL_RECYCLE = int(os.getenv("DATABASE_POOL_RECYCLE", "300"))

    # Data retention settings
    DATA_RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "30"))
    ARCHIVE_OLD_DATA = os.getenv("ARCHIVE_OLD_DATA", "false").lower() in ("true", "1", "yes")
    CLEANUP_BATCH_SIZE = int(os.getenv("CLEANUP_BATCH_SIZE", "100"))

    @classmethod
    def validate_config(cls) -> bool:
        """Validate that all required environment variables are set."""
        required_vars = [
            cls.REDDIT_CLIENT_ID,
            cls.REDDIT_CLIENT_SECRET,
            cls.REDDIT_USER_AGENT,
            cls.OPENAI_API_KEY
        ]

        if not all(required_vars):
            missing = []
            if not cls.REDDIT_CLIENT_ID:
                missing.append("REDDIT_CLIENT_ID")
            if not cls.REDDIT_CLIENT_SECRET:
                missing.append("REDDIT_CLIENT_SECRET")
            if not cls.REDDIT_USER_AGENT:
                missing.append("REDDIT_USER_AGENT")
            if not cls.OPENAI_API_KEY:
                missing.append("OPENAI_API_KEY")

            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        return True

config = Config()
