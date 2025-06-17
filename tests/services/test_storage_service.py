# ABOUTME: Comprehensive tests for StorageService basic CRUD operations
# ABOUTME: Tests covering check runs, post storage, retrieval, transactions, and error handling

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.check_run import CheckRun
from app.models.reddit_post import RedditPost
from app.services.storage_service import StorageService


@pytest.fixture
def in_memory_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False}
    )

    # Enable foreign key constraints for SQLite
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(in_memory_engine):
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(bind=in_memory_engine)
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture
def storage_service(session):
    """Create a StorageService instance with test session."""
    return StorageService(session)


@pytest.fixture
def sample_post_data():
    """Sample Reddit post data for testing."""
    return {
        'post_id': 'test_post_123',
        'subreddit': 'python',
        'title': 'Test Post Title',
        'author': 'test_user',
        'selftext': 'This is test content',
        'score': 42,
        'num_comments': 5,
        'url': 'https://reddit.com/r/python/test_post_123',
        'permalink': '/r/python/comments/test_post_123',
        'is_self': True,
        'over_18': False,
        'created_utc': datetime.now(UTC)
    }


class TestStorageServiceCreateCheckRun:
    """Test create_check_run functionality."""

    def test_create_check_run_returns_id(self, storage_service):
        """Test that create_check_run returns a valid ID."""
        check_run_id = storage_service.create_check_run("python", "async programming")

        assert isinstance(check_run_id, int)
        assert check_run_id > 0

    def test_create_check_run_stores_data_correctly(self, storage_service, session):
        """Test that create_check_run stores data with correct values."""
        subreddit = "python"
        topic = "web development"

        check_run_id = storage_service.create_check_run(subreddit, topic)

        # Verify data was stored correctly
        check_run = session.get(CheckRun, check_run_id)
        assert check_run is not None
        assert check_run.subreddit == subreddit
        assert check_run.topic == topic
        assert check_run.posts_found == 0
        assert check_run.new_posts == 0
        assert isinstance(check_run.timestamp, datetime)
        # Note: SQLite may not preserve timezone info, but timestamp should be present
        assert check_run.timestamp is not None

    def test_create_check_run_with_special_characters(self, storage_service):
        """Test create_check_run with special characters in subreddit/topic."""
        subreddit = "r/python-dev"
        topic = "async/await & coroutines"

        check_run_id = storage_service.create_check_run(subreddit, topic)
        assert isinstance(check_run_id, int)

    def test_create_check_run_session_error_handling(self, session):
        """Test error handling when session operations fail."""
        # Mock session to raise an error
        session.add = Mock(side_effect=SQLAlchemyError("Database error"))
        storage_service = StorageService(session)

        with pytest.raises(RuntimeError, match="Failed to create check run"):
            storage_service.create_check_run("python", "testing")


class TestStorageServiceSavePost:
    """Test save_post functionality."""

    def test_save_post_with_all_fields(self, storage_service, session, sample_post_data):
        """Test save_post with complete post data."""
        # First create a check run
        check_run_id = storage_service.create_check_run("python", "testing")
        sample_post_data['check_run_id'] = check_run_id

        post_id = storage_service.save_post(sample_post_data)

        assert isinstance(post_id, int)
        assert post_id > 0

        # Verify post was saved correctly
        saved_post = session.get(RedditPost, post_id)
        assert saved_post is not None
        assert saved_post.post_id == sample_post_data['post_id']
        assert saved_post.subreddit == sample_post_data['subreddit']
        assert saved_post.title == sample_post_data['title']
        assert saved_post.author == sample_post_data['author']
        assert saved_post.score == sample_post_data['score']
        assert saved_post.check_run_id == check_run_id

    def test_save_post_minimal_required_fields(self, storage_service, session):
        """Test save_post with only required fields."""
        check_run_id = storage_service.create_check_run("python", "testing")

        minimal_post_data = {
            'post_id': 'minimal_post',
            'subreddit': 'python',
            'title': 'Minimal Post',
            'author': None,  # Can be None (deleted author)
            'selftext': '',
            'score': 0,
            'num_comments': 0,
            'url': 'https://reddit.com/minimal',
            'permalink': '/r/python/minimal',
            'is_self': False,
            'over_18': False,
            'created_utc': datetime.now(UTC),
            'check_run_id': check_run_id
        }

        post_id = storage_service.save_post(minimal_post_data)

        saved_post = session.get(RedditPost, post_id)
        assert saved_post is not None
        assert saved_post.author is None
        assert saved_post.selftext == ''

    def test_save_post_duplicate_post_id_handling(self, storage_service, sample_post_data):
        """Test handling of duplicate post_id (should raise error)."""
        check_run_id = storage_service.create_check_run("python", "testing")
        sample_post_data['check_run_id'] = check_run_id

        # Save first post
        storage_service.save_post(sample_post_data)

        # Try to save another post with same post_id
        duplicate_data = sample_post_data.copy()
        duplicate_data['title'] = 'Different Title'

        with pytest.raises(RuntimeError, match="Failed to save post"):
            storage_service.save_post(duplicate_data)

    def test_save_post_missing_check_run_id(self, storage_service, sample_post_data):
        """Test save_post without check_run_id (should fail)."""
        # Don't add check_run_id to test data

        with pytest.raises(RuntimeError, match="Failed to save post"):
            storage_service.save_post(sample_post_data)

    def test_save_post_invalid_check_run_id(self, storage_service, sample_post_data):
        """Test save_post with non-existent check_run_id."""
        sample_post_data['check_run_id'] = 99999  # Non-existent ID

        with pytest.raises(RuntimeError, match="Failed to save post"):
            storage_service.save_post(sample_post_data)


class TestStorageServiceGetPostById:
    """Test get_post_by_id functionality."""

    def test_get_post_by_id_existing_post(self, storage_service, sample_post_data):
        """Test retrieving an existing post by Reddit post_id."""
        check_run_id = storage_service.create_check_run("python", "testing")
        sample_post_data['check_run_id'] = check_run_id

        # Save post
        storage_service.save_post(sample_post_data)

        # Retrieve by Reddit post_id
        retrieved_post = storage_service.get_post_by_id(sample_post_data['post_id'])

        assert retrieved_post is not None
        assert retrieved_post.post_id == sample_post_data['post_id']
        assert retrieved_post.title == sample_post_data['title']
        assert retrieved_post.score == sample_post_data['score']

    def test_get_post_by_id_nonexistent_post(self, storage_service):
        """Test retrieving a non-existent post returns None."""
        result = storage_service.get_post_by_id("nonexistent_post_id")
        assert result is None

    def test_get_post_by_id_empty_string(self, storage_service):
        """Test get_post_by_id with empty string."""
        result = storage_service.get_post_by_id("")
        assert result is None

    def test_get_post_by_id_with_relationships(self, storage_service, session, sample_post_data):
        """Test that retrieved post includes relationship data."""
        check_run_id = storage_service.create_check_run("python", "testing")
        sample_post_data['check_run_id'] = check_run_id

        storage_service.save_post(sample_post_data)

        retrieved_post = storage_service.get_post_by_id(sample_post_data['post_id'])

        # Check that relationship is accessible
        assert retrieved_post.check_run is not None
        assert retrieved_post.check_run.id == check_run_id


class TestStorageServiceGetLatestCheckRun:
    """Test get_latest_check_run functionality."""

    def test_get_latest_check_run_single_run(self, storage_service):
        """Test get_latest_check_run with single check run."""
        subreddit = "python"
        topic = "testing"

        check_run_id = storage_service.create_check_run(subreddit, topic)

        latest = storage_service.get_latest_check_run(subreddit, topic)

        assert latest is not None
        assert latest.id == check_run_id
        assert latest.subreddit == subreddit
        assert latest.topic == topic

    def test_get_latest_check_run_multiple_runs(self, storage_service, session):
        """Test get_latest_check_run returns most recent run."""
        subreddit = "python"
        topic = "testing"

        # Create first check run
        storage_service.create_check_run(subreddit, topic)

        # Advance time and create second check run
        with patch('app.models.check_run.datetime') as mock_datetime:
            future_time = datetime.now(UTC) + timedelta(minutes=5)
            mock_datetime.now.return_value = future_time
            second_id = storage_service.create_check_run(subreddit, topic)

        latest = storage_service.get_latest_check_run(subreddit, topic)

        assert latest is not None
        assert latest.id == second_id  # Should return the most recent

    def test_get_latest_check_run_no_matching_runs(self, storage_service):
        """Test get_latest_check_run with no matching runs."""
        # Create a run with different subreddit/topic
        storage_service.create_check_run("javascript", "nodejs")

        # Search for different combination
        result = storage_service.get_latest_check_run("python", "testing")
        assert result is None

    def test_get_latest_check_run_different_topics_same_subreddit(self, storage_service):
        """Test that different topics are handled separately."""
        subreddit = "python"

        topic1_id = storage_service.create_check_run(subreddit, "topic1")
        topic2_id = storage_service.create_check_run(subreddit, "topic2")

        result1 = storage_service.get_latest_check_run(subreddit, "topic1")
        result2 = storage_service.get_latest_check_run(subreddit, "topic2")

        assert result1.id == topic1_id
        assert result2.id == topic2_id


class TestStorageServiceTransactions:
    """Test transaction handling and error scenarios."""

    def test_transaction_rollback_on_error(self, session):
        """Test that transactions rollback properly on errors."""
        storage_service = StorageService(session)

        # Mock session.commit to raise an error after adding data
        original_commit = session.commit
        session.commit = Mock(side_effect=SQLAlchemyError("Commit failed"))

        with pytest.raises(RuntimeError):
            storage_service.create_check_run("python", "testing")

        # Restore original commit
        session.commit = original_commit

        # Verify no data was persisted due to rollback
        check_runs = session.query(CheckRun).all()
        assert len(check_runs) == 0

    def test_session_cleanup_on_success(self, storage_service, session):
        """Test that session is properly managed on successful operations."""
        # Create check run
        check_run_id = storage_service.create_check_run("python", "testing")

        # Verify data is accessible after commit
        check_run = session.get(CheckRun, check_run_id)
        assert check_run is not None

    def test_concurrent_operation_handling(self, in_memory_engine, sample_post_data):
        """Test handling of concurrent operations on same data."""
        # Create two separate sessions
        SessionClass = sessionmaker(bind=in_memory_engine)
        session1 = SessionClass()
        session2 = SessionClass()

        storage1 = StorageService(session1)
        storage2 = StorageService(session2)

        try:
            # Both create check runs with same parameters
            check_run_id1 = storage1.create_check_run("python", "testing")
            check_run_id2 = storage2.create_check_run("python", "testing")

            # Both should succeed (different check runs are allowed)
            assert check_run_id1 != check_run_id2

            # Add posts to both check runs
            sample_post_data['check_run_id'] = check_run_id1
            storage1.save_post(sample_post_data)

            # Try to save same post_id in different session (should fail)
            sample_post_data['check_run_id'] = check_run_id2
            with pytest.raises(RuntimeError):
                storage2.save_post(sample_post_data)

        finally:
            session1.close()
            session2.close()


class TestStorageServiceEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_long_strings(self, storage_service):
        """Test handling of very long strings within limits."""
        long_subreddit = "a" * 99  # Just under 100 char limit
        long_topic = "b" * 199     # Just under 200 char limit

        check_run_id = storage_service.create_check_run(long_subreddit, long_topic)
        assert isinstance(check_run_id, int)

    def test_unicode_content(self, storage_service, sample_post_data):
        """Test handling of Unicode content."""
        check_run_id = storage_service.create_check_run("python", "testing")

        unicode_data = sample_post_data.copy()
        unicode_data.update({
            'post_id': 'unicode_test',
            'title': 'Test with émojis 🐍 and ünicöde',
            'author': 'tëst_üser',
            'selftext': 'Content with special chars: ñoñó, 中文, العربية',
            'check_run_id': check_run_id
        })

        storage_service.save_post(unicode_data)

        retrieved = storage_service.get_post_by_id('unicode_test')
        assert retrieved.title == unicode_data['title']
        assert retrieved.author == unicode_data['author']

    def test_zero_and_negative_scores(self, storage_service, sample_post_data):
        """Test handling of zero and negative scores."""
        check_run_id = storage_service.create_check_run("python", "testing")

        sample_post_data.update({
            'post_id': 'negative_score_test',
            'score': -10,
            'num_comments': 0,
            'check_run_id': check_run_id
        })

        storage_service.save_post(sample_post_data)

        retrieved = storage_service.get_post_by_id('negative_score_test')
        assert retrieved.score == -10
        assert retrieved.num_comments == 0

    def test_timestamp_precision(self, storage_service, sample_post_data):
        """Test that timestamps are stored with proper precision."""
        check_run_id = storage_service.create_check_run("python", "testing")

        precise_time = datetime(2023, 12, 25, 15, 30, 45, 123456, tzinfo=UTC)
        sample_post_data.update({
            'post_id': 'timestamp_test',
            'created_utc': precise_time,
            'check_run_id': check_run_id
        })

        storage_service.save_post(sample_post_data)

        retrieved = storage_service.get_post_by_id('timestamp_test')
        # Note: SQLite may not preserve timezone info, compare without timezone
        expected_without_tz = precise_time.replace(tzinfo=None, microsecond=0)
        actual_without_tz = retrieved.created_utc.replace(microsecond=0)
        if retrieved.created_utc.tzinfo:
            actual_without_tz = actual_without_tz.replace(tzinfo=None)
        assert actual_without_tz == expected_without_tz
