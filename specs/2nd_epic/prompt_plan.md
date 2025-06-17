# Implementation Prompts

## Prompt 1: Database Configuration & Connection

```prompt
Create the database configuration and connection management for the Reddit Agent enhancement.

Context:
- Project uses FastAPI with existing configuration in app/core/config.py
- Need to support both SQLite (development) and PostgreSQL (production)
- Must integrate with existing project structure

Requirements:
1. First, write comprehensive tests for database configuration and connection:
   - Test SQLite connection creation
   - Test PostgreSQL connection creation
   - Test connection pooling behavior
   - Test error handling for invalid configurations
   - Test session lifecycle management

2. Then implement:
   - Add SQLAlchemy to pyproject.toml dependencies
   - Create app/db/__init__.py
   - Create app/db/base.py with Base declarative class
   - Create app/db/session.py with engine and session management
   - Update app/core/config.py with database configuration:
     - DATABASE_URL (with SQLite default)
     - Connection pool settings
   - Create get_db dependency for FastAPI endpoints

3. Ensure:
   - Proper connection pooling for production
   - SQLite configuration for local development
   - Error handling for connection failures
   - Type hints throughout
   - Integration with existing config pattern

Success Criteria:
- All tests pass
- Can connect to SQLite database
- Configuration supports PostgreSQL URL
- Sessions properly managed and closed
- No import errors with existing code
```

## Prompt 2: Core Database Models

```prompt
Create the core database models for tracking Reddit posts and check runs.

Context:
- Database configuration from Prompt 1 is complete
- Need models for check_runs and reddit_posts tables
- Must use SQLAlchemy ORM with proper relationships

Requirements:
1. First, write tests for the models:
   - Test CheckRun model creation and fields
   - Test RedditPost model creation and fields
   - Test model relationships
   - Test unique constraints
   - Test index creation
   - Test timestamp defaults

2. Then implement:
   - Create app/models/__init__.py
   - Create app/models/check_run.py with CheckRun model:
     - id, subreddit, topic, timestamp
     - posts_found, new_posts counters
     - Proper indexes
   - Create app/models/reddit_post.py with RedditPost model:
     - All fields from specification
     - Unique constraint on post_id
     - Indexes for performance
   - Add models to app/db/base.py imports

3. Ensure:
   - Proper SQLAlchemy column types
   - DateTime handling with UTC
   - Index definitions for queries
   - Type hints on all fields
   - __repr__ methods for debugging

Success Criteria:
- Models can be instantiated and saved
- Relationships work correctly
- Indexes are created in database
- All fields have correct types
- Tests verify all constraints
```

## Prompt 3: Extended Models & Migrations

```prompt
Complete the database models and set up Alembic migrations.

Context:
- Core models (CheckRun, RedditPost) exist from Prompt 2
- Need remaining models and migration system
- Must maintain referential integrity

Requirements:
1. First, write tests:
   - Test Comment model with foreign keys
   - Test PostSnapshot model relationships
   - Test ArticleContent model with URL hashing
   - Test migration execution
   - Test rollback functionality

2. Then implement:
   - Add alembic to dependencies
   - Create app/models/comment.py:
     - Foreign key to reddit_posts
     - Cascade delete behavior
   - Create app/models/post_snapshot.py:
     - Foreign keys to posts and check_runs
   - Create app/models/article_content.py:
     - URL hash generation
     - Unique constraint
   - Initialize Alembic:
     - alembic init alembic
     - Configure alembic.ini
     - Update env.py for models
   - Create initial migration

3. Ensure:
   - All foreign keys properly defined
   - Cascade deletes where appropriate
   - Migration runs successfully
   - Rollback works correctly
   - Hash function for URLs

Success Criteria:
- All models created successfully
- Migrations run without errors
- Foreign key constraints enforced
- Can rollback migrations
- URL deduplication works
```

## Prompt 4: Basic Storage Operations

```prompt
Implement the StorageService with basic CRUD operations.

Context:
- All database models exist from Prompts 1-3
- Need service layer for data persistence
- Must handle transactions properly

Requirements:
1. First, write comprehensive tests:
   - Test create_check_run returns ID
   - Test save_post with all fields
   - Test get_post_by_id retrieval
   - Test get_latest_check_run logic
   - Test transaction rollback on error
   - Test duplicate post handling

2. Then implement:
   - Create app/services/storage_service.py
   - Implement StorageService class:
     - __init__ with session dependency
     - create_check_run(subreddit, topic)
     - save_post(post_data: dict)
     - get_post_by_id(post_id: str)
     - get_latest_check_run(subreddit, topic)
   - Add proper error handling
   - Use context managers for transactions

3. Ensure:
   - Atomic transactions
   - Proper session handling
   - Error messages for debugging
   - Type hints throughout
   - Logging for operations

Success Criteria:
- All CRUD operations work
- Transactions rollback on error
- Duplicate posts handled gracefully
- Tests cover error scenarios
- No session leaks
```

## Prompt 5: Advanced Storage Features

```prompt
Extend StorageService with relationship handling and complex queries.

Context:
- Basic StorageService exists from Prompt 4
- Need to handle comments and snapshots
- Must maintain data integrity

Requirements:
1. First, write tests:
   - Test save_comment with post relationship
   - Test save_post_snapshot tracking
   - Test get_new_posts_since query
   - Test comment retrieval by post
   - Test bulk operations
   - Test query performance

2. Then implement in StorageService:
   - save_comment(comment_data, post_id):
     - Verify post exists
     - Handle parent relationships
   - save_post_snapshot(post_id, check_run_id, score, num_comments)
   - get_new_posts_since(subreddit, timestamp):
     - Efficient query with joins
     - Proper ordering
   - get_comments_for_post(post_id)
   - bulk_save_comments(comments_list)

3. Ensure:
   - Referential integrity
   - Efficient bulk operations
   - Query optimization
   - Proper error handling
   - Transaction boundaries

Success Criteria:
- Complex relationships work
- Bulk operations are efficient
- Queries return correct data
- No N+1 query problems
- Tests verify integrity
```

## Prompt 6: Data Retention & Cleanup

```prompt
Implement data retention and cleanup functionality.

Context:
- StorageService has CRUD and relationship operations
- Need configurable data retention
- Must handle large datasets efficiently

Requirements:
1. First, write tests:
   - Test cleanup_old_data with date ranges
   - Test cascade deletions
   - Test retention configuration
   - Test partial cleanup (keep summaries)
   - Test cleanup performance
   - Test data archival

2. Then implement:
   - Add retention config to app/core/config.py:
     - DATA_RETENTION_DAYS
     - ARCHIVE_OLD_DATA flag
   - Extend StorageService:
     - cleanup_old_data(days_to_keep)
     - archive_old_check_runs()
     - get_storage_statistics()
   - Create app/utils/db_maintenance.py:
     - Scheduled cleanup task
     - Database optimization

3. Ensure:
   - Cascade deletes work properly
   - Large datasets handled in batches
   - Archive option preserves summaries
   - Configurable retention periods
   - Performance monitoring

Success Criteria:
- Old data cleaned up correctly
- Cascades preserve integrity
- Batch processing prevents timeouts
- Statistics accurate
- No data loss bugs
```

## Prompt 7: Post Change Detection

```prompt
Create the ChangeDetectionService for identifying post changes.

Context:
- StorageService provides data access
- Need to compare current vs stored posts
- Must calculate meaningful deltas

Requirements:
1. First, write comprehensive tests:
   - Test find_new_posts identification
   - Test find_updated_posts with score changes
   - Test engagement delta calculation
   - Test edge cases (no previous data)
   - Test performance with many posts

2. Then implement:
   - Create app/services/change_detection_service.py
   - Create app/models/types.py for:
     - PostUpdate dataclass
     - EngagementDelta dataclass
   - Implement ChangeDetectionService:
     - find_new_posts(current_posts, last_check_time)
     - find_updated_posts(current_posts)
     - calculate_engagement_delta(post_id)
     - _compare_posts(old, new)

3. Ensure:
   - Accurate change detection
   - Meaningful delta values
   - Handle missing data gracefully
   - Type safety with dataclasses
   - Efficient comparisons

Success Criteria:
- Correctly identifies all new posts
- Detects significant changes
- Calculates accurate deltas
- Handles edge cases
- Good performance
```

## Prompt 8: Comment Analysis

```prompt
Extend change detection to handle Reddit comments.

Context:
- Post change detection works from Prompt 7
- Need similar functionality for comments
- Must handle comment trees efficiently

Requirements:
1. First, write tests:
   - Test find_new_comments detection
   - Test comment tree comparison
   - Test deleted comment handling
   - Test score change tracking
   - Test parent-child relationships

2. Then extend ChangeDetectionService:
   - find_new_comments(post_id, current_comments)
   - find_updated_comments(post_id, current_comments)
   - get_comment_tree_changes(post_id)
   - calculate_comment_metrics(post_id):
     - Total new comments
     - Average sentiment change
     - Top new comment

3. Ensure:
   - Handle deleted comments
   - Preserve comment hierarchy
   - Efficient tree traversal
   - Meaningful metrics
   - Memory efficiency

Success Criteria:
- New comments detected accurately
- Tree structure preserved
- Deleted comments handled
- Metrics are meaningful
- Good performance on large threads
```

## Prompt 9: Trend Analysis

```prompt
Implement trend analysis and pattern detection.

Context:
- Change detection for posts and comments complete
- Need historical trend analysis
- Must provide actionable insights

Requirements:
1. First, write tests:
   - Test subreddit trend calculation
   - Test time window analysis
   - Test activity pattern detection
   - Test trend data serialization
   - Test empty data handling

2. Then implement:
   - Create app/models/types.py additions:
     - TrendData dataclass
     - ActivityPattern enum
   - Extend ChangeDetectionService:
     - get_subreddit_trends(subreddit, days)
     - detect_activity_patterns(subreddit)
     - calculate_best_post_time(subreddit)
     - get_engagement_forecast(subreddit)

3. Ensure:
   - Statistical accuracy
   - Handle sparse data
   - Meaningful time windows
   - Clear trend visualization data
   - Efficient aggregation queries

Success Criteria:
- Trends accurately calculated
- Patterns detected correctly
- Forecasts are reasonable
- Performance acceptable
- Data format suitable for visualization
```

## Prompt 10: Check Updates Endpoint

```prompt
Create the /check-updates API endpoint for delta reports.

Context:
- All services (Storage, ChangeDetection) are complete
- Need REST endpoint for checking updates
- Must integrate with existing FastAPI app

Requirements:
1. First, write API tests:
   - Test endpoint with new posts
   - Test endpoint with no changes
   - Test first-time checks
   - Test error handling
   - Test response format

2. Then implement:
   - Add to app/main.py:
     - Inject services as dependencies
   - Create endpoint:
     ```python
     @app.get("/check-updates/{subreddit}/{topic}")
     async def check_updates(subreddit: str, topic: str)
     ```
   - Response model in app/models/api_models.py:
     - UpdateCheckResponse
     - Include new_posts, updated_posts, new_comments
   - Integrate all services

3. Ensure:
   - Input validation
   - Proper error responses
   - Efficient service calls
   - Clear response format
   - Backwards compatibility

Success Criteria:
- Endpoint returns delta information
- Handles edge cases gracefully
- Response format is clear
- Performance is good
- Tests verify all scenarios
```

## Prompt 11: History & Trends Endpoints

```prompt
Implement /history and /trends API endpoints.

Context:
- Update checking endpoint exists
- Need historical data access
- Must support filtering and pagination

Requirements:
1. First, write tests:
   - Test history endpoint with date filtering
   - Test pagination
   - Test trends endpoint
   - Test empty results
   - Test invalid parameters

2. Then implement:
   - Add to app/main.py:
     ```python
     @app.get("/history/{subreddit}")
     async def get_history(
         subreddit: str,
         start_date: Optional[datetime] = None,
         end_date: Optional[datetime] = None,
         page: int = 1,
         limit: int = 20
     )
     
     @app.get("/trends/{subreddit}")
     async def get_trends(
         subreddit: str,
         days: int = 7
     )
     ```
   - Create response models
   - Add query parameter validation

3. Ensure:
   - Efficient pagination
   - Date handling
   - Clear error messages
   - Proper HTTP status codes
   - Response caching

Success Criteria:
- Both endpoints work correctly
- Pagination is efficient
- Filters work as expected
- Good performance
- Clear documentation
```

## Prompt 12: Enhanced Report Generation

```prompt
Modify the existing /generate-report endpoint to store data.

Context:
- Original endpoint generates reports without persistence
- Need to integrate storage while maintaining compatibility
- Must add optional history inclusion

Requirements:
1. First, write tests:
   - Test data storage during generation
   - Test include_history parameter
   - Test backwards compatibility
   - Test storage failures don't break reports
   - Test performance impact

2. Then modify app/main.py:
   - Update generate_report endpoint:
     - Add include_history parameter
     - Integrate StorageService
     - Store posts and comments
     - Create check_run entry
   - Ensure existing functionality unchanged
   - Add error recovery

3. Ensure:
   - No breaking changes
   - Storage errors don't fail reports
   - Optional history inclusion
   - Performance acceptable
   - Clear parameter documentation

Success Criteria:
- Reports still generate correctly
- Data is stored during generation
- History parameter works
- No performance regression
- Backwards compatible
```

## Prompt 13: Delta Report Generator

```prompt
Create enhanced report templates for showing changes.

Context:
- Report generator exists for standard reports
- Need templates highlighting changes
- Must integrate with change detection

Requirements:
1. First, write tests:
   - Test delta report formatting
   - Test change highlighting
   - Test trend summary sections
   - Test empty delta handling
   - Test markdown escaping

2. Then implement:
   - Create app/utils/delta_report_generator.py:
     - create_delta_report(delta_data, subreddit, topic)
     - format_post_changes(post_update)
     - format_comment_changes(comment_data)
     - format_trend_summary(trend_data)
   - Update templates for:
     - New post indicators
     - Score change highlights
     - Comment count changes
     - Trend visualizations

3. Ensure:
   - Clear change indicators
   - Readable formatting
   - Proper markdown escaping
   - Mobile-friendly output
   - Consistent styling

Success Criteria:
- Delta reports clearly show changes
- Formatting is consistent
- Markdown renders correctly
- Trends are visualized
- Edge cases handled
```

## Prompt 14: Integration Testing

```prompt
Create comprehensive integration tests for the complete system.

Context:
- All components implemented individually
- Need end-to-end testing
- Must verify complete workflows

Requirements:
1. Write integration tests:
   - Test complete flow: fetch → store → detect → report
   - Test concurrent requests
   - Test data consistency
   - Test error recovery
   - Test performance benchmarks

2. Create tests/integration/:
   - test_complete_workflow.py:
     - First check (no history)
     - Second check (with changes)
     - Multiple subreddit tracking
   - test_concurrent_operations.py
   - test_data_consistency.py
   - test_performance.py

3. Ensure:
   - Realistic test data
   - Proper test isolation
   - Database cleanup
   - Performance baselines
   - Error injection testing

Success Criteria:
- All workflows tested
- Concurrent operations safe
- Data consistency verified
- Performance acceptable
- Error handling robust
```

## Prompt 15: Performance & Documentation

```prompt
Optimize performance and complete documentation.

Context:
- Full system implemented and tested
- Need performance optimization
- Must document for developers

Requirements:
1. First, write performance tests:
   - Test query optimization impact
   - Test caching effectiveness
   - Test bulk operation performance
   - Test memory usage
   - Test response times

2. Then implement:
   - Query optimizations:
     - Add query analysis
     - Optimize N+1 queries
     - Add strategic eager loading
   - Add caching:
     - Redis integration (optional)
     - In-memory caching
     - Cache invalidation
   - Update documentation:
     - API documentation
     - Developer guide
     - Deployment guide

3. Ensure:
   - Meet performance targets
   - Clear documentation
   - Monitoring capabilities
   - Production readiness
   - Migration guide

Success Criteria:
- Performance targets met
- Documentation complete
- Caching improves response times
- Monitoring in place
- Production ready
```
