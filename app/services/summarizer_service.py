# ABOUTME: AI content summarization service using modern OpenAI API client with robust error handling
# ABOUTME: Provides text summarization for Reddit posts and comments with retry logic and security

from collections.abc import Generator
import os
import time
from typing import Optional

from openai import OpenAI
from openai._exceptions import (
    APIConnectionError,
    APIError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)


class SummarizerError(Exception):
    """Base exception for summarizer service errors."""
    pass


class SummarizerService:
    """Modern OpenAI-based content summarization service."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the summarizer service with modern OpenAI client.
        
        Args:
            api_key: OpenAI API key. If None, loads from OPENAI_API_KEY environment variable.
        
        Raises:
            AuthenticationError: If API key is missing or invalid format
        """
        # Get API key from parameter or environment
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')

        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable.")

        # Validate API key format
        if not self._is_valid_api_key_format(self.api_key):
            raise ValueError("Invalid OpenAI API key format. Key should start with 'sk-'.")

        # Initialize modern OpenAI client
        self.client = OpenAI(api_key=self.api_key)

        # Configuration
        self.model = "gpt-4o"
        self.max_retries = 3
        self.base_delay = 1.0
        self.max_tokens = 150
        self.temperature = 0.7

    def _is_valid_api_key_format(self, api_key: str) -> bool:
        """Validate API key format."""
        return (
            isinstance(api_key, str) and
            api_key.startswith('sk-') and
            len(api_key) > 20  # Minimum reasonable length
        )

    def summarize_content(self, content: str, prompt_type: str) -> str:
        """
        Summarize content using OpenAI API with modern client and robust error handling.
        
        Args:
            content: The text content to summarize
            prompt_type: Either "post" or "comments" to determine the system prompt
            
        Returns:
            String containing the AI-generated summary or error message
        """
        if not content or not content.strip():
            return "No content available for summary."

        if prompt_type not in ["post", "comments"]:
            return f"AI summary could not be generated: Invalid prompt type '{prompt_type}'."

        # Prepare system prompt
        system_prompt = self._get_system_prompt(prompt_type)

        # Truncate content if too long (rough token estimation: 1 token ≈ 4 characters)
        max_content_length = 4000 * 4  # ~4000 tokens for content
        if len(content) > max_content_length:
            content = content[:max_content_length] + "..."

        # Attempt summarization with retry logic
        return self._summarize_with_retry(content, system_prompt)

    def _get_system_prompt(self, prompt_type: str) -> str:
        """Get appropriate system prompt based on content type."""
        if prompt_type == "post":
            return "Summarize the following article text concisely, focusing on key points and main ideas."
        elif prompt_type == "comments":
            return "Summarize the following Reddit comments, capturing the overall community sentiment and key discussion points."
        else:
            raise ValueError(f"Invalid prompt_type: {prompt_type}")

    def _summarize_with_retry(self, content: str, system_prompt: str) -> str:
        """
        Attempt summarization with exponential backoff retry logic.
        
        Args:
            content: Content to summarize
            system_prompt: System prompt to use
            
        Returns:
            Summary text or error message
        """
        last_exception: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": content}
                    ],
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    top_p=1.0,
                    frequency_penalty=0.0,
                    presence_penalty=0.0
                )

                # Extract and validate response
                if not response.choices or not response.choices[0].message.content:
                    return "AI summary could not be generated: Empty response received."

                return response.choices[0].message.content.strip()

            except RateLimitError as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)  # Exponential backoff
                    time.sleep(delay)
                    continue
                return "AI summary could not be generated due to rate limits. Please try again later."

            except AuthenticationError:
                # Don't retry authentication errors
                return "AI summary could not be generated: Invalid API key."

            except APIConnectionError as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (1.5 ** attempt)  # Shorter backoff for connection issues
                    time.sleep(delay)
                    continue
                return "AI summary could not be generated: Connection failed."

            except BadRequestError as e:
                # Handle specific bad request cases
                error_message = str(e).lower()
                if "content_filter" in error_message or "policy violation" in error_message:
                    return "AI summary could not be generated: Content filtered due to policy violation."
                elif "token" in error_message and "limit" in error_message:
                    return "AI summary could not be generated: Content too long."
                else:
                    return "AI summary could not be generated: Invalid request."

            except APIError as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = self.base_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
                return "AI summary could not be generated: API error occurred."

            except Exception as e:
                # Catch any other unexpected errors
                last_exception = e
                return "AI summary could not be generated: Unexpected error occurred."

        # If we get here, all retries failed
        return f"AI summary could not be generated after {self.max_retries} attempts."

    def summarize_content_stream(self, content: str, prompt_type: str) -> Generator[str, None, None]:
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
    """Get or create global summarizer service instance."""
    global _global_service
    if _global_service is None:
        _global_service = SummarizerService()
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
