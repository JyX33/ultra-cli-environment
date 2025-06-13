"""Module for scoring and ranking subreddits by relevance to a given topic."""

from typing import List, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.reddit_service import RedditService


def score_and_rank_subreddits(subreddits: list, topic: str, reddit_service: 'RedditService') -> List[Dict[str, any]]:
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