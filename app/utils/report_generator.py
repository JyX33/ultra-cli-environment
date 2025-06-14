import html
import re


def escape_markdown_content(content: str) -> str:
    """
    Escape potentially dangerous content for safe markdown rendering.
    
    Args:
        content: The content to escape
        
    Returns:
        Escaped content safe for markdown
    """
    if not content or not isinstance(content, str):
        return ""

    # HTML escape first
    content = html.escape(content)

    # Remove dangerous URL schemes
    content = re.sub(r'(javascript|data|vbscript|file|ftp):', 'unsafe-scheme:', content, flags=re.IGNORECASE)

    # Remove dangerous HTML attributes
    content = re.sub(r'(onerror|onload|onclick|onmouseover|onfocus|onblur)=', 'unsafe-attr=', content, flags=re.IGNORECASE)

    # Escape template injection patterns
    content = re.sub(r'\$\{[^}]*\}', '[TEMPLATE-REMOVED]', content)
    content = re.sub(r'\{\{[^}]*\}\}', '[TEMPLATE-REMOVED]', content)

    return content


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
    # Build the main header with escaped content
    report_lines = [f"# Reddit Report: {escape_markdown_content(topic)} in r/{escape_markdown_content(subreddit)}", ""]

    # Add each post section
    for index, post in enumerate(report_data, 1):
        # Section separator (except for first post)
        if index > 1:
            report_lines.append("---")
            report_lines.append("")

        # Post header with number and title (escaped)
        report_lines.append(f"### {index}. {escape_markdown_content(post['title'])}")
        report_lines.append(f"**Link:** {escape_markdown_content(post['url'])}")
        report_lines.append("")

        # Post summary section (escaped)
        report_lines.append("#### Post Summary")
        report_lines.append(escape_markdown_content(post['post_summary']))
        report_lines.append("")

        # Comments summary section (escaped)
        report_lines.append("#### Community Sentiment Summary")
        report_lines.append(escape_markdown_content(post['comments_summary']))
        report_lines.append("")

    return "\n".join(report_lines)
