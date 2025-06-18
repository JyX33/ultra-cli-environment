# ABOUTME: Comprehensive API tests for the /check-updates endpoint
# ABOUTME: Tests covering new posts, no changes, first-time checks, error handling, and integration scenarios

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.check_run import CheckRun
from app.models.types import ChangeDetectionResult, EngagementDelta, PostUpdate
from app.services.change_detection_service import ChangeDetectionService
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
def test_session(in_memory_engine):
    """Create a test database session."""
    TestingSessionLocal = sessionmaker(bind=in_memory_engine)
    session = TestingSessionLocal()
    yield session
    session.close()


@pytest.fixture
def client(test_session):
    """Create a test client with database session override."""
    def override_get_db():
        try:
            yield test_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def storage_service(test_session):
    """Create a StorageService instance with test session."""
    return StorageService(test_session)


@pytest.fixture
def change_detection_service(test_session):
    """Create a ChangeDetectionService instance with test session."""
    return ChangeDetectionService(test_session)


@pytest.fixture
def sample_reddit_posts():
    """Sample Reddit post data for testing."""
    return [
        {
            "post_id": "abc123",
            "subreddit": "technology",
            "title": "New AI Breakthrough",
            "author": "researcher_ai",
            "url": "https://reddit.com/r/technology/comments/abc123/",
            "score": 150,
            "num_comments": 25,
            "created_utc": datetime.now(UTC) - timedelta(hours=2),
            "is_self": True,
            "selftext": "Amazing breakthrough in AI research...",
            "upvote_ratio": 0.95,
            "over_18": False,
            "spoiler": False,
            "stickied": False
        },
        {
            "post_id": "def456",
            "subreddit": "technology",
            "title": "Tech Industry News",
            "author": "tech_reporter",
            "url": "https://example.com/tech-news",
            "score": 75,
            "num_comments": 12,
            "created_utc": datetime.now(UTC) - timedelta(hours=1),
            "is_self": False,
            "selftext": "",
            "upvote_ratio": 0.88,
            "over_18": False,
            "spoiler": False,
            "stickied": False
        }
    ]


@pytest.fixture
def sample_comments():
    """Sample Reddit comment data for testing."""
    return [
        {
            "comment_id": "comment1",
            "post_id": "abc123",
            "author": "commenter1",
            "body": "Great breakthrough! This will change everything.",
            "score": 10,
            "created_utc": datetime.now(UTC) - timedelta(minutes=30),
            "parent_id": None
        },
        {
            "comment_id": "comment2",
            "post_id": "abc123",
            "author": "commenter2",
            "body": "I'm skeptical about these claims.",
            "score": 5,
            "created_utc": datetime.now(UTC) - timedelta(minutes=20),
            "parent_id": None
        }
    ]


class TestCheckUpdatesEndpoint:
    """Test the /check-updates/{subreddit}/{topic} endpoint."""

    @patch('app.main.reddit_service')
    @patch('app.main.StorageService')
    @patch('app.main.ChangeDetectionService')
    def test_first_time_check_with_new_posts(self, mock_change_service, mock_storage_service, mock_reddit_service, client, sample_reddit_posts, sample_comments):
        """Test the endpoint when checking a subreddit for the first time with new posts."""
        # Setup mocks
        mock_reddit_service.get_relevant_posts_optimized.return_value = [Mock(**post) for post in sample_reddit_posts]

        mock_storage = Mock()
        mock_storage_service.return_value = mock_storage
        mock_storage.get_latest_check_run.return_value = None  # First time check
        mock_storage.create_check_run.return_value = 1
        mock_storage.save_post.return_value = None
        mock_storage.save_comment.return_value = None

        mock_change_detection = Mock()
        mock_change_service.return_value = mock_change_detection

        # Mock change detection results for first time (all posts are new)
        detection_result = ChangeDetectionResult.from_updates(
            check_run_id=1,
            subreddit="technology",
            new_posts=[
                PostUpdate(
                    post_id=1,
                    reddit_post_id="abc123",
                    subreddit="technology",
                    title="New AI Breakthrough",
                    update_type="new",
                    current_score=150,
                    current_comments=25,
                    current_timestamp=datetime.now(UTC),
                    engagement_delta=EngagementDelta(
                        post_id="abc123",
                        score_delta=150,
                        comments_delta=25,
                        previous_score=0,
                        current_score=150,
                        previous_comments=0,
                        current_comments=25,
                        time_span_hours=2.0,
                        engagement_rate=75.0
                    )
                ),
                PostUpdate(
                    post_id=2,
                    reddit_post_id="def456",
                    subreddit="technology",
                    title="Tech Industry News",
                    update_type="new",
                    current_score=75,
                    current_comments=12,
                    current_timestamp=datetime.now(UTC),
                    engagement_delta=EngagementDelta(
                        post_id="def456",
                        score_delta=75,
                        comments_delta=12,
                        previous_score=0,
                        current_score=75,
                        previous_comments=0,
                        current_comments=12,
                        time_span_hours=1.0,
                        engagement_rate=75.0
                    )
                )
            ],
            updated_posts=[]
        )
        mock_change_detection.detect_all_changes.return_value = detection_result

        # Make request
        response = client.get("/check-updates/technology/artificial-intelligence")

        # Assertions
        assert response.status_code == 200
        data = response.json()

        # Basic structure
        assert data["subreddit"] == "technology"
        assert data["topic"] == "artificial-intelligence"
        assert data["is_first_check"] is True
        assert data["last_check_time"] is None
        assert data["check_run_id"] == 1

        # New posts
        assert len(data["new_posts"]) == 2
        assert data["new_posts"][0]["post_id"] == "abc123"
        assert data["new_posts"][0]["title"] == "New AI Breakthrough"
        assert data["new_posts"][0]["is_new"] is True
        assert data["new_posts"][0]["score"] == 150
        assert data["new_posts"][0]["num_comments"] == 25

        # No updated posts on first check
        assert len(data["updated_posts"]) == 0

        # Summary
        assert data["total_posts_found"] == 2
        assert data["summary"]["new_posts_count"] == 2
        assert data["summary"]["updated_posts_count"] == 0

    @patch('app.main.reddit_service')
    @patch('app.main.StorageService')
    @patch('app.main.ChangeDetectionService')
    def test_subsequent_check_with_updated_posts(self, mock_change_service, mock_storage_service, mock_reddit_service, client, sample_reddit_posts):
        """Test the endpoint on a subsequent check with updated posts."""
        # Setup mocks
        mock_reddit_service.get_relevant_posts_optimized.return_value = [Mock(**post) for post in sample_reddit_posts]

        mock_storage = Mock()
        mock_storage_service.return_value = mock_storage

        # Mock previous check run
        previous_check = CheckRun(
            id=1,
            subreddit="technology",
            topic="artificial-intelligence",
            timestamp=datetime.now(UTC) - timedelta(hours=1),
            posts_found=2,
            new_posts=0
        )
        mock_storage.get_latest_check_run.return_value = previous_check
        mock_storage.create_check_run.return_value = 2

        mock_change_detection = Mock()
        mock_change_service.return_value = mock_change_detection

        # Mock change detection results (post has increased score)
        detection_result = ChangeDetectionResult.from_updates(
            check_run_id=2,
            subreddit="technology",
            new_posts=[],
            updated_posts=[
                PostUpdate(
                    post_id=1,
                    reddit_post_id="abc123",
                    subreddit="technology",
                    title="New AI Breakthrough",
                    update_type="both_change",
                    current_score=150,
                    current_comments=25,
                    current_timestamp=datetime.now(UTC),
                    previous_score=100,
                    previous_comments=20,
                    previous_timestamp=datetime.now(UTC) - timedelta(hours=1),
                    engagement_delta=EngagementDelta(
                        post_id="abc123",
                        score_delta=50,
                        comments_delta=5,
                        previous_score=100,
                        current_score=150,
                        previous_comments=20,
                        current_comments=25,
                        time_span_hours=1.0,
                        engagement_rate=50.0
                    )
                )
            ]
        )
        mock_change_detection.detect_all_changes.return_value = detection_result

        # Make request
        response = client.get("/check-updates/technology/artificial-intelligence")

        # Assertions
        assert response.status_code == 200
        data = response.json()

        assert data["subreddit"] == "technology"
        assert data["topic"] == "artificial-intelligence"
        assert data["is_first_check"] is False
        assert data["last_check_time"] is not None
        assert data["check_run_id"] == 2

        # No new posts
        assert len(data["new_posts"]) == 0

        # Updated posts
        assert len(data["updated_posts"]) == 1
        assert data["updated_posts"][0]["post_id"] == "abc123"
        assert data["updated_posts"][0]["is_new"] is False
        assert data["updated_posts"][0]["score_change"] == 50
        assert data["updated_posts"][0]["comment_change"] == 5

        # Summary
        assert data["summary"]["new_posts_count"] == 0
        assert data["summary"]["updated_posts_count"] == 1

    @patch('app.main.reddit_service')
    @patch('app.main.StorageService')
    @patch('app.main.ChangeDetectionService')
    def test_check_with_no_changes(self, mock_change_service, mock_storage_service, mock_reddit_service, client):
        """Test the endpoint when no changes are detected."""
        # Setup mocks
        mock_reddit_service.get_relevant_posts_optimized.return_value = []

        mock_storage = Mock()
        mock_storage_service.return_value = mock_storage

        previous_check = CheckRun(
            id=1,
            subreddit="technology",
            topic="artificial-intelligence",
            timestamp=datetime.now(UTC) - timedelta(hours=1),
            posts_found=0,
            new_posts=0
        )
        mock_storage.get_latest_check_run.return_value = previous_check
        mock_storage.create_check_run.return_value = 2

        mock_change_detection = Mock()
        mock_change_service.return_value = mock_change_detection

        # Mock no changes detected
        detection_result = ChangeDetectionResult.from_updates(
            check_run_id=2,
            subreddit="technology",
            new_posts=[],
            updated_posts=[]
        )
        mock_change_detection.detect_all_changes.return_value = detection_result

        # Make request
        response = client.get("/check-updates/technology/artificial-intelligence")

        # Assertions
        assert response.status_code == 200
        data = response.json()

        assert data["subreddit"] == "technology"
        assert data["topic"] == "artificial-intelligence"
        assert data["is_first_check"] is False
        assert len(data["new_posts"]) == 0
        assert len(data["updated_posts"]) == 0
        assert len(data["new_comments"]) == 0
        assert len(data["updated_comments"]) == 0
        assert data["total_posts_found"] == 0
        assert data["summary"]["new_posts_count"] == 0
        assert data["summary"]["updated_posts_count"] == 0

    def test_invalid_subreddit_parameter(self, client):
        """Test the endpoint with invalid subreddit parameter."""
        # Test with script injection in subreddit name
        response = client.get("/check-updates/tech<script>alert/artificial-intelligence")
        assert response.status_code == 422
        assert "malicious content" in response.json()["detail"].lower()

        # Test with SQL injection attempt in subreddit name
        response = client.get("/check-updates/DROP%20TABLE/artificial-intelligence")
        assert response.status_code == 422
        assert "malicious content" in response.json()["detail"].lower()

        # Test with too long subreddit
        long_subreddit = "a" * 150
        response = client.get(f"/check-updates/{long_subreddit}/artificial-intelligence")
        assert response.status_code == 422
        assert "too long" in response.json()["detail"].lower()

    def test_invalid_topic_parameter(self, client):
        """Test the endpoint with invalid topic parameter."""
        # Test with script injection in topic
        response = client.get("/check-updates/technology/ai<script>alert")
        assert response.status_code == 422
        assert "malicious content" in response.json()["detail"].lower()

        # Test with SQL injection attempt (URL encoded)
        response = client.get("/check-updates/technology/DROP%20TABLE%20users")
        assert response.status_code == 422
        assert "malicious content" in response.json()["detail"].lower()

    @patch('app.main.reddit_service')
    @patch('app.main.StorageService')
    def test_reddit_service_error_handling(self, mock_storage_service, mock_reddit_service, client):
        """Test error handling when Reddit service fails."""
        # Setup mocks
        mock_reddit_service.get_relevant_posts_optimized.side_effect = Exception("Reddit API error")

        mock_storage = Mock()
        mock_storage_service.return_value = mock_storage
        mock_storage.get_latest_check_run.return_value = None

        # Make request
        response = client.get("/check-updates/technology/artificial-intelligence")

        # Should return 500 error
        assert response.status_code == 500
        assert "Error processing request" in response.json()["detail"]

    @patch('app.main.reddit_service')
    @patch('app.main.StorageService')
    def test_storage_service_error_handling(self, mock_storage_service, mock_reddit_service, client):
        """Test error handling when storage service fails."""
        # Setup mocks
        mock_reddit_service.get_relevant_posts_optimized.return_value = []

        mock_storage = Mock()
        mock_storage_service.return_value = mock_storage
        mock_storage.get_latest_check_run.side_effect = Exception("Database error")

        # Make request
        response = client.get("/check-updates/technology/artificial-intelligence")

        # Should return 500 error
        assert response.status_code == 500
        assert "Error processing request" in response.json()["detail"]

    @patch('app.main.reddit_service')
    @patch('app.main.StorageService')
    @patch('app.main.ChangeDetectionService')
    def test_response_format_validation(self, mock_change_service, mock_storage_service, mock_reddit_service, client, sample_reddit_posts):
        """Test that the response format matches the expected schema."""
        # Setup mocks for a successful response
        mock_reddit_service.get_relevant_posts_optimized.return_value = [Mock(**post) for post in sample_reddit_posts]

        mock_storage = Mock()
        mock_storage_service.return_value = mock_storage
        mock_storage.get_latest_check_run.return_value = None
        mock_storage.create_check_run.return_value = 1

        mock_change_detection = Mock()
        mock_change_service.return_value = mock_change_detection

        detection_result = ChangeDetectionResult.from_updates(
            check_run_id=1,
            subreddit="technology",
            new_posts=[
                PostUpdate(
                    post_id=1,
                    reddit_post_id="abc123",
                    subreddit="technology",
                    title="New AI Breakthrough",
                    update_type="new",
                    current_score=150,
                    current_comments=25,
                    current_timestamp=datetime.now(UTC),
                    engagement_delta=EngagementDelta(
                        post_id="abc123",
                        score_delta=150,
                        comments_delta=25,
                        previous_score=0,
                        current_score=150,
                        previous_comments=0,
                        current_comments=25,
                        time_span_hours=2.0,
                        engagement_rate=75.0
                    )
                )
            ],
            updated_posts=[]
        )
        mock_change_detection.detect_all_changes.return_value = detection_result

        # Make request
        response = client.get("/check-updates/technology/artificial-intelligence")

        # Assertions
        assert response.status_code == 200
        data = response.json()

        # Check all required fields are present
        required_fields = [
            "subreddit", "topic", "check_time", "last_check_time",
            "new_posts", "updated_posts", "total_posts_found",
            "new_comments", "updated_comments", "total_comments_found",
            "summary", "is_first_check", "check_run_id"
        ]

        for field in required_fields:
            assert field in data, f"Required field '{field}' missing from response"

        # Check data types
        assert isinstance(data["subreddit"], str)
        assert isinstance(data["topic"], str)
        assert isinstance(data["new_posts"], list)
        assert isinstance(data["updated_posts"], list)
        assert isinstance(data["total_posts_found"], int)
        assert isinstance(data["is_first_check"], bool)
        assert isinstance(data["check_run_id"], int)
        assert isinstance(data["summary"], dict)

    @patch('app.main.reddit_service')
    @patch('app.main.StorageService')
    @patch('app.main.ChangeDetectionService')
    def test_concurrent_requests_handling(self, mock_change_service, mock_storage_service, mock_reddit_service, client):
        """Test that concurrent requests are handled properly."""
        # Setup mocks
        mock_reddit_service.get_relevant_posts_optimized.return_value = []

        mock_storage = Mock()
        mock_storage_service.return_value = mock_storage
        mock_storage.get_latest_check_run.return_value = None
        mock_storage.create_check_run.return_value = 1

        mock_change_detection = Mock()
        mock_change_service.return_value = mock_change_detection
        mock_change_detection.detect_all_changes.return_value = ChangeDetectionResult.from_updates(
            check_run_id=1,
            subreddit="technology",
            new_posts=[],
            updated_posts=[]
        )

        # Make multiple concurrent requests
        import threading
        import time

        results = []

        def make_request():
            try:
                response = client.get("/check-updates/technology/artificial-intelligence")
                results.append(response.status_code)
            except Exception as e:
                results.append(f"Error: {e}")

        # Create multiple threads
        threads = [threading.Thread(target=make_request) for _ in range(5)]

        # Start all threads
        for thread in threads:
            thread.start()
            time.sleep(0.01)  # Small delay to increase concurrency chance

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All requests should succeed
        assert all(result == 200 for result in results), f"Concurrent request failures: {results}"

    def test_endpoint_url_format(self, client):
        """Test that the endpoint URL format is correct."""
        # Test that the endpoint exists and accepts the expected URL format
        with patch('app.main.reddit_service') as mock_reddit_service, \
             patch('app.main.StorageService') as mock_storage_service, \
             patch('app.main.ChangeDetectionService') as mock_change_service:

            # Mock all services to return basic results
            mock_reddit_service.get_relevant_posts_optimized.return_value = []

            mock_storage = Mock()
            mock_storage_service.return_value = mock_storage
            mock_storage.get_latest_check_run.return_value = None
            mock_storage.create_check_run.return_value = 1

            mock_change_detection = Mock()
            mock_change_service.return_value = mock_change_detection
            mock_change_detection.detect_all_changes.return_value = ChangeDetectionResult.from_updates(
                check_run_id=1,
                subreddit="technology",
                new_posts=[],
                updated_posts=[]
            )

            # Test valid format
            response = client.get("/check-updates/technology/artificial-intelligence")
            assert response.status_code in [200, 500]  # Should not be 404 (endpoint exists)

            # Test with URL-encoded parameters
            response = client.get("/check-updates/technology/artificial%20intelligence")
            assert response.status_code in [200, 500]  # Should not be 404

    def test_invalid_subreddit_error_handling(self, client):
        """Test that invalid subreddit names return proper 404 errors instead of 500."""
        from prawcore.exceptions import Forbidden, NotFound

        class MockResponse:
            def __init__(self, status_code: int):
                self.status_code = status_code

        # Test NotFound exception handling
        with patch('app.main.reddit_service') as mock_reddit_service, \
             patch('app.main.StorageService') as mock_storage_service:

            mock_reddit_service.get_relevant_posts_optimized.side_effect = NotFound(MockResponse(404))

            mock_storage = Mock()
            mock_storage_service.return_value = mock_storage
            mock_storage.get_latest_check_run.return_value = None

            response = client.get("/check-updates/ThisSubredditDefinitelyDoesNotExist12345/test-topic")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()
            assert "ThisSubredditDefinitelyDoesNotExist12345" in response.json()["detail"]

        # Test Forbidden exception handling
        with patch('app.main.reddit_service') as mock_reddit_service, \
             patch('app.main.StorageService') as mock_storage_service:

            mock_reddit_service.get_relevant_posts_optimized.side_effect = Forbidden(MockResponse(403))

            mock_storage = Mock()
            mock_storage_service.return_value = mock_storage
            mock_storage.get_latest_check_run.return_value = None

            response = client.get("/check-updates/private_subreddit/test-topic")

            assert response.status_code == 422
            assert "private or restricted" in response.json()["detail"].lower()
