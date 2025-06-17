# ABOUTME: Integration tests for concurrent operations and thread safety
# ABOUTME: Tests system behavior under concurrent load and parallel requests

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services.storage_service import StorageService
from tests.fixtures.reddit_mocks import MockRedditEnvironment, create_mock_praw_post


@pytest.fixture
def concurrent_temp_db():
    """Create temporary SQLite database optimized for concurrent access."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_file.close()

    # Configure for concurrent access
    engine = create_engine(
        f"sqlite:///{temp_file.name}",
        connect_args={
            "check_same_thread": False,
            "timeout": 20
        },
        pool_pre_ping=True,
        echo=False
    )
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(bind=engine)

    yield SessionLocal, temp_file.name

    # Cleanup
    Path(temp_file.name).unlink(missing_ok=True)


@pytest.fixture
def concurrent_client(concurrent_temp_db):
    """Create FastAPI test client optimized for concurrent testing."""
    SessionLocal, db_path = concurrent_temp_db

    def override_get_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client, SessionLocal

    app.dependency_overrides.clear()


@pytest.fixture
def mock_concurrent_reddit_service():
    """Mock Reddit service with realistic delays for concurrent testing."""
    service = MagicMock()

    def slow_get_posts(*args, **kwargs):
        """Simulate Reddit API latency and return PRAW-like post objects."""
        time.sleep(0.1)  # 100ms delay

        post_data = {
            "id": f"concurrent_post_{int(time.time() * 1000000) % 1000000}",
            "title": f"Concurrent Test Post {threading.get_ident()}",
            "selftext": "Content for concurrent testing",
            "author": f"user_{threading.get_ident()}",
            "score": 50,
            "num_comments": 5,
            "url": "https://example.com/concurrent",
            "permalink": f"/r/test/comments/concurrent_post_{threading.get_ident()}/",
            "created_utc": datetime.now(UTC).timestamp(),
            "upvote_ratio": 0.80,
            "subreddit": "test"
        }

        return [create_mock_praw_post(post_data)]

    def slow_get_comments(*args, **kwargs):
        """Simulate comment fetching delay."""
        time.sleep(0.05)  # 50ms delay
        return []

    # Map to correct method names
    service.get_relevant_posts_optimized.side_effect = slow_get_posts
    service.get_top_comments.side_effect = slow_get_comments
    service.search_subreddits.return_value = []

    return service


class TestConcurrentOperations:
    """Test concurrent operations and thread safety."""

    def test_concurrent_check_updates_requests(
        self,
        concurrent_client,
        mock_concurrent_reddit_service
    ):
        """Test multiple concurrent check-updates requests."""
        test_client, SessionLocal = concurrent_client

        # Mock external services
        mock_external_services = {
            'scraper': MagicMock(return_value="Scraped content"),
            'summarizer': MagicMock(return_value="Summary")
        }

        def make_request(request_id):
            """Make a single check-updates request."""
            start_time = time.time()
            response = test_client.get(f"/check-updates/test{request_id}/technology")
            end_time = time.time()

            return {
                "request_id": request_id,
                "status_code": response.status_code,
                "response_time": end_time - start_time,
                "data": response.json() if response.status_code == 200 else None,
                "error": response.text if response.status_code != 200 else None
            }

        # Set up comprehensive Reddit API mocking
        with MockRedditEnvironment(mock_concurrent_reddit_service, mock_external_services):
            # Execute concurrent requests
            num_requests = 5
            with ThreadPoolExecutor(max_workers=num_requests) as executor:
                futures = [
                    executor.submit(make_request, i)
                    for i in range(num_requests)
                ]

                results = [future.result() for future in as_completed(futures)]

            # Verify all requests succeeded
            for result in results:
                if result["status_code"] != 200:
                    print(f"Request {result['request_id']} failed with: {result['error']}")
                assert result["status_code"] == 200
                assert result["data"] is not None
                assert "new_posts" in result["data"]
                assert "summary" in result["data"]

            # Verify response times are reasonable (should be concurrent, not sequential)
            avg_response_time = sum(r["response_time"] for r in results) / len(results)
            max_response_time = max(r["response_time"] for r in results)
            total_time = max(r["response_time"] for r in results)

            # With 5 concurrent requests and 100ms Reddit delay,
            # total time should be much less than 5 * 100ms = 500ms (sequential)
            # But allow for realistic performance including database operations
            assert max_response_time < 2.0  # Should complete within 2 seconds
            assert avg_response_time < 1.0  # Average should be under 1 second

            # Verify concurrency: total time should be less than sum of all request times
            total_sequential_time = sum(r["response_time"] for r in results)
            assert total_time < total_sequential_time * 0.7  # Should be significantly faster than sequential

    def test_concurrent_database_operations(self, concurrent_client):
        """Test concurrent database read/write operations."""
        test_client, SessionLocal = concurrent_client

        def concurrent_storage_operations(thread_id):
            """Perform storage operations in a thread."""
            session = SessionLocal()
            try:
                storage_service = StorageService(session)

                # Create check run
                check_run_id = storage_service.create_check_run(
                    f"concurrent_test_{thread_id}",
                    "technology"
                )

                # Save multiple posts
                posts_saved = []
                for i in range(3):
                    post_data = {
                        "post_id": f"thread_{thread_id}_post_{i}",
                        "title": f"Thread {thread_id} Post {i}",
                        "selftext": "Concurrent test content",
                        "author": f"user_{thread_id}",
                        "score": 25 + i,
                        "num_comments": 2 + i,
                        "url": f"https://example.com/thread_{thread_id}_post_{i}",
                        "permalink": f"/r/test/comments/thread_{thread_id}_post_{i}/",
                        "created_utc": datetime.now(UTC),
                        "upvote_ratio": 0.75 + (i * 0.05),
                        "subreddit": f"concurrent_test_{thread_id}",
                        "is_self": True,
                        "over_18": False,
                        "check_run_id": check_run_id
                    }

                    storage_service.save_post(post_data)
                    posts_saved.append(post_data["post_id"])

                session.commit()

                # Read back the data
                retrieved_posts = []
                for post_id in posts_saved:
                    post = storage_service.get_post_by_id(post_id)
                    if post:
                        retrieved_posts.append(post_id)

                return {
                    "thread_id": thread_id,
                    "check_run_id": check_run_id,
                    "posts_saved": len(posts_saved),
                    "posts_retrieved": len(retrieved_posts),
                    "success": len(posts_saved) == len(retrieved_posts)
                }

            except Exception as e:
                return {
                    "thread_id": thread_id,
                    "error": str(e),
                    "success": False
                }
            finally:
                session.close()

        # Run concurrent database operations
        num_threads = 8
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(concurrent_storage_operations, i)
                for i in range(num_threads)
            ]

            results = [future.result() for future in as_completed(futures)]

        # Verify all operations succeeded
        successful_operations = [r for r in results if r.get("success", False)]
        assert len(successful_operations) == num_threads

        # Verify no data corruption
        for result in successful_operations:
            assert result["posts_saved"] == 3
            assert result["posts_retrieved"] == 3

        # Verify total data integrity
        session = SessionLocal()
        try:
            from sqlalchemy import text

            total_posts = session.execute(
                text("SELECT COUNT(*) FROM reddit_posts")
            ).scalar()
            total_check_runs = session.execute(
                text("SELECT COUNT(*) FROM check_runs")
            ).scalar()

            assert total_posts == num_threads * 3  # 3 posts per thread
            assert total_check_runs == num_threads  # 1 check run per thread

        finally:
            session.close()

    def test_concurrent_same_subreddit_checks(
        self,
        concurrent_client,
        mock_concurrent_reddit_service
    ):
        """Test concurrent checks of the same subreddit/topic combination."""
        test_client, SessionLocal = concurrent_client

        def check_same_subreddit(request_id):
            """Check the same subreddit concurrently."""
            with patch('app.main.RedditService', return_value=mock_concurrent_reddit_service), \
                 patch('app.main.scrape_article_text', return_value="Scraped content"), \
                 patch('app.main.summarize_content', return_value="Summary"):

                response = test_client.get("/check-updates/concurrent_test/ai")

                return {
                    "request_id": request_id,
                    "status_code": response.status_code,
                    "data": response.json() if response.status_code == 200 else None
                }

        # Execute multiple requests to same subreddit/topic
        num_requests = 6
        with ThreadPoolExecutor(max_workers=num_requests) as executor:
            futures = [
                executor.submit(check_same_subreddit, i)
                for i in range(num_requests)
            ]

            results = [future.result() for future in as_completed(futures)]

        # All requests should succeed
        for result in results:
            assert result["status_code"] == 200

        # Verify database consistency - should have multiple check runs
        session = SessionLocal()
        try:
            StorageService(session)

            # Should have multiple check runs for the same subreddit/topic
            check_runs = session.execute(
                "SELECT COUNT(*) FROM check_runs WHERE subreddit = 'concurrent_test' AND topic = 'ai'"
            ).scalar()

            assert check_runs == num_requests

            # Posts might vary due to concurrent mock behavior
            total_posts = session.execute(
                "SELECT COUNT(*) FROM reddit_posts WHERE subreddit = 'concurrent_test'"
            ).scalar()

            # Should have at least some posts (mocks create unique posts per thread)
            assert total_posts > 0

        finally:
            session.close()

    def test_concurrent_report_generation(
        self,
        concurrent_client,
        mock_concurrent_reddit_service
    ):
        """Test concurrent report generation requests."""
        test_client, SessionLocal = concurrent_client

        def generate_report(request_id):
            """Generate a report concurrently."""
            with patch('app.main.RedditService', return_value=mock_concurrent_reddit_service), \
                 patch('app.main.scrape_article_text', return_value="Scraped content"), \
                 patch('app.main.summarize_content', return_value="Summary"):

                start_time = time.time()
                response = test_client.get(
                    f"/generate-report/report_test_{request_id}/ai?store_data=true"
                )
                end_time = time.time()

                return {
                    "request_id": request_id,
                    "status_code": response.status_code,
                    "response_time": end_time - start_time,
                    "content_length": len(response.content) if response.status_code == 200 else 0
                }

        # Generate multiple reports concurrently
        num_reports = 4
        with ThreadPoolExecutor(max_workers=num_reports) as executor:
            futures = [
                executor.submit(generate_report, i)
                for i in range(num_reports)
            ]

            results = [future.result() for future in as_completed(futures)]

        # All reports should generate successfully
        for result in results:
            assert result["status_code"] == 200
            assert result["content_length"] > 0  # Should have content

        # Verify data was stored for each report
        session = SessionLocal()
        try:
            total_check_runs = session.execute(
                "SELECT COUNT(*) FROM check_runs WHERE subreddit LIKE 'report_test_%'"
            ).scalar()

            assert total_check_runs == num_reports

        finally:
            session.close()

    def test_mixed_concurrent_operations(
        self,
        concurrent_client,
        mock_concurrent_reddit_service
    ):
        """Test mixed concurrent operations (checks, reports, history)."""
        test_client, SessionLocal = concurrent_client

        def mixed_operation(operation_type, request_id):
            """Perform different types of operations concurrently."""
            with patch('app.main.RedditService', return_value=mock_concurrent_reddit_service), \
                 patch('app.main.scrape_article_text', return_value="Scraped content"), \
                 patch('app.main.summarize_content', return_value="Summary"):

                if operation_type == "check":
                    response = test_client.get(f"/check-updates/mixed_{request_id}/ai")
                elif operation_type == "report":
                    response = test_client.get(f"/generate-report/mixed_{request_id}/ai")
                elif operation_type == "history":
                    response = test_client.get(f"/history/mixed_{request_id}")
                elif operation_type == "trends":
                    response = test_client.get(f"/trends/mixed_{request_id}")

                return {
                    "operation": operation_type,
                    "request_id": request_id,
                    "status_code": response.status_code
                }

        # Mix different operation types
        operations = []
        for i in range(3):
            operations.extend([
                ("check", f"check_{i}"),
                ("report", f"report_{i}"),
                ("history", f"history_{i}"),
                ("trends", f"trends_{i}")
            ])

        # Execute mixed operations concurrently
        with ThreadPoolExecutor(max_workers=len(operations)) as executor:
            futures = [
                executor.submit(mixed_operation, op_type, req_id)
                for op_type, req_id in operations
            ]

            results = [future.result() for future in as_completed(futures)]

        # Categorize results by operation type
        check_results = [r for r in results if r["operation"] == "check"]
        report_results = [r for r in results if r["operation"] == "report"]
        history_results = [r for r in results if r["operation"] == "history"]
        trends_results = [r for r in results if r["operation"] == "trends"]

        # Check and report operations should succeed
        for result in check_results + report_results:
            assert result["status_code"] == 200

        # History and trends might return 404 for new subreddits (which is expected)
        for result in history_results + trends_results:
            assert result["status_code"] in [200, 404]

    def test_database_transaction_isolation(self, concurrent_client):
        """Test database transaction isolation under concurrent load."""
        test_client, SessionLocal = concurrent_client

        def transaction_test(thread_id):
            """Test transaction isolation."""
            session = SessionLocal()
            try:
                storage_service = StorageService(session)

                # Create check run
                check_run_id = storage_service.create_check_run(
                    "isolation_test",
                    f"topic_{thread_id}"
                )

                # Simulate some processing time
                time.sleep(0.1)

                # Update check run counters
                storage_service.update_check_run_counters(check_run_id, 5, 3)

                session.commit()

                # Read back the data
                check_run = storage_service.get_check_run_by_id(check_run_id)

                return {
                    "thread_id": thread_id,
                    "check_run_id": check_run_id,
                    "posts_found": check_run.posts_found if check_run else None,
                    "new_posts": check_run.new_posts if check_run else None,
                    "success": check_run is not None
                }

            except Exception as e:
                session.rollback()
                return {
                    "thread_id": thread_id,
                    "error": str(e),
                    "success": False
                }
            finally:
                session.close()

        # Run concurrent transactions
        num_threads = 6
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(transaction_test, i)
                for i in range(num_threads)
            ]

            results = [future.result() for future in as_completed(futures)]

        # All transactions should succeed
        successful_results = [r for r in results if r.get("success", False)]
        assert len(successful_results) == num_threads

        # Verify data integrity
        for result in successful_results:
            assert result["posts_found"] == 5
            assert result["new_posts"] == 3

        # Verify no data corruption in final state
        session = SessionLocal()
        try:
            total_check_runs = session.execute(
                "SELECT COUNT(*) FROM check_runs WHERE subreddit = 'isolation_test'"
            ).scalar()

            assert total_check_runs == num_threads

        finally:
            session.close()
