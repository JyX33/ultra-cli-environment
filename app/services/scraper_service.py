import requests
from bs4 import BeautifulSoup


def scrape_article_text(url: str) -> str:
    """
    Scrapes article text from a given URL by extracting text from <p> tags.
    
    Args:
        url: The URL to scrape content from
        
    Returns:
        A string containing the concatenated text from all <p> tags,
        or an error message if scraping fails
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('p')
        article_text = ' '.join(p.get_text().strip() for p in paragraphs)
        
        return article_text
        
    except (requests.RequestException, Exception):
        return "Could not retrieve article content."