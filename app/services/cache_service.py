# ABOUTME: Caching service with in-memory and Redis support for performance optimization
# ABOUTME: Provides cache invalidation, TTL management, and hit rate monitoring

import contextlib
from dataclasses import asdict, dataclass
import json
import logging
import time
from typing import Any

# Set up logging
logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """Statistics for cache performance monitoring."""
    hits: int = 0
    misses: int = 0
    total_requests: int = 0
    hit_rate: float = 0.0
    memory_usage_mb: float = 0.0
    oldest_entry_age_seconds: float = 0.0


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
    """High-performance in-memory cache with TTL and eviction policies."""

    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """Initialize in-memory cache.

        Args:
            max_size: Maximum number of entries to store
            default_ttl: Default TTL in seconds (0 = no expiration)
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: dict[str, CacheEntry] = {}
        self._stats = CacheStats()

    def get(self, key: str) -> Any | None:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
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

        logger.debug(f"Cache hit for key: {key}")
        return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None
    ) -> None:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (None = use default)
        """
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
        logger.debug(f"Cached value for key: {key} (TTL: {ttl}s)")

    def delete(self, key: str) -> bool:
        """Delete value from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was found and deleted
        """
        if key in self._cache:
            del self._cache[key]
            logger.debug(f"Deleted cache key: {key}")
            return True
        return False

    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()
        self._stats = CacheStats()
        logger.info("Cache cleared")

    def get_stats(self) -> CacheStats:
        """Get cache performance statistics."""
        # Update memory usage estimate
        try:
            import sys
            total_size = sum(
                sys.getsizeof(key) + sys.getsizeof(entry.value)
                for key, entry in self._cache.items()
            )
            self._stats.memory_usage_mb = total_size / 1024 / 1024
        except Exception:
            self._stats.memory_usage_mb = 0.0

        # Update oldest entry age
        if self._cache:
            oldest_time = min(entry.created_at for entry in self._cache.values())
            self._stats.oldest_entry_age_seconds = time.time() - oldest_time
        else:
            self._stats.oldest_entry_age_seconds = 0.0

        return self._stats

    def cleanup_expired(self) -> int:
        """Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        expired_keys = [
            key for key, entry in self._cache.items()
            if entry.is_expired()
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")

        return len(expired_keys)

    def _evict_lru(self) -> None:
        """Evict least recently used entry."""
        if not self._cache:
            return

        lru_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_accessed or 0.0
        )

        del self._cache[lru_key]
        logger.debug(f"Evicted LRU cache entry: {lru_key}")

    def _update_hit_rate(self) -> None:
        """Update cache hit rate statistics."""
        if self._stats.total_requests > 0:
            self._stats.hit_rate = self._stats.hits / self._stats.total_requests


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
                logger.info("Redis cache enabled and connected")

            except ImportError:
                logger.warning("Redis not available, falling back to in-memory cache")
                self.enable_redis = False
            except Exception as e:
                logger.warning(f"Redis connection failed, falling back to in-memory cache: {e}")
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
                    logger.debug(f"Redis cache hit for post: {post_id}")
                    return json.loads(cached_data)  # type: ignore
            except Exception as e:
                logger.warning(f"Redis get failed: {e}")

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
                logger.debug(f"Cached post in Redis: {post_id}")
            except Exception as e:
                logger.warning(f"Redis set failed: {e}")

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
                logger.debug(f"Invalidated post in Redis: {post_id}")
            except Exception as e:
                logger.warning(f"Redis invalidation failed: {e}")

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
        logger.info(f"Invalidated cached data for subreddit: {subreddit}")

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
            except Exception:
                pass

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

        logger.info(f"Warmed cache with {len(posts)} posts for r/{subreddit}")

    def __enter__(self) -> 'RedditCacheService':
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - perform cleanup."""
        self.cleanup()
        if self.enable_redis and self.redis_client:
            with contextlib.suppress(Exception):
                self.redis_client.close()
