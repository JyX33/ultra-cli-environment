# ABOUTME: Comprehensive test suite for delta report generator functionality
# ABOUTME: Tests delta report formatting, change highlighting, trend visualization and markdown escaping

from datetime import UTC, datetime

from app.models.types import (
    ActivityPattern,
    ChangeDetectionResult,
    EngagementDelta,
    PostUpdate,
    TrendData,
)
from app.utils.delta_report_generator import (
    create_delta_report,
    format_comment_changes,
    format_post_changes,
    format_trend_summary,
)


class TestDeltaReportFormatting:
    """Tests for delta report formatting with change highlighting."""

    def test_create_delta_report_with_new_posts(self):
        """Test delta report creation with new posts only."""
        # Setup test data
        engagement_delta = EngagementDelta(
            post_id="abc123",
            score_delta=0,
            comments_delta=0,
            previous_score=0,
            current_score=150,
            previous_comments=0,
            current_comments=25,
            time_span_hours=1.0,
            engagement_rate=0.0
        )

        new_post = PostUpdate(
            post_id=1,
            reddit_post_id="abc123",
            subreddit="technology",
            title="New AI Breakthrough",
            update_type="new",
            current_score=150,
            current_comments=25,
            current_timestamp=datetime.now(UTC),
            previous_score=None,
            previous_comments=None,
            previous_timestamp=None,
            engagement_delta=engagement_delta
        )

        delta_data = ChangeDetectionResult(
            check_run_id=1,
            subreddit="technology",
            detection_timestamp=datetime.now(UTC),
            new_posts=[new_post],
            updated_posts=[],
            total_new_posts=1,
            total_updated_posts=0,
            posts_with_significant_changes=0,
            trending_up_posts=0,
            trending_down_posts=0
        )

        # Test report creation
        report = create_delta_report(delta_data, "technology", "AI breakthroughs")

        # Verify report structure
        assert "# 🔍 Reddit Update Report: AI breakthroughs in r/technology" in report
        assert "📊 **Summary**" in report
        assert "🆕 **1 new post** discovered" in report
        assert "📊 **No significant changes** detected" in report
        assert "## 🆕 New Posts" in report
        assert "### 1. New AI Breakthrough" in report
        assert "**Score:** 150 points" in report
        assert "**Comments:** 25" in report
        assert "🆕 **NEW**" in report

    def test_create_delta_report_with_updated_posts(self):
        """Test delta report creation with updated posts showing changes."""
        # Setup test data with significant changes
        engagement_delta = EngagementDelta(
            post_id="def456",
            score_delta=75,
            comments_delta=10,
            previous_score=100,
            current_score=175,
            previous_comments=15,
            current_comments=25,
            time_span_hours=2.0,
            engagement_rate=37.5
        )

        updated_post = PostUpdate(
            post_id=2,
            reddit_post_id="def456",
            subreddit="programming",
            title="Python Performance Tips",
            update_type="both_change",
            current_score=175,
            current_comments=25,
            current_timestamp=datetime.now(UTC),
            previous_score=100,
            previous_comments=15,
            previous_timestamp=datetime.now(UTC),
            engagement_delta=engagement_delta
        )

        delta_data = ChangeDetectionResult(
            check_run_id=2,
            subreddit="programming",
            detection_timestamp=datetime.now(UTC),
            new_posts=[],
            updated_posts=[updated_post],
            total_new_posts=0,
            total_updated_posts=1,
            posts_with_significant_changes=1,
            trending_up_posts=1,
            trending_down_posts=0
        )

        # Test report creation
        report = create_delta_report(delta_data, "programming", "Python tips")

        # Verify change indicators
        assert "📈 **1 post** with significant changes" in report
        assert "## 📈 Updated Posts" in report
        assert "### 1. Python Performance Tips" in report
        assert "+75 points" in report
        assert "+10 comments" in report
        assert "📈 **TRENDING UP**" in report
        assert "Engagement rate: **37.5 points/hour**" in report

    def test_create_delta_report_with_trending_down_posts(self):
        """Test delta report with posts trending down."""
        engagement_delta = EngagementDelta(
            post_id="ghi789",
            score_delta=-30,
            comments_delta=-2,
            previous_score=200,
            current_score=170,
            previous_comments=17,
            current_comments=15,
            time_span_hours=1.5,
            engagement_rate=-20.0
        )

        trending_down_post = PostUpdate(
            post_id=3,
            reddit_post_id="ghi789",
            subreddit="worldnews",
            title="Breaking News Update",
            update_type="both_change",
            current_score=170,
            current_comments=15,
            current_timestamp=datetime.now(UTC),
            previous_score=200,
            previous_comments=17,
            previous_timestamp=datetime.now(UTC),
            engagement_delta=engagement_delta
        )

        delta_data = ChangeDetectionResult(
            check_run_id=3,
            subreddit="worldnews",
            detection_timestamp=datetime.now(UTC),
            new_posts=[],
            updated_posts=[trending_down_post],
            total_new_posts=0,
            total_updated_posts=1,
            posts_with_significant_changes=1,
            trending_up_posts=0,
            trending_down_posts=1
        )

        report = create_delta_report(delta_data, "worldnews", "breaking news")

        # Verify downward trend indicators
        assert "📉 **TRENDING DOWN**" in report
        assert "-30 points" in report
        assert "-2 comments" in report
        assert "Engagement rate: **-20.0 points/hour**" in report


class TestChangeHighlighting:
    """Tests for change highlighting and trend summary sections."""

    def test_format_post_changes_new_post(self):
        """Test formatting of new post changes."""
        engagement_delta = EngagementDelta(
            post_id="new123",
            score_delta=0,
            comments_delta=0,
            previous_score=0,
            current_score=100,
            previous_comments=0,
            current_comments=10,
            time_span_hours=0.5,
            engagement_rate=0.0
        )

        new_post = PostUpdate(
            post_id=1,
            reddit_post_id="new123",
            subreddit="test",
            title="Brand New Post",
            update_type="new",
            current_score=100,
            current_comments=10,
            current_timestamp=datetime.now(UTC),
            previous_score=None,
            previous_comments=None,
            previous_timestamp=None,
            engagement_delta=engagement_delta
        )

        formatted = format_post_changes(new_post)

        assert "🆕 **NEW**" in formatted
        assert "**Score:** 100 points" in formatted
        assert "**Comments:** 10" in formatted
        assert "Brand New Post" in formatted

    def test_format_post_changes_significant_increase(self):
        """Test formatting of posts with significant score increases."""
        engagement_delta = EngagementDelta(
            post_id="up123",
            score_delta=150,
            comments_delta=25,
            previous_score=50,
            current_score=200,
            previous_comments=5,
            current_comments=30,
            time_span_hours=3.0,
            engagement_rate=50.0
        )

        trending_post = PostUpdate(
            post_id=2,
            reddit_post_id="up123",
            subreddit="test",
            title="Viral Post Going Up",
            update_type="both_change",
            current_score=200,
            current_comments=30,
            current_timestamp=datetime.now(UTC),
            previous_score=50,
            previous_comments=5,
            previous_timestamp=datetime.now(UTC),
            engagement_delta=engagement_delta
        )

        formatted = format_post_changes(trending_post)

        assert "📈 **TRENDING UP**" in formatted
        assert "+150 points" in formatted
        assert "+25 comments" in formatted
        assert "Engagement rate: **50.0 points/hour**" in formatted

    def test_format_trend_summary(self):
        """Test trend summary formatting."""
        from datetime import datetime

        trend_data = TrendData(
            subreddit="technology",
            analysis_period_days=7,
            start_date=datetime.now(UTC),
            end_date=datetime.now(UTC),
            total_posts=100,
            total_comments=500,
            average_posts_per_day=15.5,
            average_comments_per_day=75.0,
            average_score=125.0,
            median_score=100.0,
            score_standard_deviation=50.0,
            engagement_trend=ActivityPattern.INCREASING,
            best_posting_hour=14,
            best_posting_day=1,
            peak_activity_periods=["14:00-16:00"],
            predicted_daily_posts=16.0,
            predicted_daily_engagement=1250.0,
            trend_confidence=0.85,
            change_from_previous_period=12.5,
            is_trending_up=True,
            is_trending_down=False
        )

        formatted = format_trend_summary(trend_data)

        assert "📊 **Trend Analysis** (7-day period)" in formatted
        assert "**Activity:** INCREASING 📈" in formatted
        assert "**Best posting time:** 2:00 PM" in formatted
        assert "**Average posts/day:** 15.5" in formatted
        assert "+12.5%" in formatted
        assert "**Predicted engagement:** 1,250.0 points/day" in formatted

    def test_format_comment_changes_placeholder(self):
        """Test comment changes formatting (placeholder for future implementation)."""
        # For now, this is a placeholder as the prompt mentions comment structure
        # is ready for future implementation
        comment_data = {
            "post_id": "test123",
            "new_comments": 5,
            "score_changes": 3,
            "total_comments": 25
        }

        formatted = format_comment_changes(comment_data)

        # Basic structure test
        assert isinstance(formatted, str)
        assert len(formatted) > 0


class TestEmptyDeltaHandling:
    """Tests for empty delta handling and markdown escaping."""

    def test_create_delta_report_no_changes(self):
        """Test delta report creation when no changes detected."""
        delta_data = ChangeDetectionResult(
            check_run_id=4,
            subreddit="quiet",
            detection_timestamp=datetime.now(UTC),
            new_posts=[],
            updated_posts=[],
            total_new_posts=0,
            total_updated_posts=0,
            posts_with_significant_changes=0,
            trending_up_posts=0,
            trending_down_posts=0
        )

        report = create_delta_report(delta_data, "quiet", "test topic")

        assert "# 🔍 Reddit Update Report: test topic in r/quiet" in report
        assert "🔍 **No new posts** discovered" in report
        assert "📊 **No significant changes** detected" in report
        assert "🤷 **No Updates Detected**" in report
        assert "All quiet on the r/quiet front!" in report

    def test_markdown_escaping_in_post_titles(self):
        """Test markdown character escaping in post titles."""
        engagement_delta = EngagementDelta(
            post_id="escape123",
            score_delta=0,
            comments_delta=0,
            previous_score=0,
            current_score=50,
            previous_comments=0,
            current_comments=5,
            time_span_hours=1.0,
            engagement_rate=0.0
        )

        post_with_markdown = PostUpdate(
            post_id=5,
            reddit_post_id="escape123",
            subreddit="test",
            title="Title with *asterisks* and **bold** and [links](url) and # hashtags",
            update_type="new",
            current_score=50,
            current_comments=5,
            current_timestamp=datetime.now(UTC),
            previous_score=None,
            previous_comments=None,
            previous_timestamp=None,
            engagement_delta=engagement_delta
        )

        formatted = format_post_changes(post_with_markdown)

        # Verify markdown characters are escaped
        assert "\\*asterisks\\*" in formatted
        assert "\\*\\*bold\\*\\*" in formatted
        assert "\\[links\\]\\(url\\)" in formatted
        assert "\\# hashtags" in formatted

    def test_empty_trend_data_handling(self):
        """Test handling of empty or minimal trend data."""
        from datetime import datetime

        empty_trend = TrendData(
            subreddit="empty",
            analysis_period_days=7,
            start_date=datetime.now(UTC),
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

        formatted = format_trend_summary(empty_trend)

        assert "**Activity:** DORMANT 😴" in formatted
        assert "**Average posts/day:** 0.0" in formatted
        assert "**Predicted engagement:** 0.0 points/day" in formatted

    def test_unicode_content_handling(self):
        """Test handling of unicode characters in post content."""
        engagement_delta = EngagementDelta(
            post_id="unicode123",
            score_delta=0,
            comments_delta=0,
            previous_score=0,
            current_score=25,
            previous_comments=0,
            current_comments=3,
            time_span_hours=1.0,
            engagement_rate=0.0
        )

        unicode_post = PostUpdate(
            post_id=6,
            reddit_post_id="unicode123",
            subreddit="test",
            title="Post with émojis 🚀 and unicóde çharacters",
            update_type="new",
            current_score=25,
            current_comments=3,
            current_timestamp=datetime.now(UTC),
            previous_score=None,
            previous_comments=None,
            previous_timestamp=None,
            engagement_delta=engagement_delta
        )

        formatted = format_post_changes(unicode_post)

        # Verify unicode content is preserved
        assert "émojis 🚀" in formatted
        assert "unicóde çharacters" in formatted

    def test_extreme_values_formatting(self):
        """Test formatting with extreme values (very large numbers)."""
        engagement_delta = EngagementDelta(
            post_id="extreme123",
            score_delta=999999,
            comments_delta=50000,
            previous_score=1000,
            current_score=1000999,
            previous_comments=100,
            current_comments=50100,
            time_span_hours=24.0,
            engagement_rate=41666.625
        )

        extreme_post = PostUpdate(
            post_id=7,
            reddit_post_id="extreme123",
            subreddit="test",
            title="Viral Post with Extreme Numbers",
            update_type="both_change",
            current_score=1000999,
            current_comments=50100,
            current_timestamp=datetime.now(UTC),
            previous_score=1000,
            previous_comments=100,
            previous_timestamp=datetime.now(UTC),
            engagement_delta=engagement_delta
        )

        formatted = format_post_changes(extreme_post)

        # Verify large numbers are formatted with commas
        assert "1,000,999 points" in formatted
        assert "+999,999 points" in formatted
        assert "+50,000 comments" in formatted
        assert "41,666.6 points/hour" in formatted


class TestMobileFriendlyOutput:
    """Tests for mobile-friendly output and responsive formatting."""

    def test_report_line_length_mobile_friendly(self):
        """Test that report lines are mobile-friendly length."""
        # Create a typical delta report
        engagement_delta = EngagementDelta(
            post_id="mobile123",
            score_delta=50,
            comments_delta=10,
            previous_score=100,
            current_score=150,
            previous_comments=5,
            current_comments=15,
            time_span_hours=2.0,
            engagement_rate=25.0
        )

        post = PostUpdate(
            post_id=8,
            reddit_post_id="mobile123",
            subreddit="test",
            title="A reasonably long post title that might wrap on mobile devices",
            update_type="both_change",
            current_score=150,
            current_comments=15,
            current_timestamp=datetime.now(UTC),
            previous_score=100,
            previous_comments=5,
            previous_timestamp=datetime.now(UTC),
            engagement_delta=engagement_delta
        )

        delta_data = ChangeDetectionResult(
            check_run_id=5,
            subreddit="test",
            detection_timestamp=datetime.now(UTC),
            new_posts=[],
            updated_posts=[post],
            total_new_posts=0,
            total_updated_posts=1,
            posts_with_significant_changes=1,
            trending_up_posts=1,
            trending_down_posts=0
        )

        report = create_delta_report(delta_data, "test", "mobile test")

        # Check that most lines are reasonable length for mobile
        lines = report.split('\n')
        long_lines = [line for line in lines if len(line) > 80]

        # Allow some long lines but not too many
        assert len(long_lines) / len(lines) < 0.3, "Too many long lines for mobile"

    def test_consistent_emoji_usage(self):
        """Test consistent emoji usage throughout the report."""
        # Test data setup similar to above
        delta_data = ChangeDetectionResult(
            check_run_id=6,
            subreddit="emoji_test",
            detection_timestamp=datetime.now(UTC),
            new_posts=[],
            updated_posts=[],
            total_new_posts=0,
            total_updated_posts=0,
            posts_with_significant_changes=0,
            trending_up_posts=0,
            trending_down_posts=0
        )

        report = create_delta_report(delta_data, "emoji_test", "emoji consistency")

        # Verify consistent emoji usage
        assert "🔍" in report  # Search/discovery emoji
        assert "📊" in report  # Statistics emoji
        assert "🤷" in report  # No changes emoji

    def test_section_hierarchy_clear(self):
        """Test that section hierarchy is clear and well-structured."""
        # Complex report with multiple sections
        engagement_delta = EngagementDelta(
            post_id="hierarchy123",
            score_delta=25,
            comments_delta=5,
            previous_score=75,
            current_score=100,
            previous_comments=10,
            current_comments=15,
            time_span_hours=1.0,
            engagement_rate=25.0
        )

        new_post = PostUpdate(
            post_id=9,
            reddit_post_id="new999",
            subreddit="test",
            title="New Post",
            update_type="new",
            current_score=50,
            current_comments=8,
            current_timestamp=datetime.now(UTC),
            previous_score=None,
            previous_comments=None,
            previous_timestamp=None,
            engagement_delta=None
        )

        updated_post = PostUpdate(
            post_id=10,
            reddit_post_id="hierarchy123",
            subreddit="test",
            title="Updated Post",
            update_type="both_change",
            current_score=100,
            current_comments=15,
            current_timestamp=datetime.now(UTC),
            previous_score=75,
            previous_comments=10,
            previous_timestamp=datetime.now(UTC),
            engagement_delta=engagement_delta
        )

        delta_data = ChangeDetectionResult(
            check_run_id=7,
            subreddit="test",
            detection_timestamp=datetime.now(UTC),
            new_posts=[new_post],
            updated_posts=[updated_post],
            total_new_posts=1,
            total_updated_posts=1,
            posts_with_significant_changes=1,
            trending_up_posts=1,
            trending_down_posts=0
        )

        report = create_delta_report(delta_data, "test", "hierarchy test")

        # Verify clear section hierarchy
        lines = report.split('\n')
        h1_lines = [line for line in lines if line.startswith('# ')]
        h2_lines = [line for line in lines if line.startswith('## ')]
        h3_lines = [line for line in lines if line.startswith('### ')]

        assert len(h1_lines) == 1, "Should have exactly one main heading"
        assert len(h2_lines) >= 2, "Should have multiple section headings"
        assert len(h3_lines) >= 2, "Should have multiple post headings"


# Error handling and edge cases
class TestErrorHandling:
    """Tests for error handling and edge cases."""

    def test_missing_engagement_delta(self):
        """Test handling of posts without engagement delta data."""
        post_no_delta = PostUpdate(
            post_id=11,
            reddit_post_id="nodelta123",
            subreddit="test",
            title="Post Without Delta",
            update_type="new",
            current_score=25,
            current_comments=3,
            current_timestamp=datetime.now(UTC),
            previous_score=None,
            previous_comments=None,
            previous_timestamp=None,
            engagement_delta=None
        )

        formatted = format_post_changes(post_no_delta)

        # Should handle gracefully without engagement rate
        assert "Post Without Delta" in formatted
        assert "**Score:** 25 points" in formatted
        assert "**Comments:** 3" in formatted
        # Should not crash on missing engagement_delta

    def test_create_delta_report_with_trend_data(self):
        """Test delta report creation with trend data inclusion."""
        delta_data = ChangeDetectionResult(
            check_run_id=8,
            subreddit="trending",
            detection_timestamp=datetime.now(UTC),
            new_posts=[],
            updated_posts=[],
            total_new_posts=0,
            total_updated_posts=0,
            posts_with_significant_changes=0,
            trending_up_posts=0,
            trending_down_posts=0
        )

        trend_data = TrendData(
            subreddit="trending",
            analysis_period_days=7,
            start_date=datetime.now(UTC),
            end_date=datetime.now(UTC),
            total_posts=85,
            total_comments=350,
            average_posts_per_day=12.3,
            average_comments_per_day=50.0,
            average_score=100.0,
            median_score=85.0,
            score_standard_deviation=45.0,
            engagement_trend=ActivityPattern.VOLATILE,
            best_posting_hour=16,
            best_posting_day=3,
            peak_activity_periods=["16:00-18:00"],
            predicted_daily_posts=11.5,
            predicted_daily_engagement=850.5,
            trend_confidence=0.75,
            change_from_previous_period=-5.2,
            is_trending_up=False,
            is_trending_down=True
        )

        # Test with trend data
        report = create_delta_report(delta_data, "trending", "trend analysis", trend_data)

        assert "📊 **Trend Analysis**" in report
        assert "**Activity:** VOLATILE" in report
        assert "-5.2%" in report
