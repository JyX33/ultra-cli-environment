from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import io
from typing import List, Dict, Any

from app.services.reddit_service import RedditService
from app.services.summarizer_service import summarize_content
from app.utils.relevance import score_and_rank_subreddits
from app.utils.report_generator import create_markdown_report
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))
from app.services.scraper_service import scrape_article_text

app = FastAPI(title="AI Reddit News Agent", description="Automated Reddit content analysis and reporting")
reddit_service = RedditService()


@app.get("/discover-subreddits/{topic}")
async def discover_subreddits(topic: str) -> List[Dict[str, Any]]:
    """
    Discover and rank subreddits relevant to a given topic.
    
    Args:
        topic: The topic to search for relevant subreddits
        
    Returns:
        List of top 3 relevant subreddits with relevance scores
    """
    try:
        # Search for subreddits related to the topic
        subreddits = reddit_service.search_subreddits(topic)
        
        if not subreddits:
            raise HTTPException(status_code=404, detail=f"No subreddits found for topic: {topic}")
        
        # Score and rank subreddits by relevance
        scored_subreddits = score_and_rank_subreddits(subreddits, topic, reddit_service)
        
        if not scored_subreddits:
            raise HTTPException(status_code=404, detail=f"No relevant subreddits found for topic: {topic}")
        
        # Return top 3 results
        return scored_subreddits[:3]
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error discovering subreddits: {str(e)}")


@app.get("/generate-report/{subreddit}/{topic}")
async def generate_report(subreddit: str, topic: str):
    """
    Generate a comprehensive Markdown report for a given subreddit and topic.
    
    Args:
        subreddit: Name of the subreddit to analyze
        topic: Topic being reported on
        
    Returns:
        StreamingResponse with downloadable Markdown report
    """
    try:
        # Get relevant posts from the subreddit
        posts = reddit_service.get_relevant_posts(subreddit)
        
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
            
            # Get top comments and generate comments summary
            comments = reddit_service.get_top_comments(post.id, limit=10)
            comments_text = " ".join([comment.body for comment in comments if hasattr(comment, 'body')])
            comments_summary = summarize_content(comments_text, "comments") if comments_text else "No comments available for summary."
            
            # Add to report data
            report_data.append({
                'title': title,
                'url': url,
                'post_summary': post_summary,
                'comments_summary': comments_summary
            })
        
        # Generate the Markdown report
        markdown_report = create_markdown_report(report_data, subreddit, topic)
        
        # Create a downloadable file response
        file_buffer = io.StringIO(markdown_report)
        filename = f"reddit_report_{subreddit}_{topic.replace(' ', '_')}.md"
        
        return StreamingResponse(
            io.BytesIO(markdown_report.encode('utf-8')),
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"message": "AI Reddit News Agent is running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)