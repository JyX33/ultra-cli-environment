# ABOUTME: Performance monitoring service for tracking system metrics, response times, and resource usage
# ABOUTME: Provides real-time monitoring, alerting thresholds, and performance reporting capabilities

from collections import defaultdict, deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
import logging
import threading
import time
from typing import Any

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.warning("psutil not available - system metrics will be limited")

# Set up logging
logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """Single performance metric measurement."""
    name: str
    value: float
    unit: str
    timestamp: datetime
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class PerformanceThresholds:
    """Performance thresholds for alerting."""
    max_response_time_ms: float = 2000.0
    max_memory_usage_mb: float = 512.0
    max_cpu_usage_percent: float = 80.0
    max_database_queries_per_request: int = 10
    min_cache_hit_rate: float = 0.7


@dataclass
class PerformanceAlert:
    """Performance alert when thresholds are exceeded."""
    metric_name: str
    current_value: float
    threshold_value: float
    severity: str  # 'warning', 'critical'
    message: str
    timestamp: datetime


class PerformanceTimer:
    """High-precision timer for measuring operation durations."""

    def __init__(self, name: str, tags: dict[str, str] | None = None):
        self.name = name
        self.tags = tags or {}
        self.start_time: float | None = None
        self.end_time: float | None = None
        self.duration: float | None = None

    def start(self) -> 'PerformanceTimer':
        """Start the timer."""
        self.start_time = time.perf_counter()
        return self

    def stop(self) -> float:
        """Stop the timer and return duration in seconds."""
        if self.start_time is None:
            raise ValueError("Timer not started")

        self.end_time = time.perf_counter()
        self.duration = self.end_time - self.start_time
        return self.duration

    def __enter__(self) -> 'PerformanceTimer':
        """Context manager entry."""
        return self.start()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.stop()


class PerformanceMonitoringService:
    """Comprehensive performance monitoring service."""

    def __init__(
        self,
        max_metrics_history: int = 1000,
        enable_system_monitoring: bool = True,
        monitoring_interval_seconds: float = 5.0
    ):
        """Initialize performance monitoring service.

        Args:
            max_metrics_history: Maximum number of metrics to keep in memory
            enable_system_monitoring: Whether to enable system resource monitoring
            monitoring_interval_seconds: Interval for system monitoring
        """
        self.max_metrics_history = max_metrics_history
        self.enable_system_monitoring = enable_system_monitoring
        self.monitoring_interval = monitoring_interval_seconds

        # Metrics storage
        self.metrics_history: deque = deque(maxlen=max_metrics_history)
        self.current_metrics: dict[str, PerformanceMetric] = {}
        self.metric_summaries: dict[str, dict[str, float]] = defaultdict(dict)

        # Performance thresholds
        self.thresholds = PerformanceThresholds()
        self.alerts: list[PerformanceAlert] = []

        # Monitoring state
        self._monitoring_active = False
        self._monitoring_thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # Performance counters
        self.request_count = 0
        self.total_response_time = 0.0
        self.database_query_count = 0
        self.cache_hits = 0
        self.cache_misses = 0

        logger.info("Performance monitoring service initialized")

    def set_thresholds(self, **kwargs: Any) -> None:
        """Update performance thresholds.

        Args:
            **kwargs: Threshold values to update
        """
        for key, value in kwargs.items():
            if hasattr(self.thresholds, key):
                setattr(self.thresholds, key, value)
                logger.info(f"Updated threshold {key} to {value}")

    def record_metric(
        self,
        name: str,
        value: float,
        unit: str = "count",
        tags: dict[str, str] | None = None
    ) -> None:
        """Record a performance metric.

        Args:
            name: Metric name
            value: Metric value
            unit: Unit of measurement
            tags: Optional tags for categorization
        """
        metric = PerformanceMetric(
            name=name,
            value=value,
            unit=unit,
            timestamp=datetime.now(),
            tags=tags or {}
        )

        with self._lock:
            self.metrics_history.append(metric)
            self.current_metrics[name] = metric
            self._update_metric_summary(metric)
            self._check_thresholds(metric)

    def create_timer(self, name: str, tags: dict[str, str] | None = None) -> PerformanceTimer:
        """Create a performance timer.

        Args:
            name: Timer name
            tags: Optional tags

        Returns:
            PerformanceTimer instance
        """
        return PerformanceTimer(name, tags)

    @contextmanager
    def measure_time(self, operation_name: str, tags: dict[str, str] | None = None) -> Any:
        """Context manager for measuring operation time.

        Args:
            operation_name: Name of the operation being measured
            tags: Optional tags for categorization
        """
        timer = self.create_timer(operation_name, tags)
        timer.start()

        try:
            yield timer
        finally:
            duration = timer.stop()
            self.record_metric(
                f"{operation_name}_duration",
                duration * 1000,  # Convert to milliseconds
                "ms",
                tags
            )

    def record_request(self, response_time_ms: float) -> None:
        """Record an API request and its response time.

        Args:
            response_time_ms: Response time in milliseconds
        """
        with self._lock:
            self.request_count += 1
            self.total_response_time += response_time_ms

        self.record_metric("request_response_time", response_time_ms, "ms")

        # Check response time threshold
        if response_time_ms > self.thresholds.max_response_time_ms:
            self._create_alert(
                "response_time",
                response_time_ms,
                self.thresholds.max_response_time_ms,
                "warning" if response_time_ms < self.thresholds.max_response_time_ms * 2 else "critical",
                f"Response time {response_time_ms:.1f}ms exceeds threshold"
            )

    def record_database_query(self, query_time_ms: float | None = None) -> None:
        """Record a database query execution.

        Args:
            query_time_ms: Optional query execution time in milliseconds
        """
        with self._lock:
            self.database_query_count += 1

        if query_time_ms is not None:
            self.record_metric("database_query_time", query_time_ms, "ms")

    def record_cache_operation(self, hit: bool) -> None:
        """Record a cache operation (hit or miss).

        Args:
            hit: True for cache hit, False for cache miss
        """
        with self._lock:
            if hit:
                self.cache_hits += 1
            else:
                self.cache_misses += 1

        # Calculate and record hit rate
        total_cache_ops = self.cache_hits + self.cache_misses
        if total_cache_ops > 0:
            hit_rate = self.cache_hits / total_cache_ops
            self.record_metric("cache_hit_rate", hit_rate, "ratio")

            # Check cache hit rate threshold
            if hit_rate < self.thresholds.min_cache_hit_rate:
                self._create_alert(
                    "cache_hit_rate",
                    hit_rate,
                    self.thresholds.min_cache_hit_rate,
                    "warning",
                    f"Cache hit rate {hit_rate:.2%} below threshold"
                )

    def get_system_metrics(self) -> dict[str, float]:
        """Get current system resource metrics.

        Returns:
            Dictionary with system metrics
        """
        metrics = {}

        if PSUTIL_AVAILABLE:
            try:
                # CPU usage
                cpu_percent = psutil.cpu_percent(interval=0.1)
                metrics['cpu_usage_percent'] = cpu_percent

                # Memory usage
                memory = psutil.virtual_memory()
                metrics['memory_usage_mb'] = memory.used / 1024 / 1024
                metrics['memory_usage_percent'] = memory.percent

                # Disk usage
                disk = psutil.disk_usage('/')
                metrics['disk_usage_percent'] = (disk.used / disk.total) * 100

                # Network I/O (if available)
                try:
                    network = psutil.net_io_counters()
                    metrics['network_bytes_sent'] = network.bytes_sent
                    metrics['network_bytes_recv'] = network.bytes_recv
                except Exception:
                    pass  # Network stats may not be available

            except Exception as e:
                logger.warning(f"Error collecting system metrics: {e}")

        return metrics

    def start_monitoring(self) -> None:
        """Start background system monitoring."""
        if self._monitoring_active or not self.enable_system_monitoring:
            return

        self._monitoring_active = True
        self._monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._monitoring_thread.start()

        logger.info("Background system monitoring started")

    def stop_monitoring(self) -> None:
        """Stop background system monitoring."""
        self._monitoring_active = False
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=5.0)

        logger.info("Background system monitoring stopped")

    def get_performance_summary(self) -> dict[str, Any]:
        """Get comprehensive performance summary.

        Returns:
            Dictionary with performance metrics and statistics
        """
        with self._lock:
            avg_response_time = (
                self.total_response_time / self.request_count
                if self.request_count > 0 else 0
            )

            cache_hit_rate = (
                self.cache_hits / (self.cache_hits + self.cache_misses)
                if (self.cache_hits + self.cache_misses) > 0 else 0
            )

        system_metrics = self.get_system_metrics()

        return {
            'request_metrics': {
                'total_requests': self.request_count,
                'average_response_time_ms': avg_response_time,
                'database_queries': self.database_query_count,
                'queries_per_request': (
                    self.database_query_count / self.request_count
                    if self.request_count > 0 else 0
                )
            },
            'cache_metrics': {
                'hits': self.cache_hits,
                'misses': self.cache_misses,
                'hit_rate': cache_hit_rate
            },
            'system_metrics': system_metrics,
            'thresholds': asdict(self.thresholds),
            'alerts_count': len(self.alerts),
            'active_alerts': [
                alert for alert in self.alerts[-10:]  # Last 10 alerts
                if alert.timestamp > datetime.now() - timedelta(hours=1)
            ]
        }

    def get_recent_metrics(self, minutes: int = 5) -> list[PerformanceMetric]:
        """Get metrics from the last N minutes.

        Args:
            minutes: Number of minutes to look back

        Returns:
            List of recent metrics
        """
        cutoff_time = datetime.now() - timedelta(minutes=minutes)

        return [
            metric for metric in self.metrics_history
            if metric.timestamp >= cutoff_time
        ]

    def analyze_performance_trends(self) -> dict[str, Any]:
        """Analyze performance trends over time.

        Returns:
            Dictionary with trend analysis
        """
        recent_metrics = self.get_recent_metrics(30)  # Last 30 minutes

        if not recent_metrics:
            return {'error': 'No recent metrics available'}

        # Group metrics by name
        metric_groups = defaultdict(list)
        for metric in recent_metrics:
            metric_groups[metric.name].append(metric.value)

        trends = {}
        for metric_name, values in metric_groups.items():
            if len(values) >= 2:
                # Simple trend analysis
                first_half = values[:len(values)//2]
                second_half = values[len(values)//2:]

                first_avg = sum(first_half) / len(first_half)
                second_avg = sum(second_half) / len(second_half)

                trend_direction = "improving" if second_avg < first_avg else "degrading"
                trend_magnitude = abs(second_avg - first_avg) / first_avg if first_avg > 0 else 0

                trends[metric_name] = {
                    'direction': trend_direction,
                    'magnitude_percent': trend_magnitude * 100,
                    'current_average': second_avg,
                    'previous_average': first_avg,
                    'sample_count': len(values)
                }

        return {
            'analysis_period_minutes': 30,
            'trends': trends,
            'generated_at': datetime.now().isoformat()
        }

    def reset_counters(self) -> None:
        """Reset performance counters."""
        with self._lock:
            self.request_count = 0
            self.total_response_time = 0.0
            self.database_query_count = 0
            self.cache_hits = 0
            self.cache_misses = 0
            self.alerts.clear()

        logger.info("Performance counters reset")

    def export_metrics(self, format_type: str = "json") -> str | dict[str, Any]:
        """Export metrics in specified format.

        Args:
            format_type: Export format ('json', 'dict')

        Returns:
            Exported metrics data
        """
        data = {
            'summary': self.get_performance_summary(),
            'recent_metrics': [
                asdict(metric) for metric in self.get_recent_metrics(60)
            ],
            'trends': self.analyze_performance_trends(),
            'exported_at': datetime.now().isoformat()
        }

        if format_type == "json":
            import json
            return json.dumps(data, indent=2, default=str)
        else:
            return data

    def _monitoring_loop(self) -> None:
        """Background monitoring loop."""
        while self._monitoring_active:
            try:
                system_metrics = self.get_system_metrics()

                for metric_name, value in system_metrics.items():
                    self.record_metric(metric_name, value, "system")

                time.sleep(self.monitoring_interval)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.monitoring_interval)

    def _update_metric_summary(self, metric: PerformanceMetric) -> None:
        """Update metric summary statistics.

        Args:
            metric: Metric to update summary for
        """
        name = metric.name
        value = metric.value

        if name not in self.metric_summaries:
            self.metric_summaries[name] = {
                'count': 0,
                'sum': 0.0,
                'min': float('inf'),
                'max': float('-inf')
            }

        summary = self.metric_summaries[name]
        summary['count'] += 1
        summary['sum'] += value
        summary['min'] = min(summary['min'], value)
        summary['max'] = max(summary['max'], value)
        summary['avg'] = summary['sum'] / summary['count']

    def _check_thresholds(self, metric: PerformanceMetric) -> None:
        """Check if metric exceeds thresholds.

        Args:
            metric: Metric to check
        """
        name = metric.name
        value = metric.value

        # Define threshold checks
        threshold_checks = {
            'request_response_time': ('max_response_time_ms', lambda v, t: v > t),
            'memory_usage_mb': ('max_memory_usage_mb', lambda v, t: v > t),
            'cpu_usage_percent': ('max_cpu_usage_percent', lambda v, t: v > t),
            'cache_hit_rate': ('min_cache_hit_rate', lambda v, t: v < t),
        }

        if name in threshold_checks:
            threshold_attr, check_func = threshold_checks[name]
            threshold_value = getattr(self.thresholds, threshold_attr)

            if check_func(value, threshold_value):
                severity = "critical" if value > threshold_value * 1.5 else "warning"
                self._create_alert(
                    name,
                    value,
                    threshold_value,
                    severity,
                    f"{name} {value} {'below' if check_func == (lambda v, t: v < t) else 'exceeds'} threshold {threshold_value}"
                )

    def _create_alert(
        self,
        metric_name: str,
        current_value: float,
        threshold_value: float,
        severity: str,
        message: str
    ) -> None:
        """Create a performance alert.

        Args:
            metric_name: Name of the metric that triggered the alert
            current_value: Current value of the metric
            threshold_value: Threshold value that was exceeded
            severity: Alert severity level
            message: Alert message
        """
        alert = PerformanceAlert(
            metric_name=metric_name,
            current_value=current_value,
            threshold_value=threshold_value,
            severity=severity,
            message=message,
            timestamp=datetime.now()
        )

        self.alerts.append(alert)

        # Keep only last 100 alerts
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-100:]

        logger.warning(f"Performance alert: {message}")

    def __enter__(self) -> 'PerformanceMonitoringService':
        """Context manager entry."""
        self.start_monitoring()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.stop_monitoring()
