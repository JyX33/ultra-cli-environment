# ABOUTME: Configuration management for environment variables with validation
# ABOUTME: Provides centralized config access with runtime validation of required settings

from dataclasses import dataclass
import os
from typing import Any, ClassVar, Literal

from dotenv import load_dotenv

load_dotenv()

class EnvVar:
    """Descriptor for environment variables that are dynamically loaded."""
    def __init__(self, env_name: str) -> None:
        self.env_name = env_name

    def __get__(self, instance: Any, owner: Any) -> str | None:
        return os.getenv(self.env_name)


@dataclass(frozen=True)
class RedditConfig:
    """Reddit API configuration schema."""
    client_id: str
    client_secret: str
    user_agent: str
    username: str
    hot_posts_limit: int
    relevant_posts_limit: int
    top_comments_limit: int
    max_valid_posts: int
    api_timeout: int


@dataclass(frozen=True)
class OpenAIConfig:
    """OpenAI API configuration schema."""
    api_key: str
    model: str
    fallback_model: str
    max_tokens: int
    temperature: float
    max_retries: int
    retry_delay: float


@dataclass(frozen=True)
class ScraperConfig:
    """Web scraper configuration schema."""
    user_agent: str
    timeout: int
    max_retries: int
    retry_delay: float
    backoff_factor: float


@dataclass(frozen=True)
class DatabaseConfig:
    """Comprehensive database configuration schema with advanced pooling options."""
    url: str
    pool_size: int
    max_overflow: int
    pool_recycle: int
    pool_timeout: float
    pool_pre_ping: bool
    pool_reset_on_return: str  # 'commit', 'rollback', None
    pool_invalid_on_exception: bool
    pool_heartbeat_interval: int
    connect_timeout: float
    query_timeout: float
    enable_pool_monitoring: bool
    pool_size_max_threshold: float
    pool_checkout_timeout: float
    pool_overflow_ratio_warning: float


@dataclass(frozen=True)
class CacheConfig:
    """Cache configuration schema."""
    max_size: int
    default_ttl: int
    enable_redis: bool
    redis_url: str


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration schema."""
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    format: str
    enable_structured: bool


@dataclass(frozen=True)
class RateLimitConfig:
    """Rate limiting configuration schema."""
    openai_rpm: int
    openai_tpm: int
    reddit_rpm: int
    scraper_rpm: int
    burst_allowance: float
    enabled: bool

class Config:
    """Configuration class that loads environment variables for the application."""

    # Core API Keys and Authentication
    REDDIT_CLIENT_ID = EnvVar("REDDIT_CLIENT_ID")
    REDDIT_CLIENT_SECRET = EnvVar("REDDIT_CLIENT_SECRET")
    REDDIT_USER_AGENT = EnvVar("REDDIT_USER_AGENT")
    REDDIT_USERNAME: str = os.getenv("REDDIT_USERNAME", "JyXAgent")
    OPENAI_API_KEY = EnvVar("OPENAI_API_KEY")

    # AI/ML Configuration
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    OPENAI_FALLBACK_MODEL: str = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")
    OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "150"))
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
    OPENAI_MAX_RETRIES: int = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
    OPENAI_RETRY_DELAY: float = float(os.getenv("OPENAI_RETRY_DELAY", "1.0"))

    # Reddit Service Configuration
    REDDIT_HOT_POSTS_LIMIT: int = int(os.getenv("REDDIT_HOT_POSTS_LIMIT", "25"))
    REDDIT_RELEVANT_POSTS_LIMIT: int = int(os.getenv("REDDIT_RELEVANT_POSTS_LIMIT", "15"))
    REDDIT_TOP_COMMENTS_LIMIT: int = int(os.getenv("REDDIT_TOP_COMMENTS_LIMIT", "15"))
    REDDIT_MAX_VALID_POSTS: int = int(os.getenv("REDDIT_MAX_VALID_POSTS", "5"))
    REDDIT_API_TIMEOUT: int = int(os.getenv("REDDIT_API_TIMEOUT", "30"))

    # Web Scraping Configuration
    SCRAPER_USER_AGENT: str = os.getenv("SCRAPER_USER_AGENT", "AI Reddit News Agent/1.0 (Educational Research)")
    SCRAPER_TIMEOUT: int = int(os.getenv("SCRAPER_TIMEOUT", "10"))
    SCRAPER_MAX_RETRIES: int = int(os.getenv("SCRAPER_MAX_RETRIES", "3"))
    SCRAPER_RETRY_DELAY: float = float(os.getenv("SCRAPER_RETRY_DELAY", "1.0"))
    SCRAPER_BACKOFF_FACTOR: float = float(os.getenv("SCRAPER_BACKOFF_FACTOR", "2.0"))

    # Database configuration - Enhanced connection pooling
    DATABASE_URL = EnvVar("DATABASE_URL")
    DATABASE_POOL_SIZE: int = int(os.getenv("DATABASE_POOL_SIZE", "10"))
    DATABASE_MAX_OVERFLOW: int = int(os.getenv("DATABASE_MAX_OVERFLOW", "20"))
    DATABASE_POOL_RECYCLE: int = int(os.getenv("DATABASE_POOL_RECYCLE", "300"))
    DATABASE_POOL_TIMEOUT: float = float(os.getenv("DATABASE_POOL_TIMEOUT", "30.0"))
    DATABASE_POOL_PRE_PING: bool = os.getenv("DATABASE_POOL_PRE_PING", "true").lower() in ("true", "1", "yes")
    DATABASE_POOL_RESET_ON_RETURN: str = os.getenv("DATABASE_POOL_RESET_ON_RETURN", "commit")
    DATABASE_POOL_INVALID_ON_EXCEPTION: bool = os.getenv("DATABASE_POOL_INVALID_ON_EXCEPTION", "true").lower() in ("true", "1", "yes")
    DATABASE_POOL_HEARTBEAT_INTERVAL: int = int(os.getenv("DATABASE_POOL_HEARTBEAT_INTERVAL", "30"))
    DATABASE_CONNECT_TIMEOUT: float = float(os.getenv("DATABASE_CONNECT_TIMEOUT", "10.0"))
    DATABASE_QUERY_TIMEOUT: float = float(os.getenv("DATABASE_QUERY_TIMEOUT", "60.0"))
    DATABASE_ENABLE_POOL_MONITORING: bool = os.getenv("DATABASE_ENABLE_POOL_MONITORING", "true").lower() in ("true", "1", "yes")
    DATABASE_POOL_SIZE_MAX_THRESHOLD: float = float(os.getenv("DATABASE_POOL_SIZE_MAX_THRESHOLD", "0.8"))
    DATABASE_POOL_CHECKOUT_TIMEOUT: float = float(os.getenv("DATABASE_POOL_CHECKOUT_TIMEOUT", "10.0"))
    DATABASE_POOL_OVERFLOW_RATIO_WARNING: float = float(os.getenv("DATABASE_POOL_OVERFLOW_RATIO_WARNING", "0.7"))

    # Data retention settings
    DATA_RETENTION_DAYS: int = int(os.getenv("DATA_RETENTION_DAYS", "30"))
    ARCHIVE_OLD_DATA: bool = os.getenv("ARCHIVE_OLD_DATA", "false").lower() in ("true", "1", "yes")
    CLEANUP_BATCH_SIZE: int = int(os.getenv("CLEANUP_BATCH_SIZE", "100"))

    # Cache Configuration
    CACHE_MAX_SIZE: int = int(os.getenv("CACHE_MAX_SIZE", "2000"))
    CACHE_DEFAULT_TTL: int = int(os.getenv("CACHE_DEFAULT_TTL", "300"))
    ENABLE_REDIS: bool = os.getenv("ENABLE_REDIS", "false").lower() in ("true", "1", "yes")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Performance Configuration
    ENABLE_PERFORMANCE_MONITORING: bool = os.getenv("ENABLE_PERFORMANCE_MONITORING", "true").lower() in ("true", "1", "yes")
    PERFORMANCE_MONITORING_INTERVAL: float = float(os.getenv("PERFORMANCE_MONITORING_INTERVAL", "10.0"))

    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    ENABLE_STRUCTURED_LOGGING: bool = os.getenv("ENABLE_STRUCTURED_LOGGING", "false").lower() in ("true", "1", "yes")

    # Rate Limiting Configuration
    OPENAI_RATE_LIMIT_RPM: int = int(os.getenv("OPENAI_RATE_LIMIT_RPM", "60"))  # Requests per minute
    OPENAI_RATE_LIMIT_TPM: int = int(os.getenv("OPENAI_RATE_LIMIT_TPM", "90000"))  # Tokens per minute
    REDDIT_RATE_LIMIT_RPM: int = int(os.getenv("REDDIT_RATE_LIMIT_RPM", "600"))  # PRAW handles most rate limiting
    SCRAPER_RATE_LIMIT_RPM: int = int(os.getenv("SCRAPER_RATE_LIMIT_RPM", "120"))  # Conservative for web scraping
    RATE_LIMIT_BURST_ALLOWANCE: float = float(os.getenv("RATE_LIMIT_BURST_ALLOWANCE", "1.5"))  # Allow 50% burst
    ENABLE_RATE_LIMITING: bool = os.getenv("ENABLE_RATE_LIMITING", "true").lower() in ("true", "1", "yes")

    # Required environment variables for validation
    REQUIRED_VARS: ClassVar[list[str]] = [
        "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET",
        "REDDIT_USER_AGENT",
        "OPENAI_API_KEY"
    ]

    @classmethod
    def validate_config(cls) -> bool:
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

    @classmethod
    def validate_numeric_ranges(cls) -> bool:
        """Validate that numeric configuration values are within reasonable ranges."""
        validation_errors = []

        # Validate OpenAI configuration
        if not (1 <= cls.OPENAI_MAX_TOKENS <= 4096):
            validation_errors.append("OPENAI_MAX_TOKENS must be between 1 and 4096")

        if not (0.0 <= cls.OPENAI_TEMPERATURE <= 2.0):
            validation_errors.append("OPENAI_TEMPERATURE must be between 0.0 and 2.0")

        if not (1 <= cls.OPENAI_MAX_RETRIES <= 10):
            validation_errors.append("OPENAI_MAX_RETRIES must be between 1 and 10")

        # Validate Reddit configuration
        if not (1 <= cls.REDDIT_HOT_POSTS_LIMIT <= 100):
            validation_errors.append("REDDIT_HOT_POSTS_LIMIT must be between 1 and 100")

        if not (1 <= cls.REDDIT_RELEVANT_POSTS_LIMIT <= 50):
            validation_errors.append("REDDIT_RELEVANT_POSTS_LIMIT must be between 1 and 50")

        if not (5 <= cls.SCRAPER_TIMEOUT <= 60):
            validation_errors.append("SCRAPER_TIMEOUT must be between 5 and 60 seconds")

        if not (1 <= cls.SCRAPER_MAX_RETRIES <= 10):
            validation_errors.append("SCRAPER_MAX_RETRIES must be between 1 and 10")

        if not (0.1 <= cls.SCRAPER_RETRY_DELAY <= 30.0):
            validation_errors.append("SCRAPER_RETRY_DELAY must be between 0.1 and 30.0 seconds")

        if not (1.0 <= cls.SCRAPER_BACKOFF_FACTOR <= 5.0):
            validation_errors.append("SCRAPER_BACKOFF_FACTOR must be between 1.0 and 5.0")

        # Validate Database configuration
        if not (1 <= cls.DATABASE_POOL_SIZE <= 50):
            validation_errors.append("DATABASE_POOL_SIZE must be between 1 and 50")

        # Validate Rate Limiting configuration
        if not (1 <= cls.OPENAI_RATE_LIMIT_RPM <= 10000):
            validation_errors.append("OPENAI_RATE_LIMIT_RPM must be between 1 and 10000")

        if not (1000 <= cls.OPENAI_RATE_LIMIT_TPM <= 1000000):
            validation_errors.append("OPENAI_RATE_LIMIT_TPM must be between 1000 and 1000000")

        if not (1 <= cls.REDDIT_RATE_LIMIT_RPM <= 10000):
            validation_errors.append("REDDIT_RATE_LIMIT_RPM must be between 1 and 10000")

        if not (1 <= cls.SCRAPER_RATE_LIMIT_RPM <= 1000):
            validation_errors.append("SCRAPER_RATE_LIMIT_RPM must be between 1 and 1000")

        if not (1.0 <= cls.RATE_LIMIT_BURST_ALLOWANCE <= 5.0):
            validation_errors.append("RATE_LIMIT_BURST_ALLOWANCE must be between 1.0 and 5.0")

        if validation_errors:
            raise ValueError(f"Configuration validation errors: {'; '.join(validation_errors)}")

        return True

    @classmethod
    def validate_all(cls) -> bool:
        """Perform comprehensive configuration validation."""
        cls.validate_config()
        cls.validate_numeric_ranges()
        return True

    @classmethod
    def get_reddit_config(cls) -> RedditConfig:
        """Get validated Reddit configuration schema."""
        return RedditConfig(
            client_id=cls.REDDIT_CLIENT_ID or "",
            client_secret=cls.REDDIT_CLIENT_SECRET or "",
            user_agent=cls.REDDIT_USER_AGENT or "",
            username=cls.REDDIT_USERNAME,
            hot_posts_limit=cls.REDDIT_HOT_POSTS_LIMIT,
            relevant_posts_limit=cls.REDDIT_RELEVANT_POSTS_LIMIT,
            top_comments_limit=cls.REDDIT_TOP_COMMENTS_LIMIT,
            max_valid_posts=cls.REDDIT_MAX_VALID_POSTS,
            api_timeout=cls.REDDIT_API_TIMEOUT
        )

    @classmethod
    def get_openai_config(cls) -> OpenAIConfig:
        """Get validated OpenAI configuration schema."""
        return OpenAIConfig(
            api_key=cls.OPENAI_API_KEY or "",
            model=cls.OPENAI_MODEL,
            fallback_model=cls.OPENAI_FALLBACK_MODEL,
            max_tokens=cls.OPENAI_MAX_TOKENS,
            temperature=cls.OPENAI_TEMPERATURE,
            max_retries=cls.OPENAI_MAX_RETRIES,
            retry_delay=cls.OPENAI_RETRY_DELAY
        )

    @classmethod
    def get_scraper_config(cls) -> ScraperConfig:
        """Get validated scraper configuration schema."""
        return ScraperConfig(
            user_agent=cls.SCRAPER_USER_AGENT,
            timeout=cls.SCRAPER_TIMEOUT,
            max_retries=cls.SCRAPER_MAX_RETRIES,
            retry_delay=cls.SCRAPER_RETRY_DELAY,
            backoff_factor=cls.SCRAPER_BACKOFF_FACTOR
        )

    @classmethod
    def get_database_config(cls) -> DatabaseConfig:
        """Get validated database configuration schema."""
        return DatabaseConfig(
            url=cls.DATABASE_URL or "",
            pool_size=cls.DATABASE_POOL_SIZE,
            max_overflow=cls.DATABASE_MAX_OVERFLOW,
            pool_recycle=cls.DATABASE_POOL_RECYCLE,
            pool_timeout=cls.DATABASE_POOL_TIMEOUT,
            pool_pre_ping=cls.DATABASE_POOL_PRE_PING,
            pool_reset_on_return=cls.DATABASE_POOL_RESET_ON_RETURN,
            pool_invalid_on_exception=cls.DATABASE_POOL_INVALID_ON_EXCEPTION,
            pool_heartbeat_interval=cls.DATABASE_POOL_HEARTBEAT_INTERVAL,
            connect_timeout=cls.DATABASE_CONNECT_TIMEOUT,
            query_timeout=cls.DATABASE_QUERY_TIMEOUT,
            enable_pool_monitoring=cls.DATABASE_ENABLE_POOL_MONITORING,
            pool_size_max_threshold=cls.DATABASE_POOL_SIZE_MAX_THRESHOLD,
            pool_checkout_timeout=cls.DATABASE_POOL_CHECKOUT_TIMEOUT,
            pool_overflow_ratio_warning=cls.DATABASE_POOL_OVERFLOW_RATIO_WARNING
        )

    @classmethod
    def get_cache_config(cls) -> CacheConfig:
        """Get validated cache configuration schema."""
        return CacheConfig(
            max_size=cls.CACHE_MAX_SIZE,
            default_ttl=cls.CACHE_DEFAULT_TTL,
            enable_redis=cls.ENABLE_REDIS,
            redis_url=cls.REDIS_URL
        )

    @classmethod
    def get_logging_config(cls) -> LoggingConfig:
        """Get validated logging configuration schema."""
        level = cls.LOG_LEVEL
        if level not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            level = "INFO"

        return LoggingConfig(
            level=level,  # type: ignore
            format=cls.LOG_FORMAT,
            enable_structured=cls.ENABLE_STRUCTURED_LOGGING
        )

    @classmethod
    def get_rate_limit_config(cls) -> RateLimitConfig:
        """Get validated rate limiting configuration schema."""
        return RateLimitConfig(
            openai_rpm=cls.OPENAI_RATE_LIMIT_RPM,
            openai_tpm=cls.OPENAI_RATE_LIMIT_TPM,
            reddit_rpm=cls.REDDIT_RATE_LIMIT_RPM,
            scraper_rpm=cls.SCRAPER_RATE_LIMIT_RPM,
            burst_allowance=cls.RATE_LIMIT_BURST_ALLOWANCE,
            enabled=cls.ENABLE_RATE_LIMITING
        )

config = Config()
