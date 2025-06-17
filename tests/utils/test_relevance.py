from unittest.mock import MagicMock

from app.utils.relevance import score_and_rank_subreddits


class TestRelevance:
    """Test suite for relevance scoring functions."""

    def test_score_and_rank_subreddits(self, mocker):
        """Test the score_and_rank_subreddits function with mocked data."""
        # Create mock subreddit objects with display_name attributes
        mock_subreddit_tech = MagicMock()
        mock_subreddit_tech.display_name = "technology"
        mock_subreddit_tech.public_description = "Technology discussions and news"

        mock_subreddit_gadgets = MagicMock()
        mock_subreddit_gadgets.display_name = "gadgets"
        mock_subreddit_gadgets.public_description = "Latest gadgets and reviews"

        mock_subreddit_unrelated = MagicMock()
        mock_subreddit_unrelated.display_name = "cooking"
        mock_subreddit_unrelated.public_description = "Cooking recipes and tips"

        subreddits = [mock_subreddit_tech, mock_subreddit_gadgets, mock_subreddit_unrelated]

        # Create mock post objects for different subreddits
        # Posts for r/technology - 5 posts with "tech" in title
        tech_posts = []
        for i in range(5):
            post = MagicMock()
            post.title = f"Amazing tech breakthrough #{i+1}"
            tech_posts.append(post)
        # Add 2 posts without "tech" in title
        for i in range(2):
            post = MagicMock()
            post.title = f"Random post #{i+1}"
            tech_posts.append(post)

        # Posts for r/gadgets - 3 posts with "tech" in title
        gadgets_posts = []
        for i in range(3):
            post = MagicMock()
            post.title = f"New tech gadget review #{i+1}"
            gadgets_posts.append(post)
        # Add 3 posts without "tech" in title
        for i in range(3):
            post = MagicMock()
            post.title = f"Gadget news #{i+1}"
            gadgets_posts.append(post)

        # Posts for r/cooking - 0 posts with "tech" in title
        cooking_posts = []
        for i in range(5):
            post = MagicMock()
            post.title = f"Delicious recipe #{i+1}"
            cooking_posts.append(post)

        # Create a mock RedditService instance
        mock_reddit_service = MagicMock()

        # Configure the mock get_hot_posts method to return different posts for different subreddits
        subreddit_posts = {
            "technology": tech_posts,
            "gadgets": gadgets_posts,
            "cooking": cooking_posts,
        }

        def mock_get_hot_posts(subreddit_name):
            return subreddit_posts.get(subreddit_name, [])

        mock_reddit_service.get_hot_posts.side_effect = mock_get_hot_posts

        # Call the function we want to test
        result = score_and_rank_subreddits(subreddits, "tech", mock_reddit_service)

        # Assertions
        # Verify that get_hot_posts was called for each subreddit
        assert mock_reddit_service.get_hot_posts.call_count == 3
        mock_reddit_service.get_hot_posts.assert_any_call("technology")
        mock_reddit_service.get_hot_posts.assert_any_call("gadgets")
        mock_reddit_service.get_hot_posts.assert_any_call("cooking")

        # Verify the result structure and content
        assert len(result) == 3
        assert all(isinstance(item, dict) for item in result)
        assert all('name' in item and 'description' in item and 'score' in item for item in result)

        # Verify the scores are correct
        # r/technology should have score 5 (5 posts with "tech")
        # r/gadgets should have score 3 (3 posts with "tech")
        # r/cooking should have score 0 (0 posts with "tech")
        tech_result = next(item for item in result if item['name'] == 'technology')
        gadgets_result = next(item for item in result if item['name'] == 'gadgets')
        cooking_result = next(item for item in result if item['name'] == 'cooking')

        assert tech_result['score'] == 5
        assert gadgets_result['score'] == 3
        assert cooking_result['score'] == 0

        # Verify the list is sorted by score in descending order
        assert result[0]['score'] >= result[1]['score'] >= result[2]['score']
        assert result[0]['name'] == 'technology'  # Highest score (5)
        assert result[1]['name'] == 'gadgets'     # Middle score (3)
        assert result[2]['name'] == 'cooking'     # Lowest score (0)

        # Verify descriptions are included
        assert result[0]['description'] == "Technology discussions and news"
        assert result[1]['description'] == "Latest gadgets and reviews"
        assert result[2]['description'] == "Cooking recipes and tips"

    def test_score_and_rank_subreddits_case_insensitive(self, mocker):
        """Test that the scoring is case-insensitive."""
        # Create mock subreddit
        mock_subreddit = MagicMock()
        mock_subreddit.display_name = "technology"
        mock_subreddit.public_description = "Tech discussions"

        # Create posts with mixed case "TECH", "Tech", "tech"
        posts = []
        post1 = MagicMock()
        post1.title = "TECH news today"
        post2 = MagicMock()
        post2.title = "Tech breakthrough"
        post3 = MagicMock()
        post3.title = "Latest tech gadget"
        post4 = MagicMock()
        post4.title = "Unrelated post"
        posts = [post1, post2, post3, post4]

        # Mock RedditService
        mock_reddit_service = MagicMock()
        mock_reddit_service.get_hot_posts.return_value = posts

        # Test with lowercase topic
        result = score_and_rank_subreddits([mock_subreddit], "tech", mock_reddit_service)

        # Should match all 3 posts regardless of case
        assert len(result) == 1
        assert result[0]['score'] == 3

    def test_score_and_rank_subreddits_with_exception(self, mocker):
        """Test that the function handles exceptions gracefully."""
        # Create mock subreddit
        mock_subreddit = MagicMock()
        mock_subreddit.display_name = "problematic"
        mock_subreddit.public_description = "This subreddit causes issues"

        # Mock RedditService to raise an exception
        mock_reddit_service = MagicMock()
        mock_reddit_service.get_hot_posts.side_effect = Exception("API Error")

        # Call the function
        result = score_and_rank_subreddits([mock_subreddit], "tech", mock_reddit_service)

        # Should return empty list since the subreddit caused an exception
        assert result == []

    def test_score_and_rank_subreddits_missing_description(self, mocker):
        """Test handling of subreddits without public_description attribute."""
        # Create mock subreddit without public_description
        mock_subreddit = MagicMock()
        mock_subreddit.display_name = "test"
        # Don't set public_description attribute
        del mock_subreddit.public_description

        # Create mock posts
        posts = [MagicMock()]
        posts[0].title = "test post"

        # Mock RedditService
        mock_reddit_service = MagicMock()
        mock_reddit_service.get_hot_posts.return_value = posts

        # Call the function
        result = score_and_rank_subreddits([mock_subreddit], "test", mock_reddit_service)

        # Should handle missing description gracefully
        assert len(result) == 1
        assert result[0]['description'] == ''  # Should default to empty string
        assert result[0]['score'] == 1
