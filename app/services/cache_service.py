# ABOUTME: Caching service with in-memory and Redis support for performance optimization
# ABOUTME: Provides cache invalidation, TTL management, and hit rate monitoring

import contextlib
from dataclasses import asdict, dataclass, field
import json
import logging
import time
from typing import Any

from app.core.structured_logging import (
    get_logger,
    log_error_with_context,
    log_service_operation,
)

# Set up structured logging
logger = get_logger(__name__)


def _sanitize_cache_key_for_logging(cache_key: str) -> str:
    """Sanitize cache key for secure logging by obscuring sensitive data.

    This function masks potentially sensitive information in cache keys
    to prevent data leakage in logs while preserving useful debugging info.

    Args:
        cache_key: The cache key to sanitize

    Returns:
        Sanitized cache key safe for logging
    """
    if not cache_key:
        return "<empty_key>"

    # Split key by common delimiters to identify segments
    parts = cache_key.split(':')

    if len(parts) < 2:
        # Simple key without delimiters - mask middle part
        if len(cache_key) <= 6:
            return cache_key[:2] + "***"
        return cache_key[:3] + "***" + cache_key[-3:]

    # For structured keys like "post:abc123" or "subreddit_posts:python"
    sanitized_parts = []
    for i, part in enumerate(parts):
        if i == 0:
            # Keep the first part (operation type) for debugging
            sanitized_parts.append(part)
        elif len(part) <= 4:
            # Short identifiers - mask partially
            sanitized_parts.append(part[:1] + "***")
        else:
            # Longer identifiers - show prefix and suffix
            sanitized_parts.append(part[:2] + "***" + part[-2:])

    return ':'.join(sanitized_parts)


@dataclass
class CachePerformanceMetrics:
    """Detailed performance metrics for cache operations."""
    operation_type: str
    count: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float('inf')
    max_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    last_operation_time: float = 0.0

    def record_operation(self, duration_ms: float) -> None:
        """Record a cache operation with its duration."""
        self.count += 1
        self.total_duration_ms += duration_ms
        self.min_duration_ms = min(self.min_duration_ms, duration_ms)
        self.max_duration_ms = max(self.max_duration_ms, duration_ms)
        self.avg_duration_ms = self.total_duration_ms / self.count
        self.last_operation_time = time.time()


@dataclass
class CacheStats:
    """Enhanced statistics for cache performance monitoring and alerting."""
    hits: int = 0
    misses: int = 0
    total_requests: int = 0
    hit_rate: float = 0.0
    memory_usage_mb: float = 0.0
    oldest_entry_age_seconds: float = 0.0

    # Enhanced performance metrics
    average_get_time_ms: float = 0.0
    average_set_time_ms: float = 0.0
    slow_operations_count: int = 0
    evictions_count: int = 0
    expired_entries_cleaned: int = 0

    # Performance thresholds and alerts
    performance_warnings: list[str] = field(default_factory=list)
    cache_efficiency_score: float = 0.0
    memory_pressure_level: str = "normal"  # normal, moderate, high, critical

    # Historical tracking
    peak_memory_usage_mb: float = 0.0
    requests_per_second: float = 0.0
    cache_utilization_percent: float = 0.0


@dataclass
class CacheEntry:
    """Internal cache entry with metadata."""
    value: Any
    created_at: float
    ttl_seconds: int | None = None
    access_count: int = 0
    last_accessed: float | None = None

    def __post_init__(self) -> None:
        if self.last_accessed is None:
            self.last_accessed = self.created_at

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        if self.ttl_seconds is None:
            return False
        return time.time() - self.created_at > self.ttl_seconds

    def touch(self) -> None:
        """Update access statistics."""
        self.access_count += 1
        self.last_accessed = time.time()


class InMemoryCache:
    """High-performance in-memory cache with TTL, eviction policies, and performance monitoring."""

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """Initialize in-memory cache with performance monitoring.

        Args:
            max_size: Maximum number of entries to store
            default_ttl: Default TTL in seconds (0 = no expiration)
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: dict[str, CacheEntry] = {}
        self._stats = CacheStats()

        # Performance monitoring
        self._performance_metrics: dict[str, CachePerformanceMetrics] = {
            'get': CachePerformanceMetrics('get'),
            'set': CachePerformanceMetrics('set'),
            'delete': CachePerformanceMetrics('delete'),
            'eviction': CachePerformanceMetrics('eviction')
        }

        # Performance thresholds (configurable)
        self._slow_operation_threshold_ms = 10.0  # Operations slower than 10ms are considered slow
        self._memory_warning_threshold_mb = 100.0  # Warning at 100MB
        self._memory_critical_threshold_mb = 250.0  # Critical at 250MB
        self._low_hit_rate_threshold = 0.5  # Warning if hit rate below 50%

        # Historical tracking
        self._stats_reset_time = time.time()
        self._peak_memory_usage = 0.0

    def get(self, key: str) -> Any | None:
        """Get value from cache with performance monitoring.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        start_time = time.time()

        try:
            self._stats.total_requests += 1

            if key not in self._cache:
                self._stats.misses += 1
                self._update_hit_rate()
                return None

            entry = self._cache[key]

            if entry.is_expired():
                del self._cache[key]
                self._stats.misses += 1
                self._update_hit_rate()
                return None

            entry.touch()
            self._stats.hits += 1
            self._update_hit_rate()

            log_service_operation(
                logger, "InMemoryCache", "cache_hit",
                cache_key=_sanitize_cache_key_for_logging(key),
                hit_rate=self._stats.hit_rate
            )
            return entry.value

        finally:
            # Record performance metrics
            duration_ms = (time.time() - start_time) * 1000
            self._performance_metrics['get'].record_operation(duration_ms)

            # Track slow operations
            if duration_ms > self._slow_operation_threshold_ms:
                self._stats.slow_operations_count += 1

    def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None
    ) -> None:
        """Set value in cache with performance monitoring.

        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (None = use default)
        """
        start_time = time.time()

        try:
            if ttl is None:
                ttl = self.default_ttl if self.default_ttl > 0 else None

            # Evict old entries if at capacity
            if len(self._cache) >= self.max_size and key not in self._cache:
                self._evict_lru()

            entry = CacheEntry(
                value=value,
                created_at=time.time(),
                ttl_seconds=ttl
            )

            self._cache[key] = entry
            log_service_operation(
                logger, "InMemoryCache", "cache_set",
                cache_key=_sanitize_cache_key_for_logging(key),
                ttl_seconds=ttl,
                cache_size=len(self._cache)
            )

        finally:
            # Record performance metrics
            duration_ms = (time.time() - start_time) * 1000
            self._performance_metrics['set'].record_operation(duration_ms)

            # Track slow operations
            if duration_ms > self._slow_operation_threshold_ms:
                self._stats.slow_operations_count += 1

    def delete(self, key: str) -> bool:
        """Delete value from cache with performance monitoring.

        Args:
            key: Cache key to delete

        Returns:
            True if key was found and deleted
        """
        start_time = time.time()

        try:
            if key in self._cache:
                del self._cache[key]
                log_service_operation(
                    logger, "InMemoryCache", "cache_delete",
                    cache_key=_sanitize_cache_key_for_logging(key),
                    cache_size=len(self._cache)
                )
                return True
            return False

        finally:
            # Record performance metrics
            duration_ms = (time.time() - start_time) * 1000
            self._performance_metrics['delete'].record_operation(duration_ms)

            # Track slow operations
            if duration_ms > self._slow_operation_threshold_ms:
                self._stats.slow_operations_count += 1

    def clear(self) -> None:
        """Clear all cached values and reset performance metrics."""
        self._cache.clear()
        self._stats = CacheStats()

        # Reset performance metrics
        for metric in self._performance_metrics.values():
            metric.count = 0
            metric.total_duration_ms = 0.0
            metric.min_duration_ms = float('inf')
            metric.max_duration_ms = 0.0
            metric.avg_duration_ms = 0.0
            metric.last_operation_time = 0.0

        self._stats_reset_time = time.time()
        self._peak_memory_usage = 0.0

        log_service_operation(
            logger, "InMemoryCache", "cache_cleared",
            previous_size=len(self._cache),
            stats_reset=True
        )

    def get_stats(self) -> CacheStats:
        """Get comprehensive cache performance statistics with monitoring and alerts."""
        # Update memory usage estimate
        try:
            import sys
            total_size = sum(
                sys.getsizeof(key) + sys.getsizeof(entry.value)
                for key, entry in self._cache.items()
            )
            self._stats.memory_usage_mb = total_size / 1024 / 1024

            # Track peak memory usage
            if self._stats.memory_usage_mb > self._peak_memory_usage:
                self._peak_memory_usage = self._stats.memory_usage_mb
            self._stats.peak_memory_usage_mb = self._peak_memory_usage

        except Exception:
            self._stats.memory_usage_mb = 0.0

        # Update oldest entry age
        if self._cache:
            oldest_time = min(entry.created_at for entry in self._cache.values())
            self._stats.oldest_entry_age_seconds = time.time() - oldest_time
        else:
            self._stats.oldest_entry_age_seconds = 0.0

        # Update performance metrics
        self._stats.average_get_time_ms = self._performance_metrics['get'].avg_duration_ms
        self._stats.average_set_time_ms = self._performance_metrics['set'].avg_duration_ms

        # Calculate cache utilization
        self._stats.cache_utilization_percent = (len(self._cache) / self.max_size) * 100

        # Calculate requests per second
        time_since_reset = time.time() - self._stats_reset_time
        if time_since_reset > 0:
            self._stats.requests_per_second = self._stats.total_requests / time_since_reset

        # Performance analysis and warnings
        self._stats.performance_warnings = []

        # Memory pressure analysis
        if self._stats.memory_usage_mb >= self._memory_critical_threshold_mb:
            self._stats.memory_pressure_level = "critical"
            self._stats.performance_warnings.append(
                f"Critical memory usage: {self._stats.memory_usage_mb:.1f}MB >= {self._memory_critical_threshold_mb}MB"
            )
        elif self._stats.memory_usage_mb >= self._memory_warning_threshold_mb:
            self._stats.memory_pressure_level = "high"
            self._stats.performance_warnings.append(
                f"High memory usage: {self._stats.memory_usage_mb:.1f}MB >= {self._memory_warning_threshold_mb}MB"
            )
        elif self._stats.memory_usage_mb >= self._memory_warning_threshold_mb * 0.75:
            self._stats.memory_pressure_level = "moderate"
        else:
            self._stats.memory_pressure_level = "normal"

        # Hit rate analysis
        if self._stats.hit_rate < self._low_hit_rate_threshold:
            self._stats.performance_warnings.append(
                f"Low cache hit rate: {self._stats.hit_rate:.2%} < {self._low_hit_rate_threshold:.2%}"
            )

        # Slow operations analysis
        total_operations = sum(metric.count for metric in self._performance_metrics.values())
        if total_operations > 0:
            slow_operation_rate = self._stats.slow_operations_count / total_operations
            if slow_operation_rate > 0.1:  # More than 10% slow operations
                self._stats.performance_warnings.append(
                    f"High slow operation rate: {slow_operation_rate:.2%} of operations exceed {self._slow_operation_threshold_ms}ms"
                )

        # Cache efficiency score calculation
        efficiency_factors = []

        # Hit rate factor (0-40 points)
        hit_rate_score = min(self._stats.hit_rate * 40, 40)
        efficiency_factors.append(hit_rate_score)

        # Memory efficiency factor (0-30 points)
        if self._stats.cache_utilization_percent > 0:
            # Optimal utilization is around 70-80%
            optimal_utilization = 75.0
            utilization_diff = abs(self._stats.cache_utilization_percent - optimal_utilization)
            memory_score = max(0, 30 - (utilization_diff / 100 * 30))
        else:
            memory_score = 0
        efficiency_factors.append(memory_score)

        # Performance factor (0-20 points)
        avg_response_time = (self._stats.average_get_time_ms + self._stats.average_set_time_ms) / 2
        if avg_response_time > 0:
            # Target response time is under 5ms
            performance_score = max(0, 20 - (avg_response_time / 5 * 20))
        else:
            performance_score = 20
        efficiency_factors.append(performance_score)

        # Stability factor (0-10 points)
        if total_operations > 0:
            stability_score = max(0, 10 - (slow_operation_rate * 10))
        else:
            stability_score = 10
        efficiency_factors.append(stability_score)

        self._stats.cache_efficiency_score = sum(efficiency_factors)

        # Add efficiency warnings
        if self._stats.cache_efficiency_score < 60:
            self._stats.performance_warnings.append(
                f"Low cache efficiency score: {self._stats.cache_efficiency_score:.1f}/100"
            )

        return self._stats

    def cleanup_expired(self) -> int:
        """Remove expired entries from cache with performance tracking.

        Returns:
            Number of entries removed
        """
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired()
        ]

        for key in expired_keys:
            del self._cache[key]

        # Update statistics
        self._stats.expired_entries_cleaned += len(expired_keys)

        if expired_keys:
            log_service_operation(
                logger, "InMemoryCache", "expired_cleanup",
                expired_count=len(expired_keys),
                remaining_size=len(self._cache)
            )

        return len(expired_keys)

    def _evict_lru(self) -> None:
        """Evict least recently used entry with performance tracking."""
        if not self._cache:
            return

        start_time = time.time()

        try:
            lru_key = min(
                self._cache.keys(),
                key=lambda k: self._cache[k].last_accessed or 0.0
            )

            del self._cache[lru_key]

            # Update statistics
            self._stats.evictions_count += 1

            log_service_operation(
                logger, "InMemoryCache", "lru_eviction",
                evicted_key=_sanitize_cache_key_for_logging(lru_key),
                cache_size=len(self._cache),
                total_evictions=self._stats.evictions_count
            )

        finally:
            # Record performance metrics
            duration_ms = (time.time() - start_time) * 1000
            self._performance_metrics['eviction'].record_operation(duration_ms)

            # Track slow operations
            if duration_ms > self._slow_operation_threshold_ms:
                self._stats.slow_operations_count += 1

    def _update_hit_rate(self) -> None:
        """Update cache hit rate statistics."""
        if self._stats.total_requests > 0:
            self._stats.hit_rate = self._stats.hits / self._stats.total_requests

    def get_detailed_performance_metrics(self) -> dict[str, Any]:
        """Get detailed performance metrics for all cache operations.

        Returns:
            Dictionary with detailed performance data for analysis
        """
        return {
            'operation_metrics': {
                op_type: {
                    'count': metric.count,
                    'total_duration_ms': metric.total_duration_ms,
                    'min_duration_ms': metric.min_duration_ms if metric.min_duration_ms != float('inf') else 0.0,
                    'max_duration_ms': metric.max_duration_ms,
                    'avg_duration_ms': metric.avg_duration_ms,
                    'last_operation_time': metric.last_operation_time,
                    'operations_per_second': metric.count / max((time.time() - self._stats_reset_time), 1)
                }
                for op_type, metric in self._performance_metrics.items()
            },
            'thresholds': {
                'slow_operation_threshold_ms': self._slow_operation_threshold_ms,
                'memory_warning_threshold_mb': self._memory_warning_threshold_mb,
                'memory_critical_threshold_mb': self._memory_critical_threshold_mb,
                'low_hit_rate_threshold': self._low_hit_rate_threshold
            },
            'configuration': {
                'max_size': self.max_size,
                'default_ttl': self.default_ttl,
                'current_size': len(self._cache)
            }
        }

    def get_performance_report(self) -> dict[str, Any]:
        """Generate a comprehensive performance analysis report.

        Returns:
            Dictionary with performance analysis, recommendations, and insights
        """
        stats = self.get_stats()
        detailed_metrics = self.get_detailed_performance_metrics()

        # Analyze performance trends
        total_operations = sum(metric.count for metric in self._performance_metrics.values())

        # Generate recommendations
        recommendations = []

        if stats.hit_rate < 0.7:
            recommendations.append("Consider increasing cache TTL or reviewing cache key strategy to improve hit rate")

        if stats.cache_utilization_percent > 90:
            recommendations.append("Cache is near capacity - consider increasing max_size to prevent frequent evictions")
        elif stats.cache_utilization_percent < 30:
            recommendations.append("Cache utilization is low - consider reducing max_size to optimize memory usage")

        if stats.average_get_time_ms > 5.0:
            recommendations.append("Get operations are slow - consider optimizing cache key structure or reducing memory pressure")

        if stats.average_set_time_ms > 10.0:
            recommendations.append("Set operations are slow - may indicate memory pressure or complex data serialization")

        if stats.evictions_count > stats.expired_entries_cleaned * 2:
            recommendations.append("High eviction rate compared to natural expiration - consider increasing cache size or TTL")

        # Performance health assessment
        health_score = stats.cache_efficiency_score
        if health_score >= 80:
            health_status = "excellent"
        elif health_score >= 60:
            health_status = "good"
        elif health_score >= 40:
            health_status = "fair"
        else:
            health_status = "poor"

        return {
            'summary': {
                'health_status': health_status,
                'efficiency_score': health_score,
                'total_operations': total_operations,
                'uptime_seconds': time.time() - self._stats_reset_time,
                'memory_pressure': stats.memory_pressure_level
            },
            'key_metrics': {
                'hit_rate': stats.hit_rate,
                'requests_per_second': stats.requests_per_second,
                'avg_response_time_ms': (stats.average_get_time_ms + stats.average_set_time_ms) / 2,
                'memory_usage_mb': stats.memory_usage_mb,
                'cache_utilization_percent': stats.cache_utilization_percent
            },
            'performance_warnings': stats.performance_warnings,
            'recommendations': recommendations,
            'detailed_metrics': detailed_metrics,
            'generated_at': time.time()
        }

    def configure_performance_thresholds(
        self,
        slow_operation_ms: float | None = None,
        memory_warning_mb: float | None = None,
        memory_critical_mb: float | None = None,
        low_hit_rate: float | None = None
    ) -> None:
        """Configure performance monitoring thresholds.

        Args:
            slow_operation_ms: Threshold for slow operations in milliseconds
            memory_warning_mb: Memory usage warning threshold in MB
            memory_critical_mb: Memory usage critical threshold in MB
            low_hit_rate: Low hit rate warning threshold (0.0-1.0)
        """
        if slow_operation_ms is not None:
            self._slow_operation_threshold_ms = slow_operation_ms
        if memory_warning_mb is not None:
            self._memory_warning_threshold_mb = memory_warning_mb
        if memory_critical_mb is not None:
            self._memory_critical_threshold_mb = memory_critical_mb
        if low_hit_rate is not None:
            self._low_hit_rate_threshold = low_hit_rate

        log_service_operation(
            logger, "InMemoryCache", "thresholds_updated",
            slow_operation_threshold_ms=self._slow_operation_threshold_ms,
            memory_warning_threshold_mb=self._memory_warning_threshold_mb,
            memory_critical_threshold_mb=self._memory_critical_threshold_mb,
            low_hit_rate_threshold=self._low_hit_rate_threshold
        )


class RedditCacheService:
    """High-level cache service for Reddit data with intelligent invalidation."""

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int = 300,
        enable_redis: bool = False,
        redis_url: str | None = None
    ):
        """Initialize Reddit cache service.

        Args:
            max_size: Maximum cache size for in-memory cache
            default_ttl: Default TTL in seconds
            enable_redis: Whether to use Redis for distributed caching
            redis_url: Redis connection URL
        """
        self.cache = InMemoryCache(max_size=max_size, default_ttl=default_ttl)
        self.enable_redis = enable_redis
        self.redis_client = None

        if enable_redis:
            try:
                import redis  # type: ignore
                if redis_url:
                    self.redis_client = redis.from_url(redis_url)
                else:
                    self.redis_client = redis.Redis(host='localhost', port=6379, db=0)

                # Test connection
                self.redis_client.ping()
                log_service_operation(
                    logger, "RedditCacheService", "redis_connected",
                    redis_url=redis_url or "localhost:6379"
                )

            except ImportError:
                log_service_operation(
                    logger, "RedditCacheService", "redis_unavailable",
                    fallback="in-memory", reason="import_error"
                )
                self.enable_redis = False
            except Exception as e:
                log_error_with_context(
                    logger, e, "RedditCacheService", "redis_connection_failed",
                    fallback="in-memory", redis_url=redis_url
                )
                self.enable_redis = False

    def get_post(self, post_id: str) -> dict[str, Any] | None:
        """Get cached post data.

        Args:
            post_id: Reddit post ID

        Returns:
            Cached post data or None
        """
        cache_key = f"post:{post_id}"

        # Try Redis first if enabled
        if self.enable_redis and self.redis_client:
            try:
                cached_data = self.redis_client.get(cache_key)
                if cached_data:
                    log_service_operation(
                        logger, "RedditCacheService", "redis_cache_hit",
                        cache_key=_sanitize_cache_key_for_logging(post_id),
                        cache_type="redis"
                    )
                    return json.loads(cached_data)  # type: ignore
            except Exception as e:
                log_error_with_context(
                    logger, e, "RedditCacheService", "redis_get_failed",
                    cache_key=f"post:{_sanitize_cache_key_for_logging(post_id)}",
                    level=logging.DEBUG
                )

        # Fallback to in-memory cache
        return self.cache.get(cache_key)

    def set_post(
        self,
        post_id: str,
        post_data: dict[str, Any],
        ttl: int | None = None
    ) -> None:
        """Cache post data.

        Args:
            post_id: Reddit post ID
            post_data: Post data to cache
            ttl: TTL in seconds
        """
        cache_key = f"post:{post_id}"

        # Store in Redis if enabled
        if self.enable_redis and self.redis_client:
            try:
                ttl_seconds = ttl or 300  # 5 minutes default
                self.redis_client.setex(
                    cache_key,
                    ttl_seconds,
                    json.dumps(post_data, default=str)
                )
                log_service_operation(
                    logger, "RedditCacheService", "redis_cache_set",
                    cache_key=_sanitize_cache_key_for_logging(post_id),
                    ttl_seconds=ttl_seconds,
                    cache_type="redis"
                )
            except Exception as e:
                log_error_with_context(
                    logger, e, "RedditCacheService", "redis_set_failed",
                    cache_key=f"post:{_sanitize_cache_key_for_logging(post_id)}",
                    level=logging.DEBUG
                )

        # Always store in in-memory cache as fallback
        self.cache.set(cache_key, post_data, ttl)

    def get_subreddit_posts(self, subreddit: str) -> list[dict[str, Any]] | None:
        """Get cached subreddit posts.

        Args:
            subreddit: Subreddit name

        Returns:
            Cached posts list or None
        """
        cache_key = f"subreddit_posts:{subreddit}"
        return self.cache.get(cache_key)

    def set_subreddit_posts(
        self,
        subreddit: str,
        posts: list[dict[str, Any]],
        ttl: int = 180
    ) -> None:
        """Cache subreddit posts.

        Args:
            subreddit: Subreddit name
            posts: List of posts to cache
            ttl: TTL in seconds (default 3 minutes for fresh data)
        """
        cache_key = f"subreddit_posts:{subreddit}"
        self.cache.set(cache_key, posts, ttl)

    def get_check_run_results(self, subreddit: str, topic: str) -> dict[str, Any] | None:
        """Get cached check run results.

        Args:
            subreddit: Subreddit name
            topic: Topic searched

        Returns:
            Cached check run results or None
        """
        cache_key = f"check_run:{subreddit}:{topic}"
        return self.cache.get(cache_key)

    def set_check_run_results(
        self,
        subreddit: str,
        topic: str,
        results: dict[str, Any],
        ttl: int = 600
    ) -> None:
        """Cache check run results.

        Args:
            subreddit: Subreddit name
            topic: Topic searched
            results: Check run results to cache
            ttl: TTL in seconds (default 10 minutes)
        """
        cache_key = f"check_run:{subreddit}:{topic}"
        self.cache.set(cache_key, results, ttl)

    def get_trending_posts(self, subreddit: str) -> list[dict[str, Any]] | None:
        """Get cached trending posts.

        Args:
            subreddit: Subreddit name

        Returns:
            Cached trending posts or None
        """
        cache_key = f"trending:{subreddit}"
        return self.cache.get(cache_key)

    def set_trending_posts(
        self,
        subreddit: str,
        trending_posts: list[dict[str, Any]],
        ttl: int = 900
    ) -> None:
        """Cache trending posts.

        Args:
            subreddit: Subreddit name
            trending_posts: Trending posts to cache
            ttl: TTL in seconds (default 15 minutes)
        """
        cache_key = f"trending:{subreddit}"
        self.cache.set(cache_key, trending_posts, ttl)

    def invalidate_post(self, post_id: str) -> None:
        """Invalidate cached post data.

        Args:
            post_id: Reddit post ID to invalidate
        """
        cache_key = f"post:{post_id}"

        # Invalidate in Redis
        if self.enable_redis and self.redis_client:
            try:
                self.redis_client.delete(cache_key)
                log_service_operation(
                    logger, "RedditCacheService", "redis_invalidation",
                    cache_key=_sanitize_cache_key_for_logging(post_id),
                    cache_type="redis"
                )
            except Exception as e:
                log_error_with_context(
                    logger, e, "RedditCacheService", "redis_invalidation_failed",
                    cache_key=f"post:{_sanitize_cache_key_for_logging(post_id)}",
                    level=logging.DEBUG
                )

        # Invalidate in in-memory cache
        self.cache.delete(cache_key)

    def invalidate_subreddit(self, subreddit: str) -> None:
        """Invalidate all cached data for a subreddit.

        Args:
            subreddit: Subreddit name to invalidate
        """
        # Invalidate subreddit posts
        self.cache.delete(f"subreddit_posts:{subreddit}")
        self.cache.delete(f"trending:{subreddit}")

        # Invalidate check run results (pattern-based)
        # Note: This is simplified - in production, you'd want pattern matching
        log_service_operation(
            logger, "RedditCacheService", "subreddit_invalidation",
            subreddit=subreddit,
            invalidated_keys=["subreddit_posts", "trending"]
        )

    def get_cache_stats(self) -> dict[str, Any]:
        """Get comprehensive cache statistics.

        Returns:
            Dictionary with cache performance metrics
        """
        stats = self.cache.get_stats()

        redis_stats = {}
        if self.enable_redis and self.redis_client:
            try:
                redis_info = self.redis_client.info('memory')
                redis_stats = {
                    'memory_used_mb': redis_info.get('used_memory', 0) / 1024 / 1024,
                    'connected': True
                }
            except Exception as e:
                redis_stats = {'connected': False, 'error': str(e)}

        return {
            'in_memory_cache': asdict(stats),
            'redis_cache': redis_stats,
            'total_hit_rate': stats.hit_rate
        }

    def cleanup(self) -> dict[str, int]:
        """Perform cache cleanup operations.

        Returns:
            Dictionary with cleanup statistics
        """
        expired_count = self.cache.cleanup_expired()

        redis_cleaned = 0
        if self.enable_redis and self.redis_client:
            try:
                # Redis handles TTL automatically, but we can get stats
                redis_info = self.redis_client.info('stats')
                redis_cleaned = redis_info.get('expired_keys', 0)
            except Exception as e:
                log_error_with_context(
                    logger, e, "RedditCacheService", "redis_stats_unavailable",
                    level=logging.DEBUG
                )

        return {
            'in_memory_expired': expired_count,
            'redis_expired': redis_cleaned
        }

    def warm_cache_with_popular_posts(
        self,
        subreddit: str,
        posts: list[dict[str, Any]]
    ) -> None:
        """Warm the cache with popular posts to improve hit rates.

        Args:
            subreddit: Subreddit name
            posts: List of popular posts to pre-cache
        """
        for post in posts:
            post_id = post.get('post_id') or post.get('id')
            if post_id:
                self.set_post(post_id, post, ttl=600)  # 10 minutes

        # Cache the posts list too
        self.set_subreddit_posts(subreddit, posts, ttl=300)  # 5 minutes

        log_service_operation(
            logger, "RedditCacheService", "cache_warmed",
            subreddit=subreddit,
            posts_cached=len(posts),
            ttl_posts=600,
            ttl_list=300
        )

    def __enter__(self) -> 'RedditCacheService':
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - perform cleanup."""
        self.cleanup()
        if self.enable_redis and self.redis_client:
            with contextlib.suppress(Exception):
                self.redis_client.close()
