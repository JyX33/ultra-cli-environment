# ABOUTME: Security integration tests for main.py endpoints to verify filename sanitization
# ABOUTME: Tests that malicious subreddit/topic names are properly sanitized in report generation

import pytest
from app.utils.filename_sanitizer import generate_safe_filename


class TestMainFilenameGeneration:
    """Test filename generation security as used in main.py."""
    
    def test_generate_safe_filename_with_malicious_subreddit(self):
        """Test that malicious subreddit names are sanitized."""
        malicious_subreddits = [
            "../../../etc/passwd",
            "technology|rm-rf", 
            "test<script>alert('xss')</script>",
            "reddit\\..\\..\\windows\\system32"
        ]
        
        for subreddit in malicious_subreddits:
            filename = generate_safe_filename(subreddit, "ai")
            
            # Should not contain dangerous characters
            assert "../" not in filename
            assert "<script>" not in filename
            assert "|" not in filename
            assert "\\" not in filename
            
            # Should still be a valid filename
            assert filename.endswith(".md")
            assert "reddit_report_" in filename
    
    def test_generate_safe_filename_with_malicious_topic(self):
        """Test that malicious topic names are sanitized."""
        malicious_topics = [
            "../../../etc/passwd",
            "ai|dangerous",
            "tech<script>evil</script>", 
            "topic\\..\\secrets"
        ]
        
        for topic in malicious_topics:
            filename = generate_safe_filename("technology", topic)
            
            # Should not contain dangerous characters
            assert "../" not in filename
            assert "<script>" not in filename
            assert "|" not in filename
            assert "\\" not in filename
            
            # Should still be a valid filename
            assert filename.endswith(".md")
            assert "reddit_report_" in filename
            assert "technology" in filename
    
    def test_generate_safe_filename_preserves_legitimate_names(self):
        """Test that legitimate names are preserved."""
        legitimate_cases = [
            ("technology", "artificial intelligence"),
            ("python", "machine learning"),
            ("science", "climate change"),
            ("news", "world events")
        ]
        
        for subreddit, topic in legitimate_cases:
            filename = generate_safe_filename(subreddit, topic)
            
            # Should contain expected elements
            assert filename.endswith(".md")
            assert "reddit_report_" in filename
            assert subreddit in filename
            # Topic might be modified (spaces to underscores) but should be recognizable
            topic_safe = topic.replace(" ", "_")
            assert topic_safe in filename or topic.replace(" ", "") in filename
    
    def test_generate_safe_filename_handles_unicode(self):
        """Test that unicode characters are handled appropriately."""
        unicode_cases = [
            ("测试", "テスト"),
            ("файл", "тест"),
            ("🔥reddit", "💻topic")
        ]
        
        for subreddit, topic in unicode_cases:
            filename = generate_safe_filename(subreddit, topic)
            
            # Should generate a valid filename
            assert len(filename) > 0
            assert filename.endswith(".md")
            assert "reddit_report_" in filename
    
    def test_generate_safe_filename_handles_long_names(self):
        """Test that very long names are handled properly."""
        long_subreddit = "a" * 200
        long_topic = "b" * 200
        
        filename = generate_safe_filename(long_subreddit, long_topic)
        
        # Should be truncated to reasonable length
        assert len(filename) <= 255  # Typical filesystem limit
        assert filename.endswith(".md")
        assert "reddit_report_" in filename
    
    def test_generate_safe_filename_handles_reserved_names(self):
        """Test that Windows reserved names are handled."""
        reserved_names = ["CON", "PRN", "AUX", "NUL", "COM1", "LPT1"]
        
        for reserved_name in reserved_names:
            filename = generate_safe_filename(reserved_name, "topic")
            
            # Should not be exactly the reserved name
            assert filename.lower() != f"reddit_report_{reserved_name.lower()}_topic.md"
            assert filename.endswith(".md")
            assert "reddit_report_" in filename


class TestMainFilenameIntegration:
    """Test that the filename generation matches main.py usage patterns."""
    
    def test_filename_generation_matches_main_py_pattern(self):
        """Test that our generate_safe_filename produces the same pattern as main.py expects."""
        # This tests the pattern that was in main.py before our fix:
        # f"reddit_report_{subreddit}_{topic.replace(' ', '_')}.md"
        
        test_cases = [
            ("technology", "artificial intelligence"),
            ("python", "web development"),
            ("science", "climate change")
        ]
        
        for subreddit, topic in test_cases:
            filename = generate_safe_filename(subreddit, topic)
            
            # Should follow the expected pattern
            assert filename.startswith("reddit_report_")
            assert filename.endswith(".md")
            assert subreddit in filename
            
            # Topic spaces should be handled (either as underscores or removed)
            topic_processed = topic.replace(' ', '_')
            assert topic_processed in filename or topic.replace(' ', '') in filename