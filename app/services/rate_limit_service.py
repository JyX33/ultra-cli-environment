# ABOUTME: Rate limiting service using token bucket algorithm for external API calls
# ABOUTME: Provides thread-safe rate limiting with configurable burst allowances and monitoring

import asyncio
from dataclasses import dataclass, field
import threading
import time
from typing import Any, ClassVar, Literal

from app.core.config import config
from app.core.exceptions import RateLimitExceededError
from app.core.structured_logging import get_logger, log_service_operation

logger = get_logger(__name__)

ServiceName = Literal["openai", "reddit", "scraper"]


@dataclass
class TokenBucket:
    """Thread-safe token bucket implementation for rate limiting."""

    capacity: float
    refill_rate: float  # tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False)
    lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self) -> None:
        """Initialize token bucket state."""
        self.tokens = self.capacity
        self.last_refill = time.time()

    def consume(self, tokens: float = 1.0) -> bool:
        """
        Attempt to consume tokens from the bucket.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens were successfully consumed, False otherwise
        """
        with self.lock:
            now = time.time()

            # Refill tokens based on elapsed time
            elapsed = now - self.last_refill
            new_tokens = elapsed * self.refill_rate
            self.tokens = min(self.capacity, self.tokens + new_tokens)
            self.last_refill = now

            # Check if we can consume the requested tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            return False

    def get_status(self) -> dict[str, Any]:
        """Get current bucket status."""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_refill
            current_tokens = min(self.capacity, self.tokens + (elapsed * self.refill_rate))

            return {
                "current_tokens": current_tokens,
                "capacity": self.capacity,
                "refill_rate": self.refill_rate,
                "utilization": (self.capacity - current_tokens) / self.capacity,
                "time_to_full": max(0, (self.capacity - current_tokens) / self.refill_rate),
            }


@dataclass
class RateLimitStats:
    """Statistics for rate limiting operations."""
    total_requests: int = 0
    allowed_requests: int = 0
    blocked_requests: int = 0
    total_tokens_consumed: float = 0.0
    last_reset: float = field(default_factory=time.time)

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_requests == 0:
            return 100.0
        return (self.allowed_requests / self.total_requests) * 100.0

    @property
    def block_rate(self) -> float:
        """Calculate block rate percentage."""
        if self.total_requests == 0:
            return 0.0
        return (self.blocked_requests / self.total_requests) * 100.0

    def reset(self) -> None:
        """Reset statistics."""
        self.total_requests = 0
        self.allowed_requests = 0
        self.blocked_requests = 0
        self.total_tokens_consumed = 0.0
        self.last_reset = time.time()


class RateLimitService:
    """
    Service for managing rate limits across different external APIs.

    Uses token bucket algorithm to allow for bursty traffic while maintaining
    overall rate limits. Thread-safe and configurable per service.
    """

    # Global instance tracking
    _instances: ClassVar[dict[str, "RateLimitService"]] = {}
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, service_name: ServiceName) -> None:
        """
        Initialize rate limiting for a specific service.

        Args:
            service_name: Name of the service to rate limit
        """
        self.service_name = service_name
        self.config = config.get_rate_limit_config()
        self.enabled = self.config.enabled

        # Initialize token buckets based on service type
        if service_name == "openai":
            # OpenAI has both request and token limits
            rpm_capacity = self.config.openai_rpm * self.config.burst_allowance
            self.request_bucket = TokenBucket(
                capacity=rpm_capacity,
                refill_rate=self.config.openai_rpm / 60.0  # Convert RPM to RPS
            )

            tpm_capacity = self.config.openai_tpm * self.config.burst_allowance
            self.token_bucket: TokenBucket | None = TokenBucket(
                capacity=tpm_capacity,
                refill_rate=self.config.openai_tpm / 60.0  # Convert TPM to TPS
            )
        elif service_name == "reddit":
            rpm_capacity = self.config.reddit_rpm * self.config.burst_allowance
            self.request_bucket = TokenBucket(
                capacity=rpm_capacity,
                refill_rate=self.config.reddit_rpm / 60.0
            )
            self.token_bucket = None  # Reddit doesn't have token limits
        elif service_name == "scraper":
            rpm_capacity = self.config.scraper_rpm * self.config.burst_allowance
            self.request_bucket = TokenBucket(
                capacity=rpm_capacity,
                refill_rate=self.config.scraper_rpm / 60.0
            )
            self.token_bucket = None  # Web scraping doesn't have token limits
        else:
            raise ValueError(f"Unknown service name: {service_name}")

        # Initialize statistics
        self.stats = RateLimitStats()
        self.stats_lock = threading.Lock()

        log_service_operation(
            logger, "RateLimitService", "initialize",
            service=service_name, enabled=self.enabled,
            request_capacity=self.request_bucket.capacity,
            token_capacity=self.token_bucket.capacity if self.token_bucket else None
        )

    def check_rate_limit(self, tokens: float = 1.0, request_tokens: int = 1) -> None:
        """
        Check if a request can proceed within rate limits.

        Args:
            tokens: Number of tokens to consume (for OpenAI token limits)
            request_tokens: Number of request tokens to consume (usually 1)

        Raises:
            RateLimitExceededError: If rate limit would be exceeded
        """
        if not self.enabled:
            # Rate limiting disabled, allow all requests
            with self.stats_lock:
                self.stats.total_requests += 1
                self.stats.allowed_requests += 1
            return

        with self.stats_lock:
            self.stats.total_requests += 1

        # Check request rate limit
        if not self.request_bucket.consume(request_tokens):
            with self.stats_lock:
                self.stats.blocked_requests += 1

            request_status = self.request_bucket.get_status()
            log_service_operation(
                logger, "RateLimitService", "rate_limit_exceeded",
                service=self.service_name, limit_type="requests",
                current_tokens=request_status["current_tokens"],
                time_to_refill=request_status["time_to_full"]
            )

            raise RateLimitExceededError(
                f"Request rate limit exceeded for {self.service_name} service",
                error_code="RATE_LIMIT_REQUESTS_EXCEEDED",
                context={
                    "service": self.service_name,
                    "limit_type": "requests",
                    "requested_tokens": request_tokens,
                    "available_tokens": request_status["current_tokens"],
                    "time_to_refill_seconds": request_status["time_to_full"],
                    "rate_limit_rpm": getattr(self.config, f"{self.service_name}_rpm")
                }
            )

        # Check token rate limit (OpenAI only)
        if self.token_bucket and not self.token_bucket.consume(tokens):
            # Refund the request token since token limit failed
            self.request_bucket.tokens += request_tokens

            with self.stats_lock:
                self.stats.blocked_requests += 1

            token_status = self.token_bucket.get_status()
            log_service_operation(
                logger, "RateLimitService", "rate_limit_exceeded",
                service=self.service_name, limit_type="tokens",
                current_tokens=token_status["current_tokens"],
                time_to_refill=token_status["time_to_full"]
            )

            raise RateLimitExceededError(
                f"Token rate limit exceeded for {self.service_name} service",
                error_code="RATE_LIMIT_TOKENS_EXCEEDED",
                context={
                    "service": self.service_name,
                    "limit_type": "tokens",
                    "requested_tokens": tokens,
                    "available_tokens": token_status["current_tokens"],
                    "time_to_refill_seconds": token_status["time_to_full"],
                    "rate_limit_tpm": self.config.openai_tpm
                }
            )

        # Successfully passed rate limits
        with self.stats_lock:
            self.stats.allowed_requests += 1
            self.stats.total_tokens_consumed += tokens

        log_service_operation(
            logger, "RateLimitService", "rate_limit_check_passed",
            service=self.service_name, tokens_consumed=tokens,
            request_tokens_consumed=request_tokens
        )

    def get_status(self) -> dict[str, Any]:
        """Get comprehensive status of rate limiting for this service."""
        status = {
            "service": self.service_name,
            "enabled": self.enabled,
            "request_bucket": self.request_bucket.get_status(),
        }

        if self.token_bucket:
            status["token_bucket"] = self.token_bucket.get_status()

        with self.stats_lock:
            status["statistics"] = {
                "total_requests": self.stats.total_requests,
                "allowed_requests": self.stats.allowed_requests,
                "blocked_requests": self.stats.blocked_requests,
                "success_rate": self.stats.success_rate,
                "block_rate": self.stats.block_rate,
                "total_tokens_consumed": self.stats.total_tokens_consumed,
                "stats_age_seconds": time.time() - self.stats.last_reset,
            }

        return status

    def reset_stats(self) -> None:
        """Reset rate limiting statistics."""
        with self.stats_lock:
            self.stats.reset()

        log_service_operation(
            logger, "RateLimitService", "stats_reset",
            service=self.service_name
        )

    async def wait_for_availability(self, tokens: float = 1.0, request_tokens: int = 1, timeout: float = 30.0) -> None:
        """
        Wait until rate limit allows the request to proceed.

        Args:
            tokens: Number of tokens needed
            request_tokens: Number of request tokens needed
            timeout: Maximum time to wait in seconds

        Raises:
            RateLimitExceededError: If timeout is reached
            asyncio.TimeoutError: If timeout is reached
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                self.check_rate_limit(tokens, request_tokens)
                return  # Success, we can proceed
            except RateLimitExceededError as e:
                # Calculate wait time based on rate limit info
                context = getattr(e, 'context', {})
                wait_time = min(
                    context.get('time_to_refill_seconds', 1.0),
                    5.0  # Maximum wait time between retries
                )

                log_service_operation(
                    logger, "RateLimitService", "waiting_for_availability",
                    service=self.service_name, wait_time=wait_time,
                    elapsed_time=time.time() - start_time
                )

                await asyncio.sleep(wait_time)

        # Timeout reached
        raise RateLimitExceededError(
            f"Rate limit wait timeout exceeded for {self.service_name} service",
            error_code="RATE_LIMIT_WAIT_TIMEOUT",
            context={
                "service": self.service_name,
                "timeout_seconds": timeout,
                "requested_tokens": tokens,
                "requested_request_tokens": request_tokens
            }
        )


def get_rate_limiter(service_name: ServiceName) -> RateLimitService:
    """
    Get or create a rate limiter for the specified service.

    Args:
        service_name: Name of the service to get rate limiter for

    Returns:
        RateLimitService instance for the service
    """
    with RateLimitService._lock:
        if service_name not in RateLimitService._instances:
            RateLimitService._instances[service_name] = RateLimitService(service_name)
            logger.info(f"Created rate limiter for service: {service_name}")

        return RateLimitService._instances[service_name]


def get_all_rate_limit_status() -> dict[str, Any]:
    """
    Get status for all active rate limiters.

    Returns:
        Dictionary with status for each service
    """
    status = {}

    with RateLimitService._lock:
        for service_name, limiter in RateLimitService._instances.items():
            status[service_name] = limiter.get_status()

    return {
        "rate_limiters": status,
        "global_config": {
            "enabled": config.get_rate_limit_config().enabled,
            "burst_allowance": config.get_rate_limit_config().burst_allowance,
        }
    }


def reset_all_rate_limit_stats() -> None:
    """Reset statistics for all rate limiters."""
    with RateLimitService._lock:
        for limiter in RateLimitService._instances.values():
            limiter.reset_stats()

    logger.info("Reset statistics for all rate limiters")


# Convenience decorators for common use cases
def rate_limited(service_name: ServiceName, tokens: float = 1.0) -> Any:
    """
    Decorator to add rate limiting to a function.

    Args:
        service_name: Name of the service to rate limit
        tokens: Number of tokens to consume
    """
    def decorator(func: Any) -> Any:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            limiter = get_rate_limiter(service_name)
            limiter.check_rate_limit(tokens=tokens)
            return func(*args, **kwargs)
        return wrapper
    return decorator
