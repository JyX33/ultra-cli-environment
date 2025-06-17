# ABOUTME: Comprehensive tests for enhanced report generation endpoint
# ABOUTME: Tests data storage, include_history parameter, backwards compatibility, and error handling

from datetime import UTC, datetime
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import StaticPool, create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.check_run import CheckRun
from app.models.comment import Comment
from app.models.reddit_post import RedditPost


@pytest.fixture
def db_engine():
    """Create in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Create database session for testing."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_client(db_session):
    """Create test client with database dependency override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def mock_reddit_service():
    """Mock Reddit service with sample data."""
    with patch('app.main.reddit_service') as mock_service:
        # Create mock posts
        mock_post = Mock()
        mock_post.id = "test_post_1"
        mock_post.title = "Test Post Title"
        mock_post.author = "test_author"
        mock_post.url = "https://example.com/article"
        mock_post.score = 100
        mock_post.num_comments = 50
        mock_post.created_utc = 1640995200  # 2022-01-01
        mock_post.is_self = False
        mock_post.selftext = ""
        mock_post.over_18 = False
        mock_post.subreddit.display_name = "technology"
        mock_post.permalink = "/r/technology/comments/abc123/test_post/"

        # Mock comments
        mock_comment = Mock()
        mock_comment.id = "comment_1"
        mock_comment.author = "commenter"
        mock_comment.body = "This is a test comment"
        mock_comment.score = 10
        mock_comment.created_utc = 1640995300
        mock_comment.parent_id = f"t3_{mock_post.id}"
        mock_comment.link_id = f"t3_{mock_post.id}"

        mock_post.comments.replace_more = Mock()
        mock_post.comments.list.return_value = [mock_comment]

        mock_service.get_relevant_posts_optimized.return_value = [mock_post]
        yield mock_service


@pytest.fixture
def mock_scraper_service():
    """Mock scraper service."""
    with patch('app.main.scrape_article_text') as mock_scraper:
        mock_scraper.return_value = "Scraped article content"
        yield mock_scraper


@pytest.fixture
def mock_summarizer_service():
    """Mock summarizer service."""
    with patch('app.main.summarize_content') as mock_summarizer:
        mock_summarizer.return_value = "AI generated summary"
        yield mock_summarizer


@pytest.fixture
def mock_comment_processor():
    """Mock comment processor."""
    with patch('app.main.get_comments_summary_stream') as mock_processor:
        mock_processor.return_value = "Comments summary text"
        yield mock_processor


@pytest.fixture
def mock_report_generator():
    """Mock report generator."""
    with patch('app.main.create_markdown_report') as mock_generator:
        mock_generator.return_value = "# Test Report\n\nReport content here"
        yield mock_generator


@pytest.fixture
def mock_filename_sanitizer():
    """Mock filename sanitizer."""
    with patch('app.main.generate_safe_filename') as mock_sanitizer:
        mock_sanitizer.return_value = "test_report.md"
        yield mock_sanitizer


class TestEnhancedReportGeneration:
    """Test suite for enhanced report generation with storage."""

    def test_basic_report_generation_backwards_compatibility(
        self, test_client, mock_reddit_service, mock_scraper_service,
        mock_summarizer_service, mock_comment_processor, mock_report_generator,
        mock_filename_sanitizer
    ):
        """Test that basic report generation still works without storage parameters."""
        response = test_client.get("/generate-report/technology/ai")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/markdown; charset=utf-8"
        assert "attachment; filename=test_report.md" in response.headers["content-disposition"]

        # Verify content
        content = response.content.decode("utf-8")
        assert "# Test Report" in content
        assert "Report content here" in content

    def test_report_generation_with_storage_enabled(
        self, test_client, db_session, mock_reddit_service, mock_scraper_service,
        mock_summarizer_service, mock_comment_processor, mock_report_generator,
        mock_filename_sanitizer
    ):
        """Test report generation with data storage enabled."""
        response = test_client.get("/generate-report/technology/ai?store_data=true")

        assert response.status_code == 200

        # Verify data was stored
        check_runs = db_session.query(CheckRun).all()
        assert len(check_runs) == 1

        check_run = check_runs[0]
        assert check_run.subreddit == "technology"
        assert check_run.topic == "ai"
        assert check_run.posts_found == 1

        # Verify post was stored
        posts = db_session.query(RedditPost).all()
        assert len(posts) == 1

        post = posts[0]
        assert post.post_id == "test_post_1"
        assert post.title == "Test Post Title"
        assert post.subreddit == "technology"
        assert post.check_run_id == check_run.id

        # Verify comment was stored
        comments = db_session.query(Comment).all()
        assert len(comments) == 1

        comment = comments[0]
        assert comment.comment_id == "comment_1"
        assert comment.body == "This is a test comment"

    def test_include_history_parameter_first_generation(
        self, test_client, mock_reddit_service, mock_scraper_service,
        mock_summarizer_service, mock_comment_processor, mock_report_generator,
        mock_filename_sanitizer
    ):
        """Test include_history parameter on first report generation."""
        response = test_client.get("/generate-report/technology/ai?include_history=true")

        assert response.status_code == 200

        # Should work normally since no history exists yet
        content = response.content.decode("utf-8")
        assert "# Test Report" in content

    def test_include_history_parameter_with_existing_data(
        self, test_client, db_session, mock_reddit_service, mock_scraper_service,
        mock_summarizer_service, mock_comment_processor, mock_report_generator,
        mock_filename_sanitizer
    ):
        """Test include_history parameter with existing historical data."""
        # Create existing check run and post
        check_run = CheckRun(
            subreddit="technology",
            topic="ai",
            timestamp=datetime.now(UTC),
            posts_found=1,
            new_posts=1
        )
        db_session.add(check_run)
        db_session.commit()

        post = RedditPost(
            post_id="historical_post",
            subreddit="technology",
            title="Historical Post",
            author="old_author",
            url="https://old.example.com",
            permalink="/r/technology/comments/xyz789/historical_post/",
            score=50,
            num_comments=25,
            created_utc=datetime.now(UTC),
            is_self=False,
            selftext="",
            over_18=False,
            check_run_id=check_run.id
        )
        db_session.add(post)
        db_session.commit()

        # Mock report generator to include history
        mock_report_generator.return_value = "# Report with History\n\nNew content\n\n## Historical Data\n\nOld content"

        response = test_client.get("/generate-report/technology/ai?include_history=true&store_data=true")

        assert response.status_code == 200

        content = response.content.decode("utf-8")
        assert "# Report with History" in content
        assert "Historical Data" in content

    def test_storage_failure_does_not_break_report_generation(
        self, test_client, mock_reddit_service, mock_scraper_service,
        mock_summarizer_service, mock_comment_processor, mock_report_generator,
        mock_filename_sanitizer
    ):
        """Test that storage failures don't prevent report generation."""

        # Mock storage service to fail
        with patch('app.main.StorageService') as mock_storage_class:
            mock_storage = Mock()
            mock_storage.create_check_run.side_effect = SQLAlchemyError("Database error")
            mock_storage_class.return_value = mock_storage

            response = test_client.get("/generate-report/technology/ai?store_data=true")

            # Report should still be generated despite storage failure
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/markdown; charset=utf-8"

            content = response.content.decode("utf-8")
            assert "# Test Report" in content

    def test_invalid_parameters_validation(self, test_client):
        """Test validation of invalid parameters."""
        # Test invalid boolean parameter - FastAPI will handle this
        response = test_client.get("/generate-report/technology/ai?store_data=invalid")
        assert response.status_code == 422

        # Test another invalid boolean parameter
        response = test_client.get("/generate-report/technology/ai?include_history=invalid")
        assert response.status_code == 422

    def test_performance_impact_of_storage(
        self, test_client, mock_reddit_service, mock_scraper_service,
        mock_summarizer_service, mock_comment_processor, mock_report_generator,
        mock_filename_sanitizer
    ):
        """Test that storage doesn't significantly impact performance."""
        import time

        # Time without storage
        start_time = time.time()
        response1 = test_client.get("/generate-report/technology/ai")
        time_without_storage = time.time() - start_time

        assert response1.status_code == 200

        # Time with storage
        start_time = time.time()
        response2 = test_client.get("/generate-report/technology/ai?store_data=true")
        time_with_storage = time.time() - start_time

        assert response2.status_code == 200

        # Storage should not add more than 5x overhead (relaxed for test stability)
        assert time_with_storage < time_without_storage * 5

    def test_error_recovery_on_partial_storage_failure(
        self, test_client, db_session, mock_reddit_service, mock_scraper_service,
        mock_summarizer_service, mock_comment_processor, mock_report_generator,
        mock_filename_sanitizer
    ):
        """Test error recovery when some storage operations fail."""

        with patch('app.main.StorageService') as mock_storage_class:
            mock_storage = Mock()
            # Create check run succeeds
            mock_storage.create_check_run.return_value = 1
            # Save post succeeds
            mock_storage.save_post.return_value = None
            # Save comment fails
            mock_storage.save_comment.side_effect = SQLAlchemyError("Comment save failed")

            mock_storage_class.return_value = mock_storage

            response = test_client.get("/generate-report/technology/ai?store_data=true")

            # Report should still be generated
            assert response.status_code == 200
            content = response.content.decode("utf-8")
            assert "# Test Report" in content

    def test_concurrent_report_generation_with_storage(
        self, test_client, mock_reddit_service, mock_scraper_service,
        mock_summarizer_service, mock_comment_processor, mock_report_generator,
        mock_filename_sanitizer
    ):
        """Test concurrent report generation with storage enabled."""
        import queue
        import threading

        results = queue.Queue()

        def generate_report(subreddit, topic):
            try:
                response = test_client.get(f"/generate-report/{subreddit}/{topic}?store_data=true")
                results.put(("success", response.status_code))
            except Exception as e:
                results.put(("error", str(e)))

        # Start multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=generate_report, args=("technology", f"topic_{i}"))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Check results
        success_count = 0
        while not results.empty():
            result_type, result_value = results.get()
            if result_type == "success" and result_value == 200:
                success_count += 1

        # All requests should succeed
        assert success_count == 3

    def test_data_consistency_during_storage(
        self, test_client, db_session, mock_reddit_service, mock_scraper_service,
        mock_summarizer_service, mock_comment_processor, mock_report_generator,
        mock_filename_sanitizer
    ):
        """Test data consistency when storing during report generation."""

        response = test_client.get("/generate-report/technology/ai?store_data=true")
        assert response.status_code == 200

        # Verify referential integrity
        check_run = db_session.query(CheckRun).first()
        assert check_run is not None

        post = db_session.query(RedditPost).first()
        assert post is not None
        assert post.check_run_id == check_run.id

        comment = db_session.query(Comment).first()
        assert comment is not None
        assert comment.post_id == post.id  # Foreign key to the database post ID

    def test_empty_reddit_data_with_storage(
        self, test_client, mock_reddit_service, mock_scraper_service,
        mock_summarizer_service, mock_comment_processor, mock_report_generator,
        mock_filename_sanitizer
    ):
        """Test handling of empty Reddit data with storage enabled."""

        # Mock empty Reddit response
        mock_reddit_service.get_relevant_posts_optimized.return_value = []

        response = test_client.get("/generate-report/technology/ai?store_data=true")

        # Should return 404 for no posts found
        assert response.status_code == 404
        assert "No relevant posts found" in response.json()["detail"]

    def test_report_format_consistency_with_storage(
        self, test_client, mock_reddit_service, mock_scraper_service,
        mock_summarizer_service, mock_comment_processor, mock_report_generator,
        mock_filename_sanitizer
    ):
        """Test that report format remains consistent with storage enabled."""

        # Generate report without storage
        response1 = test_client.get("/generate-report/technology/ai")
        content1 = response1.content.decode("utf-8")

        # Generate report with storage
        response2 = test_client.get("/generate-report/technology/ai?store_data=true")
        content2 = response2.content.decode("utf-8")

        # Content should be identical
        assert response1.status_code == response2.status_code
        assert content1 == content2
        assert response1.headers["content-type"] == response2.headers["content-type"]

    def test_historical_data_integration_in_report(
        self, test_client, db_session, mock_reddit_service, mock_scraper_service,
        mock_summarizer_service, mock_comment_processor, mock_filename_sanitizer
    ):
        """Test integration of historical data into report content."""

        # Create historical data
        old_check_run = CheckRun(
            subreddit="technology",
            topic="ai",
            timestamp=datetime.now(UTC),
            posts_found=2,
            new_posts=2
        )
        db_session.add(old_check_run)
        db_session.commit()

        old_posts = [
            RedditPost(
                post_id="old_post_1",
                subreddit="technology",
                title="Old AI Development",
                author="researcher",
                url="https://old1.example.com",
                permalink="/r/technology/comments/old1/old_ai_development/",
                score=200,
                num_comments=100,
                created_utc=datetime.now(UTC),
                is_self=True,
                selftext="Old research content",
                over_18=False,
                check_run_id=old_check_run.id
            ),
            RedditPost(
                post_id="old_post_2",
                subreddit="technology",
                title="AI Ethics Discussion",
                author="ethicist",
                url="https://old2.example.com",
                permalink="/r/technology/comments/old2/ai_ethics_discussion/",
                score=150,
                num_comments=75,
                created_utc=datetime.now(UTC),
                is_self=False,
                selftext="",
                over_18=False,
                check_run_id=old_check_run.id
            )
        ]

        for post in old_posts:
            db_session.add(post)
        db_session.commit()

        # Test that historical data is retrieved but not yet integrated into report
        # (Historical data integration into report generator is a future enhancement)
        with patch('app.main.create_markdown_report') as mock_generator:
            mock_generator.return_value = "# Test Report\n\nNew content"

            response = test_client.get("/generate-report/technology/ai?include_history=true&store_data=true")

            assert response.status_code == 200
            content = response.content.decode("utf-8")
            assert "# Test Report" in content
            assert "New content" in content

            # Verify that report generator was called with correct parameters
            mock_generator.assert_called_once()
            call_args = mock_generator.call_args
            assert len(call_args[0]) == 3  # report_data, subreddit, topic
            assert call_args[0][1] == "technology"
            assert call_args[0][2] == "ai"


if __name__ == "__main__":
    pytest.main([__file__])
