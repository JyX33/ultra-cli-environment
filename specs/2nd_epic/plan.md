# Reddit Agent Enhancement - Development Plan

## Project Overview

This plan outlines the Test-Driven Development (TDD) approach for implementing persistence and change detection capabilities in the Reddit Agent. The enhancement enables tracking new content between checks through database storage and intelligent comparison algorithms.

## Architecture Summary

### Core Components

- **Database Layer**: SQLite/PostgreSQL with SQLAlchemy ORM
- **Storage Service**: CRUD operations and data persistence
- **Change Detection Service**: Delta calculation and trend analysis
- **Enhanced API**: New endpoints for updates and history
- **Report Generator**: Delta reports with change highlights

### Technical Stack

- SQLAlchemy 2.0+ for database operations
- Alembic for migrations
- FastAPI for API endpoints
- Python 3.9+ with type hints

## Development Chunks

### Chunk 1: Database Foundation & Models (3 steps)

**Objective**: Establish database infrastructure and ORM models

**Dependencies**: None (foundation layer)

**Steps**:

1. **Database Configuration & Connection** (Prompt 1)
   - Set up SQLAlchemy engine and session management
   - Configure database URLs for SQLite/PostgreSQL
   - Implement connection pooling and error handling
   - Test database connectivity

2. **Core Database Models** (Prompt 2)
   - Create ORM models for check_runs, reddit_posts
   - Implement proper relationships and constraints
   - Add indexes for performance
   - Test model creation and relationships

3. **Extended Models & Migrations** (Prompt 3)
   - Create models for comments, post_snapshots, article_content
   - Set up Alembic for migrations
   - Create initial migration scripts
   - Test migration execution

### Chunk 2: Storage Service Implementation (3 steps)

**Objective**: Build comprehensive data persistence layer

**Dependencies**: Chunk 1 (Database models)

**Steps**:
4. **Basic Storage Operations** (Prompt 4)

- Implement create_check_run, save_post methods
- Add transaction handling and rollback
- Create get_post_by_id, get_latest_check_run
- Test CRUD operations with mocks

5. **Advanced Storage Features** (Prompt 5)
   - Implement save_comment with relationship handling
   - Add save_post_snapshot for tracking changes
   - Create get_new_posts_since query
   - Test complex queries and relationships

6. **Data Retention & Cleanup** (Prompt 6)
   - Implement cleanup_old_data with configurable retention
   - Add batch operations for performance
   - Create database maintenance utilities
   - Test cleanup logic and edge cases

### Chunk 3: Change Detection Logic (3 steps)

**Objective**: Implement intelligent content comparison

**Dependencies**: Chunks 1-2 (Database and Storage)

**Steps**:
7. **Post Change Detection** (Prompt 7)

- Create find_new_posts method
- Implement find_updated_posts with delta calculation
- Add engagement metrics comparison
- Test detection accuracy

8. **Comment Analysis** (Prompt 8)
   - Implement find_new_comments for posts
   - Create comment tree comparison logic
   - Add sentiment change detection
   - Test comment tracking

9. **Trend Analysis** (Prompt 9)
   - Build calculate_engagement_delta method
   - Implement get_subreddit_trends with time windows
   - Create activity pattern detection
   - Test trend calculations

### Chunk 4: API Endpoints & Integration (3 steps)

**Objective**: Expose new functionality through REST API

**Dependencies**: Chunks 1-3 (All services)

**Steps**:
10. **Check Updates Endpoint** (Prompt 10)
    - Create /check-updates/{subreddit}/{topic} endpoint
    - Integrate with storage and change detection
    - Return delta information
    - Test API responses

11. **History & Trends Endpoints** (Prompt 11)
    - Implement /history/{subreddit} endpoint
    - Create /trends/{subreddit} endpoint
    - Add query parameters and filtering
    - Test pagination and filters

12. **Enhanced Report Generation** (Prompt 12)
    - Modify /generate-report to store data
    - Add include_history parameter
    - Integrate with storage service
    - Test backwards compatibility

### Chunk 5: Report Generation & Testing (3 steps)

**Objective**: Complete integration and comprehensive testing

**Dependencies**: All previous chunks

**Steps**:
13. **Delta Report Generator** (Prompt 13)
    - Create new report templates for changes
    - Implement change highlighting in markdown
    - Add trend summaries to reports
    - Test report formatting

14. **Integration Testing** (Prompt 14)
    - Create end-to-end test scenarios
    - Test full workflow from fetch to report
    - Verify data persistence across requests
    - Test concurrent operations

15. **Performance & Documentation** (Prompt 15)
    - Optimize database queries
    - Add caching layer
    - Update API documentation
    - Performance benchmarking

## Dependency Graph

```
Chunk 1 (Database Foundation)
    ↓
Chunk 2 (Storage Service)
    ↓
Chunk 3 (Change Detection)
    ↓
Chunk 4 (API Endpoints)
    ↓
Chunk 5 (Integration & Testing)
```

## Implementation Timeline

- **Week 1**: Chunks 1-2 (Database and Storage)
- **Week 2**: Chunks 3-4 (Detection and API)
- **Week 3**: Chunk 5 (Integration and Polish)

## Success Metrics

1. All unit tests pass with >95% coverage
2. Integration tests verify complete workflows
3. Performance benchmarks meet requirements:
   - < 2s response time for update checks
   - Support 1000+ posts per subreddit
4. Zero security vulnerabilities
5. Full backwards compatibility maintained

## Risk Mitigation

1. **Database Performance**: Early indexing and query optimization
2. **Memory Usage**: Streaming processing for large datasets
3. **API Compatibility**: Feature flags for gradual rollout
4. **Data Loss**: Comprehensive backup and migration testing

## Notes

- Each prompt follows TDD: write tests first, then implementation
- All code must integrate with existing codebase
- Maintain existing API contracts
- Use type hints throughout
- Follow project's code style and conventions
