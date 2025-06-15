"""Module for scoring and ranking subreddits by relevance to a given topic."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from app.services.reddit_service import RedditService

logger = logging.getLogger(__name__)


def score_and_rank_subreddits(subreddits: list, topic: str, reddit_service: 'RedditService') -> list[dict[str, Any]]:
    """
    Score and rank subreddits by relevance to a given topic.
    
    This function calculates relevance by counting how many of the top 25 hot posts
    in each subreddit contain the topic keyword in their titles (case-insensitive).
    
    Args:
        subreddits (list): List of subreddit objects to score
        topic (str): The topic keyword to search for in post titles
        reddit_service (RedditService): Service instance for fetching Reddit data
    
    Returns:
        List[Dict[str, any]]: Sorted list of dictionaries containing:
            - name (str): Subreddit display name
            - description (str): Subreddit description  
            - score (int): Relevance score (number of matching posts)
    """
    scored_subreddits = []
    topic_lower = topic.lower()

    for subreddit in subreddits:
        try:
            # Fetch hot posts for this subreddit
            hot_posts = reddit_service.get_hot_posts(subreddit.display_name)

            # Count posts with topic in title (case-insensitive)
            relevance_score = 0
            for post in hot_posts:
                if topic_lower in post.title.lower():
                    relevance_score += 1

            # Create result dictionary
            scored_subreddit = {
                'name': subreddit.display_name,
                'description': getattr(subreddit, 'public_description', ''),
                'score': relevance_score
            }
            scored_subreddits.append(scored_subreddit)

        except Exception:
            # If we can't fetch posts for a subreddit, skip it
            continue

    # Sort by score in descending order
    scored_subreddits.sort(key=lambda x: x['score'], reverse=True)

    return scored_subreddits


def score_and_rank_subreddits_concurrent(subreddits: list, topic: str, reddit_service: 'RedditService', max_workers: int = 5) -> list[dict[str, Any]]:
    """
    Score and rank subreddits by relevance using concurrent processing.
    
    This optimized version eliminates the N+1 query pattern by processing
    multiple subreddits concurrently, reducing total execution time.
    
    Args:
        subreddits (list): List of subreddit objects to score
        topic (str): The topic keyword to search for in post titles
        reddit_service (RedditService): Service instance for fetching Reddit data
        max_workers (int): Maximum number of concurrent threads (default: 5)
    
    Returns:
        List[Dict[str, any]]: Sorted list of dictionaries containing:
            - name (str): Subreddit display name
            - description (str): Subreddit description  
            - score (int): Relevance score (number of matching posts)
    """
    logger.info(f"Starting concurrent relevance scoring for {len(subreddits)} subreddits with topic: '{topic}'")
    logger.info(f"Subreddits to process: {[getattr(s, 'display_name', 'unknown') for s in subreddits]}")
    
    if not subreddits:
        logger.warning("No subreddits provided for scoring")
        return []

    topic_lower = topic.lower()
    scored_subreddits = []

    def process_subreddit(subreddit: Any) -> Optional[dict[str, Any]]:
        """Process a single subreddit and return its score."""
        subreddit_name = getattr(subreddit, 'display_name', 'unknown')
        logger.info(f"Processing subreddit: {subreddit_name} for topic: '{topic}'")
        
        try:
            # Fetch hot posts for this subreddit
            hot_posts = reddit_service.get_hot_posts(subreddit_name)
            logger.info(f"Retrieved {len(hot_posts)} hot posts from r/{subreddit_name}")
            
            if not hot_posts:
                logger.warning(f"No hot posts found for r/{subreddit_name}")
                return {
                    'name': subreddit_name,
                    'description': getattr(subreddit, 'public_description', ''),
                    'score': 0
                }

            # Count posts with topic in title (case-insensitive)
            relevance_score = 0
            matching_posts = []
            
            for i, post in enumerate(hot_posts):
                post_title = getattr(post, 'title', '')
                logger.debug(f"Post {i+1}/{len(hot_posts)}: '{post_title}'")
                
                if topic_lower in post_title.lower():
                    relevance_score += 1
                    matching_posts.append(post_title)
                    logger.debug(f"✓ Match found: '{post_title}' contains '{topic}'")
                else:
                    logger.debug(f"✗ No match: '{post_title}' does not contain '{topic}'")

            logger.info(f"Subreddit r/{subreddit_name}: {relevance_score}/{len(hot_posts)} posts match topic '{topic}'")
            if matching_posts:
                logger.info(f"Matching posts: {matching_posts[:3]}{'...' if len(matching_posts) > 3 else ''}")

            # Create result dictionary
            return {
                'name': subreddit_name,
                'description': getattr(subreddit, 'public_description', ''),
                'score': relevance_score
            }

        except Exception as e:
            # Log detailed error information
            logger.error(f"Failed to process subreddit r/{subreddit_name}: {type(e).__name__}: {e}")
            logger.error(f"Error details - Topic: '{topic}', Exception: {repr(e)}")
            return None

    # Process subreddits concurrently
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_subreddit = {executor.submit(process_subreddit, subreddit): subreddit
                              for subreddit in subreddits}

        # Collect results as they complete
        for future in as_completed(future_to_subreddit):
            result = future.result()
            if result is not None:  # Skip failed subreddits
                scored_subreddits.append(result)

    # Sort by score in descending order
    scored_subreddits.sort(key=lambda x: x['score'], reverse=True)
    
    logger.info(f"Relevance scoring completed. Processed {len(scored_subreddits)} subreddits")
    logger.info("Final scores:")
    for i, result in enumerate(scored_subreddits[:5]):  # Log top 5 results
        logger.info(f"  {i+1}. r/{result['name']}: {result['score']} matches")
    
    if not scored_subreddits:
        logger.error("No subreddits were successfully processed - all returned None!")
    elif all(s['score'] == 0 for s in scored_subreddits):
        logger.warning("All subreddits returned score 0 - potential issue with topic matching or post retrieval")

    return scored_subreddits
