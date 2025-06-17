# ABOUTME: Integration tests for performance benchmarks and optimization validation
# ABOUTME: Tests response times, memory usage, and query efficiency under load

from datetime import UTC, datetime
import gc
from pathlib import Path
import tempfile
import time
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import psutil
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services.change_detection_service import ChangeDetectionService
from app.services.storage_service import StorageService


@pytest.fixture
def performance_db():
    """Create optimized database for performance testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_file:
        temp_db_path = temp_file.name

    # Optimize SQLite for performance testing
    engine = create_engine(
        f"sqlite:///{temp_db_path}",
        connect_args={
            "check_same_thread": False,
            "timeout": 30
        },
        pool_pre_ping=True,
        echo=False  # Disable SQL logging for performance
    )

    # Create tables with optimizations
    Base.metadata.create_all(bind=engine)

    # Apply SQLite performance optimizations
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode = WAL"))
        conn.execute(text("PRAGMA synchronous = NORMAL"))
        conn.execute(text("PRAGMA cache_size = 10000"))
        conn.execute(text("PRAGMA temp_store = MEMORY"))
        conn.commit()

    SessionLocal = sessionmaker(bind=engine)

    yield SessionLocal, temp_db_path

    # Cleanup
    Path(temp_db_path).unlink(missing_ok=True)


@pytest.fixture
def performance_client(performance_db):
    """Create optimized test client for performance testing."""
    SessionLocal, db_path = performance_db

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
def large_dataset():
    """Generate large dataset for performance testing."""
    base_time = datetime.now(UTC).timestamp()

    posts = []
    comments = []

    # Generate 100 posts
    for i in range(100):
        post = {
            "id": f"perf_post_{i:03d}",
            "title": f"Performance Test Post {i:03d} - " + "Content " * 10,
            "selftext": "This is a performance test post with substantial content. " * 20,
            "author": f"perf_user_{i % 20}",  # 20 different users
            "score": 10 + (i * 2),
            "num_comments": 5 + (i % 15),
            "url": f"https://example.com/perf_post_{i:03d}",
            "permalink": f"/r/performance/comments/perf_post_{i:03d}/",
            "created_utc": base_time - (i * 300),  # 5 minutes apart
            "upvote_ratio": 0.60 + (i % 40) / 100,  # Varying ratios
            "subreddit": "performance"
        }
        posts.append(post)

        # Generate 2-10 comments per post
        num_comments = 2 + (i % 9)
        for j in range(num_comments):
            comment = {
                "id": f"perf_comment_{i:03d}_{j:02d}",
                "body": f"Performance test comment {j} for post {i}. " + "Content " * 15,
                "author": f"commenter_{j % 10}",  # 10 different commenters
                "score": 1 + (j * 2),
                "parent_id": None if j == 0 else f"perf_comment_{i:03d}_{j-1:02d}",
                "created_utc": base_time - (i * 300) + (j * 60),
                "post_id": f"perf_post_{i:03d}"
            }
            comments.append(comment)

    return {"posts": posts, "comments": comments}


class PerformanceTimer:
    """Context manager for measuring execution time."""

    def __init__(self, description="Operation"):
        self.description = description
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        gc.collect()  # Force garbage collection before timing
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()
        self.duration = self.end_time - self.start_time

    @property
    def elapsed(self):
        return self.duration if self.end_time else None


class MemoryMonitor:
    """Monitor memory usage during operations."""

    def __init__(self):
        self.process = psutil.Process()
        self.start_memory = None
        self.end_memory = None

    def start(self):
        gc.collect()
        self.start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        return self

    def stop(self):
        gc.collect()
        self.end_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        return self.end_memory - self.start_memory if self.start_memory else 0

    @property
    def delta_mb(self):
        return self.end_memory - self.start_memory if self.start_memory and self.end_memory else 0


class TestPerformanceBenchmarks:
    """Performance benchmark tests for the system."""

    def test_bulk_data_insertion_performance(self, performance_client, large_dataset):
        """Test performance of bulk data insertion operations."""
        test_client, SessionLocal = performance_client

        session = SessionLocal()
        try:
            storage_service = StorageService(session)
            memory_monitor = MemoryMonitor().start()

            # Test check run creation performance
            with PerformanceTimer("Check run creation") as timer:
                check_run_id = storage_service.create_check_run("performance", "bulk_test")
                session.commit()

            assert timer.elapsed < 0.1  # Should complete within 100ms

            # Test bulk post insertion
            posts = large_dataset["posts"]
            for post in posts:
                post["check_run_id"] = check_run_id

            with PerformanceTimer("100 posts insertion") as timer:
                for post in posts:
                    storage_service.save_post(post)
                session.commit()

            assert timer.elapsed < 5.0  # Should complete within 5 seconds
            print(f"Post insertion rate: {len(posts) / timer.elapsed:.1f} posts/second")

            # Test bulk comment insertion
            comments = large_dataset["comments"]

            with PerformanceTimer("Bulk comments insertion") as timer:
                for i in range(0, len(comments), 50):  # Process in batches of 50
                    batch = comments[i:i+50]
                    # Group by post_id for bulk save
                    post_groups = {}
                    for comment in batch:
                        post_id = comment["post_id"]
                        if post_id not in post_groups:
                            post_groups[post_id] = []
                        post_groups[post_id].append(comment)

                    for post_id, post_comments in post_groups.items():
                        storage_service.bulk_save_comments(post_comments, post_id)

                    session.commit()

            assert timer.elapsed < 10.0  # Should complete within 10 seconds
            print(f"Comment insertion rate: {len(comments) / timer.elapsed:.1f} comments/second")

            memory_usage = memory_monitor.stop()
            print(f"Memory usage for bulk insertion: {memory_usage:.1f} MB")
            assert memory_usage < 100  # Should not use more than 100MB

            # Verify data integrity
            total_posts = session.query(storage_service.models.RedditPost).count()
            total_comments = session.query(storage_service.models.Comment).count()
            assert total_posts == len(posts)
            assert total_comments == len(comments)

        finally:
            session.close()

    def test_query_performance_with_large_dataset(self, performance_client, large_dataset):
        """Test query performance with large datasets."""
        test_client, SessionLocal = performance_client

        # First populate the database
        session = SessionLocal()
        try:
            storage_service = StorageService(session)

            # Insert test data
            check_run_id = storage_service.create_check_run("performance", "query_test")

            for post in large_dataset["posts"]:
                post["check_run_id"] = check_run_id
                storage_service.save_post(post)

            for i in range(0, len(large_dataset["comments"]), 50):
                batch = large_dataset["comments"][i:i+50]
                post_groups = {}
                for comment in batch:
                    post_id = comment["post_id"]
                    if post_id not in post_groups:
                        post_groups[post_id] = []
                    post_groups[post_id].append(comment)

                for post_id, post_comments in post_groups.items():
                    storage_service.bulk_save_comments(post_comments, post_id)

            session.commit()

        finally:
            session.close()

        # Test query performance
        session = SessionLocal()
        try:
            storage_service = StorageService(session)

            # Test individual post retrieval
            with PerformanceTimer("Single post retrieval") as timer:
                post = storage_service.get_post_by_id("perf_post_050")

            assert timer.elapsed < 0.01  # Should be very fast with proper indexing
            assert post is not None

            # Test bulk post retrieval
            with PerformanceTimer("Get posts for check run") as timer:
                posts = storage_service.get_posts_for_check_run(check_run_id)

            assert timer.elapsed < 0.1  # Should complete within 100ms
            assert len(posts) == 100

            # Test time-based queries
            cutoff_time = datetime.now(UTC)
            with PerformanceTimer("Time-based post query") as timer:
                storage_service.get_new_posts_since("performance", cutoff_time)

            assert timer.elapsed < 0.1  # Should be fast with proper indexing

            # Test comment retrieval for posts
            test_post_ids = [f"perf_post_{i:03d}" for i in range(0, 100, 10)]  # Every 10th post

            with PerformanceTimer("Comments for multiple posts") as timer:
                for post_id in test_post_ids:
                    storage_service.get_comments_for_post(post_id)

            assert timer.elapsed < 0.5  # Should be reasonably fast

            # Test complex aggregation query
            with PerformanceTimer("Storage statistics") as timer:
                stats = storage_service.get_storage_statistics()

            assert timer.elapsed < 0.2  # Should complete within 200ms
            assert stats["total_posts"] == 100

        finally:
            session.close()

    def test_change_detection_performance(self, performance_client, large_dataset):
        """Test change detection performance with large datasets."""
        test_client, SessionLocal = performance_client

        # Setup initial data
        session = SessionLocal()
        try:
            storage_service = StorageService(session)
            change_detection_service = ChangeDetectionService(session)

            # Insert initial data
            check_run_id = storage_service.create_check_run("performance", "change_detection")

            initial_posts = large_dataset["posts"][:80]  # First 80 posts
            for post in initial_posts:
                post["check_run_id"] = check_run_id
                storage_service.save_post(post)

            session.commit()

            # Prepare updated dataset (modify scores, add new posts)
            updated_posts = large_dataset["posts"].copy()
            for i in range(len(updated_posts)):
                if i < 80:
                    updated_posts[i]["score"] += 10 + (i % 20)  # Modify existing posts
                    updated_posts[i]["num_comments"] += 1 + (i % 5)
                # Posts 80-99 are "new"

            memory_monitor = MemoryMonitor().start()

            # Test new post detection performance
            with PerformanceTimer("New post detection") as timer:
                cutoff_time = datetime.now(UTC)
                new_posts = change_detection_service.find_new_posts(updated_posts, cutoff_time)

            assert timer.elapsed < 1.0  # Should complete within 1 second
            assert len(new_posts) == 20  # Posts 80-99 should be new

            # Test updated post detection performance
            with PerformanceTimer("Updated post detection") as timer:
                updated_post_results = change_detection_service.find_updated_posts(updated_posts)

            assert timer.elapsed < 2.0  # Should complete within 2 seconds
            assert len(updated_post_results) == 80  # All existing posts were modified

            # Test engagement delta calculation performance
            with PerformanceTimer("Engagement delta calculation") as timer:
                for post in updated_posts[:10]:  # Test first 10 posts
                    change_detection_service.calculate_engagement_delta(
                        post["id"],
                        post["score"],
                        post["num_comments"]
                    )

            assert timer.elapsed < 0.5  # Should be fast

            memory_usage = memory_monitor.stop()
            print(f"Memory usage for change detection: {memory_usage:.1f} MB")
            assert memory_usage < 50  # Should not use excessive memory

        finally:
            session.close()

    def test_api_endpoint_performance(self, performance_client):
        """Test API endpoint response times under load."""
        test_client, SessionLocal = performance_client

        # Mock services for consistent timing
        mock_reddit_service = MagicMock()
        mock_reddit_service.get_posts.return_value = [
            {
                "id": f"api_post_{i}",
                "title": f"API Test Post {i}",
                "selftext": "API test content",
                "author": f"api_user_{i}",
                "score": 25 + i,
                "num_comments": 3 + i,
                "url": f"https://example.com/api_post_{i}",
                "permalink": f"/r/apitest/comments/api_post_{i}/",
                "created_utc": datetime.now(UTC).timestamp() - (i * 300),
                "upvote_ratio": 0.80,
                "subreddit": "apitest"
            }
            for i in range(10)
        ]
        mock_reddit_service.get_comments.return_value = []

        with patch('app.main.RedditService', return_value=mock_reddit_service), \
             patch('app.main.scrape_article_text', return_value="Scraped content"), \
             patch('app.main.summarize_content', return_value="Summary"):

            # Test check-updates endpoint performance
            with PerformanceTimer("First check-updates request") as timer:
                response = test_client.get("/check-updates/apitest/performance")

            assert response.status_code == 200
            assert timer.elapsed < 2.0  # Should complete within 2 seconds

            # Test subsequent request performance (with existing data)
            with PerformanceTimer("Subsequent check-updates request") as timer:
                response = test_client.get("/check-updates/apitest/performance")

            assert response.status_code == 200
            assert timer.elapsed < 1.0  # Should be faster with existing data

            # Test history endpoint performance
            with PerformanceTimer("History endpoint") as timer:
                response = test_client.get("/history/apitest")

            assert response.status_code == 200
            assert timer.elapsed < 0.5  # Should be fast

            # Test trends endpoint performance
            with PerformanceTimer("Trends endpoint") as timer:
                response = test_client.get("/trends/apitest")

            assert response.status_code == 200
            assert timer.elapsed < 1.0  # Should complete within 1 second

            # Test report generation performance
            with PerformanceTimer("Report generation") as timer:
                response = test_client.get("/generate-report/apitest/performance")

            assert response.status_code == 200
            assert timer.elapsed < 3.0  # Report generation can take longer

    def test_memory_usage_stability(self, performance_client):
        """Test that memory usage remains stable under repeated operations."""
        test_client, SessionLocal = performance_client

        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB

        # Perform repeated operations
        for iteration in range(10):
            session = SessionLocal()
            try:
                storage_service = StorageService(session)

                # Create and delete data repeatedly
                check_run_id = storage_service.create_check_run(
                    f"memory_test_{iteration}",
                    "stability"
                )

                # Create some posts
                for i in range(5):
                    post_data = {
                        "id": f"memory_post_{iteration}_{i}",
                        "title": f"Memory Test Post {iteration}-{i}",
                        "selftext": "Memory test content",
                        "author": f"memory_user_{i}",
                        "score": 10 + i,
                        "num_comments": 2 + i,
                        "url": f"https://example.com/memory_{iteration}_{i}",
                        "permalink": f"/r/memory/comments/post_{iteration}_{i}/",
                        "created_utc": datetime.now(UTC).timestamp(),
                        "upvote_ratio": 0.75,
                        "subreddit": f"memory_test_{iteration}",
                        "check_run_id": check_run_id
                    }
                    storage_service.save_post(post_data)

                session.commit()

                # Clean up old data
                if iteration > 5:
                    storage_service.cleanup_old_data(days_to_keep=0, batch_size=10)
                    session.commit()

            finally:
                session.close()
                gc.collect()  # Force garbage collection

        final_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory

        print(f"Memory growth after 10 iterations: {memory_growth:.1f} MB")
        assert memory_growth < 30  # Should not grow more than 30MB

    def test_database_optimization_effectiveness(self, performance_client, large_dataset):
        """Test that database optimizations are effective."""
        test_client, SessionLocal = performance_client

        session = SessionLocal()
        try:
            # Check that indexes exist
            with session.connection() as conn:
                # Check for index on reddit_posts.post_id
                result = conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='reddit_posts'"
                )).fetchall()

                index_names = [row[0] for row in result]
                assert any("post_id" in name for name in index_names), "Missing post_id index"

                # Check for index on comments.post_id
                result = conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='comments'"
                )).fetchall()

                index_names = [row[0] for row in result]
                assert any("post_id" in name for name in index_names), "Missing comment post_id index"

            # Test query plan for efficient execution
            with PerformanceTimer("Index usage verification") as timer:
                # This should use index
                result = session.execute(text(
                    "EXPLAIN QUERY PLAN SELECT * FROM reddit_posts WHERE post_id = 'test'"
                )).fetchall()

                query_plan = " ".join([str(row) for row in result])
                assert "INDEX" in query_plan.upper(), "Query not using index"

            assert timer.elapsed < 0.01  # Should be very fast

        finally:
            session.close()

    def test_concurrent_performance_impact(self, performance_client):
        """Test performance impact of concurrent operations."""
        test_client, SessionLocal = performance_client

        # Baseline: single operation performance
        mock_reddit_service = MagicMock()
        mock_reddit_service.get_posts.return_value = [
            {
                "id": "baseline_post",
                "title": "Baseline Post",
                "selftext": "Baseline content",
                "author": "baseline_user",
                "score": 50,
                "num_comments": 5,
                "url": "https://example.com/baseline",
                "permalink": "/r/baseline/comments/baseline_post/",
                "created_utc": datetime.now(UTC).timestamp(),
                "upvote_ratio": 0.80,
                "subreddit": "baseline"
            }
        ]
        mock_reddit_service.get_comments.return_value = []

        with patch('app.main.RedditService', return_value=mock_reddit_service), \
             patch('app.main.scrape_article_text', return_value="Scraped content"), \
             patch('app.main.summarize_content', return_value="Summary"):

            # Single request baseline
            with PerformanceTimer("Single request baseline") as baseline_timer:
                response = test_client.get("/check-updates/baseline/performance")

            assert response.status_code == 200
            baseline_time = baseline_timer.elapsed

            # Concurrent requests test (simulated by rapid sequential requests)
            with PerformanceTimer("Multiple rapid requests") as concurrent_timer:
                responses = []
                for i in range(5):
                    response = test_client.get(f"/check-updates/concurrent_{i}/performance")
                    responses.append(response)

            # All should succeed
            for response in responses:
                assert response.status_code == 200

            avg_concurrent_time = concurrent_timer.elapsed / 5

            # Concurrent performance shouldn't be significantly worse
            performance_ratio = avg_concurrent_time / baseline_time
            print(f"Performance ratio (concurrent/baseline): {performance_ratio:.2f}")

            # Should not be more than 3x slower under concurrent load
            assert performance_ratio < 3.0
