import io
import logging
import re
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from app.services.reddit_service import RedditService
from app.services.scraper_service import scrape_article_text
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
        raise HTTPException(status_code=500, detail="Error processing request")


@app.get("/generate-report/{subreddit}/{topic}")
async def generate_report(subreddit: str, topic: str) -> StreamingResponse:
    """
    Generate a comprehensive Markdown report for a given subreddit and topic.

    Args:
        subreddit: Name of the subreddit to analyze
        topic: Topic being reported on

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
            if post.is_self:
                # Text post - use selftext
                content = post.selftext
            else:
                # Link post - scrape article content
                content = scrape_article_text(post.url)

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

            # Add to report data
            report_data.append(
                {
                    "title": title,
                    "url": url,
                    "post_summary": post_summary,
                    "comments_summary": comments_summary,
                }
            )

        # Generate the Markdown report
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
        raise HTTPException(status_code=500, detail="Error processing request")


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
            except Exception:
                pass

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
