# ABOUTME: Database session management and engine configuration
# ABOUTME: Handles SQLAlchemy engine creation, session lifecycle, and dependency injection

from collections.abc import Generator
import os
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool


def get_database_url() -> str:
    """Get database URL from environment or default to SQLite.

    Returns:
        Database URL string for SQLAlchemy engine creation.
    """
    # Check for DATABASE_URL environment variable first
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        return database_url

    # Default to SQLite for development
    return "sqlite:///./reddit_agent.db"


def validate_database_url(url: str) -> bool:
    """Validate database URL format and supported databases.

    Args:
        url: Database URL to validate

    Returns:
        True if URL is valid and supported, False otherwise
    """
    if not url or not isinstance(url, str):
        return False

    try:
        parsed = urlparse(url)
        supported_schemes = {"sqlite", "postgresql", "postgresql+psycopg2"}

        # Check scheme is supported
        if parsed.scheme not in supported_schemes:
            return False

        # Additional validation for PostgreSQL URLs
        return not (parsed.scheme.startswith("postgresql") and (
            not parsed.hostname or not parsed.path or parsed.path == "/"
        ))
    except Exception:
        return False


def create_database_engine(
    database_url: str, echo: bool = False, **kwargs: Any
) -> Engine:
    """Create SQLAlchemy engine with appropriate configuration.

    Args:
        database_url: Database connection URL
        echo: Whether to echo SQL statements (for debugging)
        **kwargs: Additional engine configuration options

    Returns:
        Configured SQLAlchemy Engine instance

    Raises:
        ValueError: If database URL is invalid
        SQLAlchemyError: If engine creation fails
    """
    if not validate_database_url(database_url):
        raise ValueError(f"Invalid or unsupported database URL: {database_url}")

    try:
        # Parse URL to determine database type
        parsed = urlparse(database_url)

        # Configure engine based on database type
        engine_kwargs = {"echo": echo, **kwargs}

        if parsed.scheme == "sqlite":
            # SQLite-specific configuration
            engine_kwargs.update(
                {
                    "connect_args": {"check_same_thread": False},
                    "poolclass": StaticPool,
                }
            )
        elif parsed.scheme.startswith("postgresql"):
            # PostgreSQL-specific configuration
            engine_kwargs.update(
                {
                    "poolclass": QueuePool,
                    "pool_size": 10,
                    "max_overflow": 20,
                    "pool_pre_ping": True,
                    "pool_recycle": 300,
                }
            )

        return create_engine(database_url, **engine_kwargs)

    except Exception as e:
        raise SQLAlchemyError(f"Failed to create database engine: {e}") from e


# Get database URL and create engine
DATABASE_URL = get_database_url()
engine = create_database_engine(DATABASE_URL)

# Create session factory
SessionLocal = sessionmaker(
    bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions.

    Creates a new database session for each request and ensures
    proper cleanup after the request is completed.

    Yields:
        SQLAlchemy Session instance
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
