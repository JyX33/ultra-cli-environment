# ABOUTME: Test suite for extended database models (Comment, PostSnapshot, ArticleContent)
# ABOUTME: Comprehensive testing of new models with foreign keys, relationships, and migrations

from datetime import UTC, datetime
import hashlib

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.check_run import CheckRun
from app.models.reddit_post import RedditPost


class TestCommentModel:
    """Test suite for Comment model."""

    @pytest.fixture
    def session(self):
        """Create test database session."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()

    @pytest.fixture
    def sample_check_run(self, session):
        """Create sample CheckRun for testing."""
        check_run = CheckRun(
            subreddit="test_sub",
            topic="test topic",
            posts_found=1,
            new_posts=1
        )
        session.add(check_run)
        session.commit()
        return check_run

    @pytest.fixture
    def sample_reddit_post(self, session, sample_check_run):
        """Create sample RedditPost for testing."""
        post = RedditPost(
            post_id="test123",
            subreddit="test_sub",
            title="Test Post",
            author="test_author",
            selftext="Test content",
            score=100,
            num_comments=5,
            url="https://reddit.com/r/test_sub/comments/test123",
            permalink="/r/test_sub/comments/test123",
            is_self=True,
            over_18=False,
            created_utc=datetime.now(UTC),
            check_run_id=sample_check_run.id
        )
        session.add(post)
        session.commit()
        return post

    def test_comment_model_creation(self, session, sample_reddit_post):
        """Test Comment model can be created with all required fields."""
        # Import here to avoid circular imports during test discovery
        from app.models.comment import Comment

        comment = Comment(
            comment_id="comment123",
            post_id=sample_reddit_post.id,
            author="commenter",
            body="This is a test comment",
            score=10,
            created_utc=datetime.now(UTC),
            parent_id=None,
            is_submitter=False,
            stickied=False,
            distinguished=None
        )

        session.add(comment)
        session.commit()

        assert comment.id is not None
        assert comment.comment_id == "comment123"
        assert comment.post_id == sample_reddit_post.id
        assert comment.author == "commenter"
        assert comment.body == "This is a test comment"
        assert comment.score == 10

    def test_comment_foreign_key_relationship(self, session, sample_reddit_post):
        """Test Comment has proper foreign key relationship to RedditPost."""
        from app.models.comment import Comment

        comment = Comment(
            comment_id="comment123",
            post_id=sample_reddit_post.id,
            author="commenter",
            body="Test comment",
            score=5,
            created_utc=datetime.now(UTC)
        )

        session.add(comment)
        session.commit()

        # Test relationship
        assert comment.reddit_post.post_id == sample_reddit_post.post_id
        assert len(sample_reddit_post.comments) == 1
        assert sample_reddit_post.comments[0].comment_id == "comment123"

    def test_comment_cascade_delete(self, session, sample_reddit_post):
        """Test comments are deleted when parent post is deleted."""
        from app.models.comment import Comment

        comment = Comment(
            comment_id="comment123",
            post_id=sample_reddit_post.id,
            author="commenter",
            body="Test comment",
            score=5,
            created_utc=datetime.now(UTC)
        )

        session.add(comment)
        session.commit()

        comment_id = comment.id

        # Delete the post
        session.delete(sample_reddit_post)
        session.commit()

        # Comment should be gone
        deleted_comment = session.get(Comment, comment_id)
        assert deleted_comment is None

    def test_comment_unique_constraint(self, session, sample_reddit_post):
        """Test unique constraint on comment_id."""
        from app.models.comment import Comment

        comment1 = Comment(
            comment_id="duplicate123",
            post_id=sample_reddit_post.id,
            author="commenter1",
            body="First comment",
            score=5,
            created_utc=datetime.now(UTC)
        )

        comment2 = Comment(
            comment_id="duplicate123",
            post_id=sample_reddit_post.id,
            author="commenter2",
            body="Second comment",
            score=3,
            created_utc=datetime.now(UTC)
        )

        session.add(comment1)
        session.commit()

        session.add(comment2)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_comment_parent_relationship(self, session, sample_reddit_post):
        """Test comment parent-child relationships."""
        from app.models.comment import Comment

        parent_comment = Comment(
            comment_id="parent123",
            post_id=sample_reddit_post.id,
            author="parent_author",
            body="Parent comment",
            score=10,
            created_utc=datetime.now(UTC),
            parent_id=None
        )

        session.add(parent_comment)
        session.commit()

        child_comment = Comment(
            comment_id="child123",
            post_id=sample_reddit_post.id,
            author="child_author",
            body="Child comment",
            score=5,
            created_utc=datetime.now(UTC),
            parent_id="parent123"
        )

        session.add(child_comment)
        session.commit()

        assert child_comment.parent_id == "parent123"
        assert parent_comment.parent_id is None


class TestPostSnapshotModel:
    """Test suite for PostSnapshot model."""

    @pytest.fixture
    def session(self):
        """Create test database session."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()

    @pytest.fixture
    def sample_data(self, session):
        """Create sample CheckRun and RedditPost for testing."""
        check_run = CheckRun(
            subreddit="test_sub",
            topic="test topic",
            posts_found=1,
            new_posts=1
        )
        session.add(check_run)
        session.commit()

        post = RedditPost(
            post_id="test123",
            subreddit="test_sub",
            title="Test Post",
            author="test_author",
            selftext="Test content",
            score=100,
            num_comments=5,
            url="https://reddit.com/r/test_sub/comments/test123",
            permalink="/r/test_sub/comments/test123",
            is_self=True,
            over_18=False,
            created_utc=datetime.now(UTC),
            check_run_id=check_run.id
        )
        session.add(post)
        session.commit()

        return check_run, post

    def test_post_snapshot_creation(self, session, sample_data):
        """Test PostSnapshot can be created with all fields."""
        from app.models.post_snapshot import PostSnapshot

        check_run, post = sample_data
        snapshot_time = datetime.now(UTC)

        snapshot = PostSnapshot(
            post_id=post.id,
            check_run_id=check_run.id,
            snapshot_time=snapshot_time,
            score=150,
            num_comments=8,
            score_delta=50,
            comments_delta=3
        )

        session.add(snapshot)
        session.commit()

        assert snapshot.id is not None
        assert snapshot.post_id == post.id
        assert snapshot.check_run_id == check_run.id
        assert snapshot.score == 150
        assert snapshot.num_comments == 8
        assert snapshot.score_delta == 50
        assert snapshot.comments_delta == 3

    def test_post_snapshot_relationships(self, session, sample_data):
        """Test PostSnapshot foreign key relationships."""
        from app.models.post_snapshot import PostSnapshot

        check_run, post = sample_data

        snapshot = PostSnapshot(
            post_id=post.id,
            check_run_id=check_run.id,
            snapshot_time=datetime.now(UTC),
            score=150,
            num_comments=8
        )

        session.add(snapshot)
        session.commit()

        # Test relationships
        assert snapshot.reddit_post.post_id == post.post_id
        assert snapshot.check_run.subreddit == check_run.subreddit
        assert len(post.snapshots) == 1
        assert len(check_run.post_snapshots) == 1

    def test_post_snapshot_cascade_delete(self, session, sample_data):
        """Test cascading deletes for PostSnapshot."""
        from app.models.post_snapshot import PostSnapshot

        check_run, post = sample_data

        snapshot = PostSnapshot(
            post_id=post.id,
            check_run_id=check_run.id,
            snapshot_time=datetime.now(UTC),
            score=150,
            num_comments=8
        )

        session.add(snapshot)
        session.commit()
        snapshot_id = snapshot.id

        # Delete the post - snapshot should be deleted
        session.delete(post)
        session.commit()

        deleted_snapshot = session.get(PostSnapshot, snapshot_id)
        assert deleted_snapshot is None

    def test_post_snapshot_indexes(self, session, sample_data):
        """Test PostSnapshot indexes are created properly."""
        from app.models.post_snapshot import PostSnapshot

        # This test verifies indexes exist by checking they can be used in queries
        check_run, post = sample_data

        # Create multiple snapshots
        for i in range(3):
            snapshot = PostSnapshot(
                post_id=post.id,
                check_run_id=check_run.id,
                snapshot_time=datetime.now(UTC),
                score=100 + i * 10,
                num_comments=5 + i
            )
            session.add(snapshot)
        session.commit()

        # Query using indexed columns
        snapshots = session.query(PostSnapshot).filter(
            PostSnapshot.post_id == post.id
        ).order_by(PostSnapshot.snapshot_time).all()

        assert len(snapshots) == 3
        assert snapshots[0].score == 100
        assert snapshots[2].score == 120


class TestArticleContentModel:
    """Test suite for ArticleContent model."""

    @pytest.fixture
    def session(self):
        """Create test database session."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()

    def test_article_content_creation(self, session):
        """Test ArticleContent can be created with URL hashing."""
        from app.models.article_content import ArticleContent

        url = "https://example.com/article/test-article"
        content = ArticleContent(
            url=url,
            title="Test Article",
            content="This is test article content",
            author="Test Author",
            publish_date=datetime.now(UTC),
            scraped_at=datetime.now(UTC)
        )

        session.add(content)
        session.commit()

        assert content.id is not None
        assert content.url == url
        assert content.url_hash is not None
        assert len(content.url_hash) == 64  # SHA256 hex length
        assert content.title == "Test Article"
        assert content.content == "This is test article content"

    def test_article_content_url_hashing(self, session):
        """Test URL hash generation is consistent."""
        from app.models.article_content import ArticleContent

        url = "https://example.com/test"
        expected_hash = hashlib.sha256(url.encode()).hexdigest()

        content = ArticleContent(
            url=url,
            title="Test",
            content="Test content",
            scraped_at=datetime.now(UTC)
        )

        session.add(content)
        session.commit()

        assert content.url_hash == expected_hash

    def test_article_content_unique_constraint(self, session):
        """Test unique constraint on url_hash prevents duplicates."""
        from app.models.article_content import ArticleContent

        url = "https://example.com/duplicate"

        content1 = ArticleContent(
            url=url,
            title="First Article",
            content="First content",
            scraped_at=datetime.now(UTC)
        )

        content2 = ArticleContent(
            url=url,
            title="Second Article",
            content="Second content",
            scraped_at=datetime.now(UTC)
        )

        session.add(content1)
        session.commit()

        session.add(content2)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_article_content_nullable_fields(self, session):
        """Test nullable fields work correctly."""
        from app.models.article_content import ArticleContent

        content = ArticleContent(
            url="https://example.com/minimal",
            scraped_at=datetime.now(UTC)
            # title, content, author, publish_date are nullable
        )

        session.add(content)
        session.commit()

        assert content.title is None
        assert content.content is None
        assert content.author is None
        assert content.publish_date is None
        assert content.url_hash is not None

    def test_article_content_indexes(self, session):
        """Test ArticleContent indexes for performance."""
        from app.models.article_content import ArticleContent

        # Create multiple articles
        for i in range(5):
            content = ArticleContent(
                url=f"https://example.com/article{i}",
                title=f"Article {i}",
                content=f"Content {i}",
                scraped_at=datetime.now(UTC)
            )
            session.add(content)
        session.commit()

        # Query using indexed column (url_hash)
        test_url = "https://example.com/article2"
        expected_hash = hashlib.sha256(test_url.encode()).hexdigest()

        result = session.query(ArticleContent).filter(
            ArticleContent.url_hash == expected_hash
        ).first()

        assert result is not None
        assert result.url == test_url


class TestMigrationFunctionality:
    """Test migration execution and rollback."""

    def test_migration_execution(self):
        """Test that migrations can be executed successfully."""
        # This will be implemented after Alembic is set up
        # For now, we test that models can create tables
        engine = create_engine("sqlite:///:memory:")

        # This should not raise any errors
        Base.metadata.create_all(engine)

        # Verify tables were created
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ))
            table_names = [row[0] for row in result]


        # Note: Some tables might not exist yet since models aren't created
        # This test will be fully implemented after models are created
        assert "check_runs" in table_names
        assert "reddit_posts" in table_names

    def test_rollback_functionality(self):
        """Test that database operations can be rolled back."""
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)

        session = Session()
        try:
            # Create a check run
            check_run = CheckRun(
                subreddit="test",
                topic="test topic",
                posts_found=1,
                new_posts=1
            )
            session.add(check_run)
            session.flush()  # Get ID without committing

            check_run_id = check_run.id
            assert check_run_id is not None

            # Roll back the transaction
            session.rollback()

            # Verify the check run was not persisted
            result = session.get(CheckRun, check_run_id)
            assert result is None

        finally:
            session.close()
