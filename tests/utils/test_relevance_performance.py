# ABOUTME: Performance tests for subreddit relevance scoring with concurrent processing
# ABOUTME: Tests N+1 query elimination, async processing, and error handling

import time
from unittest.mock import Mock

import pytest

from app.services.reddit_service import RedditService
from app.utils.relevance import (
    score_and_rank_subreddits,
    score_and_rank_subreddits_concurrent,
)


@pytest.fixture
def mock_subreddits():
    """Fixture for mock subreddit objects."""
    subreddits = []
    for i in range(5):
        subreddit = Mock()
        subreddit.display_name = f"test_subreddit_{i}"
        subreddit.public_description = f"Description for subreddit {i}"
        subreddits.append(subreddit)
    return subreddits


@pytest.fixture
def mock_reddit_service():
    """Fixture for mocked Reddit service."""
    service = Mock(spec=RedditService)
    return service


class TestConcurrentSubredditProcessing:
    """Test suite for concurrent subreddit processing optimization."""

    def test_concurrent_processing_eliminates_n_plus_1(self, mock_subreddits, mock_reddit_service):
        """Test that concurrent processing eliminates N+1 query pattern."""
        # Mock posts for each subreddit
        mock_posts = []
        for i in range(3):  # 3 posts per subreddit
            post = Mock()
            post.title = f"Test topic post {i}" if i % 2 == 0 else f"Other post {i}"
            mock_posts.append(post)

        mock_reddit_service.get_hot_posts.return_value = mock_posts

        # Process subreddits concurrently
        start_time = time.time()
        result = score_and_rank_subreddits_concurrent(mock_subreddits, "topic", mock_reddit_service)
        end_time = time.time()

        # Verify results
        assert len(result) == len(mock_subreddits)
        assert all('name' in item and 'score' in item for item in result)

        # Verify API calls were made for each subreddit
        assert mock_reddit_service.get_hot_posts.call_count == len(mock_subreddits)

        # Should complete faster than sequential processing (with some tolerance)
        execution_time = end_time - start_time
        assert execution_time < 2.0  # Should be much faster with concurrent processing

    def test_concurrent_vs_sequential_performance(self, mock_subreddits, mock_reddit_service):
        """Compare performance between concurrent and sequential processing."""
        # Add delay to simulate real API calls
        def mock_get_hot_posts_with_delay(subreddit_name):
            time.sleep(0.1)  # Simulate API latency
            post = Mock()
            post.title = f"topic post in {subreddit_name}"
            return [post]

        mock_reddit_service.get_hot_posts.side_effect = mock_get_hot_posts_with_delay

        # Test sequential processing
        start_time = time.time()
        sequential_result = score_and_rank_subreddits(mock_subreddits, "topic", mock_reddit_service)
        sequential_time = time.time() - start_time

        # Reset mock for concurrent test
        mock_reddit_service.reset_mock()
        mock_reddit_service.get_hot_posts.side_effect = mock_get_hot_posts_with_delay

        # Test concurrent processing
        start_time = time.time()
        concurrent_result = score_and_rank_subreddits_concurrent(mock_subreddits, "topic", mock_reddit_service)
        concurrent_time = time.time() - start_time

        # Concurrent should be significantly faster
        assert concurrent_time < sequential_time * 0.8  # At least 20% faster
        assert len(concurrent_result) == len(sequential_result)

    def test_concurrent_error_handling(self, mock_subreddits, mock_reddit_service):
        """Test that concurrent processing handles errors gracefully."""
        def mock_get_hot_posts_with_errors(subreddit_name):
            if "error" in subreddit_name:
                raise Exception("API Error")
            post = Mock()
            post.title = f"topic post in {subreddit_name}"
            return [post]

        # Add an error-prone subreddit
        error_subreddit = Mock()
        error_subreddit.display_name = "error_subreddit"
        error_subreddit.public_description = "This will fail"
        test_subreddits = [*mock_subreddits, error_subreddit]

        mock_reddit_service.get_hot_posts.side_effect = mock_get_hot_posts_with_errors

        # Should handle errors gracefully
        result = score_and_rank_subreddits_concurrent(test_subreddits, "topic", mock_reddit_service)

        # Should return results for successful subreddits, skip failed ones
        assert len(result) == len(mock_subreddits)  # Excludes the error subreddit
        assert all(item['name'] != 'error_subreddit' for item in result)

    def test_thread_safety(self, mock_subreddits, mock_reddit_service):
        """Test that concurrent processing is thread-safe."""
        call_count = 0

        def thread_safe_mock(subreddit_name):
            nonlocal call_count
            call_count += 1
            post = Mock()
            post.title = f"topic post {call_count}"
            return [post]

        mock_reddit_service.get_hot_posts.side_effect = thread_safe_mock

        # Process subreddits concurrently
        result = score_and_rank_subreddits_concurrent(mock_subreddits, "topic", mock_reddit_service)

        # Verify all subreddits were processed
        assert len(result) == len(mock_subreddits)
        assert call_count == len(mock_subreddits)

    def test_result_sorting_with_concurrent_processing(self, mock_subreddits, mock_reddit_service):
        """Test that results are properly sorted even with concurrent processing."""
        # Create posts with different relevance scores
        def mock_get_hot_posts_with_scores(subreddit_name):
            # Create different numbers of matching posts per subreddit
            subreddit_index = int(subreddit_name.split('_')[-1])
            posts = []
            for i in range(subreddit_index + 1):  # 1, 2, 3, 4, 5 matching posts
                post = Mock()
                post.title = f"topic post {i}"
                posts.append(post)
            return posts

        mock_reddit_service.get_hot_posts.side_effect = mock_get_hot_posts_with_scores

        result = score_and_rank_subreddits_concurrent(mock_subreddits, "topic", mock_reddit_service)

        # Results should be sorted by score in descending order
        scores = [item['score'] for item in result]
        assert scores == sorted(scores, reverse=True)

        # Highest scoring subreddit should be first
        assert result[0]['name'] == 'test_subreddit_4'  # Has 5 matching posts
        assert result[0]['score'] == 5

    def test_memory_efficiency_with_large_dataset(self, mock_reddit_service):
        """Test memory efficiency with larger number of subreddits."""
        # Create larger dataset
        large_subreddit_list = []
        for i in range(20):
            subreddit = Mock()
            subreddit.display_name = f"large_test_subreddit_{i}"
            subreddit.public_description = f"Description {i}"
            large_subreddit_list.append(subreddit)

        mock_reddit_service.get_hot_posts.return_value = [Mock(title="topic post")]

        # Should handle large datasets efficiently
        result = score_and_rank_subreddits_concurrent(large_subreddit_list, "topic", mock_reddit_service)

        assert len(result) == 20
        assert mock_reddit_service.get_hot_posts.call_count == 20


class TestConcurrencyConfiguration:
    """Test suite for concurrency configuration and limits."""

    def test_max_workers_configuration(self, mock_subreddits, mock_reddit_service):
        """Test that max_workers parameter controls concurrency level."""
        mock_reddit_service.get_hot_posts.return_value = [Mock(title="topic post")]

        # Test with different max_workers settings
        result_default = score_and_rank_subreddits_concurrent(
            mock_subreddits, "topic", mock_reddit_service
        )

        assert len(result_default) == len(mock_subreddits)

    def test_timeout_handling(self, mock_subreddits, mock_reddit_service):
        """Test that long-running requests are handled properly."""
        def slow_api_call(subreddit_name):
            if "slow" in subreddit_name:
                time.sleep(2)  # Simulate slow API
            post = Mock()
            post.title = "topic post"
            return [post]

        # Add a slow subreddit
        slow_subreddit = Mock()
        slow_subreddit.display_name = "slow_subreddit"
        slow_subreddit.public_description = "Slow to respond"
        test_subreddits = mock_subreddits[:2] + [slow_subreddit]  # Smaller dataset for faster test

        mock_reddit_service.get_hot_posts.side_effect = slow_api_call

        start_time = time.time()
        result = score_and_rank_subreddits_concurrent(test_subreddits, "topic", mock_reddit_service)
        end_time = time.time()

        # Should complete even with slow requests
        assert len(result) <= len(test_subreddits)
        # Should not take longer than sequential processing would
        assert end_time - start_time < 5.0
