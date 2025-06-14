import io
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

app = FastAPI(title="AI Reddit News Agent", description="Automated Reddit content analysis and reporting")
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
        raise HTTPException(status_code=422, detail=f"Invalid {param_name}: must be a non-empty string")

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
            raise HTTPException(status_code=422, detail=f"Invalid {param_name}: contains potentially malicious content")

    # Length validation
    if len(input_str) > 100:
        raise HTTPException(status_code=422, detail=f"Invalid {param_name}: too long (max 100 characters)")

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
            raise HTTPException(status_code=404, detail=f"No subreddits found for topic: {topic}")

        # Score and rank subreddits by relevance using concurrent processing
        scored_subreddits = score_and_rank_subreddits_concurrent(subreddits, topic, reddit_service)

        if not scored_subreddits:
            raise HTTPException(status_code=404, detail=f"No relevant subreddits found for topic: {topic}")

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
                detail=f"No relevant posts found in r/{subreddit} for the last day"
            )

        # Initialize report data list
        report_data = []

        # Process each post
        for post in posts:
            # Get post title and URL
            title = post.title
            url = post.url if not post.is_self else f"https://reddit.com{post.permalink}"

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
            comments_text = get_comments_summary_stream(post.id, reddit_service, max_memory_mb=10, top_count=10)
            comments_summary = summarize_content(comments_text, "comments") if comments_text != "No comments available for summary." else "No comments available for summary."

            # Add to report data
            report_data.append({
                'title': title,
                'url': url,
                'post_summary': post_summary,
                'comments_summary': comments_summary
            })

        # Generate the Markdown report
        markdown_report = create_markdown_report(report_data, subreddit, topic)

        # Create a downloadable file response with secure filename
        file_buffer = io.StringIO(markdown_report)
        filename = generate_safe_filename(subreddit, topic)

        return StreamingResponse(
            io.BytesIO(markdown_report.encode('utf-8')),
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        # Don't expose internal error details
        raise HTTPException(status_code=500, detail="Error processing request")


@app.get("/")
async def root() -> dict[str, str]:
    """Health check endpoint."""
    return {"message": "AI Reddit News Agent is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
