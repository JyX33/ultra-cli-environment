# ABOUTME: Tests for ChangeDetectionService functionality - new post detection and change tracking
# ABOUTME: Comprehensive test suite covering post comparisons, delta calculations, and edge cases

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.reddit_post import RedditPost
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
def change_detection_service(session, storage_service):
    """Create a ChangeDetectionService instance with test session."""
    return ChangeDetectionService(session, storage_service)


@pytest.fixture
def sample_current_posts():
    """Sample current posts from Reddit API."""
    base_time = datetime.now(UTC)
    return [
        {
            'post_id': 'new_post_1',
            'subreddit': 'python',
            'title': 'New Python Feature Released',
            'author': 'python_dev',
            'selftext': 'Check out this new feature',
            'score': 50,
            'num_comments': 5,
            'url': 'https://reddit.com/new1',
            'permalink': '/r/python/new1',
            'is_self': True,
            'over_18': False,
            'created_utc': base_time - timedelta(hours=2),
        },
        {
            'post_id': 'existing_post_1',
            'subreddit': 'python',
            'title': 'Existing Post with Changes',
            'author': 'python_user',
            'selftext': 'This post has been around',
            'score': 150,  # Changed from 100
            'num_comments': 25,  # Changed from 20
            'url': 'https://reddit.com/existing1',
            'permalink': '/r/python/existing1',
            'is_self': True,
            'over_18': False,
            'created_utc': base_time - timedelta(hours=6),
        },
        {
            'post_id': 'existing_post_2',
            'subreddit': 'python',
            'title': 'Existing Post No Changes',
            'author': 'python_author',
            'selftext': 'This post is unchanged',
            'score': 75,  # Same as before
            'num_comments': 10,  # Same as before
            'url': 'https://reddit.com/existing2',
            'permalink': '/r/python/existing2',
            'is_self': True,
            'over_18': False,
            'created_utc': base_time - timedelta(hours=8),
        }
    ]


@pytest.fixture
def existing_stored_posts(storage_service):
    """Create existing posts in the database for comparison."""
    base_time = datetime.now(UTC)

    # Create a check run
    check_run_id = storage_service.create_check_run('python', 'testing')

    # Create existing posts in database
    existing_posts_data = [
        {
            'post_id': 'existing_post_1',
            'subreddit': 'python',
            'title': 'Existing Post with Changes',
            'author': 'python_user',
            'selftext': 'This post has been around',
            'score': 100,  # Will change to 150
            'num_comments': 20,  # Will change to 25
            'url': 'https://reddit.com/existing1',
            'permalink': '/r/python/existing1',
            'is_self': True,
            'over_18': False,
            'created_utc': base_time - timedelta(hours=6),
            'check_run_id': check_run_id
        },
        {
            'post_id': 'existing_post_2',
            'subreddit': 'python',
            'title': 'Existing Post No Changes',
            'author': 'python_author',
            'selftext': 'This post is unchanged',
            'score': 75,  # Same
            'num_comments': 10,  # Same
            'url': 'https://reddit.com/existing2',
            'permalink': '/r/python/existing2',
            'is_self': True,
            'over_18': False,
            'created_utc': base_time - timedelta(hours=8),
            'check_run_id': check_run_id
        }
    ]

    stored_posts = []
    for post_data in existing_posts_data:
        post_id = storage_service.save_post(post_data)
        stored_posts.append(storage_service.session.get(RedditPost, post_id))

    return stored_posts, check_run_id


class TestChangeDetectionServiceNewPosts:
    """Test new post detection functionality."""

    def test_find_new_posts_basic(self, change_detection_service, existing_stored_posts, sample_current_posts):
        """Test basic new post identification."""
        stored_posts, check_run_id = existing_stored_posts
        last_check_time = datetime.now(UTC) - timedelta(hours=4)

        new_posts = change_detection_service.find_new_posts(sample_current_posts, last_check_time)

        # Should find 1 new post (new_post_1)
        assert len(new_posts) == 1
        assert new_posts[0].reddit_post_id == 'new_post_1'
        assert new_posts[0].is_new_post
        assert new_posts[0].update_type == 'new'
        assert new_posts[0].current_score == 50
        assert new_posts[0].current_comments == 5

    def test_find_new_posts_empty_database(self, change_detection_service, sample_current_posts):
        """Test finding new posts when database is empty."""
        # Set last check time to very old, so all posts should be considered new
        last_check_time = datetime.now(UTC) - timedelta(hours=10)

        new_posts = change_detection_service.find_new_posts(sample_current_posts, last_check_time)

        # All posts should be considered new since database is empty and all posts are newer than last check
        assert len(new_posts) == 3
        for post in new_posts:
            assert post.is_new_post
            assert post.update_type == 'new'

    def test_find_new_posts_no_new_posts(self, change_detection_service, existing_stored_posts):
        """Test when there are no new posts."""
        stored_posts, check_run_id = existing_stored_posts
        last_check_time = datetime.now(UTC) - timedelta(hours=1)

        # Only provide existing posts
        current_posts = [
            {
                'post_id': 'existing_post_1',
                'subreddit': 'python',
                'title': 'Existing Post',
                'author': 'user',
                'score': 100,
                'num_comments': 20,
                'url': 'https://reddit.com/existing1',
                'permalink': '/r/python/existing1',
                'is_self': True,
                'over_18': False,
                'created_utc': datetime.now(UTC) - timedelta(hours=6),
            }
        ]

        new_posts = change_detection_service.find_new_posts(current_posts, last_check_time)

        assert len(new_posts) == 0

    def test_find_new_posts_with_time_filter(self, change_detection_service, existing_stored_posts, sample_current_posts):
        """Test new post detection with time filtering."""
        stored_posts, check_run_id = existing_stored_posts

        # Set last check time to 1 hour ago (after new_post_1 was created 2 hours ago)
        last_check_time = datetime.now(UTC) - timedelta(hours=1)

        new_posts = change_detection_service.find_new_posts(sample_current_posts, last_check_time)

        # new_post_1 was created 2 hours ago, before last check time, so shouldn't be "new"
        assert len(new_posts) == 0

    def test_find_new_posts_handles_missing_fields(self, change_detection_service):
        """Test new post detection with missing optional fields."""
        current_posts = [
            {
                'post_id': 'minimal_post',
                'subreddit': 'python',
                'title': 'Minimal Post',
                'author': None,  # Missing author
                'url': 'https://reddit.com/minimal',
                'permalink': '/r/python/minimal',
                'is_self': True,
                'over_18': False,
                'created_utc': datetime.now(UTC) - timedelta(minutes=30),
                # Missing score, num_comments, selftext
            }
        ]

        last_check_time = datetime.now(UTC) - timedelta(hours=1)

        new_posts = change_detection_service.find_new_posts(current_posts, last_check_time)

        assert len(new_posts) == 1
        assert new_posts[0].reddit_post_id == 'minimal_post'
        assert new_posts[0].current_score == 0  # Default value
        assert new_posts[0].current_comments == 0  # Default value


class TestChangeDetectionServiceUpdatedPosts:
    """Test updated post detection functionality."""

    def test_find_updated_posts_basic(self, change_detection_service, existing_stored_posts, sample_current_posts):
        """Test basic updated post identification."""
        stored_posts, check_run_id = existing_stored_posts

        updated_posts = change_detection_service.find_updated_posts(sample_current_posts)

        # Should find 1 updated post (existing_post_1 with score/comment changes)
        assert len(updated_posts) == 1

        updated_post = updated_posts[0]
        assert updated_post.reddit_post_id == 'existing_post_1'
        assert updated_post.has_engagement_change
        assert updated_post.update_type == 'both_change'
        assert updated_post.score_delta == 50  # 150 - 100
        assert updated_post.comments_delta == 5  # 25 - 20

    def test_find_updated_posts_score_only_change(self, change_detection_service, existing_stored_posts):
        """Test detection when only score changes."""
        stored_posts, check_run_id = existing_stored_posts

        current_posts = [
            {
                'post_id': 'existing_post_1',
                'subreddit': 'python',
                'title': 'Existing Post with Changes',
                'author': 'python_user',
                'selftext': 'This post has been around',
                'score': 120,  # Changed from 100
                'num_comments': 20,  # Same
                'url': 'https://reddit.com/existing1',
                'permalink': '/r/python/existing1',
                'is_self': True,
                'over_18': False,
                'created_utc': datetime.now(UTC) - timedelta(hours=6),
            }
        ]

        updated_posts = change_detection_service.find_updated_posts(current_posts)

        assert len(updated_posts) == 1
        assert updated_posts[0].update_type == 'score_change'
        assert updated_posts[0].score_delta == 20
        assert updated_posts[0].comments_delta == 0

    def test_find_updated_posts_comments_only_change(self, change_detection_service, existing_stored_posts):
        """Test detection when only comment count changes."""
        stored_posts, check_run_id = existing_stored_posts

        current_posts = [
            {
                'post_id': 'existing_post_1',
                'subreddit': 'python',
                'title': 'Existing Post with Changes',
                'author': 'python_user',
                'selftext': 'This post has been around',
                'score': 100,  # Same
                'num_comments': 30,  # Changed from 20
                'url': 'https://reddit.com/existing1',
                'permalink': '/r/python/existing1',
                'is_self': True,
                'over_18': False,
                'created_utc': datetime.now(UTC) - timedelta(hours=6),
            }
        ]

        updated_posts = change_detection_service.find_updated_posts(current_posts)

        assert len(updated_posts) == 1
        assert updated_posts[0].update_type == 'comment_change'
        assert updated_posts[0].score_delta == 0
        assert updated_posts[0].comments_delta == 10

    def test_find_updated_posts_no_changes(self, change_detection_service, existing_stored_posts):
        """Test when posts have no changes."""
        stored_posts, check_run_id = existing_stored_posts

        # Provide current posts with same values as stored
        current_posts = [
            {
                'post_id': 'existing_post_1',
                'subreddit': 'python',
                'title': 'Existing Post with Changes',
                'author': 'python_user',
                'selftext': 'This post has been around',
                'score': 100,  # Same as stored
                'num_comments': 20,  # Same as stored
                'url': 'https://reddit.com/existing1',
                'permalink': '/r/python/existing1',
                'is_self': True,
                'over_18': False,
                'created_utc': datetime.now(UTC) - timedelta(hours=6),
            }
        ]

        updated_posts = change_detection_service.find_updated_posts(current_posts)

        assert len(updated_posts) == 0

    def test_find_updated_posts_post_not_in_database(self, change_detection_service, existing_stored_posts):
        """Test updated post detection for posts not in database."""
        stored_posts, check_run_id = existing_stored_posts

        current_posts = [
            {
                'post_id': 'unknown_post',
                'subreddit': 'python',
                'title': 'Unknown Post',
                'author': 'user',
                'score': 50,
                'num_comments': 5,
                'url': 'https://reddit.com/unknown',
                'permalink': '/r/python/unknown',
                'is_self': True,
                'over_18': False,
                'created_utc': datetime.now(UTC) - timedelta(hours=2),
            }
        ]

        updated_posts = change_detection_service.find_updated_posts(current_posts)

        # Post not in database, so no updates detected
        assert len(updated_posts) == 0


class TestChangeDetectionServiceEngagementDelta:
    """Test engagement delta calculation functionality."""

    def test_calculate_engagement_delta_basic(self, change_detection_service, existing_stored_posts):
        """Test basic engagement delta calculation."""
        stored_posts, check_run_id = existing_stored_posts
        stored_post = stored_posts[0]  # existing_post_1

        # Calculate delta with new values
        delta = change_detection_service.calculate_engagement_delta(
            stored_post.post_id,
            current_score=150,
            current_comments=25,
            current_timestamp=datetime.now(UTC)
        )

        assert delta is not None
        assert delta.post_id == stored_post.post_id
        assert delta.score_delta == 50  # 150 - 100
        assert delta.comments_delta == 5  # 25 - 20
        assert delta.previous_score == 100
        assert delta.current_score == 150
        assert delta.previous_comments == 20
        assert delta.current_comments == 25
        assert delta.time_span_hours > 0
        assert delta.engagement_rate > 0  # Positive score change

    def test_calculate_engagement_delta_trending_up(self, change_detection_service, existing_stored_posts):
        """Test delta calculation for trending up posts."""
        stored_posts, check_run_id = existing_stored_posts
        stored_post = stored_posts[0]

        delta = change_detection_service.calculate_engagement_delta(
            stored_post.post_id,
            current_score=200,
            current_comments=30,
            current_timestamp=datetime.now(UTC)
        )

        assert delta.is_trending_up
        assert not delta.is_trending_down
        assert delta.has_significant_change  # Score delta >= 10

    def test_calculate_engagement_delta_trending_down(self, change_detection_service, existing_stored_posts):
        """Test delta calculation for trending down posts."""
        stored_posts, check_run_id = existing_stored_posts
        stored_post = stored_posts[0]

        delta = change_detection_service.calculate_engagement_delta(
            stored_post.post_id,
            current_score=80,
            current_comments=15,
            current_timestamp=datetime.now(UTC)
        )

        assert not delta.is_trending_up
        assert delta.is_trending_down
        assert delta.score_delta == -20  # 80 - 100
        assert delta.comments_delta == -5  # 15 - 20

    def test_calculate_engagement_delta_no_previous_data(self, change_detection_service):
        """Test delta calculation for posts with no previous data."""
        delta = change_detection_service.calculate_engagement_delta(
            'nonexistent_post',
            current_score=50,
            current_comments=5,
            current_timestamp=datetime.now(UTC)
        )

        # Should return None when no previous data exists
        assert delta is None

    def test_calculate_engagement_delta_zero_time_span(self, change_detection_service, existing_stored_posts):
        """Test delta calculation with very short time span."""
        stored_posts, check_run_id = existing_stored_posts
        stored_post = stored_posts[0]

        # Use the same timestamp as last_updated
        delta = change_detection_service.calculate_engagement_delta(
            stored_post.post_id,
            current_score=110,
            current_comments=22,
            current_timestamp=stored_post.last_updated
        )

        assert delta is not None
        # Should handle zero/minimal time span gracefully
        assert delta.time_span_hours >= 0
        # Engagement rate might be very high or infinite, but shouldn't crash


class TestChangeDetectionServiceCompareFunction:
    """Test the _compare_posts private function."""

    def test_compare_posts_basic_changes(self, change_detection_service):
        """Test basic post comparison functionality."""
        old_post_data = {
            'score': 100,
            'num_comments': 20
        }

        new_post_data = {
            'score': 150,
            'num_comments': 25
        }

        result = change_detection_service._compare_posts(old_post_data, new_post_data)

        assert result['has_changes']
        assert result['score_changed']
        assert result['comments_changed']
        assert result['score_delta'] == 50
        assert result['comments_delta'] == 5

    def test_compare_posts_no_changes(self, change_detection_service):
        """Test post comparison with no changes."""
        post_data = {
            'score': 100,
            'num_comments': 20
        }

        result = change_detection_service._compare_posts(post_data, post_data)

        assert not result['has_changes']
        assert not result['score_changed']
        assert not result['comments_changed']
        assert result['score_delta'] == 0
        assert result['comments_delta'] == 0

    def test_compare_posts_missing_fields(self, change_detection_service):
        """Test post comparison with missing fields."""
        old_post_data = {
            'score': 100,
            'num_comments': 20
        }

        new_post_data = {
            'score': 150,
            # Missing num_comments
        }

        result = change_detection_service._compare_posts(old_post_data, new_post_data)

        assert result['has_changes']
        assert result['score_changed']
        assert result['comments_changed']  # 20 -> 0 (default)
        assert result['score_delta'] == 50
        assert result['comments_delta'] == -20


class TestChangeDetectionServicePerformance:
    """Test performance aspects of change detection."""

    def test_find_new_posts_performance_many_posts(self, change_detection_service, storage_service):
        """Test performance with many current posts."""
        import time

        # Create many current posts
        base_time = datetime.now(UTC)
        current_posts = []

        for i in range(100):
            current_posts.append({
                'post_id': f'perf_post_{i}',
                'subreddit': 'python',
                'title': f'Performance Post {i}',
                'author': f'user_{i}',
                'selftext': f'Content for post {i}',
                'score': i * 10,
                'num_comments': i * 2,
                'url': f'https://reddit.com/perf_{i}',
                'permalink': f'/r/python/perf_{i}',
                'is_self': True,
                'over_18': False,
                'created_utc': base_time - timedelta(minutes=i),
            })

        last_check_time = base_time - timedelta(hours=2)

        # Measure performance
        start_time = time.time()
        new_posts = change_detection_service.find_new_posts(current_posts, last_check_time)
        end_time = time.time()

        # All should be new posts
        assert len(new_posts) == 100

        # Should complete in reasonable time (less than 1 second)
        duration = end_time - start_time
        assert duration < 1.0, f"New post detection took {duration:.2f} seconds, expected < 1.0"

    def test_find_updated_posts_performance_large_dataset(self, change_detection_service, storage_service):
        """Test performance of update detection with large dataset."""
        import time

        # Create check run and many stored posts
        check_run_id = storage_service.create_check_run('python', 'performance_test')
        base_time = datetime.now(UTC)

        # Create 50 stored posts
        for i in range(50):
            post_data = {
                'post_id': f'perf_stored_{i}',
                'subreddit': 'python',
                'title': f'Stored Post {i}',
                'author': f'stored_user_{i}',
                'selftext': f'Stored content {i}',
                'score': i * 10,
                'num_comments': i * 2,
                'url': f'https://reddit.com/stored_{i}',
                'permalink': f'/r/python/stored_{i}',
                'is_self': True,
                'over_18': False,
                'created_utc': base_time - timedelta(hours=i),
                'check_run_id': check_run_id
            }
            storage_service.save_post(post_data)

        # Create current posts with some changes
        current_posts = []
        for i in range(50):
            current_posts.append({
                'post_id': f'perf_stored_{i}',
                'subreddit': 'python',
                'title': f'Stored Post {i}',
                'author': f'stored_user_{i}',
                'selftext': f'Stored content {i}',
                'score': (i * 10) + (i % 10),  # Slight score changes
                'num_comments': (i * 2) + (i % 5),  # Slight comment changes
                'url': f'https://reddit.com/stored_{i}',
                'permalink': f'/r/python/stored_{i}',
                'is_self': True,
                'over_18': False,
                'created_utc': base_time - timedelta(hours=i),
            })

        # Measure performance
        start_time = time.time()
        updated_posts = change_detection_service.find_updated_posts(current_posts)
        end_time = time.time()

        # Should find some updates
        assert len(updated_posts) > 0

        # Should complete in reasonable time (less than 2 seconds)
        duration = end_time - start_time
        assert duration < 2.0, f"Update detection took {duration:.2f} seconds, expected < 2.0"


class TestChangeDetectionServiceEdgeCases:
    """Test edge cases and error conditions."""

    def test_handle_database_error_in_new_posts(self, change_detection_service):
        """Test handling of database errors during new post detection."""
        # Mock the storage service to raise an error
        change_detection_service.storage_service.get_post_by_id = Mock(side_effect=SQLAlchemyError("Database error"))

        current_posts = [{'post_id': 'test_post', 'subreddit': 'test', 'created_utc': datetime.now(UTC) - timedelta(minutes=30)}]
        last_check_time = datetime.now(UTC) - timedelta(hours=1)

        # Should handle error gracefully and return empty list
        new_posts = change_detection_service.find_new_posts(current_posts, last_check_time)
        assert len(new_posts) == 0

    def test_handle_database_error_in_updated_posts(self, change_detection_service):
        """Test handling of database errors during updated post detection."""
        # Mock the storage service to raise an error
        change_detection_service.storage_service.get_post_by_id = Mock(side_effect=SQLAlchemyError("Database error"))

        current_posts = [{'post_id': 'test_post', 'subreddit': 'test', 'score': 100, 'num_comments': 10}]

        # Should handle error gracefully and return empty list
        updated_posts = change_detection_service.find_updated_posts(current_posts)
        assert len(updated_posts) == 0

    def test_handle_malformed_current_posts(self, change_detection_service):
        """Test handling of malformed current post data."""
        # Missing required fields
        malformed_posts = [
            {'post_id': 'incomplete_post'},  # Missing many required fields
            {'subreddit': 'test'},  # Missing post_id
            {}  # Empty dict
        ]

        last_check_time = datetime.now(UTC) - timedelta(hours=1)

        # Should handle malformed data gracefully
        new_posts = change_detection_service.find_new_posts(malformed_posts, last_check_time)

        # May return some posts with default values, but shouldn't crash
        assert isinstance(new_posts, list)

    def test_empty_current_posts_list(self, change_detection_service):
        """Test behavior with empty current posts list."""
        last_check_time = datetime.now(UTC) - timedelta(hours=1)

        new_posts = change_detection_service.find_new_posts([], last_check_time)
        updated_posts = change_detection_service.find_updated_posts([])

        assert len(new_posts) == 0
        assert len(updated_posts) == 0


class TestChangeDetectionResult:
    """Test ChangeDetectionResult dataclass functionality."""

    def test_change_detection_result_creation(self):
        """Test creation of ChangeDetectionResult from updates."""
        base_time = datetime.now(UTC)

        # Create sample updates
        new_posts = [
            PostUpdate(
                post_id=1,
                reddit_post_id='new_1',
                subreddit='python',
                title='New Post',
                update_type='new',
                current_score=50,
                current_comments=5,
                current_timestamp=base_time
            )
        ]

        updated_posts = [
            PostUpdate(
                post_id=2,
                reddit_post_id='updated_1',
                subreddit='python',
                title='Updated Post',
                update_type='both_change',
                current_score=150,
                current_comments=25,
                current_timestamp=base_time,
                previous_score=100,
                previous_comments=20,
                engagement_delta=EngagementDelta(
                    post_id='updated_1',
                    score_delta=50,
                    comments_delta=5,
                    previous_score=100,
                    current_score=150,
                    previous_comments=20,
                    current_comments=25,
                    time_span_hours=2.0,
                    engagement_rate=25.0
                )
            )
        ]

        result = ChangeDetectionResult.from_updates(
            check_run_id=1,
            subreddit='python',
            new_posts=new_posts,
            updated_posts=updated_posts
        )

        assert result.total_new_posts == 1
        assert result.total_updated_posts == 1
        assert result.posts_with_significant_changes == 1  # Delta >= 10
        assert result.trending_up_posts == 1
        assert result.trending_down_posts == 0
        assert result.subreddit == 'python'
        assert result.check_run_id == 1
