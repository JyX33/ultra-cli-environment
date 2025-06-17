# ABOUTME: Centralized Reddit API mock fixtures for consistent testing across all test suites
# ABOUTME: Provides standardized mock data structures and reddit service mocks to eliminate real API calls

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_reddit_post_data():
    """Standard mock Reddit post data structure."""
    base_time = datetime.now(UTC).timestamp()

    return {
        "id": "test_post_1",
        "title": "Test Post Title",
        "selftext": "This is test post content for testing purposes.",
        "author": "test_user",
        "score": 100,
        "num_comments": 15,
        "url": "https://reddit.com/r/test/comments/test_post_1/",
        "permalink": "/r/test/comments/test_post_1/test_post_title/",
        "created_utc": base_time - 3600,  # 1 hour ago
        "upvote_ratio": 0.85,
        "is_self": True,
        "over_18": False,
        "spoiler": False,
        "stickied": False,
        "subreddit": "test"
    }


@pytest.fixture
def mock_reddit_comment_data():
    """Standard mock Reddit comment data structure."""
    base_time = datetime.now(UTC).timestamp()

    return [
        {
            "id": "comment_1",
            "author": "commenter_1",
            "body": "Great analysis! Really insightful.",
            "score": 25,
            "created_utc": base_time - 3000,
            "parent_id": None,
            "is_submitter": False,
            "stickied": False,
            "distinguished": None
        },
        {
            "id": "comment_2",
            "author": "commenter_2",
            "body": "I agree with this perspective on the topic.",
            "score": 18,
            "created_utc": base_time - 2700,
            "parent_id": None,
            "is_submitter": False,
            "stickied": False,
            "distinguished": None
        }
    ]


@pytest.fixture
def mock_reddit_posts_list(mock_reddit_post_data):
    """Create a list of mock Reddit posts with varying data."""
    base_post = mock_reddit_post_data.copy()
    posts = []

    for i in range(3):
        post = base_post.copy()
        post["id"] = f"test_post_{i+1}"
        post["title"] = f"Test Post {i+1}"
        post["score"] = 100 - (i * 10)
        post["num_comments"] = 15 - (i * 2)
        post["created_utc"] = post["created_utc"] - (i * 1800)  # 30 mins apart
        posts.append(post)

    return posts


def create_mock_praw_post(post_data: dict[str, Any]) -> MagicMock:
    """Create a mock PRAW post object with proper structure."""
    mock_post = MagicMock()

    # Basic post attributes
    mock_post.id = post_data["id"]
    mock_post.title = post_data["title"]
    mock_post.selftext = post_data.get("selftext", "")
    mock_post.score = post_data["score"]
    mock_post.num_comments = post_data["num_comments"]
    mock_post.url = post_data["url"]
    mock_post.permalink = post_data["permalink"]
    mock_post.created_utc = post_data["created_utc"]
    mock_post.upvote_ratio = post_data.get("upvote_ratio", 0.8)
    mock_post.is_self = post_data.get("is_self", True)
    mock_post.over_18 = post_data.get("over_18", False)
    mock_post.spoiler = post_data.get("spoiler", False)
    mock_post.stickied = post_data.get("stickied", False)

    # Mock author object
    mock_author = MagicMock()
    mock_author.name = post_data["author"]
    mock_author.__str__ = MagicMock(return_value=post_data["author"])
    mock_post.author = mock_author

    # Mock subreddit object
    mock_subreddit = MagicMock()
    mock_subreddit.display_name = post_data["subreddit"]
    mock_post.subreddit = mock_subreddit

    # Mock comments structure
    mock_post.comments = MagicMock()
    mock_post.comments.replace_more = MagicMock()
    mock_post.comments.list = MagicMock(return_value=[])

    return mock_post


def create_mock_praw_comment(comment_data: dict[str, Any]) -> MagicMock:
    """Create a mock PRAW comment object with proper structure."""
    mock_comment = MagicMock()

    mock_comment.id = comment_data["id"]
    mock_comment.body = comment_data["body"]
    mock_comment.score = comment_data["score"]
    mock_comment.created_utc = comment_data["created_utc"]
    mock_comment.parent_id = comment_data.get("parent_id")
    mock_comment.is_submitter = comment_data.get("is_submitter", False)
    mock_comment.stickied = comment_data.get("stickied", False)
    mock_comment.distinguished = comment_data.get("distinguished")

    # Mock author object
    mock_author = MagicMock()
    mock_author.name = comment_data["author"]
    mock_author.__str__ = MagicMock(return_value=comment_data["author"])
    mock_comment.author = mock_author

    return mock_comment


@pytest.fixture
def mock_praw_posts(mock_reddit_posts_list):
    """Create mock PRAW post objects from post data."""
    return [create_mock_praw_post(post_data) for post_data in mock_reddit_posts_list]


@pytest.fixture
def mock_praw_comments(mock_reddit_comment_data):
    """Create mock PRAW comment objects from comment data."""
    return [create_mock_praw_comment(comment_data) for comment_data in mock_reddit_comment_data]


@pytest.fixture
def mock_reddit_service():
    """Mock Reddit service with consistent return values."""
    mock_service = MagicMock()

    # Mock service methods with standard returns
    mock_service.get_relevant_posts_optimized.return_value = []
    mock_service.get_hot_posts.return_value = []
    mock_service.search_subreddits.return_value = []
    mock_service.get_top_comments.return_value = []

    return mock_service


@pytest.fixture
def mock_reddit_service_with_data(mock_praw_posts, mock_praw_comments):
    """Mock Reddit service pre-populated with test data."""
    mock_service = MagicMock()

    # Return mock data for service methods
    mock_service.get_relevant_posts_optimized.return_value = mock_praw_posts
    mock_service.get_hot_posts.return_value = mock_praw_posts
    mock_service.get_top_comments.return_value = mock_praw_comments

    # Mock subreddit search results
    mock_subreddit = MagicMock()
    mock_subreddit.display_name = "test"
    mock_subreddit.public_description = "Test subreddit for development"
    mock_subreddit.subscribers = 50000
    mock_service.search_subreddits.return_value = [mock_subreddit]

    return mock_service


@pytest.fixture
def mock_external_services():
    """Mock all external services (scraper, summarizer, etc.)."""
    mocks = {}

    # Mock scraper service
    mocks['scraper'] = MagicMock()
    mocks['scraper'].return_value = "Scraped article content for testing."

    # Mock summarizer service
    mocks['summarizer'] = MagicMock()
    mocks['summarizer'].return_value = "AI-generated summary for testing."

    return mocks


class MockRedditEnvironment:
    """Context manager for mocking Reddit API environment."""

    def __init__(self, reddit_service_mock, external_services_mock=None):
        self.reddit_service_mock = reddit_service_mock
        self.external_services_mock = external_services_mock or {}
        self.patches = []

    def __enter__(self):
        from unittest.mock import patch

        # Patch Reddit service in main module
        self.patches.append(patch('app.main.reddit_service', self.reddit_service_mock))

        # Patch external services if provided
        if 'scraper' in self.external_services_mock:
            self.patches.append(patch('app.main.scrape_article_text', self.external_services_mock['scraper']))

        if 'summarizer' in self.external_services_mock:
            self.patches.append(patch('app.main.summarize_content', self.external_services_mock['summarizer']))

        # Start all patches
        for patch_obj in self.patches:
            patch_obj.start()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Stop all patches
        for patch_obj in self.patches:
            patch_obj.stop()
        self.patches.clear()


@pytest.fixture
def reddit_mock_environment(mock_reddit_service_with_data, mock_external_services):
    """Complete Reddit API mock environment for integration tests."""
    return MockRedditEnvironment(mock_reddit_service_with_data, mock_external_services)


# Test environment configuration
TEST_ENV_VARS = {
    "REDDIT_CLIENT_ID": "test_client_id",
    "REDDIT_CLIENT_SECRET": "test_client_secret",
    "REDDIT_USER_AGENT": "test_user_agent_v1.0",
    "OPENAI_API_KEY": "test_openai_key",
    "DATABASE_URL": "sqlite:///test.db"
}


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Automatically set up test environment variables for all tests."""
    for key, value in TEST_ENV_VARS.items():
        monkeypatch.setenv(key, value)

