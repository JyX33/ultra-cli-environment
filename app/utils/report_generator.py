def create_markdown_report(report_data: list, subreddit: str, topic: str) -> str:
    """
    Create a Markdown report from Reddit post data.
    
    Args:
        report_data: List of dictionaries containing post data with keys:
                    'title', 'url', 'post_summary', 'comments_summary'
        subreddit: Name of the subreddit
        topic: Topic being reported on
        
    Returns:
        str: Complete Markdown report as a string
    """
    # Build the main header
    report_lines = [f"# Reddit Report: {topic} in r/{subreddit}", ""]
    
    # Add each post section
    for index, post in enumerate(report_data, 1):
        # Section separator (except for first post)
        if index > 1:
            report_lines.append("---")
            report_lines.append("")
        
        # Post header with number and title
        report_lines.append(f"### {index}. {post['title']}")
        report_lines.append(f"**Link:** {post['url']}")
        report_lines.append("")
        
        # Post summary section
        report_lines.append("#### Post Summary")
        report_lines.append(post['post_summary'])
        report_lines.append("")
        
        # Comments summary section
        report_lines.append("#### Community Sentiment Summary")
        report_lines.append(post['comments_summary'])
        report_lines.append("")
    
    return "\n".join(report_lines)