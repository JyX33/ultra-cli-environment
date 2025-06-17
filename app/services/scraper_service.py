# ABOUTME: Scrapes article text from URLs with security validation to prevent SSRF attacks
# ABOUTME: Extracts content from paragraph tags while blocking malicious URLs

from bs4 import BeautifulSoup
import requests

from app.utils.url_validator import URLValidationError, validate_url


def scrape_article_text(url: str) -> str:
    """
    Scrapes article text from a given URL by extracting text from <p> tags.

    This function validates URLs for security before making requests to prevent
    SSRF attacks and other security vulnerabilities.

    Args:
        url: The URL to scrape content from

    Returns:
        A string containing the concatenated text from all <p> tags,
        or an error message if scraping fails or URL is invalid
    """
    try:
        # Validate URL for security before making any requests
        validate_url(url)

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('p')
        article_text = ' '.join(p.get_text().strip() for p in paragraphs)

        return article_text

    except (URLValidationError, requests.RequestException, Exception):
        return "Could not retrieve article content."
