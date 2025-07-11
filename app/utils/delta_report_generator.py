# ABOUTME: Delta report generator using Jinja2 templates for Reddit change visualization
# ABOUTME: Creates enhanced markdown reports highlighting post changes, trends, and engagement deltas

from typing import Any

from jinja2 import BaseLoader, Environment

from app.models.types import (
    ActivityPattern,
    ChangeDetectionResult,
    PostUpdate,
    TrendData,
)


class StringTemplateLoader(BaseLoader):
    """Simple string-based template loader for Jinja2."""

    def __init__(self, templates: dict[str, str]) -> None:
        self.templates = templates

    def get_source(self, environment: Environment, template: str) -> tuple:
        if template not in self.templates:
            raise FileNotFoundError(f"Template {template} not found")
        source = self.templates[template]
        return source, None, lambda: True


# Jinja2 template definitions
TEMPLATES = {
    "delta_report": """# 🔍 Reddit Update Report: {{ topic }} in r/{{ subreddit }}

*Generated: {{ timestamp.strftime('%Y-%m-%d %H:%M:%S UTC') }}*

---

## 📊 **Summary**

{% if total_new_posts > 0 -%}
🆕 **{{ total_new_posts }} new post{{ 's' if total_new_posts != 1 else '' }}** discovered
{% else -%}
🔍 **No new posts** discovered
{% endif %}
{% if posts_with_significant_changes > 0 -%}
📈 **{{ posts_with_significant_changes }} post{{ 's' if posts_with_significant_changes != 1 else '' }}** with significant changes
{% else -%}
📊 **No significant changes** detected
{% endif %}
{% if trending_up_posts > 0 -%}
📈 **{{ trending_up_posts }} post{{ 's' if trending_up_posts != 1 else '' }}** trending up
{% endif %}
{% if trending_down_posts > 0 -%}
📉 **{{ trending_down_posts }} post{{ 's' if trending_down_posts != 1 else '' }}** trending down
{% endif %}

---

{% if new_posts -%}
## 🆕 New Posts

{% for post in new_posts -%}
{{ format_post_changes(post, loop.index) }}

{% if not loop.last %}---{% endif %}

{% endfor %}
{% endif %}

{% if updated_posts -%}
## 📈 Updated Posts

{% for post in updated_posts -%}
{{ format_post_changes(post, loop.index) }}

{% if not loop.last %}---{% endif %}

{% endfor %}
{% endif %}

{% if not new_posts and not updated_posts -%}
## 🤷 **No Updates Detected**

All quiet on the r/{{ subreddit }} front! No new posts or significant changes since the last check.

*Try checking back later or consider broadening your search criteria.*
{% endif %}

{% if trend_data -%}
---

{{ format_trend_summary(trend_data) }}
{% endif %}

---

*🤖 Report generated by AI Reddit Agent*""",

    "post_changes": """### {{ post_number }}. {{ escape_markdown(post.title) }}

{% if post.update_type == 'new' -%}
🆕 **NEW**
{% elif post.engagement_delta and post.engagement_delta.is_trending_up -%}
📈 **TRENDING UP**
{% elif post.engagement_delta and post.engagement_delta.is_trending_down -%}
📉 **TRENDING DOWN**
{% elif post.update_type in ['score_change', 'comment_change', 'both_change'] -%}
📊 **UPDATED**
{% endif %}

{% if post.update_type == 'new' -%}
**Score:** {{ "{:,}".format(post.current_score) }} points
**Comments:** {{ post.current_comments }}
{% else -%}
**Score:** {{ "{:,}".format(post.current_score) }} points {% if post.engagement_delta -%}({{ '+' if post.engagement_delta.score_delta >= 0 else '' }}{{ "{:,}".format(post.engagement_delta.score_delta) }} points){% endif %}
**Comments:** {{ post.current_comments }}{% if post.engagement_delta %} ({{ '+' if post.engagement_delta.comments_delta >= 0 else '' }}{{ "{:,}".format(post.engagement_delta.comments_delta) }} comments){% endif %}
{% endif %}

{% if post.engagement_delta and post.engagement_delta.engagement_rate != 0.0 -%}
Engagement rate: **{{ "{:,.1f}".format(post.engagement_delta.engagement_rate) }} points/hour**
{% endif %}

*Posted in r/{{ post.subreddit }}*""",

    "trend_summary": """## 📊 **Trend Analysis** ({{ trend.analysis_period_days }}-day period)

{% set activity_icons = {
    'STEADY': '➡️',
    'INCREASING': '📈',
    'DECREASING': '📉',
    'VOLATILE': '📊',
    'DORMANT': '😴',
    'SURGE': '🚀'
} -%}

**Activity:** {{ trend.engagement_trend.name }} {{ activity_icons.get(trend.engagement_trend.name, '📊') }}
**Best posting time:** {{ format_hour(trend.best_posting_hour) }}
**Average posts/day:** {{ trend.average_posts_per_day }}
**Change from previous period:** {{ '+' if trend.change_from_previous_period >= 0 else '' }}{{ "{:.1f}".format(trend.change_from_previous_period) }}%
**Predicted engagement:** {{ "{:,.1f}".format(trend.predicted_daily_engagement) }} points/day

{% if trend.is_trending_up -%}
📈 **This subreddit is gaining momentum!** Consider posting during peak hours for maximum visibility.
{% elif trend.is_trending_down -%}
📉 **Activity has been declining.** This might be a good time to post high-quality content to stand out.
{% elif trend.engagement_trend == ActivityPattern.VOLATILE -%}
📊 **Activity patterns are unpredictable.** Monitor closely for optimal posting opportunities.
{% elif trend.engagement_trend == ActivityPattern.DORMANT -%}
😴 **Very low activity detected.** Consider checking more active subreddits or wait for increased activity.
{% else -%}
➡️ **Steady activity patterns.** Consistent posting schedule recommended.
{% endif %}""",

    "comment_changes": """📝 **Comment Activity**

{% if new_comments > 0 -%}
🆕 **{{ new_comments }} new comments**
{% endif %}
{% if score_changes > 0 -%}
📊 **{{ score_changes }} comments** with score changes
{% endif %}
{% if total_comments > 0 -%}
💬 **{{ total_comments }} total comments** in discussion
{% endif %}

*Comment analysis feature coming soon*"""
}


def _create_jinja_env() -> Environment:
    """Create and configure Jinja2 environment with custom functions."""
    env = Environment(loader=StringTemplateLoader(TEMPLATES))

    # Add custom functions
    env.globals['escape_markdown'] = escape_markdown_content
    env.globals['format_post_changes'] = _format_post_changes_template
    env.globals['format_trend_summary'] = _format_trend_summary_template
    env.globals['format_hour'] = _format_hour
    env.globals['ActivityPattern'] = ActivityPattern

    return env


def escape_markdown_content(content: str) -> str:
    """Escape markdown special characters in content."""
    if not content:
        return ""

    # Escape markdown special characters
    markdown_chars = ['*', '_', '[', ']', '(', ')', '#', '`', '~', '>', '|']
    escaped_content = content

    for char in markdown_chars:
        escaped_content = escaped_content.replace(char, f'\\{char}')

    return escaped_content


def _format_hour(hour: int) -> str:
    """Format hour as 12-hour time with AM/PM."""
    if hour == 0:
        return "12:00 AM"
    elif hour < 12:
        return f"{hour}:00 AM"
    elif hour == 12:
        return "12:00 PM"
    else:
        return f"{hour - 12}:00 PM"


def _format_post_changes_template(post: PostUpdate, post_number: int) -> str:
    """Template function for formatting post changes."""
    env = _create_jinja_env()
    template = env.get_template("post_changes")
    return template.render(post=post, post_number=post_number, escape_markdown=escape_markdown_content)


def _format_trend_summary_template(trend: TrendData) -> str:
    """Template function for formatting trend summary."""
    env = _create_jinja_env()
    template = env.get_template("trend_summary")
    return template.render(trend=trend, format_hour=_format_hour)


def create_delta_report(
    delta_data: ChangeDetectionResult,
    subreddit: str,
    topic: str,
    trend_data: TrendData | None = None
) -> str:
    """
    Create a comprehensive delta report showing changes in Reddit posts.

    Args:
        delta_data: Change detection results with new and updated posts
        subreddit: The subreddit name
        topic: The topic being tracked
        trend_data: Optional trend analysis data

    Returns:
        Formatted markdown delta report
    """
    env = _create_jinja_env()
    template = env.get_template("delta_report")

    return template.render(
        topic=topic,
        subreddit=subreddit,
        timestamp=delta_data.detection_timestamp,
        total_new_posts=delta_data.total_new_posts,
        total_updated_posts=delta_data.total_updated_posts,
        posts_with_significant_changes=delta_data.posts_with_significant_changes,
        trending_up_posts=delta_data.trending_up_posts,
        trending_down_posts=delta_data.trending_down_posts,
        new_posts=delta_data.new_posts,
        updated_posts=delta_data.updated_posts,
        trend_data=trend_data,
        format_post_changes=_format_post_changes_template,
        format_trend_summary=_format_trend_summary_template
    )


def format_post_changes(post: PostUpdate) -> str:
    """
    Format individual post changes with engagement indicators.

    Args:
        post: PostUpdate object with change information

    Returns:
        Formatted markdown section for the post
    """
    return _format_post_changes_template(post, 1)


def format_comment_changes(comment_data: dict[str, Any]) -> str:
    """
    Format comment changes section (placeholder for future implementation).

    Args:
        comment_data: Dictionary containing comment change information

    Returns:
        Formatted markdown section for comment changes
    """
    env = _create_jinja_env()
    template = env.get_template("comment_changes")

    return template.render(
        new_comments=comment_data.get("new_comments", 0),
        score_changes=comment_data.get("score_changes", 0),
        total_comments=comment_data.get("total_comments", 0)
    )


def format_trend_summary(trend_data: TrendData) -> str:
    """
    Format trend analysis summary with activity patterns and insights.

    Args:
        trend_data: TrendData object with subreddit trend information

    Returns:
        Formatted markdown section for trend analysis
    """
    return _format_trend_summary_template(trend_data)
