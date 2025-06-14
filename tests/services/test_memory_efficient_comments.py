# ABOUTME: Memory efficiency tests for comment processing with streaming and memory limits
# ABOUTME: Tests large comment thread handling, memory usage validation, and streaming processing

import pytest
from unittest.mock import Mock, patch
import sys
from io import StringIO
from app.services.reddit_service import RedditService
from app.utils.comment_processor import process_comments_stream, CommentMemoryTracker


@pytest.fixture
def mock_reddit_service():
    """Fixture for mocked Reddit service."""
    with patch('app.services.reddit_service.praw.Reddit') as mock_reddit:
        service = RedditService()
        return service, mock_reddit


@pytest.fixture
def large_comment_dataset():
    """Fixture for large comment dataset to test memory efficiency."""
    comments = []
    for i in range(100):  # Large comment thread
        comment = Mock()
        comment.body = f"This is comment number {i} with some substantial text content that takes up memory. " * 10
        comment.score = 100 - i  # Descending scores
        comments.append(comment)
    return comments


class TestMemoryEfficientCommentProcessing:
    """Test suite for memory-efficient comment processing."""
    
    def test_streaming_comment_processing(self, mock_reddit_service, large_comment_dataset):
        """Test that comments are processed in streaming fashion without loading all into memory."""
        service, mock_reddit = mock_reddit_service
        
        # Mock the get_top_comments method directly
        service.get_top_comments = Mock(return_value=large_comment_dataset)
        
        # Process comments with memory limit
        result = process_comments_stream("test_post_id", service, max_memory_mb=10, top_count=10)
        
        # Should return limited number of comments without exhausting memory
        assert len(result) <= 10
        assert isinstance(result, list)
        assert all(isinstance(comment, str) for comment in result)
    
    def test_memory_usage_tracking(self, large_comment_dataset):
        """Test that memory usage is tracked and limited during processing."""
        tracker = CommentMemoryTracker(max_memory_mb=0.1)  # Very small limit to force early termination
        
        # Process comments while tracking memory
        processed_comments = []
        for comment in large_comment_dataset:
            if tracker.can_add_comment(comment.body):
                tracker.add_comment(comment.body)
                processed_comments.append(comment.body)
            else:
                break  # Memory limit reached
        
        # Should stop before processing all comments due to memory limit
        assert len(processed_comments) < len(large_comment_dataset)
        assert tracker.get_memory_usage_mb() <= 0.1
    
    def test_top_comments_selection_with_memory_limit(self, mock_reddit_service):
        """Test that top comments are selected efficiently within memory constraints."""
        service, mock_reddit = mock_reddit_service
        
        # Create comments with varying scores and sizes
        comments = []
        for i in range(50):
            comment = Mock()
            comment.body = f"Comment {i}: " + "text " * (i + 1)  # Increasing size
            comment.score = 50 - i  # Decreasing score (first comment has highest score)
            comments.append(comment)
        
        # Mock the get_top_comments method directly
        service.get_top_comments = Mock(return_value=comments)
        
        # Process with memory constraint
        result = process_comments_stream("test_post_id", service, max_memory_mb=1, top_count=15)
        
        # Should prioritize high-scoring comments within memory limit
        assert len(result) > 0
        assert len(result) <= 15
        
        # Verify that the processing respects memory limits
        total_text_length = sum(len(comment) for comment in result)
        assert total_text_length < 1024 * 1024  # Should be well under 1MB
    
    def test_generator_based_processing(self, large_comment_dataset):
        """Test that comment processing uses generators for memory efficiency."""
        def comment_generator():
            """Generator that yields comments one at a time."""
            for comment in large_comment_dataset:
                yield comment.body
        
        # Process using generator
        processed = []
        memory_tracker = CommentMemoryTracker(max_memory_mb=0.1)  # Very small limit
        
        for comment_text in comment_generator():
            if memory_tracker.can_add_comment(comment_text):
                memory_tracker.add_comment(comment_text)
                processed.append(comment_text)
            else:
                break
        
        # Should process some comments without loading all into memory
        assert len(processed) > 0
        assert len(processed) < len(large_comment_dataset)
        assert memory_tracker.get_memory_usage_mb() <= 0.1
    
    def test_memory_limit_edge_cases(self):
        """Test edge cases in memory limit handling."""
        tracker = CommentMemoryTracker(max_memory_mb=1)  # Very small limit
        
        # Test with very large single comment
        large_comment = "Very large comment text " * 10000  # ~250KB
        
        # Should handle large comment gracefully
        can_add = tracker.can_add_comment(large_comment)
        if can_add:
            tracker.add_comment(large_comment)
            assert tracker.get_memory_usage_mb() > 0
        
        # Test with empty comments
        assert tracker.can_add_comment("")
        tracker.add_comment("")
        
        # Test with None (edge case)
        assert not tracker.can_add_comment(None)
    
    def test_streaming_with_early_termination(self, mock_reddit_service):
        """Test that streaming terminates early when memory limit is reached."""
        service, mock_reddit = mock_reddit_service
        
        # Create many large comments
        large_comments = []
        for i in range(20):
            comment = Mock()
            comment.body = f"Large comment {i}: " + "text " * 1000  # Each comment ~4KB
            comment.score = 100 - i
            large_comments.append(comment)
        
        # Mock the get_top_comments method directly
        service.get_top_comments = Mock(return_value=large_comments)
        
        # Should terminate early due to memory limit
        result = process_comments_stream("test_post_id", service, max_memory_mb=0.5, top_count=20)
        
        # Should return fewer comments than requested due to memory limit
        assert len(result) < 20
        assert len(result) > 0
    
    def test_comment_deduplication_in_stream(self, mock_reddit_service):
        """Test that duplicate comments are handled efficiently in streaming."""
        service, mock_reddit = mock_reddit_service
        
        # Create comments with some duplicates
        comments = []
        for i in range(10):
            comment = Mock()
            # Create some duplicate content
            comment.body = f"Comment text {i % 3}"  # Will create duplicates
            comment.score = 10 - i
            comments.append(comment)
        
        mock_submission = Mock()
        mock_submission.comments.replace_more = Mock()
        mock_submission.comments = comments
        mock_reddit.return_value.submission.return_value = mock_submission
        
        result = process_comments_stream("test_post_id", service, max_memory_mb=5, top_count=10, deduplicate=True)
        
        # Should have fewer results due to deduplication
        unique_comments = set(result)
        assert len(unique_comments) <= 3  # Based on our duplicate pattern
        assert len(result) <= len(comments)


class TestCommentMemoryTracker:
    """Test suite specifically for the CommentMemoryTracker utility."""
    
    def test_memory_tracking_accuracy(self):
        """Test that memory tracking provides reasonably accurate measurements."""
        tracker = CommentMemoryTracker(max_memory_mb=1)
        
        # Add known-size content
        test_text = "a" * 1000  # 1KB
        tracker.add_comment(test_text)
        
        # Memory usage should be proportional to content size
        usage_kb = tracker.get_memory_usage_mb() * 1024
        assert usage_kb >= 1  # Should be at least 1KB
        assert usage_kb < 10   # But not unreasonably high
    
    def test_memory_limit_enforcement(self):
        """Test that memory limits are properly enforced."""
        tracker = CommentMemoryTracker(max_memory_mb=0.1)  # 100KB limit
        
        # Add content until limit is reached
        added_count = 0
        for i in range(100):
            text = f"Comment {i}: " + "text " * 100  # ~0.5KB each
            if tracker.can_add_comment(text):
                tracker.add_comment(text)
                added_count += 1
            else:
                break
        
        # Should stop adding before all 100 comments
        assert added_count < 100
        assert tracker.get_memory_usage_mb() <= 0.1
    
    def test_reset_functionality(self):
        """Test that memory tracker can be reset."""
        tracker = CommentMemoryTracker(max_memory_mb=1)
        
        # Add some content
        tracker.add_comment("Test content")
        assert tracker.get_memory_usage_mb() > 0
        
        # Reset and verify
        tracker.reset()
        assert tracker.get_memory_usage_mb() == 0
        assert tracker.can_add_comment("New content after reset")
