# ABOUTME: Security tests for scraper service to prevent SSRF and other web-based attacks
# ABOUTME: Tests URL validation, malicious input handling, and security edge cases

import pytest
from unittest.mock import patch, MagicMock
from app.services.scraper_service import scrape_article_text
from app.utils.url_validator import validate_url_strict as validate_url, URLValidationError


class TestURLValidation:
    """Test suite for URL validation to prevent SSRF attacks."""
    
    def test_validate_url_allows_legitimate_http_urls(self):
        """Test that legitimate HTTP URLs are allowed."""
        valid_urls = [
            "http://example.com/article",
            "http://news.com/story.html",
            "http://blog.example.org/post/123"
        ]
        
        for url in valid_urls:
            # This should not raise an exception
            validate_url(url)
    
    def test_validate_url_allows_legitimate_https_urls(self):
        """Test that legitimate HTTPS URLs are allowed."""
        valid_urls = [
            "https://example.com/article",
            "https://news.com/story.html", 
            "https://secure.blog.org/post/123"
        ]
        
        for url in valid_urls:
            # This should not raise an exception
            validate_url(url)
    
    def test_validate_url_blocks_localhost_variations(self):
        """Test that localhost and local IP variations are blocked."""
        malicious_urls = [
            "http://localhost/admin",
            "http://127.0.0.1/internal",
            "http://127.0.0.1:8080/admin",
            "https://localhost:9000/secrets",
            "http://127.1/test",
            "http://0.0.0.0/admin"
        ]
        
        for url in malicious_urls:
            with pytest.raises(URLValidationError, match="Internal network access not allowed"):
                validate_url(url)
    
    def test_validate_url_blocks_private_ip_ranges(self):
        """Test that private IP address ranges are blocked."""
        private_ips = [
            "http://10.0.0.1/internal",
            "http://10.255.255.255/admin", 
            "http://192.168.1.1/router",
            "http://192.168.0.100:8080/admin",
            "http://172.16.0.1/internal",
            "http://172.31.255.255/secrets"
        ]
        
        for url in private_ips:
            with pytest.raises(URLValidationError, match="Internal network access not allowed"):
                validate_url(url)
    
    def test_validate_url_blocks_non_http_schemes(self):
        """Test that non-HTTP/HTTPS schemes are blocked."""
        malicious_schemes = [
            "ftp://example.com/file",
            "file:///etc/passwd",
            "gopher://example.com/",
            "dict://example.com:2628/",
            "ssh://example.com/",
            "mailto:test@example.com"
        ]
        
        for url in malicious_schemes:
            with pytest.raises(URLValidationError, match="Only HTTP and HTTPS schemes are allowed"):
                validate_url(url)
    
    def test_validate_url_blocks_suspicious_ports(self):
        """Test that suspicious ports commonly used for internal services are blocked."""
        suspicious_ports = [
            "http://example.com:22/",  # SSH
            "http://example.com:23/",  # Telnet
            "http://example.com:25/",  # SMTP
            "http://example.com:53/",  # DNS
            "http://example.com:3306/",  # MySQL
            "http://example.com:5432/",  # PostgreSQL
            "http://example.com:6379/",  # Redis
            "http://example.com:27017/"  # MongoDB
        ]
        
        for url in suspicious_ports:
            with pytest.raises(URLValidationError, match="Port .* is not allowed"):
                validate_url(url)
    
    def test_validate_url_allows_standard_web_ports(self):
        """Test that standard web ports are allowed."""
        allowed_ports = [
            "http://example.com:80/article",
            "https://example.com:443/article",
            "http://example.com:8080/article",  # Common web port
            "https://example.com:8443/article"  # Common HTTPS alt port
        ]
        
        for url in allowed_ports:
            # These should not raise exceptions
            validate_url(url)
    
    def test_validate_url_handles_malformed_urls(self):
        """Test that malformed URLs are properly handled."""
        # URLs that should fail with format errors
        format_error_urls = [
            "http://",
            "http:///path", 
            "",
            None
        ]
        
        for url in format_error_urls:
            with pytest.raises(URLValidationError, match="Invalid URL format"):
                validate_url(url)
        
        # URLs that should fail with scheme errors
        scheme_error_urls = [
            "not-a-url",
            "://example.com"
        ]
        
        for url in scheme_error_urls:
            with pytest.raises(URLValidationError, match="Only HTTP and HTTPS schemes are allowed"):
                validate_url(url)
    
    def test_validate_url_handles_url_with_userinfo(self):
        """Test that URLs with user info are handled securely."""
        urls_with_userinfo = [
            "http://user:pass@localhost/admin",
            "https://admin@192.168.1.1/config",
            "http://user@127.0.0.1:8080/internal"
        ]
        
        for url in urls_with_userinfo:
            with pytest.raises(URLValidationError, match="Internal network access not allowed"):
                validate_url(url)
    
    def test_validate_url_blocks_ip_address_obfuscation(self):
        """Test that various IP address obfuscation techniques are blocked."""
        obfuscated_ips = [
            "http://2130706433/",  # 127.0.0.1 as decimal
            "http://0x7f000001/",  # 127.0.0.1 as hex
            "http://017700000001/",  # 127.0.0.1 as octal
            "http://127.1/",  # Short form of 127.0.0.1
        ]
        
        for url in obfuscated_ips:
            with pytest.raises(URLValidationError, match="Internal network access not allowed"):
                validate_url(url)


class TestScraperServiceSecurity:
    """Test suite for scraper service security integration."""
    
    def test_scraper_rejects_malicious_urls(self):
        """Test that scraper service rejects malicious URLs."""
        malicious_urls = [
            "http://localhost/admin",
            "http://127.0.0.1/internal", 
            "http://192.168.1.1/router",
            "ftp://example.com/file"
        ]
        
        for url in malicious_urls:
            result = scrape_article_text(url)
            assert result == "Could not retrieve article content."
    
    def test_scraper_allows_legitimate_urls(self):
        """Test that scraper service allows legitimate URLs and processes them."""
        with patch('requests.get') as mock_get:
            # Mock successful response
            mock_response = MagicMock()
            mock_response.text = '<html><body><p>This is article content.</p></body></html>'
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            result = scrape_article_text("https://example.com/article")
            
            # Should process the content normally
            assert "This is article content." in result
            mock_get.assert_called_once()
    
    def test_scraper_handles_validation_errors_gracefully(self):
        """Test that scraper handles URL validation errors gracefully."""
        # Test with various invalid URLs
        invalid_urls = [
            "not-a-url",
            "",
            None,
            "http://localhost/admin"
        ]
        
        for url in invalid_urls:
            result = scrape_article_text(url)
            assert result == "Could not retrieve article content."
    
    @patch('app.services.scraper_service.validate_url')
    def test_scraper_calls_url_validation(self, mock_validate):
        """Test that scraper service calls URL validation."""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.text = '<html><body><p>Content</p></body></html>'
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response
            
            scrape_article_text("https://example.com/article")
            
            # Verify that validation was called
            mock_validate.assert_called_once_with("https://example.com/article")


class TestURLValidationEdgeCases:
    """Test edge cases and security considerations for URL validation."""
    
    def test_validate_url_with_unicode_domains(self):
        """Test URL validation with unicode domain names."""
        unicode_urls = [
            "https://тест.example.com/article",
            "https://测试.example.com/path", 
            "https://テスト.example.com/content"
        ]
        
        for url in unicode_urls:
            # These should be handled properly (either allowed or rejected consistently)
            try:
                validate_url(url)
            except URLValidationError:
                # It's OK to reject unicode domains for security
                pass
    
    def test_validate_url_with_very_long_urls(self):
        """Test URL validation with very long URLs."""
        # Create a very long URL
        long_path = "a" * 10000
        long_url = f"https://example.com/{long_path}"
        
        # Should either accept it or reject it gracefully
        try:
            validate_url(long_url)
        except URLValidationError:
            # It's acceptable to reject very long URLs
            pass
    
    def test_validate_url_with_fragments_and_queries(self):
        """Test that URLs with fragments and query parameters work correctly."""
        urls_with_params = [
            "https://example.com/article?id=123&source=test",
            "https://example.com/article#section1",
            "https://example.com/article?query=test#section"
        ]
        
        for url in urls_with_params:
            # These should be allowed
            validate_url(url)
    
    def test_validate_url_case_insensitive_scheme(self):
        """Test that scheme validation is case insensitive."""
        mixed_case_urls = [
            "HTTP://example.com/article",
            "HTTPS://example.com/article",
            "Http://example.com/article",
            "Https://example.com/article"
        ]
        
        for url in mixed_case_urls:
            # These should be allowed (HTTP/HTTPS regardless of case)
            validate_url(url)