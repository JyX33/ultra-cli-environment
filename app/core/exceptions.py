# ABOUTME: Custom exception hierarchy for different service types with detailed error information
# ABOUTME: Provides structured error handling and context for debugging and error reporting

from typing import Any


class RedditAgentError(Exception):
    """Base exception for all Reddit Agent errors."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
        original_error: Exception | None = None
    ) -> None:
        """Initialize base exception with context.

        Args:
            message: Human-readable error message
            error_code: Machine-readable error code for programmatic handling
            context: Additional context information for debugging
            original_error: Original exception that caused this error
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}
        self.original_error = original_error

    def __str__(self) -> str:
        """Return string representation of error."""
        parts = [self.message]
        if self.error_code:
            parts.append(f"(Code: {self.error_code})")
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            parts.append(f"[{context_str}]")
        return " ".join(parts)


# Configuration Errors
class ConfigurationError(RedditAgentError):
    """Raised when configuration is invalid or missing."""
    pass


class MissingConfigurationError(ConfigurationError):
    """Raised when required configuration values are missing."""
    pass


class InvalidConfigurationError(ConfigurationError):
    """Raised when configuration values are invalid."""
    pass


# Reddit Service Errors
class RedditServiceError(RedditAgentError):
    """Base exception for Reddit API service errors."""
    pass


class RedditAuthenticationError(RedditServiceError):
    """Raised when Reddit API authentication fails."""
    pass


class RedditRateLimitError(RedditServiceError):
    """Raised when Reddit API rate limit is exceeded."""
    pass


class RedditPermissionError(RedditServiceError):
    """Raised when Reddit API access is forbidden (private subreddit, etc.)."""
    pass


class RedditNotFoundError(RedditServiceError):
    """Raised when Reddit resource (subreddit, post) is not found."""
    pass


class RedditAPIError(RedditServiceError):
    """Raised for general Reddit API errors."""
    pass


# Storage Service Errors
class StorageServiceError(RedditAgentError):
    """Base exception for storage service errors."""
    pass


class DatabaseConnectionError(StorageServiceError):
    """Raised when database connection fails."""
    pass


class DatabaseQueryError(StorageServiceError):
    """Raised when database query execution fails."""
    pass


class DataValidationError(StorageServiceError):
    """Raised when data validation fails before storage."""
    pass


class DataIntegrityError(StorageServiceError):
    """Raised when data integrity constraints are violated."""
    pass


# Scraper Service Errors
class ScraperServiceError(RedditAgentError):
    """Base exception for web scraping service errors."""
    pass


class URLValidationError(ScraperServiceError):
    """Raised when URL validation fails."""
    pass


class InvalidURLFormatError(URLValidationError):
    """Raised when URL format is invalid or malformed."""
    pass


class UnsupportedSchemeError(URLValidationError):
    """Raised when URL uses an unsupported scheme (not HTTP/HTTPS)."""
    pass


class RestrictedNetworkError(URLValidationError):
    """Raised when URL targets restricted internal network addresses."""
    pass


class RestrictedPortError(URLValidationError):
    """Raised when URL uses restricted or dangerous ports."""
    pass


class SecurityViolationError(URLValidationError):
    """Raised when URL contains patterns that violate security policies."""
    pass


class ScrapingTimeoutError(ScraperServiceError):
    """Raised when web scraping request times out."""
    pass


class ScrapingPermissionError(ScraperServiceError):
    """Raised when web scraping is blocked or forbidden."""
    pass


class ScrapingParseError(ScraperServiceError):
    """Raised when scraped content cannot be parsed."""
    pass


# Summarizer Service Errors
class SummarizerServiceError(RedditAgentError):
    """Base exception for AI summarization service errors."""
    pass


class SummarizerAuthenticationError(SummarizerServiceError):
    """Raised when OpenAI API authentication fails."""
    pass


class SummarizerRateLimitError(SummarizerServiceError):
    """Raised when OpenAI API rate limit is exceeded."""
    pass


class SummarizerContentError(SummarizerServiceError):
    """Raised when content violates OpenAI policies or is too long."""
    pass


class SummarizerAPIError(SummarizerServiceError):
    """Raised for general OpenAI API errors."""
    pass


# Cache Service Errors
class CacheServiceError(RedditAgentError):
    """Base exception for cache service errors."""
    pass


class CacheConnectionError(CacheServiceError):
    """Raised when cache connection (Redis) fails."""
    pass


class CacheOperationError(CacheServiceError):
    """Raised when cache operation fails."""
    pass


# Performance and Monitoring Errors
class PerformanceError(RedditAgentError):
    """Base exception for performance monitoring errors."""
    pass


class PerformanceThresholdError(PerformanceError):
    """Raised when performance thresholds are exceeded."""
    pass


# Rate Limiting Errors
class RateLimitExceededError(RedditAgentError):
    """Raised when rate limits are exceeded for external services."""
    pass


# Error handling utilities
def wrap_external_error(
    original_error: Exception,
    service_error_class: type[RedditAgentError],
    message: str,
    error_code: str | None = None,
    context: dict[str, Any] | None = None
) -> RedditAgentError:
    """Wrap external exceptions in service-specific error types.

    Args:
        original_error: The original exception to wrap
        service_error_class: The service-specific error class to use
        message: Human-readable error message
        error_code: Machine-readable error code
        context: Additional context for debugging

    Returns:
        Service-specific error with original error context
    """
    enhanced_context = context or {}
    enhanced_context.update({
        "original_error_type": type(original_error).__name__,
        "original_error_message": str(original_error)
    })

    return service_error_class(
        message=message,
        error_code=error_code,
        context=enhanced_context,
        original_error=original_error
    )


def create_error_context(**kwargs: Any) -> dict[str, Any]:
    """Create error context dictionary with non-None values.

    Args:
        **kwargs: Context key-value pairs

    Returns:
        Dictionary with non-None values only
    """
    return {k: v for k, v in kwargs.items() if v is not None}
