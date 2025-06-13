import praw
from app.core.config import config


class RedditService:
    """Service class for interacting with the Reddit API."""
    
    def __init__(self):
        """Initialize the Reddit service with authenticated PRAW client."""
        self.reddit = praw.Reddit(
            client_id=config.REDDIT_CLIENT_ID,
            client_secret=config.REDDIT_CLIENT_SECRET,
            user_agent=config.REDDIT_USER_AGENT
        )
    
    def search_subreddits(self, topic: str, limit: int = 10) -> list:
        """
        Search for subreddits related to a given topic.
        
        Args:
            topic (str): The topic to search for
            limit (int): Maximum number of subreddits to return (default: 10)
        
        Returns:
            list: List of subreddit objects matching the topic
        """
        return list(self.reddit.subreddits.search(topic, limit=limit))
    
    def get_hot_posts(self, subreddit_name: str, limit: int = 25) -> list:
        """
        Get hot posts from a specific subreddit.
        
        Args:
            subreddit_name (str): Name of the subreddit
            limit (int): Maximum number of posts to return (default: 25)
        
        Returns:
            list: List of hot post objects from the subreddit
        """
        subreddit = self.reddit.subreddit(subreddit_name)
        return list(subreddit.hot(limit=limit))
    
    def get_relevant_posts(self, subreddit_name: str) -> list:
        """
        Get relevant posts from a subreddit, filtered and sorted for report generation.
        
        Args:
            subreddit_name (str): Name of the subreddit
        
        Returns:
            list: List of 5 valid post objects sorted by comment count
        """
        # Fetch top posts from the last day (generous limit for sorting)
        subreddit = self.reddit.subreddit(subreddit_name)
        posts = list(subreddit.top(time_filter='day', limit=50))
        
        # Sort posts by number of comments in descending order
        posts.sort(key=lambda post: post.num_comments, reverse=True)
        
        # Media file extensions to exclude
        media_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.mp4')
        media_domains = ('i.redd.it', 'v.redd.it', 'i.imgur.com')
        
        valid_posts = []
        
        # Iterate through sorted posts and filter for valid ones
        for post in posts:
            # Check if we have enough valid posts
            if len(valid_posts) >= 5:
                break
            
            # Validate post according to FR-06
            is_valid = False
            
            # Text posts are always valid
            if post.is_self:
                is_valid = True
            else:
                # For link posts, check if URL is not a media file or from media domains
                post_url = post.url.lower()
                
                # Check if URL ends with media extensions
                if not post_url.endswith(media_extensions):
                    # Check if URL is from media domains
                    is_media_domain = any(domain in post_url for domain in media_domains)
                    if not is_media_domain:
                        is_valid = True
            
            if is_valid:
                valid_posts.append(post)
        
        return valid_posts
    
    def get_top_comments(self, post_id: str, limit: int = 15) -> list:
        """
        Get top comments from a specific post.
        
        Args:
            post_id (str): The ID of the post
            limit (int): Maximum number of comments to return (default: 15)
        
        Returns:
            list: List of top comment objects from the post
        """
        submission = self.reddit.submission(id=post_id)
        # Replace MoreComments objects and get top-level comments
        submission.comments.replace_more(limit=0)
        # Sort comments by score and return top ones
        top_comments = sorted(submission.comments, key=lambda x: x.score, reverse=True)
        return top_comments[:limit]