# End-to-End API Testing

This directory contains comprehensive end-to-end tests that verify the AI Reddit Agent APIs using real Docker containers and actual external API services.

## Overview

These tests follow the project's "no mocks" philosophy by using:

- **Real Docker containers** for the application services
- **Actual Reddit API calls** with real credentials
- **Real OpenAI API integration** for summarization
- **Real PostgreSQL database** for data persistence
- **Real Redis caching** for performance testing

## Test Coverage

### Standard API Endpoints (`app.main`)

- `GET /` - Health check
- `GET /discover-subreddits/{topic}` - Subreddit discovery with "Claude Code"
- `GET /generate-report/{subreddit}/{topic}` - Report generation for "ClaudeAI/Claude Code"
- `GET /check-updates/{subreddit}/{topic}` - Change detection for "ClaudeAI/Claude Code"
- `GET /history/{subreddit}` - Historical data retrieval
- `GET /trends/{subreddit}` - Trend analysis
- `GET /debug/relevance/{topic}` - Debug relevance scoring
- `GET /debug/reddit-api` - Reddit API connectivity test

### Optimized API Endpoints (`app.main_optimized`)

- `GET /performance/stats` - Real-time performance metrics
- `GET /performance/report` - Detailed performance analysis
- `POST /performance/reset` - Reset performance counters
- `GET /check-updates/{subreddit}/{topic}` - Optimized change detection
- `GET /trending/{subreddit}` - Cached trending posts
- `GET /analytics/{subreddit}` - Advanced analytics
- `POST /optimize-database` - Database optimization
- `GET /discover-subreddits/{topic}` - Cached subreddit discovery

### Cross-API Testing

- Consistency between standard and optimized APIs
- Performance comparison verification
- Cache behavior validation

### Error Handling

- Invalid input rejection
- Malicious input sanitization
- API failure graceful handling

## Setup Requirements

### 1. Real API Credentials

Create `tests/e2e/.env.test` with your actual API credentials:

```env
# Reddit API Credentials
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=TestBot/1.0 by YourUsername

# OpenAI API Key
OPENAI_API_KEY=sk-your-openai-api-key

# Test Database (automatically configured)
DATABASE_URL=postgresql://testuser:testpass@postgres:5432/testdb
REDIS_URL=redis://redis:6379/0
ENABLE_REDIS=true
ENABLE_PERFORMANCE_MONITORING=true
```

### 2. Docker Requirements

Ensure Docker and Docker Compose are installed and running:

```bash
# Verify Docker is running
docker --version
docker-compose --version

# Ensure Docker daemon is started
sudo systemctl start docker  # Linux
# or
open -a Docker  # macOS
```

## Running the Tests

### Full E2E Test Suite

```bash
# Run all E2E tests with real APIs
uv run pytest tests/e2e/ -v

# Run with detailed output and no capture
uv run pytest tests/e2e/ -v -s

# Run specific test class
uv run pytest tests/e2e/test_real_api_endpoints.py::TestStandardAPIEndpoints -v

# Run single test
uv run pytest tests/e2e/test_real_api_endpoints.py::TestStandardAPIEndpoints::test_discover_subreddits_real_api -v
```

### Test Categories

```bash
# Test standard API only
uv run pytest tests/e2e/ -k "TestStandardAPIEndpoints" -v

# Test optimized API only  
uv run pytest tests/e2e/ -k "TestOptimizedAPIEndpoints" -v

# Test error handling
uv run pytest tests/e2e/ -k "TestErrorHandling" -v

# Test cross-API consistency
uv run pytest tests/e2e/ -k "TestCrossAPIConsistency" -v
```

## Test Behavior

### Docker Container Management

- Tests automatically start Docker Compose services
- PostgreSQL and Redis containers are health-checked
- Both standard and optimized API servers are started
- Containers are automatically cleaned up after tests

### Database Isolation

- Each test gets a clean database state
- Data is automatically cleaned before and after tests
- Schema is preserved between tests

### Rate Limiting

- Tests include delays to respect Reddit API limits
- 2-second delays between tests to avoid rate limiting
- Extended timeouts (120s) for real API calls

### Real API Integration

- Actual Reddit API calls for subreddit discovery and post fetching
- Real OpenAI API calls for content summarization
- Genuine Redis caching behavior testing
- Authentic PostgreSQL database operations

## Expected Test Results

### Success Cases

- **API Discovery**: Should find relevant subreddits for "Claude Code"
- **Report Generation**: Should create markdown reports for "ClaudeAI" subreddit
- **Change Detection**: Should track real engagement changes over time
- **Performance Metrics**: Should show measurable cache hit rates and response times

### Acceptable Failures

- **404 Responses**: If "ClaudeAI" subreddit doesn't exist or has no recent posts
- **Rate Limit Errors**: If Reddit API quota is exceeded
- **API Quota Errors**: If OpenAI API credits are insufficient

### Error Validation

- **Malicious Input**: Should reject XSS, SQL injection, and path traversal attempts
- **Invalid Subreddits**: Should handle non-existent subreddits gracefully
- **Network Failures**: Should fail gracefully if external APIs are unavailable

## Debugging

### View Container Logs

```bash
# View application logs
docker-compose -f docker-compose.test.yml logs app

# View database logs
docker-compose -f docker-compose.test.yml logs postgres

# View all service logs
docker-compose -f docker-compose.test.yml logs
```

### Test with Debug Output

```bash
# Run with maximum verbosity
uv run pytest tests/e2e/ -v -s --tb=long --log-cli-level=DEBUG
```

### Manual Container Testing

```bash
# Start test environment manually
docker-compose -f docker-compose.test.yml up

# Test endpoints manually
curl http://localhost:8000/
curl http://localhost:8000/discover-subreddits/Claude%20Code
curl http://localhost:8001/performance/stats

# Cleanup
docker-compose -f docker-compose.test.yml down
```

## Cost Considerations

These tests use real APIs which may incur costs:

- **Reddit API**: Free tier with rate limits
- **OpenAI API**: Charges per token used
- **Docker Resources**: Local compute and storage

Monitor your API usage and costs when running these tests frequently.
