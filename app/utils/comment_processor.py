# ABOUTME: Memory-efficient comment processing with streaming and memory limit tracking
# ABOUTME: Provides utilities for processing large comment threads without memory exhaustion

from collections.abc import Generator
import sys

from app.services.reddit_service import RedditService


class CommentMemoryTracker:
    """Tracks memory usage during comment processing to prevent memory exhaustion."""

    def __init__(self, max_memory_mb: float):
        """
        Initialize memory tracker with maximum memory limit.

        Args:
            max_memory_mb: Maximum memory usage in megabytes
        """
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.current_memory_bytes = 0
        self.comment_count = 0

    def can_add_comment(self, comment_text: str | None) -> bool:
        """
        Check if a comment can be added without exceeding memory limit.

        Args:
            comment_text: The comment text to check

        Returns:
            bool: True if comment can be added safely
        """
        if comment_text is None:
            return False

        # Accurate memory estimation using sys.getsizeof for Python object overhead
        # plus UTF-8 byte length for the actual string content
        estimated_size = sys.getsizeof(comment_text) + len(comment_text.encode('utf-8'))

        return (self.current_memory_bytes + estimated_size) <= self.max_memory_bytes

    def add_comment(self, comment_text: str) -> None:
        """
        Add a comment to memory tracking.

        Args:
            comment_text: The comment text being added
        """
        if comment_text is not None:
            # Use the same accurate memory estimation as can_add_comment
            comment_size = sys.getsizeof(comment_text) + len(comment_text.encode('utf-8'))
            self.current_memory_bytes += comment_size
            self.comment_count += 1

    def get_memory_usage_mb(self) -> float:
        """
        Get current memory usage in megabytes.

        Returns:
            float: Current memory usage in MB
        """
        return self.current_memory_bytes / (1024 * 1024)

    def reset(self) -> None:
        """
        Reset memory tracking counters.
        """
        self.current_memory_bytes = 0
        self.comment_count = 0


def process_comments_stream(
    post_id: str,
    reddit_service: RedditService,
    max_memory_mb: float = 10,
    top_count: int = 15,
    deduplicate: bool = False
) -> list[str]:
    """
    Process comments from a Reddit post using memory-efficient streaming.

    This function processes comments one at a time, tracking memory usage
    and stopping when limits are reached or enough top comments are collected.

    Args:
        post_id: Reddit post ID
        reddit_service: Service for Reddit API access
        max_memory_mb: Maximum memory usage in megabytes
        top_count: Maximum number of top comments to return
        deduplicate: Whether to remove duplicate comments

    Returns:
        List[str]: Processed comment texts, limited by memory and count constraints
    """
    memory_tracker = CommentMemoryTracker(max_memory_mb)
    processed_comments: list[str] = []
    seen_comments: set[str] | None = set() if deduplicate else None

    try:
        # Get comments using the existing Reddit service method
        comments = reddit_service.get_top_comments(post_id, limit=top_count * 2)  # Get more to allow for filtering

        # Process comments in order of score (already sorted by get_top_comments)
        for comment in comments:
            # Stop if we have enough comments
            if len(processed_comments) >= top_count:
                break

            # Extract comment text
            comment_text = getattr(comment, 'body', '')
            if not comment_text or comment_text == '[deleted]' or comment_text == '[removed]':
                continue

            # Check for duplicates if deduplication is enabled
            if deduplicate and seen_comments is not None and comment_text in seen_comments:
                continue

            # Check memory limit
            if not memory_tracker.can_add_comment(comment_text):
                break  # Memory limit reached

            # Add comment
            memory_tracker.add_comment(comment_text)
            processed_comments.append(comment_text)

            if deduplicate and seen_comments is not None:
                seen_comments.add(comment_text)

    except Exception as e:
        # Log error but don't crash - return what we have so far
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Error processing comments for post {post_id}: {e}")

    return processed_comments


def get_comments_summary_stream(
    post_id: str,
    reddit_service: RedditService,
    max_memory_mb: float = 10,
    top_count: int = 10
) -> str:
    """
    Get a memory-efficient summary of top comments from a post.

    Args:
        post_id: Reddit post ID
        reddit_service: Service for Reddit API access
        max_memory_mb: Maximum memory usage in megabytes
        top_count: Maximum number of comments to include

    Returns:
        str: Combined text of top comments, space-separated
    """
    comments = process_comments_stream(
        post_id,
        reddit_service,
        max_memory_mb=max_memory_mb,
        top_count=top_count,
        deduplicate=True  # Remove duplicates for cleaner summary
    )

    if not comments:
        return "No comments available for summary."

    # Join comments with separators for better AI processing
    return " [COMMENT_SEPARATOR] ".join(comments)


def comment_generator(comments: list) -> Generator[str, None, None]:
    """
    Generator that yields comment texts one at a time for memory efficiency.

    Args:
        comments: List of comment objects

    Yields:
        str: Comment text
    """
    for comment in comments:
        comment_text = getattr(comment, 'body', '')
        if comment_text and comment_text not in ['[deleted]', '[removed]']:
            yield comment_text
