# ABOUTME: AI content summarization service using modern OpenAI API client with robust error handling
# ABOUTME: Provides text summarization for Reddit posts and comments with retry logic and security

from collections.abc import Generator
import os
import time

from openai import OpenAI
from openai._exceptions import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)

from app.core.config import config
from app.core.error_handling import openai_error_handler
from app.core.exceptions import (
    RateLimitExceededError,
    SummarizerAuthenticationError,
    wrap_external_error,
)
from app.core.structured_logging import get_logger
from app.services.rate_limit_service import get_rate_limiter

# Set up structured logging
logger = get_logger(__name__)


# Legacy exception for backward compatibility
class SummarizerError(Exception):
    """Base exception for summarizer service errors (legacy)."""

    pass


class SummarizerService:
    """Modern OpenAI-based content summarization service."""

    def __init__(self, api_key: str | None = None):
        """
        Initialize the summarizer service with modern OpenAI client and configuration.

        Args:
            api_key: OpenAI API key. If None, loads from configuration.

        Raises:
            SummarizerAuthenticationError: If API key is missing or invalid format
        """
        # Get configuration
        self.config = config.get_openai_config()

        # Get API key from parameter, config, or environment
        self.api_key = api_key or self.config.api_key or os.getenv("OPENAI_API_KEY")

        if not self.api_key:
            raise SummarizerAuthenticationError(
                "OpenAI API key is required",
                error_code="OPENAI_API_KEY_MISSING",
                context={"checked_sources": ["parameter", "config", "environment"]},
            )

        # Validate API key format
        if not self._is_valid_api_key_format(self.api_key):
            raise SummarizerAuthenticationError(
                "Invalid OpenAI API key format",
                error_code="OPENAI_API_KEY_INVALID_FORMAT",
                context={"expected_format": "sk-..."},
            )

        # Initialize modern OpenAI client
        try:
            self.client = OpenAI(api_key=self.api_key)
        except Exception as e:
            raise wrap_external_error(
                e,
                SummarizerAuthenticationError,
                "Failed to initialize OpenAI client",
                "OPENAI_CLIENT_INIT_FAILED",
            ) from e

        # Use configuration-driven settings
        self.model = self.config.model
        self.fallback_model = self.config.fallback_model
        self.max_retries = self.config.max_retries
        self.base_delay = self.config.retry_delay
        self.max_tokens = self.config.max_tokens
        self.temperature = self.config.temperature

        # Initialize rate limiter for OpenAI API calls
        self.rate_limiter = get_rate_limiter("openai")

        logger.info(
            f"Initialized SummarizerService with model: {self.model}, "
            f"fallback: {self.fallback_model}, max_retries: {self.max_retries}",
            extra={
                "config": {
                    "model": self.model,
                    "fallback_model": self.fallback_model,
                    "max_retries": self.max_retries,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "rate_limiting_enabled": self.rate_limiter.enabled,
                }
            },
        )

    def _is_valid_api_key_format(self, api_key: str) -> bool:
        """Validate API key format."""
        return (
            isinstance(api_key, str)
            and api_key.startswith("sk-")
            and len(api_key) > 20  # Minimum reasonable length
        )

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text content.

        Uses rough approximation: 1 token ≈ 4 characters for English text.
        This is conservative and accounts for overhead.

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated token count
        """
        # Basic token estimation: 1 token ≈ 4 characters
        # Add some overhead for message structure and system prompt
        base_tokens = len(text) // 4
        overhead_tokens = 50  # For system prompt and message structure

        return max(1, base_tokens + overhead_tokens)

    @openai_error_handler
    def summarize_content(self, content: str, prompt_type: str) -> str:
        """
        Summarize content using OpenAI API with configuration-driven settings.

        Args:
            content: The text content to summarize
            prompt_type: Either "post" or "comments" to determine the system prompt

        Returns:
            String containing the AI-generated summary or error message
        """
        logger.debug(
            f"Starting summarization for {prompt_type} content (length: {len(content)} chars)"
        )

        if not content or not content.strip():
            logger.warning("Empty content provided for summarization")
            return "No content available for summary."

        if prompt_type not in ["post", "comments"]:
            logger.error(f"Invalid prompt type: {prompt_type}")
            return f"AI summary could not be generated: Invalid prompt type '{prompt_type}'."

        # Prepare system prompt
        system_prompt = self._get_system_prompt(prompt_type)

        # Truncate content if too long (rough token estimation: 1 token ≈ 4 characters)
        max_content_length = 4000 * 4  # ~4000 tokens for content
        if len(content) > max_content_length:
            logger.warning(
                f"Content truncated from {len(content)} to {max_content_length} characters",
                extra={
                    "original_length": len(content),
                    "truncated_length": max_content_length,
                },
            )
            content = content[:max_content_length] + "..."

        # Attempt summarization with retry logic
        return self._summarize_with_retry(content, system_prompt, prompt_type)

    def _get_system_prompt(self, prompt_type: str) -> str:
        """Get appropriate system prompt based on content type."""
        if prompt_type == "post":
            return "Summarize the following article text concisely, focusing on key points and main ideas."
        elif prompt_type == "comments":
            return "Summarize the following Reddit comments, capturing the overall community sentiment and key discussion points."
        else:
            raise ValueError(f"Invalid prompt_type: {prompt_type}")

    def _summarize_with_retry(
        self, content: str, system_prompt: str, prompt_type: str
    ) -> str:
        """
        Attempt summarization with exponential backoff retry logic and model fallback.

        Args:
            content: Content to summarize
            system_prompt: System prompt to use
            prompt_type: Type of content being summarized

        Returns:
            Summary text or error message
        """
        models_to_try = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models_to_try.append(self.fallback_model)

        last_error: Exception | None = None

        for model_attempt, current_model in enumerate(models_to_try):
            logger.debug(
                f"Attempting summarization with model {current_model} "
                f"(attempt {model_attempt + 1}/{len(models_to_try)})"
            )

            for attempt in range(self.max_retries):
                try:
                    logger.debug(
                        f"Making API call with model {current_model} "
                        f"(retry {attempt + 1}/{self.max_retries})",
                        extra={
                            "model": current_model,
                            "attempt": attempt + 1,
                            "max_retries": self.max_retries,
                            "prompt_type": prompt_type,
                        },
                    )

                    # Check rate limits before making API call
                    estimated_tokens = self._estimate_tokens(content + system_prompt)
                    try:
                        self.rate_limiter.check_rate_limit(
                            tokens=float(estimated_tokens),
                            request_tokens=1
                        )
                        logger.debug(
                            f"Rate limit check passed for {estimated_tokens} tokens",
                            extra={
                                "estimated_tokens": estimated_tokens,
                                "model": current_model,
                            }
                        )
                    except RateLimitExceededError as e:
                        # Rate limit exceeded, treat as temporary error and retry
                        logger.debug(
                            f"Rate limit exceeded for model {current_model}: {e}",
                            extra={
                                "estimated_tokens": estimated_tokens,
                                "model": current_model,
                                "attempt": attempt + 1,
                                "rate_limit_error": str(e),
                            }
                        )
                        # If we have retries left, wait and try again
                        if attempt < self.max_retries - 1:
                            delay = self.base_delay * (2**attempt)
                            logger.debug(f"Waiting {delay}s before retry due to rate limit")
                            time.sleep(delay)
                            continue
                        # If no more retries, try fallback model or fail
                        if model_attempt < len(models_to_try) - 1:
                            logger.debug(f"Rate limit exhausted for {current_model}, trying fallback model")
                            break
                        # Only log final failure at warning level
                        logger.warning(f"Rate limit exhausted for all models after {self.max_retries} attempts")
                        return "AI summary could not be generated due to rate limits. Please try again later."

                    response = self.client.chat.completions.create(
                        model=current_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": content},
                        ],
                        max_tokens=self.max_tokens,
                        temperature=self.temperature,
                        top_p=1.0,
                        frequency_penalty=0.0,
                        presence_penalty=0.0,
                    )

                    # Extract and validate response
                    if not response.choices or not response.choices[0].message.content:
                        logger.warning("Empty response received from OpenAI API")
                        return "AI summary could not be generated: Empty response received."

                    summary = response.choices[0].message.content.strip()
                    logger.info(
                        f"Successfully generated summary using model {current_model} "
                        f"(length: {len(summary)} chars)",
                        extra={
                            "model": current_model,
                            "summary_length": len(summary),
                            "attempts_used": attempt + 1,
                        },
                    )
                    return summary

                except RateLimitError as e:
                    last_error = e
                    if attempt < self.max_retries - 1:
                        delay = self.base_delay * (2**attempt)  # Exponential backoff
                        logger.debug(
                            f"Rate limit hit, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries})",
                            extra={"delay": delay, "model": current_model},
                        )
                        time.sleep(delay)
                        continue
                    # Try fallback model if available
                    if model_attempt < len(models_to_try) - 1:
                        logger.debug(
                            f"Rate limit exhausted for {current_model}, trying fallback model"
                        )
                        break
                    # Only log final failure at warning level
                    logger.warning(f"Rate limit exhausted for all models after {self.max_retries} attempts")
                    return "AI summary could not be generated due to rate limits. Please try again later."

                except AuthenticationError as e:
                    # Don't retry authentication errors
                    logger.error(f"Authentication failed with OpenAI API: {e}")
                    return "AI summary could not be generated: Invalid API key."

                except APIConnectionError as e:
                    last_error = e
                    if attempt < self.max_retries - 1:
                        delay = self.base_delay * (
                            1.5**attempt
                        )  # Shorter backoff for connection issues
                        logger.debug(
                            f"Connection error, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries}): {e}",
                            extra={"delay": delay, "model": current_model},
                        )
                        time.sleep(delay)
                        continue
                    # Try fallback model if available
                    if model_attempt < len(models_to_try) - 1:
                        logger.debug(
                            f"Connection failed for {current_model}, trying fallback model"
                        )
                        break
                    # Only log final failure at warning level
                    logger.warning(f"Connection failed for all models after {self.max_retries} attempts: {e}")
                    return "AI summary could not be generated: Connection failed."

                except BadRequestError as e:
                    # Handle specific bad request cases
                    error_message = str(e).lower()
                    logger.warning(
                        f"Bad request error from OpenAI: {e}",
                        extra={"model": current_model},
                    )

                    if (
                        "content_filter" in error_message
                        or "policy violation" in error_message
                    ):
                        return "AI summary could not be generated: Content filtered due to policy violation."
                    elif "token" in error_message and "limit" in error_message:
                        return "AI summary could not be generated: Content too long."
                    elif (
                        "model" in error_message
                        and model_attempt < len(models_to_try) - 1
                    ):
                        # Try fallback model if current model is not available
                        logger.info(
                            f"Model {current_model} not available, trying fallback model"
                        )
                        break
                    else:
                        return "AI summary could not be generated: Invalid request."

                except APIError as e:
                    last_error = e
                    if attempt < self.max_retries - 1:
                        delay = self.base_delay * (2**attempt)
                        logger.debug(
                            f"API error, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries}): {e}",
                            extra={"delay": delay, "model": current_model},
                        )
                        time.sleep(delay)
                        continue
                    # Try fallback model if available
                    if model_attempt < len(models_to_try) - 1:
                        logger.debug(
                            f"API error with {current_model}, trying fallback model"
                        )
                        break
                    # Only log final failure at warning level
                    logger.warning(f"API error for all models after {self.max_retries} attempts: {e}")
                    return "AI summary could not be generated: API error occurred."

                except Exception as e:
                    # Catch any other unexpected errors
                    last_error = e
                    logger.error(
                        f"Unexpected error during summarization: {e}", exc_info=True
                    )
                    return (
                        "AI summary could not be generated: Unexpected error occurred."
                    )

        # If we get here, all models and retries failed
        logger.error(
            f"All summarization attempts failed after trying {len(models_to_try)} models "
            f"with {self.max_retries} retries each",
            extra={
                "models_tried": models_to_try,
                "max_retries": self.max_retries,
                "last_error": str(last_error) if last_error else None,
            },
        )
        return f"AI summary could not be generated after {self.max_retries} attempts with {len(models_to_try)} models."

    def summarize_content_stream(
        self, content: str, prompt_type: str
    ) -> Generator[str, None, None]:
        """
        Stream summarization response for large content (future feature).

        Args:
            content: Content to summarize
            prompt_type: Type of content prompt

        Yields:
            Chunks of summarized content
        """
        # Placeholder for streaming implementation
        # This would use stream=True in the API call
        yield self.summarize_content(content, prompt_type)


# Global service instance for backward compatibility
_global_service = None


def get_summarizer_service() -> SummarizerService:
    """Get or create global summarizer service instance with configuration."""
    global _global_service
    if _global_service is None:
        try:
            _global_service = SummarizerService()
            logger.info("Created global SummarizerService instance")
        except Exception as e:
            logger.error(f"Failed to create SummarizerService: {e}", exc_info=True)
            raise
    return _global_service


def summarize_content(content: str, prompt_type: str) -> str:
    """
    Legacy function for backward compatibility.

    Args:
        content: The text content to summarize
        prompt_type: Either "post" or "comments" to determine the system prompt

    Returns:
        String containing the AI-generated summary or error message
    """
    try:
        service = get_summarizer_service()
        return service.summarize_content(content, prompt_type)
    except Exception:
        return "AI summary could not be generated."
