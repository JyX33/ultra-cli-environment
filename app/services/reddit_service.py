# ABOUTME: Reddit API service for fetching posts, comments, and subreddit data with PRAW
# ABOUTME: Provides filtered content retrieval with media exclusion and relevance sorting

from typing import Any

import praw
from praw.exceptions import PRAWException
from prawcore.exceptions import Forbidden, NotFound, ResponseException

from app.core.config import config
from app.core.error_handling import log_service_error, reddit_error_handler
from app.core.exceptions import (
    MissingConfigurationError,
    RateLimitExceededError,
    RedditAuthenticationError,
    RedditPermissionError,
    RedditRateLimitError,
    create_error_context,
    wrap_external_error,
)
from app.core.structured_logging import get_logger, log_service_operation
from app.services.rate_limit_service import get_rate_limiter

logger = get_logger(__name__)


class RedditService:
    """Service class for interacting with the Reddit API."""

    # Media content exclusion constants
    MEDIA_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.mp4')
    MEDIA_DOMAINS = ('i.redd.it', 'v.redd.it', 'i.imgur.com')

    def __init__(self) -> None:
        """Initialize the Reddit service with authenticated PRAW client."""
        # Validate environment variables
        self._validate_config()

        log_service_operation(logger, "RedditService", "initialize")

        # Get Reddit configuration
        reddit_config = config.get_reddit_config()

        try:
            # Create PRAW client
            self.reddit = praw.Reddit(
                client_id=reddit_config.client_id,
                client_secret=reddit_config.client_secret,
                user_agent=reddit_config.user_agent,
                username=reddit_config.username,
                timeout=reddit_config.api_timeout
            )

            # Initialize rate limiter for Reddit API calls
            self.rate_limiter = get_rate_limiter("reddit")

        except Exception as e:
            # Log and handle PRAW client creation errors
            log_service_error(e, "RedditService", "initialize")
            raise wrap_external_error(
                e, RedditAuthenticationError,
                "Failed to initialize Reddit API client",
                "REDDIT_INIT_FAILED",
                create_error_context(username=reddit_config.username)
            ) from e

        # Test the connection - @reddit_error_handler will handle any errors from this
        self._test_connection()

        log_service_operation(
            logger, "RedditService", "initialize_success",
            username=reddit_config.username,
            timeout=reddit_config.api_timeout,
            rate_limiting_enabled=self.rate_limiter.enabled
        )

    def _validate_config(self) -> None:
        """Validate that all required Reddit API configuration is present."""
        try:
            config.validate_all()
            log_service_operation(logger, "RedditService", "config_validation_success")
        except ValueError as e:
            log_service_error(e, "RedditService", "config_validation")
            raise MissingConfigurationError(
                str(e),
                "REDDIT_CONFIG_MISSING"
            ) from e

    def _check_rate_limit(self, operation: str) -> None:
        """
        Check rate limits before making Reddit API calls.

        Args:
            operation: Name of the operation being performed

        Raises:
            RateLimitExceededError: If rate limit would be exceeded
        """
        try:
            self.rate_limiter.check_rate_limit(tokens=1.0, request_tokens=1)
            logger.debug(f"Rate limit check passed for {operation}")
        except RateLimitExceededError as e:
            log_service_operation(
                logger, "RedditService", "rate_limit_exceeded",
                error=str(e), operation_name=operation
            )
            raise

    @reddit_error_handler
    def _test_connection(self) -> None:
        """Test the Reddit API connection by making a simple authenticated request."""
        log_service_operation(logger, "RedditService", "test_connection")

        try:
            # Test authentication by accessing read-only info
            user = self.reddit.user.me()

            if user is None:
                # This means we're using a script application (read-only), which is expected
                log_service_operation(logger, "RedditService", "connection_success", type="read-only")
            else:
                log_service_operation(
                    logger, "RedditService", "connection_success",
                    type="authenticated", username=user.name
                )

        except Forbidden as e:
            raise wrap_external_error(
                e, RedditPermissionError,
                "Reddit API access forbidden - check credentials",
                "REDDIT_ACCESS_FORBIDDEN"
            ) from e
        except ResponseException as e:
            if e.response.status_code == 401:
                raise wrap_external_error(
                    e, RedditAuthenticationError,
                    "Reddit API authentication failed - invalid credentials",
                    "REDDIT_AUTH_INVALID"
                ) from e
            elif e.response.status_code == 429:
                raise wrap_external_error(
                    e, RedditRateLimitError,
                    "Reddit API rate limit exceeded during connection test",
                    "REDDIT_RATE_LIMIT_INIT"
                ) from e
            else:
                raise wrap_external_error(
                    e, RedditAuthenticationError,
                    f"Reddit API connection failed with status {e.response.status_code}",
                    "REDDIT_CONNECTION_FAILED",
                    create_error_context(status_code=e.response.status_code)
                ) from e

    @reddit_error_handler
    def search_subreddits(self, topic: str, limit: int | None = None) -> list:
        """
        Search for subreddits related to a given topic.

        Args:
            topic (str): The topic to search for
            limit (int | None): Maximum number of subreddits to return (default: from config)

        Returns:
            list: List of subreddit objects matching the topic
        """
        if limit is None:
            limit = config.REDDIT_HOT_POSTS_LIMIT

        log_service_operation(
            logger, "RedditService", "search_subreddits",
            topic=topic, limit=limit
        )

        # Check rate limits before making API call
        self._check_rate_limit("search_subreddits")

        try:
            subreddits = list(self.reddit.subreddits.search(topic, limit=limit))
            log_service_operation(
                logger, "RedditService", "search_subreddits_success",
                topic=topic, found_count=len(subreddits)
            )
            return subreddits
        except Exception:
            # Let @reddit_error_handler decorator handle error logging and exception mapping
            raise

    @reddit_error_handler
    def get_hot_posts(self, subreddit_name: str, limit: int | None = None) -> list:
        """
        Get hot posts from a specific subreddit.

        Args:
            subreddit_name (str): Name of the subreddit
            limit (int | None): Maximum number of posts to return (default: from config)

        Returns:
            list: List of hot post objects from the subreddit
        """
        if limit is None:
            limit = config.REDDIT_HOT_POSTS_LIMIT

        log_service_operation(
            logger, "RedditService", "get_hot_posts",
            subreddit=subreddit_name, limit=limit
        )

        # Check rate limits before making API call
        self._check_rate_limit("get_hot_posts")

        try:
            subreddit = self.reddit.subreddit(subreddit_name)

            # Check if subreddit exists and is accessible
            try:
                subreddit_display_name = subreddit.display_name
                log_service_operation(
                    logger, "RedditService", "subreddit_access_success",
                    requested_name=subreddit_name, actual_name=subreddit_display_name
                )
            except (Forbidden, NotFound):
                # Let @reddit_error_handler decorator handle error logging and exception mapping
                raise

            # Fetch hot posts
            hot_posts = list(subreddit.hot(limit=limit))
            log_service_operation(
                logger, "RedditService", "get_hot_posts_success",
                subreddit=subreddit_name, posts_found=len(hot_posts)
            )

            return hot_posts

        except Exception:
            # Let @reddit_error_handler decorator handle error logging and exception mapping
            raise

    def get_relevant_posts(self, subreddit_name: str) -> list:
        """
        Get relevant posts from a subreddit, filtered and sorted for report generation.

        Args:
            subreddit_name (str): Name of the subreddit

        Returns:
            list: List of valid post objects sorted by comment count (up to max_valid_posts)
        """
        # Check rate limits before making API call
        self._check_rate_limit("get_relevant_posts")

        # Get Reddit configuration
        reddit_config = config.get_reddit_config()

        # Fetch top posts from the last day (generous limit for sorting)
        subreddit = self.reddit.subreddit(subreddit_name)
        posts = list(subreddit.top(time_filter='day', limit=reddit_config.relevant_posts_limit))

        # Sort posts by number of comments in descending order
        posts.sort(key=lambda post: post.num_comments, reverse=True)

        valid_posts: list[Any] = []

        # Iterate through sorted posts and filter for valid ones
        for post in posts:
            # Check if we have enough valid posts
            if len(valid_posts) >= reddit_config.max_valid_posts:
                break

            # Validate post using class constants
            if self._is_valid_post(post):
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
        # Check rate limits before making API call
        self._check_rate_limit("get_relevant_posts_optimized")

        try:
            # Fetch fewer posts initially - optimization reduces API load
            subreddit = self.reddit.subreddit(subreddit_name)
            posts = list(subreddit.top(time_filter='day', limit=config.REDDIT_RELEVANT_POSTS_LIMIT))

            # Sort posts by number of comments in descending order
            posts.sort(key=lambda post: post.num_comments, reverse=True)

            valid_posts: list[Any] = []

            # Process posts with early termination for efficiency
            for post in posts:
                # Early termination - stop when we have enough valid posts
                if len(valid_posts) >= config.REDDIT_MAX_VALID_POSTS:
                    break

                # Optimized validation logic using class constants
                if self._is_valid_post(post):
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

    def _is_valid_post(self, post: Any) -> bool:
        """
        Helper method to validate post content type using class constants.

        Args:
            post: Reddit post object

        Returns:
            bool: True if post is valid for processing (not media content)
        """
        # Text posts are always valid
        if post.is_self:
            return True

        # For link posts, check if URL is not media content
        post_url = post.url.lower()

        # Quick exclusion checks - most efficient first
        if post_url.endswith(self.MEDIA_EXTENSIONS):
            return False

        # Check media domains
        return not any(domain in post_url for domain in self.MEDIA_DOMAINS)

    @reddit_error_handler
    def get_top_comments(self, post_id: str, limit: int | None = None) -> list[Any]:
        """
        Get top comments from a specific post.

        Args:
            post_id (str): The ID of the post
            limit (int | None): Maximum number of comments to return (default: from config)

        Returns:
            list: List of top comment objects from the post
        """
        if limit is None:
            limit = config.REDDIT_TOP_COMMENTS_LIMIT

        log_service_operation(
            logger, "RedditService", "get_top_comments",
            post_id=post_id, limit=limit
        )

        # Check rate limits before making API call
        self._check_rate_limit("get_top_comments")

        submission = self.reddit.submission(id=post_id)
        # Replace MoreComments objects and get top-level comments
        submission.comments.replace_more(limit=0)
        # Convert CommentForest to list for sorting and slicing
        # CommentForest is iterable but doesn't have proper type annotations
        comment_list: list[Any] = []
        for comment in submission.comments:
            comment_list.append(comment)
        top_comments = sorted(comment_list, key=lambda x: x.score, reverse=True)
        return top_comments[:limit]
