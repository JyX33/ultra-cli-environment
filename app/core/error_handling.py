# ABOUTME: Error handling utilities and decorators for consistent exception management
# ABOUTME: Provides retry logic, error context tracking, and standardized error handling patterns

from collections.abc import Callable
import functools
import logging
import time
from typing import Any, TypeVar

from sqlalchemy.exc import (
    DatabaseError,
    DataError,
    DisconnectionError,
    IntegrityError,
    OperationalError,
    SQLAlchemyError,
    StatementError,
)

from app.core.exceptions import (
    CacheConnectionError,
    CacheServiceError,
    DatabaseConnectionError,
    DatabaseQueryError,
    DataValidationError,
    RedditAgentError,
    RedditAPIError,
    RedditAuthenticationError,
    RedditNotFoundError,
    RedditPermissionError,
    RedditRateLimitError,
    ScrapingTimeoutError,
    StorageServiceError,
    SummarizerAPIError,
    SummarizerAuthenticationError,
    SummarizerRateLimitError,
    wrap_external_error,
)

logger = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable[..., Any])


def handle_exceptions(
    *,
    default_return: Any = None,
    log_errors: bool = True,
    re_raise: bool = True,
    error_context: dict[str, Any] | None = None
) -> Callable[[F], F]:
    """Decorator for standardized exception handling.

    Args:
        default_return: Value to return if exception occurs and re_raise is False
        log_errors: Whether to log caught exceptions
        re_raise: Whether to re-raise exceptions after handling
        error_context: Additional context to include in error logs

    Returns:
        Decorated function with exception handling
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_errors:
                    context = error_context or {}
                    context.update({
                        "function": func.__name__,
                        "args_count": len(args),
                        "kwargs_keys": list(kwargs.keys()),
                        "exception_type": type(e).__name__
                    })

                    if isinstance(e, RedditAgentError):
                        logger.error(f"Service error in {func.__name__}: {e}", extra={"context": context})
                    else:
                        logger.error(f"Unexpected error in {func.__name__}: {e}", extra={"context": context}, exc_info=True)

                if re_raise:
                    raise
                return default_return

        return wrapper  # type: ignore
    return decorator


def retry_on_failure(
    *,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[int, Exception], None] | None = None
) -> Callable[[F], F]:
    """Decorator for retry logic with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff_factor: Multiplier for delay on each retry
        exceptions: Tuple of exception types to retry on
        on_retry: Optional callback function called on each retry

    Returns:
        Decorated function with retry logic
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt < max_retries:
                        if on_retry:
                            on_retry(attempt + 1, e)

                        logger.debug(
                            f"Retry attempt {attempt + 1}/{max_retries} for {func.__name__} "
                            f"after {current_delay}s delay. Error: {e}"
                        )

                        time.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        logger.error(
                            f"Function {func.__name__} failed after {max_retries} retries. "
                            f"Final error: {e}"
                        )
                        raise

            # This should never be reached, but included for type safety
            if last_exception:
                raise last_exception

        return wrapper  # type: ignore
    return decorator


def reddit_error_handler(func: F) -> F:
    """Decorator for handling Reddit API specific errors.

    Converts PRAW exceptions to standardized Reddit service exceptions.
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_message = str(e).lower()

            # Map PRAW exceptions to our custom exceptions
            if "forbidden" in error_message or "private" in error_message:
                raise wrap_external_error(
                    e, RedditPermissionError,
                    "Access to Reddit resource is forbidden or private",
                    "REDDIT_PERMISSION_DENIED"
                ) from e
            elif "not found" in error_message or "404" in error_message:
                raise wrap_external_error(
                    e, RedditNotFoundError,
                    "Reddit resource not found",
                    "REDDIT_NOT_FOUND"
                ) from e
            elif "rate limit" in error_message or "429" in error_message:
                raise wrap_external_error(
                    e, RedditRateLimitError,
                    "Reddit API rate limit exceeded",
                    "REDDIT_RATE_LIMIT"
                ) from e
            elif "authentication" in error_message or "401" in error_message:
                raise wrap_external_error(
                    e, RedditAuthenticationError,
                    "Reddit API authentication failed",
                    "REDDIT_AUTH_FAILED"
                ) from e
            else:
                raise wrap_external_error(
                    e, RedditAPIError,
                    f"Reddit API error: {e!s}",
                    "REDDIT_API_ERROR"
                ) from e

    return wrapper  # type: ignore


def database_error_handler(func: F) -> F:
    """Decorator for handling database specific errors.

    Converts SQLAlchemy exceptions to standardized storage service exceptions
    with specific error type classification and detailed error context.
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except SQLAlchemyError as e:
            # Handle specific SQLAlchemy exception types
            if isinstance(e, IntegrityError):
                # Handle constraint violations, unique key violations, foreign key errors
                error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)

                if "UNIQUE constraint failed" in error_msg or "duplicate key" in error_msg.lower():
                    raise wrap_external_error(
                        e, DatabaseQueryError,
                        "Duplicate record detected - data already exists in database",
                        "DB_DUPLICATE_KEY_ERROR",
                        {"sql_error": error_msg, "operation": func.__name__}
                    )
                elif "FOREIGN KEY constraint failed" in error_msg or "foreign key" in error_msg.lower():
                    raise wrap_external_error(
                        e, DatabaseQueryError,
                        "Foreign key constraint violation - referenced record does not exist",
                        "DB_FOREIGN_KEY_ERROR",
                        {"sql_error": error_msg, "operation": func.__name__}
                    )
                elif "NOT NULL constraint failed" in error_msg or "not null" in error_msg.lower():
                    raise wrap_external_error(
                        e, DataValidationError,
                        "Required field is missing - null value in non-nullable column",
                        "DB_NOT_NULL_ERROR",
                        {"sql_error": error_msg, "operation": func.__name__}
                    )
                elif "CHECK constraint failed" in error_msg or "check constraint" in error_msg.lower():
                    raise wrap_external_error(
                        e, DataValidationError,
                        "Data validation failed - value does not meet database constraints",
                        "DB_CHECK_CONSTRAINT_ERROR",
                        {"sql_error": error_msg, "operation": func.__name__}
                    )
                else:
                    raise wrap_external_error(
                        e, DatabaseQueryError,
                        "Database integrity constraint violation",
                        "DB_INTEGRITY_ERROR",
                        {"sql_error": error_msg, "operation": func.__name__}
                    )

            elif isinstance(e, OperationalError):
                # Handle connection issues, timeouts, database unavailable
                error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)

                if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                    raise wrap_external_error(
                        e, DatabaseConnectionError,
                        "Database operation timed out - query took too long to execute",
                        "DB_TIMEOUT_ERROR",
                        {"sql_error": error_msg, "operation": func.__name__}
                    )
                elif "connection" in error_msg.lower() or "connect" in error_msg.lower():
                    raise wrap_external_error(
                        e, DatabaseConnectionError,
                        "Database connection failed - unable to connect to database server",
                        "DB_CONNECTION_ERROR",
                        {"sql_error": error_msg, "operation": func.__name__}
                    )
                elif "database is locked" in error_msg.lower() or "locked" in error_msg.lower():
                    raise wrap_external_error(
                        e, DatabaseConnectionError,
                        "Database is locked - concurrent access conflict",
                        "DB_LOCKED_ERROR",
                        {"sql_error": error_msg, "operation": func.__name__}
                    )
                elif "no such table" in error_msg.lower() or ("table" in error_msg.lower() and "not exist" in error_msg.lower()):
                    raise wrap_external_error(
                        e, DatabaseQueryError,
                        "Database table does not exist - possible migration issue",
                        "DB_TABLE_NOT_FOUND",
                        {"sql_error": error_msg, "operation": func.__name__}
                    )
                else:
                    raise wrap_external_error(
                        e, DatabaseConnectionError,
                        f"Database operational error: {error_msg}",
                        "DB_OPERATIONAL_ERROR",
                        {"sql_error": error_msg, "operation": func.__name__}
                    )

            elif isinstance(e, DataError):
                # Handle data type conversion errors, invalid data format
                error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
                raise wrap_external_error(
                    e, DataValidationError,
                    "Invalid data format - data type conversion failed",
                    "DB_DATA_TYPE_ERROR",
                    {"sql_error": error_msg, "operation": func.__name__}
                )

            elif isinstance(e, StatementError):
                # Handle SQL statement compilation errors, invalid SQL
                error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
                raise wrap_external_error(
                    e, DatabaseQueryError,
                    "SQL statement error - invalid or malformed query",
                    "DB_STATEMENT_ERROR",
                    {"sql_error": error_msg, "operation": func.__name__}
                )

            elif isinstance(e, DisconnectionError):
                # Handle database disconnection during operation
                error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
                raise wrap_external_error(
                    e, DatabaseConnectionError,
                    "Database connection lost during operation",
                    "DB_DISCONNECTION_ERROR",
                    {"sql_error": error_msg, "operation": func.__name__}
                )

            elif isinstance(e, DatabaseError):
                # Handle generic database errors
                error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
                raise wrap_external_error(
                    e, StorageServiceError,
                    f"Database error: {error_msg}",
                    "DB_GENERIC_ERROR",
                    {"sql_error": error_msg, "operation": func.__name__}
                )

            else:
                # Handle any other SQLAlchemy errors
                error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
                raise wrap_external_error(
                    e, StorageServiceError,
                    f"Unexpected database error: {error_msg}",
                    "DB_UNKNOWN_ERROR",
                    {"sql_error": error_msg, "operation": func.__name__, "exception_type": type(e).__name__}
                )

        except Exception as e:
            # Handle non-SQLAlchemy exceptions that might occur in database operations
            if "connection" in str(e).lower() or "connect" in str(e).lower():
                raise wrap_external_error(
                    e, DatabaseConnectionError,
                    "Database connection failed",
                    "DB_CONNECTION_FAILED",
                    {"error_message": str(e), "operation": func.__name__}
                )
            else:
                raise wrap_external_error(
                    e, StorageServiceError,
                    f"Database operation failed: {e!s}",
                    "DB_OPERATION_FAILED",
                    {"error_message": str(e), "operation": func.__name__}
                )

    return wrapper  # type: ignore


def cache_error_handler(func: F) -> F:
    """Decorator for handling cache service specific errors.

    Converts Redis and cache exceptions to standardized cache service exceptions.
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_message = str(e).lower()

            # Map cache exceptions to our custom exceptions
            if "connection" in error_message or "connect" in error_message:
                raise wrap_external_error(
                    e, CacheConnectionError,
                    "Cache connection failed",
                    "CACHE_CONNECTION_FAILED"
                )
            else:
                raise wrap_external_error(
                    e, CacheServiceError,
                    f"Cache operation failed: {e!s}",
                    "CACHE_OPERATION_FAILED"
                )

    return wrapper  # type: ignore


def openai_error_handler(func: F) -> F:
    """Decorator for handling OpenAI API specific errors.

    Converts OpenAI exceptions to standardized summarizer service exceptions.
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_message = str(e).lower()

            # Map OpenAI exceptions to our custom exceptions
            if "rate limit" in error_message or "429" in error_message:
                raise wrap_external_error(
                    e, SummarizerRateLimitError,
                    "OpenAI API rate limit exceeded",
                    "OPENAI_RATE_LIMIT"
                )
            elif "authentication" in error_message or "401" in error_message:
                raise wrap_external_error(
                    e, SummarizerAuthenticationError,
                    "OpenAI API authentication failed",
                    "OPENAI_AUTH_FAILED"
                )
            else:
                raise wrap_external_error(
                    e, SummarizerAPIError,
                    f"OpenAI API error: {e!s}",
                    "OPENAI_API_ERROR"
                )

    return wrapper  # type: ignore


def timeout_handler(timeout_seconds: float) -> Callable[[F], F]:
    """Decorator for handling operation timeouts.

    Args:
        timeout_seconds: Maximum time to allow for operation

    Returns:
        Decorated function with timeout handling
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            import signal

            def timeout_handler_signal(signum: int, frame: Any) -> None:
                raise ScrapingTimeoutError(
                    f"Operation {func.__name__} timed out after {timeout_seconds} seconds",
                    "OPERATION_TIMEOUT"
                )

            # Set up signal handler
            old_handler = signal.signal(signal.SIGALRM, timeout_handler_signal)
            signal.alarm(int(timeout_seconds))

            try:
                result = func(*args, **kwargs)
                signal.alarm(0)  # Cancel the alarm
                return result
            finally:
                signal.signal(signal.SIGALRM, old_handler)

        return wrapper  # type: ignore
    return decorator


def performance_monitor(
    threshold_ms: float | None = None,
    log_performance: bool = True
) -> Callable[[F], F]:
    """Decorator for monitoring function performance.

    Args:
        threshold_ms: Optional threshold in milliseconds to trigger warnings
        log_performance: Whether to log performance metrics

    Returns:
        Decorated function with performance monitoring
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                return result
            finally:
                end_time = time.time()
                duration_ms = (end_time - start_time) * 1000

                if log_performance:
                    logger.debug(f"Function {func.__name__} took {duration_ms:.2f}ms")

                if threshold_ms and duration_ms > threshold_ms:
                    logger.warning(
                        f"Function {func.__name__} exceeded performance threshold: "
                        f"{duration_ms:.2f}ms > {threshold_ms:.2f}ms"
                    )

                    # Optionally raise performance threshold error
                    # raise PerformanceThresholdError(
                    #     f"Performance threshold exceeded in {func.__name__}",
                    #     "PERFORMANCE_THRESHOLD_EXCEEDED",
                    #     {"duration_ms": duration_ms, "threshold_ms": threshold_ms}
                    # )

        return wrapper  # type: ignore
    return decorator


# Utility functions for error context
def create_service_context(
    service_name: str,
    operation: str,
    **additional_context: Any
) -> dict[str, Any]:
    """Create standardized service operation context.

    Args:
        service_name: Name of the service
        operation: Operation being performed
        **additional_context: Additional context key-value pairs

    Returns:
        Standardized context dictionary
    """
    context = {
        "service": service_name,
        "operation": operation,
        "timestamp": time.time()
    }
    context.update(additional_context)
    return context


def log_service_error(
    error: Exception,
    service_name: str,
    operation: str,
    **context: Any
) -> None:
    """Log service error with standardized format.

    Args:
        error: The exception that occurred
        service_name: Name of the service where error occurred
        operation: Operation that failed
        **context: Additional context for logging
    """
    error_context = create_service_context(service_name, operation, **context)

    if isinstance(error, RedditAgentError):
        logger.error(
            f"Service error in {service_name}.{operation}: {error}",
            extra={"context": error_context}
        )
    else:
        logger.error(
            f"Unexpected error in {service_name}.{operation}: {error}",
            extra={"context": error_context},
            exc_info=True
        )
