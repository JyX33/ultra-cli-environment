# Reddit Agent Enhancement: Track New Content Since Last Check

## Project Overview

This specification outlines the enhancement of the AI Reddit News Agent to track and identify new content since its last check. The system will implement a persistence layer to store Reddit findings and enable efficient change detection, allowing users to see what's new in their monitored subreddits.

## Technical Architecture

### Database Design

**Technology Choice**: SQLite for development/lightweight deployments, with PostgreSQL support for production scalability.

**Database Schema**:

```sql
-- Track when checks were performed
CREATE TABLE check_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subreddit VARCHAR(100) NOT NULL,
    topic VARCHAR(255) NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    posts_found INTEGER DEFAULT 0,
    new_posts INTEGER DEFAULT 0,
    INDEX idx_subreddit_topic_time (subreddit, topic, timestamp)
);

-- Store Reddit post data
CREATE TABLE reddit_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id VARCHAR(20) UNIQUE NOT NULL,
    subreddit VARCHAR(100) NOT NULL,
    title TEXT NOT NULL,
    author VARCHAR(100),
    url TEXT,
    selftext TEXT,
    score INTEGER DEFAULT 0,
    num_comments INTEGER DEFAULT 0,
    created_utc DATETIME NOT NULL,
    first_seen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_updated DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_self BOOLEAN DEFAULT FALSE,
    post_summary TEXT,
    INDEX idx_post_id (post_id),
    INDEX idx_subreddit_time (subreddit, created_utc)
);

-- Store comment data
CREATE TABLE comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comment_id VARCHAR(20) UNIQUE NOT NULL,
    post_id VARCHAR(20) NOT NULL,
    author VARCHAR(100),
    body TEXT,
    score INTEGER DEFAULT 0,
    created_utc DATETIME NOT NULL,
    first_seen DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    parent_id VARCHAR(20),
    FOREIGN KEY (post_id) REFERENCES reddit_posts(post_id),
    INDEX idx_comment_id (comment_id),
    INDEX idx_post_comments (post_id, score DESC)
);

-- Track post changes over time
CREATE TABLE post_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id VARCHAR(20) NOT NULL,
    check_run_id INTEGER NOT NULL,
    score INTEGER,
    num_comments INTEGER,
    snapshot_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (post_id) REFERENCES reddit_posts(post_id),
    FOREIGN KEY (check_run_id) REFERENCES check_runs(id),
    INDEX idx_post_snapshots (post_id, snapshot_time)
);

-- Store scraped article content
CREATE TABLE article_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash VARCHAR(64) UNIQUE NOT NULL,
    url TEXT NOT NULL,
    content TEXT,
    scraped_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_url_hash (url_hash)
);
```

### New Service Components

#### 1. StorageService (`app/services/storage_service.py`)

**Responsibilities**:
- Database connection management
- CRUD operations for all entities
- Transaction handling
- Data retention/cleanup

**Key Methods**:
```python
class StorageService:
    def create_check_run(self, subreddit: str, topic: str) -> int
    def save_post(self, post_data: dict) -> None
    def save_comment(self, comment_data: dict, post_id: str) -> None
    def get_post_by_id(self, post_id: str) -> dict | None
    def get_latest_check_run(self, subreddit: str, topic: str) -> dict | None
    def get_new_posts_since(self, subreddit: str, timestamp: datetime) -> list[dict]
    def save_post_snapshot(self, post_id: str, check_run_id: int, score: int, num_comments: int) -> None
    def cleanup_old_data(self, days_to_keep: int = 30) -> None
```

#### 2. ChangeDetectionService (`app/services/change_detection_service.py`)

**Responsibilities**:
- Compare current data with stored data
- Identify new posts, comments, and changes
- Calculate deltas and trends

**Key Methods**:
```python
class ChangeDetectionService:
    def find_new_posts(self, current_posts: list, last_check_time: datetime) -> list
    def find_updated_posts(self, current_posts: list) -> list[PostUpdate]
    def find_new_comments(self, post_id: str, current_comments: list) -> list
    def calculate_engagement_delta(self, post_id: str) -> EngagementDelta
    def get_subreddit_trends(self, subreddit: str, days: int = 7) -> TrendData
```

#### 3. Enhanced ReportGeneratorService

**New Features**:
- Delta reports showing only new content
- Change highlights (score changes, new comments)
- Trend summaries

### API Enhancements

#### New Endpoints

1. **Check for Updates**: `GET /check-updates/{subreddit}/{topic}`
   - Returns only new/changed content since last check
   - Response includes new posts, updated posts, and new comments

2. **View History**: `GET /history/{subreddit}`
   - Returns past check runs with statistics
   - Optional date range filtering

3. **Get Trends**: `GET /trends/{subreddit}`
   - Returns engagement trends over time
   - Useful for identifying best posting times

#### Modified Endpoints

1. **Generate Report**: `GET /generate-report/{subreddit}/{topic}`
   - Now stores all fetched data
   - Adds `include_history` parameter to show changes

### Data Flow

1. **Initial Check**:
   ```
   User Request → Fetch Reddit Data → Store in DB → Generate Report
   ```

2. **Update Check**:
   ```
   User Request → Fetch Reddit Data → Compare with DB → 
   Store Updates → Generate Delta Report
   ```

### Implementation Plan

#### Phase 1: Database Foundation (2 days)
- [ ] Add SQLAlchemy and alembic dependencies
- [ ] Create database models
- [ ] Write migration scripts
- [ ] Implement StorageService with tests

#### Phase 2: Data Collection (2 days)
- [ ] Update RedditService to use StorageService
- [ ] Modify scraper to cache article content
- [ ] Update main.py endpoints to store data
- [ ] Add data retention job

#### Phase 3: Change Detection (3 days)
- [ ] Implement ChangeDetectionService
- [ ] Create delta calculation logic
- [ ] Add trend analysis
- [ ] Write comprehensive tests

#### Phase 4: API & Reporting (2 days)
- [ ] Add new API endpoints
- [ ] Enhance report generator for deltas
- [ ] Create new report templates
- [ ] Update existing endpoints

#### Phase 5: Testing & Optimization (1 day)
- [ ] End-to-end testing
- [ ] Performance optimization
- [ ] Documentation updates
- [ ] Docker configuration updates

### Configuration Updates

**New Environment Variables**:
```bash
DATABASE_URL=sqlite:///./reddit_agent.db  # or postgresql://...
DATA_RETENTION_DAYS=30
ENABLE_CHANGE_TRACKING=true
```

**Updated Dependencies** (`pyproject.toml`):
```toml
dependencies = [
    # ... existing dependencies ...
    "sqlalchemy>=2.0.0",
    "alembic>=1.13.0",
    "python-dateutil>=2.8.0",
]
```

### Testing Strategy

1. **Unit Tests**:
   - StorageService CRUD operations
   - ChangeDetectionService logic
   - Database transaction handling

2. **Integration Tests**:
   - Full data flow with persistence
   - API endpoint testing with database
   - Change detection accuracy

3. **Performance Tests**:
   - Query performance with large datasets
   - Memory usage during processing
   - Concurrent request handling

### Data Retention Policy

- Keep full post/comment data for 30 days
- Keep aggregated statistics indefinitely
- Archive old check runs after 90 days
- Implement configurable retention periods

### Migration Strategy

1. **Existing Deployments**:
   - Database migrations run automatically on startup
   - Backwards compatible API (existing endpoints unchanged)
   - Feature flag for change tracking

2. **New Features Opt-in**:
   - Change tracking disabled by default
   - Enable via environment variable
   - Gradual rollout possible

### Security Considerations

1. **SQL Injection Prevention**:
   - Use parameterized queries
   - SQLAlchemy ORM for query building
   - Input validation on all user data

2. **Data Privacy**:
   - No storage of personal Reddit user data
   - Configurable data retention
   - Option to anonymize old data

### Performance Optimization

1. **Database Indexes**:
   - Index on post_id for fast lookups
   - Composite index on (subreddit, timestamp)
   - Index on comment scores for sorting

2. **Caching Strategy**:
   - Cache recent check results
   - Memory-efficient comment processing
   - Batch database operations

3. **Query Optimization**:
   - Limit full-text searches
   - Use pagination for large results
   - Optimize N+1 query problems

### Success Criteria

1. **Functional Requirements**:
   - ✓ Track all Reddit posts/comments in database
   - ✓ Identify new content since last check
   - ✓ Generate delta reports
   - ✓ Show engagement trends

2. **Performance Requirements**:
   - < 2s response time for update checks
   - Support 1000+ posts per subreddit
   - Handle 10 concurrent users

3. **Quality Requirements**:
   - 95%+ test coverage
   - No security vulnerabilities
   - Clear documentation

### Future Enhancements

1. **Notification System**:
   - Email/webhook alerts for new content
   - Configurable thresholds

2. **Advanced Analytics**:
   - Sentiment analysis trends
   - Engagement prediction
   - Best time to post analysis

3. **Multi-user Support**:
   - User accounts and preferences
   - Personalized tracking lists
   - Sharing capabilities

## Acceptance Criteria

The implementation will be considered complete when:

1. All database models are created and tested
2. StorageService handles all CRUD operations
3. ChangeDetectionService accurately identifies changes
4. New API endpoints return correct delta information
5. Reports clearly show new vs existing content
6. All tests pass with >95% coverage
7. Documentation is updated
8. Performance meets specified requirements