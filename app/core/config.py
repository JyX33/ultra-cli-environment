import os
from dotenv import load_dotenv

load_dotenv()

class EnvVar:
    """Descriptor for environment variables that are dynamically loaded."""
    def __init__(self, env_name):
        self.env_name = env_name
    
    def __get__(self, instance, owner):
        return os.getenv(self.env_name)

class Config:
    """Configuration class that loads environment variables for the application."""
    
    REDDIT_CLIENT_ID = EnvVar("REDDIT_CLIENT_ID")
    REDDIT_CLIENT_SECRET = EnvVar("REDDIT_CLIENT_SECRET")
    REDDIT_USER_AGENT = EnvVar("REDDIT_USER_AGENT")
    OPENAI_API_KEY = EnvVar("OPENAI_API_KEY")
    
    @classmethod
    def validate_config(cls):
        """Validate that all required environment variables are set."""
        required_vars = [
            cls.REDDIT_CLIENT_ID,
            cls.REDDIT_CLIENT_SECRET,
            cls.REDDIT_USER_AGENT,
            cls.OPENAI_API_KEY
        ]
        
        if not all(required_vars):
            missing = []
            if not cls.REDDIT_CLIENT_ID:
                missing.append("REDDIT_CLIENT_ID")
            if not cls.REDDIT_CLIENT_SECRET:
                missing.append("REDDIT_CLIENT_SECRET")
            if not cls.REDDIT_USER_AGENT:
                missing.append("REDDIT_USER_AGENT")
            if not cls.OPENAI_API_KEY:
                missing.append("OPENAI_API_KEY")
            
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        return True

config = Config()