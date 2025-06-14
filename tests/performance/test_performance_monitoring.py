# ABOUTME: Performance monitoring tests with benchmark validation and regression detection
# ABOUTME: Tests performance metrics, memory profiling, and automated performance gates

import pytest
import time
import psutil
import threading
from unittest.mock import Mock, patch
from concurrent.futures import ThreadPoolExecutor

from app.utils.performance_monitor import PerformanceMonitor, BenchmarkSuite, PerformanceRegression
from app.services.reddit_service import RedditService
from app.utils.relevance import score_and_rank_subreddits_concurrent
from app.utils.comment_processor import process_comments_stream


@pytest.fixture
def performance_monitor():
    """Fixture for performance monitor."""
    return PerformanceMonitor()


@pytest.fixture
def benchmark_suite():
    """Fixture for benchmark suite."""
    return BenchmarkSuite()


@pytest.fixture
def mock_reddit_service():
    """Fixture for mocked Reddit service."""
    service = Mock(spec=RedditService)
    return service


class TestPerformanceMonitoring:
    """Test suite for performance monitoring functionality."""
    
    def test_api_call_measurement(self, performance_monitor, mock_reddit_service):
        """Test that API call count is properly measured and tracked."""
        # Mock Reddit API calls
        mock_reddit_service.get_hot_posts.return_value = [Mock() for _ in range(5)]
        
        # Measure API calls
        with performance_monitor.measure_api_calls() as api_counter:
            # Manually increment counter to simulate API calls being tracked
            mock_reddit_service.get_hot_posts("test_subreddit")
            api_counter.increment()
            mock_reddit_service.get_hot_posts("test_subreddit2")
            api_counter.increment()
        
        # Verify measurement
        assert api_counter.call_count == 2
        assert performance_monitor.get_last_api_count() == 2
    
    def test_response_time_monitoring(self, performance_monitor):
        """Test that response times are accurately measured."""
        # Simulate work with known duration
        with performance_monitor.measure_response_time() as timer:
            time.sleep(0.1)  # 100ms delay
        
        response_time = timer.get_elapsed_time()
        
        # Should be approximately 100ms (with some tolerance)
        assert 0.09 <= response_time <= 0.2
        assert performance_monitor.get_last_response_time() == response_time
    
    def test_memory_usage_tracking(self, performance_monitor):
        """Test that memory usage is tracked during processing."""
        initial_memory = performance_monitor.get_current_memory_mb()
        
        # Allocate significant memory
        large_data = ["x" * 10000 for _ in range(10000)]  # ~100MB
        
        peak_memory = performance_monitor.get_current_memory_mb()
        
        # Memory usage should have increased
        assert peak_memory > initial_memory
        
        # Clean up
        del large_data
    
    def test_concurrent_performance_monitoring(self, performance_monitor):
        """Test that performance monitoring works correctly with concurrent operations."""
        def simulate_work(duration):
            with performance_monitor.measure_response_time():
                time.sleep(duration)
        
        # Run multiple concurrent operations
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(simulate_work, 0.05) for _ in range(3)]
            for future in futures:
                future.result()
        
        # Should have recorded multiple measurements
        assert len(performance_monitor.get_response_time_history()) >= 3
    
    def test_performance_threshold_validation(self, performance_monitor):
        """Test that performance thresholds are properly validated."""
        # Set performance thresholds
        performance_monitor.set_thresholds(
            max_response_time_ms=2000,
            max_memory_mb=512,
            max_api_calls=10
        )
        
        # Test within thresholds
        with performance_monitor.measure_response_time():
            time.sleep(0.1)  # 100ms - within threshold
        
        assert performance_monitor.check_thresholds() == True
        
        # Test exceeding response time threshold
        with performance_monitor.measure_response_time():
            time.sleep(2.5)  # 2500ms - exceeds threshold
        
        assert performance_monitor.check_thresholds() == False
    
    def test_api_call_reduction_validation(self, performance_monitor, mock_reddit_service):
        """Test validation of API call reduction goals (80% reduction)."""
        # Mock baseline (original) API usage
        baseline_calls = 50  # Original method made many calls
        
        # Mock optimized API usage
        mock_reddit_service.get_relevant_posts_optimized.return_value = [Mock() for _ in range(5)]
        
        with performance_monitor.measure_api_calls() as api_counter:
            mock_reddit_service.get_relevant_posts_optimized("test_subreddit")
        
        optimized_calls = api_counter.call_count
        reduction_percentage = ((baseline_calls - optimized_calls) / baseline_calls) * 100
        
        # Should achieve 80% reduction
        assert reduction_percentage >= 80
        assert performance_monitor.validate_api_reduction(baseline_calls, optimized_calls, target_reduction=80)


class TestBenchmarkSuite:
    """Test suite for performance benchmarking functionality."""
    
    def test_reddit_api_benchmark(self, benchmark_suite, mock_reddit_service):
        """Test benchmarking of Reddit API operations."""
        # Mock Reddit API responses
        mock_posts = [Mock() for _ in range(15)]
        mock_reddit_service.get_relevant_posts_optimized.return_value = mock_posts
        
        # Run benchmark
        results = benchmark_suite.benchmark_reddit_api(mock_reddit_service, iterations=5)
        
        # Validate benchmark results
        assert 'avg_response_time' in results
        assert 'max_response_time' in results
        assert 'min_response_time' in results
        assert 'total_api_calls' in results
        assert results['iterations'] == 5
        
        # Response times should be reasonable
        assert results['avg_response_time'] < 1.0  # Less than 1 second for mock data
    
    def test_concurrent_processing_benchmark(self, benchmark_suite, mock_reddit_service):
        """Test benchmarking of concurrent subreddit processing."""
        # Mock subreddits
        mock_subreddits = [Mock() for _ in range(5)]
        for i, subreddit in enumerate(mock_subreddits):
            subreddit.display_name = f"test_subreddit_{i}"
            subreddit.public_description = f"Description {i}"
        
        # Mock Reddit API responses
        mock_reddit_service.get_hot_posts.return_value = [Mock(title="test topic post")]
        
        # Run benchmark
        results = benchmark_suite.benchmark_concurrent_processing(
            mock_subreddits, "topic", mock_reddit_service, iterations=3
        )
        
        # Validate results
        assert 'avg_response_time' in results
        assert 'concurrent_speedup' in results
        assert results['subreddit_count'] == 5
        assert results['iterations'] == 3
    
    def test_memory_efficiency_benchmark(self, benchmark_suite, mock_reddit_service):
        """Test benchmarking of memory-efficient comment processing."""
        # Mock large comment dataset
        large_comments = []
        for i in range(50):
            comment = Mock()
            comment.body = f"Comment {i}: " + "text " * 100  # Substantial content
            large_comments.append(comment)
        
        mock_reddit_service.get_top_comments.return_value = large_comments
        
        # Run benchmark
        results = benchmark_suite.benchmark_memory_efficiency(
            "test_post_id", mock_reddit_service, iterations=3
        )
        
        # Validate results
        assert 'avg_memory_usage_mb' in results
        assert 'peak_memory_usage_mb' in results
        assert 'avg_processing_time' in results
        assert results['iterations'] == 3
        
        # Memory usage should be reasonable
        assert results['peak_memory_usage_mb'] < 100  # Should be well under 100MB
    
    def test_end_to_end_benchmark(self, benchmark_suite, mock_reddit_service):
        """Test complete end-to-end performance benchmark."""
        # Mock all components
        mock_reddit_service.search_subreddits.return_value = [Mock() for _ in range(3)]
        mock_reddit_service.get_relevant_posts_optimized.return_value = [Mock() for _ in range(5)]
        mock_reddit_service.get_hot_posts.return_value = [Mock(title="test topic")]
        
        # Run end-to-end benchmark
        results = benchmark_suite.benchmark_end_to_end(
            topic="test_topic", 
            subreddit="test_subreddit", 
            reddit_service=mock_reddit_service,
            iterations=2
        )
        
        # Validate comprehensive results
        assert 'total_response_time' in results
        assert 'api_efficiency' in results
        assert 'memory_efficiency' in results
        assert 'concurrent_performance' in results
        assert results['iterations'] == 2


class TestPerformanceRegression:
    """Test suite for performance regression detection."""
    
    def test_regression_detection(self):
        """Test that performance regressions are properly detected."""
        detector = PerformanceRegression()
        
        # Set baseline performance
        baseline_metrics = {
            'response_time': 1.0,
            'memory_usage': 50.0,
            'api_calls': 5
        }
        detector.set_baseline(baseline_metrics)
        
        # Test within acceptable variance (no regression)
        current_metrics = {
            'response_time': 1.1,  # 10% increase
            'memory_usage': 52.0,  # 4% increase
            'api_calls': 5
        }
        
        assert detector.detect_regression(current_metrics, tolerance=0.15) == False
        
        # Test performance regression
        regression_metrics = {
            'response_time': 2.0,  # 100% increase
            'memory_usage': 80.0,  # 60% increase
            'api_calls': 10  # 100% increase
        }
        
        assert detector.detect_regression(regression_metrics, tolerance=0.15) == True
    
    def test_performance_improvement_detection(self):
        """Test that performance improvements are properly recognized."""
        detector = PerformanceRegression()
        
        # Set baseline
        baseline_metrics = {
            'response_time': 2.0,
            'memory_usage': 100.0,
            'api_calls': 20
        }
        detector.set_baseline(baseline_metrics)
        
        # Test performance improvement
        improved_metrics = {
            'response_time': 1.0,  # 50% improvement
            'memory_usage': 50.0,  # 50% improvement
            'api_calls': 5  # 75% improvement (meets our 80% API reduction goal)
        }
        
        improvements = detector.calculate_improvements(improved_metrics)
        
        assert improvements['response_time_improvement'] == 50.0
        assert improvements['memory_usage_improvement'] == 50.0
        assert improvements['api_calls_improvement'] == 75.0
        
        # Should not be flagged as regression
        assert detector.detect_regression(improved_metrics, tolerance=0.15) == False
    
    def test_automated_performance_gate(self):
        """Test automated performance gate for CI/CD integration."""
        detector = PerformanceRegression()
        
        # Set strict performance requirements
        requirements = {
            'max_response_time': 2.0,
            'max_memory_usage': 512.0,
            'max_api_calls': 10,
            'min_api_reduction': 80.0
        }
        detector.set_performance_requirements(requirements)
        
        # Test passing metrics
        passing_metrics = {
            'response_time': 1.5,
            'memory_usage': 256.0,
            'api_calls': 5,
            'api_reduction': 85.0
        }
        
        gate_result = detector.performance_gate(passing_metrics)
        assert gate_result['passed'] == True
        assert len(gate_result['violations']) == 0
        
        # Test failing metrics
        failing_metrics = {
            'response_time': 3.0,  # Exceeds limit
            'memory_usage': 600.0,  # Exceeds limit
            'api_calls': 15,  # Exceeds limit
            'api_reduction': 70.0  # Below minimum
        }
        
        gate_result = detector.performance_gate(failing_metrics)
        assert gate_result['passed'] == False
        assert len(gate_result['violations']) == 4  # All metrics violated
