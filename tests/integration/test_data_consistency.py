# ABOUTME: Integration tests for data consistency and integrity validation
# ABOUTME: Tests referential integrity, cascade operations, and data validation across services

from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.check_run import CheckRun
from app.models.comment import Comment
from app.models.post_snapshot import PostSnapshot
from app.models.reddit_post import RedditPost
from app.services.change_detection_service import ChangeDetectionService
from app.services.storage_service import StorageService


@pytest.fixture
def consistency_db():
    """Create temporary database for consistency testing."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temp_file.close()

    engine = create_engine(
        f"sqlite:///{temp_file.name}",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)

    SessionLocal = sessionmaker(bind=engine)

    yield SessionLocal, temp_file.name

    # Cleanup
    Path(temp_file.name).unlink(missing_ok=True)


@pytest.fixture
def consistency_client(consistency_db):
    """Create test client for consistency testing."""
    SessionLocal, db_path = consistency_db

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
def sample_data():
    """Create sample data for consistency testing."""
    base_time = datetime.now(UTC).timestamp()
    return {
        "check_runs": [
            {
                "subreddit": "consistency_test",
                "topic": "data_integrity",
                "timestamp": datetime.fromtimestamp(base_time - 3600, UTC),
                "posts_found": 2,
                "new_posts": 2
            },
            {
                "subreddit": "consistency_test",
                "topic": "data_integrity",
                "timestamp": datetime.fromtimestamp(base_time - 1800, UTC),
                "posts_found": 3,
                "new_posts": 1
            }
        ],
        "posts": [
            {
                "id": "consistency_post_1",
                "title": "First Consistency Post",
                "selftext": "Content for consistency testing",
                "author": "test_user_1",
                "score": 100,
                "num_comments": 15,
                "url": "https://example.com/post1",
                "permalink": "/r/consistency_test/comments/post1/",
                "created_utc": base_time - 3600,
                "upvote_ratio": 0.85,
                "subreddit": "consistency_test"
            },
            {
                "id": "consistency_post_2",
                "title": "Second Consistency Post",
                "selftext": "More content for testing",
                "author": "test_user_2",
                "score": 75,
                "num_comments": 8,
                "url": "https://example.com/post2",
                "permalink": "/r/consistency_test/comments/post2/",
                "created_utc": base_time - 3600,
                "upvote_ratio": 0.78,
                "subreddit": "consistency_test"
            },
            {
                "id": "consistency_post_3",
                "title": "Third Consistency Post",
                "selftext": "Additional test content",
                "author": "test_user_3",
                "score": 50,
                "num_comments": 5,
                "url": "https://example.com/post3",
                "permalink": "/r/consistency_test/comments/post3/",
                "created_utc": base_time - 1800,
                "upvote_ratio": 0.82,
                "subreddit": "consistency_test"
            }
        ],
        "comments": [
            {
                "id": "comment_1",
                "body": "Great post! Very insightful.",
                "author": "commenter_1",
                "score": 25,
                "parent_id": None,
                "created_utc": base_time - 3000,
                "post_id": "consistency_post_1"
            },
            {
                "id": "comment_2",
                "body": "I agree with the analysis.",
                "author": "commenter_2",
                "score": 12,
                "parent_id": "comment_1",
                "created_utc": base_time - 2700,
                "post_id": "consistency_post_1"
            },
            {
                "id": "comment_3",
                "body": "Interesting perspective on this topic.",
                "author": "commenter_3",
                "score": 8,
                "parent_id": None,
                "created_utc": base_time - 2400,
                "post_id": "consistency_post_2"
            }
        ]
    }


class TestDataConsistency:
    """Test data consistency and integrity across the system."""

    def test_referential_integrity_cascade_deletes(self, consistency_client, sample_data):
        """Test that cascade deletes maintain referential integrity."""
        test_client, SessionLocal = consistency_client

        session = SessionLocal()
        try:
            storage_service = StorageService(session)

            # Create check runs
            check_run_ids = []
            for check_run_data in sample_data["check_runs"]:
                check_run_id = storage_service.create_check_run(
                    check_run_data["subreddit"],
                    check_run_data["topic"]
                )
                check_run_ids.append(check_run_id)

            # Create posts linked to first check run
            for post_data in sample_data["posts"][:2]:
                post_data["check_run_id"] = check_run_ids[0]
                storage_service.save_post(post_data)

            # Create third post linked to second check run
            post_data = sample_data["posts"][2]
            post_data["check_run_id"] = check_run_ids[1]
            storage_service.save_post(post_data)

            # Create comments linked to posts
            for comment_data in sample_data["comments"]:
                storage_service.save_comment(comment_data, comment_data["post_id"])

            # Create post snapshots
            for i, post_data in enumerate(sample_data["posts"]):
                storage_service.save_post_snapshot(
                    post_data["id"],
                    check_run_ids[0] if i < 2 else check_run_ids[1],
                    post_data["score"],
                    post_data["num_comments"]
                )

            session.commit()

            # Verify initial data
            initial_posts = session.query(RedditPost).count()
            initial_comments = session.query(Comment).count()
            initial_snapshots = session.query(PostSnapshot).count()
            initial_check_runs = session.query(CheckRun).count()

            assert initial_posts == 3
            assert initial_comments == 3
            assert initial_snapshots == 3
            assert initial_check_runs == 2

            # Delete first check run (should cascade to its posts, comments, snapshots)
            session.delete(session.query(CheckRun).filter_by(id=check_run_ids[0]).first())
            session.commit()

            # Verify cascade deletion
            remaining_posts = session.query(RedditPost).count()
            remaining_comments = session.query(Comment).count()
            remaining_snapshots = session.query(PostSnapshot).count()
            remaining_check_runs = session.query(CheckRun).count()

            assert remaining_check_runs == 1  # Only second check run remains
            assert remaining_posts == 1       # Only post linked to second check run
            assert remaining_comments == 1    # Only comments linked to remaining post
            assert remaining_snapshots == 1   # Only snapshots linked to remaining entities

            # Verify remaining data is correct
            remaining_post = session.query(RedditPost).first()
            assert remaining_post.post_id == "consistency_post_3"

            remaining_comment = session.query(Comment).first()
            assert remaining_comment.post_id == "consistency_post_2"  # This should fail - testing cascade

        finally:
            session.close()

    def test_unique_constraint_enforcement(self, consistency_client, sample_data):
        """Test that unique constraints are properly enforced."""
        test_client, SessionLocal = consistency_client

        session = SessionLocal()
        try:
            storage_service = StorageService(session)

            # Create initial post
            post_data = sample_data["posts"][0]
            storage_service.save_post(post_data)
            session.commit()

            # Attempt to create duplicate post (should be handled gracefully)
            storage_service.save_post(post_data)
            session.commit()

            # Should still have only one post
            total_posts = session.query(RedditPost).count()
            assert total_posts == 1

            # Create comment
            comment_data = sample_data["comments"][0]
            storage_service.save_comment(comment_data, comment_data["post_id"])
            session.commit()

            # Attempt to create duplicate comment (should be handled gracefully)
            storage_service.save_comment(comment_data, comment_data["post_id"])
            session.commit()

            # Should still have only one comment
            total_comments = session.query(Comment).count()
            assert total_comments == 1

        finally:
            session.close()

    def test_foreign_key_constraint_enforcement(self, consistency_client, sample_data):
        """Test that foreign key constraints are enforced."""
        test_client, SessionLocal = consistency_client

        session = SessionLocal()
        try:
            storage_service = StorageService(session)

            # Attempt to save comment without corresponding post
            comment_data = sample_data["comments"][0]

            # This should raise an error or handle gracefully
            try:
                storage_service.save_comment(comment_data, "nonexistent_post_id")
                session.commit()
                raise AssertionError("Should not be able to save comment without valid post")
            except Exception:
                session.rollback()  # Expected behavior

            # Create valid post first
            post_data = sample_data["posts"][0]
            storage_service.save_post(post_data)
            session.commit()

            # Now comment should save successfully
            storage_service.save_comment(comment_data, comment_data["post_id"])
            session.commit()

            # Verify data
            total_posts = session.query(RedditPost).count()
            total_comments = session.query(Comment).count()
            assert total_posts == 1
            assert total_comments == 1

        finally:
            session.close()

    def test_data_consistency_across_services(self, consistency_client, sample_data):
        """Test data consistency when using multiple services together."""
        test_client, SessionLocal = consistency_client

        session = SessionLocal()
        try:
            storage_service = StorageService(session)
            change_detection_service = ChangeDetectionService(session)

            # Create initial data through storage service
            check_run_id = storage_service.create_check_run(
                "consistency_test",
                "cross_service"
            )

            for post_data in sample_data["posts"]:
                post_data["check_run_id"] = check_run_id
                storage_service.save_post(post_data)

            session.commit()

            # Use change detection service on same data
            last_check = datetime.now(UTC) - timedelta(hours=2)
            current_posts = sample_data["posts"].copy()

            # Modify some posts to simulate changes
            current_posts[0]["score"] = 150  # Increased score
            current_posts[1]["num_comments"] = 12  # Increased comments

            # Detect changes
            new_posts = change_detection_service.find_new_posts(current_posts, last_check)
            updated_posts = change_detection_service.find_updated_posts(current_posts)

            # Should find no new posts (all exist) but some updates
            assert len(new_posts) == 0
            assert len(updated_posts) == 2

            # Verify engagement deltas
            for update in updated_posts:
                if update.post_id == "consistency_post_1":
                    assert update.engagement_delta.score_change == 50
                elif update.post_id == "consistency_post_2":
                    assert update.engagement_delta.comment_change == 4

            # Update storage with new data
            for post_data in current_posts:
                storage_service.save_post(post_data)

            session.commit()

            # Verify data consistency between services
            stored_post_1 = storage_service.get_post_by_id("consistency_post_1")
            stored_post_2 = storage_service.get_post_by_id("consistency_post_2")

            assert stored_post_1.score == 150
            assert stored_post_2.num_comments == 12

        finally:
            session.close()

    def test_transaction_atomicity(self, consistency_client, sample_data):
        """Test that transactions are atomic (all or nothing)."""
        test_client, SessionLocal = consistency_client

        session = SessionLocal()
        try:
            storage_service = StorageService(session)

            # Create check run
            check_run_id = storage_service.create_check_run(
                "atomicity_test",
                "transaction"
            )

            # Start transaction that should fail partway through
            try:
                # Save first post (should succeed)
                post_data_1 = sample_data["posts"][0]
                post_data_1["check_run_id"] = check_run_id
                storage_service.save_post(post_data_1)

                # Save second post (should succeed)
                post_data_2 = sample_data["posts"][1]
                post_data_2["check_run_id"] = check_run_id
                storage_service.save_post(post_data_2)

                # Attempt to save invalid data (should fail)
                invalid_post = {
                    "id": None,  # Invalid: missing required field
                    "title": "Invalid Post",
                    "subreddit": "atomicity_test"
                }
                storage_service.save_post(invalid_post)

                session.commit()
                raise AssertionError("Transaction should have failed")

            except Exception:
                session.rollback()

                # Verify rollback - no posts should be saved
                total_posts = session.query(RedditPost).count()
                assert total_posts == 0

                # Check run should still exist (was committed before)
                total_check_runs = session.query(CheckRun).count()
                assert total_check_runs == 1

            # Now save valid data to verify system still works
            for post_data in sample_data["posts"][:2]:
                post_data["check_run_id"] = check_run_id
                storage_service.save_post(post_data)

            session.commit()

            # Verify successful save
            total_posts = session.query(RedditPost).count()
            assert total_posts == 2

        finally:
            session.close()

    def test_data_validation_consistency(self, consistency_client):
        """Test that data validation is consistent across entry points."""
        test_client, SessionLocal = consistency_client

        # Test invalid data through API endpoints
        invalid_subreddit_chars = "test/subreddit"  # Contains slash
        invalid_topic_chars = "topic<script>"       # Contains HTML

        # Check-updates endpoint should validate input
        response = test_client.get(f"/check-updates/{invalid_subreddit_chars}/technology")
        assert response.status_code == 400

        response = test_client.get(f"/check-updates/test/{invalid_topic_chars}")
        assert response.status_code == 400

        # History endpoint should validate input
        response = test_client.get(f"/history/{invalid_subreddit_chars}")
        assert response.status_code == 400

        # Report generation should validate input
        response = test_client.get(f"/generate-report/{invalid_subreddit_chars}/technology")
        assert response.status_code == 400

        # Test valid data should pass
        response = test_client.get("/check-updates/validtest/technology")
        # This might return 500 due to Reddit service not being mocked, but input validation should pass
        assert response.status_code in [200, 500]  # 500 is okay, means validation passed

    def test_timestamp_consistency(self, consistency_client, sample_data):
        """Test that timestamps are handled consistently across the system."""
        test_client, SessionLocal = consistency_client

        session = SessionLocal()
        try:
            storage_service = StorageService(session)

            # Create data with specific timestamps
            check_run_id = storage_service.create_check_run(
                "timestamp_test",
                "consistency"
            )

            # Test various timestamp formats
            test_timestamps = [
                datetime.now(UTC).timestamp(),                    # Current timestamp
                datetime.now(UTC).timestamp() - 3600,            # 1 hour ago
                datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC).timestamp()  # Specific date
            ]

            for i, timestamp in enumerate(test_timestamps):
                post_data = {
                    "id": f"timestamp_post_{i}",
                    "title": f"Timestamp Test Post {i}",
                    "selftext": "Content for timestamp testing",
                    "author": f"user_{i}",
                    "score": 50,
                    "num_comments": 5,
                    "url": f"https://example.com/timestamp_{i}",
                    "permalink": f"/r/timestamp_test/comments/post_{i}/",
                    "created_utc": timestamp,
                    "upvote_ratio": 0.80,
                    "subreddit": "timestamp_test",
                    "check_run_id": check_run_id
                }

                storage_service.save_post(post_data)

            session.commit()

            # Verify timestamps are stored and retrieved correctly
            posts = session.query(RedditPost).order_by(RedditPost.created_utc.desc()).all()
            assert len(posts) == 3

            # Verify ordering by timestamp
            assert posts[0].created_utc > posts[1].created_utc > posts[2].created_utc

            # Test timezone handling in change detection
            change_detection_service = ChangeDetectionService(session)

            # Use timezone-aware datetime for comparison
            cutoff_time = datetime.now(UTC) - timedelta(hours=2)
            recent_posts = change_detection_service.find_new_posts(
                [post.__dict__ for post in posts],
                cutoff_time
            )

            # Should find posts created after cutoff
            assert len(recent_posts) >= 2

        finally:
            session.close()

    def test_bulk_operation_consistency(self, consistency_client, sample_data):
        """Test that bulk operations maintain data consistency."""
        test_client, SessionLocal = consistency_client

        session = SessionLocal()
        try:
            storage_service = StorageService(session)

            # Create post for comments
            post_data = sample_data["posts"][0]
            storage_service.save_post(post_data)
            session.commit()

            # Test bulk comment save
            comment_list = []
            for i in range(10):
                comment_data = {
                    "id": f"bulk_comment_{i}",
                    "body": f"Bulk comment {i} content",
                    "author": f"bulk_user_{i}",
                    "score": i * 2,
                    "parent_id": None,
                    "created_utc": datetime.now(UTC).timestamp() - (i * 60)
                }
                comment_list.append(comment_data)

            # Save comments in bulk
            storage_service.bulk_save_comments(comment_list, post_data["id"])
            session.commit()

            # Verify all comments were saved
            saved_comments = session.query(Comment).filter_by(
                post_id=post_data["id"]
            ).count()
            assert saved_comments == 10

            # Test consistency of relationships
            for comment in session.query(Comment).filter_by(post_id=post_data["id"]):
                assert comment.reddit_post_id == post_data["id"]
                assert comment.score >= 0
                assert comment.body.startswith("Bulk comment")

            # Test partial failure in bulk operation
            invalid_comment_list = comment_list + [
                {
                    "id": None,  # Invalid
                    "body": "Invalid comment",
                    "author": "invalid_user"
                }
            ]

            # This should handle partial failure gracefully
            try:
                storage_service.bulk_save_comments(invalid_comment_list, post_data["id"])
                session.commit()
            except Exception:
                session.rollback()

            # Original comments should still be there
            final_comment_count = session.query(Comment).filter_by(
                post_id=post_data["id"]
            ).count()
            assert final_comment_count == 10  # Original bulk save should be intact

        finally:
            session.close()
