# ABOUTME: Optimized FastAPI application with performance monitoring, caching, and query optimization
# ABOUTME: Enhanced version of main.py with integrated performance improvements and monitoring

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
import logging
import os
import re
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from prawcore.exceptions import Forbidden, NotFound
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.db.session import get_db
from app.models.api_models import (
    PostUpdateResponse,
    UpdateCheckResponse,
)
from app.services.cache_service import RedditCacheService
from app.services.change_detection_service import ChangeDetectionService
from app.services.optimized_storage_service import OptimizedStorageService
from app.services.performance_monitoring_service import PerformanceMonitoringService
from app.services.reddit_service import RedditService
from app.utils.relevance import score_and_rank_subreddits_concurrent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)

# Set specific loggers for performance monitoring
logging.getLogger("app.services.optimized_storage_service").setLevel(logging.DEBUG)
logging.getLogger("app.services.performance_monitoring_service").setLevel(logging.INFO)

# Initialize global services
reddit_service = RedditService()

# Initialize performance monitoring
performance_monitor = PerformanceMonitoringService(
    enable_system_monitoring=True,
    monitoring_interval_seconds=10.0
)

# Initialize cache service
ENABLE_REDIS = os.getenv("ENABLE_REDIS", "false").lower() == "true"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

cache_service = RedditCacheService(
    max_size=2000,
    default_ttl=300,  # 5 minutes default
    enable_redis=ENABLE_REDIS,
    redis_url=REDIS_URL if ENABLE_REDIS else None
)


class PerformanceMiddleware(BaseHTTPMiddleware):
    """Middleware for automatic performance monitoring."""

    async def dispatch(self, request: Request, call_next: Callable) -> Any:
        """Process request with performance monitoring."""
        datetime.now()

        # Start database query counting
        if hasattr(request.state, 'db_session'):
            # This would be set by a database middleware
            pass

        with performance_monitor.measure_time(f"request_{request.url.path}", {
            "method": request.method,
            "endpoint": request.url.path
        }) as timer:
            response = await call_next(request)

        # Record response time
        duration_ms = timer.duration * 1000 if timer.duration is not None else 0
        performance_monitor.record_request(duration_ms)

        # Add performance headers
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
        response.headers["X-Cache-Service"] = "enabled" if cache_service else "disabled"

        return response


# Create FastAPI app with performance enhancements
app = FastAPI(
    title="AI Reddit News Agent (Optimized)",
    description="Automated Reddit content analysis and reporting with performance optimizations",
    version="2.0.0"
)

# Add performance middleware
app.add_middleware(PerformanceMiddleware)


def validate_input_string(input_str: str, param_name: str) -> str:
    """Validate and sanitize input string parameters."""
    if not input_str or len(input_str.strip()) == 0:
        raise HTTPException(status_code=400, detail=f"{param_name} cannot be empty")

    if len(input_str) > 100:
        raise HTTPException(status_code=400, detail=f"{param_name} too long (max 100 characters)")

    if not re.match(r'^[a-zA-Z0-9_\-\s]+$', input_str):
        raise HTTPException(status_code=400, detail=f"{param_name} contains invalid characters")

    return input_str.strip()


def get_optimized_storage_service(session: Session = Depends(get_db)) -> OptimizedStorageService:
    """Get optimized storage service instance."""
    service = OptimizedStorageService(session)
    service.enable_query_logging(True)  # Enable for performance analysis
    return service


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize services on startup."""
    performance_monitor.start_monitoring()
    logger = logging.getLogger(__name__)
    logger.info("Optimized Reddit Agent API started with performance monitoring")

    # Log configuration
    logger.info(f"Redis cache: {'enabled' if ENABLE_REDIS else 'disabled'}")
    logger.info("Performance monitoring: enabled")
    logger.info("Query optimization: enabled")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup on shutdown."""
    performance_monitor.stop_monitoring()
    logging.getLogger(__name__).info("Optimized Reddit Agent API shutdown")


@app.get("/")
async def root() -> dict[str, Any]:
    """Root endpoint with service status."""
    return {
        "message": "AI Reddit News Agent (Optimized)",
        "version": "2.0.0",
        "features": {
            "performance_monitoring": True,
            "query_optimization": True,
            "caching": cache_service is not None,
            "redis_cache": ENABLE_REDIS
        },
        "endpoints": [
            "/discover-subreddits/{topic}",
            "/generate-report/{subreddit}/{topic}",
            "/check-updates/{subreddit}/{topic}",
            "/history/{subreddit}",
            "/trends/{subreddit}",
            "/performance/stats",
            "/performance/report"
        ]
    }


@app.get("/performance/stats")
async def get_performance_stats() -> dict[str, Any]:
    """Get current performance statistics."""
    stats = performance_monitor.get_performance_summary()
    cache_stats = cache_service.get_cache_stats() if cache_service else None

    return {
        "performance": stats,
        "cache": cache_stats,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/performance/report")
async def get_performance_report() -> dict[str, Any]:
    """Get detailed performance report with trends."""
    summary = performance_monitor.get_performance_summary()
    trends = performance_monitor.analyze_performance_trends()

    return {
        "summary": summary,
        "trends": trends,
        "recent_metrics": [
            {
                "name": metric.name,
                "value": metric.value,
                "unit": metric.unit,
                "timestamp": metric.timestamp.isoformat(),
                "tags": metric.tags
            }
            for metric in performance_monitor.get_recent_metrics(10)
        ],
        "generated_at": datetime.now().isoformat()
    }


@app.post("/performance/reset")
async def reset_performance_counters() -> dict[str, str]:
    """Reset performance counters (useful for testing)."""
    performance_monitor.reset_counters()
    return {"message": "Performance counters reset"}


@app.get("/check-updates/{subreddit}/{topic}", response_model=UpdateCheckResponse)
async def check_updates_optimized(
    subreddit: str,
    topic: str,
    storage_service: OptimizedStorageService = Depends(get_optimized_storage_service)
) -> UpdateCheckResponse:
    """Check for updates with optimized performance and caching."""
    subreddit = validate_input_string(subreddit, "subreddit")
    topic = validate_input_string(topic, "topic")

    # Check cache first
    if cache_service:
        cached_result = cache_service.get_check_run_results(subreddit, topic)
        if cached_result:
            performance_monitor.record_cache_operation(hit=True)
            return UpdateCheckResponse(**cached_result)
        performance_monitor.record_cache_operation(hit=False)

    try:
        with performance_monitor.measure_time("reddit_api_fetch") as timer:
            # Get posts from Reddit
            try:
                posts_data = reddit_service.get_relevant_posts_optimized(subreddit)
            except NotFound:
                raise HTTPException(
                    status_code=404,
                    detail=f"Subreddit r/{subreddit} not found. Please check the subreddit name and try again."
                )
            except Forbidden:
                raise HTTPException(
                    status_code=422,
                    detail=f"Subreddit r/{subreddit} is private or restricted and cannot be accessed."
                )
            performance_monitor.record_database_query()

        # Get last check run using optimized query
        with performance_monitor.measure_time("get_latest_check_run") as timer:
            last_check_run = storage_service.get_latest_check_run(subreddit, topic)
            performance_monitor.record_database_query(timer.duration * 1000 if timer.duration is not None else 0)

        # Create new check run
        with performance_monitor.measure_time("create_check_run") as timer:
            check_run_id = storage_service.create_check_run(subreddit, topic)
            storage_service.session.commit()
            performance_monitor.record_database_query(timer.duration * 1000 if timer.duration is not None else 0)

        # Convert Reddit posts to dictionaries for storage
        with performance_monitor.measure_time("convert_posts") as timer:
            current_posts = []
            for post in posts_data:
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
                    "permalink": post.permalink,
                    "check_run_id": check_run_id
                }
                current_posts.append(post_data)

        # Store posts efficiently
        with performance_monitor.measure_time("bulk_store_posts") as timer:
            for post_data in current_posts:
                storage_service.save_post(post_data)
            storage_service.session.commit()

        # Use change detection service
        change_detection_service = ChangeDetectionService(storage_service.session, storage_service)
        last_check_time = last_check_run.timestamp if last_check_run else None

        # Detect changes using converted post data
        with performance_monitor.measure_time("change_detection") as timer:
            detection_result = change_detection_service.detect_all_changes(
                current_posts=current_posts,
                last_check_time=last_check_time,
                check_run_id=check_run_id,
                subreddit=subreddit
            )

        new_posts = detection_result.new_posts
        updated_posts = detection_result.updated_posts
        new_comments = []  # Not implemented yet in change detection service

        # Generate summary
        summary = f"Found {len(new_posts)} new posts, {len(updated_posts)} updated posts, and {len(new_comments)} new comments in r/{subreddit}"

        # Convert PostUpdate objects to PostUpdateResponse format (same as standard API)
        new_posts_response = []
        for post_update in new_posts:
            post_response = PostUpdateResponse(
                post_id=post_update.reddit_post_id,
                title=post_update.title,
                author=None,  # Will be filled from original post data if available
                subreddit=post_update.subreddit,
                url="",  # Will be filled from original post data if available
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
        for post_update in updated_posts:
            post_response = PostUpdateResponse(
                post_id=post_update.reddit_post_id,
                title=post_update.title,
                author=None,  # Will be filled from original post data if available
                subreddit=post_update.subreddit,
                url="",  # Will be filled from original post data if available
                score=post_update.current_score,
                num_comments=post_update.current_comments,
                created_utc=post_update.current_timestamp,
                is_new=False,
                score_change=post_update.engagement_delta.score_delta if post_update.engagement_delta else None,
                comment_change=post_update.engagement_delta.comments_delta if post_update.engagement_delta else None,
                engagement_delta=post_update.engagement_delta
            )
            updated_posts_response.append(post_response)

        # Enrich posts with original Reddit data (URL and author)
        post_data_map = {post["post_id"]: post for post in current_posts}

        for post_response in new_posts_response:
            if post_response.post_id in post_data_map:
                original_post = post_data_map[post_response.post_id]
                post_response.url = original_post["url"]
                post_response.author = original_post["author"]

        for post_response in updated_posts_response:
            if post_response.post_id in post_data_map:
                original_post = post_data_map[post_response.post_id]
                post_response.url = original_post["url"]
                post_response.author = original_post["author"]

        # Prepare response - using same format as standard API for consistency
        response_data = {
            "new_posts": new_posts_response,
            "updated_posts": updated_posts_response,
            "new_comments": new_comments,
            "summary": summary
        }

        # Cache the result
        if cache_service:
            cache_service.set_check_run_results(
                subreddit,
                topic,
                response_data,
                ttl=180  # 3 minutes cache
            )

        # Update check run counters
        storage_service.update_check_run_counters(
            check_run_id,
            posts_found=len(posts_data),
            new_posts=len(new_posts)
        )
        storage_service.session.commit()

        # Log performance metrics
        query_count = storage_service.get_query_count()
        logging.getLogger(__name__).info(
            f"Check updates completed: {query_count} queries, "
            f"{len(new_posts)} new posts, {len(updated_posts)} updated posts"
        )

        new_posts_list: list[PostUpdateResponse] = response_data["new_posts"]  # type: ignore
        updated_posts_list: list[PostUpdateResponse] = response_data["updated_posts"]  # type: ignore
        summary_dict: dict[str, Any] = response_data["summary"]  # type: ignore

        return UpdateCheckResponse(
            subreddit=subreddit,
            topic=topic,
            check_time=datetime.now(UTC),
            last_check_time=last_check_run.timestamp if last_check_run else None,
            new_posts=new_posts_list,
            updated_posts=updated_posts_list,
            total_posts_found=len(posts_data),
            new_comments=[],
            updated_comments=[],
            total_comments_found=0,
            summary=summary_dict,
            trends=None,
            is_first_check=last_check_run is None,
            check_run_id=check_run_id
        )

    except HTTPException:
        # Re-raise HTTPExceptions (like 404, 422) without modification
        raise
    except Exception as e:
        logging.getLogger(__name__).error(f"Error in check_updates_optimized: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check updates: {e!s}") from None


@app.get("/trending/{subreddit}")
async def get_trending_posts_optimized(
    subreddit: str,
    hours: int = 24,
    storage_service: OptimizedStorageService = Depends(get_optimized_storage_service)
) -> dict[str, Any]:
    """Get trending posts using optimized queries."""
    subreddit = validate_input_string(subreddit, "subreddit")

    # Check cache first
    if cache_service:
        cached_trending = cache_service.get_trending_posts(subreddit)
        if cached_trending:
            performance_monitor.record_cache_operation(hit=True)
            return {"trending_posts": cached_trending}
        performance_monitor.record_cache_operation(hit=False)

    try:
        with performance_monitor.measure_time("get_trending_posts") as timer:
            trending_posts = storage_service.get_trending_posts_optimized(
                subreddit=subreddit,
                time_window_hours=hours,
                min_score=10
            )
            # Safe access to timer.duration after the operation
            query_time = timer.duration * 1000 if timer.duration is not None else 0
            performance_monitor.record_database_query(query_time)

        # Cache the results
        if cache_service:
            cache_service.set_trending_posts(subreddit, trending_posts, ttl=900)  # 15 minutes

        return {
            "subreddit": subreddit,
            "time_window_hours": hours,
            "trending_posts": trending_posts,
            "generated_at": datetime.now().isoformat()
        }

    except Exception as e:
        logging.getLogger(__name__).error(f"Error getting trending posts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get trending posts: {e!s}") from None


@app.get("/analytics/{subreddit}")
async def get_subreddit_analytics(
    subreddit: str,
    days: int = 7,
    storage_service: OptimizedStorageService = Depends(get_optimized_storage_service)
) -> dict[str, Any]:
    """Get detailed analytics for a subreddit using optimized aggregations."""
    subreddit = validate_input_string(subreddit, "subreddit")

    try:
        # Use optimized statistics query
        with performance_monitor.measure_time("get_posts_with_statistics") as timer:
            start_date = datetime.now(UTC) - timedelta(days=days)
            posts_with_stats = storage_service.get_posts_with_statistics(
                subreddit=subreddit,
                start_date=start_date
            )
            performance_monitor.record_database_query(timer.duration * 1000 if timer.duration is not None else 0)

        # Compute aggregate statistics
        if posts_with_stats:
            total_posts = len(posts_with_stats)
            total_comments = sum(p['comment_count'] for p in posts_with_stats)
            avg_score = sum(p['post'].score for p in posts_with_stats) / total_posts
            avg_engagement = sum(p['engagement_ratio'] for p in posts_with_stats) / total_posts

            top_posts = sorted(
                posts_with_stats,
                key=lambda x: x['post'].score,
                reverse=True
            )[:5]
        else:
            total_posts = total_comments = avg_score = avg_engagement = 0
            top_posts = []

        analytics = {
            "subreddit": subreddit,
            "analysis_period_days": days,
            "statistics": {
                "total_posts": total_posts,
                "total_comments": total_comments,
                "average_score": avg_score,
                "average_engagement_ratio": avg_engagement
            },
            "top_posts": [
                {
                    "post_id": post['post'].post_id,
                    "title": post['post'].title,
                    "score": post['post'].score,
                    "comment_count": post['comment_count'],
                    "engagement_ratio": post['engagement_ratio']
                }
                for post in top_posts
            ],
            "generated_at": datetime.now().isoformat()
        }

        return analytics

    except Exception as e:
        logging.getLogger(__name__).error(f"Error getting analytics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get analytics: {e!s}") from None


@app.post("/optimize-database")
async def optimize_database_performance(
    storage_service: OptimizedStorageService = Depends(get_optimized_storage_service)
) -> dict[str, Any]:
    """Trigger database optimization."""
    try:
        with performance_monitor.measure_time("database_optimization") as timer:
            result = storage_service.optimize_database_performance()

        return {
            "optimization_result": result,
            "duration_ms": timer.duration * 1000 if timer.duration is not None else 0,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logging.getLogger(__name__).error(f"Error optimizing database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to optimize database: {e!s}") from None


# Include original endpoints for backward compatibility
@app.get("/discover-subreddits/{topic}")
async def discover_subreddits(topic: str) -> dict[str, Any]:
    """Discover relevant subreddits for a topic."""
    topic = validate_input_string(topic, "topic")

    with performance_monitor.measure_time("discover_subreddits"):
        try:
            subreddits = reddit_service.search_subreddits(topic, limit=10)
            scored_subreddits = score_and_rank_subreddits_concurrent(subreddits, topic, reddit_service)
            top_3 = scored_subreddits[:3]

            return {
                "topic": topic,
                "subreddits": [
                    {
                        "name": sub["name"],
                        "description": sub["description"] or "No description available",
                        "subscribers": sub.get("subscribers", 0),
                        "relevance_score": sub["score"],
                    }
                    for sub in top_3
                ],
            }
        except Exception as e:
            logging.getLogger(__name__).error(f"Error discovering subreddits: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to discover subreddits: {e!s}") from None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
