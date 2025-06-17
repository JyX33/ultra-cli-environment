# ABOUTME: Integration tests for complete system workflows
# ABOUTME: Tests end-to-end flows from Reddit fetch to delta report generation

from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.check_run import CheckRun
from app.models.reddit_post import RedditPost
from app.services.storage_service import StorageService
from tests.fixtures.reddit_mocks import MockRedditEnvironment, create_mock_praw_post


@pytest.fixture
def temp_db():
    """Create temporary SQLite database for testing."""
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
def client(temp_db):
    """Create FastAPI test client with temporary database."""
    SessionLocal, db_path = temp_db

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
def mock_reddit_data():
    """Mock Reddit data for testing complete workflows."""
    return {
        "posts": [
            {
                "post_id": "test_post_1",
                "id": "test_post_1",
                "title": "Test Post 1 - Breaking News",
                "selftext": "This is a test post about important news.",
                "author": "test_user_1",
                "score": 150,
                "num_comments": 25,
                "url": "https://example.com/article1",
                "permalink": "/r/test/comments/test_post_1/",
                "created_utc": datetime.now(UTC).timestamp(),
                "upvote_ratio": 0.85,
                "subreddit": "test",
                "is_self": True,
                "over_18": False,
                "check_run_id": 1
            },
            {
                "post_id": "test_post_2",
                "id": "test_post_2",
                "title": "Test Post 2 - Analysis",
                "selftext": "Detailed analysis of recent events.",
                "author": "test_user_2",
                "score": 89,
                "num_comments": 12,
                "url": "https://example.com/article2",
                "permalink": "/r/test/comments/test_post_2/",
                "created_utc": datetime.now(UTC).timestamp(),
                "upvote_ratio": 0.78,
                "subreddit": "test",
                "is_self": True,
                "over_18": False,
                "check_run_id": 1
            }
        ],
        "comments": [
            {
                "id": "comment_1",
                "body": "Great analysis! Really insightful.",
                "author": "commenter_1",
                "score": 15,
                "parent_id": "test_post_1",
                "created_utc": (datetime.now(UTC) - timedelta(seconds=1800)).timestamp()
            },
            {
                "id": "comment_2",
                "body": "I agree with the main points made here.",
                "author": "commenter_2",
                "score": 8,
                "parent_id": "test_post_1",
                "created_utc": (datetime.now(UTC) - timedelta(seconds=900)).timestamp()
            }
        ]
    }


@pytest.fixture
def mock_reddit_service():
    """Mock RedditService for testing."""
    service = MagicMock()
    service.get_posts.return_value = []
    service.get_relevant_posts_optimized.return_value = []
    service.get_comments.return_value = []
    service.get_top_comments.return_value = []
    service.search_subreddits.return_value = []
    return service


@pytest.fixture
def mock_scraper_service():
    """Mock scraper service for testing."""
    return MagicMock(return_value="Scraped article content for testing.")


@pytest.fixture
def mock_summarizer_service():
    """Mock summarizer service for testing."""
    return MagicMock(return_value="AI-generated summary of the content.")


class TestCompleteWorkflow:
    """Test complete system workflows from fetch to report generation."""

    def test_first_time_check_workflow(
        self,
        client,
        mock_reddit_data,
        mock_reddit_service,
        mock_scraper_service,
        mock_summarizer_service
    ):
        """Test complete workflow for first-time subreddit check."""
        test_client, SessionLocal = client

        # Create mock post objects with proper structure
        mock_posts = []
        for post_data in mock_reddit_data["posts"]:
            mock_post = MagicMock()
            mock_post.id = post_data["post_id"]
            mock_post.title = post_data["title"]
            mock_post.selftext = post_data["selftext"]
            # Set author as a simple string-convertible object
            mock_author = MagicMock()
            mock_author.return_value = post_data["author"]
            mock_author.__str__ = MagicMock(return_value=post_data["author"])
            mock_post.author = mock_author
            mock_post.score = post_data["score"]
            mock_post.num_comments = post_data["num_comments"]
            mock_post.url = post_data["url"]
            mock_post.permalink = post_data["permalink"]
            mock_post.created_utc = post_data["created_utc"]
            mock_post.upvote_ratio = post_data["upvote_ratio"]
            mock_post.is_self = True
            mock_post.over_18 = False
            mock_post.spoiler = False
            mock_post.subreddit = MagicMock()
            mock_post.subreddit.display_name = post_data["subreddit"]

            # Mock comments structure
            mock_post.comments = MagicMock()
            mock_post.comments.replace_more = MagicMock()
            mock_post.comments.list = MagicMock(return_value=[])

            mock_posts.append(mock_post)

        # Convert mock data to the format expected by integration
        mock_reddit_data["posts"]

        with patch('app.main.reddit_service.get_relevant_posts_optimized', return_value=mock_posts), \
             patch('app.main.scrape_article_text', mock_scraper_service), \
             patch('app.main.summarize_content', mock_summarizer_service):

            # Execute first check
            response = test_client.get("/check-updates/test/technology")

            assert response.status_code == 200
            data = response.json()

            # Verify response structure
            assert "new_posts" in data
            assert "updated_posts" in data
            assert "new_comments" in data
            assert "summary" in data

            # First check should find all posts as new
            assert len(data["new_posts"]) == 2
            assert len(data["updated_posts"]) == 0

            # Verify data was stored in database
            session = SessionLocal()
            try:
                storage_service = StorageService(session)

                # Check that check run was created
                check_run = storage_service.get_latest_check_run("test", "technology")
                assert check_run is not None
                assert check_run.posts_found == 2

                # Check that posts were stored
                for post_data in mock_reddit_data["posts"]:
                    stored_post = storage_service.get_post_by_id(post_data["post_id"])
                    assert stored_post is not None
                    assert stored_post.title == post_data["title"]
                    assert stored_post.score == post_data["score"]

            finally:
                session.close()

    def test_subsequent_check_with_changes(
        self,
        client,
        mock_reddit_data,
        mock_reddit_service,
        mock_scraper_service,
        mock_summarizer_service
    ):
        """Test workflow for subsequent check with post changes."""
        test_client, SessionLocal = client

        # Setup initial data
        session = SessionLocal()
        try:
            storage_service = StorageService(session)

            # Create initial check run and store posts
            check_run_id = storage_service.create_check_run("test", "technology")

            for post_data in mock_reddit_data["posts"]:
                # Convert timestamp to datetime for storage service
                post_data_copy = post_data.copy()
                post_data_copy["created_utc"] = datetime.fromtimestamp(post_data["created_utc"], UTC)
                post_data_copy["check_run_id"] = check_run_id
                storage_service.save_post(post_data_copy)

            session.commit()

        finally:
            session.close()

        # Create updated mock post objects for second check (simulate score changes)
        updated_mock_posts = []
        for i, post_data in enumerate(mock_reddit_data["posts"]):
            mock_post = MagicMock()
            mock_post.id = post_data["post_id"]
            mock_post.title = post_data["title"]
            mock_post.selftext = post_data["selftext"]
            # Set author as a simple string-convertible object
            mock_author = MagicMock()
            mock_author.return_value = post_data["author"]
            mock_author.__str__ = MagicMock(return_value=post_data["author"])
            mock_post.author = mock_author

            # Apply score changes for simulation
            if i == 0:  # First post
                mock_post.score = 200  # Score increased
                mock_post.num_comments = 35  # Comments increased
            elif i == 1:  # Second post
                mock_post.score = 75  # Score decreased
                mock_post.num_comments = post_data["num_comments"]
            else:
                mock_post.score = post_data["score"]
                mock_post.num_comments = post_data["num_comments"]

            mock_post.url = post_data["url"]
            mock_post.permalink = post_data["permalink"]
            mock_post.created_utc = post_data["created_utc"]
            mock_post.upvote_ratio = post_data["upvote_ratio"]
            mock_post.is_self = True
            mock_post.over_18 = False
            mock_post.spoiler = False
            mock_post.stickied = False
            mock_post.subreddit = MagicMock()
            mock_post.subreddit.display_name = post_data["subreddit"]

            # Mock comments structure
            mock_post.comments = MagicMock()
            mock_post.comments.replace_more = MagicMock()
            mock_post.comments.list = MagicMock(return_value=[])

            updated_mock_posts.append(mock_post)

        with patch('app.main.reddit_service.get_relevant_posts_optimized', return_value=updated_mock_posts), \
             patch('app.main.reddit_service.get_top_comments', return_value=mock_reddit_data["comments"]), \
             patch('app.main.scrape_article_text', mock_scraper_service), \
             patch('app.main.summarize_content', mock_summarizer_service):

            # Execute second check
            response = test_client.get("/check-updates/test/technology")

            assert response.status_code == 200
            data = response.json()

            # Should find no new posts but updates to existing ones
            assert len(data["new_posts"]) == 0
            assert len(data["updated_posts"]) == 2

            # Verify engagement deltas
            for update in data["updated_posts"]:
                if update["post_id"] == "test_post_1":
                    assert update["engagement_delta"]["score_delta"] == 50
                    assert update["engagement_delta"]["comments_delta"] == 10
                elif update["post_id"] == "test_post_2":
                    assert update["engagement_delta"]["score_delta"] == -14

    def test_multiple_subreddit_tracking(
        self,
        client,
        mock_reddit_service,
        mock_scraper_service,
        mock_summarizer_service
    ):
        """Test tracking multiple subreddits independently."""
        test_client, SessionLocal = client

        # Create mock post objects for different subreddits
        def create_mock_post(post_id, title, selftext, author, score, num_comments, url, permalink, subreddit):
            mock_post = MagicMock()
            mock_post.id = post_id
            mock_post.title = title
            mock_post.selftext = selftext
            # Set author as a simple string-convertible object
            mock_author = MagicMock()
            mock_author.return_value = author
            mock_author.__str__ = MagicMock(return_value=author)
            mock_post.author = mock_author
            mock_post.score = score
            mock_post.num_comments = num_comments
            mock_post.url = url
            mock_post.permalink = permalink
            mock_post.created_utc = datetime.now(UTC).timestamp()
            mock_post.upvote_ratio = 0.85
            mock_post.is_self = True
            mock_post.over_18 = False
            mock_post.spoiler = False
            mock_post.stickied = False
            mock_post.subreddit = MagicMock()
            mock_post.subreddit.display_name = subreddit

            # Mock comments structure
            mock_post.comments = MagicMock()
            mock_post.comments.replace_more = MagicMock()
            mock_post.comments.list = MagicMock(return_value=[])

            return mock_post

        tech_posts = [create_mock_post(
            "tech_post_1", "Tech News", "Technology content", "tech_user",
            100, 15, "https://example.com/tech", "/r/technology/comments/tech_post_1/", "technology"
        )]

        science_posts = [create_mock_post(
            "science_post_1", "Science Discovery", "Science content", "science_user",
            200, 25, "https://example.com/science", "/r/science/comments/science_post_1/", "science"
        )]

        with patch('app.main.reddit_service.get_relevant_posts_optimized') as mock_posts, \
             patch('app.main.reddit_service.get_top_comments', return_value=[]), \
             patch('app.main.scrape_article_text', mock_scraper_service), \
             patch('app.main.summarize_content', mock_summarizer_service):

            # Check technology subreddit
            mock_posts.return_value = tech_posts

            tech_response = test_client.get("/check-updates/technology/ai")
            assert tech_response.status_code == 200
            tech_data = tech_response.json()

            # Check science subreddit
            mock_posts.return_value = science_posts

            science_response = test_client.get("/check-updates/science/research")
            assert science_response.status_code == 200
            science_data = science_response.json()

            # Verify independent tracking
            assert len(tech_data["new_posts"]) == 1
            assert len(science_data["new_posts"]) == 1
            assert tech_data["new_posts"][0]["post_id"] == "tech_post_1"
            assert science_data["new_posts"][0]["post_id"] == "science_post_1"

            # Verify separate storage
            session = SessionLocal()
            try:
                storage_service = StorageService(session)

                tech_check = storage_service.get_latest_check_run("technology", "ai")
                science_check = storage_service.get_latest_check_run("science", "research")

                assert tech_check is not None
                assert science_check is not None
                assert tech_check.id != science_check.id

            finally:
                session.close()

    def test_generate_report_with_storage(
        self,
        client,
        mock_reddit_data,
        mock_reddit_service,
        mock_scraper_service,
        mock_summarizer_service
    ):
        """Test report generation with data storage enabled."""
        test_client, SessionLocal = client

        # Create standardized test post data
        test_post_data = {
            "id": "report_post_1",
            "title": "Report Test Post",
            "selftext": "Content for report testing",
            "author": "report_user",
            "score": 75,
            "num_comments": 10,
            "url": "https://example.com/report",
            "permalink": "/r/test/comments/report_post_1/",
            "created_utc": datetime.now(UTC).timestamp() - 3600,
            "upvote_ratio": 0.80,
            "subreddit": "test"
        }

        # Create proper PRAW-like mock post
        mock_post = create_mock_praw_post(test_post_data)
        mock_posts = [mock_post]

        # Create mock Reddit service
        reddit_service_mock = MagicMock()
        reddit_service_mock.get_relevant_posts_optimized.return_value = mock_posts

        # Create mock external services
        external_services_mock = {
            'scraper': MagicMock(return_value="Scraped article content"),
            'summarizer': MagicMock(return_value="Test summary")
        }

        # Use the centralized mocking environment
        with MockRedditEnvironment(reddit_service_mock, external_services_mock):
            # Generate report with storage enabled
            response = test_client.get(
                "/generate-report/test/technology?store_data=true&include_history=false"
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "text/markdown; charset=utf-8"

            # Verify data was stored during report generation
            session = SessionLocal()
            try:
                storage_service = StorageService(session)

                # Check that a check run was created
                check_run = storage_service.get_latest_check_run("test", "technology")
                assert check_run is not None

                # Check that the post was stored with the correct ID
                stored_post = storage_service.get_post_by_id("report_post_1")
                assert stored_post is not None, "Post with ID 'report_post_1' not found in database"
                assert stored_post.title == "Report Test Post"

            finally:
                session.close()

    def test_error_recovery_workflow(
        self,
        client,
        mock_reddit_service
    ):
        """Test system behavior when services fail."""
        test_client, SessionLocal = client

        # Test Reddit service failure
        mock_reddit_service.get_relevant_posts_optimized.side_effect = Exception("Reddit API Error")

        with patch('app.main.reddit_service', mock_reddit_service):
            response = test_client.get("/check-updates/test/technology")

            # Should handle error gracefully - either 500 or 200 with error message
            assert response.status_code in [200, 500]

        # Test successful recovery after error
        mock_reddit_service.get_relevant_posts_optimized.side_effect = None  # Reset side effect
        mock_reddit_service.get_relevant_posts_optimized.return_value = []

        with patch('app.main.reddit_service', mock_reddit_service):
            response = test_client.get("/check-updates/test/technology")

            # Should recover and process successfully
            assert response.status_code == 200
            data = response.json()
            assert "new_posts" in data
            assert "updated_posts" in data

    def test_data_consistency_across_requests(
        self,
        client,
        mock_reddit_data,
        mock_reddit_service,
        mock_scraper_service,
        mock_summarizer_service
    ):
        """Test data consistency when making multiple requests."""
        test_client, SessionLocal = client

        # Create mock post objects from the mock data
        mock_posts = []
        for post_data in mock_reddit_data["posts"]:
            mock_post = MagicMock()
            mock_post.id = post_data["post_id"]
            mock_post.title = post_data["title"]
            mock_post.selftext = post_data["selftext"]
            # Set author as a simple string-convertible object
            mock_author = MagicMock()
            mock_author.return_value = post_data["author"]
            mock_author.__str__ = MagicMock(return_value=post_data["author"])
            mock_post.author = mock_author
            mock_post.score = post_data["score"]
            mock_post.num_comments = post_data["num_comments"]
            mock_post.url = post_data["url"]
            mock_post.permalink = post_data["permalink"]
            mock_post.created_utc = post_data["created_utc"]
            mock_post.upvote_ratio = post_data["upvote_ratio"]
            mock_post.is_self = True
            mock_post.over_18 = False
            mock_post.spoiler = False
            mock_post.stickied = False
            mock_post.subreddit = MagicMock()
            mock_post.subreddit.display_name = post_data["subreddit"]

            # Mock comments structure
            mock_post.comments = MagicMock()
            mock_post.comments.replace_more = MagicMock()
            mock_post.comments.list = MagicMock(return_value=[])

            mock_posts.append(mock_post)

        with patch('app.main.reddit_service.get_relevant_posts_optimized', return_value=mock_posts), \
             patch('app.main.reddit_service.get_top_comments', return_value=mock_reddit_data["comments"]), \
             patch('app.main.scrape_article_text', mock_scraper_service), \
             patch('app.main.summarize_content', mock_summarizer_service):

            # Make multiple requests to same endpoint
            responses = []
            for _ in range(3):
                response = test_client.get("/check-updates/test/technology")
                assert response.status_code == 200
                responses.append(response.json())

            # First request should find new posts
            assert len(responses[0]["new_posts"]) == 2

            # Subsequent requests should find no new posts (consistency)
            assert len(responses[1]["new_posts"]) == 0
            assert len(responses[2]["new_posts"]) == 0

            # Verify data consistency in database
            session = SessionLocal()
            try:
                StorageService(session)

                all_posts = session.query(RedditPost).all()
                assert len(all_posts) == 2  # Should not duplicate posts

                all_check_runs = session.query(CheckRun).all()
                assert len(all_check_runs) == 3  # One for each request

            finally:
                session.close()
