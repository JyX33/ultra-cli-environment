# ABOUTME: Tests for StorageService data retention and cleanup functionality
# ABOUTME: Tests covering retention periods, cascade deletions, archival, and performance optimization

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.check_run import CheckRun
from app.models.comment import Comment
from app.models.post_snapshot import PostSnapshot
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
def sample_data_with_timestamps(storage_service, session):
    """Create sample data with various timestamps for testing retention."""
    base_time = datetime.now(UTC)

    # Create data at different time periods
    data_points = [
        (base_time - timedelta(days=90), "old"),      # 90 days ago
        (base_time - timedelta(days=45), "medium"),   # 45 days ago
        (base_time - timedelta(days=15), "recent"),   # 15 days ago
        (base_time - timedelta(days=5), "new"),       # 5 days ago
    ]

    created_data = []

    for timestamp, age_category in data_points:
        # Create check run
        check_run_id = storage_service.create_check_run(f"python_{age_category}", "testing")

        # Manually update the timestamp to our desired value
        check_run = session.get(CheckRun, check_run_id)
        check_run.timestamp = timestamp
        session.commit()

        # Create post
        post_data = {
            'post_id': f'{age_category}_post',
            'subreddit': f'python_{age_category}',
            'title': f'{age_category} Post',
            'author': f'user_{age_category}',
            'selftext': f'{age_category} content',
            'score': 10,
            'num_comments': 2,
            'url': f'https://reddit.com/{age_category}',
            'permalink': f'/r/python_{age_category}/post',
            'is_self': True,
            'over_18': False,
            'created_utc': timestamp,
            'check_run_id': check_run_id
        }

        post_id = storage_service.save_post(post_data)

        # Create comments
        comment_data = {
            'comment_id': f'{age_category}_comment',
            'author': f'commenter_{age_category}',
            'body': f'{age_category} comment',
            'score': 5,
            'created_utc': timestamp,
            'parent_id': None,
            'is_submitter': False,
            'stickied': False,
            'distinguished': None
        }

        comment_id = storage_service.save_comment(comment_data, post_id)

        # Create snapshot
        snapshot_id = storage_service.save_post_snapshot(post_id, check_run_id, 10, 2)

        created_data.append({
            'age_category': age_category,
            'timestamp': timestamp,
            'check_run_id': check_run_id,
            'post_id': post_id,
            'comment_id': comment_id,
            'snapshot_id': snapshot_id
        })

    return created_data


class TestStorageServiceCleanupOldData:
    """Test cleanup_old_data functionality."""

    def test_cleanup_old_data_basic(self, storage_service, sample_data_with_timestamps, session):
        """Test basic cleanup of old data based on retention days."""
        # Keep data from last 30 days (should remove 90-day and 45-day old data)
        deleted_count = storage_service.cleanup_old_data(days_to_keep=30)

        # Should delete 2 check runs (90-day and 45-day old)
        assert deleted_count == 2

        # Verify remaining data
        remaining_check_runs = session.query(CheckRun).all()
        remaining_subreddits = [cr.subreddit for cr in remaining_check_runs]

        # Should only have recent and new data
        assert 'python_recent' in remaining_subreddits
        assert 'python_new' in remaining_subreddits
        assert 'python_old' not in remaining_subreddits
        assert 'python_medium' not in remaining_subreddits

    def test_cleanup_old_data_cascade_deletions(self, storage_service, sample_data_with_timestamps, session):
        """Test that cleanup properly cascades to related data."""
        # Count initial data
        initial_posts = session.query(RedditPost).count()
        initial_comments = session.query(Comment).count()
        initial_snapshots = session.query(PostSnapshot).count()

        assert initial_posts == 4
        assert initial_comments == 4
        assert initial_snapshots == 4

        # Cleanup old data (keep last 20 days)
        deleted_count = storage_service.cleanup_old_data(days_to_keep=20)

        # Should delete 2 check runs, which should cascade to posts, comments, and snapshots
        assert deleted_count == 2

        # Verify cascaded deletions
        remaining_posts = session.query(RedditPost).count()
        remaining_comments = session.query(Comment).count()
        remaining_snapshots = session.query(PostSnapshot).count()

        assert remaining_posts == 2  # Only recent and new posts
        assert remaining_comments == 2  # Only recent and new comments
        assert remaining_snapshots == 2  # Only recent and new snapshots

    def test_cleanup_old_data_no_data_to_delete(self, storage_service, sample_data_with_timestamps):
        """Test cleanup when no data is old enough to delete."""
        # Keep data from last 365 days (nothing should be deleted)
        deleted_count = storage_service.cleanup_old_data(days_to_keep=365)

        assert deleted_count == 0

    def test_cleanup_old_data_all_data_old(self, storage_service, sample_data_with_timestamps, session):
        """Test cleanup when all data is older than retention period."""
        # Keep data from last 1 day (everything should be deleted)
        deleted_count = storage_service.cleanup_old_data(days_to_keep=1)

        assert deleted_count == 4  # All 4 check runs deleted

        # Verify all data is gone
        assert session.query(CheckRun).count() == 0
        assert session.query(RedditPost).count() == 0
        assert session.query(Comment).count() == 0
        assert session.query(PostSnapshot).count() == 0

    def test_cleanup_old_data_batch_processing(self, storage_service, session):
        """Test that cleanup handles large datasets in batches."""
        base_time = datetime.now(UTC)
        old_time = base_time - timedelta(days=60)

        # Create many old check runs
        check_run_ids = []
        for i in range(25):  # Create more than default batch size
            check_run_id = storage_service.create_check_run(f"batch_test_{i}", "cleanup_test")

            # Update timestamp to old time
            check_run = session.get(CheckRun, check_run_id)
            check_run.timestamp = old_time
            session.commit()

            check_run_ids.append(check_run_id)

        # Verify data was created
        assert session.query(CheckRun).count() == 25

        # Cleanup with small batch size
        deleted_count = storage_service.cleanup_old_data(days_to_keep=30, batch_size=10)

        # All should be deleted
        assert deleted_count == 25
        assert session.query(CheckRun).count() == 0

    def test_cleanup_old_data_invalid_retention_days(self, storage_service):
        """Test cleanup with invalid retention period."""
        with pytest.raises(ValueError, match="days_to_keep must be positive"):
            storage_service.cleanup_old_data(days_to_keep=0)

        with pytest.raises(ValueError, match="days_to_keep must be positive"):
            storage_service.cleanup_old_data(days_to_keep=-5)

    def test_cleanup_old_data_database_error_handling(self, storage_service, session):
        """Test cleanup handles database errors gracefully."""
        # Mock session to raise error during deletion
        original_query = session.query
        session.query = Mock(side_effect=SQLAlchemyError("Database error"))

        with pytest.raises(RuntimeError, match="Failed to cleanup old data"):
            storage_service.cleanup_old_data(days_to_keep=30)

        # Restore original query
        session.query = original_query


class TestStorageServiceArchiveOldCheckRuns:
    """Test archive_old_check_runs functionality."""

    def test_archive_old_check_runs_basic(self, storage_service, sample_data_with_timestamps, session):
        """Test basic archiving of old check runs (preserve summaries, remove details)."""
        # Archive check runs older than 30 days
        archived_count = storage_service.archive_old_check_runs(days_to_keep=30)

        # Should archive 2 check runs (90-day and 45-day old)
        assert archived_count == 2

        # Check runs should still exist
        all_check_runs = session.query(CheckRun).all()
        assert len(all_check_runs) == 4

        # But posts, comments, and snapshots for old check runs should be deleted
        # while preserving the check run summary data
        old_check_runs = [cr for cr in all_check_runs if cr.subreddit in ['python_old', 'python_medium']]

        for check_run in old_check_runs:
            # Posts should be deleted
            posts = session.query(RedditPost).filter(RedditPost.check_run_id == check_run.id).all()
            assert len(posts) == 0

            # Comments should be deleted (cascaded from posts)
            # Snapshots should be deleted (cascaded from posts)

    def test_archive_old_check_runs_preserve_summary_data(self, storage_service, sample_data_with_timestamps, session):
        """Test that archiving preserves check run summary statistics."""
        # Get original check run data before archiving
        old_check_runs = session.query(CheckRun).filter(
            CheckRun.subreddit.in_(['python_old', 'python_medium'])
        ).all()

        original_data = {}
        for cr in old_check_runs:
            original_data[cr.id] = {
                'subreddit': cr.subreddit,
                'topic': cr.topic,
                'timestamp': cr.timestamp,
                'posts_found': cr.posts_found,
                'new_posts': cr.new_posts
            }

        # Archive old check runs
        archived_count = storage_service.archive_old_check_runs(days_to_keep=30)
        assert archived_count == 2

        # Verify check run summary data is preserved
        for check_run_id, original in original_data.items():
            archived_check_run = session.get(CheckRun, check_run_id)
            assert archived_check_run is not None
            assert archived_check_run.subreddit == original['subreddit']
            assert archived_check_run.topic == original['topic']
            assert archived_check_run.timestamp == original['timestamp']
            # Note: posts_found and new_posts should remain as they were

    def test_archive_old_check_runs_no_data_to_archive(self, storage_service, sample_data_with_timestamps):
        """Test archiving when no data is old enough to archive."""
        # Archive check runs older than 365 days (nothing should be archived)
        archived_count = storage_service.archive_old_check_runs(days_to_keep=365)

        assert archived_count == 0

    def test_archive_old_check_runs_partial_cleanup(self, storage_service, sample_data_with_timestamps, session):
        """Test that archiving only removes details, not check run records."""
        initial_check_runs = session.query(CheckRun).count()
        initial_posts = session.query(RedditPost).count()

        # Archive old data
        storage_service.archive_old_check_runs(days_to_keep=30)

        # Check runs should remain the same
        final_check_runs = session.query(CheckRun).count()
        assert final_check_runs == initial_check_runs

        # But some posts should be deleted
        final_posts = session.query(RedditPost).count()
        assert final_posts < initial_posts

    def test_archive_old_check_runs_batch_processing(self, storage_service, session):
        """Test that archiving handles large datasets in batches."""
        base_time = datetime.now(UTC)
        old_time = base_time - timedelta(days=60)

        # Create many old check runs with posts
        for i in range(15):
            check_run_id = storage_service.create_check_run(f"archive_batch_{i}", "test")

            # Update timestamp to old time
            check_run = session.get(CheckRun, check_run_id)
            check_run.timestamp = old_time
            session.commit()

            # Add a post to each
            post_data = {
                'post_id': f'archive_post_{i}',
                'subreddit': f'archive_batch_{i}',
                'title': f'Archive Post {i}',
                'author': 'test_user',
                'selftext': 'Test content',
                'score': 10,
                'num_comments': 2,
                'url': f'https://reddit.com/archive_{i}',
                'permalink': f'/r/archive_batch_{i}/post',
                'is_self': True,
                'over_18': False,
                'created_utc': old_time,
                'check_run_id': check_run_id
            }
            storage_service.save_post(post_data)

        # Verify data was created
        assert session.query(CheckRun).count() == 15
        assert session.query(RedditPost).count() == 15

        # Archive with small batch size
        archived_count = storage_service.archive_old_check_runs(days_to_keep=30, batch_size=5)

        # All check runs should be archived
        assert archived_count == 15

        # Check runs remain, posts are deleted
        assert session.query(CheckRun).count() == 15
        assert session.query(RedditPost).count() == 0


class TestStorageServiceGetStorageStatistics:
    """Test get_storage_statistics functionality."""

    def test_get_storage_statistics_basic(self, storage_service, sample_data_with_timestamps):
        """Test basic storage statistics retrieval."""
        stats = storage_service.get_storage_statistics()

        # Should have counts for all tables
        assert 'check_runs' in stats
        assert 'reddit_posts' in stats
        assert 'comments' in stats
        assert 'post_snapshots' in stats

        # Verify counts match expected data
        assert stats['check_runs'] == 4
        assert stats['reddit_posts'] == 4
        assert stats['comments'] == 4
        assert stats['post_snapshots'] == 4

    def test_get_storage_statistics_with_date_breakdown(self, storage_service, sample_data_with_timestamps):
        """Test storage statistics with date-based breakdown."""
        stats = storage_service.get_storage_statistics(include_date_breakdown=True)

        # Should include date-based analysis
        assert 'date_breakdown' in stats
        assert 'oldest_check_run' in stats
        assert 'newest_check_run' in stats

        # Verify date information
        assert stats['oldest_check_run'] is not None
        assert stats['newest_check_run'] is not None

    def test_get_storage_statistics_empty_database(self, storage_service):
        """Test storage statistics on empty database."""
        stats = storage_service.get_storage_statistics()

        # All counts should be zero
        assert stats['check_runs'] == 0
        assert stats['reddit_posts'] == 0
        assert stats['comments'] == 0
        assert stats['post_snapshots'] == 0

    def test_get_storage_statistics_size_estimation(self, storage_service, sample_data_with_timestamps, session):
        """Test storage statistics includes size estimation."""
        stats = storage_service.get_storage_statistics(include_size_estimation=True)

        # Should include size estimates
        assert 'estimated_size' in stats
        assert 'size_by_table' in stats

        # Size should be reasonable (greater than 0 for non-empty tables)
        assert stats['estimated_size']['total_bytes'] > 0

    def test_get_storage_statistics_retention_analysis(self, storage_service, sample_data_with_timestamps):
        """Test storage statistics includes retention period analysis."""
        stats = storage_service.get_storage_statistics(retention_days=30)

        # Should include retention analysis
        assert 'retention_analysis' in stats
        assert 'data_to_cleanup' in stats['retention_analysis']
        assert 'data_to_keep' in stats['retention_analysis']

        # Should identify old data for cleanup
        assert stats['retention_analysis']['data_to_cleanup'] > 0
        assert stats['retention_analysis']['data_to_keep'] > 0


class TestStorageServiceRetentionConfiguration:
    """Test retention configuration integration."""

    @patch('app.core.config.os.getenv')
    def test_cleanup_with_config_retention_days(self, mock_getenv, storage_service, sample_data_with_timestamps):
        """Test that cleanup uses configuration for retention days."""
        # Mock configuration to return 30 days retention
        mock_getenv.side_effect = lambda key, default=None: "30" if key == "DATA_RETENTION_DAYS" else default

        # Use config-based cleanup
        deleted_count = storage_service.cleanup_old_data_from_config()

        # Should delete 2 old check runs (older than 30 days)
        assert deleted_count == 2

    @patch('app.core.config.config')
    def test_archive_with_config_flag(self, mock_config, storage_service, sample_data_with_timestamps):
        """Test that archiving respects configuration flag."""
        # Mock configuration to enable archiving
        mock_config.DATA_RETENTION_DAYS = 30
        mock_config.ARCHIVE_OLD_DATA = True
        mock_config.CLEANUP_BATCH_SIZE = 100

        # Use config-based archiving
        archived_count = storage_service.archive_old_data_from_config()

        # Should archive 2 old check runs
        assert archived_count == 2

    @patch('app.core.config.os.getenv')
    def test_config_with_default_values(self, mock_getenv, storage_service):
        """Test that retention functions use sensible defaults when config is missing."""
        # Mock configuration to return None (missing values)
        mock_getenv.return_value = None

        # Should use default retention period (30 days)
        # This test verifies the method doesn't crash with missing config
        try:
            deleted_count = storage_service.cleanup_old_data_from_config()
            assert isinstance(deleted_count, int)
        except Exception as e:
            # Should not raise configuration errors
            assert "config" not in str(e).lower()


class TestStorageServiceRetentionPerformance:
    """Test retention operation performance."""

    def test_cleanup_performance_large_dataset(self, storage_service, session):
        """Test cleanup performance with large datasets."""
        import time

        base_time = datetime.now(UTC)
        old_time = base_time - timedelta(days=60)

        # Create a large number of old check runs (but not too many for test performance)
        num_records = 50
        for i in range(num_records):
            check_run_id = storage_service.create_check_run(f"perf_test_{i}", "performance")

            # Update timestamp to old time
            check_run = session.get(CheckRun, check_run_id)
            check_run.timestamp = old_time
            session.commit()

        # Measure cleanup time
        start_time = time.time()
        deleted_count = storage_service.cleanup_old_data(days_to_keep=30, batch_size=20)
        end_time = time.time()

        # Verify all records were deleted
        assert deleted_count == num_records

        # Performance should be reasonable (less than 2 seconds for 50 records)
        cleanup_time = end_time - start_time
        assert cleanup_time < 2.0, f"Cleanup took {cleanup_time:.2f} seconds, expected < 2.0"

    def test_archive_performance_with_relationships(self, storage_service, session):
        """Test archive performance when handling related data."""
        import time

        base_time = datetime.now(UTC)
        old_time = base_time - timedelta(days=60)

        # Create check runs with posts and comments
        num_check_runs = 20
        for i in range(num_check_runs):
            check_run_id = storage_service.create_check_run(f"perf_archive_{i}", "performance")

            # Update timestamp to old time
            check_run = session.get(CheckRun, check_run_id)
            check_run.timestamp = old_time
            session.commit()

            # Create posts for each check run
            for j in range(3):  # 3 posts per check run
                post_data = {
                    'post_id': f'perf_post_{i}_{j}',
                    'subreddit': f'perf_archive_{i}',
                    'title': f'Performance Post {i}-{j}',
                    'author': 'perf_user',
                    'selftext': 'Performance test content',
                    'score': 10,
                    'num_comments': 1,
                    'url': f'https://reddit.com/perf_{i}_{j}',
                    'permalink': f'/r/perf_archive_{i}/post_{j}',
                    'is_self': True,
                    'over_18': False,
                    'created_utc': old_time,
                    'check_run_id': check_run_id
                }
                post_id = storage_service.save_post(post_data)

                # Add a comment to each post
                comment_data = {
                    'comment_id': f'perf_comment_{i}_{j}',
                    'author': 'perf_commenter',
                    'body': f'Performance comment {i}-{j}',
                    'score': 2,
                    'created_utc': old_time,
                    'parent_id': None,
                    'is_submitter': False,
                    'stickied': False,
                    'distinguished': None
                }
                storage_service.save_comment(comment_data, post_id)

        # Verify data was created
        assert session.query(CheckRun).count() == num_check_runs
        assert session.query(RedditPost).count() == num_check_runs * 3
        assert session.query(Comment).count() == num_check_runs * 3

        # Measure archive time
        start_time = time.time()
        archived_count = storage_service.archive_old_check_runs(days_to_keep=30, batch_size=10)
        end_time = time.time()

        # Verify archiving worked
        assert archived_count == num_check_runs
        assert session.query(CheckRun).count() == num_check_runs  # Check runs preserved
        assert session.query(RedditPost).count() == 0  # Posts deleted
        assert session.query(Comment).count() == 0  # Comments deleted (cascaded)

        # Performance should be reasonable
        archive_time = end_time - start_time
        assert archive_time < 3.0, f"Archive took {archive_time:.2f} seconds, expected < 3.0"

    def test_statistics_performance_large_dataset(self, storage_service, session):
        """Test that statistics gathering is efficient on large datasets."""
        import time

        # Create a moderate amount of data
        base_time = datetime.now(UTC)
        for i in range(30):
            timestamp = base_time - timedelta(days=i)
            check_run_id = storage_service.create_check_run(f"stats_test_{i}", "statistics")

            # Update timestamp to old time
            check_run = session.get(CheckRun, check_run_id)
            check_run.timestamp = timestamp
            session.commit()

        # Measure statistics gathering time
        start_time = time.time()
        stats = storage_service.get_storage_statistics(
            include_date_breakdown=True,
            include_size_estimation=True,
            retention_days=30
        )
        end_time = time.time()

        # Verify statistics are complete
        assert stats['check_runs'] == 30
        assert 'date_breakdown' in stats
        assert 'estimated_size' in stats
        assert 'retention_analysis' in stats

        # Performance should be reasonable (less than 1 second)
        stats_time = end_time - start_time
        assert stats_time < 1.0, f"Statistics took {stats_time:.2f} seconds, expected < 1.0"
