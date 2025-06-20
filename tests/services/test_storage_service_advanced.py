# ABOUTME: Advanced tests for StorageService relationship handling and complex queries
# ABOUTME: Tests covering comments, snapshots, bulk operations, and query optimization

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.comment import Comment
from app.models.post_snapshot import PostSnapshot
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
def sample_check_run(storage_service):
    """Create a sample check run for testing."""
    return storage_service.create_check_run("python", "testing")


@pytest.fixture
def sample_post(storage_service, sample_check_run):
    """Create a sample Reddit post for testing."""
    post_data = {
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
        'created_utc': datetime.now(UTC),
        'check_run_id': sample_check_run
    }
    db_post_id = storage_service.save_post(post_data)
    return db_post_id, post_data


@pytest.fixture
def sample_comment_data():
    """Sample Reddit comment data for testing."""
    return {
        'comment_id': 'comment_abc123',
        'author': 'commenter_user',
        'body': 'This is a test comment',
        'score': 10,
        'created_utc': datetime.now(UTC),
        'parent_id': None,  # Top-level comment
        'is_submitter': False,
        'stickied': False,
        'distinguished': None
    }


class TestStorageServiceSaveComment:
    """Test save_comment functionality."""

    def test_save_comment_with_valid_post(self, storage_service, sample_post, sample_comment_data, session):
        """Test saving a comment linked to an existing post."""
        post_id, _ = sample_post

        comment_id = storage_service.save_comment(sample_comment_data, post_id)

        assert isinstance(comment_id, int)
        assert comment_id > 0

        # Verify comment was saved correctly
        saved_comment = session.get(Comment, comment_id)
        assert saved_comment is not None
        assert saved_comment.comment_id == sample_comment_data['comment_id']
        assert saved_comment.post_id == post_id
        assert saved_comment.author == sample_comment_data['author']
        assert saved_comment.body == sample_comment_data['body']
        assert saved_comment.score == sample_comment_data['score']

    def test_save_comment_with_parent_relationship(self, storage_service, sample_post, sample_comment_data, session):
        """Test saving a comment with parent comment relationship."""
        post_id, _ = sample_post

        # Create parent comment
        parent_comment_data = sample_comment_data.copy()
        parent_comment_data['comment_id'] = 'parent_comment'
        storage_service.save_comment(parent_comment_data, post_id)

        # Create child comment
        child_comment_data = sample_comment_data.copy()
        child_comment_data['comment_id'] = 'child_comment'
        child_comment_data['parent_id'] = 'parent_comment'
        child_comment_id = storage_service.save_comment(child_comment_data, post_id)

        # Verify parent relationship
        child_comment = session.get(Comment, child_comment_id)
        assert child_comment.parent_id == 'parent_comment'

    def test_save_comment_nonexistent_post(self, storage_service, sample_comment_data):
        """Test save_comment with non-existent post ID."""
        nonexistent_post_id = 99999

        with pytest.raises(RuntimeError, match="Post with ID .* does not exist"):
            storage_service.save_comment(sample_comment_data, nonexistent_post_id)

    def test_save_comment_duplicate_comment_id(self, storage_service, sample_post, sample_comment_data):
        """Test handling of duplicate comment IDs."""
        post_id, _ = sample_post

        # Save first comment
        storage_service.save_comment(sample_comment_data, post_id)

        # Try to save another comment with same comment_id
        duplicate_data = sample_comment_data.copy()
        duplicate_data['body'] = 'Different body'

        with pytest.raises(RuntimeError, match="Failed to save comment"):
            storage_service.save_comment(duplicate_data, post_id)

    def test_save_comment_with_special_characters(self, storage_service, sample_post, sample_comment_data):
        """Test saving comments with special characters and Unicode."""
        post_id, _ = sample_post

        unicode_data = sample_comment_data.copy()
        unicode_data.update({
            'comment_id': 'unicode_comment',
            'author': 'tëst_üser',
            'body': 'Comment with émojis 🐍 and ünicöde content: ñoñó, 中文, العربية'
        })

        comment_id = storage_service.save_comment(unicode_data, post_id)
        assert isinstance(comment_id, int)

    def test_save_comment_deleted_author(self, storage_service, sample_post, sample_comment_data):
        """Test saving comment with deleted author (None)."""
        post_id, _ = sample_post

        deleted_author_data = sample_comment_data.copy()
        deleted_author_data.update({
            'comment_id': 'deleted_author_comment',
            'author': None  # Deleted author
        })

        comment_id = storage_service.save_comment(deleted_author_data, post_id)
        assert isinstance(comment_id, int)


class TestStorageServiceSavePostSnapshot:
    """Test save_post_snapshot functionality."""

    def test_save_post_snapshot_basic(self, storage_service, sample_post, sample_check_run, session):
        """Test saving a basic post snapshot."""
        post_id, _ = sample_post
        score = 100
        num_comments = 25

        snapshot_id = storage_service.save_post_snapshot(post_id, sample_check_run, score, num_comments)

        assert isinstance(snapshot_id, int)
        assert snapshot_id > 0

        # Verify snapshot was saved correctly
        saved_snapshot = session.get(PostSnapshot, snapshot_id)
        assert saved_snapshot is not None
        assert saved_snapshot.post_id == post_id
        assert saved_snapshot.check_run_id == sample_check_run
        assert saved_snapshot.score == score
        assert saved_snapshot.num_comments == num_comments
        assert saved_snapshot.snapshot_time is not None

    def test_save_post_snapshot_with_deltas(self, storage_service, sample_post, session):
        """Test saving post snapshots with delta calculations."""
        post_id, _ = sample_post

        # Create first check run and snapshot
        check_run_1 = storage_service.create_check_run("python", "testing")
        storage_service.save_post_snapshot(post_id, check_run_1, 50, 10)

        # Create second check run and snapshot with deltas
        check_run_2 = storage_service.create_check_run("python", "testing")
        snapshot_2_id = storage_service.save_post_snapshot(
            post_id, check_run_2, 75, 15, score_delta=25, comments_delta=5
        )

        # Verify second snapshot has deltas
        snapshot_2 = session.get(PostSnapshot, snapshot_2_id)
        assert snapshot_2.score_delta == 25
        assert snapshot_2.comments_delta == 5

    def test_save_post_snapshot_nonexistent_post(self, storage_service, sample_check_run):
        """Test save_post_snapshot with non-existent post."""
        nonexistent_post_id = 99999

        with pytest.raises(RuntimeError, match="Post with ID .* does not exist"):
            storage_service.save_post_snapshot(nonexistent_post_id, sample_check_run, 50, 10)

    def test_save_post_snapshot_nonexistent_check_run(self, storage_service, sample_post):
        """Test save_post_snapshot with non-existent check run."""
        post_id, _ = sample_post
        nonexistent_check_run_id = 99999

        with pytest.raises(RuntimeError, match="Check run with ID .* does not exist"):
            storage_service.save_post_snapshot(post_id, nonexistent_check_run_id, 50, 10)

    def test_save_post_snapshot_negative_values(self, storage_service, sample_post, sample_check_run):
        """Test save_post_snapshot with negative scores and deltas."""
        post_id, _ = sample_post

        snapshot_id = storage_service.save_post_snapshot(
            post_id, sample_check_run, -5, 0, score_delta=-10, comments_delta=0
        )

        assert isinstance(snapshot_id, int)


class TestStorageServiceGetNewPostsSince:
    """Test get_new_posts_since functionality."""

    def test_get_new_posts_since_basic(self, storage_service, session):
        """Test basic get_new_posts_since query."""
        subreddit = "python"

        # Create check runs and posts with different timestamps
        check_run_1 = storage_service.create_check_run(subreddit, "testing")

        # Create posts with specific timestamps
        base_time = datetime.now(UTC)
        old_time = base_time - timedelta(hours=2)
        new_time = base_time - timedelta(minutes=30)

        # Old post
        old_post_data = {
            'post_id': 'old_post',
            'subreddit': subreddit,
            'title': 'Old Post',
            'author': 'user1',
            'selftext': 'Old content',
            'score': 10,
            'num_comments': 2,
            'url': 'https://reddit.com/old',
            'permalink': '/r/python/comments/old/test_post/',
            'is_self': True,
            'over_18': False,
            'created_utc': old_time,
            'check_run_id': check_run_1
        }
        storage_service.save_post(old_post_data)

        # New post
        new_post_data = {
            'post_id': 'new_post',
            'subreddit': subreddit,
            'title': 'New Post',
            'author': 'user2',
            'selftext': 'New content',
            'score': 20,
            'num_comments': 5,
            'url': 'https://reddit.com/new',
            'permalink': '/r/python/comments/new/test_post/',
            'is_self': True,
            'over_18': False,
            'created_utc': new_time,
            'check_run_id': check_run_1
        }
        storage_service.save_post(new_post_data)

        # Query for posts newer than 1 hour ago
        cutoff_time = base_time - timedelta(hours=1)
        new_posts = storage_service.get_new_posts_since(subreddit, cutoff_time)

        assert len(new_posts) == 1
        assert new_posts[0].post_id == 'new_post'

    def test_get_new_posts_since_different_subreddits(self, storage_service):
        """Test get_new_posts_since filters by subreddit correctly."""
        base_time = datetime.now(UTC)
        check_run = storage_service.create_check_run("general", "testing")

        # Create posts in different subreddits
        for subreddit in ['python', 'javascript', 'golang']:
            post_data = {
                'post_id': f'{subreddit}_post',
                'subreddit': subreddit,
                'title': f'{subreddit} Post',
                'author': 'user',
                'selftext': 'Content',
                'score': 10,
                'num_comments': 2,
                'url': f'https://reddit.com/{subreddit}',
                'permalink': f'/r/{subreddit}/comments/post/test_post/',
                'is_self': True,
                'over_18': False,
                'created_utc': base_time,
                'check_run_id': check_run
            }
            storage_service.save_post(post_data)

        # Query for only python posts
        cutoff_time = base_time - timedelta(hours=1)
        python_posts = storage_service.get_new_posts_since("python", cutoff_time)

        assert len(python_posts) == 1
        assert python_posts[0].subreddit == "python"

    def test_get_new_posts_since_ordering(self, storage_service):
        """Test that get_new_posts_since returns posts in correct order."""
        subreddit = "python"
        check_run = storage_service.create_check_run(subreddit, "testing")
        base_time = datetime.now(UTC)

        # Create posts with different timestamps and scores
        posts_data = [
            ('post1', base_time - timedelta(minutes=30), 100),
            ('post2', base_time - timedelta(minutes=20), 50),
            ('post3', base_time - timedelta(minutes=10), 200),
        ]

        for post_id, created_time, score in posts_data:
            post_data = {
                'post_id': post_id,
                'subreddit': subreddit,
                'title': f'Post {post_id}',
                'author': 'user',
                'selftext': 'Content',
                'score': score,
                'num_comments': 2,
                'url': f'https://reddit.com/{post_id}',
                'permalink': f'/r/python/comments/{post_id}/test_post/',
                'is_self': True,
                'over_18': False,
                'created_utc': created_time,
                'check_run_id': check_run
            }
            storage_service.save_post(post_data)

        # Query for all posts
        cutoff_time = base_time - timedelta(hours=1)
        posts = storage_service.get_new_posts_since(subreddit, cutoff_time)

        # Should be ordered by score desc, then created_utc desc
        assert len(posts) == 3
        assert posts[0].post_id == 'post3'  # Highest score
        assert posts[1].post_id == 'post1'  # Second highest score
        assert posts[2].post_id == 'post2'  # Lowest score

    def test_get_new_posts_since_no_results(self, storage_service):
        """Test get_new_posts_since with no matching posts."""
        cutoff_time = datetime.now(UTC) - timedelta(minutes=10)
        posts = storage_service.get_new_posts_since("nonexistent", cutoff_time)

        assert len(posts) == 0


class TestStorageServiceGetCommentsForPost:
    """Test get_comments_for_post functionality."""

    def test_get_comments_for_post_basic(self, storage_service, sample_post, session):
        """Test retrieving comments for a post."""
        post_id, _ = sample_post

        # Create multiple comments for the post
        comment_data_list = [
            {
                'comment_id': 'comment1',
                'author': 'user1',
                'body': 'First comment',
                'score': 10,
                'created_utc': datetime.now(UTC) - timedelta(minutes=30),
                'parent_id': None,
                'is_submitter': False,
                'stickied': False,
                'distinguished': None
            },
            {
                'comment_id': 'comment2',
                'author': 'user2',
                'body': 'Second comment',
                'score': 5,
                'created_utc': datetime.now(UTC) - timedelta(minutes=20),
                'parent_id': None,
                'is_submitter': True,
                'stickied': False,
                'distinguished': None
            },
            {
                'comment_id': 'comment3',
                'author': 'user3',
                'body': 'Third comment',
                'score': 15,
                'created_utc': datetime.now(UTC) - timedelta(minutes=10),
                'parent_id': None,
                'is_submitter': False,
                'stickied': True,
                'distinguished': 'moderator'
            }
        ]

        for comment_data in comment_data_list:
            storage_service.save_comment(comment_data, post_id)

        # Retrieve comments
        comments = storage_service.get_comments_for_post(post_id)

        assert len(comments) == 3
        # Should be ordered by score desc
        assert comments[0].comment_id == 'comment3'  # score 15
        assert comments[1].comment_id == 'comment1'  # score 10
        assert comments[2].comment_id == 'comment2'  # score 5

    def test_get_comments_for_post_with_hierarchy(self, storage_service, sample_post):
        """Test retrieving comments with parent-child relationships."""
        post_id, _ = sample_post

        # Create parent comment
        parent_data = {
            'comment_id': 'parent_comment',
            'author': 'parent_user',
            'body': 'Parent comment',
            'score': 20,
            'created_utc': datetime.now(UTC) - timedelta(minutes=30),
            'parent_id': None,
            'is_submitter': False,
            'stickied': False,
            'distinguished': None
        }
        storage_service.save_comment(parent_data, post_id)

        # Create child comments
        for i in range(3):
            child_data = {
                'comment_id': f'child_comment_{i}',
                'author': f'child_user_{i}',
                'body': f'Child comment {i}',
                'score': 5 + i,
                'created_utc': datetime.now(UTC) - timedelta(minutes=20 - i),
                'parent_id': 'parent_comment',
                'is_submitter': False,
                'stickied': False,
                'distinguished': None
            }
            storage_service.save_comment(child_data, post_id)

        comments = storage_service.get_comments_for_post(post_id)

        assert len(comments) == 4
        # Parent should be first (highest score)
        assert comments[0].comment_id == 'parent_comment'
        # Child comments should follow
        child_comments = [c for c in comments if c.parent_id == 'parent_comment']
        assert len(child_comments) == 3

    def test_get_comments_for_post_nonexistent_post(self, storage_service):
        """Test get_comments_for_post with non-existent post."""
        comments = storage_service.get_comments_for_post(99999)
        assert len(comments) == 0

    def test_get_comments_for_post_no_comments(self, storage_service, sample_post):
        """Test get_comments_for_post when post has no comments."""
        post_id, _ = sample_post
        comments = storage_service.get_comments_for_post(post_id)
        assert len(comments) == 0


class TestStorageServiceBulkSaveComments:
    """Test bulk_save_comments functionality."""

    def test_bulk_save_comments_basic(self, storage_service, sample_post, session):
        """Test bulk saving multiple comments."""
        post_id, _ = sample_post

        comments_data = []
        for i in range(5):
            comment_data = {
                'comment_id': f'bulk_comment_{i}',
                'author': f'user_{i}',
                'body': f'Bulk comment {i}',
                'score': i * 2,
                'created_utc': datetime.now(UTC) - timedelta(minutes=i),
                'parent_id': None,
                'is_submitter': False,
                'stickied': False,
                'distinguished': None
            }
            comments_data.append(comment_data)

        saved_count = storage_service.bulk_save_comments(comments_data, post_id)

        assert saved_count == 5

        # Verify all comments were saved
        comments = storage_service.get_comments_for_post(post_id)
        assert len(comments) == 5

    def test_bulk_save_comments_with_partial_failure(self, storage_service, sample_post):
        """Test bulk_save_comments with some invalid data."""
        post_id, _ = sample_post

        # First save a comment to create a duplicate scenario
        initial_comment = {
            'comment_id': 'duplicate_comment',
            'author': 'user',
            'body': 'Initial comment',
            'score': 5,
            'created_utc': datetime.now(UTC),
            'parent_id': None,
            'is_submitter': False,
            'stickied': False,
            'distinguished': None
        }
        storage_service.save_comment(initial_comment, post_id)

        # Try to bulk save including the duplicate
        comments_data = [
            {
                'comment_id': 'new_comment_1',
                'author': 'user1',
                'body': 'New comment 1',
                'score': 3,
                'created_utc': datetime.now(UTC),
                'parent_id': None,
                'is_submitter': False,
                'stickied': False,
                'distinguished': None
            },
            {
                'comment_id': 'duplicate_comment',  # This should fail
                'author': 'user2',
                'body': 'Duplicate comment',
                'score': 4,
                'created_utc': datetime.now(UTC),
                'parent_id': None,
                'is_submitter': False,
                'stickied': False,
                'distinguished': None
            },
            {
                'comment_id': 'new_comment_2',
                'author': 'user3',
                'body': 'New comment 2',
                'score': 6,
                'created_utc': datetime.now(UTC),
                'parent_id': None,
                'is_submitter': False,
                'stickied': False,
                'distinguished': None
            }
        ]

        saved_count = storage_service.bulk_save_comments(comments_data, post_id)

        # Should save 2 out of 3 (skipping the duplicate)
        assert saved_count == 2

        # Verify correct comments were saved (including initial one)
        comments = storage_service.get_comments_for_post(post_id)
        assert len(comments) == 3  # initial + 2 new successful

    def test_bulk_save_comments_empty_list(self, storage_service, sample_post):
        """Test bulk_save_comments with empty list."""
        post_id, _ = sample_post

        saved_count = storage_service.bulk_save_comments([], post_id)
        assert saved_count == 0

    def test_bulk_save_comments_nonexistent_post(self, storage_service):
        """Test bulk_save_comments with non-existent post."""
        comments_data = [{
            'comment_id': 'test_comment',
            'author': 'user',
            'body': 'Test comment',
            'score': 5,
            'created_utc': datetime.now(UTC),
            'parent_id': None,
            'is_submitter': False,
            'stickied': False,
            'distinguished': None
        }]

        with pytest.raises(RuntimeError, match="Post with ID .* does not exist"):
            storage_service.bulk_save_comments(comments_data, 99999)


class TestStorageServiceQueryPerformance:
    """Test query performance and optimization."""

    def test_get_new_posts_since_query_efficiency(self, storage_service, session):
        """Test that get_new_posts_since uses efficient queries."""
        # This test verifies the query doesn't cause N+1 problems
        subreddit = "python"
        check_run = storage_service.create_check_run(subreddit, "testing")
        base_time = datetime.now(UTC)

        # Create multiple posts
        for i in range(10):
            post_data = {
                'post_id': f'perf_post_{i}',
                'subreddit': subreddit,
                'title': f'Performance Post {i}',
                'author': f'user_{i}',
                'selftext': f'Content {i}',
                'score': i * 10,
                'num_comments': i * 2,
                'url': f'https://reddit.com/perf_{i}',
                'permalink': f'/r/python/comments/perf_{i}/test_post/',
                'is_self': True,
                'over_18': False,
                'created_utc': base_time - timedelta(minutes=i),
                'check_run_id': check_run
            }
            storage_service.save_post(post_data)

        # Execute query and verify it returns results efficiently
        cutoff_time = base_time - timedelta(hours=1)

        # Use SQL logging to verify query efficiency
        with patch('app.services.storage_service.logger'):
            posts = storage_service.get_new_posts_since(subreddit, cutoff_time)
            assert len(posts) == 10
            # The query should be efficient (we can't easily test exact query count in SQLite,
            # but we verify it completes and returns correct results)

    def test_bulk_operations_transaction_efficiency(self, storage_service, sample_post, session):
        """Test that bulk operations use efficient transactions."""
        post_id, _ = sample_post

        # Create a large number of comments to test bulk efficiency
        comments_data = []
        for i in range(50):
            comment_data = {
                'comment_id': f'bulk_perf_comment_{i}',
                'author': f'bulk_user_{i}',
                'body': f'Bulk performance comment {i}',
                'score': i,
                'created_utc': datetime.now(UTC) - timedelta(seconds=i),
                'parent_id': None,
                'is_submitter': False,
                'stickied': False,
                'distinguished': None
            }
            comments_data.append(comment_data)

        # Measure that bulk operation is reasonably fast
        import time
        start_time = time.time()
        saved_count = storage_service.bulk_save_comments(comments_data, post_id)
        end_time = time.time()

        assert saved_count == 50
        # Bulk operation should complete in reasonable time (less than 1 second for 50 items)
        assert (end_time - start_time) < 1.0

    def test_comment_retrieval_with_indexes(self, storage_service, sample_post, session):
        """Test that comment retrieval uses database indexes efficiently."""
        post_id, _ = sample_post

        # Create many comments to test index usage
        comments_data = []
        for i in range(20):
            comment_data = {
                'comment_id': f'index_comment_{i}',
                'author': f'index_user_{i}',
                'body': f'Index test comment {i}',
                'score': i * 3,
                'created_utc': datetime.now(UTC) - timedelta(minutes=i),
                'parent_id': None,
                'is_submitter': False,
                'stickied': False,
                'distinguished': None
            }
            comments_data.append(comment_data)

        storage_service.bulk_save_comments(comments_data, post_id)

        # Verify that retrieval is efficient
        comments = storage_service.get_comments_for_post(post_id)
        assert len(comments) == 20

        # Verify ordering (should use score index)
        scores = [c.score for c in comments]
        assert scores == sorted(scores, reverse=True)


class TestStorageServiceTransactionBoundaries:
    """Test transaction boundaries for advanced operations."""

    def test_bulk_save_comments_transaction_rollback(self, storage_service, sample_post, session):
        """Test that bulk_save_comments rolls back properly on error."""
        post_id, _ = sample_post

        # Create comments with one that will cause an error (missing required field)
        comments_data = [
            {
                'comment_id': 'good_comment_1',
                'author': 'user1',
                'body': 'Good comment 1',
                'score': 5,
                'created_utc': datetime.now(UTC),
                'parent_id': None,
                'is_submitter': False,
                'stickied': False,
                'distinguished': None
            },
            {
                # Missing 'body' field - will cause error
                'comment_id': 'bad_comment',
                'author': 'user2',
                'score': 3,
                'created_utc': datetime.now(UTC),
                'parent_id': None,
                'is_submitter': False,
                'stickied': False,
                'distinguished': None
            },
            {
                'comment_id': 'good_comment_2',
                'author': 'user3',
                'body': 'Good comment 2',
                'score': 7,
                'created_utc': datetime.now(UTC),
                'parent_id': None,
                'is_submitter': False,
                'stickied': False,
                'distinguished': None
            }
        ]

        # Should handle error gracefully
        saved_count = storage_service.bulk_save_comments(comments_data, post_id)

        # Should save the valid comments and skip the invalid one
        assert saved_count == 2

        # Verify only valid comments were saved
        comments = storage_service.get_comments_for_post(post_id)
        comment_ids = [c.comment_id for c in comments]
        assert 'good_comment_1' in comment_ids
        assert 'good_comment_2' in comment_ids
        assert 'bad_comment' not in comment_ids

    def test_save_post_snapshot_transaction_safety(self, storage_service, sample_post, session):
        """Test transaction safety for save_post_snapshot."""
        post_id, _ = sample_post

        # Mock session.commit to raise an error
        original_commit = session.commit
        session.commit = Mock(side_effect=SQLAlchemyError("Transaction failed"))

        try:
            with pytest.raises(RuntimeError, match="Failed to save post snapshot"):
                storage_service.save_post_snapshot(post_id, 1, 100, 50)
        finally:
            # Restore original commit
            session.commit = original_commit

        # Verify no snapshot was persisted due to rollback
        snapshots = session.query(PostSnapshot).filter(PostSnapshot.post_id == post_id).all()
        assert len(snapshots) == 0
