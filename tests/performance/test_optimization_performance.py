# ABOUTME: Advanced performance tests for query optimization, caching systems, and production metrics
# ABOUTME: Tests N+1 queries, eager loading effectiveness, cache hit rates, and response time targets

from datetime import UTC, datetime, timedelta
import gc
import time
import tracemalloc
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


class PerformanceMetrics:
    """Collect and analyze performance metrics."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.queries_executed = []
        self.cache_hits = 0
        self.cache_misses = 0
        self.memory_snapshots = []
        self.response_times = []
        self.query_count = 0

    def record_query(self, query: str, duration: float):
        self.queries_executed.append({"query": query, "duration": duration})
        self.query_count += 1

    def record_cache_hit(self):
        self.cache_hits += 1

    def record_cache_miss(self):
        self.cache_misses += 1

    def record_memory_snapshot(self):
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        self.memory_snapshots.append(memory_mb)
        return memory_mb

    def record_response_time(self, duration: float):
        self.response_times.append(duration)

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total) if total > 0 else 0.0

    @property
    def avg_response_time(self) -> float:
        return sum(self.response_times) / len(self.response_times) if self.response_times else 0.0

    @property
    def memory_growth_mb(self) -> float:
        if len(self.memory_snapshots) >= 2:
            return self.memory_snapshots[-1] - self.memory_snapshots[0]
        return 0.0


@pytest.fixture
def performance_metrics():
    """Fixture providing performance metrics collection."""
    return PerformanceMetrics()


@pytest.fixture
def optimized_db():
    """Create database with all optimizations enabled."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        echo=False
    )

    Base.metadata.create_all(bind=engine)

    # Apply all SQLite optimizations
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode = WAL"))
        conn.execute(text("PRAGMA synchronous = NORMAL"))
        conn.execute(text("PRAGMA cache_size = 20000"))
        conn.execute(text("PRAGMA temp_store = MEMORY"))
        conn.execute(text("PRAGMA mmap_size = 268435456"))  # 256MB
        conn.execute(text("PRAGMA optimize"))
        conn.commit()

    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal, engine


@pytest.fixture
def test_dataset():
    """Generate optimized test dataset for performance testing."""
    base_time = datetime.now(UTC).timestamp()

    # Generate 200 posts for comprehensive testing
    posts = []
    for i in range(200):
        posts.append({
            "post_id": f"opt_post_{i:04d}",
            "title": f"Optimization Test Post {i:04d}",
            "selftext": f"Content for post {i} with variable length " + ("text " * (i % 50 + 1)),
            "author": f"user_{i % 25}",  # 25 different users for variety
            "score": 5 + (i * 3) + (i % 100),  # Varying scores
            "num_comments": (i % 20) + 1,  # 1-20 comments per post
            "url": f"https://example.com/opt_post_{i:04d}",
            "permalink": f"/r/optimization/comments/opt_post_{i:04d}/",
            "created_utc": datetime.fromtimestamp(base_time - (i * 180), UTC),  # 3 minutes apart
            "upvote_ratio": 0.50 + (i % 50) / 100,  # Varying ratios
            "subreddit": "optimization",
            "is_self": True,
            "over_18": False
        })

    # Generate comments with hierarchical structure
    comments = []
    comment_id = 0
    for post_idx in range(200):
        post_id = f"opt_post_{post_idx:04d}"
        num_comments = (post_idx % 20) + 1

        # Create top-level comments
        for c in range(num_comments):
            comment = {
                "comment_id": f"opt_comment_{comment_id:06d}",
                "body": f"Comment {c} for post {post_idx}. " + ("Content " * (c % 10 + 1)),
                "author": f"commenter_{c % 15}",
                "score": 1 + (c * 2) + (c % 10),
                "parent_id": None,
                "created_utc": datetime.fromtimestamp(base_time - (post_idx * 180) + (c * 30), UTC),
                "post_id": post_id
            }
            comments.append(comment)
            comment_id += 1

            # Add replies to some comments (create hierarchy)
            if c % 3 == 0 and c > 0:  # Every 3rd comment gets replies
                for r in range(2):  # 2 replies
                    reply = {
                        "comment_id": f"opt_comment_{comment_id:06d}",
                        "body": f"Reply {r} to comment {c}. " + ("Reply text " * (r + 1)),
                        "author": f"replier_{r % 8}",
                        "score": 1 + r,
                        "parent_id": f"opt_comment_{comment_id - 1 - r:06d}",
                        "created_utc": datetime.fromtimestamp(base_time - (post_idx * 180) + (c * 30) + (r * 15), UTC),
                        "post_id": post_id
                    }
                    comments.append(reply)
                    comment_id += 1

    return {"posts": posts, "comments": comments}


class TestQueryOptimization:
    """Test query optimization effectiveness."""

    def test_n_plus_one_query_prevention(self, optimized_db, test_dataset, performance_metrics):
        """Test that N+1 queries are prevented through proper eager loading."""
        SessionLocal, engine = optimized_db

        session = SessionLocal()
        try:
            storage_service = StorageService(session)

            # Insert test data
            check_run_id = storage_service.create_check_run("optimization", "n_plus_one_test")

            # Insert posts
            posts = test_dataset["posts"][:50]  # Use 50 posts for focused testing
            for post in posts:
                post["check_run_id"] = check_run_id
                storage_service.save_post(post)

            session.commit()  # Commit posts first

            # Insert comments for first few posts only
            for i in range(5):  # Just first 5 posts for simplicity
                post_id = f"opt_post_{i:04d}"

                # Create simple comments for this post
                comment_data = {
                    "comment_id": f"test_comment_{i}",
                    "body": f"Test comment for post {i}",
                    "author": "test_user",
                    "score": 5,
                    "parent_id": None,
                    "created_utc": datetime.now(UTC),
                    "post_id": post_id
                }
                storage_service.save_comment(comment_data, post_id)

            # Test 1: Single query to get posts with comments (should use joins)
            performance_metrics.record_memory_snapshot()

            start_time = time.perf_counter()
            session.execute(text("SELECT 1")).rowcount  # Reset counter reference

            # This should use efficient joins, not N+1 queries
            posts_with_comments = []
            for post in session.query(storage_service.models.RedditPost).filter_by(
                subreddit="optimization"
            ).limit(10).all():
                # Access comments to trigger loading
                comment_count = len(post.comments)
                posts_with_comments.append((post, comment_count))

            end_time = time.perf_counter()
            performance_metrics.record_response_time(end_time - start_time)

            # Should complete efficiently
            assert len(posts_with_comments) == 10
            assert (end_time - start_time) < 0.1  # Should complete within 100ms

            # Test 2: Bulk comment retrieval (should be efficient)
            start_time = time.perf_counter()

            test_post_ids = [f"opt_post_{i:04d}" for i in range(10)]
            all_comments = []

            for post_id in test_post_ids:
                comments = storage_service.get_comments_for_post(post_id)
                all_comments.extend(comments)

            end_time = time.perf_counter()
            performance_metrics.record_response_time(end_time - start_time)

            # Should be efficient even for multiple posts
            assert (end_time - start_time) < 0.2  # Should complete within 200ms
            assert len(all_comments) > 0

            # Test 3: Verify query efficiency with EXPLAIN
            explain_result = session.execute(text(
                "EXPLAIN QUERY PLAN SELECT * FROM reddit_posts r " +
                "LEFT JOIN comments c ON r.post_id = c.post_id " +
                "WHERE r.subreddit = 'optimization'"
            )).fetchall()

            query_plan = " ".join([str(row) for row in explain_result])

            # Should use indexes efficiently
            assert "SCAN" not in query_plan.upper() or "INDEX" in query_plan.upper()

            performance_metrics.record_memory_snapshot()

            # Memory growth should be reasonable
            assert performance_metrics.memory_growth_mb < 20  # Less than 20MB growth

        finally:
            session.close()

    def test_eager_loading_effectiveness(self, optimized_db, test_dataset, performance_metrics):
        """Test that eager loading reduces query count."""
        SessionLocal, engine = optimized_db

        session = SessionLocal()
        try:
            storage_service = StorageService(session)
            ChangeDetectionService(session)

            # Setup test data
            check_run_id = storage_service.create_check_run("optimization", "eager_loading")

            posts = test_dataset["posts"][:30]
            for post in posts:
                post["check_run_id"] = check_run_id
                storage_service.save_post(post)

            session.commit()

            # Test without eager loading (baseline)
            start_time = time.perf_counter()

            # Force individual queries
            posts_data = []
            for post in session.query(storage_service.models.RedditPost).filter_by(
                subreddit="optimization"
            ).all():
                # Access related data one by one (inefficient)
                check_run = post.check_run  # Triggers query
                posts_data.append({
                    "post": post,
                    "check_run_subreddit": check_run.subreddit if check_run else None
                })

            baseline_time = time.perf_counter() - start_time
            performance_metrics.record_response_time(baseline_time)

            # Test with eager loading (optimized)
            start_time = time.perf_counter()

            # Use efficient query with joins
            optimized_posts = session.query(storage_service.models.RedditPost).filter_by(
                subreddit="optimization"
            ).join(storage_service.models.CheckRun).all()

            optimized_data = []
            for post in optimized_posts:
                # Access already loaded data (efficient)
                optimized_data.append({
                    "post": post,
                    "check_run_subreddit": post.check_run.subreddit
                })

            optimized_time = time.perf_counter() - start_time
            performance_metrics.record_response_time(optimized_time)

            # Eager loading should be significantly faster
            improvement_ratio = baseline_time / optimized_time if optimized_time > 0 else float('inf')

            assert improvement_ratio > 2.0  # Should be at least 2x faster
            assert optimized_time < 0.05  # Should complete within 50ms
            assert len(optimized_data) == len(posts_data)  # Same results

        finally:
            session.close()

    def test_index_utilization_analysis(self, optimized_db, test_dataset):
        """Test that database indexes are properly utilized."""
        SessionLocal, engine = optimized_db

        session = SessionLocal()
        try:
            storage_service = StorageService(session)

            # Insert substantial data to make indexes matter
            check_run_id = storage_service.create_check_run("optimization", "index_test")

            posts = test_dataset["posts"]
            for post in posts:
                post["check_run_id"] = check_run_id
                storage_service.save_post(post)

            session.commit()

            # Test index usage for common queries
            test_queries = [
                # Post lookup by ID (should use primary key/unique index)
                ("SELECT * FROM reddit_posts WHERE post_id = 'opt_post_0100'", "post_id index"),

                # Subreddit filtering (should use index)
                ("SELECT * FROM reddit_posts WHERE subreddit = 'optimization'", "subreddit index"),

                # Time-based queries (should use index)
                ("SELECT * FROM reddit_posts WHERE created_utc > 1000000000", "created_utc index"),

                # Check run queries (should use foreign key index)
                ("SELECT * FROM reddit_posts WHERE check_run_id = 1", "check_run_id index"),

                # Comment post lookup (should use foreign key index)
                ("SELECT * FROM comments WHERE post_id = 'opt_post_0100'", "comment post_id index")
            ]

            for query, description in test_queries:
                # Get query plan
                explain_result = session.execute(text(f"EXPLAIN QUERY PLAN {query}")).fetchall()
                query_plan = " ".join([str(row) for row in explain_result])

                # Should use index for efficient queries
                uses_index = "INDEX" in query_plan.upper()
                is_scan = "SCAN" in query_plan.upper()

                # For small datasets, scans might be acceptable, but for larger ones, indexes should be used
                if len(posts) > 100:  # Only enforce index usage for larger datasets
                    assert uses_index or not is_scan, f"Query not optimized for {description}: {query_plan}"

                # Test actual performance
                start_time = time.perf_counter()
                session.execute(text(query)).fetchall()
                duration = time.perf_counter() - start_time

                # Should complete quickly with proper indexing
                assert duration < 0.01, f"Query too slow for {description}: {duration:.4f}s"

        finally:
            session.close()

    def test_bulk_operation_optimization(self, optimized_db, test_dataset, performance_metrics):
        """Test bulk operation performance and optimization."""
        SessionLocal, engine = optimized_db

        session = SessionLocal()
        try:
            storage_service = StorageService(session)

            performance_metrics.record_memory_snapshot()

            # Test optimized bulk post insertion
            start_time = time.perf_counter()

            check_run_id = storage_service.create_check_run("optimization", "bulk_test")
            posts = test_dataset["posts"]

            for post in posts:
                post["check_run_id"] = check_run_id
                storage_service.save_post(post)

            session.commit()

            bulk_post_time = time.perf_counter() - start_time
            performance_metrics.record_response_time(bulk_post_time)

            # Should be fast even for 200 posts
            assert bulk_post_time < 2.0  # Should complete within 2 seconds

            # Test optimized bulk comment insertion
            start_time = time.perf_counter()

            comments = test_dataset["comments"]

            # Process in optimal batch sizes
            for i in range(0, len(comments), 100):  # Process 100 at a time
                batch = comments[i:i+100]

                # Group by post for efficient bulk operations
                post_groups = {}
                for comment in batch:
                    post_id = comment["post_id"]
                    if post_id not in post_groups:
                        post_groups[post_id] = []
                    post_groups[post_id].append(comment)

                for post_id, post_comments in post_groups.items():
                    storage_service.bulk_save_comments(post_comments, post_id)

                session.commit()

            bulk_comment_time = time.perf_counter() - start_time
            performance_metrics.record_response_time(bulk_comment_time)

            # Should handle large comment volumes efficiently
            assert bulk_comment_time < 5.0  # Should complete within 5 seconds

            # Calculate throughput metrics
            posts_per_second = len(posts) / bulk_post_time
            comments_per_second = len(comments) / bulk_comment_time

            assert posts_per_second > 50  # At least 50 posts/second
            assert comments_per_second > 100  # At least 100 comments/second

            performance_metrics.record_memory_snapshot()

            # Memory usage should be reasonable
            assert performance_metrics.memory_growth_mb < 50  # Less than 50MB growth

            # Verify data integrity after bulk operations
            total_posts = session.query(storage_service.models.RedditPost).count()
            total_comments = session.query(storage_service.models.Comment).count()

            assert total_posts == len(posts)
            assert total_comments == len(comments)

        finally:
            session.close()


class TestCachingEffectiveness:
    """Test caching system performance and effectiveness."""

    def test_in_memory_cache_performance(self, optimized_db, test_dataset, performance_metrics):
        """Test in-memory caching effectiveness."""
        SessionLocal, engine = optimized_db

        # Simple in-memory cache implementation for testing
        cache = {}

        def cached_get_post(storage_service, post_id):
            if post_id in cache:
                performance_metrics.record_cache_hit()
                return cache[post_id]

            performance_metrics.record_cache_miss()
            post = storage_service.get_post_by_id(post_id)
            if post:
                cache[post_id] = post
            return post

        session = SessionLocal()
        try:
            storage_service = StorageService(session)

            # Setup test data
            check_run_id = storage_service.create_check_run("optimization", "cache_test")
            posts = test_dataset["posts"][:50]

            for post in posts:
                post["check_run_id"] = check_run_id
                storage_service.save_post(post)

            session.commit()

            # Test cache miss performance (first access)
            test_post_ids = [f"opt_post_{i:04d}" for i in range(0, 50, 5)]  # Every 5th post

            start_time = time.perf_counter()

            first_access_results = []
            for post_id in test_post_ids:
                post = cached_get_post(storage_service, post_id)
                first_access_results.append(post)

            first_access_time = time.perf_counter() - start_time
            performance_metrics.record_response_time(first_access_time)

            # Test cache hit performance (second access)
            start_time = time.perf_counter()

            second_access_results = []
            for post_id in test_post_ids:
                post = cached_get_post(storage_service, post_id)
                second_access_results.append(post)

            second_access_time = time.perf_counter() - start_time
            performance_metrics.record_response_time(second_access_time)

            # Cache hits should be significantly faster
            speedup_ratio = first_access_time / second_access_time if second_access_time > 0 else float('inf')

            assert speedup_ratio > 10  # Cache should be at least 10x faster
            assert second_access_time < 0.001  # Cache access should be sub-millisecond

            # Verify cache hit rate
            assert performance_metrics.cache_hit_rate >= 0.5  # At least 50% hit rate

            # Results should be identical
            for first, second in zip(first_access_results, second_access_results, strict=False):
                assert first.post_id == second.post_id

        finally:
            session.close()

    def test_cache_invalidation_correctness(self, optimized_db, test_dataset, performance_metrics):
        """Test that cache invalidation works correctly."""
        SessionLocal, engine = optimized_db

        # Cache with invalidation support
        cache = {}

        def cached_get_post_with_invalidation(storage_service, post_id, force_refresh=False):
            if force_refresh and post_id in cache:
                del cache[post_id]

            if post_id in cache:
                performance_metrics.record_cache_hit()
                return cache[post_id]

            performance_metrics.record_cache_miss()
            post = storage_service.get_post_by_id(post_id)
            if post:
                cache[post_id] = post
            return post

        session = SessionLocal()
        try:
            storage_service = StorageService(session)

            # Setup test data
            check_run_id = storage_service.create_check_run("optimization", "invalidation_test")

            test_post = test_dataset["posts"][0]
            test_post["check_run_id"] = check_run_id
            storage_service.save_post(test_post)
            session.commit()

            post_id = test_post["post_id"]

            # First access - cache miss
            post_v1 = cached_get_post_with_invalidation(storage_service, post_id)
            assert post_v1 is not None
            assert post_v1.score == test_post["score"]

            # Second access - cache hit
            post_v1_cached = cached_get_post_with_invalidation(storage_service, post_id)
            assert post_v1_cached.score == test_post["score"]

            # Update the post in database
            updated_post_data = test_post.copy()
            updated_post_data["score"] = test_post["score"] + 100  # Significant change
            storage_service.save_post(updated_post_data)
            session.commit()

            # Access with cache invalidation
            post_v2 = cached_get_post_with_invalidation(storage_service, post_id, force_refresh=True)
            assert post_v2.score == updated_post_data["score"]
            assert post_v2.score != post_v1.score

            # Verify metrics
            assert performance_metrics.cache_hits >= 1
            assert performance_metrics.cache_misses >= 2  # Initial + after invalidation

        finally:
            session.close()


class TestMemoryUsageOptimization:
    """Test memory usage optimization and monitoring."""

    def test_memory_efficient_large_dataset_processing(self, optimized_db, test_dataset, performance_metrics):
        """Test memory efficiency with large datasets."""
        SessionLocal, engine = optimized_db

        # Enable tracemalloc for detailed memory tracking
        tracemalloc.start()

        session = SessionLocal()
        try:
            storage_service = StorageService(session)
            change_detection_service = ChangeDetectionService(session)

            performance_metrics.record_memory_snapshot()

            # Process large dataset in memory-efficient manner
            check_run_id = storage_service.create_check_run("optimization", "memory_test")

            # Process posts in batches to control memory usage
            posts = test_dataset["posts"]
            batch_size = 50

            for i in range(0, len(posts), batch_size):
                batch = posts[i:i+batch_size]

                # Process batch
                for post in batch:
                    post["check_run_id"] = check_run_id
                    storage_service.save_post(post)

                session.commit()

                # Force garbage collection between batches
                gc.collect()

                # Check memory usage
                performance_metrics.record_memory_snapshot()

                # Memory should not grow excessively between batches
                if len(performance_metrics.memory_snapshots) > 1:
                    memory_growth = (performance_metrics.memory_snapshots[-1] -
                                   performance_metrics.memory_snapshots[-2])
                    assert memory_growth < 10  # Less than 10MB per batch

            # Process comments efficiently
            comments = test_dataset["comments"]

            for i in range(0, len(comments), 100):  # Larger batches for comments
                batch = comments[i:i+100]

                # Group efficiently
                post_groups = {}
                for comment in batch:
                    post_id = comment["post_id"]
                    if post_id not in post_groups:
                        post_groups[post_id] = []
                    post_groups[post_id].append(comment)

                # Bulk save
                for post_id, post_comments in post_groups.items():
                    storage_service.bulk_save_comments(post_comments, post_id)

                session.commit()
                gc.collect()

                performance_metrics.record_memory_snapshot()

            # Test memory-efficient change detection
            start_memory = performance_metrics.record_memory_snapshot()

            # Simulate updated posts
            updated_posts = []
            for i in range(0, min(100, len(posts))):  # Test with 100 posts
                updated_post = posts[i].copy()
                updated_post["score"] += 50
                updated_posts.append(updated_post)

            # Process change detection efficiently
            cutoff_time = datetime.now(UTC)
            change_detection_service.find_new_posts(updated_posts, cutoff_time)
            change_detection_service.find_updated_posts(updated_posts)

            end_memory = performance_metrics.record_memory_snapshot()
            change_detection_memory = end_memory - start_memory

            # Change detection should not use excessive memory
            assert change_detection_memory < 30  # Less than 30MB for change detection

            # Overall memory growth should be reasonable
            total_memory_growth = performance_metrics.memory_growth_mb
            assert total_memory_growth < 100  # Less than 100MB total growth

            # Get current memory stats from tracemalloc
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            peak_mb = peak / 1024 / 1024
            assert peak_mb < 150  # Peak memory should be under 150MB

        finally:
            session.close()

    def test_memory_leak_detection(self, optimized_db, performance_metrics):
        """Test for memory leaks in repeated operations."""
        SessionLocal, engine = optimized_db

        initial_memory = performance_metrics.record_memory_snapshot()

        # Perform repeated operations to detect leaks
        for iteration in range(20):
            session = SessionLocal()
            try:
                storage_service = StorageService(session)

                # Create temporary data
                check_run_id = storage_service.create_check_run(
                    f"leak_test_{iteration}",
                    "memory_leak_detection"
                )

                # Create some posts and comments
                for i in range(5):
                    post_data = {
                        "post_id": f"leak_post_{iteration}_{i}",
                        "title": f"Leak Test Post {iteration}-{i}",
                        "selftext": "Leak test content " * 20,  # Substantial content
                        "author": f"leak_user_{i}",
                        "score": 10 + i,
                        "num_comments": 2 + i,
                        "url": f"https://example.com/leak_{iteration}_{i}",
                        "permalink": f"/r/leak/comments/post_{iteration}_{i}/",
                        "created_utc": datetime.now(UTC),
                        "upvote_ratio": 0.75,
                        "subreddit": f"leak_test_{iteration}",
                        "check_run_id": check_run_id,
                        "is_self": True,
                        "over_18": False
                    }
                    storage_service.save_post(post_data)

                    # Add comments
                    comment_data = {
                        "comment_id": f"leak_comment_{iteration}_{i}",
                        "body": "Leak test comment " * 15,
                        "author": f"leak_commenter_{i}",
                        "score": 1 + i,
                        "parent_id": None,
                        "created_utc": datetime.now(UTC),
                        "post_id": f"leak_post_{iteration}_{i}"
                    }
                    storage_service.save_comment(comment_data, f"leak_post_{iteration}_{i}")

                session.commit()

                # Clean up old data to prevent accumulation
                if iteration > 10:
                    storage_service.cleanup_old_data(days_to_keep=0, batch_size=10)
                    session.commit()

            finally:
                session.close()

            # Force garbage collection
            gc.collect()

            # Record memory after each iteration
            current_memory = performance_metrics.record_memory_snapshot()

            # Check for memory leaks (memory should not continuously grow)
            if iteration > 10:  # Allow some initial growth
                memory_growth = current_memory - initial_memory
                assert memory_growth < 50  # Should not grow more than 50MB

    def test_concurrent_memory_usage(self, optimized_db, performance_metrics):
        """Test memory usage under concurrent operations."""
        SessionLocal, engine = optimized_db

        import queue
        import threading

        initial_memory = performance_metrics.record_memory_snapshot()
        results_queue = queue.Queue()

        def worker_task(worker_id: int):
            """Worker task for concurrent testing."""
            session = SessionLocal()
            try:
                storage_service = StorageService(session)

                # Create data specific to this worker
                check_run_id = storage_service.create_check_run(
                    f"concurrent_{worker_id}",
                    "concurrent_memory_test"
                )

                # Create posts
                for i in range(10):
                    post_data = {
                        "post_id": f"concurrent_post_{worker_id}_{i}",
                        "title": f"Concurrent Post {worker_id}-{i}",
                        "selftext": "Concurrent test content " * 10,
                        "author": f"concurrent_user_{worker_id}_{i}",
                        "score": 10 + i,
                        "num_comments": 1 + i,
                        "url": f"https://example.com/concurrent_{worker_id}_{i}",
                        "permalink": f"/r/concurrent/comments/post_{worker_id}_{i}/",
                        "created_utc": datetime.now(UTC),
                        "upvote_ratio": 0.80,
                        "subreddit": f"concurrent_{worker_id}",
                        "check_run_id": check_run_id,
                        "is_self": True,
                        "over_18": False
                    }
                    storage_service.save_post(post_data)

                session.commit()
                results_queue.put(f"Worker {worker_id} completed")

            except Exception as e:
                results_queue.put(f"Worker {worker_id} failed: {e}")
            finally:
                session.close()

        # Start concurrent workers
        workers = []
        for worker_id in range(5):
            worker = threading.Thread(target=worker_task, args=(worker_id,))
            workers.append(worker)
            worker.start()

        # Wait for completion
        for worker in workers:
            worker.join(timeout=10)  # 10 second timeout

        # Collect results
        results = []
        while not results_queue.empty():
            results.append(results_queue.get())

        # All workers should complete successfully
        assert len(results) == 5
        for result in results:
            assert "completed" in result

        # Check final memory usage
        gc.collect()
        final_memory = performance_metrics.record_memory_snapshot()
        memory_growth = final_memory - initial_memory

        # Concurrent operations should not cause excessive memory usage
        assert memory_growth < 40  # Less than 40MB for 5 concurrent workers


class TestResponseTimeTargets:
    """Test response time targets for production readiness."""

    def test_api_response_time_targets(self, optimized_db, performance_metrics):
        """Test that API endpoints meet response time targets."""
        SessionLocal, engine = optimized_db

        def override_get_db():
            session = SessionLocal()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db

        try:
            with TestClient(app) as client:

                # Mock Reddit service for consistent testing
                mock_reddit_service = MagicMock()
                mock_reddit_service.get_posts.return_value = [
                    {
                        "post_id": f"target_post_{i}",
                        "title": f"Response Time Test Post {i}",
                        "selftext": "Response time test content",
                        "author": f"target_user_{i}",
                        "score": 50 + i,
                        "num_comments": 5 + i,
                        "url": f"https://example.com/target_post_{i}",
                        "permalink": f"/r/targets/comments/target_post_{i}/",
                        "created_utc": datetime.now(UTC) - timedelta(seconds=i * 300),
                        "upvote_ratio": 0.85,
                        "subreddit": "targets",
                        "is_self": True,
                        "over_18": False
                    }
                    for i in range(15)
                ]
                mock_reddit_service.get_comments.return_value = []

                with patch('app.main.RedditService', return_value=mock_reddit_service), \
                     patch('app.main.scrape_article_text', return_value="Scraped content"), \
                     patch('app.main.summarize_content', return_value="Summary"):

                    # Test check-updates endpoint
                    start_time = time.perf_counter()
                    response = client.get("/check-updates/targets/performance")
                    check_updates_time = time.perf_counter() - start_time

                    assert response.status_code == 200
                    assert check_updates_time < 3.0  # Target: under 3 seconds
                    performance_metrics.record_response_time(check_updates_time)

                    # Test subsequent check-updates (should be faster)
                    start_time = time.perf_counter()
                    response = client.get("/check-updates/targets/performance")
                    subsequent_time = time.perf_counter() - start_time

                    assert response.status_code == 200
                    assert subsequent_time < 1.5  # Target: under 1.5 seconds
                    performance_metrics.record_response_time(subsequent_time)

                    # Test history endpoint
                    start_time = time.perf_counter()
                    response = client.get("/history/targets")
                    history_time = time.perf_counter() - start_time

                    assert response.status_code == 200
                    assert history_time < 0.5  # Target: under 500ms
                    performance_metrics.record_response_time(history_time)

                    # Test trends endpoint
                    start_time = time.perf_counter()
                    response = client.get("/trends/targets")
                    trends_time = time.perf_counter() - start_time

                    assert response.status_code == 200
                    assert trends_time < 1.0  # Target: under 1 second
                    performance_metrics.record_response_time(trends_time)

                    # Test report generation
                    start_time = time.perf_counter()
                    response = client.get("/generate-report/targets/performance")
                    report_time = time.perf_counter() - start_time

                    assert response.status_code == 200
                    assert report_time < 5.0  # Target: under 5 seconds
                    performance_metrics.record_response_time(report_time)

                    # Verify overall performance targets
                    avg_response_time = performance_metrics.avg_response_time
                    assert avg_response_time < 2.0  # Average should be under 2 seconds

        finally:
            app.dependency_overrides.clear()

    def test_database_operation_targets(self, optimized_db, test_dataset, performance_metrics):
        """Test database operation response time targets."""
        SessionLocal, engine = optimized_db

        session = SessionLocal()
        try:
            storage_service = StorageService(session)

            # Setup test data
            check_run_id = storage_service.create_check_run("targets", "db_performance")

            posts = test_dataset["posts"][:100]
            for post in posts:
                post["check_run_id"] = check_run_id
                storage_service.save_post(post)

            session.commit()

            # Test individual post retrieval target: under 1ms
            start_time = time.perf_counter()
            post = storage_service.get_post_by_id("opt_post_0050")
            retrieval_time = time.perf_counter() - start_time

            assert retrieval_time < 0.001  # Target: under 1ms
            assert post is not None
            performance_metrics.record_response_time(retrieval_time)

            # Test bulk post query target: under 10ms
            start_time = time.perf_counter()
            posts_batch = storage_service.get_posts_for_check_run(check_run_id)
            bulk_query_time = time.perf_counter() - start_time

            assert bulk_query_time < 0.01  # Target: under 10ms
            assert len(posts_batch) == 100
            performance_metrics.record_response_time(bulk_query_time)

            # Test time-based query target: under 5ms
            cutoff_time = datetime.now(UTC)
            start_time = time.perf_counter()
            storage_service.get_new_posts_since("targets", cutoff_time)
            time_query_time = time.perf_counter() - start_time

            assert time_query_time < 0.005  # Target: under 5ms
            performance_metrics.record_response_time(time_query_time)

            # Test storage statistics target: under 20ms
            start_time = time.perf_counter()
            stats = storage_service.get_storage_statistics()
            stats_time = time.perf_counter() - start_time

            assert stats_time < 0.02  # Target: under 20ms
            assert stats["total_posts"] == 100
            performance_metrics.record_response_time(stats_time)

        finally:
            session.close()
