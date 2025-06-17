# ABOUTME: Test suite for trend analysis functionality in ChangeDetectionService
# ABOUTME: Tests subreddit trend calculation, time window analysis, and activity patterns

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from app.models.types import ActivityPattern, TrendData
from app.services.change_detection_service import ChangeDetectionService
from app.services.storage_service import StorageService


class TestTrendAnalysis:
    """Test suite for trend analysis functionality."""

    @pytest.fixture
    def mock_storage_service(self):
        """Create a mock storage service for testing."""
        mock_storage = Mock(spec=StorageService)
        return mock_storage

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session for testing."""
        return Mock()

    @pytest.fixture
    def change_detection_service(self, mock_session, mock_storage_service):
        """Create a ChangeDetectionService instance with mocked dependencies."""
        return ChangeDetectionService(session=mock_session, storage_service=mock_storage_service)

    @pytest.fixture
    def sample_posts_data(self):
        """Create sample posts data for testing."""
        base_time = datetime.now(UTC)
        return [
            {
                'post_id': 'post1',
                'subreddit': 'technology',
                'score': 100,
                'num_comments': 20,
                'created_utc': base_time - timedelta(days=1),
                'title': 'Test Post 1',
                'author': 'user1'
            },
            {
                'post_id': 'post2',
                'subreddit': 'technology',
                'score': 250,
                'num_comments': 45,
                'created_utc': base_time - timedelta(days=2),
                'title': 'Test Post 2',
                'author': 'user2'
            },
            {
                'post_id': 'post3',
                'subreddit': 'technology',
                'score': 50,
                'num_comments': 10,
                'created_utc': base_time - timedelta(days=3),
                'title': 'Test Post 3',
                'author': 'user3'
            }
        ]

    def test_get_subreddit_trends_basic_calculation(self, change_detection_service, mock_storage_service):
        """Test basic subreddit trend calculation."""
        # Setup mock data
        base_time = datetime.now(UTC)
        mock_posts = [
            Mock(
                post_id='post1',
                score=100,
                num_comments=20,
                created_utc=base_time - timedelta(days=1),
                first_seen=base_time - timedelta(days=1)
            ),
            Mock(
                post_id='post2',
                score=200,
                num_comments=30,
                created_utc=base_time - timedelta(days=2),
                first_seen=base_time - timedelta(days=2)
            )
        ]

        mock_storage_service.get_posts_in_timeframe.return_value = mock_posts

        # Execute
        trend_data = change_detection_service.get_subreddit_trends('technology', 7)

        # Verify
        assert isinstance(trend_data, TrendData)
        assert trend_data.subreddit == 'technology'
        assert trend_data.analysis_period_days == 7
        assert trend_data.total_posts == 2
        assert trend_data.total_comments == 50
        assert trend_data.average_score == 150.0  # (100 + 200) / 2

    def test_get_subreddit_trends_empty_data(self, change_detection_service, mock_storage_service):
        """Test trend calculation with no data."""
        mock_storage_service.get_posts_in_timeframe.return_value = []

        trend_data = change_detection_service.get_subreddit_trends('technology', 7)

        assert isinstance(trend_data, TrendData)
        assert trend_data.total_posts == 0
        assert trend_data.total_comments == 0
        assert trend_data.average_posts_per_day == 0.0
        assert trend_data.engagement_trend == ActivityPattern.DORMANT

    def test_get_subreddit_trends_time_window_analysis(self, change_detection_service, mock_storage_service):
        """Test time window analysis with different periods."""
        base_time = datetime.now(UTC)

        # Mock data spanning multiple days
        mock_posts = []
        for i in range(14):  # 14 days of data
            mock_posts.append(Mock(
                post_id=f'post{i}',
                score=100 + i * 10,  # Increasing scores
                num_comments=10 + i * 2,
                created_utc=base_time - timedelta(days=i),
                first_seen=base_time - timedelta(days=i)
            ))

        mock_storage_service.get_posts_in_timeframe.return_value = mock_posts

        # Test 7-day window
        trend_data_7d = change_detection_service.get_subreddit_trends('technology', 7)
        assert trend_data_7d.analysis_period_days == 7
        assert trend_data_7d.average_posts_per_day == 14 / 7  # 2 posts per day

        # Test 14-day window
        trend_data_14d = change_detection_service.get_subreddit_trends('technology', 14)
        assert trend_data_14d.analysis_period_days == 14
        assert trend_data_14d.average_posts_per_day == 1.0  # 14 posts in 14 days

    def test_detect_activity_patterns_steady(self, change_detection_service, mock_storage_service):
        """Test detection of steady activity pattern."""
        base_time = datetime.now(UTC)

        # Create consistent daily activity
        mock_posts = []
        for day in range(7):
            for post_num in range(5):  # 5 posts per day
                mock_posts.append(Mock(
                    post_id=f'post{day}_{post_num}',
                    score=100,  # Consistent scores
                    num_comments=20,
                    created_utc=base_time - timedelta(days=day),
                    first_seen=base_time - timedelta(days=day)
                ))

        mock_storage_service.get_posts_in_timeframe.return_value = mock_posts

        pattern = change_detection_service.detect_activity_patterns('technology')
        assert pattern == ActivityPattern.STEADY

    def test_detect_activity_patterns_increasing(self, change_detection_service, mock_storage_service):
        """Test detection of increasing activity pattern."""
        base_time = datetime.now(UTC)

        # Create increasing activity over time
        mock_posts = []
        for day in range(7):
            posts_per_day = day + 1  # Increasing number of posts each day
            for post_num in range(posts_per_day):
                mock_posts.append(Mock(
                    post_id=f'post{day}_{post_num}',
                    score=100 + day * 20,  # Increasing scores
                    num_comments=20,
                    created_utc=base_time - timedelta(days=6-day),  # Reverse order for increasing
                    first_seen=base_time - timedelta(days=6-day)
                ))

        mock_storage_service.get_posts_in_timeframe.return_value = mock_posts

        pattern = change_detection_service.detect_activity_patterns('technology')
        assert pattern == ActivityPattern.INCREASING

    def test_detect_activity_patterns_volatile(self, change_detection_service, mock_storage_service):
        """Test detection of volatile activity pattern."""
        base_time = datetime.now(UTC)

        # Create volatile activity (high variance)
        post_counts = [1, 20, 2, 25, 3, 22, 1]  # High variance in daily posts
        mock_posts = []
        for day, count in enumerate(post_counts):
            for post_num in range(count):
                mock_posts.append(Mock(
                    post_id=f'post{day}_{post_num}',
                    score=100,
                    num_comments=20,
                    created_utc=base_time - timedelta(days=day),
                    first_seen=base_time - timedelta(days=day)
                ))

        mock_storage_service.get_posts_in_timeframe.return_value = mock_posts

        pattern = change_detection_service.detect_activity_patterns('technology')
        assert pattern == ActivityPattern.VOLATILE

    def test_calculate_best_post_time_hour_analysis(self, change_detection_service, mock_storage_service):
        """Test calculation of best posting hour."""
        base_time = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

        # Create posts with different hours, hour 14 (2 PM) has highest scores
        mock_posts = []
        for hour in range(24):
            score = 200 if hour == 14 else 100  # Higher score at 2 PM
            mock_posts.append(Mock(
                post_id=f'post_hour_{hour}',
                score=score,
                num_comments=20,
                created_utc=base_time.replace(hour=hour),
                first_seen=base_time.replace(hour=hour)
            ))

        mock_storage_service.get_posts_in_timeframe.return_value = mock_posts

        best_hour = change_detection_service.calculate_best_post_time('technology')
        assert best_hour == 14

    def test_calculate_best_post_time_empty_data(self, change_detection_service, mock_storage_service):
        """Test best post time calculation with no data."""
        mock_storage_service.get_posts_in_timeframe.return_value = []

        best_hour = change_detection_service.calculate_best_post_time('technology')
        assert best_hour == 12  # Default to noon

    def test_get_engagement_forecast_basic(self, change_detection_service, mock_storage_service):
        """Test basic engagement forecasting."""
        base_time = datetime.now(UTC)

        # Create trend data: increasing activity
        mock_posts = []
        for day in range(14):
            posts_count = 5 + day  # Increasing from 5 to 18 posts per day
            for post_num in range(posts_count):
                mock_posts.append(Mock(
                    post_id=f'post{day}_{post_num}',
                    score=100 + day * 5,  # Increasing scores
                    num_comments=20,
                    created_utc=base_time - timedelta(days=13-day),
                    first_seen=base_time - timedelta(days=13-day)
                ))

        mock_storage_service.get_posts_in_timeframe.return_value = mock_posts

        forecast = change_detection_service.get_engagement_forecast('technology')

        assert 'predicted_daily_posts' in forecast
        assert 'predicted_daily_engagement' in forecast
        assert 'trend_confidence' in forecast
        assert forecast['predicted_daily_posts'] > 18  # Should predict higher than current
        assert 0.0 <= forecast['trend_confidence'] <= 1.0

    def test_trend_data_serialization(self, change_detection_service, mock_storage_service):
        """Test that TrendData can be properly serialized."""
        base_time = datetime.now(UTC)
        mock_posts = [
            Mock(
                post_id='post1',
                score=100,
                num_comments=20,
                created_utc=base_time - timedelta(days=1),
                first_seen=base_time - timedelta(days=1)
            )
        ]

        mock_storage_service.get_posts_in_timeframe.return_value = mock_posts

        trend_data = change_detection_service.get_subreddit_trends('technology', 7)

        # Test that TrendData properties work
        assert trend_data.posts_per_hour >= 0
        assert trend_data.comments_per_post >= 0
        assert trend_data.activity_intensity in ['very_low', 'low', 'moderate', 'high', 'very_high']

        # Test that datetime fields are timezone-aware
        assert trend_data.start_date.tzinfo is not None
        assert trend_data.end_date.tzinfo is not None

    def test_trend_data_activity_intensity_classification(self, change_detection_service, mock_storage_service):
        """Test activity intensity classification."""
        test_cases = [
            (150, 'very_high'),  # >= 100 posts per day
            (75, 'high'),        # >= 50 posts per day
            (35, 'moderate'),    # >= 20 posts per day
            (10, 'low'),         # >= 5 posts per day
            (2, 'very_low')      # < 5 posts per day
        ]

        for posts_per_day, expected_intensity in test_cases:
            base_time = datetime.now(UTC)
            mock_posts = []

            # Create the specified number of posts
            for i in range(int(posts_per_day * 7)):  # 7 days worth
                mock_posts.append(Mock(
                    post_id=f'post{i}',
                    score=100,
                    num_comments=20,
                    created_utc=base_time - timedelta(days=i // posts_per_day),
                    first_seen=base_time - timedelta(days=i // posts_per_day)
                ))

            mock_storage_service.get_posts_in_timeframe.return_value = mock_posts

            trend_data = change_detection_service.get_subreddit_trends('technology', 7)
            assert trend_data.activity_intensity == expected_intensity

    def test_error_handling_database_failure(self, change_detection_service, mock_storage_service):
        """Test error handling when database operations fail."""
        # Mock database failure
        mock_storage_service.get_posts_in_timeframe.side_effect = Exception("Database connection failed")

        # Should handle gracefully and return default/empty trend data
        trend_data = change_detection_service.get_subreddit_trends('technology', 7)

        assert isinstance(trend_data, TrendData)
        assert trend_data.total_posts == 0
        assert trend_data.engagement_trend == ActivityPattern.DORMANT

    def test_performance_with_large_dataset(self, change_detection_service, mock_storage_service):
        """Test performance with large number of posts."""
        base_time = datetime.now(UTC)

        # Create large dataset (1000 posts)
        mock_posts = []
        for i in range(1000):
            mock_posts.append(Mock(
                post_id=f'post{i}',
                score=100 + i % 500,  # Varying scores
                num_comments=20 + i % 100,
                created_utc=base_time - timedelta(days=i % 30),
                first_seen=base_time - timedelta(days=i % 30)
            ))

        mock_storage_service.get_posts_in_timeframe.return_value = mock_posts

        # Should complete without timeout or memory issues
        trend_data = change_detection_service.get_subreddit_trends('technology', 30)

        assert trend_data.total_posts == 1000
        assert trend_data.average_posts_per_day > 0

    def test_statistical_accuracy(self, change_detection_service, mock_storage_service):
        """Test statistical accuracy of trend calculations."""
        base_time = datetime.now(UTC)

        # Create known dataset for statistical verification
        scores = [100, 200, 150, 300, 250]  # Known values
        mock_posts = []

        for i, score in enumerate(scores):
            mock_posts.append(Mock(
                post_id=f'post{i}',
                score=score,
                num_comments=20,
                created_utc=base_time - timedelta(days=i),
                first_seen=base_time - timedelta(days=i)
            ))

        mock_storage_service.get_posts_in_timeframe.return_value = mock_posts

        trend_data = change_detection_service.get_subreddit_trends('technology', 5)

        # Verify statistical calculations
        expected_average = sum(scores) / len(scores)  # 200.0
        assert abs(trend_data.average_score - expected_average) < 0.1

        # Verify median calculation
        sorted_scores = sorted(scores)
        expected_median = sorted_scores[len(sorted_scores) // 2]  # 200
        assert abs(trend_data.median_score - expected_median) < 0.1
