# ABOUTME: Database session management and engine configuration
# ABOUTME: Handles SQLAlchemy engine creation, session lifecycle, and dependency injection

from collections.abc import Generator
import os
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from app.core.config import Config

if TYPE_CHECKING:
    from app.services.database_pool_service import DatabasePoolService


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
    database_url: str, echo: bool = False, use_advanced_pooling: bool = True, **kwargs: Any
) -> Engine:
    """Create SQLAlchemy engine with appropriate configuration.

    Args:
        database_url: Database connection URL
        echo: Whether to echo SQL statements (for debugging)
        use_advanced_pooling: Whether to use advanced pooling configuration from config
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
            # SQLite-specific configuration with advanced options
            connect_args = {"check_same_thread": False}

            if use_advanced_pooling:
                connect_args.update({
                    "timeout": Config.DATABASE_CONNECT_TIMEOUT,
                    "isolation_level": None  # Enable autocommit for better performance
                })

            engine_kwargs.update({
                "connect_args": connect_args,
                "poolclass": StaticPool,
            })

        elif parsed.scheme.startswith("postgresql"):
            # PostgreSQL-specific configuration with advanced pooling
            base_config = {
                "poolclass": QueuePool,
                "pool_pre_ping": True,
                "pool_recycle": 300,
            }

            if use_advanced_pooling:
                # Use advanced configuration from Config
                base_config.update({
                    "pool_size": Config.DATABASE_POOL_SIZE,
                    "max_overflow": Config.DATABASE_MAX_OVERFLOW,
                    "pool_timeout": Config.DATABASE_POOL_TIMEOUT,
                    "pool_recycle": Config.DATABASE_POOL_RECYCLE,
                    "pool_pre_ping": Config.DATABASE_POOL_PRE_PING,
                    "pool_reset_on_return": Config.DATABASE_POOL_RESET_ON_RETURN,
                    "connect_args": {
                        "connect_timeout": int(Config.DATABASE_CONNECT_TIMEOUT),
                        "command_timeout": int(Config.DATABASE_QUERY_TIMEOUT),
                        "server_settings": {
                            "jit": "off",  # Disable JIT for consistent performance
                            "application_name": "ai_reddit_agent"
                        }
                    }
                })
            else:
                # Use basic configuration for backward compatibility
                base_config.update({
                    "pool_size": 10,
                    "max_overflow": 20,
                })

            engine_kwargs.update(base_config)

        return create_engine(database_url, **engine_kwargs)

    except Exception as e:
        raise SQLAlchemyError(f"Failed to create database engine: {e}") from e


# Get database URL and create engine with advanced pooling
DATABASE_URL = get_database_url()
engine = create_database_engine(DATABASE_URL, use_advanced_pooling=True)

# Create session factory with optimized settings
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

# Advanced pool service integration (optional)
_advanced_pool_service: 'DatabasePoolService | None' = None


def get_advanced_pool_service() -> 'DatabasePoolService | None':
    """Get the advanced database pool service if available.

    Returns:
        DatabasePoolService instance or None if not configured
    """
    global _advanced_pool_service

    if _advanced_pool_service is None and Config.DATABASE_ENABLE_POOL_MONITORING:
        try:
            from app.services.database_pool_service import get_database_pool_service
            from app.services.performance_monitoring_service import (
                PerformanceMonitoringService,
            )

            # Initialize with performance monitoring if enabled
            performance_monitor = None
            if Config.ENABLE_PERFORMANCE_MONITORING:
                performance_monitor = PerformanceMonitoringService(enable_system_monitoring=False)

            _advanced_pool_service = get_database_pool_service(
                database_url=DATABASE_URL,
                performance_monitor=performance_monitor
            )
            _advanced_pool_service.start_monitoring()

        except ImportError:
            # Advanced pool service not available
            pass
        except Exception as e:
            import logging
            logging.warning(f"Failed to initialize advanced pool service: {e}")

    return _advanced_pool_service


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions with advanced pool support.

    Creates a new database session for each request and ensures
    proper cleanup after the request is completed. Uses advanced
    pool service if available for enhanced monitoring and error handling.

    Yields:
        SQLAlchemy Session instance
    """
    # Try to use advanced pool service first
    advanced_pool = get_advanced_pool_service()

    if advanced_pool:
        # Use advanced pool service with monitoring
        with advanced_pool.get_session() as session:
            yield session
    else:
        # Fallback to standard session management
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()


def get_pool_status() -> dict[str, Any]:
    """Get current database pool status and metrics.

    Returns:
        Dictionary with pool status information
    """
    advanced_pool = get_advanced_pool_service()

    if advanced_pool:
        return advanced_pool.get_pool_status_report()
    else:
        # Basic pool information from engine
        pool_info: dict[str, Any] = {"pool_type": "basic", "monitoring": "disabled"}

        # Use safe attribute access for pool metrics
        try:
            if hasattr(engine.pool, 'size'):
                pool_info.update({
                    "pool_size": engine.pool.size(),
                    "checked_in": getattr(engine.pool, 'checkedin', lambda: 0)(),
                    "checked_out": getattr(engine.pool, 'checkedout', lambda: 0)(),
                    "overflow": getattr(engine.pool, 'overflow', lambda: 0)(),
                })
        except AttributeError:
            # Pool metrics not available for this pool type
            pool_info["metrics_available"] = False

        return pool_info


def cleanup_database_connections() -> None:
    """Clean up database connections and dispose of engine."""
    global _advanced_pool_service

    if _advanced_pool_service:
        _advanced_pool_service.stop_monitoring()
        _advanced_pool_service = None

    if engine:
        engine.dispose()
