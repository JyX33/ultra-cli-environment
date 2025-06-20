# ABOUTME: Structured logging utilities with correlation IDs and sanitized data for better debugging
# ABOUTME: Provides JSON logging, correlation tracking, and sensitive data sanitization

from contextvars import ContextVar
import json
import logging
import logging.config
import re
from typing import Any, ClassVar
import uuid

from app.core.config import config

# Context variable for correlation ID tracking across async operations
correlation_id: ContextVar[str | None] = ContextVar('correlation_id', default=None)


class SensitiveDataFilter:
    """Filter to sanitize sensitive data from log records."""

    SENSITIVE_KEYS: ClassVar[set[str]] = {
        'password', 'passwd', 'secret', 'token', 'key', 'api_key',
        'client_secret', 'auth', 'authorization', 'credential',
        'private_key', 'oauth', 'session_id', 'cookie'
    }

    PARTIAL_REDACTION_KEYS: ClassVar[set[str]] = {
        'client_id', 'user_id', 'username', 'email'
    }

    @staticmethod
    def sanitize_dict(data: dict[str, Any]) -> Any:
        """Recursively sanitize sensitive data from dictionary.

        Args:
            data: Dictionary to sanitize

        Returns:
            Dictionary with sensitive values redacted, or original data if not a dict
        """
        if not isinstance(data, dict):
            return data  # type: ignore[unreachable]

        sanitized: dict[str, Any] = {}

        for key, value in data.items():
            key_lower = key.lower()

            if isinstance(value, dict):
                sanitized[key] = SensitiveDataFilter.sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    SensitiveDataFilter.sanitize_dict(item) if isinstance(item, dict) else item
                    for item in value
                ]
            elif any(sensitive in key_lower for sensitive in SensitiveDataFilter.SENSITIVE_KEYS):
                sanitized[key] = "***REDACTED***"
            elif any(partial in key_lower for partial in SensitiveDataFilter.PARTIAL_REDACTION_KEYS):
                # Show only first few characters for debugging purposes
                if isinstance(value, str) and len(value) > 8:
                    sanitized[key] = value[:4] + "***" + value[-2:]
                else:
                    sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = value

        return sanitized

    @staticmethod
    def sanitize_string(text: str) -> str:
        """Sanitize sensitive data from string content.

        Args:
            text: String to sanitize

        Returns:
            String with potential sensitive data patterns redacted
        """

        # Pattern for common secrets (API keys, tokens, etc.)
        string_patterns = [
            (r'sk-[a-zA-Z0-9]{32,}', 'sk-***REDACTED***'),  # OpenAI API keys
            (r'Bearer\s+[a-zA-Z0-9._-]+', 'Bearer ***REDACTED***'),  # Bearer tokens
            (r'Basic\s+[a-zA-Z0-9+/=]+', 'Basic ***REDACTED***'),  # Basic auth
        ]

        sanitized = text

        # Apply string replacements
        for pattern, replacement in string_patterns:
            sanitized = re.sub(pattern, replacement, sanitized)

        # Apply callable replacements for long tokens
        def replace_long_tokens(match: re.Match[str]) -> str:
            token = match.group(0)
            if len(token) > 20:
                return token[:8] + '***REDACTED***'
            return token

        sanitized = re.sub(r'[a-zA-Z0-9]{32,}', replace_long_tokens, sanitized)

        return sanitized

    @staticmethod
    def sanitize_url(url: str) -> str:
        """Sanitize URLs to remove potentially sensitive query parameters.

        Args:
            url: URL to sanitize

        Returns:
            URL with sensitive query parameters redacted
        """
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

        try:
            parsed = urlparse(url)

            # If no query parameters, return as-is with domain only for security
            if not parsed.query:
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

            # Parse query parameters
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            sanitized_params = {}

            # Sensitive parameter names to redact
            sensitive_params = {
                'api_key', 'apikey', 'key', 'token', 'access_token', 'refresh_token',
                'secret', 'client_secret', 'password', 'pwd', 'auth', 'authorization',
                'credential', 'session', 'session_id', 'sessionid', 'oauth', 'bearer'
            }

            for param_name, param_values in query_params.items():
                param_lower = param_name.lower()

                # Check if parameter name contains sensitive keywords
                if any(sensitive in param_lower for sensitive in sensitive_params):
                    sanitized_params[param_name] = ['***REDACTED***']
                else:
                    # Still sanitize values that look like tokens/keys
                    sanitized_values = []
                    for value in param_values:
                        if isinstance(value, str) and len(value) > 20 and re.match(r'^[a-zA-Z0-9._-]+$', value):
                            sanitized_values.append(value[:4] + '***REDACTED***')
                        else:
                            sanitized_values.append(value)
                    sanitized_params[param_name] = sanitized_values

            # Reconstruct URL with sanitized parameters
            sanitized_query = urlencode(sanitized_params, doseq=True)
            sanitized_parsed = parsed._replace(query=sanitized_query)

            return urlunparse(sanitized_parsed)

        except Exception:
            # If URL parsing fails, return domain only for safety
            try:
                parsed = urlparse(url)
                return f"{parsed.scheme}://{parsed.netloc}/***PATH_REDACTED***"
            except Exception:
                return "***URL_REDACTED***"


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON.

        Args:
            record: Log record to format

        Returns:
            JSON formatted log string
        """
        # Base log entry
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add correlation ID if available
        current_correlation_id = correlation_id.get()
        if current_correlation_id:
            log_entry["correlation_id"] = current_correlation_id

        # Add exception information if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info)
            }

        # Add extra context if present
        if hasattr(record, 'context') and record.context:
            log_entry["context"] = SensitiveDataFilter.sanitize_dict(record.context)

        # Add any other extra fields
        for key, value in record.__dict__.items():
            if key not in {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
                'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                'thread', 'threadName', 'processName', 'process', 'message',
                'context'
            }:
                log_entry[key] = value

        # Sanitize the entire log entry
        log_entry = SensitiveDataFilter.sanitize_dict(log_entry)

        return json.dumps(log_entry, default=str, ensure_ascii=False)


class CorrelationFilter(logging.Filter):
    """Filter to add correlation ID to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation ID to log record.

        Args:
            record: Log record to modify

        Returns:
            True to allow the record to be processed
        """
        current_correlation_id = correlation_id.get()
        if current_correlation_id:
            record.correlation_id = current_correlation_id
        return True


def generate_correlation_id() -> str:
    """Generate a new correlation ID.

    Returns:
        UUID-based correlation ID
    """
    return str(uuid.uuid4())


def set_correlation_id(cid: str | None = None) -> str:
    """Set correlation ID for current context.

    Args:
        cid: Correlation ID to set, or None to generate new one

    Returns:
        The set correlation ID
    """
    if cid is None:
        cid = generate_correlation_id()
    correlation_id.set(cid)
    return cid


def get_correlation_id() -> str | None:
    """Get current correlation ID.

    Returns:
        Current correlation ID or None if not set
    """
    return correlation_id.get()


def clear_correlation_id() -> None:
    """Clear correlation ID from current context."""
    correlation_id.set(None)


def setup_structured_logging() -> None:
    """Configure structured logging based on application configuration."""

    # Determine if structured logging is enabled
    use_structured = config.ENABLE_STRUCTURED_LOGGING
    log_level = config.LOG_LEVEL

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    # Clear any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level, logging.INFO))

    if use_structured:
        # Use structured JSON formatter
        structured_formatter = StructuredFormatter()
        console_handler.setFormatter(structured_formatter)

        # Add correlation filter
        correlation_filter = CorrelationFilter()
        console_handler.addFilter(correlation_filter)
    else:
        # Use standard formatter
        standard_formatter = logging.Formatter(config.LOG_FORMAT)
        console_handler.setFormatter(standard_formatter)

    root_logger.addHandler(console_handler)

    # Configure specific logger levels for debugging
    if log_level == "DEBUG":
        logging.getLogger("app.utils.relevance").setLevel(logging.DEBUG)
        logging.getLogger("app.services.reddit_service").setLevel(logging.DEBUG)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with proper configuration.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Add correlation filter if structured logging is enabled
    if config.ENABLE_STRUCTURED_LOGGING:
        correlation_filter = CorrelationFilter()
        if not any(isinstance(f, CorrelationFilter) for f in logger.filters):
            logger.addFilter(correlation_filter)

    return logger


def log_service_operation(
    logger: logging.Logger,
    service_name: str,
    operation: str,
    level: int = logging.INFO,
    **context: Any
) -> None:
    """Log a service operation with structured context.

    Args:
        logger: Logger instance to use
        service_name: Name of the service
        operation: Operation being performed
        level: Log level
        **context: Additional context to include
    """
    message = f"{service_name}.{operation}"

    operation_context = {
        "service": service_name,
        "operation": operation,
        **context
    }

    logger.log(level, message, extra={"context": operation_context})


def log_performance_metric(
    logger: logging.Logger,
    operation: str,
    duration_ms: float,
    **context: Any
) -> None:
    """Log performance metrics with structured data.

    Args:
        logger: Logger instance to use
        operation: Operation that was measured
        duration_ms: Duration in milliseconds
        **context: Additional context to include
    """
    performance_context = {
        "operation": operation,
        "duration_ms": duration_ms,
        "performance_metric": True,
        **context
    }

    logger.info(f"Performance: {operation} took {duration_ms:.2f}ms", extra={"context": performance_context})


def log_error_with_context(
    logger: logging.Logger,
    error: Exception,
    service_name: str,
    operation: str,
    **context: Any
) -> None:
    """Log an error with full context and correlation tracking.

    Args:
        logger: Logger instance to use
        error: Exception that occurred
        service_name: Name of the service where error occurred
        operation: Operation that failed
        **context: Additional context to include
    """
    error_context = {
        "service": service_name,
        "operation": operation,
        "error_type": type(error).__name__,
        "error_message": str(error),
        **context
    }

    logger.error(
        f"Error in {service_name}.{operation}: {error}",
        extra={"context": error_context},
        exc_info=True
    )


def log_with_sanitized_url(
    logger: logging.Logger,
    level: int,
    message: str,
    url: str,
    **context: Any
) -> None:
    """Log a message with a sanitized URL to prevent sensitive data exposure.

    Args:
        logger: Logger instance to use
        level: Log level (logging.DEBUG, logging.INFO, etc.)
        message: Base log message
        url: URL to sanitize and include in context
        **context: Additional context to include
    """
    sanitized_url = SensitiveDataFilter.sanitize_url(url)

    # Replace {url} placeholder in message with sanitized URL
    safe_message = message.format(url=sanitized_url) if '{url}' in message else message

    url_context = {
        "url": sanitized_url,
        "url_domain": sanitized_url.split('/')[2] if '//' in sanitized_url else "unknown",
        **context
    }

    logger.log(level, safe_message, extra={"context": url_context})
