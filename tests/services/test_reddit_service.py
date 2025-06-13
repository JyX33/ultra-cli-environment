import pytest
from unittest.mock import MagicMock, patch
from app.services.reddit_service import RedditService


class TestRedditService:
    """Test suite for RedditService class."""
    
    def test_search_subreddits(self, mocker):
        """Test the search_subreddits method with mocked PRAW client."""
        # Create mock subreddit objects
        mock_subreddit1 = MagicMock()
        mock_subreddit1.display_name = "technology"
        mock_subreddit1.public_description = "Technology discussions"
        
        mock_subreddit2 = MagicMock()
        mock_subreddit2.display_name = "gadgets"
        mock_subreddit2.public_description = "Latest gadgets and tech"
        
        mock_subreddit_list = [mock_subreddit1, mock_subreddit2]
        
        # Mock the praw.Reddit class
        mock_reddit = mocker.patch('praw.Reddit')
        mock_reddit_instance = mock_reddit.return_value
        mock_reddit_instance.subreddits.search.return_value = mock_subreddit_list
        
        # Instantiate RedditService (this will use the mocked Reddit client)
        reddit_service = RedditService()
        
        # Call the method we want to test
        result = reddit_service.search_subreddits("test topic")
        
        # Assertions
        # Verify that praw.Reddit was called with the correct configuration
        mock_reddit.assert_called_once()
        
        # Verify that the search method was called with correct parameters
        mock_reddit_instance.subreddits.search.assert_called_once_with("test topic", limit=10)
        
        # Verify that the method returns the expected list of mock objects
        assert result == mock_subreddit_list
        assert len(result) == 2
        assert result[0].display_name == "technology"
        assert result[1].display_name == "gadgets"
    
    def test_search_subreddits_with_custom_limit(self, mocker):
        """Test the search_subreddits method with custom limit parameter."""
        # Create a single mock subreddit
        mock_subreddit = MagicMock()
        mock_subreddit.display_name = "python"
        mock_subreddit_list = [mock_subreddit]
        
        # Mock the praw.Reddit class
        mock_reddit = mocker.patch('praw.Reddit')
        mock_reddit_instance = mock_reddit.return_value
        mock_reddit_instance.subreddits.search.return_value = mock_subreddit_list
        
        # Instantiate RedditService
        reddit_service = RedditService()
        
        # Call the method with custom limit
        result = reddit_service.search_subreddits("python", limit=5)
        
        # Verify that the search method was called with correct custom limit
        mock_reddit_instance.subreddits.search.assert_called_once_with("python", limit=5)
        
        # Verify the result
        assert result == mock_subreddit_list
    
    def test_get_hot_posts(self, mocker):
        """Test the get_hot_posts method with mocked PRAW client."""
        # Create mock post objects with titles
        mock_post1 = MagicMock()
        mock_post1.title = "First tech post"
        mock_post1.id = "post1"
        
        mock_post2 = MagicMock()
        mock_post2.title = "Second tech post"
        mock_post2.id = "post2"
        
        mock_post3 = MagicMock()
        mock_post3.title = "Third non-tech post"
        mock_post3.id = "post3"
        
        mock_posts_list = [mock_post1, mock_post2, mock_post3]
        
        # Mock the praw.Reddit class
        mock_reddit = mocker.patch('praw.Reddit')
        mock_reddit_instance = mock_reddit.return_value
        mock_subreddit = mock_reddit_instance.subreddit.return_value
        mock_subreddit.hot.return_value = mock_posts_list
        
        # Instantiate RedditService
        reddit_service = RedditService()
        
        # Call the method we want to test
        result = reddit_service.get_hot_posts("technology")
        
        # Assertions
        # Verify that subreddit was called with correct name
        mock_reddit_instance.subreddit.assert_called_once_with("technology")
        
        # Verify that hot() was called with correct limit
        mock_subreddit.hot.assert_called_once_with(limit=25)
        
        # Verify that the method returns the expected list of mock posts
        assert result == mock_posts_list
        assert len(result) == 3
        assert result[0].title == "First tech post"
        assert result[1].title == "Second tech post"
        assert result[2].title == "Third non-tech post"
    
    def test_get_hot_posts_with_custom_limit(self, mocker):
        """Test the get_hot_posts method with custom limit parameter."""
        # Create a single mock post
        mock_post = MagicMock()
        mock_post.title = "Test post"
        mock_post.id = "test_post"
        mock_posts_list = [mock_post]
        
        # Mock the praw.Reddit class
        mock_reddit = mocker.patch('praw.Reddit')
        mock_reddit_instance = mock_reddit.return_value
        mock_subreddit = mock_reddit_instance.subreddit.return_value
        mock_subreddit.hot.return_value = mock_posts_list
        
        # Instantiate RedditService
        reddit_service = RedditService()
        
        # Call the method with custom limit
        result = reddit_service.get_hot_posts("python", limit=10)
        
        # Verify that hot() was called with correct custom limit
        mock_subreddit.hot.assert_called_once_with(limit=10)
        
        # Verify the result
        assert result == mock_posts_list
    
    def test_get_relevant_posts(self, mocker):
        """Test the get_relevant_posts method with comprehensive mock data."""
        # Create comprehensive mock post objects with different types and comment counts
        # Text posts (always valid)
        text_post1 = MagicMock()
        text_post1.is_self = True
        text_post1.num_comments = 150
        text_post1.title = "Text post 1"
        text_post1.id = "text1"
        
        text_post2 = MagicMock()
        text_post2.is_self = True
        text_post2.num_comments = 75
        text_post2.title = "Text post 2"
        text_post2.id = "text2"
        
        text_post3 = MagicMock()
        text_post3.is_self = True
        text_post3.num_comments = 25
        text_post3.title = "Text post 3"
        text_post3.id = "text3"
        
        # Link posts to articles (valid)
        article_post1 = MagicMock()
        article_post1.is_self = False
        article_post1.url = "https://example.com/article1.html"
        article_post1.num_comments = 200
        article_post1.title = "Article post 1"
        article_post1.id = "article1"
        
        article_post2 = MagicMock()
        article_post2.is_self = False
        article_post2.url = "https://news.com/story.php"
        article_post2.num_comments = 120
        article_post2.title = "Article post 2"
        article_post2.id = "article2"
        
        article_post3 = MagicMock()
        article_post3.is_self = False
        article_post3.url = "https://blog.com/post"
        article_post3.num_comments = 50
        article_post3.title = "Article post 3"
        article_post3.id = "article3"
        
        # Link posts to images (invalid - should be filtered out)
        image_post1 = MagicMock()
        image_post1.is_self = False
        image_post1.url = "https://example.com/image.jpg"
        image_post1.num_comments = 300
        image_post1.title = "Image post 1"
        image_post1.id = "image1"
        
        image_post2 = MagicMock()
        image_post2.is_self = False
        image_post2.url = "https://example.com/photo.png"
        image_post2.num_comments = 80
        image_post2.title = "Image post 2"
        image_post2.id = "image2"
        
        image_post3 = MagicMock()
        image_post3.is_self = False
        image_post3.url = "https://example.com/video.mp4"
        image_post3.num_comments = 40
        image_post3.title = "Video post"
        image_post3.id = "video1"
        
        # Link posts to media domains (invalid - should be filtered out)
        reddit_media1 = MagicMock()
        reddit_media1.is_self = False
        reddit_media1.url = "https://i.redd.it/abcd123.jpg"
        reddit_media1.num_comments = 250
        reddit_media1.title = "Reddit media 1"
        reddit_media1.id = "reddit1"
        
        reddit_media2 = MagicMock()
        reddit_media2.is_self = False
        reddit_media2.url = "https://v.redd.it/xyz789"
        reddit_media2.num_comments = 90
        reddit_media2.title = "Reddit video"
        reddit_media2.id = "reddit2"
        
        imgur_media = MagicMock()
        imgur_media.is_self = False
        imgur_media.url = "https://i.imgur.com/test123.gif"
        imgur_media.num_comments = 60
        imgur_media.title = "Imgur media"
        imgur_media.id = "imgur1"
        
        # Create the list in an order different from the final sorted order
        # This ensures we test that sorting by num_comments actually works
        mock_posts_list = [
            text_post2,        # 75 comments
            reddit_media1,     # 250 comments (invalid, should be filtered)
            article_post1,     # 200 comments
            text_post3,        # 25 comments
            image_post1,       # 300 comments (invalid, should be filtered)
            article_post2,     # 120 comments
            reddit_media2,     # 90 comments (invalid, should be filtered)
            text_post1,        # 150 comments
            image_post2,       # 80 comments (invalid, should be filtered)
            article_post3,     # 50 comments
            imgur_media,       # 60 comments (invalid, should be filtered)
            image_post3        # 40 comments (invalid, should be filtered)
        ]
        
        # Mock the praw.Reddit class
        mock_reddit = mocker.patch('praw.Reddit')
        mock_reddit_instance = mock_reddit.return_value
        mock_subreddit = mock_reddit_instance.subreddit.return_value
        mock_subreddit.top.return_value = mock_posts_list
        
        # Instantiate RedditService
        reddit_service = RedditService()
        
        # Call the method we want to test
        result = reddit_service.get_relevant_posts("testsub")
        
        # Assertions
        # Verify that subreddit was called with correct name
        mock_reddit_instance.subreddit.assert_called_once_with("testsub")
        
        # Verify that top() was called with correct parameters
        mock_subreddit.top.assert_called_once_with(time_filter='day', limit=50)
        
        # Assert that the returned list contains exactly 5 posts
        assert len(result) == 5, f"Expected 5 posts, got {len(result)}"
        
        # Assert that all returned posts are valid (not media links)
        for post in result:
            if not post.is_self:
                # If it's a link post, it should not be a media file or from media domains
                url = post.url.lower()
                assert not url.endswith(('.jpg', '.jpeg', '.png', '.gif', '.mp4')), f"Found media file URL: {post.url}"
                assert 'i.redd.it' not in url, f"Found i.redd.it URL: {post.url}"
                assert 'v.redd.it' not in url, f"Found v.redd.it URL: {post.url}"
                assert 'i.imgur.com' not in url, f"Found i.imgur.com URL: {post.url}"
        
        # Assert that the list is correctly sorted by num_comments in descending order
        expected_order = [article_post1, text_post1, article_post2, text_post2, article_post3]  # 200, 150, 120, 75, 50
        assert result == expected_order, f"Posts not sorted correctly by num_comments"
        
        # Verify the comment counts are in descending order
        comment_counts = [post.num_comments for post in result]
        assert comment_counts == [200, 150, 120, 75, 50], f"Comment counts not in descending order: {comment_counts}"
        
        # Verify specific posts are included (the top 5 valid ones by comment count)
        expected_ids = ["article1", "text1", "article2", "text2", "article3"]
        actual_ids = [post.id for post in result]
        assert actual_ids == expected_ids, f"Expected post IDs {expected_ids}, got {actual_ids}"
    
    def test_get_top_comments(self, mocker):
        """Test the get_top_comments method with mocked PRAW client."""
        # Create mock comment objects with different scores
        comment1 = MagicMock()
        comment1.body = "Great post! Very informative."
        comment1.score = 150
        comment1.id = "comment1"
        
        comment2 = MagicMock()
        comment2.body = "I disagree with this analysis."
        comment2.score = 75
        comment2.id = "comment2"
        
        comment3 = MagicMock()
        comment3.body = "Thanks for sharing this."
        comment3.score = 45
        comment3.id = "comment3"
        
        comment4 = MagicMock()
        comment4.body = "This is spam."
        comment4.score = -10
        comment4.id = "comment4"
        
        # Create mock comments list in unsorted order
        mock_comments = [comment2, comment4, comment1, comment3]  # Unsorted by score
        
        # Mock the praw.Reddit class and submission
        mock_reddit = mocker.patch('praw.Reddit')
        mock_reddit_instance = mock_reddit.return_value
        mock_submission = mock_reddit_instance.submission.return_value
        
        # Create a mock comments object that can be iterated and has replace_more
        mock_comments_obj = MagicMock()
        mock_comments_obj.__iter__ = lambda self: iter(mock_comments)
        mock_comments_obj.replace_more = MagicMock()
        mock_submission.comments = mock_comments_obj
        
        # Instantiate RedditService
        reddit_service = RedditService()
        
        # Call the method we want to test
        result = reddit_service.get_top_comments("test_post_id")
        
        # Assertions
        # Verify that submission was called with correct post ID
        mock_reddit_instance.submission.assert_called_once_with(id="test_post_id")
        
        # Verify that replace_more was called
        mock_submission.comments.replace_more.assert_called_once_with(limit=0)
        
        # Verify that the method returns comments sorted by score in descending order
        expected_order = [comment1, comment2, comment3, comment4]  # Sorted by score: 150, 75, 45, -10
        assert result == expected_order, f"Comments not sorted correctly by score"
        
        # Verify the scores are in descending order
        comment_scores = [comment.score for comment in result]
        assert comment_scores == [150, 75, 45, -10], f"Comment scores not in descending order: {comment_scores}"
    
    def test_get_top_comments_with_limit(self, mocker):
        """Test the get_top_comments method with custom limit parameter."""
        # Create mock comment objects
        comments = []
        for i in range(20):
            comment = MagicMock()
            comment.body = f"Comment {i}"
            comment.score = 100 - i  # Scores from 100 down to 81
            comment.id = f"comment{i}"
            comments.append(comment)
        
        # Mock the praw.Reddit class and submission
        mock_reddit = mocker.patch('praw.Reddit')
        mock_reddit_instance = mock_reddit.return_value
        mock_submission = mock_reddit_instance.submission.return_value
        
        # Create a mock comments object that can be iterated and has replace_more
        mock_comments_obj = MagicMock()
        mock_comments_obj.__iter__ = lambda self: iter(comments)
        mock_comments_obj.replace_more = MagicMock()
        mock_submission.comments = mock_comments_obj
        
        # Instantiate RedditService
        reddit_service = RedditService()
        
        # Call the method with custom limit of 5
        result = reddit_service.get_top_comments("test_post_id", limit=5)
        
        # Verify that only 5 comments are returned
        assert len(result) == 5, f"Expected 5 comments, got {len(result)}"
        
        # Verify that the top 5 comments by score are returned
        expected_scores = [100, 99, 98, 97, 96]
        actual_scores = [comment.score for comment in result]
        assert actual_scores == expected_scores, f"Expected scores {expected_scores}, got {actual_scores}"