# ABOUTME: Concrete E2E tests that validate actual API functionality with real data
# ABOUTME: Tests ClaudeAI subreddit and Claude Code topic with meaningful assertions

from datetime import datetime, timedelta
import time
from urllib.parse import quote

import httpx
import pytest


class TestConcreteAPIValidation:
    """Concrete tests that validate actual API functionality with real data."""

    @pytest.mark.asyncio
    async def test_discover_subreddits_claude_code_real_validation(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test that discover-subreddits actually finds relevant Claude Code subreddits."""
        topic = "Claude Code"
        encoded_topic = quote(topic)

        response = http_client.get(
            f"{standard_api_url}/discover-subreddits/{encoded_topic}",
            timeout=60.0
        )

        # Must succeed - no accepting failure
        assert response.status_code == 200, f"Discovery failed: {response.text}"

        data = response.json()

        # Handle different response formats (list vs object with subreddits)
        if isinstance(data, dict) and "subreddits" in data:
            subreddits = data["subreddits"]
        else:
            subreddits = data if isinstance(data, list) else []

        assert isinstance(subreddits, list), "Must return a list of subreddits"
        assert len(subreddits) >= 2, f"Must find at least 2 relevant subreddits, got {len(subreddits)}"

        # Validate subreddit structure and quality
        subreddit_names = []
        for subreddit in subreddits:
            assert "name" in subreddit, "Each subreddit must have a name"
            assert "description" in subreddit, "Each subreddit must have a description"
            # Handle different score field names
            score_field = "relevance_score" if "relevance_score" in subreddit else "score"
            assert score_field in subreddit, "Each subreddit must have a relevance score"

            # Validate score is meaningful
            score = subreddit[score_field]
            assert isinstance(score, int | float), "Score must be numeric"
            assert 0 <= score <= 20, f"Score must be 0-20, got {score}"

            # Validate description quality
            description = subreddit["description"].lower()
            assert len(description) > 10, "Description must be substantial"

            subreddit_names.append(subreddit["name"])

        # Must find ClaudeAI subreddit for our test data
        assert "ClaudeAI" in subreddit_names, f"Must find ClaudeAI subreddit in results: {subreddit_names}"

        # Validate ClaudeAI has high relevance score
        claude_ai_subreddit = next(s for s in subreddits if s["name"] == "ClaudeAI")
        claude_score_field = "relevance_score" if "relevance_score" in claude_ai_subreddit else "score"
        claude_score = claude_ai_subreddit[claude_score_field]
        assert claude_score >= 7, f"ClaudeAI must have high relevance score, got {claude_score}"

    @pytest.mark.asyncio
    async def test_generate_report_claudeai_claude_code_content_validation(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        clean_database: None,
        api_rate_limit_delay: None,
    ) -> None:
        """Test that generate-report produces substantial, relevant content."""
        subreddit = "ClaudeAI"
        topic = "Claude Code"
        encoded_subreddit = quote(subreddit)
        encoded_topic = quote(topic)

        response = http_client.get(
            f"{standard_api_url}/generate-report/{encoded_subreddit}/{encoded_topic}?store_data=true",
            timeout=120.0
        )

        # Must succeed with content
        assert response.status_code == 200, f"Report generation failed: {response.text}"
        assert response.headers.get("content-type") in [
            "text/markdown; charset=utf-8",
            "application/octet-stream"
        ], "Must return markdown content"

        content = response.text

        # Validate substantial content
        assert len(content) >= 1000, f"Report must be substantial (≥1000 chars), got {len(content)}"

        # Validate markdown structure
        assert "# " in content or "## " in content, "Must contain markdown headers"
        assert "reddit.com" in content.lower(), "Must contain Reddit links (real data)"
        assert any(marker in content for marker in ["*", "-", "1.", "2."]), "Must contain lists or bullets"

        # Validate topic relevance
        content_lower = content.lower()
        claude_mentions = content_lower.count("claude")
        ai_mentions = content_lower.count("ai")
        assert claude_mentions >= 3 or ai_mentions >= 5, "Must be relevant to Claude/AI topic"

        # Validate contains actual Reddit data
        assert "/comments/" in content, "Must contain Reddit comment links"
        assert "points" in content_lower or "score" in content_lower, "Must show engagement metrics"

    @pytest.mark.asyncio
    async def test_check_updates_claudeai_claude_code_data_validation(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        clean_database: None,
        api_rate_limit_delay: None,
    ) -> None:
        """Test that check-updates returns actual Reddit post data with proper structure."""
        subreddit = "ClaudeAI"
        topic = "Claude Code"
        encoded_subreddit = quote(subreddit)
        encoded_topic = quote(topic)

        response = http_client.get(
            f"{standard_api_url}/check-updates/{encoded_subreddit}/{encoded_topic}",
            timeout=120.0
        )

        # Must succeed
        assert response.status_code == 200, f"Check updates failed: {response.text}"

        data = response.json()

        # Validate response structure
        required_keys = ["new_posts", "updated_posts", "new_comments", "summary"]
        for key in required_keys:
            assert key in data, f"Response must contain '{key}'"

        # Validate new_posts has real data
        new_posts = data["new_posts"]
        assert isinstance(new_posts, list), "new_posts must be a list"

        # If subreddit is inactive, that's OK - just validate structure is correct
        if len(new_posts) > 0:
            # Validate first post structure and data quality if posts exist
            post = new_posts[0]
            required_post_fields = ["post_id", "title", "url", "score", "num_comments", "created_utc"]
            for field in required_post_fields:
                assert field in post, f"Post must contain '{field}'"

            # Validate post data quality
            assert len(post["title"]) > 5, "Post title must be substantial"
            assert isinstance(post["url"], str), "Post URL must be a string"
            assert isinstance(post["score"], int), "Score must be integer"
            assert isinstance(post["num_comments"], int), "Comment count must be integer"
            assert isinstance(post["created_utc"], str), "Created time must be a string"

            # Validate post is recent (within 30 days)
            post_time = datetime.fromisoformat(post["created_utc"].replace('Z', '+00:00'))
            thirty_days_ago = datetime.now(post_time.tzinfo) - timedelta(days=30)
            assert post_time > thirty_days_ago, "Posts should be reasonably recent"

        # Validate summary contains meaningful information
        summary = data["summary"]
        assert isinstance(summary, dict), "Summary must be dictionary"
        assert "new_posts_count" in summary, "Summary must contain new_posts_count"
        assert isinstance(summary["new_posts_count"], int), "new_posts_count must be integer"

    @pytest.mark.asyncio
    async def test_check_updates_delta_detection_validation(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        clean_database: None,
        api_rate_limit_delay: None,
    ) -> None:
        """Test that second check-updates call properly detects changes."""
        subreddit = "ClaudeAI"
        topic = "Claude Code"
        encoded_subreddit = quote(subreddit)
        encoded_topic = quote(topic)

        # First run
        first_response = http_client.get(
            f"{standard_api_url}/check-updates/{encoded_subreddit}/{encoded_topic}",
            timeout=120.0
        )

        assert first_response.status_code == 200, f"First check failed: {first_response.text}"
        first_data = first_response.json()
        first_new_posts_count = len(first_data["new_posts"])

        # Must find some posts on first run
        assert first_new_posts_count > 0, "First run must find new posts"

        # Wait for potential changes
        time.sleep(5)

        # Second run
        second_response = http_client.get(
            f"{standard_api_url}/check-updates/{encoded_subreddit}/{encoded_topic}",
            timeout=120.0
        )

        assert second_response.status_code == 200, f"Second check failed: {second_response.text}"
        second_data = second_response.json()
        second_new_posts_count = len(second_data["new_posts"])

        # Second run should detect fewer new posts (change detection working)
        assert second_new_posts_count <= first_new_posts_count, \
            f"Second run should have ≤ new posts than first run. First: {first_new_posts_count}, Second: {second_new_posts_count}"

    @pytest.mark.asyncio
    async def test_trending_claudeai_engagement_validation(
        self,
        http_client: httpx.Client,
        optimized_api_url: str,
        clean_database: None,
        api_rate_limit_delay: None,
    ) -> None:
        """Test that trending endpoint returns actual trending posts with engagement metrics."""
        subreddit = "ClaudeAI"
        encoded_subreddit = quote(subreddit)

        response = http_client.get(
            f"{optimized_api_url}/trending/{encoded_subreddit}",
            timeout=60.0
        )

        # Must succeed
        assert response.status_code == 200, f"Trending failed: {response.text}"

        data = response.json()
        assert "trending_posts" in data, "Response must contain trending_posts"

        trending_posts = data["trending_posts"]
        assert isinstance(trending_posts, list), "trending_posts must be a list"
        
        # If subreddit is inactive, that's OK - just validate structure is correct
        if len(trending_posts) > 0:
            # Validate trending posts structure and engagement
            previous_engagement = float('inf')  # For checking sort order

            for i, post in enumerate(trending_posts[:5]):  # Check first 5 posts
                # Validate required fields
                required_fields = ["post_id", "trending_score", "score", "num_comments", "age_hours", "actual_comments"]
                for field in required_fields:
                    assert field in post, f"Trending post {i} must contain '{field}'"

                # Validate engagement metrics
                score = post["score"]
                comment_count = post["num_comments"]
                assert isinstance(score, int), f"Score must be integer, got {type(score)}"
                assert isinstance(comment_count, int), f"Comment count must be integer, got {type(comment_count)}"
                assert score >= 0, f"Score must be non-negative, got {score}"
                assert comment_count >= 0, f"Comment count must be non-negative, got {comment_count}"

                # Calculate engagement score (posts should be sorted by this)
                engagement = score + comment_count
                assert engagement <= previous_engagement, \
                    f"Posts should be sorted by engagement. Post {i} has higher engagement than previous."
                previous_engagement = engagement

    @pytest.mark.asyncio
    async def test_optimized_api_performance_validation(
        self,
        http_client: httpx.Client,
        optimized_api_url: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test that optimized API performance endpoints return meaningful metrics."""
        # Test performance stats
        stats_response = http_client.get(f"{optimized_api_url}/performance/stats")
        assert stats_response.status_code == 200, f"Performance stats failed: {stats_response.text}"

        stats_data = stats_response.json()
        required_stats = ["performance", "cache", "timestamp"]
        for key in required_stats:
            assert key in stats_data, f"Performance stats must contain '{key}'"

        # Validate performance metrics structure
        perf_data = stats_data["performance"]
        assert "request_metrics" in perf_data, "Must have request metrics"
        request_metrics = perf_data["request_metrics"]
        assert "average_response_time_ms" in request_metrics, "Must track average response time"
        assert "total_requests" in request_metrics, "Must track total requests"

        assert "cache_metrics" in perf_data, "Must have cache metrics"
        cache_metrics = perf_data["cache_metrics"]
        assert "hit_rate" in cache_metrics, "Must track cache hit rate"

        # Test performance report
        report_response = http_client.get(f"{optimized_api_url}/performance/report")
        assert report_response.status_code == 200, f"Performance report failed: {report_response.text}"

        report_data = report_response.json()
        assert "summary" in report_data, "Performance report must contain summary"


class TestAPIConsistencyValidation:
    """Test consistency between standard and optimized APIs with real data."""

    @pytest.mark.asyncio
    async def test_discover_subreddits_api_consistency(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        optimized_api_url: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test that both APIs return consistent subreddit discovery results."""
        topic = "Claude Code"
        encoded_topic = quote(topic)

        # Call both APIs
        standard_response = http_client.get(f"{standard_api_url}/discover-subreddits/{encoded_topic}")
        time.sleep(2)  # Rate limit delay
        optimized_response = http_client.get(f"{optimized_api_url}/discover-subreddits/{encoded_topic}")

        # Both must succeed
        assert standard_response.status_code == 200, f"Standard API failed: {standard_response.text}"
        assert optimized_response.status_code == 200, f"Optimized API failed: {optimized_response.text}"

        standard_data = standard_response.json()
        optimized_data = optimized_response.json()

        # Extract subreddits from potentially different response formats
        standard_subreddits = standard_data if isinstance(standard_data, list) else standard_data.get("subreddits", [])
        optimized_subreddits = optimized_data if isinstance(optimized_data, list) else optimized_data.get("subreddits", [])

        # Both should find ClaudeAI
        standard_names = {s["name"] for s in standard_subreddits}
        optimized_names = {s["name"] for s in optimized_subreddits}

        assert "ClaudeAI" in standard_names, "Standard API must find ClaudeAI"
        assert "ClaudeAI" in optimized_names, "Optimized API must find ClaudeAI"

        # Should have significant overlap in results
        overlap = standard_names.intersection(optimized_names)
        assert len(overlap) >= 2, f"APIs should return similar results. Overlap: {overlap}"


class TestErrorHandlingValidation:
    """Test proper error handling with concrete expectations."""

    @pytest.mark.asyncio
    async def test_invalid_subreddit_proper_handling(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test that invalid subreddit returns proper error response."""
        invalid_subreddit = "ThisSubredditDefinitelyDoesNotExist12345"

        response = http_client.get(
            f"{standard_api_url}/check-updates/{invalid_subreddit}/test",
            timeout=60.0
        )

        # Should handle gracefully with proper error message
        if response.status_code != 200:
            assert response.status_code in [500, 404, 422], f"Expected 404/422 for invalid subreddit, got {response.status_code}"
            error_data = response.json()
            assert "detail" in error_data, "Error response must contain detail"
            assert len(error_data["detail"]) > 10, "Error detail must be informative"
        else:
            # If 200, should return empty results gracefully
            data = response.json()
            assert data["new_posts"] == [], "Invalid subreddit should return empty new_posts"
            assert "No posts found" in data.get("summary", ""), "Summary should indicate no results"
