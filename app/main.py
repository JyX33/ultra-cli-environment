from datetime import UTC, datetime
import io
import logging
import re
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.api_models import (
    CommentUpdateResponse,
    HistoryResponse,
    PostUpdateResponse,
    TrendsResponse,
    TrendSummary,
    UpdateCheckResponse,
)
from app.services.change_detection_service import ChangeDetectionService
from app.services.reddit_service import RedditService
from app.services.scraper_service import scrape_article_text
from app.services.storage_service import StorageService
from app.services.summarizer_service import summarize_content
from app.utils.comment_processor import get_comments_summary_stream
from app.utils.filename_sanitizer import generate_safe_filename
from app.utils.relevance import score_and_rank_subreddits_concurrent
from app.utils.report_generator import create_markdown_report

# Configure logging for debugging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)

# Set specific loggers to DEBUG for debugging purposes
logging.getLogger("app.utils.relevance").setLevel(logging.DEBUG)
logging.getLogger("app.services.reddit_service").setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Reddit News Agent",
    description="Automated Reddit content analysis and reporting",
)
reddit_service = RedditService()


def validate_input_string(input_str: str, param_name: str) -> str:
    """
    Validate input string to prevent injection attacks.

    Args:
        input_str: The input string to validate
        param_name: Name of the parameter for error messages

    Returns:
        The validated input string

    Raises:
        HTTPException: If input contains malicious patterns
    """
    if not input_str or not isinstance(input_str, str):
        raise HTTPException(
            status_code=422, detail=f"Invalid {param_name}: must be a non-empty string"
        )

    # Check for common injection patterns
    dangerous_patterns = [
        r"[<>\"'`]",  # HTML/JS injection
        r"(?i)(script|javascript|vbscript)",  # Script injection
        r"(?i)(drop|delete|insert|update|select|union|exec|execute)",  # SQL injection
        r"(?i)(file|ftp|http|https|ldap|gopher)://",  # Protocol injection
        r"(?i)(\$\{|\{\{|%\{)",  # Template injection
        r"\.\.+[/\\]",  # Path traversal
        r"(?i)(etc/passwd|/etc/shadow|proc/self)",  # System file access
        r"[;&|`$()]",  # Command injection
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, input_str):
            raise HTTPException(
                status_code=422,
                detail=f"Invalid {param_name}: contains potentially malicious content",
            )

    # Length validation
    if len(input_str) > 100:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {param_name}: too long (max 100 characters)",
        )

    return input_str.strip()


@app.get("/discover-subreddits/{topic}")
async def discover_subreddits(topic: str) -> list[dict[str, Any]]:
    """
    Discover and rank subreddits relevant to a given topic.

    Args:
        topic: The topic to search for relevant subreddits

    Returns:
        List of top 3 relevant subreddits with relevance scores
    """
    try:
        # Validate input to prevent injection attacks
        topic = validate_input_string(topic, "topic")
        # Search for subreddits related to the topic
        subreddits = reddit_service.search_subreddits(topic)

        if not subreddits:
            raise HTTPException(
                status_code=404, detail=f"No subreddits found for topic: {topic}"
            )

        # Score and rank subreddits by relevance using concurrent processing
        scored_subreddits = score_and_rank_subreddits_concurrent(
            subreddits, topic, reddit_service
        )

        if not scored_subreddits:
            raise HTTPException(
                status_code=404,
                detail=f"No relevant subreddits found for topic: {topic}",
            )

        # Return top 3 results
        return scored_subreddits[:3]

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        # Don't expose internal error details
        raise HTTPException(status_code=500, detail="Error processing request") from None


@app.get("/generate-report/{subreddit}/{topic}")
async def generate_report(
    subreddit: str,
    topic: str,
    store_data: bool = False,
    include_history: bool = False,
    db: Session = Depends(get_db)
) -> StreamingResponse:
    """
    Generate a comprehensive Markdown report for a given subreddit and topic.

    Args:
        subreddit: Name of the subreddit to analyze
        topic: Topic being reported on
        store_data: Whether to store posts and comments in database (default: False)
        include_history: Whether to include historical data in report (default: False)
        db: Database session dependency

    Returns:
        StreamingResponse with downloadable Markdown report
    """
    try:
        # Validate inputs to prevent injection attacks
        subreddit = validate_input_string(subreddit, "subreddit")
        topic = validate_input_string(topic, "topic")
        # Get relevant posts from the subreddit using optimized API calls
        posts = reddit_service.get_relevant_posts_optimized(subreddit)

        if not posts:
            raise HTTPException(
                status_code=404,
                detail=f"No relevant posts found in r/{subreddit} for the last day",
            )

        # Initialize services for storage if enabled
        storage_service = None
        check_run_id = None
        historical_data = None

        if store_data:
            try:
                storage_service = StorageService(db)
                check_run_id = storage_service.create_check_run(subreddit, topic)
                logging.info(f"Created check run {check_run_id} for {subreddit}/{topic}")
            except Exception as e:
                logging.warning(f"Failed to create check run: {e}")
                # Continue without storage - don't let storage failures break report generation

        # Get historical data if requested and storage is enabled
        if include_history and storage_service:
            try:
                # Get the latest check run for this subreddit/topic to retrieve historical posts
                latest_check_run = storage_service.get_latest_check_run(subreddit, topic)
                if latest_check_run:
                    historical_posts = storage_service.get_posts_for_check_run(latest_check_run.id)
                    if historical_posts:
                        historical_data = [
                            {
                                "title": post.title,
                                "url": post.url,
                                "score": post.score,
                                "num_comments": post.num_comments,
                                "author": post.author,
                                "created_utc": post.created_utc
                            }
                            for post in historical_posts
                        ]
                        logging.info(f"Retrieved {len(historical_data)} historical posts from check run {latest_check_run.id}")
            except Exception as e:
                logging.warning(f"Failed to retrieve historical data: {e}")
                # Continue without history - don't let history failures break report generation

        # Initialize report data list
        report_data = []

        # Process each post
        for post in posts:
            # Get post title and URL
            title = post.title
            url = (
                post.url if not post.is_self else f"https://reddit.com{post.permalink}"
            )

            # Get post content
            content = post.selftext if post.is_self else scrape_article_text(post.url)

            # Generate post summary
            post_summary = summarize_content(content, "post")

            # Get top comments using memory-efficient streaming processing
            comments_text = get_comments_summary_stream(
                post.id, reddit_service, max_memory_mb=10, top_count=10
            )
            comments_summary = (
                summarize_content(comments_text, "comments")
                if comments_text != "No comments available for summary."
                else "No comments available for summary."
            )

            # Store post and comments if storage is enabled
            if storage_service and check_run_id:
                try:
                    # Store the post first and get the database ID
                    post_data = {
                        "post_id": post.id,
                        "subreddit": post.subreddit.display_name,
                        "title": post.title,
                        "author": str(post.author) if post.author else None,
                        "url": post.url,
                        "permalink": post.permalink,
                        "score": post.score,
                        "num_comments": post.num_comments,
                        "created_utc": datetime.fromtimestamp(post.created_utc, UTC),
                        "is_self": post.is_self,
                        "selftext": post.selftext if hasattr(post, 'selftext') else "",
                        "over_18": post.over_18,
                        "check_run_id": check_run_id
                    }
                    db_post_id = storage_service.save_post(post_data)
                    logging.debug(f"Stored post {post.id} with database ID {db_post_id}")

                    # Store comments using the database post ID
                    try:
                        post.comments.replace_more(limit=0)  # Remove "more comments" placeholders
                        comment_count = 0
                        for comment in post.comments.list()[:20]:  # Limit to top 20 comments
                            if hasattr(comment, 'body') and comment.body != "[deleted]":
                                comment_data = {
                                    "comment_id": comment.id,
                                    "author": str(comment.author) if comment.author else None,
                                    "body": comment.body,
                                    "score": comment.score,
                                    "created_utc": datetime.fromtimestamp(comment.created_utc, UTC),
                                    "parent_id": comment.parent_id if comment.parent_id != comment.link_id else None
                                }
                                storage_service.save_comment(comment_data, db_post_id)
                                comment_count += 1
                        logging.debug(f"Stored {comment_count} comments for post {post.id}")
                    except Exception as e:
                        logging.warning(f"Failed to save comments for post {post.id}: {e}")
                        # Continue processing - don't let comment storage failures break report generation

                except Exception as e:
                    logging.warning(f"Failed to save post {post.id}: {e}")
                    # Continue processing - don't let storage failures break report generation

            # Add to report data
            report_data.append(
                {
                    "title": title,
                    "url": url,
                    "post_summary": post_summary,
                    "comments_summary": comments_summary,
                }
            )

        # Update check run with final counts if storage is enabled
        if storage_service and check_run_id:
            try:
                storage_service.update_check_run_counters(
                    check_run_id,
                    posts_found=len(posts),
                    new_posts=len(posts)  # All posts are "new" in this context
                )
                logging.info(f"Updated check run {check_run_id} with {len(posts)} posts")
            except Exception as e:
                logging.warning(f"Failed to update check run counters: {e}")

        # Generate the Markdown report
        # Note: Historical data integration would require updating the report generator
        # For now, generate standard report and log historical data availability
        if include_history and historical_data:
            logging.info(f"Historical data available: {len(historical_data)} posts")
            # Future enhancement: Could append historical summary to report

        markdown_report = create_markdown_report(report_data, subreddit, topic)

        # Create a downloadable file response with secure filename
        filename = generate_safe_filename(subreddit, topic)

        return StreamingResponse(
            io.BytesIO(markdown_report.encode("utf-8")),
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        # Don't expose internal error details
        raise HTTPException(status_code=500, detail="Error processing request") from None


@app.get("/check-updates/{subreddit}/{topic}", response_model=UpdateCheckResponse)
async def check_updates(
    subreddit: str,
    topic: str,
    db: Session = Depends(get_db)
) -> UpdateCheckResponse:
    """
    Check for updates in a subreddit for a given topic since the last check.

    This endpoint analyzes a subreddit to detect new posts, updated posts,
    new comments, and trending changes since the last check was performed.
    If this is the first check for the subreddit/topic combination, all
    found posts will be considered "new".

    Args:
        subreddit: Name of the subreddit to check (e.g., "technology")
        topic: Topic being monitored (e.g., "artificial-intelligence")
        db: Database session dependency

    Returns:
        UpdateCheckResponse with details about new and updated content

    Raises:
        HTTPException: 422 for invalid parameters, 500 for processing errors
    """
    try:
        # Validate inputs to prevent injection attacks
        subreddit = validate_input_string(subreddit, "subreddit")
        topic = validate_input_string(topic, "topic")

        # Initialize services
        storage_service = StorageService(db)
        change_detection_service = ChangeDetectionService(db, storage_service)
        current_time = datetime.now(UTC)

        # Get the latest check run for this subreddit/topic combination
        latest_check_run = storage_service.get_latest_check_run(subreddit, topic)
        is_first_check = latest_check_run is None
        # For first checks, set last_check_time to far in the past so all posts are considered new
        if is_first_check:
            last_check_time = datetime.fromtimestamp(0, UTC)  # Unix epoch (1970)
        else:
            last_check_time = latest_check_run.timestamp if latest_check_run else datetime.fromtimestamp(0, UTC)

        # Get current posts from Reddit
        reddit_posts = reddit_service.get_relevant_posts_optimized(subreddit)

        # Create new check run
        check_run_id = storage_service.create_check_run(subreddit, topic)

        # Convert Reddit posts to dictionaries for change detection
        current_posts = []
        for post in reddit_posts:
            post_data = {
                "post_id": post.id,
                "subreddit": post.subreddit.display_name,
                "title": post.title,
                "author": str(post.author) if post.author else None,
                "url": post.url,
                "score": post.score,
                "num_comments": post.num_comments,
                "created_utc": datetime.fromtimestamp(post.created_utc, UTC),
                "is_self": post.is_self,
                "selftext": post.selftext if hasattr(post, 'selftext') else "",
                "upvote_ratio": post.upvote_ratio,
                "over_18": post.over_18,
                "spoiler": post.spoiler,
                "stickied": post.stickied,
                "permalink": post.permalink
            }
            current_posts.append(post_data)

        # Detect changes
        detection_result = change_detection_service.detect_all_changes(
            current_posts=current_posts,
            last_check_time=last_check_time,
            check_run_id=check_run_id,
            subreddit=subreddit
        )

        # Save current posts and comments to database
        total_posts_saved = 0
        total_comments_saved = 0

        for i, post in enumerate(reddit_posts):
            try:
                # Add check_run_id to the already-converted post data
                post_data = current_posts[i].copy()
                post_data["check_run_id"] = check_run_id
                storage_service.save_post(post_data)
                total_posts_saved += 1

                # Save comments for each post
                try:
                    post.comments.replace_more(limit=0)  # Remove "more comments" placeholders
                    for comment in post.comments.list()[:20]:  # Limit to top 20 comments
                        if hasattr(comment, 'body') and comment.body != "[deleted]":
                            comment_data = {
                                "comment_id": comment.id,
                                "author": str(comment.author) if comment.author else None,
                                "body": comment.body,
                                "score": comment.score,
                                "created_utc": datetime.fromtimestamp(comment.created_utc, UTC),
                                "parent_id": comment.parent_id if comment.parent_id != comment.link_id else None
                            }
                            storage_service.save_comment(comment_data, post.id)
                            total_comments_saved += 1
                except Exception as e:
                    logging.warning(f"Failed to save comments for post {post.id}: {e}")

            except Exception as e:
                logging.warning(f"Failed to save post {post.id}: {e}")

        # Convert detection results to API response format
        new_posts_response = []
        for post_update in detection_result.new_posts:
            post_response = PostUpdateResponse(
                post_id=post_update.reddit_post_id,
                title=post_update.title,
                author=None,  # Will be filled from post data if available
                subreddit=post_update.subreddit,
                url="",  # Will be filled from post data if available
                score=post_update.current_score,
                num_comments=post_update.current_comments,
                created_utc=post_update.current_timestamp,
                is_new=True,
                score_change=post_update.engagement_delta.score_delta if post_update.engagement_delta else None,
                comment_change=post_update.engagement_delta.comments_delta if post_update.engagement_delta else None,
                engagement_delta=post_update.engagement_delta
            )
            new_posts_response.append(post_response)

        updated_posts_response = []
        for post_update in detection_result.updated_posts:
            post_response = PostUpdateResponse(
                post_id=post_update.reddit_post_id,
                title=post_update.title,
                author=None,  # Will be filled from post data if available
                subreddit=post_update.subreddit,
                url="",  # Will be filled from post data if available
                score=post_update.current_score,
                num_comments=post_update.current_comments,
                created_utc=post_update.current_timestamp,
                is_new=False,
                score_change=post_update.engagement_delta.score_delta if post_update.engagement_delta else None,
                comment_change=post_update.engagement_delta.comments_delta if post_update.engagement_delta else None,
                engagement_delta=post_update.engagement_delta
            )
            updated_posts_response.append(post_response)

        # Comments are not yet implemented in change detection
        new_comments_response: list[CommentUpdateResponse] = []
        updated_comments_response: list[CommentUpdateResponse] = []

        # Update check run with final counts
        storage_service.update_check_run_counters(
            check_run_id,
            posts_found=total_posts_saved,
            new_posts=len(detection_result.new_posts)
        )

        # Create summary statistics
        summary = {
            "new_posts_count": len(detection_result.new_posts),
            "updated_posts_count": len(detection_result.updated_posts),
            "new_comments_count": 0,  # Comments not yet implemented in change detection
            "updated_comments_count": 0,  # Comments not yet implemented in change detection
            "total_posts_processed": len(current_posts),
            "posts_saved_to_db": total_posts_saved,
            "comments_saved_to_db": total_comments_saved,
            "processing_time_seconds": (datetime.now(UTC) - current_time).total_seconds()
        }

        # Try to generate trend analysis if we have historical data
        trends = None
        if not is_first_check:
            try:
                trend_data = change_detection_service.get_subreddit_trends(subreddit, days=7)
                if trend_data:
                    trends = TrendSummary(
                        activity_trend=trend_data.engagement_trend.value,
                        engagement_change=trend_data.change_from_previous_period,
                        peak_activity_hour=trend_data.best_posting_hour,
                        posts_per_hour=trend_data.posts_per_hour,
                        comments_per_hour=trend_data.average_comments_per_day / 24.0
                    )
            except Exception as e:
                logging.warning(f"Failed to generate trend analysis: {e}")

        # Build and return response
        response = UpdateCheckResponse(
            subreddit=subreddit,
            topic=topic,
            check_time=current_time,
            last_check_time=last_check_time,
            new_posts=new_posts_response,
            updated_posts=updated_posts_response,
            total_posts_found=len(current_posts),
            new_comments=new_comments_response,
            updated_comments=updated_comments_response,
            total_comments_found=total_comments_saved,
            summary=summary,
            trends=trends,
            is_first_check=is_first_check,
            check_run_id=check_run_id
        )

        return response

    except Exception as e:
        # Log the error for debugging but don't expose internal details
        logging.error(f"Error in check_updates endpoint: {type(e).__name__}: {e}")

        if isinstance(e, HTTPException):
            raise e

        # Return generic error to prevent information leakage
        raise HTTPException(status_code=500, detail="Error processing request") from None


@app.get("/history/{subreddit}", response_model=HistoryResponse)
async def get_history(
    subreddit: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db)
) -> HistoryResponse:
    """
    Get historical check run data for a subreddit with optional date filtering and pagination.

    Args:
        subreddit: Name of the subreddit to get history for
        start_date: Optional start date filter (ISO format)
        end_date: Optional end date filter (ISO format)
        page: Page number (1-based, default: 1)
        limit: Items per page (default: 20, max: 100)
        db: Database session dependency

    Returns:
        HistoryResponse with paginated check run history

    Raises:
        HTTPException: 422 for invalid parameters, 500 for processing errors
    """
    try:
        # Validate inputs
        subreddit = validate_input_string(subreddit, "subreddit")

        # Validate pagination parameters
        if page < 1:
            raise HTTPException(status_code=422, detail="Page must be >= 1")
        if limit < 1 or limit > 100:
            raise HTTPException(status_code=422, detail="Limit must be between 1 and 100")

        # Validate date parameters if provided
        if start_date and end_date and start_date > end_date:
            raise HTTPException(status_code=422, detail="start_date must be before end_date")

        # Initialize storage service
        storage_service = StorageService(db)

        # Get check run history with pagination
        check_runs, total_count = storage_service.get_check_run_history(
            subreddit=subreddit,
            start_date=start_date,
            end_date=end_date,
            page=page,
            limit=limit
        )

        # Get date range for the subreddit
        earliest_date, latest_date = storage_service.get_subreddit_date_range(subreddit)

        # Convert check runs to response format
        checks = []
        for check_run in check_runs:
            check_data = {
                "id": check_run.id,
                "timestamp": check_run.timestamp,
                "topic": check_run.topic,
                "posts_found": check_run.posts_found,
                "new_posts": check_run.new_posts,
                "summary": {
                    "check_duration": "N/A",  # Would need to calculate if we stored end times
                    "posts_processed": check_run.posts_found,
                    "new_content_found": check_run.new_posts > 0
                }
            }
            checks.append(check_data)

        # Calculate pagination info
        total_pages = (total_count + limit - 1) // limit  # Ceiling division

        pagination = {
            "page": page,
            "limit": limit,
            "total_items": total_count,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }

        # Build response
        response = HistoryResponse(
            subreddit=subreddit,
            total_checks=total_count,
            date_range={
                "start": earliest_date,
                "end": latest_date
            },
            checks=checks,
            pagination=pagination
        )

        return response

    except Exception as e:
        # Log the error for debugging but don't expose internal details
        logging.error(f"Error in get_history endpoint: {type(e).__name__}: {e}")

        if isinstance(e, HTTPException):
            raise e

        # Return generic error to prevent information leakage
        raise HTTPException(status_code=500, detail="Error processing request") from None


@app.get("/trends/{subreddit}", response_model=TrendsResponse)
async def get_trends(
    subreddit: str,
    days: int = 7,
    db: Session = Depends(get_db)
) -> TrendsResponse:
    """
    Get trend analysis for a subreddit over a specified time period.

    Args:
        subreddit: Name of the subreddit to analyze trends for
        days: Number of days to analyze (default: 7, max: 90)
        db: Database session dependency

    Returns:
        TrendsResponse with comprehensive trend analysis

    Raises:
        HTTPException: 422 for invalid parameters, 500 for processing errors
    """
    try:
        # Validate inputs
        subreddit = validate_input_string(subreddit, "subreddit")

        # Validate days parameter
        if days < 1 or days > 90:
            raise HTTPException(status_code=422, detail="Days must be between 1 and 90")

        # Initialize services
        storage_service = StorageService(db)
        change_detection_service = ChangeDetectionService(db, storage_service)

        # Get trend analysis
        trend_data = change_detection_service.get_subreddit_trends(subreddit, days)

        # Build response
        response = TrendsResponse(
            subreddit=subreddit,
            analysis_period_days=days,
            trend_data=trend_data,
            generated_at=datetime.now(UTC)
        )

        return response

    except Exception as e:
        # Log the error for debugging but don't expose internal details
        logging.error(f"Error in get_trends endpoint: {type(e).__name__}: {e}")

        if isinstance(e, HTTPException):
            raise e

        # Return generic error to prevent information leakage
        raise HTTPException(status_code=500, detail="Error processing request") from None


@app.get("/debug/relevance/{topic}")
async def debug_relevance_scoring(
    topic: str, subreddit_names: str | None = None
) -> dict[str, Any]:
    """
    Debug endpoint to test relevance scoring in isolation.

    Args:
        topic: The topic to search for
        subreddit_names: Comma-separated list of subreddit names to test (default: search for topic-related subreddits)

    Returns:
        Debug information about the relevance scoring process
    """
    try:
        # Validate input
        topic = validate_input_string(topic, "topic")

        # Parse subreddit names or search for topic-related ones
        if subreddit_names:
            subreddit_name_list = [name.strip() for name in subreddit_names.split(",")]
        else:
            # Search for subreddits related to the topic for more relevant testing
            search_subreddits = reddit_service.search_subreddits(topic, limit=3)
            subreddit_name_list = [s.display_name for s in search_subreddits]

        # Create mock subreddit objects for testing
        mock_subreddits = []
        for name in subreddit_name_list:
            # Try to get real subreddit objects first
            try:
                real_subreddits = reddit_service.search_subreddits(name, limit=1)
                if real_subreddits:
                    mock_subreddits.extend(real_subreddits)
                    continue
            except Exception as e:
                logger.debug(f"Failed to search for subreddit '{name}': {e}")

            # If we can't find the subreddit, create a mock object
            class MockSubreddit:
                def __init__(self, display_name: str):
                    self.display_name = display_name
                    self.public_description = f"Debug subreddit: {display_name}"

            mock_subreddits.append(MockSubreddit(name))

        if not mock_subreddits:
            return {
                "error": "No subreddits could be found or created for testing",
                "subreddit_names": subreddit_name_list,
            }

        # Test relevance scoring with detailed logging
        scored_subreddits = score_and_rank_subreddits_concurrent(
            mock_subreddits, topic, reddit_service
        )

        # Collect debug information
        debug_info = {
            "topic": topic,
            "subreddits_tested": len(mock_subreddits),
            "subreddit_names": [
                getattr(s, "display_name", "unknown") for s in mock_subreddits
            ],
            "results": scored_subreddits,
            "total_matches": sum(s["score"] for s in scored_subreddits),
            "zero_score_count": sum(1 for s in scored_subreddits if s["score"] == 0),
            "api_status": "connected" if reddit_service else "disconnected",
        }

        # Add additional diagnostic info
        if all(s["score"] == 0 for s in scored_subreddits):
            debug_info["diagnosis"] = (
                "All scores are 0 - likely authentication or API issue"
            )
        elif not scored_subreddits:
            debug_info["diagnosis"] = (
                "No results returned - possible exception handling issue"
            )
        else:
            debug_info["diagnosis"] = "Scoring appears to be working normally"

        return debug_info

    except Exception as e:
        return {
            "error": f"Debug endpoint failed: {type(e).__name__}: {e}",
            "topic": topic,
            "subreddit_names": subreddit_names,
        }


@app.get("/debug/reddit-api")
async def debug_reddit_api() -> dict[str, Any]:
    """
    Debug endpoint to test Reddit API connectivity and configuration.

    Returns:
        Information about Reddit API status and configuration
    """
    try:
        from app.core.config import config

        debug_info = {
            "config_status": {
                "reddit_client_id_set": bool(config.REDDIT_CLIENT_ID),
                "reddit_client_secret_set": bool(config.REDDIT_CLIENT_SECRET),
                "reddit_user_agent_set": bool(config.REDDIT_USER_AGENT),
                "openai_api_key_set": bool(config.OPENAI_API_KEY),
            },
            "client_info": {
                "reddit_client_id_preview": config.REDDIT_CLIENT_ID[:8] + "..."
                if config.REDDIT_CLIENT_ID
                else None,
                "reddit_user_agent": config.REDDIT_USER_AGENT,
            },
        }

        # Test basic API access
        try:
            # Test subreddit search
            test_subreddits = reddit_service.search_subreddits("test", limit=1)
            debug_info["api_test_search"] = {
                "status": "success",
                "subreddits_found": len(test_subreddits),
            }
        except Exception as e:
            debug_info["api_test_search"] = {
                "status": "failed",
                "error": f"{type(e).__name__}: {e}",
            }

        # Test getting hot posts from a known subreddit
        try:
            test_posts = reddit_service.get_hot_posts("announcements", limit=5)
            debug_info["api_test_posts"] = {
                "status": "success",
                "posts_found": len(test_posts),
                "sample_titles": [
                    getattr(p, "title", "No title")[:50] + "..." for p in test_posts[:2]
                ],
            }
        except Exception as e:
            debug_info["api_test_posts"] = {
                "status": "failed",
                "error": f"{type(e).__name__}: {e}",
            }

        return debug_info

    except Exception as e:
        return {"error": f"Debug API endpoint failed: {type(e).__name__}: {e}"}


@app.get("/")
async def root() -> dict[str, str]:
    """Health check endpoint."""
    return {"message": "AI Reddit News Agent is running"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
