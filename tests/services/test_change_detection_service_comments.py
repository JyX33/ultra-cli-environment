# ABOUTME: Tests for ChangeDetectionService comment analysis functionality
# ABOUTME: Comprehensive test suite covering comment change detection, tree traversal, and metrics

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.comment import Comment
from app.models.reddit_post import RedditPost
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
def sample_post_with_comments(storage_service):
    """Create a test post with stored comments for comparison."""
    base_time = datetime.now(UTC)

    # Create check run
    check_run_id = storage_service.create_check_run('python', 'comment_testing')

    # Create a post
    post_data = {
        'post_id': 'test_post_123',
        'subreddit': 'python',
        'title': 'Test Post for Comments',
        'author': 'post_author',
        'selftext': 'This is a test post',
        'score': 100,
        'num_comments': 5,
        'url': 'https://reddit.com/test_post',
        'permalink': '/r/python/comments/test_post/test_post/',
        'is_self': True,
        'over_18': False,
        'created_utc': base_time - timedelta(hours=2),
        'check_run_id': check_run_id
    }

    post_db_id = storage_service.save_post(post_data)
    stored_post = storage_service.session.get(RedditPost, post_db_id)

    # Create stored comments
    stored_comments = []
    comment_data_list = [
        {
            'comment_id': 'comment_1',
            'post_id': post_db_id,
            'author': 'commenter_1',
            'body': 'This is the first comment',
            'score': 10,
            'created_utc': base_time - timedelta(hours=1, minutes=30),
            'parent_id': 'test_post_123',  # Top-level comment
            'is_submitter': False,
            'stickied': False
        },
        {
            'comment_id': 'comment_2',
            'post_id': post_db_id,
            'author': 'commenter_2',
            'body': 'This is a reply to comment 1',
            'score': 5,
            'created_utc': base_time - timedelta(hours=1, minutes=20),
            'parent_id': 'comment_1',  # Reply to comment_1
            'is_submitter': False,
            'stickied': False
        },
        {
            'comment_id': 'comment_3',
            'post_id': post_db_id,
            'author': 'commenter_3',
            'body': 'Another top-level comment',
            'score': 8,
            'created_utc': base_time - timedelta(hours=1, minutes=10),
            'parent_id': 'test_post_123',  # Top-level comment
            'is_submitter': False,
            'stickied': False
        }
    ]

    for comment_data in comment_data_list:
        storage_service.save_comment(comment_data, post_db_id)
        stored_comment = storage_service.session.query(Comment).filter_by(
            comment_id=comment_data['comment_id']
        ).first()
        stored_comments.append(stored_comment)

    return stored_post, stored_comments, check_run_id


@pytest.fixture
def sample_current_comments():
    """Sample current comments from Reddit API."""
    base_time = datetime.now(UTC)
    return [
        {
            'comment_id': 'comment_1',
            'author': 'commenter_1',
            'body': 'This is the first comment',
            'score': 15,  # Changed from 10
            'created_utc': base_time - timedelta(hours=1, minutes=30),
            'parent_id': 'test_post_123',
            'is_submitter': False,
            'stickied': False
        },
        {
            'comment_id': 'comment_2',
            'author': 'commenter_2',
            'body': 'This is a reply to comment 1',
            'score': 5,  # Same
            'created_utc': base_time - timedelta(hours=1, minutes=20),
            'parent_id': 'comment_1',
            'is_submitter': False,
            'stickied': False
        },
        {
            'comment_id': 'comment_3',
            'author': 'commenter_3',
            'body': 'Another top-level comment',
            'score': 12,  # Changed from 8
            'created_utc': base_time - timedelta(hours=1, minutes=10),
            'parent_id': 'test_post_123',
            'is_submitter': False,
            'stickied': False
        },
        {
            'comment_id': 'comment_4',  # New comment
            'author': 'commenter_4',
            'body': 'This is a new comment',
            'score': 3,
            'created_utc': base_time - timedelta(minutes=30),
            'parent_id': 'test_post_123',
            'is_submitter': False,
            'stickied': False
        },
        {
            'comment_id': 'comment_5',  # New reply
            'author': 'commenter_5',
            'body': 'Reply to new comment',
            'score': 1,
            'created_utc': base_time - timedelta(minutes=20),
            'parent_id': 'comment_4',
            'is_submitter': False,
            'stickied': False
        }
    ]


class TestChangeDetectionServiceFindNewComments:
    """Test new comment detection functionality."""

    def test_find_new_comments_basic(self, change_detection_service, sample_post_with_comments, sample_current_comments):
        """Test basic new comment identification."""
        stored_post, stored_comments, check_run_id = sample_post_with_comments

        new_comments = change_detection_service.find_new_comments(
            stored_post.id,  # Use database ID, not Reddit post_id
            sample_current_comments
        )

        # Should find 2 new comments (comment_4 and comment_5)
        assert len(new_comments) == 2
        new_comment_ids = [comment['comment_id'] for comment in new_comments]
        assert 'comment_4' in new_comment_ids
        assert 'comment_5' in new_comment_ids

    def test_find_new_comments_empty_current(self, change_detection_service, sample_post_with_comments):
        """Test new comment detection with empty current comments."""
        stored_post, stored_comments, check_run_id = sample_post_with_comments

        new_comments = change_detection_service.find_new_comments(
            stored_post.id,
            []
        )

        assert len(new_comments) == 0

    def test_find_new_comments_no_stored_comments(self, change_detection_service, storage_service, sample_current_comments):
        """Test new comment detection when no comments are stored."""
        # Create a post without comments
        check_run_id = storage_service.create_check_run('python', 'no_comments_test')
        post_data = {
            'post_id': 'empty_post',
            'subreddit': 'python',
            'title': 'Post with no stored comments',
            'author': 'author',
            'score': 50,
            'num_comments': 0,
            'url': 'https://reddit.com/empty',
            'permalink': '/r/python/comments/empty/test_post/',
            'is_self': True,
            'over_18': False,
            'created_utc': datetime.now(UTC) - timedelta(hours=2),
            'check_run_id': check_run_id
        }

        post_db_id = storage_service.save_post(post_data)

        new_comments = change_detection_service.find_new_comments(
            post_db_id,
            sample_current_comments
        )

        # All current comments should be considered new
        assert len(new_comments) == len(sample_current_comments)

    def test_find_new_comments_nonexistent_post(self, change_detection_service, sample_current_comments):
        """Test new comment detection for nonexistent post."""
        new_comments = change_detection_service.find_new_comments(
            999999,  # Non-existent post ID
            sample_current_comments
        )

        # Should return empty list for nonexistent post
        assert len(new_comments) == 0

    def test_find_new_comments_handles_deleted_authors(self, change_detection_service, sample_post_with_comments):
        """Test new comment detection with deleted authors."""
        stored_post, stored_comments, check_run_id = sample_post_with_comments

        current_comments_with_deleted = [
            {
                'comment_id': 'deleted_comment',
                'author': None,  # Deleted author
                'body': '[deleted]',
                'score': 0,
                'created_utc': datetime.now(UTC) - timedelta(minutes=30),
                'parent_id': 'test_post_123',
                'is_submitter': False,
                'stickied': False
            }
        ]

        new_comments = change_detection_service.find_new_comments(
            stored_post.id,
            current_comments_with_deleted
        )

        assert len(new_comments) == 1
        assert new_comments[0]['author'] is None
        assert new_comments[0]['comment_id'] == 'deleted_comment'


class TestChangeDetectionServiceFindUpdatedComments:
    """Test updated comment detection functionality."""

    def test_find_updated_comments_basic(self, change_detection_service, sample_post_with_comments, sample_current_comments):
        """Test basic updated comment identification."""
        stored_post, stored_comments, check_run_id = sample_post_with_comments

        updated_comments = change_detection_service.find_updated_comments(
            stored_post.id,
            sample_current_comments
        )

        # Should find 2 updated comments (comment_1: 10->15, comment_3: 8->12)
        assert len(updated_comments) == 2

        updated_comment_ids = [comment['comment_id'] for comment in updated_comments]
        assert 'comment_1' in updated_comment_ids
        assert 'comment_3' in updated_comment_ids

        # Check score changes
        for comment in updated_comments:
            if comment['comment_id'] == 'comment_1':
                assert comment['score_delta'] == 5  # 15 - 10
            elif comment['comment_id'] == 'comment_3':
                assert comment['score_delta'] == 4  # 12 - 8

    def test_find_updated_comments_no_changes(self, change_detection_service, sample_post_with_comments):
        """Test updated comment detection when no changes exist."""
        stored_post, stored_comments, check_run_id = sample_post_with_comments

        # Use current comments with same scores as stored
        unchanged_comments = [
            {
                'comment_id': 'comment_1',
                'author': 'commenter_1',
                'body': 'This is the first comment',
                'score': 10,  # Same as stored
                'created_utc': datetime.now(UTC) - timedelta(hours=1, minutes=30),
                'parent_id': 'test_post_123',
                'is_submitter': False,
                'stickied': False
            }
        ]

        updated_comments = change_detection_service.find_updated_comments(
            stored_post.id,
            unchanged_comments
        )

        assert len(updated_comments) == 0

    def test_find_updated_comments_score_decrease(self, change_detection_service, sample_post_with_comments):
        """Test detection of comment score decreases."""
        stored_post, stored_comments, check_run_id = sample_post_with_comments

        decreased_comments = [
            {
                'comment_id': 'comment_1',
                'author': 'commenter_1',
                'body': 'This is the first comment',
                'score': 5,  # Decreased from 10
                'created_utc': datetime.now(UTC) - timedelta(hours=1, minutes=30),
                'parent_id': 'test_post_123',
                'is_submitter': False,
                'stickied': False
            }
        ]

        updated_comments = change_detection_service.find_updated_comments(
            stored_post.id,
            decreased_comments
        )

        assert len(updated_comments) == 1
        assert updated_comments[0]['score_delta'] == -5  # 5 - 10

    def test_find_updated_comments_missing_from_current(self, change_detection_service, sample_post_with_comments):
        """Test handling of comments missing from current data (potentially deleted)."""
        stored_post, stored_comments, check_run_id = sample_post_with_comments

        # Only provide one comment, missing the others
        partial_comments = [
            {
                'comment_id': 'comment_1',
                'author': 'commenter_1',
                'body': 'This is the first comment',
                'score': 10,
                'created_utc': datetime.now(UTC) - timedelta(hours=1, minutes=30),
                'parent_id': 'test_post_123',
                'is_submitter': False,
                'stickied': False
            }
        ]

        updated_comments = change_detection_service.find_updated_comments(
            stored_post.id,
            partial_comments
        )

        # Should only process the comment that exists in current data
        assert len(updated_comments) == 0  # No score changes for comment_1


class TestChangeDetectionServiceCommentTreeChanges:
    """Test comment tree change detection functionality."""

    def test_get_comment_tree_changes_basic(self, change_detection_service, sample_post_with_comments, sample_current_comments):
        """Test basic comment tree change detection."""
        stored_post, stored_comments, check_run_id = sample_post_with_comments

        tree_changes = change_detection_service.get_comment_tree_changes(
            stored_post.id
        )

        # Should include information about comment structure
        assert 'post_id' in tree_changes
        assert 'total_stored_comments' in tree_changes
        assert 'comment_hierarchy' in tree_changes
        assert tree_changes['post_id'] == stored_post.id
        assert tree_changes['total_stored_comments'] == 3

    def test_get_comment_tree_changes_hierarchy(self, change_detection_service, sample_post_with_comments):
        """Test comment tree hierarchy analysis."""
        stored_post, stored_comments, check_run_id = sample_post_with_comments

        tree_changes = change_detection_service.get_comment_tree_changes(
            stored_post.id
        )

        hierarchy = tree_changes['comment_hierarchy']

        # Should have top-level comments and replies structure
        assert 'top_level_count' in hierarchy
        assert 'max_depth' in hierarchy
        assert 'total_replies' in hierarchy

        # We have 2 top-level comments (comment_1, comment_3) and 1 reply (comment_2)
        assert hierarchy['top_level_count'] == 2
        assert hierarchy['total_replies'] == 1
        assert hierarchy['max_depth'] == 3  # Post (1) -> Comment (2) -> Reply (3)

    def test_get_comment_tree_changes_empty_post(self, change_detection_service, storage_service):
        """Test comment tree analysis for post with no comments."""
        # Create a post without comments
        check_run_id = storage_service.create_check_run('python', 'empty_tree_test')
        post_data = {
            'post_id': 'empty_tree_post',
            'subreddit': 'python',
            'title': 'Post with no comments',
            'author': 'author',
            'score': 50,
            'num_comments': 0,
            'url': 'https://reddit.com/empty_tree',
            'permalink': '/r/python/comments/empty_tree/test_post/',
            'is_self': True,
            'over_18': False,
            'created_utc': datetime.now(UTC) - timedelta(hours=2),
            'check_run_id': check_run_id
        }

        post_db_id = storage_service.save_post(post_data)

        tree_changes = change_detection_service.get_comment_tree_changes(post_db_id)

        assert tree_changes['total_stored_comments'] == 0
        assert tree_changes['comment_hierarchy']['top_level_count'] == 0
        assert tree_changes['comment_hierarchy']['total_replies'] == 0
        assert tree_changes['comment_hierarchy']['max_depth'] == 0

    def test_get_comment_tree_changes_nonexistent_post(self, change_detection_service):
        """Test comment tree analysis for nonexistent post."""
        tree_changes = change_detection_service.get_comment_tree_changes(999999)

        # Should return empty structure for nonexistent post
        assert tree_changes['total_stored_comments'] == 0


class TestChangeDetectionServiceCommentMetrics:
    """Test comment metrics calculation functionality."""

    def test_calculate_comment_metrics_basic(self, change_detection_service, sample_post_with_comments, sample_current_comments):
        """Test basic comment metrics calculation."""
        stored_post, stored_comments, check_run_id = sample_post_with_comments

        metrics = change_detection_service.calculate_comment_metrics(
            stored_post.id,
            sample_current_comments
        )

        # Should include key metrics
        assert 'post_id' in metrics
        assert 'total_new_comments' in metrics
        assert 'average_score_change' in metrics
        assert 'top_new_comment' in metrics
        assert 'score_change_distribution' in metrics

        assert metrics['post_id'] == stored_post.id
        assert metrics['total_new_comments'] == 2  # comment_4 and comment_5

    def test_calculate_comment_metrics_score_changes(self, change_detection_service, sample_post_with_comments, sample_current_comments):
        """Test comment metrics score change calculations."""
        stored_post, stored_comments, check_run_id = sample_post_with_comments

        metrics = change_detection_service.calculate_comment_metrics(
            stored_post.id,
            sample_current_comments
        )

        # Check score change metrics
        score_changes = metrics['score_change_distribution']
        assert 'positive_changes' in score_changes
        assert 'negative_changes' in score_changes
        assert 'unchanged' in score_changes

        # We have 2 positive changes (comment_1: +5, comment_3: +4) and 1 unchanged (comment_2)
        assert score_changes['positive_changes'] == 2
        assert score_changes['unchanged'] == 1
        assert score_changes['negative_changes'] == 0

    def test_calculate_comment_metrics_top_comment(self, change_detection_service, sample_post_with_comments, sample_current_comments):
        """Test identification of top new comment."""
        stored_post, stored_comments, check_run_id = sample_post_with_comments

        metrics = change_detection_service.calculate_comment_metrics(
            stored_post.id,
            sample_current_comments
        )

        top_comment = metrics['top_new_comment']

        # Should identify comment_4 as top new comment (score 3 vs comment_5 score 1)
        assert top_comment['comment_id'] == 'comment_4'
        assert top_comment['score'] == 3

    def test_calculate_comment_metrics_no_new_comments(self, change_detection_service, sample_post_with_comments):
        """Test comment metrics when no new comments exist."""
        stored_post, stored_comments, check_run_id = sample_post_with_comments

        # Use only existing comments with no new ones
        existing_comments = [
            {
                'comment_id': 'comment_1',
                'author': 'commenter_1',
                'body': 'This is the first comment',
                'score': 10,
                'created_utc': datetime.now(UTC) - timedelta(hours=1, minutes=30),
                'parent_id': 'test_post_123',
                'is_submitter': False,
                'stickied': False
            }
        ]

        metrics = change_detection_service.calculate_comment_metrics(
            stored_post.id,
            existing_comments
        )

        assert metrics['total_new_comments'] == 0
        assert metrics['top_new_comment'] is None

    def test_calculate_comment_metrics_empty_current(self, change_detection_service, sample_post_with_comments):
        """Test comment metrics with empty current comments."""
        stored_post, stored_comments, check_run_id = sample_post_with_comments

        metrics = change_detection_service.calculate_comment_metrics(
            stored_post.id,
            []
        )

        assert metrics['total_new_comments'] == 0
        assert metrics['average_score_change'] == 0
        assert metrics['top_new_comment'] is None


class TestChangeDetectionServiceCommentErrorHandling:
    """Test error handling in comment analysis."""

    def test_find_new_comments_database_error(self, change_detection_service):
        """Test handling of database errors during new comment detection."""
        # Mock the storage service to raise an error
        change_detection_service.storage_service.get_comments_for_post = Mock(
            side_effect=SQLAlchemyError("Database error")
        )

        current_comments = [{'comment_id': 'test_comment', 'score': 5}]

        # Should handle error gracefully and return empty list
        new_comments = change_detection_service.find_new_comments(1, current_comments)
        assert len(new_comments) == 0

    def test_find_updated_comments_database_error(self, change_detection_service):
        """Test handling of database errors during updated comment detection."""
        # Mock the storage service to raise an error
        change_detection_service.storage_service.get_comments_for_post = Mock(
            side_effect=SQLAlchemyError("Database error")
        )

        current_comments = [{'comment_id': 'test_comment', 'score': 10}]

        # Should handle error gracefully and return empty list
        updated_comments = change_detection_service.find_updated_comments(1, current_comments)
        assert len(updated_comments) == 0

    def test_get_comment_tree_changes_database_error(self, change_detection_service):
        """Test handling of database errors during tree analysis."""
        # Mock the session to raise an error
        change_detection_service.session.query = Mock(
            side_effect=SQLAlchemyError("Database error")
        )

        # Should handle error gracefully and return empty structure
        tree_changes = change_detection_service.get_comment_tree_changes(1)
        assert tree_changes['total_stored_comments'] == 0

    def test_malformed_comment_data(self, change_detection_service, sample_post_with_comments):
        """Test handling of malformed comment data."""
        stored_post, stored_comments, check_run_id = sample_post_with_comments

        malformed_comments = [
            {'comment_id': 'incomplete_comment'},  # Missing required fields
            {'score': 5},  # Missing comment_id
            {}  # Empty dict
        ]

        # Should handle malformed data gracefully
        new_comments = change_detection_service.find_new_comments(
            stored_post.id,
            malformed_comments
        )

        # May return some comments with default values, but shouldn't crash
        assert isinstance(new_comments, list)


class TestChangeDetectionServiceCommentPerformance:
    """Test performance aspects of comment change detection."""

    def test_comment_detection_performance_many_comments(self, change_detection_service, storage_service):
        """Test performance with many comments."""
        import time

        # Create a post
        check_run_id = storage_service.create_check_run('python', 'performance_test')
        post_data = {
            'post_id': 'perf_post',
            'subreddit': 'python',
            'title': 'Performance Test Post',
            'author': 'author',
            'score': 100,
            'num_comments': 100,
            'url': 'https://reddit.com/perf',
            'permalink': '/r/python/comments/perf/test_post/',
            'is_self': True,
            'over_18': False,
            'created_utc': datetime.now(UTC) - timedelta(hours=2),
            'check_run_id': check_run_id
        }

        post_db_id = storage_service.save_post(post_data)

        # Create many stored comments
        base_time = datetime.now(UTC)
        for i in range(50):
            comment_data = {
                'comment_id': f'stored_comment_{i}',
                'post_id': post_db_id,
                'author': f'author_{i}',
                'body': f'Stored comment {i}',
                'score': i,
                'created_utc': base_time - timedelta(minutes=i),
                'parent_id': 'perf_post' if i % 3 == 0 else f'stored_comment_{i-1}',
                'is_submitter': False,
                'stickied': False
            }
            storage_service.save_comment(comment_data, post_db_id)

        # Create many current comments with some changes
        current_comments = []
        for i in range(70):  # 50 existing + 20 new
            current_comments.append({
                'comment_id': f'stored_comment_{i}' if i < 50 else f'new_comment_{i}',
                'author': f'author_{i}',
                'body': f'Comment {i}',
                'score': i + (i % 10),  # Slight score changes for existing
                'created_utc': base_time - timedelta(minutes=i),
                'parent_id': 'perf_post' if i % 3 == 0 else f'stored_comment_{max(0, i-1)}',
                'is_submitter': False,
                'stickied': False
            })

        # Measure performance
        start_time = time.time()
        new_comments = change_detection_service.find_new_comments(post_db_id, current_comments)
        updated_comments = change_detection_service.find_updated_comments(post_db_id, current_comments)
        end_time = time.time()

        # Should find new comments and some updates
        assert len(new_comments) == 20  # 20 new comments
        assert len(updated_comments) > 0  # Some score changes

        # Should complete in reasonable time (less than 2 seconds)
        duration = end_time - start_time
        assert duration < 2.0, f"Comment detection took {duration:.2f} seconds, expected < 2.0"

    def test_comment_tree_analysis_performance(self, change_detection_service, storage_service):
        """Test performance of comment tree analysis with deep hierarchy."""
        import time

        # Create a post
        check_run_id = storage_service.create_check_run('python', 'tree_performance')
        post_data = {
            'post_id': 'tree_perf_post',
            'subreddit': 'python',
            'title': 'Tree Performance Test',
            'author': 'author',
            'score': 50,
            'num_comments': 30,
            'url': 'https://reddit.com/tree_perf',
            'permalink': '/r/python/comments/tree_perf/test_post/',
            'is_self': True,
            'over_18': False,
            'created_utc': datetime.now(UTC) - timedelta(hours=2),
            'check_run_id': check_run_id
        }

        post_db_id = storage_service.save_post(post_data)

        # Create deep comment hierarchy
        base_time = datetime.now(UTC)
        prev_comment_id = 'tree_perf_post'

        for i in range(30):
            comment_data = {
                'comment_id': f'deep_comment_{i}',
                'post_id': post_db_id,
                'author': f'deep_author_{i}',
                'body': f'Deep comment {i}',
                'score': i,
                'created_utc': base_time - timedelta(minutes=i),
                'parent_id': prev_comment_id,
                'is_submitter': False,
                'stickied': False
            }
            storage_service.save_comment(comment_data, post_db_id)
            prev_comment_id = f'deep_comment_{i}'

        # Measure performance
        start_time = time.time()
        tree_changes = change_detection_service.get_comment_tree_changes(post_db_id)
        end_time = time.time()

        # Should analyze deep hierarchy correctly
        assert tree_changes['total_stored_comments'] == 30
        assert tree_changes['comment_hierarchy']['max_depth'] == 31  # Post + 30 comments

        # Should complete in reasonable time (less than 1 second)
        duration = end_time - start_time
        assert duration < 1.0, f"Tree analysis took {duration:.2f} seconds, expected < 1.0"
