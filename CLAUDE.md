# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **AI Reddit News Agent** - a production-ready Python application that automates finding relevant Reddit discussions and generates comprehensive reports with AI-powered analysis. The system uses FastAPI, PRAW (Reddit API), web scraping, and OpenAI summarization to create detailed Markdown reports from Reddit posts and comments.

## Architecture

The application follows a modular FastAPI architecture with two deployment modes:

- **Standard API** (`app/main.py`): Full-featured application with all services
- **Optimized API** (`app/main_optimized.py`): Performance-optimized version with multi-tier caching and query optimization

### Key Components

- `app/services/reddit_service.py` - Reddit API interactions and subreddit discovery
- `app/services/scraper_service.py` - Web scraping for external article content
- `app/services/summarizer_service.py` - OpenAI-powered content summarization
- `app/services/storage_service.py` - Database operations with SQLAlchemy
- `app/services/cache_service.py` - Multi-tier caching (Redis + in-memory)
- `app/services/performance_monitoring_service.py` - Real-time performance tracking
- `app/utils/relevance.py` - Subreddit relevance scoring algorithms
- `app/utils/report_generator.py` - Basic Markdown report generation
- `app/utils/delta_report_generator.py` - Jinja2 templated reports with change detection

## Development Commands

### Package Management
Use `uv` for all Python package management and command execution:

```bash
# Install dependencies
uv sync

# Install with development and performance extras
uv sync --extra dev --extra performance

# Run any command through uv
uv run <command>
```

### Application Startup
```bash
# Standard API server
uv run uvicorn app.main:app --reload

# Performance-optimized API (recommended for development)
uv run uvicorn app.main_optimized:app --reload
```

### Database Management
```bash
# Apply database migrations
uv run alembic upgrade head

# Create new migration
uv run alembic revision --autogenerate -m "description"

# Downgrade to previous migration
uv run alembic downgrade -1
```

### Testing Strategy

This project follows **Test-Driven Development (TDD)** with comprehensive coverage:

```bash
# Run all tests with coverage
uv run pytest --cov=app

# Run specific test categories
uv run pytest tests/integration/     # End-to-end workflows
uv run pytest tests/performance/     # Performance benchmarks
uv run pytest tests/security/        # Security validation
uv run pytest tests/services/        # Unit tests

# Run single test file
uv run pytest tests/services/test_reddit_service.py

# Run with verbose output
uv run pytest -v
```

### Code Quality Pipeline
```bash
# Format code (run first)
uv run ruff format app/ tests/

# Fix linting issues
uv run ruff check app/ tests/ --fix

# Type checking (100% coverage required)
uv run mypy app/

# Run complete quality check pipeline
uv run mypy app/ && uv run ruff check app/ tests/
```

### Docker Deployment
```bash
# Full stack with Docker Compose
docker-compose up --build

# Manual container build
docker build -t ai-reddit-agent .
docker run -p 8000:8000 --env-file .env ai-reddit-agent
```

## API Workflow

The core content processing flow:

1. **Discovery**: `GET /discover-subreddits/{topic}` → score relevance → user selects subreddit
2. **Content Fetching**: Fetch top 5 posts (last 24h, sorted by comment count)
3. **Content Processing**: Filter media posts → extract content → scrape articles if needed
4. **AI Summarization**: Generate summaries for post content and top comments
5. **Report Generation**: `GET /generate-report/{subreddit}/{topic}` → downloadable Markdown
6. **Change Tracking**: `GET /check-updates/{subreddit}/{topic}` → delta reports

## Error Handling Standards

- **API Rate Limits**: Exponential backoff with jitter
- **Failed Scraping**: Return "Could not retrieve article content." 
- **Failed AI Summarization**: Return "AI summary could not be generated."
- **No Results Found**: Specific error messages for UI handling
- **Database Errors**: Automatic retry with connection pooling

## Environment Configuration

Required environment variables:
```env
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=your_app/1.0
OPENAI_API_KEY=your_openai_api_key
```

Optional performance configuration:
```env
DATABASE_URL=postgresql://user:pass@localhost/dbname  # Production
REDIS_URL=redis://localhost:6379  # Caching
ENABLE_PERFORMANCE_MONITORING=true
```

## Performance Optimizations

The optimized API (`main_optimized.py`) includes:

- **Query Optimization**: 70% reduction in database queries
- **Multi-tier Caching**: Redis + in-memory with 78% cache hit rate  
- **Response Time**: 56% improvement (3.2s → 1.4s average)
- **Memory Efficiency**: 60% reduction in usage
- **Real-time Monitoring**: Performance metrics at `/performance/stats`

## Code Quality Standards

- **Type Safety**: 100% MyPy coverage with strict settings
- **Test Coverage**: 100% line coverage requirement across all test types
- **Security**: Built-in SQL injection prevention and input validation
- **Formatting**: Ruff formatter with automatic fixing
- **Documentation**: All services have comprehensive docstrings

## Testing Requirements

Every component must have:
- **Unit Tests**: Individual function testing with comprehensive mocking
- **Integration Tests**: Complete workflow testing with realistic scenarios
- **Performance Tests**: Benchmarking for optimization validation
- **Security Tests**: Input validation and vulnerability scanning

Use `tests/fixtures/` for centralized mocking and test data management.