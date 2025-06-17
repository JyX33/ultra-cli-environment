# ABOUTME: Test database configuration and connection management functionality
# ABOUTME: Validates SQLite and PostgreSQL connection setup with proper session handling

import os
import tempfile
from unittest.mock import patch

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


def test_sqlite_connection_creation():
    """Test SQLite database connection creation with proper configuration."""
    # This test will fail until we implement the database configuration
    from app.db.session import create_database_engine

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        temp_db_path = temp_db.name

    try:
        database_url = f"sqlite:///{temp_db_path}"
        engine = create_database_engine(database_url)

        assert engine is not None
        assert isinstance(engine, Engine)

        # Test connection works
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

    finally:
        # Cleanup
        if os.path.exists(temp_db_path):
            os.unlink(temp_db_path)


def test_postgresql_connection_creation():
    """Test PostgreSQL database connection creation."""
    from app.db.session import create_database_engine

    # Mock PostgreSQL URL (won't actually connect)
    database_url = "postgresql://user:password@localhost:5432/test_db"

    # This should create engine without error (actual connection would happen later)
    engine = create_database_engine(database_url)
    assert engine is not None
    assert isinstance(engine, Engine)
    assert "postgresql" in str(engine.url)


def test_connection_pooling_configuration():
    """Test that connection pooling is properly configured."""
    from app.db.session import create_database_engine

    database_url = "sqlite:///test.db"
    engine = create_database_engine(database_url)

    # Check pool configuration
    assert engine.pool is not None
    # For SQLite, pool size should be handled appropriately
    # (SQLite uses different pooling than PostgreSQL)


def test_invalid_database_url_handling():
    """Test error handling for invalid database configurations."""
    from app.db.session import create_database_engine

    # Test various invalid URLs
    invalid_urls = [
        "invalid://url",
        "",
        None,
        "postgresql://incomplete",
    ]

    for invalid_url in invalid_urls:
        if invalid_url is None:
            with pytest.raises((ValueError, TypeError)):
                create_database_engine(invalid_url)
        else:
            with pytest.raises((ValueError, SQLAlchemyError)):
                create_database_engine(invalid_url)


def test_session_lifecycle_management():
    """Test session creation and proper lifecycle management."""
    from app.db.session import SessionLocal, get_db

    # Test session creation
    session = SessionLocal()
    assert isinstance(session, Session)

    # Test session can execute queries
    result = session.execute(text("SELECT 1"))
    assert result.scalar() == 1

    # Test session cleanup
    session.close()

    # Test get_db dependency function
    db_generator = get_db()
    db = next(db_generator)
    assert isinstance(db, Session)

    # Test cleanup via generator
    try:
        next(db_generator)
    except StopIteration:
        pass  # Expected behavior


def test_database_configuration_from_config():
    """Test database configuration integration with app config."""
    from app.db.session import get_database_url

    # Test default SQLite configuration
    with patch.dict(os.environ, {}, clear=True):
        # Should default to SQLite when no DATABASE_URL is provided
        url = get_database_url()
        assert url.startswith("sqlite:///")
        assert "reddit_agent.db" in url or "database.db" in url


def test_database_url_from_environment():
    """Test database URL configuration from environment variables."""
    from app.db.session import get_database_url

    test_url = "postgresql://user:pass@localhost:5432/testdb"

    with patch.dict(os.environ, {"DATABASE_URL": test_url}):
        url = get_database_url()
        assert url == test_url


def test_connection_error_handling():
    """Test handling of database connection failures."""
    from app.db.session import create_database_engine

    # Test connection to non-existent PostgreSQL server
    bad_url = "postgresql://user:pass@nonexistent-host:5432/db"
    engine = create_database_engine(bad_url)

    # Engine creation should succeed, but connection should fail
    with pytest.raises(SQLAlchemyError), engine.connect():
        pass


def test_session_factory_configuration():
    """Test SessionLocal factory is properly configured."""
    from app.db.session import SessionLocal

    # Test session factory properties
    session = SessionLocal()

    # Verify session configuration
    assert not session.autoflush  # Should be False for explicit control
    # Note: autocommit is no longer an attribute in SQLAlchemy 2.0+
    # Transactions are handled differently

    # Test that we can begin a transaction
    session.begin()
    assert session.in_transaction()
    session.rollback()

    session.close()


def test_get_db_dependency_cleanup():
    """Test that get_db dependency properly manages session lifecycle."""
    from app.db.session import get_db

    # Test that the dependency function works as a context manager
    # This is how FastAPI actually uses it
    sessions_created = []

    def simulate_fastapi_request():
        """Simulate how FastAPI would use the dependency."""
        gen = get_db()
        try:
            db = next(gen)
            sessions_created.append(db)
            # Verify session works
            result = db.execute(text("SELECT 1"))
            assert result.scalar() == 1
            return db
        finally:
            # FastAPI does this cleanup automatically
            gen.close()

    # Simulate multiple requests
    simulate_fastapi_request()
    simulate_fastapi_request()

    # Different sessions should be created for each request
    assert len(sessions_created) == 2
    assert sessions_created[0] is not sessions_created[1]

    # Both sessions should be functional
    for session in sessions_created:
        assert session is not None


def test_database_url_validation():
    """Test validation of database URL formats."""
    from app.db.session import validate_database_url

    valid_urls = [
        "sqlite:///test.db",
        "sqlite:///:memory:",
        "postgresql://user:pass@localhost:5432/db",
        "postgresql+psycopg2://user:pass@localhost/db",
    ]

    invalid_urls = [
        "not_a_url",
        "http://example.com",
        "mysql://user:pass@localhost/db",  # Not supported
        "",
    ]

    for url in valid_urls:
        assert validate_database_url(url) is True

    for url in invalid_urls:
        assert validate_database_url(url) is False


def test_connection_pool_settings():
    """Test connection pool configuration for production readiness."""
    from app.db.session import create_database_engine

    # Test PostgreSQL pool settings
    postgresql_url = "postgresql://user:pass@localhost:5432/db"
    engine = create_database_engine(postgresql_url)

    # Check that pool has reasonable settings for production
    pool = engine.pool
    assert pool.size() >= 5  # Minimum pool size
    assert hasattr(pool, '_max_overflow')  # Overflow handling

    # Test SQLite settings (different pooling strategy)
    sqlite_url = "sqlite:///test.db"
    sqlite_engine = create_database_engine(sqlite_url)
    assert sqlite_engine.pool is not None


def test_database_engine_echo_configuration():
    """Test that database engine echo can be configured."""
    from app.db.session import create_database_engine

    # Test with echo enabled (for development)
    engine_with_echo = create_database_engine("sqlite:///test.db", echo=True)
    assert engine_with_echo.echo is True

    # Test with echo disabled (for production)
    engine_without_echo = create_database_engine("sqlite:///test.db", echo=False)
    assert engine_without_echo.echo is False


def test_concurrent_session_handling():
    """Test handling of concurrent database sessions."""
    from app.db.session import SessionLocal

    # Create multiple sessions to test independence
    session1 = SessionLocal()
    session2 = SessionLocal()

    try:
        # Both sessions should be independent
        assert session1 is not session2
        assert session1.bind is session2.bind  # Same engine

        # Both should be able to execute queries
        result1 = session1.execute(text("SELECT 1"))
        result2 = session2.execute(text("SELECT 2"))

        assert result1.scalar() == 1
        assert result2.scalar() == 2

    finally:
        session1.close()
        session2.close()


def test_transaction_isolation():
    """Test transaction isolation between sessions."""
    from app.db.session import SessionLocal

    session1 = SessionLocal()
    session2 = SessionLocal()

    try:
        # Start transactions
        session1.begin()
        session2.begin()

        # Transactions should be independent
        assert session1.in_transaction()
        assert session2.in_transaction()

        # Test rollback
        session1.rollback()
        assert not session1.in_transaction()
        assert session2.in_transaction()  # Should still be active

        session2.rollback()

    finally:
        session1.close()
        session2.close()
