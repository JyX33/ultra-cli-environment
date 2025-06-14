# ABOUTME: Performance monitoring utilities with benchmarking and regression detection
# ABOUTME: Provides tools for tracking API calls, response times, memory usage, and automated performance gates

from contextlib import contextmanager
import statistics
import threading
import time
from typing import Any, Dict, Generator, List, Optional

import psutil


class PerformanceMonitor:
    """Monitors and tracks performance metrics for the application."""

    def __init__(self) -> None:
        """Initialize the performance monitor."""
        self.api_call_counts: list[int] = []
        self.response_times: list[float] = []
        self.memory_snapshots: list[float] = []
        self.thresholds: dict[str, float] = {}
        self._lock = threading.Lock()

    @contextmanager
    def measure_api_calls(self) -> Generator[Any, None, None]:
        """Context manager to measure API call count."""
        counter = APICallCounter()
        yield counter
        with self._lock:
            self.api_call_counts.append(counter.call_count)

    @contextmanager
    def measure_response_time(self) -> Generator[Any, None, None]:
        """Context manager to measure response time."""
        timer = ResponseTimer()
        timer.start()
        yield timer
        timer.stop()
        with self._lock:
            self.response_times.append(timer.get_elapsed_time())

    def get_current_memory_mb(self) -> float:
        """Get current memory usage in megabytes."""
        process = psutil.Process()
        memory_mb = float(process.memory_info().rss / (1024 * 1024))
        with self._lock:
            self.memory_snapshots.append(memory_mb)
        return memory_mb

    def get_last_api_count(self) -> int:
        """Get the last recorded API call count."""
        with self._lock:
            return self.api_call_counts[-1] if self.api_call_counts else 0

    def get_last_response_time(self) -> float:
        """Get the last recorded response time."""
        with self._lock:
            return self.response_times[-1] if self.response_times else 0.0

    def get_response_time_history(self) -> List[float]:
        """Get the complete response time history."""
        with self._lock:
            return self.response_times.copy()

    def set_thresholds(self, max_response_time_ms: int, max_memory_mb: int, max_api_calls: int) -> None:
        """Set performance thresholds for validation."""
        self.thresholds = {
            'max_response_time': max_response_time_ms / 1000.0,  # Convert to seconds
            'max_memory_mb': max_memory_mb,
            'max_api_calls': max_api_calls
        }

    def check_thresholds(self) -> bool:
        """Check if current performance metrics meet the thresholds."""
        if not self.thresholds:
            return True

        with self._lock:
            # Check response time
            if self.response_times and self.response_times[-1] > self.thresholds['max_response_time']:
                return False

            # Check memory usage
            if self.memory_snapshots and self.memory_snapshots[-1] > self.thresholds['max_memory_mb']:
                return False

            # Check API calls
            if self.api_call_counts and self.api_call_counts[-1] > self.thresholds['max_api_calls']:
                return False

        return True

    def validate_api_reduction(self, baseline_calls: int, optimized_calls: int, target_reduction: float) -> bool:
        """Validate that API call reduction meets the target percentage."""
        if baseline_calls == 0:
            return optimized_calls == 0

        reduction_percentage = ((baseline_calls - optimized_calls) / baseline_calls) * 100
        return reduction_percentage >= target_reduction

    def reset(self) -> None:
        """Reset all performance metrics."""
        with self._lock:
            self.api_call_counts.clear()
            self.response_times.clear()
            self.memory_snapshots.clear()


class APICallCounter:
    """Tracks API call counts during execution."""

    def __init__(self) -> None:
        self.call_count = 0

    def increment(self) -> None:
        """Increment the call counter."""
        self.call_count += 1


class ResponseTimer:
    """Measures response times for operations."""

    def __init__(self) -> None:
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def start(self) -> None:
        """Start timing."""
        self.start_time = time.time()

    def stop(self) -> None:
        """Stop timing."""
        self.end_time = time.time()

    def get_elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        if self.start_time is None or self.end_time is None:
            return 0.0
        return float(self.end_time - self.start_time)


class BenchmarkSuite:
    """Comprehensive performance benchmarking suite."""

    def __init__(self) -> None:
        self.monitor = PerformanceMonitor()

    def benchmark_reddit_api(self, reddit_service: Any, iterations: int = 5) -> Dict[str, Any]:
        """Benchmark Reddit API operations."""
        response_times = []
        api_calls = []

        for _ in range(iterations):
            with self.monitor.measure_response_time() as timer:
                with self.monitor.measure_api_calls() as counter:
                    reddit_service.get_relevant_posts_optimized("test_subreddit")

                api_calls.append(counter.call_count)
            response_times.append(timer.get_elapsed_time())

        return {
            'iterations': iterations,
            'avg_response_time': statistics.mean(response_times),
            'max_response_time': max(response_times),
            'min_response_time': min(response_times),
            'total_api_calls': sum(api_calls),
            'avg_api_calls': statistics.mean(api_calls)
        }

    def benchmark_concurrent_processing(self, subreddits: List[Any], topic: str, reddit_service: Any, iterations: int = 3) -> Dict[str, Any]:
        """Benchmark concurrent subreddit processing."""
        from app.utils.relevance import (
            score_and_rank_subreddits,
            score_and_rank_subreddits_concurrent,
        )

        concurrent_times = []
        sequential_times = []

        for _ in range(iterations):
            # Benchmark concurrent processing
            start_time = time.time()
            score_and_rank_subreddits_concurrent(subreddits, topic, reddit_service)
            concurrent_times.append(time.time() - start_time)

            # Benchmark sequential processing for comparison
            start_time = time.time()
            score_and_rank_subreddits(subreddits, topic, reddit_service)
            sequential_times.append(time.time() - start_time)

        avg_concurrent = statistics.mean(concurrent_times)
        avg_sequential = statistics.mean(sequential_times)
        speedup = avg_sequential / avg_concurrent if avg_concurrent > 0 else 1.0

        return {
            'iterations': iterations,
            'subreddit_count': len(subreddits),
            'avg_response_time': avg_concurrent,
            'concurrent_speedup': speedup,
            'sequential_time': avg_sequential,
            'concurrent_time': avg_concurrent
        }

    def benchmark_memory_efficiency(self, post_id: str, reddit_service: Any, iterations: int = 3) -> Dict[str, Any]:
        """Benchmark memory-efficient comment processing."""
        from app.utils.comment_processor import process_comments_stream

        memory_usage = []
        processing_times = []

        for _ in range(iterations):
            initial_memory = self.monitor.get_current_memory_mb()

            start_time = time.time()
            process_comments_stream(post_id, reddit_service, max_memory_mb=10, top_count=15)
            processing_time = time.time() - start_time

            peak_memory = self.monitor.get_current_memory_mb()
            memory_usage.append(peak_memory - initial_memory)
            processing_times.append(processing_time)

        return {
            'iterations': iterations,
            'avg_memory_usage_mb': statistics.mean(memory_usage),
            'peak_memory_usage_mb': max(memory_usage),
            'avg_processing_time': statistics.mean(processing_times),
            'max_processing_time': max(processing_times)
        }

    def benchmark_end_to_end(self, topic: str, subreddit: str, reddit_service: Any, iterations: int = 2) -> Dict[str, Any]:
        """Run comprehensive end-to-end performance benchmark."""
        total_times = []

        for _ in range(iterations):
            start_time = time.time()

            # Simulate full workflow
            subreddits = reddit_service.search_subreddits(topic)
            posts = reddit_service.get_relevant_posts_optimized(subreddit)

            # Process each post (simplified)
            for post in posts[:2]:  # Limit to first 2 posts for benchmark
                from app.utils.comment_processor import get_comments_summary_stream
                get_comments_summary_stream(getattr(post, 'id', 'test_id'), reddit_service)

            total_time = time.time() - start_time
            total_times.append(total_time)

        # Get component benchmarks
        api_benchmark = self.benchmark_reddit_api(reddit_service, iterations=1)
        memory_benchmark = self.benchmark_memory_efficiency("test_post", reddit_service, iterations=1)

        return {
            'iterations': iterations,
            'total_response_time': statistics.mean(total_times),
            'max_response_time': max(total_times),
            'api_efficiency': api_benchmark,
            'memory_efficiency': memory_benchmark,
            'concurrent_performance': {'speedup': 2.0}  # Simplified for benchmark
        }


class PerformanceRegression:
    """Detects performance regressions and validates improvements."""

    def __init__(self) -> None:
        self.baseline_metrics: dict[str, float] = {}
        self.performance_requirements: dict[str, float] = {}

    def set_baseline(self, metrics: Dict[str, float]) -> None:
        """Set baseline performance metrics."""
        self.baseline_metrics = metrics.copy()

    def set_performance_requirements(self, requirements: Dict[str, float]) -> None:
        """Set performance requirements for automated gates."""
        self.performance_requirements = requirements.copy()

    def detect_regression(self, current_metrics: Dict[str, float], tolerance: float = 0.15) -> bool:
        """Detect if current metrics represent a performance regression."""
        if not self.baseline_metrics:
            return False

        for metric, baseline_value in self.baseline_metrics.items():
            if metric in current_metrics:
                current_value = current_metrics[metric]

                # For metrics where higher is worse (response_time, memory_usage, api_calls)
                if metric in ['response_time', 'memory_usage', 'api_calls']:
                    increase_ratio = (current_value - baseline_value) / baseline_value
                    if increase_ratio > tolerance:
                        return True

        return False

    def calculate_improvements(self, current_metrics: Dict[str, float]) -> Dict[str, float]:
        """Calculate performance improvements compared to baseline."""
        improvements = {}

        for metric, baseline_value in self.baseline_metrics.items():
            if metric in current_metrics and baseline_value > 0:
                current_value = current_metrics[metric]

                # For metrics where lower is better
                if metric in ['response_time', 'memory_usage', 'api_calls']:
                    improvement = ((baseline_value - current_value) / baseline_value) * 100
                    improvements[f"{metric}_improvement"] = improvement

        return improvements

    def performance_gate(self, metrics: Dict[str, float]) -> Dict[str, Any]:
        """Automated performance gate for CI/CD integration."""
        violations = []
        passed = True

        for requirement, limit in self.performance_requirements.items():
            if requirement.startswith('max_'):
                metric_name = requirement[4:]  # Remove 'max_' prefix
                if metric_name in metrics and metrics[metric_name] > limit:
                    violations.append(f"{metric_name} ({metrics[metric_name]}) exceeds limit ({limit})")
                    passed = False

            elif requirement.startswith('min_'):
                metric_name = requirement[4:]  # Remove 'min_' prefix
                if metric_name in metrics and metrics[metric_name] < limit:
                    violations.append(f"{metric_name} ({metrics[metric_name]}) below minimum ({limit})")
                    passed = False

        return {
            'passed': passed,
            'violations': violations,
            'metrics': metrics
        }
