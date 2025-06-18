# ABOUTME: Optimized storage service with query optimizations, eager loading, and performance enhancements
# ABOUTME: Extends base storage service with N+1 query prevention, bulk operations, and strategic caching

from datetime import UTC, datetime, timedelta
import logging
from typing import Any

import sqlalchemy as sa
from sqlalchemy import and_, desc, func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.models.check_run import CheckRun
from app.models.comment import Comment
from app.models.reddit_post import RedditPost
from app.services.storage_service import StorageService

# Set up logging
logger = logging.getLogger(__name__)


class OptimizedStorageService(StorageService):
    """Optimized storage service with advanced query optimizations.

    This service extends the base StorageService with:
    - N+1 query prevention through eager loading
    - Optimized bulk operations
    - Strategic query optimization
    - Performance monitoring hooks
    """

    def __init__(self, session: Session) -> None:
        """Initialize OptimizedStorageService with database session.

        Args:
            session: SQLAlchemy session for database operations
        """
        super().__init__(session)
        self._query_count = 0
        self._cache: dict[str, Any] = {}
        self._enable_query_logging = False

    def enable_query_logging(self, enabled: bool = True) -> None:
        """Enable or disable query logging for performance analysis.

        Args:
            enabled: Whether to enable query logging
        """
        self._enable_query_logging = enabled
        if enabled:
            logger.info("Query logging enabled for performance analysis")

    def get_query_count(self) -> int:
        """Get the number of queries executed in this session.

        Returns:
            Number of queries executed
        """
        return self._query_count

    def reset_query_count(self) -> None:
        """Reset the query counter."""
        self._query_count = 0

    def _log_query(self, query_description: str) -> None:
        """Log query execution for performance monitoring.

        Args:
            query_description: Description of the query being executed
        """
        self._query_count += 1
        if self._enable_query_logging:
            logger.debug(f"Query #{self._query_count}: {query_description}")

    def get_posts_with_comments_optimized(
        self,
        subreddit: str,
        limit: int = 50,
        with_snapshots: bool = False
    ) -> list[RedditPost]:
        """Get posts with their comments using optimized queries.

        This method prevents N+1 queries by using eager loading to fetch
        posts and their related comments in a minimal number of queries.

        Args:
            subreddit: Subreddit to filter by
            limit: Maximum number of posts to return
            with_snapshots: Whether to also load post snapshots

        Returns:
            List of posts with eagerly loaded comments
        """
        self._log_query(f"get_posts_with_comments_optimized(subreddit={subreddit}, limit={limit})")

        try:
            # Use joined loading for comments to prevent N+1 queries
            query = (
                self.session.query(RedditPost)
                .options(selectinload(RedditPost.comments))  # Eager load comments
                .filter(RedditPost.subreddit == subreddit)
                .order_by(desc(RedditPost.score))
                .limit(limit)
            )

            # Optionally include snapshots
            if with_snapshots:
                query = query.options(selectinload(RedditPost.snapshots))

            posts = query.all()

            logger.info(
                f"Retrieved {len(posts)} posts with comments for r/{subreddit} "
                f"using optimized query"
            )

            return posts

        except SQLAlchemyError as e:
            logger.error(f"Failed to get optimized posts with comments: {e}")
            raise RuntimeError(f"Failed to get posts with comments: {e}") from e

    def get_check_run_with_posts_optimized(self, check_run_id: int) -> CheckRun | None:
        """Get a check run with all its posts using optimized loading.

        Args:
            check_run_id: ID of the check run to retrieve

        Returns:
            CheckRun with eagerly loaded posts, or None if not found
        """
        self._log_query(f"get_check_run_with_posts_optimized(check_run_id={check_run_id})")

        try:
            check_run = (
                self.session.query(CheckRun)
                .options(selectinload(CheckRun.reddit_posts))  # Eager load posts
                .filter(CheckRun.id == check_run_id)
                .first()
            )

            if check_run:
                logger.info(
                    f"Retrieved check run {check_run_id} with {len(check_run.reddit_posts)} posts "
                    f"using optimized query"
                )

            return check_run

        except SQLAlchemyError as e:
            logger.error(f"Failed to get optimized check run: {e}")
            raise RuntimeError(f"Failed to get check run with posts: {e}") from e

    def bulk_get_posts_by_ids(self, post_ids: list[str]) -> dict[str, RedditPost]:
        """Efficiently retrieve multiple posts by their IDs.

        This method uses a single query with IN clause instead of multiple
        individual queries, significantly improving performance.

        Args:
            post_ids: List of post IDs to retrieve

        Returns:
            Dictionary mapping post_id to RedditPost objects
        """
        if not post_ids:
            return {}

        self._log_query(f"bulk_get_posts_by_ids(count={len(post_ids)})")

        try:
            # Single query with IN clause instead of multiple individual queries
            posts = (
                self.session.query(RedditPost)
                .filter(RedditPost.post_id.in_(post_ids))
                .all()
            )

            # Convert to dictionary for O(1) lookup
            posts_dict = {post.post_id: post for post in posts}

            logger.info(f"Retrieved {len(posts)} posts in single bulk query")

            return posts_dict

        except SQLAlchemyError as e:
            logger.error(f"Failed to bulk get posts: {e}")
            raise RuntimeError(f"Failed to bulk get posts: {e}") from e

    def get_posts_with_statistics(
        self,
        subreddit: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Get posts with computed statistics using efficient aggregation.

        This method uses database-level aggregation instead of Python loops
        to compute statistics, significantly improving performance.

        Args:
            subreddit: Subreddit to filter by
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of dictionaries with post data and statistics
        """
        self._log_query(f"get_posts_with_statistics(subreddit={subreddit})")

        try:
            # Build query with aggregations
            query = (
                self.session.query(
                    RedditPost,
                    func.count(Comment.id).label('comment_count'),
                    func.avg(Comment.score).label('avg_comment_score'),
                    func.max(Comment.score).label('max_comment_score')
                )
                .outerjoin(Comment, RedditPost.post_id == Comment.post_id)
                .filter(RedditPost.subreddit == subreddit)
                .group_by(RedditPost.id)
            )

            # Apply date filters if provided
            if start_date:
                query = query.filter(RedditPost.created_utc >= start_date)
            if end_date:
                query = query.filter(RedditPost.created_utc <= end_date)

            results = query.all()

            # Convert to dictionaries with statistics
            posts_with_stats = []
            for post, comment_count, avg_score, max_score in results:
                posts_with_stats.append({
                    'post': post,
                    'comment_count': comment_count or 0,
                    'avg_comment_score': float(avg_score) if avg_score else 0.0,
                    'max_comment_score': max_score or 0,
                    'engagement_ratio': (comment_count or 0) / max(post.score, 1)
                })

            logger.info(
                f"Retrieved {len(posts_with_stats)} posts with statistics "
                f"using efficient aggregation"
            )

            return posts_with_stats

        except SQLAlchemyError as e:
            logger.error(f"Failed to get posts with statistics: {e}")
            raise RuntimeError(f"Failed to get posts with statistics: {e}") from e

    def get_trending_posts_optimized(
        self,
        subreddit: str,
        time_window_hours: int = 24,
        min_score: int = 10
    ) -> list[dict[str, Any]]:
        """Get trending posts using optimized subqueries and aggregations.

        Args:
            subreddit: Subreddit to analyze
            time_window_hours: Time window for trend analysis
            min_score: Minimum score threshold

        Returns:
            List of trending posts with computed metrics
        """
        self._log_query(f"get_trending_posts_optimized(subreddit={subreddit})")

        # Enable query logging for debugging
        self.enable_query_logging(True)

        try:
            cutoff_time = datetime.now(UTC) - timedelta(hours=time_window_hours)
            logger.debug(f"Cutoff time: {cutoff_time}, time_window_hours: {time_window_hours}")

            # Use subquery to calculate engagement metrics efficiently
            # PostgreSQL-compatible age calculation
            subquery = (
                self.session.query(
                    RedditPost.post_id,
                    RedditPost.score,
                    RedditPost.num_comments,
                    RedditPost.created_utc,
                    func.count(Comment.id).label('actual_comments'),
                    func.cast(
                        (func.extract('epoch', func.now()) - func.extract('epoch', RedditPost.created_utc)),
                        sa.Integer
                    ).label('age_seconds')
                )
                .outerjoin(Comment)
                .filter(
                    and_(
                        RedditPost.subreddit == subreddit,
                        RedditPost.created_utc >= cutoff_time,
                        RedditPost.score >= min_score
                    )
                )
                .group_by(RedditPost.id)
                .subquery()
            )

            # Calculate trending score using database functions
            # Use CASE statement for SQLite compatibility (replaces greatest function)
            from sqlalchemy import case

            # Handle potential None values in age and score calculations
            safe_age_seconds = case(
                (subquery.c.age_seconds.is_(None), 3600),  # Default to 1 hour if None
                else_=subquery.c.age_seconds
            )
            age_hours = safe_age_seconds / 3600
            safe_age_hours = case(
                (age_hours < 1, 1),
                else_=age_hours
            )

            safe_score = case(
                (subquery.c.score.is_(None), 0),  # Default to 0 if None
                else_=subquery.c.score
            )

            trending_posts = (
                self.session.query(
                    subquery.c.post_id,
                    subquery.c.score,
                    subquery.c.num_comments,
                    subquery.c.actual_comments,
                    subquery.c.age_seconds,
                    (safe_score / safe_age_hours).label('trending_score')
                )
                .order_by(text('trending_score DESC'))
                .limit(50)
                .all()
            )

            # Convert to dictionaries
            results = []
            for row in trending_posts:
                # Debug null values
                logger.debug(f"Row values: post_id={row.post_id}, score={row.score}, age_seconds={row.age_seconds}, trending_score={row.trending_score}")

                # Handle potential None values safely
                age_seconds = row.age_seconds if row.age_seconds is not None else 0
                age_hours = age_seconds / 3600
                trending_score = row.trending_score if row.trending_score is not None else 0.0

                results.append({
                    'post_id': row.post_id,
                    'score': row.score or 0,
                    'num_comments': row.num_comments or 0,
                    'actual_comments': row.actual_comments or 0,
                    'age_hours': age_hours,
                    'trending_score': float(trending_score)
                })

            logger.info(f"Found {len(results)} trending posts using optimized query")

            return results

        except SQLAlchemyError as e:
            logger.error(f"Failed to get trending posts: {e}")
            raise RuntimeError(f"Failed to get trending posts: {e}") from e

    def analyze_query_performance(self) -> dict[str, Any]:
        """Analyze query performance for the current session.

        Returns:
            Dictionary with performance metrics
        """
        try:
            # Get SQLite query analyzer stats
            bind_url = getattr(self.session.bind, 'url', None)
            if bind_url and 'sqlite' in str(bind_url):
                # SQLite-specific query analysis
                result = self.session.execute(text("PRAGMA optimize")).fetchall()
                cache_stats = self.session.execute(text("PRAGMA cache_size")).fetchone()

                return {
                    'query_count': self._query_count,
                    'cache_size': cache_stats[0] if cache_stats else 0,
                    'database_type': 'sqlite',
                    'optimization_applied': len(result) > 0
                }
            else:
                # PostgreSQL-specific analysis would go here
                return {
                    'query_count': self._query_count,
                    'database_type': 'postgresql'
                }

        except SQLAlchemyError as e:
            logger.warning(f"Could not analyze query performance: {e}")
            return {
                'query_count': self._query_count,
                'analysis_error': str(e)
            }

    def optimize_database_performance(self) -> dict[str, Any]:
        """Apply database-specific performance optimizations.

        Returns:
            Dictionary with optimization results
        """
        optimizations_applied = []

        try:
            bind_url = getattr(self.session.bind, 'url', None)
            if bind_url and 'sqlite' in str(bind_url):
                # Apply SQLite optimizations
                self.session.execute(text("PRAGMA optimize"))
                optimizations_applied.append("SQLite PRAGMA optimize")

                # Analyze database statistics
                self.session.execute(text("ANALYZE"))
                optimizations_applied.append("SQLite ANALYZE")

                logger.info("Applied SQLite performance optimizations")

            else:
                # PostgreSQL optimizations would go here
                self.session.execute(text("VACUUM ANALYZE"))
                optimizations_applied.append("PostgreSQL VACUUM ANALYZE")

                logger.info("Applied PostgreSQL performance optimizations")

            return {
                'success': True,
                'optimizations_applied': optimizations_applied
            }

        except SQLAlchemyError as e:
            logger.error(f"Failed to apply performance optimizations: {e}")
            return {
                'success': False,
                'error': str(e),
                'optimizations_applied': optimizations_applied
            }

    def get_memory_efficient_comment_stream(
        self,
        post_id: str,
        batch_size: int = 100
    ) -> Any:
        """Get comments for a post using memory-efficient streaming.

        This method yields comments in batches to avoid loading large
        comment trees into memory all at once.

        Args:
            post_id: ID of the post to get comments for
            batch_size: Number of comments to load per batch

        Yields:
            Batches of comments
        """
        self._log_query(f"get_memory_efficient_comment_stream(post_id={post_id})")

        try:
            offset = 0
            while True:
                comments_batch = (
                    self.session.query(Comment)
                    .filter(Comment.post_id == post_id)
                    .order_by(Comment.score.desc())
                    .offset(offset)
                    .limit(batch_size)
                    .all()
                )

                if not comments_batch:
                    break

                yield comments_batch
                offset += batch_size

                # Optional: Force garbage collection between batches
                import gc
                gc.collect()

        except SQLAlchemyError as e:
            logger.error(f"Failed to stream comments: {e}")
            raise RuntimeError(f"Failed to stream comments: {e}") from e

    def batch_update_post_scores(
        self,
        score_updates: dict[str, int]
    ) -> int:
        """Efficiently update multiple post scores in a single transaction.

        Args:
            score_updates: Dictionary mapping post_id to new score

        Returns:
            Number of posts updated
        """
        if not score_updates:
            return 0

        self._log_query(f"batch_update_post_scores(count={len(score_updates)})")

        try:
            updated_count = 0

            # Use bulk update with CASE statement for efficiency
            for post_id, new_score in score_updates.items():
                result = (
                    self.session.query(RedditPost)
                    .filter(RedditPost.post_id == post_id)
                    .update(
                        {
                            RedditPost.score: new_score,
                            RedditPost.last_updated: datetime.now(UTC)
                        },
                        synchronize_session=False  # Faster for bulk updates
                    )
                )
                updated_count += result

            self.session.commit()

            logger.info(f"Batch updated {updated_count} post scores")

            return updated_count

        except SQLAlchemyError as e:
            self.session.rollback()
            logger.error(f"Failed to batch update post scores: {e}")
            raise RuntimeError(f"Failed to batch update scores: {e}") from e

    def get_performance_report(self) -> dict[str, Any]:
        """Generate a comprehensive performance report.

        Returns:
            Dictionary with performance metrics and recommendations
        """
        try:
            # Get basic statistics
            total_posts = self.session.query(func.count(RedditPost.id)).scalar()
            total_comments = self.session.query(func.count(Comment.id)).scalar()
            total_check_runs = self.session.query(func.count(CheckRun.id)).scalar()

            # Get query performance metrics
            query_metrics = self.analyze_query_performance()

            # Calculate recommendations
            recommendations = []
            if query_metrics.get('query_count', 0) > 100:
                recommendations.append("Consider implementing caching for frequently accessed data")

            if total_comments > 10000:
                recommendations.append("Consider archiving old comments to improve query performance")

            return {
                'database_statistics': {
                    'total_posts': total_posts,
                    'total_comments': total_comments,
                    'total_check_runs': total_check_runs
                },
                'query_metrics': query_metrics,
                'recommendations': recommendations,
                'generated_at': datetime.now(UTC).isoformat()
            }

        except SQLAlchemyError as e:
            logger.error(f"Failed to generate performance report: {e}")
            return {
                'error': str(e),
                'generated_at': datetime.now(UTC).isoformat()
            }
