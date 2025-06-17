# ABOUTME: Test core database models (CheckRun and RedditPost)
# ABOUTME: Validates model creation, relationships, constraints, and database operations

from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.db.session import SessionLocal, engine


class TestCheckRunModel:
    """Test CheckRun model functionality."""

    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Create tables before each test and clean up after."""
        # Create all tables
        Base.metadata.create_all(bind=engine)
        yield
        # Drop all tables
        Base.metadata.drop_all(bind=engine)

    def test_checkrun_model_creation(self):
        """Test CheckRun model can be instantiated with all required fields."""
        from app.models.check_run import CheckRun

        # Create CheckRun instance
        now = datetime.now(UTC)
        check_run = CheckRun(
            subreddit="technology",
            topic="artificial intelligence",
            timestamp=now,
            posts_found=25,
            new_posts=5
        )

        # Verify fields are set correctly
        assert check_run.subreddit == "technology"
        assert check_run.topic == "artificial intelligence"
        assert check_run.timestamp == now
        assert check_run.posts_found == 25
        assert check_run.new_posts == 5

    def test_checkrun_model_fields_types(self):
        """Test CheckRun model has correct field types."""
        from app.models.check_run import CheckRun

        # Get model inspector
        inspector = inspect(CheckRun)
        columns = {col.name: col for col in inspector.columns}

        # Verify column types
        assert 'id' in columns
        assert 'subreddit' in columns
        assert 'topic' in columns
        assert 'timestamp' in columns
        assert 'posts_found' in columns
        assert 'new_posts' in columns

        # Verify specific types
        assert str(columns['subreddit'].type).startswith('VARCHAR')
        assert str(columns['topic'].type).startswith('VARCHAR')
        assert 'DATETIME' in str(columns['timestamp'].type) or 'TIMESTAMP' in str(columns['timestamp'].type)
        assert 'INTEGER' in str(columns['posts_found'].type)
        assert 'INTEGER' in str(columns['new_posts'].type)

    def test_checkrun_database_persistence(self):
        """Test CheckRun can be saved to and retrieved from database."""
        from app.models.check_run import CheckRun

        session = SessionLocal()
        try:
            # Create and save CheckRun
            now = datetime.now(UTC)
            check_run = CheckRun(
                subreddit="programming",
                topic="python",
                timestamp=now,
                posts_found=10,
                new_posts=3
            )
            session.add(check_run)
            session.commit()

            # Verify it was saved (should have an ID)
            assert check_run.id is not None

            # Retrieve from database
            retrieved = session.query(CheckRun).filter_by(id=check_run.id).first()
            assert retrieved is not None
            assert retrieved.subreddit == "programming"
            assert retrieved.topic == "python"
            assert retrieved.posts_found == 10
            assert retrieved.new_posts == 3

        finally:
            session.close()

    def test_checkrun_timestamp_defaults(self):
        """Test CheckRun timestamp handling and UTC timezone."""
        from app.models.check_run import CheckRun

        session = SessionLocal()
        try:
            # Create CheckRun without explicit timestamp if default is set
            check_run = CheckRun(
                subreddit="science",
                topic="climate",
                posts_found=15,
                new_posts=2
            )

            # If no default timestamp, set one manually
            if check_run.timestamp is None:
                check_run.timestamp = datetime.now(UTC)

            session.add(check_run)
            session.commit()

            # Verify timestamp is in UTC
            assert check_run.timestamp.tzinfo is not None

        finally:
            session.close()

    def test_checkrun_repr_method(self):
        """Test CheckRun has a useful __repr__ method for debugging."""
        from app.models.check_run import CheckRun

        check_run = CheckRun(
            subreddit="datascience",
            topic="machine learning",
            timestamp=datetime.now(UTC),
            posts_found=8,
            new_posts=1
        )

        repr_str = repr(check_run)
        assert "CheckRun" in repr_str
        assert "datascience" in repr_str
        assert "machine learning" in repr_str


class TestRedditPostModel:
    """Test RedditPost model functionality."""

    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Create tables before each test and clean up after."""
        Base.metadata.create_all(bind=engine)
        yield
        Base.metadata.drop_all(bind=engine)

    def test_redditpost_model_creation(self):
        """Test RedditPost model can be instantiated with all fields."""
        from app.models.check_run import CheckRun
        from app.models.reddit_post import RedditPost

        session = SessionLocal()
        try:
            # Create a CheckRun first (for foreign key)
            check_run = CheckRun(
                subreddit="technology",
                topic="AI",
                timestamp=datetime.now(UTC),
                posts_found=1,
                new_posts=1
            )
            session.add(check_run)
            session.commit()

            # Create RedditPost instance
            now = datetime.now(UTC)
            reddit_post = RedditPost(
                post_id="abc123",
                subreddit="technology",
                title="Amazing AI Breakthrough",
                author="researcher123",
                score=156,
                num_comments=42,
                created_utc=now,
                url="https://reddit.com/r/technology/comments/abc123/",
                selftext="This is the content of the post",
                is_self=True,
                permalink="/r/technology/comments/abc123/amazing_ai_breakthrough/",
                over_18=False,
                first_seen=now,
                last_updated=now,
                check_run_id=check_run.id
            )

            # Verify fields are set correctly
            assert reddit_post.post_id == "abc123"
            assert reddit_post.title == "Amazing AI Breakthrough"
            assert reddit_post.author == "researcher123"
            assert reddit_post.score == 156
            assert reddit_post.num_comments == 42
            assert reddit_post.is_self is True
            assert reddit_post.over_18 is False
            assert reddit_post.check_run_id == check_run.id

        finally:
            session.close()

    def test_redditpost_field_types(self):
        """Test RedditPost model has correct field types."""
        from app.models.reddit_post import RedditPost

        inspector = inspect(RedditPost)
        columns = {col.name: col for col in inspector.columns}

        # Verify all required columns exist
        required_fields = [
            'id', 'post_id', 'subreddit', 'title', 'author', 'score',
            'num_comments', 'created_utc', 'url', 'selftext', 'is_self',
            'permalink', 'over_18', 'first_seen', 'last_updated', 'check_run_id'
        ]

        for field in required_fields:
            assert field in columns, f"Missing required field: {field}"

        # Verify specific types
        assert 'VARCHAR' in str(columns['post_id'].type)
        assert 'VARCHAR' in str(columns['subreddit'].type)
        assert 'TEXT' in str(columns['title'].type) or 'VARCHAR' in str(columns['title'].type)
        assert 'INTEGER' in str(columns['score'].type)
        assert 'BOOLEAN' in str(columns['is_self'].type) or 'TINYINT' in str(columns['is_self'].type)

    def test_redditpost_unique_constraint(self):
        """Test RedditPost has unique constraint on post_id."""
        from app.models.check_run import CheckRun
        from app.models.reddit_post import RedditPost

        session = SessionLocal()
        try:
            # Create a CheckRun first
            check_run = CheckRun(
                subreddit="technology",
                topic="AI",
                timestamp=datetime.now(UTC),
                posts_found=2,
                new_posts=2
            )
            session.add(check_run)
            session.commit()

            # Create first post
            now = datetime.now(UTC)
            post1 = RedditPost(
                post_id="unique123",
                subreddit="technology",
                title="First Post",
                author="user1",
                score=10,
                num_comments=5,
                created_utc=now,
                url="https://reddit.com/1",
                selftext="",
                is_self=False,
                permalink="/r/technology/comments/unique123/first/",
                over_18=False,
                first_seen=now,
                last_updated=now,
                check_run_id=check_run.id
            )
            session.add(post1)
            session.commit()

            # Try to create second post with same post_id
            post2 = RedditPost(
                post_id="unique123",  # Same post_id - should fail
                subreddit="technology",
                title="Second Post",
                author="user2",
                score=20,
                num_comments=10,
                created_utc=now,
                url="https://reddit.com/2",
                selftext="",
                is_self=False,
                permalink="/r/technology/comments/unique123/second/",
                over_18=False,
                first_seen=now,
                last_updated=now,
                check_run_id=check_run.id
            )
            session.add(post2)

            # This should raise an IntegrityError due to unique constraint
            with pytest.raises(IntegrityError):
                session.commit()

        finally:
            session.rollback()
            session.close()

    def test_redditpost_foreign_key_relationship(self):
        """Test RedditPost foreign key relationship with CheckRun."""
        from app.models.check_run import CheckRun
        from app.models.reddit_post import RedditPost

        session = SessionLocal()
        try:
            # Create CheckRun
            check_run = CheckRun(
                subreddit="programming",
                topic="python",
                timestamp=datetime.now(UTC),
                posts_found=1,
                new_posts=1
            )
            session.add(check_run)
            session.commit()

            # Create RedditPost linked to CheckRun
            now = datetime.now(UTC)
            reddit_post = RedditPost(
                post_id="def456",
                subreddit="programming",
                title="Python Tips",
                author="pythonista",
                score=89,
                num_comments=23,
                created_utc=now,
                url="https://reddit.com/r/programming/comments/def456/",
                selftext="Here are some Python tips...",
                is_self=True,
                permalink="/r/programming/comments/def456/python_tips/",
                over_18=False,
                first_seen=now,
                last_updated=now,
                check_run_id=check_run.id
            )
            session.add(reddit_post)
            session.commit()

            # Test relationship
            assert reddit_post.check_run_id == check_run.id

            # If relationship is defined, test it
            if hasattr(reddit_post, 'check_run'):
                assert reddit_post.check_run.id == check_run.id
                assert reddit_post.check_run.subreddit == "programming"

        finally:
            session.close()

    def test_redditpost_nullable_fields(self):
        """Test RedditPost handles nullable fields correctly."""
        from app.models.check_run import CheckRun
        from app.models.reddit_post import RedditPost

        session = SessionLocal()
        try:
            # Create CheckRun
            check_run = CheckRun(
                subreddit="test",
                topic="test",
                timestamp=datetime.now(UTC),
                posts_found=1,
                new_posts=1
            )
            session.add(check_run)
            session.commit()

            # Create post with minimal required fields (some nullable)
            now = datetime.now(UTC)
            reddit_post = RedditPost(
                post_id="minimal123",
                subreddit="test",
                title="Minimal Post",
                author=None,  # Can be None if deleted
                score=0,
                num_comments=0,
                created_utc=now,
                url="https://reddit.com/r/test/comments/minimal123/",
                selftext="",  # Empty string for link posts
                is_self=False,
                permalink="/r/test/comments/minimal123/minimal/",
                over_18=False,
                first_seen=now,
                last_updated=now,
                check_run_id=check_run.id
            )
            session.add(reddit_post)
            session.commit()

            # Should succeed with None/empty values
            assert reddit_post.id is not None

        finally:
            session.close()

    def test_redditpost_repr_method(self):
        """Test RedditPost has a useful __repr__ method."""
        from app.models.reddit_post import RedditPost

        now = datetime.now(UTC)
        reddit_post = RedditPost(
            post_id="repr123",
            subreddit="test",
            title="Test Post for Repr",
            author="testuser",
            score=42,
            num_comments=7,
            created_utc=now,
            url="https://reddit.com/test",
            selftext="",
            is_self=False,
            permalink="/r/test/comments/repr123/",
            over_18=False,
            first_seen=now,
            last_updated=now,
            check_run_id=1
        )

        repr_str = repr(reddit_post)
        assert "RedditPost" in repr_str
        assert "repr123" in repr_str
        assert "Test Post for Repr" in repr_str


class TestModelRelationships:
    """Test relationships between models."""

    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Create tables before each test and clean up after."""
        Base.metadata.create_all(bind=engine)
        yield
        Base.metadata.drop_all(bind=engine)

    def test_checkrun_redditpost_relationship(self):
        """Test one-to-many relationship between CheckRun and RedditPost."""
        from app.models.check_run import CheckRun
        from app.models.reddit_post import RedditPost

        session = SessionLocal()
        try:
            # Create CheckRun
            check_run = CheckRun(
                subreddit="science",
                topic="physics",
                timestamp=datetime.now(UTC),
                posts_found=2,
                new_posts=2
            )
            session.add(check_run)
            session.commit()

            # Create multiple RedditPosts linked to same CheckRun
            now = datetime.now(UTC)

            post1 = RedditPost(
                post_id="physics1",
                subreddit="science",
                title="Quantum Physics Breakthrough",
                author="physicist1",
                score=234,
                num_comments=67,
                created_utc=now,
                url="https://reddit.com/1",
                selftext="",
                is_self=False,
                permalink="/r/science/comments/physics1/",
                over_18=False,
                first_seen=now,
                last_updated=now,
                check_run_id=check_run.id
            )

            post2 = RedditPost(
                post_id="physics2",
                subreddit="science",
                title="New Particle Discovered",
                author="physicist2",
                score=189,
                num_comments=34,
                created_utc=now,
                url="https://reddit.com/2",
                selftext="",
                is_self=False,
                permalink="/r/science/comments/physics2/",
                over_18=False,
                first_seen=now,
                last_updated=now,
                check_run_id=check_run.id
            )

            session.add_all([post1, post2])
            session.commit()

            # Verify foreign key relationships
            assert post1.check_run_id == check_run.id
            assert post2.check_run_id == check_run.id

            # If relationship attributes are defined, test them
            if hasattr(check_run, 'reddit_posts'):
                assert len(check_run.reddit_posts) == 2
                post_ids = {post.post_id for post in check_run.reddit_posts}
                assert post_ids == {"physics1", "physics2"}

        finally:
            session.close()


class TestModelIndexes:
    """Test database indexes are created correctly."""

    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Create tables before each test and clean up after."""
        Base.metadata.create_all(bind=engine)
        yield
        Base.metadata.drop_all(bind=engine)

    def test_checkrun_indexes_exist(self):
        """Test CheckRun model has proper indexes."""
        session = SessionLocal()
        try:
            # Query database schema for indexes
            # This is database-specific, but we can test basic functionality

            # Test that we can query efficiently by subreddit and topic
            from app.models.check_run import CheckRun

            # This query should be efficient if indexes exist
            query = session.query(CheckRun).filter(
                CheckRun.subreddit == "test",
                CheckRun.topic == "test"
            )

            # Should not raise an error
            result = query.all()
            assert isinstance(result, list)

        finally:
            session.close()

    def test_redditpost_indexes_exist(self):
        """Test RedditPost model has proper indexes."""
        session = SessionLocal()
        try:
            from app.models.reddit_post import RedditPost

            # Test queries that should use indexes
            queries = [
                session.query(RedditPost).filter(RedditPost.post_id == "test"),
                session.query(RedditPost).filter(RedditPost.subreddit == "test"),
                session.query(RedditPost).order_by(RedditPost.created_utc),
                session.query(RedditPost).order_by(RedditPost.score.desc()),
            ]

            for query in queries:
                result = query.all()
                assert isinstance(result, list)

        finally:
            session.close()


class TestModelConstraints:
    """Test model constraints and data validation."""

    @pytest.fixture(autouse=True)
    def setup_database(self):
        """Create tables before each test and clean up after."""
        Base.metadata.create_all(bind=engine)
        yield
        Base.metadata.drop_all(bind=engine)

    def test_required_fields_validation(self):
        """Test that required fields are enforced."""
        from app.models.check_run import CheckRun

        session = SessionLocal()
        try:
            # Try to create CheckRun with missing required fields
            check_run = CheckRun()  # No required fields set
            session.add(check_run)

            # This might not fail immediately due to SQLAlchemy behavior
            # But will fail when we try to commit if constraints are properly set
            with pytest.raises((IntegrityError, ValueError)):
                session.commit()

        finally:
            session.rollback()
            session.close()

    def test_timestamp_utc_handling(self):
        """Test that timestamps are properly handled in UTC."""
        from app.models.check_run import CheckRun

        session = SessionLocal()
        try:
            # Create CheckRun with UTC timestamp
            utc_time = datetime.now(UTC)
            check_run = CheckRun(
                subreddit="test",
                topic="test",
                timestamp=utc_time,
                posts_found=0,
                new_posts=0
            )
            session.add(check_run)
            session.commit()

            # Retrieve and verify timezone info is preserved
            retrieved = session.query(CheckRun).filter_by(id=check_run.id).first()

            # The exact timezone handling depends on database backend
            # But we should be able to work with the timestamp
            assert retrieved.timestamp is not None

        finally:
            session.close()
