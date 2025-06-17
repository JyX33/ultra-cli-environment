# ABOUTME: Performance tests for Reddit API optimization and efficiency improvements
# ABOUTME: Tests API call reduction, intelligent filtering, and response time validation

import time
from unittest.mock import Mock, patch

import pytest

from app.services.reddit_service import RedditService


@pytest.fixture
def mock_reddit_service():
    """Fixture for mocked Reddit service."""
    with patch('app.services.reddit_service.praw.Reddit') as mock_reddit:
        service = RedditService()
        return service, mock_reddit


class TestRedditAPIEfficiency:
    """Test suite for Reddit API efficiency optimizations."""

    def test_api_call_reduction_in_relevant_posts(self, mock_reddit_service):
        """Test that get_relevant_posts reduces API calls by using smart filtering."""
        service, mock_reddit = mock_reddit_service

        # Create mock posts with varied characteristics for filtering
        mock_posts = []
        for i in range(20):
            post = Mock()
            post.num_comments = 50 - i  # Descending comment count
            post.is_self = i % 3 == 0  # Every 3rd post is text
            post.url = f"https://example{i}.com/article" if not post.is_self else ""
            mock_posts.append(post)

        # Mock subreddit.top() to return our test posts
        mock_subreddit = Mock()
        mock_subreddit.top.return_value = mock_posts
        mock_reddit.return_value.subreddit.return_value = mock_subreddit

        # Call the method
        result = service.get_relevant_posts_optimized("test_subreddit")

        # Verify API efficiency
        assert len(result) <= 5  # Should limit results
        mock_subreddit.top.assert_called_once()  # Only one API call

        # Verify posts are sorted by comment count
        comment_counts = [post.num_comments for post in result]
        assert comment_counts == sorted(comment_counts, reverse=True)

    def test_intelligent_post_filtering(self, mock_reddit_service):
        """Test that posts are intelligently filtered to avoid media content."""
        service, mock_reddit = mock_reddit_service

        # Create mock posts with different content types
        mock_posts = [
            self._create_mock_post(1, 100, True, ""),  # Text post - should be included
            self._create_mock_post(2, 90, False, "https://example.com/article"),  # Link - should be included
            self._create_mock_post(3, 80, False, "https://i.redd.it/image.jpg"),  # Image - should be excluded
            self._create_mock_post(4, 70, False, "https://v.redd.it/video.mp4"),  # Video - should be excluded
            self._create_mock_post(5, 60, False, "https://example.com/news.html"),  # Link - should be included
        ]

        mock_subreddit = Mock()
        mock_subreddit.top.return_value = mock_posts
        mock_reddit.return_value.subreddit.return_value = mock_subreddit

        result = service.get_relevant_posts_optimized("test_subreddit")

        # Should exclude media posts
        result_urls = [post.url for post in result if not post.is_self]
        assert "https://i.redd.it/image.jpg" not in result_urls
        assert "https://v.redd.it/video.mp4" not in result_urls
        assert "https://example.com/article" in result_urls

    def test_response_time_optimization(self, mock_reddit_service):
        """Test that optimized method completes within acceptable time limits."""
        service, mock_reddit = mock_reddit_service

        # Create larger dataset to test performance
        mock_posts = [self._create_mock_post(i, 100-i, i%2==0, f"https://example{i}.com")
                     for i in range(50)]

        mock_subreddit = Mock()
        mock_subreddit.top.return_value = mock_posts
        mock_reddit.return_value.subreddit.return_value = mock_subreddit

        # Measure execution time
        start_time = time.time()
        result = service.get_relevant_posts_optimized("test_subreddit")
        end_time = time.time()

        execution_time = end_time - start_time

        # Should complete within reasonable time (less than 1 second for mock data)
        assert execution_time < 1.0
        assert len(result) <= 5

    def test_api_call_count_tracking(self, mock_reddit_service):
        """Test that we can track and verify API call reduction."""
        service, mock_reddit = mock_reddit_service

        # Mock posts for testing
        mock_posts = [self._create_mock_post(i, 50-i, True, "") for i in range(10)]
        mock_subreddit = Mock()
        mock_subreddit.top.return_value = mock_posts
        mock_reddit.return_value.subreddit.return_value = mock_subreddit

        # Track API calls directly through mock
        result = service.get_relevant_posts_optimized("test_subreddit")

        # Should make minimal API calls
        mock_subreddit.top.assert_called_once()
        assert len(result) <= 5

        # Verify call was made with optimized limit
        call_args = mock_subreddit.top.call_args
        assert call_args[1]['limit'] == 15  # Optimized limit vs original 50

    def test_early_termination_optimization(self, mock_reddit_service):
        """Test that processing stops early when enough valid posts are found."""
        service, mock_reddit = mock_reddit_service

        # Create exactly 5 valid text posts followed by many invalid ones
        valid_posts = [self._create_mock_post(i, 100-i, True, "") for i in range(5)]
        invalid_posts = [self._create_mock_post(i+5, 50-i, False, f"https://i.redd.it/img{i}.jpg")
                        for i in range(20)]

        mock_posts = valid_posts + invalid_posts
        mock_subreddit = Mock()
        mock_subreddit.top.return_value = mock_posts
        mock_reddit.return_value.subreddit.return_value = mock_subreddit

        result = service.get_relevant_posts_optimized("test_subreddit")

        # Should return exactly 5 posts and stop processing early
        assert len(result) == 5
        # All returned posts should be the valid text posts
        assert all(post.is_self for post in result)

    def _create_mock_post(self, post_id: int, num_comments: int, is_self: bool, url: str):
        """Helper to create mock post objects."""
        post = Mock()
        post.id = str(post_id)
        post.num_comments = num_comments
        post.is_self = is_self
        post.url = url
        return post


class TestAPICallReduction:
    """Test suite specifically for measuring API call reduction."""

    def test_baseline_vs_optimized_calls(self, mock_reddit_service):
        """Compare API calls between original and optimized methods."""
        service, mock_reddit = mock_reddit_service

        mock_posts = [self._create_mock_post(i, 50-i, i%2==0, f"https://example{i}.com")
                     for i in range(30)]

        mock_subreddit = Mock()
        mock_subreddit.top.return_value = mock_posts
        mock_reddit.return_value.subreddit.return_value = mock_subreddit

        # Test optimized method
        result_optimized = service.get_relevant_posts_optimized("test_subreddit")
        optimized_calls = mock_subreddit.top.call_count

        # Reset mock for baseline test
        mock_subreddit.reset_mock()

        # Test original method (if it exists for comparison)
        result_original = service.get_relevant_posts("test_subreddit")
        original_calls = mock_subreddit.top.call_count

        # Optimized should use same or fewer API calls
        assert optimized_calls <= original_calls
        assert len(result_optimized) <= 5
        assert len(result_original) <= 5

    def _create_mock_post(self, post_id: int, num_comments: int, is_self: bool, url: str):
        """Helper to create mock post objects."""
        post = Mock()
        post.id = str(post_id)
        post.num_comments = num_comments
        post.is_self = is_self
        post.url = url
        return post
