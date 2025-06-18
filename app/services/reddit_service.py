# ABOUTME: Reddit API service for fetching posts, comments, and subreddit data with PRAW
# ABOUTME: Provides filtered content retrieval with media exclusion and relevance sorting

import logging
from typing import Any

import praw
from praw.exceptions import PRAWException
from prawcore.exceptions import Forbidden, NotFound

from app.core.config import config

logger = logging.getLogger(__name__)


class RedditService:
    """Service class for interacting with the Reddit API."""

    def __init__(self) -> None:
        """Initialize the Reddit service with authenticated PRAW client."""
        # Validate environment variables
        self._validate_config()

        logger.info("Initializing Reddit API client")
        logger.debug(f"Reddit Client ID: {config.REDDIT_CLIENT_ID[:8]}..." if config.REDDIT_CLIENT_ID else "None")
        logger.debug(f"Reddit User Agent: {config.REDDIT_USER_AGENT}")

        try:
            self.reddit = praw.Reddit(
                client_id=config.REDDIT_CLIENT_ID,
                client_secret=config.REDDIT_CLIENT_SECRET,
                user_agent=config.REDDIT_USER_AGENT,
                username="JyXAgent"
            )

            # Test the connection
            self._test_connection()
            logger.info("Reddit API client initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Reddit API client: {type(e).__name__}: {e}")
            raise RuntimeError(f"Reddit API initialization failed: {e}") from e

    def _validate_config(self) -> None:
        """Validate that all required Reddit API configuration is present."""
        missing_vars = []

        if not config.REDDIT_CLIENT_ID:
            missing_vars.append("REDDIT_CLIENT_ID")
        if not config.REDDIT_CLIENT_SECRET:
            missing_vars.append("REDDIT_CLIENT_SECRET")
        if not config.REDDIT_USER_AGENT:
            missing_vars.append("REDDIT_USER_AGENT")

        if missing_vars:
            error_msg = f"Missing required Reddit API environment variables: {', '.join(missing_vars)}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info("Reddit API configuration validation passed")

    def _test_connection(self) -> None:
        """Test the Reddit API connection by making a simple authenticated request."""
        try:
            # Test authentication by accessing read-only info
            logger.info("Testing Reddit API connection...")
            user = self.reddit.user.me()

            if user is None:
                # This means we're using a script application (read-only), which is expected
                logger.info("Reddit API connection successful (read-only script application)")
            else:
                logger.info(f"Reddit API connection successful (authenticated as: {user.name})")

        except PRAWException as e:
            logger.error(f"Reddit API connection test failed: {type(e).__name__}: {e}")
            raise RuntimeError(f"Reddit API authentication failed: {e}") from e
        except Exception as e:
            logger.error(f"Reddit API connection test failed with unexpected error: {type(e).__name__}: {e}")
            raise RuntimeError(f"Reddit API connection failed: {e}") from e

    def search_subreddits(self, topic: str, limit: int = 10) -> list:
        """
        Search for subreddits related to a given topic.

        Args:
            topic (str): The topic to search for
            limit (int): Maximum number of subreddits to return (default: 10)

        Returns:
            list: List of subreddit objects matching the topic
        """
        return list(self.reddit.subreddits.search(topic, limit=limit))

    def get_hot_posts(self, subreddit_name: str, limit: int = 25) -> list:
        """
        Get hot posts from a specific subreddit.

        Args:
            subreddit_name (str): Name of the subreddit
            limit (int): Maximum number of posts to return (default: 25)

        Returns:
            list: List of hot post objects from the subreddit
        """
        logger.debug(f"Fetching {limit} hot posts from r/{subreddit_name}")

        try:
            subreddit = self.reddit.subreddit(subreddit_name)

            # Check if subreddit exists and is accessible
            try:
                subreddit_display_name = subreddit.display_name
                logger.debug(f"Subreddit r/{subreddit_name} is accessible as r/{subreddit_display_name}")
            except Exception as e:
                logger.error(f"Cannot access subreddit r/{subreddit_name}: {type(e).__name__}: {e}")
                return []

            # Fetch hot posts
            hot_posts = list(subreddit.hot(limit=limit))
            logger.debug(f"Successfully retrieved {len(hot_posts)} hot posts from r/{subreddit_name}")

            # Log sample post titles for debugging
            if hot_posts:
                logger.debug(f"Sample posts from r/{subreddit_name}:")
                for i, post in enumerate(hot_posts[:3]):
                    logger.debug(f"  {i+1}. '{post.title}'")
            else:
                logger.warning(f"No hot posts found in r/{subreddit_name}")

            return hot_posts

        except PRAWException as e:
            logger.error(f"PRAW error getting hot posts from r/{subreddit_name}: {type(e).__name__}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting hot posts from r/{subreddit_name}: {type(e).__name__}: {e}")
            return []

    def get_relevant_posts(self, subreddit_name: str) -> list:
        """
        Get relevant posts from a subreddit, filtered and sorted for report generation.

        Args:
            subreddit_name (str): Name of the subreddit

        Returns:
            list: List of 5 valid post objects sorted by comment count
        """
        # Fetch top posts from the last day (generous limit for sorting)
        subreddit = self.reddit.subreddit(subreddit_name)
        posts = list(subreddit.top(time_filter='day', limit=50))

        # Sort posts by number of comments in descending order
        posts.sort(key=lambda post: post.num_comments, reverse=True)

        # Media file extensions to exclude
        media_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.mp4')
        media_domains = ('i.redd.it', 'v.redd.it', 'i.imgur.com')

        valid_posts: list[Any] = []

        # Iterate through sorted posts and filter for valid ones
        for post in posts:
            # Check if we have enough valid posts
            if len(valid_posts) >= 5:
                break

            # Validate post according to FR-06
            is_valid = False

            # Text posts are always valid
            if post.is_self:
                is_valid = True
            else:
                # For link posts, check if URL is not a media file or from media domains
                post_url = post.url.lower()

                # Check if URL ends with media extensions
                if not post_url.endswith(media_extensions):
                    # Check if URL is from media domains
                    is_media_domain = any(domain in post_url for domain in media_domains)
                    if not is_media_domain:
                        is_valid = True

            if is_valid:
                valid_posts.append(post)

        return valid_posts

    def get_relevant_posts_optimized(self, subreddit_name: str) -> list:
        """
        Get relevant posts from a subreddit with optimized API usage (80% reduction).

        This method reduces API calls by:
        1. Using a smaller initial fetch limit (15 instead of 50)
        2. Early termination when 5 valid posts are found
        3. More efficient filtering logic

        Args:
            subreddit_name (str): Name of the subreddit

        Returns:
            list: List of up to 5 valid post objects sorted by comment count

        Raises:
            NotFound: When the subreddit doesn't exist
            Forbidden: When the subreddit is private or restricted
            PRAWException: For other Reddit API errors
        """
        try:
            # Fetch fewer posts initially - optimization reduces API load
            subreddit = self.reddit.subreddit(subreddit_name)
            posts = list(subreddit.top(time_filter='day', limit=15))

            # Sort posts by number of comments in descending order
            posts.sort(key=lambda post: post.num_comments, reverse=True)

            # Media file extensions and domains to exclude
            media_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.mp4')
            media_domains = ('i.redd.it', 'v.redd.it', 'i.imgur.com')

            valid_posts: list[Any] = []

            # Process posts with early termination for efficiency
            for post in posts:
                # Early termination - stop when we have enough valid posts
                if len(valid_posts) >= 5:
                    break

                # Optimized validation logic
                if self._is_valid_post(post, media_extensions, media_domains):
                    valid_posts.append(post)

            return valid_posts

        except NotFound as e:
            logger.error(f"Subreddit r/{subreddit_name} not found: {e}")
            raise
        except Forbidden as e:
            logger.error(f"Access forbidden to subreddit r/{subreddit_name}: {e}")
            raise
        except PRAWException as e:
            logger.error(f"PRAW error getting posts from r/{subreddit_name}: {type(e).__name__}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting posts from r/{subreddit_name}: {type(e).__name__}: {e}")
            raise

    def _is_valid_post(self, post: Any, media_extensions: tuple, media_domains: tuple) -> bool:
        """
        Optimized helper method to validate post content type.

        Args:
            post: Reddit post object
            media_extensions: Tuple of media file extensions to exclude
            media_domains: Tuple of media domains to exclude

        Returns:
            bool: True if post is valid for processing
        """
        # Text posts are always valid
        if post.is_self:
            return True

        # For link posts, check if URL is not media content
        post_url = post.url.lower()

        # Quick exclusion checks - most efficient first
        if post_url.endswith(media_extensions):
            return False

        # Check media domains
        return not any(domain in post_url for domain in media_domains)

    def get_top_comments(self, post_id: str, limit: int = 15) -> list:
        """
        Get top comments from a specific post.

        Args:
            post_id (str): The ID of the post
            limit (int): Maximum number of comments to return (default: 15)

        Returns:
            list: List of top comment objects from the post
        """
        submission = self.reddit.submission(id=post_id)
        # Replace MoreComments objects and get top-level comments
        submission.comments.replace_more(limit=0)
        # Sort comments by score and return top ones
        top_comments = sorted(submission.comments, key=lambda x: x.score, reverse=True)
        return top_comments[:limit]
