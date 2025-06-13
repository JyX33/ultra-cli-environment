import pytest
from app.utils.report_generator import create_markdown_report


def test_create_markdown_report():
    """Test that create_markdown_report generates correct Markdown structure."""
    # Sample report data
    report_data = [
        {
            "title": "First Test Post",
            "url": "https://reddit.com/r/test/post1",
            "post_summary": "This is a summary of the first post content.",
            "comments_summary": "Comments show positive sentiment about the topic."
        },
        {
            "title": "Second Test Post",
            "url": "https://reddit.com/r/test/post2", 
            "post_summary": "This is a summary of the second post content.",
            "comments_summary": "Mixed reactions in the comment section."
        }
    ]
    
    subreddit = "testsubreddit"
    topic = "artificial intelligence"
    
    # Call the function
    result = create_markdown_report(report_data, subreddit, topic)
    
    # Assert main header exists
    assert "# Reddit Report: artificial intelligence in r/testsubreddit" in result
    
    # Assert post sections exist
    assert "### 1. First Test Post" in result
    assert "### 2. Second Test Post" in result
    
    # Assert links are formatted correctly
    assert "**Link:** https://reddit.com/r/test/post1" in result
    assert "**Link:** https://reddit.com/r/test/post2" in result
    
    # Assert summaries are included
    assert "#### Post Summary" in result
    assert "#### Community Sentiment Summary" in result
    assert "This is a summary of the first post content." in result
    assert "Comments show positive sentiment about the topic." in result
    assert "This is a summary of the second post content." in result
    assert "Mixed reactions in the comment section." in result
    
    # Assert section separators
    assert "---" in result
    
    # Check that result is a string
    assert isinstance(result, str)
    assert len(result) > 0


def test_create_markdown_report_empty_data():
    """Test that function handles empty report data gracefully."""
    report_data = []
    subreddit = "empty"
    topic = "test"
    
    result = create_markdown_report(report_data, subreddit, topic)
    
    # Should still have header
    assert "# Reddit Report: test in r/empty" in result
    assert isinstance(result, str)


def test_create_markdown_report_single_post():
    """Test with a single post to verify numbering works correctly."""
    report_data = [
        {
            "title": "Only Post",
            "url": "https://reddit.com/r/test/single",
            "post_summary": "Single post summary.",
            "comments_summary": "Single post comments."
        }
    ]
    
    subreddit = "single"
    topic = "solo"
    
    result = create_markdown_report(report_data, subreddit, topic)
    
    assert "# Reddit Report: solo in r/single" in result
    assert "### 1. Only Post" in result
    assert "**Link:** https://reddit.com/r/test/single" in result
    assert "Single post summary." in result
    assert "Single post comments." in result