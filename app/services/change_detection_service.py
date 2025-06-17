# ABOUTME: ChangeDetectionService for identifying changes in Reddit posts over time
# ABOUTME: Compares current posts with stored data to detect new posts and engagement changes

from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.comment import Comment
from app.models.reddit_post import RedditPost
from app.models.types import (
    ActivityPattern,
    ChangeDetectionResult,
    EngagementDelta,
    PostUpdate,
    TrendData,
)
from app.services.storage_service import StorageService

# Set up logging
logger = logging.getLogger(__name__)


class ChangeDetectionService:
    """Service for detecting changes in Reddit posts and engagement.

    This service compares current post data from Reddit with previously
    stored data to identify new posts and track engagement changes.
    """

    def __init__(self, session: Session, storage_service: StorageService) -> None:
        """Initialize ChangeDetectionService.

        Args:
            session: SQLAlchemy session for database operations
            storage_service: StorageService instance for data access
        """
        self.session = session
        self.storage_service = storage_service

    def find_new_posts(
        self, current_posts: list[dict[str, Any]], last_check_time: datetime
    ) -> list[PostUpdate]:
        """Find posts that are new since the last check.

        Args:
            current_posts: List of current post data from Reddit API
            last_check_time: Timestamp of the last check run

        Returns:
            List of PostUpdate objects for new posts
        """
        if not current_posts:
            return []

        new_posts: list[PostUpdate] = []

        try:
            for post_data in current_posts:
                try:
                    # Check if post exists in database
                    post_id = post_data.get('post_id')
                    if not post_id:
                        logger.warning("Post data missing post_id, skipping")
                        continue

                    try:
                        existing_post = self.storage_service.get_post_by_id(post_id)
                    except SQLAlchemyError as db_error:
                        logger.error(f"Database error checking post {post_id}: {db_error}")
                        continue

                    # If post doesn't exist in database and meets time criteria
                    post_created = post_data.get('created_utc', datetime.now(UTC))
                    # Ensure both timestamps are timezone-aware for comparison
                    if isinstance(post_created, datetime) and post_created.tzinfo is None:
                        post_created = post_created.replace(tzinfo=UTC)
                    if isinstance(last_check_time, datetime) and last_check_time.tzinfo is None:
                        last_check_time = last_check_time.replace(tzinfo=UTC)

                    if existing_post is None and post_created > last_check_time:
                        new_post = PostUpdate(
                            post_id=0,  # Will be set when saved to database
                            reddit_post_id=post_id,
                            subreddit=post_data.get('subreddit', ''),
                            title=post_data.get('title', ''),
                            update_type='new',
                            current_score=post_data.get('score', 0),
                            current_comments=post_data.get('num_comments', 0),
                            current_timestamp=datetime.now(UTC),
                            previous_score=None,
                            previous_comments=None,
                            previous_timestamp=None,
                            engagement_delta=None
                        )

                        new_posts.append(new_post)

                        logger.debug(
                            f"Found new post: {post_id} in r/{post_data.get('subreddit')}"
                        )

                except (KeyError, TypeError) as e:
                    logger.warning(f"Error processing post data: {e}")
                    continue

        except SQLAlchemyError as e:
            logger.error(f"Database error finding new posts: {e}")
            return []

        logger.info(f"Found {len(new_posts)} new posts since {last_check_time}")
        return new_posts

    def find_updated_posts(
        self, current_posts: list[dict[str, Any]]
    ) -> list[PostUpdate]:
        """Find posts that have engagement changes since last stored.

        Args:
            current_posts: List of current post data from Reddit API

        Returns:
            List of PostUpdate objects for posts with changes
        """
        if not current_posts:
            return []

        updated_posts: list[PostUpdate] = []

        try:
            for post_data in current_posts:
                try:
                    post_id = post_data.get('post_id')
                    if not post_id:
                        continue

                    # Get existing post from database
                    existing_post = self.storage_service.get_post_by_id(post_id)
                    if existing_post is None:
                        # Post not in database, not an update
                        continue

                    # Compare current vs stored data
                    comparison = self._compare_posts(
                        {
                            'score': existing_post.score,
                            'num_comments': existing_post.num_comments
                        },
                        {
                            'score': post_data.get('score', 0),
                            'num_comments': post_data.get('num_comments', 0)
                        }
                    )

                    if comparison['has_changes']:
                        # Determine update type
                        if comparison['score_changed'] and comparison['comments_changed']:
                            update_type = 'both_change'
                        elif comparison['score_changed']:
                            update_type = 'score_change'
                        else:
                            update_type = 'comment_change'

                        # Calculate engagement delta
                        current_timestamp = datetime.now(UTC)
                        engagement_delta = self.calculate_engagement_delta(
                            post_id,
                            current_score=post_data.get('score', 0),
                            current_comments=post_data.get('num_comments', 0),
                            current_timestamp=current_timestamp
                        )

                        updated_post = PostUpdate(
                            post_id=existing_post.id,
                            reddit_post_id=post_id,
                            subreddit=existing_post.subreddit,
                            title=existing_post.title,
                            update_type=update_type,
                            current_score=post_data.get('score', 0),
                            current_comments=post_data.get('num_comments', 0),
                            current_timestamp=current_timestamp,
                            previous_score=existing_post.score,
                            previous_comments=existing_post.num_comments,
                            previous_timestamp=existing_post.last_updated,
                            engagement_delta=engagement_delta
                        )

                        updated_posts.append(updated_post)

                        logger.debug(
                            f"Found updated post: {post_id} with {update_type} "
                            f"(score: {comparison['score_delta']:+}, "
                            f"comments: {comparison['comments_delta']:+})"
                        )

                except (KeyError, TypeError) as e:
                    logger.warning(f"Error processing post update: {e}")
                    continue

        except SQLAlchemyError as e:
            logger.error(f"Database error finding updated posts: {e}")
            return []

        logger.info(f"Found {len(updated_posts)} posts with engagement changes")
        return updated_posts

    def calculate_engagement_delta(
        self,
        post_id: str,
        current_score: int,
        current_comments: int,
        current_timestamp: datetime
    ) -> EngagementDelta | None:
        """Calculate engagement delta for a post.

        Args:
            post_id: Reddit post ID
            current_score: Current post score
            current_comments: Current comment count
            current_timestamp: Current timestamp

        Returns:
            EngagementDelta object or None if no previous data
        """
        try:
            # Get previous post data
            existing_post = self.storage_service.get_post_by_id(post_id)
            if existing_post is None:
                logger.debug(f"No previous data for post {post_id}")
                return None

            # Calculate time span - handle timezone-aware comparisons
            last_updated = existing_post.last_updated
            if isinstance(last_updated, datetime) and last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=UTC)
            if isinstance(current_timestamp, datetime) and current_timestamp.tzinfo is None:
                current_timestamp = current_timestamp.replace(tzinfo=UTC)

            time_diff = current_timestamp - last_updated
            time_span_hours = max(time_diff.total_seconds() / 3600, 0.001)  # Minimum 0.001 hours

            # Calculate deltas
            score_delta = current_score - existing_post.score
            comments_delta = current_comments - existing_post.num_comments

            # Calculate engagement rate (score change per hour)
            engagement_rate = score_delta / time_span_hours

            delta = EngagementDelta(
                post_id=post_id,
                score_delta=score_delta,
                comments_delta=comments_delta,
                previous_score=existing_post.score,
                current_score=current_score,
                previous_comments=existing_post.num_comments,
                current_comments=current_comments,
                time_span_hours=time_span_hours,
                engagement_rate=engagement_rate
            )

            logger.debug(
                f"Calculated engagement delta for {post_id}: "
                f"score {score_delta:+}, comments {comments_delta:+}, "
                f"rate {engagement_rate:.2f}/hr"
            )

            return delta

        except SQLAlchemyError as e:
            logger.error(f"Error calculating engagement delta for {post_id}: {e}")
            return None

    def _compare_posts(
        self, old_post_data: dict[str, Any], new_post_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Compare two posts to identify changes.

        Args:
            old_post_data: Previous post data
            new_post_data: Current post data

        Returns:
            Dictionary with comparison results
        """
        old_score = old_post_data.get('score', 0)
        old_comments = old_post_data.get('num_comments', 0)
        new_score = new_post_data.get('score', 0)
        new_comments = new_post_data.get('num_comments', 0)

        score_delta = new_score - old_score
        comments_delta = new_comments - old_comments

        score_changed = score_delta != 0
        comments_changed = comments_delta != 0
        has_changes = score_changed or comments_changed

        return {
            'has_changes': has_changes,
            'score_changed': score_changed,
            'comments_changed': comments_changed,
            'score_delta': score_delta,
            'comments_delta': comments_delta
        }

    def detect_all_changes(
        self,
        current_posts: list[dict[str, Any]],
        last_check_time: datetime,
        check_run_id: int,
        subreddit: str
    ) -> ChangeDetectionResult:
        """Perform comprehensive change detection for all posts.

        Args:
            current_posts: List of current post data from Reddit API
            last_check_time: Timestamp of the last check
            check_run_id: ID of the current check run
            subreddit: Subreddit being analyzed

        Returns:
            ChangeDetectionResult with all detected changes
        """
        logger.info(
            f"Starting change detection for r/{subreddit} "
            f"with {len(current_posts)} current posts"
        )

        try:
            # Find new posts
            new_posts = self.find_new_posts(current_posts, last_check_time)

            # Find updated posts
            updated_posts = self.find_updated_posts(current_posts)

            # Create comprehensive result
            result = ChangeDetectionResult.from_updates(
                check_run_id=check_run_id,
                subreddit=subreddit,
                new_posts=new_posts,
                updated_posts=updated_posts
            )

            logger.info(
                f"Change detection completed for r/{subreddit}: "
                f"{result.total_new_posts} new posts, "
                f"{result.total_updated_posts} updated posts, "
                f"{result.posts_with_significant_changes} significant changes, "
                f"{result.trending_up_posts} trending up, "
                f"{result.trending_down_posts} trending down"
            )

            return result

        except Exception as e:
            logger.error(f"Error in comprehensive change detection: {e}")

            # Return empty result on error
            return ChangeDetectionResult.from_updates(
                check_run_id=check_run_id,
                subreddit=subreddit,
                new_posts=[],
                updated_posts=[]
            )

    def get_trending_posts(
        self,
        subreddit: str,
        min_score_delta: int = 10,
        min_time_span_hours: float = 1.0,
        limit: int = 10
    ) -> list[tuple[RedditPost, EngagementDelta]]:
        """Get posts that are currently trending based on engagement deltas.

        Args:
            subreddit: Subreddit to analyze
            min_score_delta: Minimum score change to consider trending
            min_time_span_hours: Minimum time span for analysis
            limit: Maximum number of posts to return

        Returns:
            List of tuples containing (RedditPost, EngagementDelta) for trending posts
        """
        try:
            # Get recent posts from the subreddit
            recent_posts = (
                self.session.query(RedditPost)
                .filter(RedditPost.subreddit == subreddit)
                .order_by(RedditPost.last_updated.desc())
                .limit(limit * 2)  # Get more to filter from
                .all()
            )

            trending_posts: list[tuple[RedditPost, EngagementDelta]] = []

            for post in recent_posts:
                # Calculate current engagement delta (would need current Reddit data)
                # For now, this is a placeholder - in real implementation,
                # this would fetch current data from Reddit API

                # Simulate current values (in real implementation, get from Reddit)
                current_score = post.score  # Would be fetched from Reddit
                current_comments = post.num_comments  # Would be fetched from Reddit
                current_timestamp = datetime.now(UTC)

                delta = self.calculate_engagement_delta(
                    post.post_id,
                    current_score,
                    current_comments,
                    current_timestamp
                )

                if (delta and
                    abs(delta.score_delta) >= min_score_delta and
                    delta.time_span_hours >= min_time_span_hours and
                    delta.is_trending_up):

                    trending_posts.append((post, delta))

                if len(trending_posts) >= limit:
                    break

            # Sort by engagement rate (highest first)
            trending_posts.sort(key=lambda x: x[1].engagement_rate, reverse=True)

            logger.debug(f"Found {len(trending_posts)} trending posts in r/{subreddit}")
            return trending_posts

        except SQLAlchemyError as e:
            logger.error(f"Error getting trending posts for r/{subreddit}: {e}")
            return []

    def find_new_comments(
        self, post_id: int, current_comments: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Find comments that are new since last stored for a post.

        Args:
            post_id: Database ID of the post
            current_comments: List of current comment data from Reddit API

        Returns:
            List of new comment dictionaries
        """
        if not current_comments:
            return []

        try:
            # Get existing comments for the post
            existing_comments = self.storage_service.get_comments_for_post(post_id)

            # For nonexistent posts, we should return empty list (no comments can be new for nonexistent post)
            # Check if post exists by trying to get it
            post = self.session.query(RedditPost).filter(RedditPost.id == post_id).first()
            if post is None:
                logger.debug(f"Post {post_id} does not exist, returning no new comments")
                return []

            # Create set of existing comment IDs for fast lookup
            existing_comment_ids = {comment.comment_id for comment in existing_comments}

            new_comments = []
            for comment_data in current_comments:
                try:
                    comment_id = comment_data.get('comment_id')
                    if not comment_id:
                        logger.warning("Comment data missing comment_id, skipping")
                        continue

                    # If comment doesn't exist in database, it's new
                    if comment_id not in existing_comment_ids:
                        new_comments.append(comment_data)
                        logger.debug(f"Found new comment: {comment_id}")

                except (KeyError, TypeError) as e:
                    logger.warning(f"Error processing comment data: {e}")
                    continue

            logger.info(f"Found {len(new_comments)} new comments for post {post_id}")
            return new_comments

        except SQLAlchemyError as e:
            logger.error(f"Database error finding new comments for post {post_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error finding new comments for post {post_id}: {e}")
            return []

    def find_updated_comments(
        self, post_id: int, current_comments: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Find comments that have score changes since last stored.

        Args:
            post_id: Database ID of the post
            current_comments: List of current comment data from Reddit API

        Returns:
            List of updated comment dictionaries with delta information
        """
        if not current_comments:
            return []

        try:
            # Get existing comments for the post
            existing_comments = self.storage_service.get_comments_for_post(post_id)

            # For nonexistent posts, we should return empty list
            post = self.session.query(RedditPost).filter(RedditPost.id == post_id).first()
            if post is None:
                logger.debug(f"Post {post_id} does not exist, returning no updated comments")
                return []

            # Create mapping of existing comments by comment_id
            existing_comment_map = {comment.comment_id: comment for comment in existing_comments}

            updated_comments = []
            for comment_data in current_comments:
                try:
                    comment_id = comment_data.get('comment_id')
                    if not comment_id:
                        continue

                    # Check if comment exists in database
                    existing_comment = existing_comment_map.get(comment_id)
                    if existing_comment is None:
                        # Comment not in database, not an update
                        continue

                    # Compare scores
                    current_score = comment_data.get('score', 0)
                    existing_score = existing_comment.score
                    score_delta = current_score - existing_score

                    if score_delta != 0:
                        # Comment has score change
                        updated_comment = comment_data.copy()
                        updated_comment['score_delta'] = score_delta
                        updated_comment['previous_score'] = existing_score
                        updated_comment['current_score'] = current_score
                        updated_comment['last_updated'] = existing_comment.last_updated

                        updated_comments.append(updated_comment)

                        logger.debug(
                            f"Found updated comment: {comment_id} with score change "
                            f"{score_delta:+} ({existing_score} -> {current_score})"
                        )

                except (KeyError, TypeError) as e:
                    logger.warning(f"Error processing comment update: {e}")
                    continue

            logger.info(f"Found {len(updated_comments)} updated comments for post {post_id}")
            return updated_comments

        except SQLAlchemyError as e:
            logger.error(f"Database error finding updated comments for post {post_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error finding updated comments for post {post_id}: {e}")
            return []

    def get_comment_tree_changes(self, post_id: int) -> dict[str, Any]:
        """Analyze comment tree structure and hierarchy for a post.

        Args:
            post_id: Database ID of the post

        Returns:
            Dictionary with comment tree analysis
        """
        try:
            # Get all comments for the post
            comments = (
                self.session.query(Comment)
                .filter(Comment.post_id == post_id)
                .all()
            )

            total_comments = len(comments)

            if total_comments == 0:
                return {
                    'post_id': post_id,
                    'total_stored_comments': 0,
                    'comment_hierarchy': {
                        'top_level_count': 0,
                        'total_replies': 0,
                        'max_depth': 0
                    }
                }

            # Analyze comment hierarchy
            post_reddit_id = None
            if comments:
                # Get the post's reddit ID from the first comment's relationship
                post = self.session.query(RedditPost).filter(RedditPost.id == post_id).first()
                if post:
                    post_reddit_id = post.post_id

            # Count top-level comments (parent_id is the post ID)
            top_level_comments = [c for c in comments if c.parent_id == post_reddit_id]
            top_level_count = len(top_level_comments)
            total_replies = total_comments - top_level_count

            # Calculate maximum depth using BFS
            max_depth = self._calculate_comment_tree_depth(comments, post_reddit_id)

            hierarchy = {
                'top_level_count': top_level_count,
                'total_replies': total_replies,
                'max_depth': max_depth
            }

            logger.debug(
                f"Comment tree analysis for post {post_id}: "
                f"{total_comments} total, {top_level_count} top-level, "
                f"{total_replies} replies, max depth {max_depth}"
            )

            return {
                'post_id': post_id,
                'total_stored_comments': total_comments,
                'comment_hierarchy': hierarchy
            }

        except SQLAlchemyError as e:
            logger.error(f"Database error analyzing comment tree for post {post_id}: {e}")
            return {
                'post_id': post_id,
                'total_stored_comments': 0,
                'comment_hierarchy': {
                    'top_level_count': 0,
                    'total_replies': 0,
                    'max_depth': 0
                }
            }
        except Exception as e:
            logger.error(f"Unexpected error analyzing comment tree for post {post_id}: {e}")
            return {
                'post_id': post_id,
                'total_stored_comments': 0,
                'comment_hierarchy': {
                    'top_level_count': 0,
                    'total_replies': 0,
                    'max_depth': 0
                }
            }

    def _calculate_comment_tree_depth(
        self, comments: list[Comment], post_reddit_id: str | None
    ) -> int:
        """Calculate the maximum depth of comment tree using breadth-first traversal.

        Args:
            comments: List of Comment objects
            post_reddit_id: Reddit ID of the post (root of the tree)

        Returns:
            Maximum depth of the comment tree
        """
        if not comments or not post_reddit_id:
            return 0

        # Create mapping of parent_id to list of children
        children_map: dict[str, list[Comment]] = {}
        for comment in comments:
            parent_id = comment.parent_id
            if parent_id is not None:  # Only process comments with valid parent_id
                if parent_id not in children_map:
                    children_map[parent_id] = []
                children_map[parent_id].append(comment)

        # BFS to find maximum depth
        max_depth = 1  # Start with depth 1 (the post itself)

        # Start with top-level comments (children of the post)
        if post_reddit_id in children_map:
            queue = [(comment, 2) for comment in children_map[post_reddit_id]]  # Depth 2

            while queue:
                current_comment, depth = queue.pop(0)
                max_depth = max(max_depth, depth)

                # Add children of current comment to queue
                comment_id = current_comment.comment_id
                if comment_id in children_map:
                    for child_comment in children_map[comment_id]:
                        queue.append((child_comment, depth + 1))

        return max_depth

    def calculate_comment_metrics(
        self, post_id: int, current_comments: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Calculate comprehensive metrics for comment changes.

        Args:
            post_id: Database ID of the post
            current_comments: List of current comment data from Reddit API

        Returns:
            Dictionary with comment metrics and analysis
        """
        try:
            # Get new and updated comments
            new_comments = self.find_new_comments(post_id, current_comments)
            updated_comments = self.find_updated_comments(post_id, current_comments)

            # Calculate new comment metrics
            total_new_comments = len(new_comments)
            top_new_comment = None

            if new_comments:
                # Find top new comment by score
                top_new_comment = max(new_comments, key=lambda c: c.get('score', 0))
                top_new_comment = {
                    'comment_id': top_new_comment.get('comment_id'),
                    'author': top_new_comment.get('author'),
                    'score': top_new_comment.get('score', 0),
                    'body_preview': (top_new_comment.get('body', '')[:100] + '...'
                                   if len(top_new_comment.get('body', '')) > 100
                                   else top_new_comment.get('body', ''))
                }

            # Calculate score change metrics
            score_changes = {
                'positive_changes': 0,
                'negative_changes': 0,
                'unchanged': 0,
                'total_score_change': 0
            }

            total_score_delta = 0
            change_count = 0

            for comment in updated_comments:
                score_delta = comment.get('score_delta', 0)
                if score_delta > 0:
                    score_changes['positive_changes'] += 1
                elif score_delta < 0:
                    score_changes['negative_changes'] += 1
                else:
                    score_changes['unchanged'] += 1

                total_score_delta += score_delta
                change_count += 1

            score_changes['total_score_change'] = total_score_delta

            # Calculate average score change
            average_score_change: float = 0.0
            if change_count > 0:
                average_score_change = total_score_delta / change_count

            # Also count unchanged existing comments
            existing_comments = self.storage_service.get_comments_for_post(post_id)
            if existing_comments:
                existing_comment_ids = {comment.comment_id for comment in existing_comments}
                current_comment_ids = {comment.get('comment_id') for comment in current_comments if comment.get('comment_id')}
                updated_comment_ids = {comment.get('comment_id') for comment in updated_comments if comment.get('comment_id')}

                # Comments that exist in both but have no score change
                unchanged_count = len(existing_comment_ids & current_comment_ids - updated_comment_ids)
                score_changes['unchanged'] = unchanged_count

            metrics = {
                'post_id': post_id,
                'total_new_comments': total_new_comments,
                'total_updated_comments': len(updated_comments),
                'average_score_change': average_score_change,
                'top_new_comment': top_new_comment,
                'score_change_distribution': score_changes
            }

            logger.debug(
                f"Comment metrics for post {post_id}: "
                f"{total_new_comments} new, {len(updated_comments)} updated, "
                f"avg score change {average_score_change:.2f}"
            )

            return metrics

        except Exception as e:
            logger.error(f"Error calculating comment metrics for post {post_id}: {e}")
            return {
                'post_id': post_id,
                'total_new_comments': 0,
                'total_updated_comments': 0,
                'average_score_change': 0,
                'top_new_comment': None,
                'score_change_distribution': {
                    'positive_changes': 0,
                    'negative_changes': 0,
                    'unchanged': 0,
                    'total_score_change': 0
                }
            }

    def get_subreddit_trends(self, subreddit: str, days: int = 7) -> TrendData:
        """Calculate comprehensive trend analysis for a subreddit.

        Args:
            subreddit: Name of the subreddit to analyze
            days: Number of days to analyze (default: 7)

        Returns:
            TrendData object with comprehensive trend analysis
        """
        try:
            # Calculate time window
            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(days=days)

            # Get posts from storage service (assuming this method exists)
            posts = self.storage_service.get_posts_in_timeframe(subreddit, start_date, end_date)

            if not posts:
                # Return empty trend data for no posts
                return TrendData(
                    subreddit=subreddit,
                    analysis_period_days=days,
                    start_date=start_date,
                    end_date=end_date,
                    total_posts=0,
                    total_comments=0,
                    average_posts_per_day=0.0,
                    average_comments_per_day=0.0,
                    average_score=0.0,
                    median_score=0.0,
                    score_standard_deviation=0.0,
                    engagement_trend=ActivityPattern.DORMANT,
                    best_posting_hour=12,  # Default to noon
                    best_posting_day=0,    # Default to Monday
                    peak_activity_periods=[],
                    predicted_daily_posts=0.0,
                    predicted_daily_engagement=0.0,
                    trend_confidence=0.0,
                    change_from_previous_period=0.0,
                    is_trending_up=False,
                    is_trending_down=False
                )

            # Calculate basic metrics
            total_posts = len(posts)
            total_comments = sum(post.num_comments for post in posts)
            scores = [post.score for post in posts]

            # Calculate statistical measures
            average_score = sum(scores) / len(scores) if scores else 0.0
            sorted_scores = sorted(scores)
            median_score = sorted_scores[len(sorted_scores) // 2] if sorted_scores else 0.0

            # Calculate standard deviation
            if len(scores) > 1:
                mean_score = average_score
                variance = sum((score - mean_score) ** 2 for score in scores) / len(scores)
                score_std_dev = variance ** 0.5
            else:
                score_std_dev = 0.0

            # Calculate daily averages
            average_posts_per_day = total_posts / days
            average_comments_per_day = total_comments / days

            # Detect activity pattern
            engagement_trend = self.detect_activity_patterns(subreddit)

            # Find best posting times
            best_posting_hour = self.calculate_best_post_time(subreddit)

            # Calculate best posting day (simplified - using current logic)
            day_scores: dict[int, list[float]] = {}
            for post in posts:
                day = post.created_utc.weekday()
                if day not in day_scores:
                    day_scores[day] = []
                day_scores[day].append(post.score)

            best_posting_day = 0  # Default Monday
            if day_scores:
                day_averages = {day: sum(scores) / len(scores) for day, scores in day_scores.items()}
                best_posting_day = max(day_averages, key=lambda day: day_averages[day])

            # Get forecast data
            forecast = self.get_engagement_forecast(subreddit)

            # Calculate change from previous period (simplified)
            change_from_previous = 0.0
            is_trending_up = average_posts_per_day > (total_posts / (days * 2)) if days > 1 else False
            is_trending_down = not is_trending_up and total_posts > 0

            return TrendData(
                subreddit=subreddit,
                analysis_period_days=days,
                start_date=start_date,
                end_date=end_date,
                total_posts=total_posts,
                total_comments=total_comments,
                average_posts_per_day=average_posts_per_day,
                average_comments_per_day=average_comments_per_day,
                average_score=average_score,
                median_score=median_score,
                score_standard_deviation=score_std_dev,
                engagement_trend=engagement_trend,
                best_posting_hour=best_posting_hour,
                best_posting_day=best_posting_day,
                peak_activity_periods=self._identify_peak_periods(posts),
                predicted_daily_posts=forecast.get('predicted_daily_posts', average_posts_per_day),
                predicted_daily_engagement=forecast.get('predicted_daily_engagement', average_score),
                trend_confidence=forecast.get('trend_confidence', 0.5),
                change_from_previous_period=change_from_previous,
                is_trending_up=is_trending_up,
                is_trending_down=is_trending_down
            )

        except Exception as e:
            logger.error(f"Error calculating subreddit trends for r/{subreddit}: {e}")
            # Return default empty trend data on error
            return TrendData(
                subreddit=subreddit,
                analysis_period_days=days,
                start_date=datetime.now(UTC) - timedelta(days=days),
                end_date=datetime.now(UTC),
                total_posts=0,
                total_comments=0,
                average_posts_per_day=0.0,
                average_comments_per_day=0.0,
                average_score=0.0,
                median_score=0.0,
                score_standard_deviation=0.0,
                engagement_trend=ActivityPattern.DORMANT,
                best_posting_hour=12,
                best_posting_day=0,
                peak_activity_periods=[],
                predicted_daily_posts=0.0,
                predicted_daily_engagement=0.0,
                trend_confidence=0.0,
                change_from_previous_period=0.0,
                is_trending_up=False,
                is_trending_down=False
            )

    def detect_activity_patterns(self, subreddit: str) -> ActivityPattern:
        """Detect activity patterns in subreddit data.

        Args:
            subreddit: Name of the subreddit to analyze

        Returns:
            ActivityPattern enum indicating the detected pattern
        """
        try:
            # Get last 14 days of data for pattern analysis
            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(days=14)

            posts = self.storage_service.get_posts_in_timeframe(subreddit, start_date, end_date)

            if not posts:
                return ActivityPattern.DORMANT

            # Group posts by day
            daily_counts: dict[str, int] = {}
            daily_scores: dict[str, list[float]] = {}

            for post in posts:
                day_key = post.created_utc.strftime('%Y-%m-%d')
                daily_counts[day_key] = daily_counts.get(day_key, 0) + 1

                if day_key not in daily_scores:
                    daily_scores[day_key] = []
                daily_scores[day_key].append(post.score)

            if not daily_counts:
                return ActivityPattern.DORMANT

            # Calculate daily activity metrics
            post_counts = list(daily_counts.values())
            avg_daily_posts = sum(post_counts) / len(post_counts)

            # Very low activity threshold
            if avg_daily_posts < 1:
                return ActivityPattern.DORMANT

            # Calculate variance to detect volatility
            if len(post_counts) > 1:
                variance = sum((count - avg_daily_posts) ** 2 for count in post_counts) / len(post_counts)
                std_dev = variance ** 0.5
                coefficient_of_variation = std_dev / avg_daily_posts if avg_daily_posts > 0 else 0

                # High volatility threshold (lowered to catch more volatile patterns)
                if coefficient_of_variation > 0.8:
                    return ActivityPattern.VOLATILE

            # Check for trends (comparing first and second half)
            mid_point = len(post_counts) // 2
            if mid_point > 0:
                first_half_avg = sum(post_counts[:mid_point]) / mid_point
                second_half_avg = sum(post_counts[mid_point:]) / (len(post_counts) - mid_point)

                change_ratio = (second_half_avg - first_half_avg) / first_half_avg if first_half_avg > 0 else 0

                # Only consider steady trends if volatility is low
                # Recalculate volatility to prioritize VOLATILE over trend patterns
                if coefficient_of_variation <= 0.8:
                    # Trend thresholds (only applied if not volatile)
                    if change_ratio > 0.3:  # 30% increase
                        return ActivityPattern.INCREASING
                    elif change_ratio < -0.3:  # 30% decrease
                        return ActivityPattern.DECREASING

            # Check for sudden surge (any day with 3x average activity)
            surge_threshold = avg_daily_posts * 3
            if any(count >= surge_threshold for count in post_counts):
                return ActivityPattern.SURGE

            # Default to steady if no other pattern detected
            return ActivityPattern.STEADY

        except Exception as e:
            logger.error(f"Error detecting activity patterns for r/{subreddit}: {e}")
            return ActivityPattern.DORMANT

    def calculate_best_post_time(self, subreddit: str) -> int:
        """Calculate the best hour of day to post for maximum engagement.

        Args:
            subreddit: Name of the subreddit to analyze

        Returns:
            Best hour of day (0-23) for posting
        """
        try:
            # Get last 30 days of data for reliable hour analysis
            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(days=30)

            posts = self.storage_service.get_posts_in_timeframe(subreddit, start_date, end_date)

            if not posts:
                return 12  # Default to noon

            # Group posts by hour and calculate average engagement
            hourly_engagement: dict[int, list[float]] = {}

            for post in posts:
                hour = post.created_utc.hour
                if hour not in hourly_engagement:
                    hourly_engagement[hour] = []
                # Use normalized engagement score (score per comment ratio)
                engagement = post.score + (post.num_comments * 2)  # Weight comments 2x
                hourly_engagement[hour].append(engagement)

            if not hourly_engagement:
                return 12

            # Calculate average engagement per hour
            hourly_averages = {}
            for hour, engagements in hourly_engagement.items():
                hourly_averages[hour] = sum(engagements) / len(engagements)

            # Return hour with highest average engagement
            best_hour = max(hourly_averages, key=lambda hour: hourly_averages[hour])

            logger.debug(f"Best posting hour for r/{subreddit}: {best_hour}:00")
            return best_hour

        except Exception as e:
            logger.error(f"Error calculating best post time for r/{subreddit}: {e}")
            return 12  # Default to noon

    def get_engagement_forecast(self, subreddit: str) -> dict[str, float]:
        """Generate engagement forecast based on historical trends.

        Args:
            subreddit: Name of the subreddit to analyze

        Returns:
            Dictionary with forecast data
        """
        try:
            # Get 14 days of historical data for forecasting
            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(days=14)

            posts = self.storage_service.get_posts_in_timeframe(subreddit, start_date, end_date)

            if not posts:
                return {
                    'predicted_daily_posts': 0.0,
                    'predicted_daily_engagement': 0.0,
                    'trend_confidence': 0.0
                }

            # Group by day for trend analysis
            daily_data: dict[str, dict[str, float]] = {}

            for post in posts:
                day_key = post.created_utc.strftime('%Y-%m-%d')
                if day_key not in daily_data:
                    daily_data[day_key] = {'posts': 0, 'total_score': 0, 'total_comments': 0}

                daily_data[day_key]['posts'] += 1
                daily_data[day_key]['total_score'] += post.score
                daily_data[day_key]['total_comments'] += post.num_comments

            if len(daily_data) < 3:  # Need at least 3 days for trend
                avg_posts = len(posts) / 14
                avg_engagement = sum(post.score for post in posts) / len(posts) if posts else 0

                return {
                    'predicted_daily_posts': avg_posts,
                    'predicted_daily_engagement': avg_engagement,
                    'trend_confidence': 0.3  # Low confidence with limited data
                }

            # Simple linear trend analysis
            days = sorted(daily_data.keys())
            post_counts = [daily_data[day]['posts'] for day in days]
            avg_scores = [daily_data[day]['total_score'] / daily_data[day]['posts']
                         if daily_data[day]['posts'] > 0 else 0 for day in days]

            # Calculate linear trend for posts
            n = len(post_counts)
            x_values = list(range(n))

            # Simple linear regression for post count trend
            x_mean = sum(x_values) / n
            y_mean = sum(post_counts) / n

            numerator = sum((x_values[i] - x_mean) * (post_counts[i] - y_mean) for i in range(n))
            denominator = sum((x_values[i] - x_mean) ** 2 for i in range(n))

            if denominator != 0:
                slope = numerator / denominator
                intercept = y_mean - slope * x_mean
                predicted_posts = slope * n + intercept  # Predict next day
            else:
                predicted_posts = y_mean

            # Similar calculation for engagement
            eng_mean = sum(avg_scores) / n
            eng_numerator = sum((x_values[i] - x_mean) * (avg_scores[i] - eng_mean) for i in range(n))

            if denominator != 0:
                eng_slope = eng_numerator / denominator
                eng_intercept = eng_mean - eng_slope * x_mean
                predicted_engagement = eng_slope * n + eng_intercept
            else:
                predicted_engagement = eng_mean

            # Calculate confidence based on data consistency
            post_variance = sum((count - y_mean) ** 2 for count in post_counts) / n
            post_std = post_variance ** 0.5
            coefficient_of_variation = post_std / y_mean if y_mean > 0 else 1.0

            # Higher confidence for more consistent data
            confidence = max(0.1, min(0.9, 1.0 - coefficient_of_variation / 2))

            logger.debug(
                f"Engagement forecast for r/{subreddit}: "
                f"{predicted_posts:.1f} posts/day, "
                f"{predicted_engagement:.1f} avg engagement, "
                f"{confidence:.2f} confidence"
            )

            return {
                'predicted_daily_posts': max(0, predicted_posts),
                'predicted_daily_engagement': max(0, predicted_engagement),
                'trend_confidence': confidence
            }

        except Exception as e:
            logger.error(f"Error generating engagement forecast for r/{subreddit}: {e}")
            return {
                'predicted_daily_posts': 0.0,
                'predicted_daily_engagement': 0.0,
                'trend_confidence': 0.0
            }

    def _identify_peak_periods(self, posts: list) -> list[str]:
        """Identify peak activity periods from posts data.

        Args:
            posts: List of RedditPost objects

        Returns:
            List of peak period descriptions
        """
        try:
            if not posts:
                return []

            # Group posts by 4-hour periods
            period_counts: dict[str, int] = {}

            for post in posts:
                hour = post.created_utc.hour
                if hour < 6:
                    period = "late_night"  # 0-5
                elif hour < 12:
                    period = "morning"     # 6-11
                elif hour < 18:
                    period = "afternoon"   # 12-17
                else:
                    period = "evening"     # 18-23

                period_counts[period] = period_counts.get(period, 0) + 1

            if not period_counts:
                return []

            # Find periods with above-average activity
            avg_count = sum(period_counts.values()) / len(period_counts)
            peak_periods = [
                period for period, count in period_counts.items()
                if count > avg_count * 1.2  # 20% above average
            ]

            return peak_periods

        except Exception as e:
            logger.error(f"Error identifying peak periods: {e}")
            return []
