# API Reference

The AI Reddit Agent provides both standard and optimized API endpoints for Reddit content analysis and performance monitoring.

## Base URLs

- **Standard API**: `http://localhost:8000` (from `app.main`)
- **Optimized API**: `http://localhost:8000` (from `app.main_optimized`)

## Authentication

Currently, the API does not require authentication. In production, consider implementing:
- API key authentication
- Rate limiting per user/IP
- OAuth2 for user-specific operations

## Rate Limiting

The optimized API includes built-in rate limiting:
- **Default**: 10 requests per minute per IP
- **Burst**: Up to 20 requests in short bursts
- **Headers**: Rate limit information in response headers

## Standard Endpoints

### Discover Subreddits

Discover relevant subreddits for a given topic.

```http
GET /discover-subreddits/{topic}
```

**Parameters:**
- `topic` (string, required): Topic to search for (max 100 characters)

**Response:**
```json
{
  "topic": "artificial intelligence",
  "subreddits": [
    {
      "name": "MachineLearning",
      "description": "Machine Learning community",
      "subscribers": 2500000,
      "relevance_score": 0.95
    }
  ]
}
```

**Response Codes:**
- `200`: Success
- `400`: Invalid topic parameter
- `500`: Server error

### Generate Report

Generate a comprehensive markdown report for Reddit discussions.

```http
GET /generate-report/{subreddit}/{topic}
```

**Parameters:**
- `subreddit` (string, required): Target subreddit name
- `topic` (string, required): Topic to analyze
- `store_data` (boolean, optional): Whether to store data in database (default: false)
- `include_history` (boolean, optional): Include historical data (default: false)

**Response:**
```http
Content-Type: application/octet-stream
Content-Disposition: attachment; filename="report.md"

[Markdown report content as downloadable file]
```

**Response Codes:**
- `200`: Success - returns downloadable markdown file
- `400`: Invalid parameters
- `500`: Server error

### Check Updates

Check for new and updated posts since last check.

```http
GET /check-updates/{subreddit}/{topic}
```

**Parameters:**
- `subreddit` (string, required): Target subreddit name
- `topic` (string, required): Topic to monitor

**Response:**
```json
{
  "subreddit": "python",
  "topic": "performance",
  "check_timestamp": "2025-06-17T17:16:54.123456Z",
  "new_posts": [
    {
      "post_id": "abc123",
      "title": "Performance optimization tips",
      "score": 156,
      "comment_count": 23,
      "url": "https://reddit.com/r/python/comments/abc123/",
      "is_new": true,
      "engagement_delta": null
    }
  ],
  "updated_posts": [
    {
      "post_id": "def456",
      "title": "Previous post with updates",
      "score": 203,
      "comment_count": 45,
      "url": "https://reddit.com/r/python/comments/def456/",
      "is_new": false,
      "engagement_delta": {
        "score_change": 47,
        "comment_change": 12,
        "trending": "trending_up"
      }
    }
  ],
  "new_comments": [],
  "summary": {
    "total_new_posts": 1,
    "total_updated_posts": 1,
    "total_new_comments": 0,
    "check_run_id": 42
  },
  "trend_summary": null
}
```

### History

Get historical check runs for a subreddit.

```http
GET /history/{subreddit}
```

**Parameters:**
- `subreddit` (string, required): Target subreddit name
- `start_date` (string, optional): ISO datetime string (e.g., "2025-06-10T00:00:00Z")
- `end_date` (string, optional): ISO datetime string
- `page` (integer, optional): Page number (default: 1)
- `limit` (integer, optional): Items per page (default: 20, max: 100)

**Response:**
```json
{
  "subreddit": "python",
  "check_runs": [
    {
      "id": 42,
      "topic": "performance",
      "timestamp": "2025-06-17T17:16:54.123456Z",
      "posts_found": 15,
      "new_posts": 3
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 1,
    "pages": 1
  },
  "date_range": {
    "start": "2025-06-10T00:00:00Z",
    "end": "2025-06-17T23:59:59Z"
  }
}
```

### Trends

Get trend analysis for a subreddit.

```http
GET /trends/{subreddit}
```

**Parameters:**
- `subreddit` (string, required): Target subreddit name
- `days` (integer, optional): Analysis period in days (default: 7, max: 90)

**Response:**
```json
{
  "subreddit": "python",
  "analysis_period_days": 7,
  "post_count": 45,
  "average_score": 156.7,
  "total_comments": 1234,
  "activity_pattern": "INCREASING",
  "best_post_time": {
    "hour": 14,
    "description": "2 PM UTC"
  },
  "engagement_forecast": {
    "predicted_posts": 52,
    "predicted_engagement": 1.15,
    "confidence": 0.78
  },
  "trend_summary": {
    "direction": "improving",
    "magnitude": 15.3
  }
}
```

## Optimized Endpoints

The optimized API includes additional performance and monitoring endpoints.

### Performance Statistics

Get current performance metrics.

```http
GET /performance/stats
```

**Response:**
```json
{
  "performance": {
    "request_metrics": {
      "total_requests": 1547,
      "average_response_time_ms": 1247.3,
      "database_queries": 4891,
      "queries_per_request": 3.16
    },
    "cache_metrics": {
      "hits": 1205,
      "misses": 342,
      "hit_rate": 0.779
    },
    "system_metrics": {
      "cpu_usage_percent": 45.2,
      "memory_usage_mb": 324.7,
      "memory_usage_percent": 63.4
    },
    "thresholds": {
      "max_response_time_ms": 2000.0,
      "max_memory_usage_mb": 512.0,
      "max_cpu_usage_percent": 80.0,
      "min_cache_hit_rate": 0.7
    },
    "alerts_count": 0,
    "active_alerts": []
  },
  "cache": {
    "in_memory_cache": {
      "hits": 856,
      "misses": 234,
      "hit_rate": 0.785,
      "memory_usage_mb": 15.7
    },
    "redis_cache": {
      "memory_used_mb": 45.2,
      "connected": true
    }
  },
  "timestamp": "2025-06-17T17:16:54.123456Z"
}
```

### Performance Report

Get detailed performance report with trends.

```http
GET /performance/report
```

**Response:**
```json
{
  "summary": {
    "request_metrics": {
      "total_requests": 1547,
      "average_response_time_ms": 1247.3
    },
    "cache_metrics": {
      "hit_rate": 0.779
    },
    "system_metrics": {
      "cpu_usage_percent": 45.2,
      "memory_usage_mb": 324.7
    }
  },
  "trends": {
    "analysis_period_minutes": 30,
    "trends": {
      "request_response_time": {
        "direction": "improving",
        "magnitude_percent": 12.5,
        "current_average": 1247.3,
        "previous_average": 1423.8
      },
      "cache_hit_rate": {
        "direction": "improving",
        "magnitude_percent": 5.2,
        "current_average": 0.779,
        "previous_average": 0.741
      }
    }
  },
  "recent_metrics": [
    {
      "name": "request_response_time",
      "value": 1245.0,
      "unit": "ms",
      "timestamp": "2025-06-17T17:16:54.123456Z",
      "tags": {
        "endpoint": "/check-updates/python/performance"
      }
    }
  ],
  "generated_at": "2025-06-17T17:16:54.123456Z"
}
```

### Reset Performance Counters

Reset performance monitoring counters.

```http
POST /performance/reset
```

**Response:**
```json
{
  "message": "Performance counters reset"
}
```

### Trending Posts (Optimized)

Get trending posts using optimized database queries.

```http
GET /trending/{subreddit}
```

**Parameters:**
- `subreddit` (string, required): Target subreddit name
- `hours` (integer, optional): Time window in hours (default: 24)

**Response:**
```json
{
  "subreddit": "python",
  "time_window_hours": 24,
  "trending_posts": [
    {
      "post_id": "trending123",
      "score": 456,
      "num_comments": 67,
      "actual_comments": 67,
      "age_hours": 8.5,
      "trending_score": 53.6
    }
  ],
  "generated_at": "2025-06-17T17:16:54.123456Z"
}
```

### Subreddit Analytics

Get detailed analytics with database-level aggregations.

```http
GET /analytics/{subreddit}
```

**Parameters:**
- `subreddit` (string, required): Target subreddit name
- `days` (integer, optional): Analysis period (default: 7, max: 90)

**Response:**
```json
{
  "subreddit": "python",
  "analysis_period_days": 7,
  "statistics": {
    "total_posts": 143,
    "total_comments": 2847,
    "average_score": 167.3,
    "average_engagement_ratio": 0.234
  },
  "top_posts": [
    {
      "post_id": "top123",
      "title": "Amazing Python trick",
      "score": 1256,
      "comment_count": 89,
      "engagement_ratio": 0.708
    }
  ],
  "generated_at": "2025-06-17T17:16:54.123456Z"
}
```

### Database Optimization

Trigger database optimization procedures.

```http
POST /optimize-database
```

**Response:**
```json
{
  "optimization_result": {
    "success": true,
    "optimizations_applied": [
      "SQLite PRAGMA optimize",
      "SQLite ANALYZE"
    ]
  },
  "duration_ms": 234.5,
  "timestamp": "2025-06-17T17:16:54.123456Z"
}
```

## Response Headers

### Standard Headers

All responses include standard HTTP headers:

```http
Content-Type: application/json
Content-Length: 1234
Date: Mon, 17 Jun 2025 17:16:54 GMT
```

### Performance Headers (Optimized API)

The optimized API adds performance-related headers:

```http
X-Response-Time: 1247.30ms
X-Cache-Service: enabled
X-Query-Count: 3
X-Cache-Hit-Rate: 0.779
```

### Rate Limiting Headers

When rate limiting is active:

```http
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1624821414
```

## Error Responses

### Error Format

All errors follow a consistent format:

```json
{
  "detail": "Error description",
  "error_code": "VALIDATION_ERROR",
  "timestamp": "2025-06-17T17:16:54.123456Z"
}
```

### Common Error Codes

| Status | Code | Description |
|--------|------|-------------|
| 400 | `VALIDATION_ERROR` | Invalid input parameters |
| 400 | `INVALID_SUBREDDIT` | Subreddit name contains invalid characters |
| 400 | `TOPIC_TOO_LONG` | Topic exceeds maximum length |
| 429 | `RATE_LIMIT_EXCEEDED` | Too many requests |
| 500 | `REDDIT_API_ERROR` | Reddit API is unavailable |
| 500 | `DATABASE_ERROR` | Database operation failed |
| 500 | `CACHE_ERROR` | Cache operation failed |
| 503 | `SERVICE_UNAVAILABLE` | Service temporarily unavailable |

### Error Examples

**Validation Error:**
```json
{
  "detail": "topic cannot be empty",
  "error_code": "VALIDATION_ERROR",
  "timestamp": "2025-06-17T17:16:54.123456Z"
}
```

**Rate Limit Exceeded:**
```json
{
  "detail": "Rate limit exceeded: 10 per 1 minute",
  "error_code": "RATE_LIMIT_EXCEEDED",
  "timestamp": "2025-06-17T17:16:54.123456Z"
}
```

**Server Error:**
```json
{
  "detail": "Failed to connect to Reddit API",
  "error_code": "REDDIT_API_ERROR",
  "timestamp": "2025-06-17T17:16:54.123456Z"
}
```

## OpenAPI/Swagger Documentation

Interactive API documentation is available at:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

## SDK Examples

### Python

```python
import requests
from typing import Dict, List, Optional

class RedditAgentClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
    
    def discover_subreddits(self, topic: str) -> Dict:
        """Discover relevant subreddits for a topic."""
        response = self.session.get(f"{self.base_url}/discover-subreddits/{topic}")
        response.raise_for_status()
        return response.json()
    
    def check_updates(self, subreddit: str, topic: str) -> Dict:
        """Check for updates in a subreddit."""
        response = self.session.get(f"{self.base_url}/check-updates/{subreddit}/{topic}")
        response.raise_for_status()
        return response.json()
    
    def get_performance_stats(self) -> Dict:
        """Get performance statistics (optimized API only)."""
        response = self.session.get(f"{self.base_url}/performance/stats")
        response.raise_for_status()
        return response.json()
    
    def generate_report(self, subreddit: str, topic: str, 
                       store_data: bool = False) -> bytes:
        """Generate and download markdown report."""
        params = {"store_data": store_data}
        response = self.session.get(
            f"{self.base_url}/generate-report/{subreddit}/{topic}",
            params=params
        )
        response.raise_for_status()
        return response.content

# Usage example
client = RedditAgentClient("http://localhost:8000")

# Discover subreddits
subreddits = client.discover_subreddits("machine learning")
print(f"Found {len(subreddits['subreddits'])} relevant subreddits")

# Check for updates
updates = client.check_updates("MachineLearning", "transformers")
print(f"Found {updates['summary']['total_new_posts']} new posts")

# Get performance stats (if using optimized API)
try:
    stats = client.get_performance_stats()
    print(f"Average response time: {stats['performance']['request_metrics']['average_response_time_ms']:.1f}ms")
except requests.exceptions.HTTPError:
    print("Performance stats not available (using standard API)")
```

### JavaScript/Node.js

```javascript
class RedditAgentClient {
    constructor(baseUrl = 'http://localhost:8000') {
        this.baseUrl = baseUrl.replace(/\/$/, '');
    }
    
    async discoverSubreddits(topic) {
        const response = await fetch(`${this.baseUrl}/discover-subreddits/${topic}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return response.json();
    }
    
    async checkUpdates(subreddit, topic) {
        const response = await fetch(`${this.baseUrl}/check-updates/${subreddit}/${topic}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return response.json();
    }
    
    async getPerformanceStats() {
        const response = await fetch(`${this.baseUrl}/performance/stats`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return response.json();
    }
    
    async generateReport(subreddit, topic, storeData = false) {
        const params = new URLSearchParams({ store_data: storeData });
        const response = await fetch(
            `${this.baseUrl}/generate-report/${subreddit}/${topic}?${params}`
        );
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        return response.blob();
    }
}

// Usage example
const client = new RedditAgentClient('http://localhost:8000');

// Discover subreddits
client.discoverSubreddits('artificial intelligence')
    .then(data => {
        console.log(`Found ${data.subreddits.length} relevant subreddits`);
    })
    .catch(error => {
        console.error('Error:', error.message);
    });

// Check for updates
client.checkUpdates('MachineLearning', 'neural networks')
    .then(data => {
        console.log(`Found ${data.summary.total_new_posts} new posts`);
    })
    .catch(error => {
        console.error('Error:', error.message);
    });
```

### cURL Examples

```bash
# Discover subreddits
curl -X GET "http://localhost:8000/discover-subreddits/python" \
     -H "Accept: application/json"

# Check updates
curl -X GET "http://localhost:8000/check-updates/python/performance" \
     -H "Accept: application/json"

# Generate report
curl -X GET "http://localhost:8000/generate-report/python/async?store_data=true" \
     -H "Accept: application/octet-stream" \
     -o "python_async_report.md"

# Get performance stats (optimized API)
curl -X GET "http://localhost:8000/performance/stats" \
     -H "Accept: application/json"

# Get trending posts
curl -X GET "http://localhost:8000/trending/python?hours=48" \
     -H "Accept: application/json"

# Reset performance counters
curl -X POST "http://localhost:8000/performance/reset" \
     -H "Accept: application/json"
```

## Webhooks (Future Feature)

Planned webhook support for real-time notifications:

```json
{
  "webhook_url": "https://your-app.com/webhooks/reddit-updates",
  "events": ["new_posts", "trending_changes"],
  "subreddit": "python",
  "topic": "performance"
}
```

## GraphQL Support (Future Feature)

Planned GraphQL endpoint for flexible data querying:

```graphql
query {
  subreddit(name: "python") {
    posts(topic: "performance", limit: 10) {
      id
      title
      score
      comments {
        id
        body
        score
      }
    }
    trends(days: 7) {
      activityPattern
      averageScore
    }
  }
}
```

This API reference provides comprehensive documentation for both standard and optimized endpoints, with examples in multiple programming languages.