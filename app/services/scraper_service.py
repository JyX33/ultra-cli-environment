# ABOUTME: Scrapes article text from URLs with security validation to prevent SSRF attacks
# ABOUTME: Extracts content from paragraph tags while blocking malicious URLs

import logging
import time

from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import HTTPError, RequestException, Timeout

from app.core.config import config
from app.core.exceptions import RateLimitExceededError
from app.core.structured_logging import get_logger, log_with_sanitized_url
from app.services.rate_limit_service import get_rate_limiter
from app.utils.url_validator import URLValidationError, validate_url_detailed

# Set up structured logging
logger = get_logger(__name__)

# Configure robust HTTP session with proper headers and connection pooling
class ScraperSession:
    """Configured HTTP session for web scraping with security and performance optimizations."""

    def __init__(self) -> None:
        """Initialize scraper session with robust configuration."""
        # Get scraper configuration
        self.config = config.get_scraper_config()
        self.session = requests.Session()

        # Initialize rate limiter for web scraping requests
        self.rate_limiter = get_rate_limiter("scraper")

        # Set realistic User-Agent header to avoid blocking (prioritize config, fallback to default)
        user_agent = (
            self.config.user_agent if self.config.user_agent != "AI Reddit News Agent/1.0 (Educational Research)"
            else (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
        )

        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept': (
                'text/html,application/xhtml+xml,application/xml;q=0.9,'
                'image/webp,image/apng,*/*;q=0.8'
            ),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',  # Do Not Track
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })

        # Configure connection pooling for better performance
        adapter = HTTPAdapter(
            pool_connections=10,  # Number of connection pools
            pool_maxsize=20,      # Max connections per pool
            max_retries=0,        # Disable automatic retries (we'll handle manually)
            pool_block=False      # Don't block when pool is full
        )

        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        logger.debug(
            f"Initialized scraper session with config: timeout={self.config.timeout}s, "
            f"max_retries={self.config.max_retries}, retry_delay={self.config.retry_delay}s, "
            f"backoff_factor={self.config.backoff_factor}, "
            f"rate_limiting_enabled={self.rate_limiter.enabled}"
        )

    def get_with_retry(self, url: str, timeout: int | None = None) -> requests.Response:
        """Make GET request with configured session and retry logic.

        Args:
            url: URL to request
            timeout: Request timeout in seconds (uses config default if None)

        Returns:
            HTTP response object

        Raises:
            requests.RequestException: If request fails after all retries
        """
        if timeout is None:
            timeout = self.config.timeout

        last_exception = None
        current_delay = self.config.retry_delay

        # Define which exceptions we should retry on
        retryable_exceptions = (
            Timeout,           # Request timeouts
            RequestsConnectionError,   # Connection issues
            HTTPError,         # HTTP 5xx errors (server errors)
        )

        for attempt in range(self.config.max_retries + 1):
            try:
                # Check rate limits before making request
                try:
                    self.rate_limiter.check_rate_limit(tokens=1.0, request_tokens=1)
                    logger.debug("Rate limit check passed for scraping request")
                except RateLimitExceededError as e:
                    logger.warning(
                        f"Rate limit exceeded for scraping: {e}",
                        extra={"attempt": attempt + 1, "rate_limit_error": str(e)}
                    )
                    # If we have retries left, wait and try again
                    if attempt < self.config.max_retries:
                        delay = self.config.retry_delay * (self.config.backoff_factor ** attempt)
                        logger.info(f"Waiting {delay}s before retry due to rate limit")
                        time.sleep(delay)
                        continue
                    # No more retries, fail
                    raise

                log_with_sanitized_url(
                    logger, logging.DEBUG,
                    f"Making request to {{url}} (attempt {attempt + 1}/{self.config.max_retries + 1})",
                    url, attempt=attempt + 1, max_retries=self.config.max_retries + 1
                )
                response = self.session.get(url, timeout=timeout)

                # Check for server errors (5xx) that we should retry
                if response.status_code >= 500:
                    response.raise_for_status()  # This will raise HTTPError

                # Check for client errors (4xx) that we should NOT retry
                response.raise_for_status()

                # Success! Log if this was a retry
                if attempt > 0:
                    logger.info(f"Request succeeded on attempt {attempt + 1} for {url}")

                return response

            except retryable_exceptions as e:
                last_exception = e

                # Don't retry if this was the last attempt
                if attempt >= self.config.max_retries:
                    logger.error(
                        f"Request failed after {self.config.max_retries + 1} attempts for {url}: {e}"
                    )
                    raise

                # Log retry attempt
                logger.warning(
                    f"Request failed on attempt {attempt + 1}/{self.config.max_retries + 1} for {url}: {e}. "
                    f"Retrying in {current_delay:.1f}s..."
                )

                # Wait before retrying with exponential backoff
                time.sleep(current_delay)
                current_delay *= self.config.backoff_factor

            except HTTPError as e:
                # Don't retry client errors (4xx) as they're likely permanent
                if e.response and 400 <= e.response.status_code < 500:
                    log_with_sanitized_url(
                        logger, logging.WARNING,
                        f"Client error {e.response.status_code} for {{url}}, not retrying: {e}",
                        url, status_code=e.response.status_code, error=str(e)
                    )
                    raise
                # For other HTTP errors, let the retry logic handle it
                last_exception = e
                if attempt >= self.config.max_retries:
                    raise
                log_with_sanitized_url(
                    logger, logging.WARNING,
                    f"HTTP error on attempt {attempt + 1}/{self.config.max_retries + 1} for {{url}}: {e}. "
                    f"Retrying in {current_delay:.1f}s...",
                    url, attempt=attempt + 1, max_retries=self.config.max_retries + 1,
                    error=str(e), retry_delay=current_delay
                )
                time.sleep(current_delay)
                current_delay *= self.config.backoff_factor

            except RequestException as e:
                # For other request exceptions, don't retry as they're likely permanent
                log_with_sanitized_url(
                    logger, logging.ERROR,
                    f"Non-retryable request error for {{url}}: {e}",
                    url, error=str(e)
                )
                raise

        # This should never be reached, but included for safety
        if last_exception:
            raise last_exception
        from app.core.structured_logging import SensitiveDataFilter
        sanitized_url = SensitiveDataFilter.sanitize_url(url)
        raise RequestException(f"Unexpected failure making request to {sanitized_url}")

    def get(self, url: str, timeout: int | None = None) -> requests.Response:
        """Make GET request with configured session (legacy method for compatibility).

        Args:
            url: URL to request
            timeout: Request timeout in seconds (uses config default if None)

        Returns:
            HTTP response object

        Raises:
            requests.RequestException: If request fails
        """
        return self.get_with_retry(url, timeout)

    def close(self) -> None:
        """Close the session and clean up connections."""
        self.session.close()
        logger.debug("Closed scraper session")

    def __enter__(self) -> 'ScraperSession':
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: type | None, exc_val: Exception | None, exc_tb: type | None) -> None:
        """Context manager exit with cleanup."""
        self.close()


# Global session instance for reuse across requests
_scraper_session: ScraperSession | None = None


def get_scraper_session() -> ScraperSession:
    """Get or create the global scraper session.

    Returns:
        Configured scraper session instance
    """
    global _scraper_session
    if _scraper_session is None:
        _scraper_session = ScraperSession()
        logger.info("Created new global scraper session")
    return _scraper_session


def scrape_article_text(url: str, timeout: int | None = None) -> str:
    """
    Scrapes article text from a given URL by extracting text from <p> tags.

    This function validates URLs for security before making requests to prevent
    SSRF attacks and other security vulnerabilities. Uses a configured session
    with proper User-Agent headers, connection pooling, and exponential backoff
    retry logic for better performance and reduced blocking by websites.

    Args:
        url: The URL to scrape content from
        timeout: Request timeout in seconds (uses config default if None)

    Returns:
        A string containing the concatenated text from all <p> tags,
        or an error message if scraping fails or URL is invalid
    """
    try:
        # Validate URL for security before making any requests with detailed results
        logger.debug(f"Validating URL for scraping: {url}")
        validation_result = validate_url_detailed(url)

        if validation_result.is_invalid:
            # Log detailed validation failure information
            logger.warning(
                f"URL validation failed for {url}: {validation_result.error_message} "
                f"(Type: {validation_result.error_type}, Code: {validation_result.error_code})",
                extra={
                    "validation_result": {
                        "url": validation_result.url,
                        "error_type": validation_result.error_type,
                        "error_code": validation_result.error_code,
                        "error_message": validation_result.error_message,
                        "context": validation_result.validation_context
                    }
                }
            )

            # Raise appropriate exception with detailed context
            raise URLValidationError(
                validation_result.error_message or "URL validation failed",
                error_code=validation_result.error_code,
                context=validation_result.validation_context
            )

        # Log successful validation with context
        logger.debug(
            f"URL validation successful for {url}",
            extra={
                "validation_context": validation_result.validation_context
            }
        )

        # Use configured session with proper headers, connection pooling, and retry logic
        session = get_scraper_session()
        logger.debug(f"Making request with retry logic to: {url}")
        response = session.get_with_retry(url, timeout=timeout)

        # Log successful response details
        logger.info(
            f"Successfully scraped content from {url} "
            f"(status: {response.status_code}, size: {len(response.content)} bytes)"
        )

        # Parse HTML and extract paragraph text
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('p')
        article_text = ' '.join(p.get_text().strip() for p in paragraphs if p.get_text().strip())

        # Log extraction results
        paragraph_count = len(paragraphs)
        text_length = len(article_text)
        logger.debug(
            f"Extracted text from {paragraph_count} paragraphs, "
            f"total length: {text_length} characters"
        )

        if not article_text.strip():
            log_with_sanitized_url(
                logger, logging.WARNING,
                "No paragraph content found at {url}",
                url
            )
            return "Could not retrieve article content."

        return article_text

    except URLValidationError as e:
        # Enhanced logging with error code and context for debugging
        error_code = getattr(e, 'error_code', 'URL_VALIDATION_FAILED')
        error_context = getattr(e, 'context', {})

        logger.warning(
            f"URL validation failed for {url}: {e} (Code: {error_code})",
            extra={
                "error_code": error_code,
                "error_context": error_context,
                "url": url
            }
        )

        # Return user-friendly error message based on error type
        if error_code in ['URL_SCHEME_UNSUPPORTED']:
            return "Could not retrieve article content (unsupported URL scheme)."
        elif error_code in ['URL_NETWORK_RESTRICTED', 'URL_LOCALHOST_ACCESS', 'URL_PRIVATE_NETWORK']:
            return "Could not retrieve article content (restricted network access)."
        elif error_code in ['URL_PORT_RESTRICTED', 'URL_PORT_BLOCKED']:
            return "Could not retrieve article content (restricted port access)."
        elif error_code in ['URL_SECURITY_VIOLATION', 'URL_HEADER_INJECTION']:
            return "Could not retrieve article content (security policy violation)."
        else:
            return "Could not retrieve article content (invalid URL format)."
    except requests.exceptions.Timeout:
        log_with_sanitized_url(
            logger, logging.WARNING,
            "Request timeout after retries for {url}",
            url
        )
        return "Could not retrieve article content."
    except requests.exceptions.HTTPError as e:
        log_with_sanitized_url(
            logger, logging.WARNING,
            f"HTTP error after retries for {{url}} - {e.response.status_code if e.response else 'unknown'}: {e}",
            url, status_code=e.response.status_code if e.response else 'unknown', error=str(e)
        )
        return "Could not retrieve article content."
    except requests.RequestException as e:
        log_with_sanitized_url(
            logger, logging.WARNING,
            f"Request failed after retries for {{url}}: {e}",
            url, error=str(e)
        )
        return "Could not retrieve article content."
    except Exception as e:
        log_with_sanitized_url(
            logger, logging.ERROR,
            f"Unexpected error scraping {{url}}: {e}",
            url, error=str(e)
        )
        logger.error("", exc_info=True)  # Log the full traceback separately for debugging
        return "Could not retrieve article content."


def cleanup_scraper_session() -> None:
    """Clean up the global scraper session.

    This function should be called when the application shuts down
    to properly close connections and free resources.
    """
    global _scraper_session
    if _scraper_session is not None:
        _scraper_session.close()
        _scraper_session = None
        logger.info("Cleaned up global scraper session")
