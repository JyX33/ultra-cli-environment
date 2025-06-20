# ABOUTME: StorageService for managing Reddit data persistence and CRUD operations
# ABOUTME: Handles check runs, posts, and provides transactional database operations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import time
from typing import Any, TypeVar, cast

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.error_handling import database_error_handler, log_service_error
from app.core.exceptions import DataValidationError, StorageServiceError
from app.core.structured_logging import get_logger, log_service_operation
from app.models.check_run import CheckRun
from app.models.comment import Comment
from app.models.post_snapshot import PostSnapshot
from app.models.reddit_post import RedditPost
from app.models.validation_schemas import (
    validate_comment_data,
    validate_reddit_post_data,
)
from app.services.performance_monitoring_service import PerformanceMonitoringService

# Set up structured logging
logger = get_logger(__name__)

F = TypeVar('F', bound=Callable[..., Any])


def database_operation_monitor(operation_name: str) -> Callable[[F], F]:
    """Decorator for monitoring database operation performance.

    Args:
        operation_name: Name of the database operation being monitored
    """
    def decorator(func: F) -> F:
        def wrapper(self: 'StorageService', *args: Any, **kwargs: Any) -> Any:
            if not hasattr(self, 'performance_monitor'):
                # Fallback if no performance monitor available
                return func(self, *args, **kwargs)

            # Track operation with performance monitoring
            with self.performance_monitor.measure_time(
                f"db_{operation_name}",
                tags={"operation": operation_name, "service": "storage"}
            ) as timer:
                try:
                    result = func(self, *args, **kwargs)

                    # Record successful operation
                    self._record_query_success(timer.duration * 1000 if timer.duration else 0)
                    return result

                except Exception as e:
                    # Record failed operation
                    self._record_query_failure(timer.duration * 1000 if timer.duration else 0, str(e))
                    raise

        return cast('F', wrapper)
    return decorator


class StorageService:
    """Service for managing Reddit data storage and retrieval.

    This service provides CRUD operations for Reddit data with proper
    transaction management, error handling, and data validation.
    """

    def __init__(self, session: Session, performance_monitor: PerformanceMonitoringService | None = None) -> None:
        """Initialize StorageService with database session and optional performance monitoring.

        Args:
            session: SQLAlchemy session for database operations
            performance_monitor: Optional performance monitoring service for query tracking
        """
        self.session = session
        self.performance_monitor = performance_monitor or PerformanceMonitoringService(
            max_metrics_history=500,
            enable_system_monitoring=False  # Don't start background monitoring by default
        )

        # Query performance tracking
        self._query_count = 0
        self._slow_query_threshold_ms = 100.0  # Configurable threshold for slow queries
        self._query_performance_stats = {
            'total_queries': 0,
            'slow_queries': 0,
            'failed_queries': 0,
            'total_duration_ms': 0.0
        }

    def _record_query_success(self, duration_ms: float) -> None:
        """Record successful database query performance.

        Args:
            duration_ms: Query duration in milliseconds
        """
        self._query_count += 1
        self._query_performance_stats['total_queries'] += 1
        self._query_performance_stats['total_duration_ms'] += duration_ms

        if duration_ms > self._slow_query_threshold_ms:
            self._query_performance_stats['slow_queries'] += 1
            logger.warning(
                f"Slow database query detected: {duration_ms:.2f}ms (threshold: {self._slow_query_threshold_ms}ms)"
            )

        # Record in performance monitor
        self.performance_monitor.record_database_query(duration_ms)

    def _record_query_failure(self, duration_ms: float, error_message: str) -> None:
        """Record failed database query performance.

        Args:
            duration_ms: Query duration in milliseconds before failure
            error_message: Error message from the failed query
        """
        self._query_count += 1
        self._query_performance_stats['total_queries'] += 1
        self._query_performance_stats['failed_queries'] += 1
        self._query_performance_stats['total_duration_ms'] += duration_ms

        logger.error(f"Database query failed after {duration_ms:.2f}ms: {error_message}")

        # Record in performance monitor with error tag
        self.performance_monitor.record_metric(
            "database_query_failure",
            1,
            "count",
            {"error": "query_failed", "duration_ms": str(duration_ms)}
        )

    @contextmanager
    def monitor_database_operation(self, operation_name: str, **context: Any) -> Iterator[None]:
        """Context manager for monitoring database operations with detailed tracking.

        Args:
            operation_name: Name of the database operation
            **context: Additional context information for logging
        """
        start_time = time.perf_counter()
        operation_context = {"operation": operation_name, "service": "storage", **context}

        try:
            with self.performance_monitor.measure_time(f"db_{operation_name}", operation_context):
                yield

                # Record successful operation
                duration_ms = (time.perf_counter() - start_time) * 1000
                self._record_query_success(duration_ms)

                logger.debug(
                    f"Database operation '{operation_name}' completed successfully in {duration_ms:.2f}ms",
                    extra={"operation_context": operation_context}
                )

        except Exception as e:
            # Record failed operation
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_query_failure(duration_ms, str(e))

            logger.error(
                f"Database operation '{operation_name}' failed after {duration_ms:.2f}ms: {e}",
                extra={"operation_context": operation_context, "error": str(e)}
            )
            raise

    def get_query_performance_stats(self) -> dict[str, Any]:
        """Get comprehensive database query performance statistics.

        Returns:
            Dictionary with query performance metrics and analysis
        """
        stats = self._query_performance_stats.copy()

        # Calculate derived metrics
        if stats['total_queries'] > 0:
            stats['average_query_time_ms'] = stats['total_duration_ms'] / stats['total_queries']
            stats['slow_query_rate'] = stats['slow_queries'] / stats['total_queries']
            stats['failure_rate'] = stats['failed_queries'] / stats['total_queries']
        else:
            stats['average_query_time_ms'] = 0.0
            stats['slow_query_rate'] = 0.0
            stats['failure_rate'] = 0.0

        # Add threshold configuration
        stats['slow_query_threshold_ms'] = self._slow_query_threshold_ms

        # Add performance assessment
        performance_score = 100.0
        if stats['slow_query_rate'] > 0.1:  # More than 10% slow queries
            performance_score -= 30
        if stats['failure_rate'] > 0.05:  # More than 5% failed queries
            performance_score -= 40
        if stats['average_query_time_ms'] > 50:  # Average over 50ms
            performance_score -= 20

        stats['performance_score'] = max(0, performance_score)

        return stats

    def configure_query_monitoring(self, slow_query_threshold_ms: float | None = None) -> None:
        """Configure query performance monitoring settings.

        Args:
            slow_query_threshold_ms: Threshold for considering queries slow (in milliseconds)
        """
        if slow_query_threshold_ms is not None:
            self._slow_query_threshold_ms = slow_query_threshold_ms
            logger.info(f"Updated slow query threshold to {slow_query_threshold_ms}ms")

    @database_operation_monitor("create_check_run")
    def create_check_run(self, subreddit: str, topic: str) -> int:
        """Create a new check run record.

        Args:
            subreddit: The subreddit being monitored
            topic: The topic being searched for

        Returns:
            The ID of the created check run

        Raises:
            RuntimeError: If check run creation fails
        """
        try:
            check_run = CheckRun(
                subreddit=subreddit,
                topic=topic,
                timestamp=datetime.now(UTC),
                posts_found=0,
                new_posts=0,
            )

            self.session.add(check_run)
            self.session.commit()

            logger.info(
                f"Created check run {check_run.id} for subreddit '{subreddit}' "
                f"with topic '{topic}'"
            )

            return check_run.id

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Failed to create check run: {e}")
            raise RuntimeError(f"Failed to create check run: {e}") from e

    @database_error_handler
    def save_post(self, post_data: dict[str, Any]) -> int:
        """Save a Reddit post to the database with comprehensive validation.

        Args:
            post_data: Dictionary containing post data with the following required keys:
                - post_id: Reddit post ID (unique)
                - subreddit: Subreddit name
                - title: Post title
                - author: Post author (can be None for deleted)
                - selftext: Post self text content
                - score: Post score/upvotes
                - num_comments: Number of comments
                - url: Post URL
                - permalink: Reddit permalink
                - is_self: Whether it's a self post
                - over_18: Whether post is NSFW
                - created_utc: When post was created
                - check_run_id: Foreign key to check run

        Returns:
            The database ID of the saved post

        Raises:
            StorageServiceError: If validation fails or database operation fails
        """
        log_service_operation(logger, "StorageService", "save_post_start",
                            post_id=post_data.get("post_id"),
                            subreddit=post_data.get("subreddit"))

        try:
            # STEP 1: Validate input data before database operations
            try:
                validated_data = validate_reddit_post_data(post_data)
                log_service_operation(logger, "StorageService", "post_validation_success",
                                    post_id=validated_data["post_id"])
            except DataValidationError as e:
                log_service_error(e, "StorageService", "post_validation",
                                post_id=post_data.get("post_id"))
                raise StorageServiceError(
                    f"Reddit post validation failed: {e.message}",
                    "POST_VALIDATION_FAILED",
                    e.context
                ) from e

            # STEP 2: Create RedditPost instance from validated data
            reddit_post = RedditPost(
                post_id=validated_data["post_id"],
                subreddit=validated_data["subreddit"],
                title=validated_data["title"],
                author=validated_data.get("author"),  # Can be None
                selftext=validated_data.get("selftext", ""),
                score=validated_data.get("score", 0),
                num_comments=validated_data.get("num_comments", 0),
                url=validated_data["url"],
                permalink=validated_data["permalink"],
                is_self=validated_data.get("is_self", False),
                over_18=validated_data.get("over_18", False),
                created_utc=validated_data["created_utc"],
                check_run_id=validated_data["check_run_id"],
                first_seen=datetime.now(UTC),
                last_updated=datetime.now(UTC),
            )

            # STEP 3: Save to database
            self.session.add(reddit_post)
            self.session.commit()

            log_service_operation(logger, "StorageService", "save_post_success",
                                post_id=reddit_post.post_id,
                                db_id=reddit_post.id,
                                subreddit=reddit_post.subreddit)

            return reddit_post.id

        except StorageServiceError:
            # Re-raise storage service errors without wrapping
            raise
        except (SQLAlchemyError, KeyError) as e:
            self.session.rollback()
            # Let @database_error_handler decorator handle error logging and exception mapping
            raise StorageServiceError(
                f"Database operation failed while saving post: {e!s}",
                "POST_DATABASE_ERROR",
                {"post_id": post_data.get("post_id"), "error_type": type(e).__name__}
            ) from e

    def get_post_by_id(self, post_id: str) -> RedditPost | None:
        """Retrieve a Reddit post by its Reddit post ID.

        Args:
            post_id: The Reddit post ID to search for

        Returns:
            RedditPost instance if found, None otherwise
        """
        if not post_id:
            return None

        try:
            post = (
                self.session.query(RedditPost)
                .filter(RedditPost.post_id == post_id)
                .first()
            )

            if post:
                logger.debug(f"Retrieved post with Reddit ID '{post_id}'")
            else:
                logger.debug(f"No post found with Reddit ID '{post_id}'")

            return post

        except SQLAlchemyError as e:
            logger.error(f"Error retrieving post '{post_id}': {e}")
            return None

    def get_latest_check_run(self, subreddit: str, topic: str) -> CheckRun | None:
        """Get the most recent check run for a subreddit and topic.

        Args:
            subreddit: The subreddit to search for
            topic: The topic to search for

        Returns:
            Most recent CheckRun instance if found, None otherwise
        """
        try:
            check_run = (
                self.session.query(CheckRun)
                .filter(CheckRun.subreddit == subreddit, CheckRun.topic == topic)
                .order_by(CheckRun.timestamp.desc())
                .first()
            )

            if check_run:
                logger.debug(
                    f"Found latest check run {check_run.id} for r/{subreddit} "
                    f"topic '{topic}' at {check_run.timestamp}"
                )
            else:
                logger.debug(f"No check runs found for r/{subreddit} topic '{topic}'")

            return check_run

        except SQLAlchemyError as e:
            logger.error(
                f"Error retrieving latest check run for r/{subreddit} "
                f"topic '{topic}': {e}"
            )
            return None

    def update_check_run_counters(
        self, check_run_id: int, posts_found: int, new_posts: int
    ) -> bool:
        """Update the post counters for a check run.

        Args:
            check_run_id: ID of the check run to update
            posts_found: Total posts found in this run
            new_posts: Number of new posts discovered

        Returns:
            True if update successful, False otherwise
        """
        try:
            check_run = self.session.get(CheckRun, check_run_id)

            if not check_run:
                logger.warning(f"Check run {check_run_id} not found for update")
                return False

            check_run.posts_found = posts_found
            check_run.new_posts = new_posts

            self.session.commit()

            logger.info(
                f"Updated check run {check_run_id}: {posts_found} posts found, "
                f"{new_posts} new posts"
            )

            return True

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Failed to update check run {check_run_id}: {e}")
            return False

    def get_posts_for_check_run(self, check_run_id: int) -> list[RedditPost]:
        """Get all posts associated with a specific check run.

        Args:
            check_run_id: ID of the check run

        Returns:
            List of RedditPost instances for the check run
        """
        try:
            posts = (
                self.session.query(RedditPost)
                .filter(RedditPost.check_run_id == check_run_id)
                .order_by(RedditPost.score.desc(), RedditPost.created_utc.desc())
                .all()
            )

            logger.debug(f"Retrieved {len(posts)} posts for check run {check_run_id}")

            return posts

        except SQLAlchemyError as e:
            logger.error(f"Error retrieving posts for check run {check_run_id}: {e}")
            return []

    def post_exists(self, post_id: str) -> bool:
        """Check if a post with the given Reddit ID already exists.

        Args:
            post_id: Reddit post ID to check

        Returns:
            True if post exists, False otherwise
        """
        if not post_id:
            return False

        try:
            exists = (
                self.session.query(RedditPost)
                .filter(RedditPost.post_id == post_id)
                .first()
            ) is not None

            return exists

        except SQLAlchemyError as e:
            logger.error(f"Error checking if post '{post_id}' exists: {e}")
            return False

    def get_check_run_by_id(self, check_run_id: int) -> CheckRun | None:
        """Get a check run by its database ID.

        Args:
            check_run_id: Database ID of the check run

        Returns:
            CheckRun instance if found, None otherwise
        """
        try:
            check_run = self.session.get(CheckRun, check_run_id)

            if check_run:
                logger.debug(f"Retrieved check run {check_run_id}")
            else:
                logger.debug(f"Check run {check_run_id} not found")

            return check_run

        except SQLAlchemyError as e:
            logger.error(f"Error retrieving check run {check_run_id}: {e}")
            return None

    @database_error_handler
    @database_operation_monitor("save_comment")
    def save_comment(self, comment_data: dict[str, Any], post_id: int) -> int:
        """Save a Reddit comment linked to a post with comprehensive validation.

        Args:
            comment_data: Dictionary containing comment data with required keys:
                - comment_id: Reddit comment ID (unique)
                - author: Comment author (can be None for deleted)
                - body: Comment body text
                - score: Comment score/upvotes
                - created_utc: When comment was created
                - parent_id: Parent comment ID (can be None for top-level)
                - is_submitter: Whether author is post submitter
                - stickied: Whether comment is stickied
                - distinguished: Moderator/admin status (can be None)
            post_id: Database ID of the post this comment belongs to

        Returns:
            The database ID of the saved comment

        Raises:
            StorageServiceError: If validation fails, post doesn't exist, or database operation fails
        """
        log_service_operation(logger, "StorageService", "save_comment_start",
                            comment_id=comment_data.get("comment_id"),
                            post_id=post_id)

        try:
            # STEP 1: Verify post exists before validation
            post = self.session.get(RedditPost, post_id)
            if not post:
                raise StorageServiceError(
                    f"Cannot save comment: Post with ID {post_id} does not exist",
                    "POST_NOT_FOUND",
                    {"post_id": post_id, "comment_id": comment_data.get("comment_id")}
                )

            # STEP 2: Prepare comment data for validation (add post_id)
            validation_data = comment_data.copy()
            validation_data["post_id"] = post_id

            # STEP 3: Validate input data before database operations
            try:
                validated_data = validate_comment_data(validation_data)
                log_service_operation(logger, "StorageService", "comment_validation_success",
                                    comment_id=validated_data["comment_id"],
                                    post_id=post_id)
            except DataValidationError as e:
                log_service_error(e, "StorageService", "comment_validation",
                                comment_id=comment_data.get("comment_id"),
                                post_id=post_id)
                raise StorageServiceError(
                    f"Reddit comment validation failed: {e.message}",
                    "COMMENT_VALIDATION_FAILED",
                    e.context
                ) from e

            # STEP 4: Create Comment instance from validated data
            comment = Comment(
                comment_id=validated_data["comment_id"],
                post_id=post_id,
                author=validated_data.get("author"),
                body=validated_data["body"],
                score=validated_data.get("score", 0),
                created_utc=validated_data["created_utc"],
                parent_id=validated_data.get("parent_id"),
                is_submitter=validated_data.get("is_submitter", False),
                stickied=validated_data.get("stickied", False),
                distinguished=validated_data.get("distinguished"),
                first_seen=datetime.now(UTC),
                last_updated=datetime.now(UTC),
            )

            # STEP 5: Save to database
            self.session.add(comment)
            self.session.commit()

            log_service_operation(logger, "StorageService", "save_comment_success",
                                comment_id=comment.comment_id,
                                db_id=comment.id,
                                post_id=post_id)

            return comment.id

        except StorageServiceError:
            # Re-raise storage service errors without wrapping
            raise
        except (SQLAlchemyError, KeyError) as e:
            self.session.rollback()
            # Let @database_error_handler decorator handle error logging and exception mapping
            raise StorageServiceError(
                f"Database operation failed while saving comment: {e!s}",
                "COMMENT_DATABASE_ERROR",
                {"comment_id": comment_data.get("comment_id"), "post_id": post_id, "error_type": type(e).__name__}
            ) from e

    def save_post_snapshot(
        self,
        post_id: int,
        check_run_id: int,
        score: int,
        num_comments: int,
        score_delta: int | None = None,
        comments_delta: int | None = None,
    ) -> int:
        """Save a point-in-time snapshot of a post's metrics.

        Args:
            post_id: Database ID of the post
            check_run_id: Database ID of the check run
            score: Post score at snapshot time
            num_comments: Number of comments at snapshot time
            score_delta: Change in score from previous snapshot (optional)
            comments_delta: Change in comments from previous snapshot (optional)

        Returns:
            The database ID of the saved snapshot

        Raises:
            RuntimeError: If snapshot saving fails or references don't exist
        """
        try:
            # Verify post and check run exist
            post = self.session.get(RedditPost, post_id)
            if not post:
                raise RuntimeError(f"Post with ID {post_id} does not exist")

            check_run = self.session.get(CheckRun, check_run_id)
            if not check_run:
                raise RuntimeError(f"Check run with ID {check_run_id} does not exist")

            snapshot = PostSnapshot(
                post_id=post_id,
                check_run_id=check_run_id,
                snapshot_time=datetime.now(UTC),
                score=score,
                num_comments=num_comments,
                score_delta=score_delta,
                comments_delta=comments_delta,
            )

            self.session.add(snapshot)
            self.session.commit()

            logger.info(
                f"Saved snapshot {snapshot.id} for post {post_id} "
                f"in check run {check_run_id}"
            )

            return snapshot.id

        except (SQLAlchemyError, KeyError) as e:
            self.session.rollback()
            logger.error(f"Failed to save post snapshot: {e}")
            raise RuntimeError(f"Failed to save post snapshot: {e}") from e

    @database_operation_monitor("get_new_posts_since")
    def get_new_posts_since(
        self, subreddit: str, timestamp: datetime
    ) -> list[RedditPost]:
        """Get posts from a subreddit that were created after a given timestamp.

        Args:
            subreddit: The subreddit to search in
            timestamp: Only return posts created after this time

        Returns:
            List of RedditPost instances ordered by score desc, then created_utc desc
        """
        try:
            posts = (
                self.session.query(RedditPost)
                .filter(
                    RedditPost.subreddit == subreddit,
                    RedditPost.created_utc > timestamp,
                )
                .order_by(RedditPost.score.desc(), RedditPost.created_utc.desc())
                .all()
            )

            logger.debug(
                f"Retrieved {len(posts)} posts from r/{subreddit} "
                f"created after {timestamp}"
            )

            return posts

        except SQLAlchemyError as e:
            logger.error(
                f"Error retrieving new posts from r/{subreddit} since {timestamp}: {e}"
            )
            return []

    def get_comments_for_post(self, post_id: int) -> list[Comment]:
        """Get all comments for a specific post.

        Args:
            post_id: Database ID of the post

        Returns:
            List of Comment instances ordered by score desc, then created_utc desc
        """
        try:
            comments = (
                self.session.query(Comment)
                .filter(Comment.post_id == post_id)
                .order_by(Comment.score.desc(), Comment.created_utc.desc())
                .all()
            )

            logger.debug(f"Retrieved {len(comments)} comments for post {post_id}")

            return comments

        except SQLAlchemyError as e:
            logger.error(f"Error retrieving comments for post {post_id}: {e}")
            return []

    @database_error_handler
    def bulk_save_comments(
        self, comments_data: list[dict[str, Any]], post_id: int
    ) -> int:
        """Bulk save multiple comments for a post efficiently with comprehensive validation.

        Args:
            comments_data: List of comment data dictionaries
            post_id: Database ID of the post these comments belong to

        Returns:
            Number of comments successfully saved

        Raises:
            StorageServiceError: If post doesn't exist or critical database error occurs
        """
        if not comments_data:
            return 0

        log_service_operation(logger, "StorageService", "bulk_save_comments_start",
                            post_id=post_id,
                            comment_count=len(comments_data))

        try:
            # STEP 1: Verify post exists first
            post = self.session.get(RedditPost, post_id)
            if not post:
                raise StorageServiceError(
                    f"Cannot bulk save comments: Post with ID {post_id} does not exist",
                    "POST_NOT_FOUND",
                    {"post_id": post_id, "comment_count": len(comments_data)}
                )

            # STEP 2: Validate each comment and prepare for bulk insertion
            validated_comments = []
            validation_failures = 0

            for i, comment_data in enumerate(comments_data):
                try:
                    # Prepare comment data for validation (add post_id)
                    validation_data = comment_data.copy()
                    validation_data["post_id"] = post_id

                    # Validate comment data
                    validated_data = validate_comment_data(validation_data)

                    # Create Comment instance from validated data
                    comment = Comment(
                        comment_id=validated_data["comment_id"],
                        post_id=post_id,
                        author=validated_data.get("author"),
                        body=validated_data["body"],
                        score=validated_data.get("score", 0),
                        created_utc=validated_data["created_utc"],
                        parent_id=validated_data.get("parent_id"),
                        is_submitter=validated_data.get("is_submitter", False),
                        stickied=validated_data.get("stickied", False),
                        distinguished=validated_data.get("distinguished"),
                        first_seen=datetime.now(UTC),
                        last_updated=datetime.now(UTC),
                    )
                    validated_comments.append(comment)

                except DataValidationError as e:
                    validation_failures += 1
                    log_service_error(e, "StorageService", "bulk_comment_validation",
                                    comment_id=comment_data.get("comment_id"),
                                    post_id=post_id,
                                    index=i)
                    # Continue processing other comments rather than failing entire batch
                    continue
                except KeyError as e:
                    validation_failures += 1
                    logger.warning(
                        f"Skipping comment {i} due to missing field {e}: "
                        f"{comment_data.get('comment_id', 'unknown')}"
                    )
                    continue

            # STEP 3: Bulk save validated comments
            saved_count = 0
            if validated_comments:
                log_service_operation(logger, "StorageService", "bulk_save_comments_validated",
                                    post_id=post_id,
                                    valid_comments=len(validated_comments),
                                    validation_failures=validation_failures)

                self.session.add_all(validated_comments)

                try:
                    self.session.commit()
                    saved_count = len(validated_comments)
                    log_service_operation(logger, "StorageService", "bulk_save_comments_success",
                                        post_id=post_id,
                                        saved_count=saved_count,
                                        validation_failures=validation_failures)

                except SQLAlchemyError as e:
                    self.session.rollback()
                    # If bulk commit fails, try individual saves to handle unique constraint violations
                    log_service_error(e, "StorageService", "bulk_commit_failed",
                                    post_id=post_id,
                                    comment_count=len(validated_comments))

                    for comment in validated_comments:
                        try:
                            # Start new transaction for each comment
                            self.session.add(comment)
                            self.session.commit()
                            saved_count += 1
                        except SQLAlchemyError as individual_error:
                            self.session.rollback()
                            logger.debug(
                                f"Failed to save individual comment "
                                f"{comment.comment_id}: {individual_error}"
                            )
                            continue

                    log_service_operation(logger, "StorageService", "bulk_save_comments_individual_success",
                                        post_id=post_id,
                                        saved_count=saved_count,
                                        validation_failures=validation_failures)

            if validation_failures > 0:
                logger.warning(
                    f"Bulk save completed with {validation_failures} validation failures out of "
                    f"{len(comments_data)} comments for post {post_id}"
                )

            return saved_count

        except StorageServiceError:
            # Re-raise storage service errors without wrapping
            raise
        except SQLAlchemyError as e:
            self.session.rollback()
            # Let @database_error_handler decorator handle error logging and exception mapping
            raise StorageServiceError(
                f"Database operation failed during bulk comment save: {e!s}",
                "BULK_COMMENT_DATABASE_ERROR",
                {"post_id": post_id, "comment_count": len(comments_data), "error_type": type(e).__name__}
            ) from e

    def get_posts_with_snapshots(
        self, subreddit: str, limit: int = 20
    ) -> list[RedditPost]:
        """Get posts that have snapshots for trend analysis.

        Args:
            subreddit: The subreddit to search in
            limit: Maximum number of posts to return

        Returns:
            List of RedditPost instances that have at least one snapshot
        """
        try:
            posts = (
                self.session.query(RedditPost)
                .join(PostSnapshot)
                .filter(RedditPost.subreddit == subreddit)
                .distinct()
                .order_by(RedditPost.score.desc())
                .limit(limit)
                .all()
            )

            logger.debug(
                f"Retrieved {len(posts)} posts with snapshots from r/{subreddit}"
            )

            return posts

        except SQLAlchemyError as e:
            logger.error(
                f"Error retrieving posts with snapshots from r/{subreddit}: {e}"
            )
            return []

    def get_comment_count_for_post(self, post_id: int) -> int:
        """Get the total number of comments for a post efficiently.

        Args:
            post_id: Database ID of the post

        Returns:
            Total number of comments for the post
        """
        try:
            count = (
                self.session.query(Comment).filter(Comment.post_id == post_id).count()
            )

            return count

        except SQLAlchemyError as e:
            logger.error(f"Error counting comments for post {post_id}: {e}")
            return 0

    @database_operation_monitor("cleanup_old_data")
    def cleanup_old_data(self, days_to_keep: int, batch_size: int = 100) -> int:
        """Remove check runs and associated data older than specified days.

        Args:
            days_to_keep: Number of days of data to retain
            batch_size: Number of records to process in each batch

        Returns:
            Number of check runs deleted

        Raises:
            ValueError: If days_to_keep is not positive
            RuntimeError: If cleanup operation fails
        """
        if days_to_keep <= 0:
            raise ValueError("days_to_keep must be positive")

        try:
            cutoff_date = datetime.now(UTC) - timedelta(days=days_to_keep)

            logger.info(
                f"Starting cleanup of data older than {cutoff_date} "
                f"(keeping {days_to_keep} days)"
            )

            # Find old check runs in batches
            total_deleted = 0

            while True:
                # Get a batch of old check runs
                old_check_runs = (
                    self.session.query(CheckRun)
                    .filter(CheckRun.timestamp < cutoff_date)
                    .limit(batch_size)
                    .all()
                )

                if not old_check_runs:
                    break

                # Delete this batch
                check_run_ids = [cr.id for cr in old_check_runs]

                # Delete check runs (cascades to posts, comments, snapshots)
                for check_run in old_check_runs:
                    self.session.delete(check_run)

                self.session.commit()

                batch_deleted = len(old_check_runs)
                total_deleted += batch_deleted

                logger.info(
                    f"Deleted batch of {batch_deleted} check runs "
                    f"(IDs: {check_run_ids})"
                )

            logger.info(f"Cleanup completed: {total_deleted} check runs deleted")
            return total_deleted

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Failed to cleanup old data: {e}")
            raise RuntimeError(f"Failed to cleanup old data: {e}") from e

    def archive_old_check_runs(self, days_to_keep: int, batch_size: int = 100) -> int:
        """Archive old check runs by preserving summaries but removing detailed data.

        This preserves check run records with their metadata but removes
        associated posts, comments, and snapshots to save space.

        Args:
            days_to_keep: Number of days of detailed data to retain
            batch_size: Number of records to process in each batch

        Returns:
            Number of check runs archived

        Raises:
            ValueError: If days_to_keep is not positive
            RuntimeError: If archive operation fails
        """
        if days_to_keep <= 0:
            raise ValueError("days_to_keep must be positive")

        try:
            cutoff_date = datetime.now(UTC) - timedelta(days=days_to_keep)

            logger.info(
                f"Starting archival of data older than {cutoff_date} "
                f"(keeping {days_to_keep} days of detailed data)"
            )

            # Find old check runs to archive (get all at once since we're not deleting the check runs)
            old_check_runs = (
                self.session.query(CheckRun)
                .filter(CheckRun.timestamp < cutoff_date)
                .all()
            )

            if not old_check_runs:
                logger.info("No check runs found for archival")
                return 0

            total_archived = 0

            # Process in batches for memory efficiency
            for i in range(0, len(old_check_runs), batch_size):
                batch = old_check_runs[i:i + batch_size]

                # For each check run in batch, delete associated posts (which cascades to comments and snapshots)
                for check_run in batch:
                    # Delete posts for this check run (cascades to comments and snapshots)
                    posts_deleted = (
                        self.session.query(RedditPost)
                        .filter(RedditPost.check_run_id == check_run.id)
                        .delete(synchronize_session=False)
                    )

                    if posts_deleted > 0:
                        logger.debug(f"Deleted {posts_deleted} posts for check run {check_run.id}")

                self.session.commit()

                batch_archived = len(batch)
                total_archived += batch_archived

                logger.info(
                    f"Archived batch of {batch_archived} check runs - preserved summaries, removed details"
                )

            logger.info(f"Archival completed: {total_archived} check runs archived")
            return total_archived

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Failed to archive old check runs: {e}")
            raise RuntimeError(f"Failed to archive old check runs: {e}") from e

    @database_operation_monitor("get_storage_statistics")
    def get_storage_statistics(
        self,
        include_date_breakdown: bool = False,
        include_size_estimation: bool = False,
        retention_days: int | None = None,
    ) -> dict[str, Any]:
        """Get comprehensive storage statistics for the database.

        Args:
            include_date_breakdown: Include date-based analysis
            include_size_estimation: Include storage size estimates
            retention_days: Include retention analysis for specified days

        Returns:
            Dictionary containing storage statistics and analysis
        """
        try:
            stats: dict[str, Any] = {}

            # Basic counts
            stats["check_runs"] = self.session.query(CheckRun).count()
            stats["reddit_posts"] = self.session.query(RedditPost).count()
            stats["comments"] = self.session.query(Comment).count()
            stats["post_snapshots"] = self.session.query(PostSnapshot).count()

            # Date breakdown if requested
            if include_date_breakdown:
                oldest_check_run = (
                    self.session.query(CheckRun)
                    .order_by(CheckRun.timestamp.asc())
                    .first()
                )
                newest_check_run = (
                    self.session.query(CheckRun)
                    .order_by(CheckRun.timestamp.desc())
                    .first()
                )

                date_breakdown = {
                    "oldest_check_run": oldest_check_run.timestamp
                    if oldest_check_run
                    else None,
                    "newest_check_run": newest_check_run.timestamp
                    if newest_check_run
                    else None,
                    "data_span_days": (
                        (newest_check_run.timestamp - oldest_check_run.timestamp).days
                        if oldest_check_run and newest_check_run
                        else 0
                    ),
                }

                stats["date_breakdown"] = date_breakdown
                stats["oldest_check_run"] = date_breakdown["oldest_check_run"]
                stats["newest_check_run"] = date_breakdown["newest_check_run"]

            # Size estimation if requested
            if include_size_estimation:
                # Rough estimates based on typical record sizes
                size_estimates = {
                    "check_run_bytes": 200,  # Basic metadata
                    "reddit_post_bytes": 2000,  # Title, content, metadata
                    "comment_bytes": 500,  # Comment text and metadata
                    "post_snapshot_bytes": 100,  # Just metrics
                }

                total_bytes = (
                    stats["check_runs"] * size_estimates["check_run_bytes"]
                    + stats["reddit_posts"] * size_estimates["reddit_post_bytes"]
                    + stats["comments"] * size_estimates["comment_bytes"]
                    + stats["post_snapshots"] * size_estimates["post_snapshot_bytes"]
                )

                estimated_size = {
                    "total_bytes": total_bytes,
                    "total_mb": round(total_bytes / (1024 * 1024), 2),
                }

                size_by_table = {
                    "check_runs_mb": round(
                        (stats["check_runs"] * size_estimates["check_run_bytes"])
                        / (1024 * 1024),
                        2,
                    ),
                    "reddit_posts_mb": round(
                        (stats["reddit_posts"] * size_estimates["reddit_post_bytes"])
                        / (1024 * 1024),
                        2,
                    ),
                    "comments_mb": round(
                        (stats["comments"] * size_estimates["comment_bytes"])
                        / (1024 * 1024),
                        2,
                    ),
                    "post_snapshots_mb": round(
                        (
                            stats["post_snapshots"]
                            * size_estimates["post_snapshot_bytes"]
                        )
                        / (1024 * 1024),
                        2,
                    ),
                }

                stats["estimated_size"] = estimated_size
                stats["size_by_table"] = size_by_table

            # Retention analysis if requested
            if retention_days:
                cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)

                old_check_runs = (
                    self.session.query(CheckRun)
                    .filter(CheckRun.timestamp < cutoff_date)
                    .count()
                )

                recent_check_runs = (
                    self.session.query(CheckRun)
                    .filter(CheckRun.timestamp >= cutoff_date)
                    .count()
                )

                retention_analysis = {
                    "retention_days": retention_days,
                    "cutoff_date": cutoff_date,
                    "data_to_cleanup": old_check_runs,
                    "data_to_keep": recent_check_runs,
                    "cleanup_percentage": round(
                        (old_check_runs / (old_check_runs + recent_check_runs) * 100)
                        if (old_check_runs + recent_check_runs) > 0
                        else 0,
                        1,
                    ),
                }

                stats["retention_analysis"] = retention_analysis

            logger.debug(f"Generated storage statistics: {stats}")
            return stats

        except SQLAlchemyError as e:
            logger.error(f"Error generating storage statistics: {e}")
            return {
                "error": str(e),
                "check_runs": 0,
                "reddit_posts": 0,
                "comments": 0,
                "post_snapshots": 0,
            }

    def cleanup_old_data_from_config(self) -> int:
        """Cleanup old data using configuration settings.

        Returns:
            Number of check runs deleted
        """
        from app.core.config import config

        retention_days = getattr(config, "DATA_RETENTION_DAYS", 30)
        batch_size = getattr(config, "CLEANUP_BATCH_SIZE", 100)

        logger.info(
            f"Starting config-based cleanup: {retention_days} days retention, "
            f"batch size {batch_size}"
        )

        return self.cleanup_old_data(days_to_keep=retention_days, batch_size=batch_size)

    def archive_old_data_from_config(self) -> int:
        """Archive old data using configuration settings.

        Returns:
            Number of check runs archived
        """
        from app.core.config import config

        retention_days = getattr(config, "DATA_RETENTION_DAYS", 30)
        batch_size = getattr(config, "CLEANUP_BATCH_SIZE", 100)
        archive_enabled = getattr(config, "ARCHIVE_OLD_DATA", False)

        if not archive_enabled:
            logger.info("Archival is disabled in configuration")
            return 0

        logger.info(
            f"Starting config-based archival: {retention_days} days retention, "
            f"batch size {batch_size}"
        )

        return self.archive_old_check_runs(
            days_to_keep=retention_days, batch_size=batch_size
        )

    def get_data_retention_status(self) -> dict[str, Any]:
        """Get current data retention status and recommendations.

        Returns:
            Dictionary with retention status and cleanup recommendations
        """
        from app.core.config import config

        retention_days = getattr(config, "DATA_RETENTION_DAYS", 30)
        archive_enabled = getattr(config, "ARCHIVE_OLD_DATA", False)

        stats = self.get_storage_statistics(
            include_date_breakdown=True,
            include_size_estimation=True,
            retention_days=retention_days,
        )

        # Calculate recommendations
        recommendations = []

        if "retention_analysis" in stats:
            cleanup_count = stats["retention_analysis"]["data_to_cleanup"]
            if cleanup_count > 0:
                if archive_enabled:
                    recommendations.append(
                        f"Archive {cleanup_count} old check runs to preserve summaries"
                    )
                else:
                    recommendations.append(
                        f"Delete {cleanup_count} old check runs to free space"
                    )

        if stats.get("estimated_size", {}).get("total_mb", 0) > 100:
            recommendations.append("Consider enabling archival to reduce storage usage")

        if not recommendations:
            recommendations.append("No cleanup needed at this time")

        return {
            "current_config": {
                "retention_days": retention_days,
                "archive_enabled": archive_enabled,
            },
            "storage_stats": stats,
            "recommendations": recommendations,
            "last_checked": datetime.now(UTC),
        }

    def get_posts_in_timeframe(
        self, subreddit: str, start_date: datetime, end_date: datetime
    ) -> list[RedditPost]:
        """Get all posts in a specific timeframe for trend analysis.

        Args:
            subreddit: Name of the subreddit
            start_date: Start of time window (inclusive)
            end_date: End of time window (inclusive)

        Returns:
            List of RedditPost objects within the timeframe

        Raises:
            RuntimeError: If database query fails
        """
        try:
            posts = (
                self.session.query(RedditPost)
                .filter(
                    RedditPost.subreddit == subreddit,
                    RedditPost.created_utc >= start_date,
                    RedditPost.created_utc <= end_date,
                )
                .order_by(RedditPost.created_utc.desc())
                .all()
            )

            logger.debug(
                f"Retrieved {len(posts)} posts from r/{subreddit} "
                f"between {start_date.strftime('%Y-%m-%d')} and {end_date.strftime('%Y-%m-%d')}"
            )

            return posts

        except SQLAlchemyError as e:
            logger.error(
                f"Database error retrieving posts for r/{subreddit} "
                f"in timeframe {start_date} to {end_date}: {e}"
            )
            raise RuntimeError(f"Failed to retrieve posts in timeframe: {e}") from e

    def get_check_run_history(
        self,
        subreddit: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        limit: int = 20
    ) -> tuple[list[CheckRun], int]:
        """Get paginated check run history for a subreddit.

        Args:
            subreddit: Subreddit name
            start_date: Optional start date filter
            end_date: Optional end date filter
            page: Page number (1-based)
            limit: Items per page

        Returns:
            Tuple of (check_runs_list, total_count)

        Raises:
            RuntimeError: If query fails
        """
        try:
            query = self.session.query(CheckRun).filter(
                CheckRun.subreddit == subreddit
            )

            # Apply date filters if provided
            if start_date:
                query = query.filter(CheckRun.timestamp >= start_date)
            if end_date:
                query = query.filter(CheckRun.timestamp <= end_date)

            # Get total count for pagination
            total_count = query.count()

            # Apply pagination and ordering
            offset = (page - 1) * limit
            check_runs = query.order_by(CheckRun.timestamp.desc()).offset(offset).limit(limit).all()

            logger.info(
                f"Retrieved {len(check_runs)} check runs for r/{subreddit} "
                f"(page {page}, limit {limit}, total: {total_count})"
            )

            return check_runs, total_count

        except SQLAlchemyError as e:
            logger.error(f"Database error retrieving check run history for r/{subreddit}: {e}")
            raise RuntimeError(f"Failed to retrieve check run history: {e}") from e

    def get_subreddit_date_range(self, subreddit: str) -> tuple[datetime | None, datetime | None]:
        """Get the date range of data available for a subreddit.

        Args:
            subreddit: Subreddit name

        Returns:
            Tuple of (earliest_date, latest_date) or (None, None) if no data

        Raises:
            RuntimeError: If query fails
        """
        try:
            from sqlalchemy import func

            result = self.session.query(
                func.min(CheckRun.timestamp).label('earliest'),
                func.max(CheckRun.timestamp).label('latest')
            ).filter(CheckRun.subreddit == subreddit).first()

            if result and result.earliest:
                logger.info(
                    f"Date range for r/{subreddit}: {result.earliest} to {result.latest}"
                )
                return result.earliest, result.latest
            else:
                logger.info(f"No data found for r/{subreddit}")
                return None, None

        except SQLAlchemyError as e:
            logger.error(f"Database error getting date range for r/{subreddit}: {e}")
            raise RuntimeError(f"Failed to get date range: {e}") from e
