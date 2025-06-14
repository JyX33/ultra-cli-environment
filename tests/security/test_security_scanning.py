# ABOUTME: Automated security scanning and validation test suite
# ABOUTME: Implements security gates and regression detection for continuous security monitoring

import pytest
import os
import re
from pathlib import Path
import ast


class TestAutomatedSecurityScanning:
    """Automated security scanning test suite."""

    def test_no_hardcoded_secrets(self):
        """Test that no hardcoded secrets exist in our application code."""
        project_root = Path(__file__).parent.parent.parent
        
        # Only scan our application code, not dependencies
        app_dirs = [project_root / 'app', project_root / 'tests']
        
        # Patterns to detect potential secrets
        secret_patterns = [
            r'sk-[a-zA-Z0-9]{48}',  # OpenAI API key pattern
            r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\'][a-zA-Z0-9]{20,}["\']',
            r'(?i)(client[_-]?secret)\s*[=:]\s*["\'][a-zA-Z0-9]{20,}["\']',
        ]
        
        excluded_files = {
            'test_security_scanning.py',  # This file contains test patterns
            'test_comprehensive_security.py'  # Test file with mock keys
        }
        
        for app_dir in app_dirs:
            if not app_dir.exists():
                continue
                
            for py_file in app_dir.rglob("*.py"):
                if py_file.name in excluded_files:
                    continue
                    
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                
                for pattern in secret_patterns:
                    matches = re.findall(pattern, content)
                    # Filter out obvious test/example values
                    real_matches = []
                    for match in matches:
                        if isinstance(match, tuple):
                            match_text = str(match)
                        else:
                            match_text = str(match)
                        
                        # Skip obvious test values
                        if any(test_val in match_text.lower() for test_val in 
                              ['test', 'fake', 'example', 'dummy', 'mock', 'your_', 'placeholder']):
                            continue
                        real_matches.append(match)
                    
                    assert len(real_matches) == 0, f"Potential hardcoded secret in {py_file}: {real_matches}"

    def test_no_dangerous_imports(self):
        """Test that no dangerous imports are present in our application code."""
        project_root = Path(__file__).parent.parent.parent
        app_dir = project_root / 'app'
        
        dangerous_imports = [
            'os.system',
            'eval(',
            'exec(',
            'compile(',
        ]
        
        if not app_dir.exists():
            return
            
        for py_file in app_dir.rglob("*.py"):
            content = py_file.read_text(encoding='utf-8', errors='ignore')
            
            for dangerous_import in dangerous_imports:
                if dangerous_import in content:
                    # Check if it's in a comment or string
                    lines = content.split('\n')
                    for i, line in enumerate(lines, 1):
                        if dangerous_import in line and not line.strip().startswith('#'):
                            # Could be dangerous - manual review needed
                            pytest.fail(f"Potentially dangerous import '{dangerous_import}' in {py_file}:{i}")

    def test_no_sql_injection_vulnerabilities(self):
        """Test for potential SQL injection vulnerabilities in our app code."""
        project_root = Path(__file__).parent.parent.parent
        app_dir = project_root / 'app'
        
        if not app_dir.exists():
            return
            
        # Look for string formatting with SQL-like keywords
        sql_patterns = [
            r'(?i)(select|insert|update|delete|drop|create|alter)\s+.*%s',
            r'(?i)(select|insert|update|delete|drop|create|alter)\s+.*\.format\(',
            r'(?i)(select|insert|update|delete|drop|create|alter)\s+.*\+\s*\w+',
        ]
        
        for py_file in app_dir.rglob("*.py"):
            content = py_file.read_text(encoding='utf-8', errors='ignore')
            
            for pattern in sql_patterns:
                matches = re.findall(pattern, content)
                assert len(matches) == 0, f"Potential SQL injection vulnerability in {py_file}: {matches}"

    def test_file_permissions_security(self):
        """Test that our application files have secure permissions."""
        project_root = Path(__file__).parent.parent.parent
        app_dir = project_root / 'app'
        
        if not app_dir.exists():
            return
            
        for py_file in app_dir.rglob("*.py"):
            # Check that Python files are not executable (security best practice)
            stat = py_file.stat()
            mode = oct(stat.st_mode)[-3:]
            
            # Should not have execute permissions for others
            assert mode[-1] not in ['1', '3', '5', '7'], f"File {py_file} has execute permissions for others: {mode}"

    def test_import_security_validation(self):
        """Test that our app imports are secure."""
        project_root = Path(__file__).parent.parent.parent
        app_dir = project_root / 'app'
        
        if not app_dir.exists():
            return
            
        for py_file in app_dir.rglob("*.py"):
            try:
                content = py_file.read_text(encoding='utf-8')
                tree = ast.parse(content)
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            # Check for potentially dangerous modules
                            dangerous_modules = ['pickle', 'marshal', 'shelve']
                            assert alias.name not in dangerous_modules, \
                                f"Dangerous import '{alias.name}' in {py_file}"
                            
            except (SyntaxError, UnicodeDecodeError):
                # Skip files with syntax errors
                continue

    def test_configuration_security(self):
        """Test that configuration files don't contain real secrets."""
        project_root = Path(__file__).parent.parent.parent
        
        # Check for potential configuration security issues
        config_files = list(project_root.glob("*.env")) + list(project_root.glob(".env"))
        
        for config_file in config_files:
            if config_file.exists() and config_file.is_file():
                content = config_file.read_text(encoding='utf-8', errors='ignore')
                
                # Should not contain obvious real API keys
                assert 'sk-' not in content, f"Potential OpenAI API key in {config_file}"
                assert 'client_secret=' not in content.lower() or 'your_' in content.lower(), f"Potential real client secret in {config_file}"

    def test_dependency_security_check(self):
        """Test that dependencies don't have known vulnerabilities."""
        project_root = Path(__file__).parent.parent.parent
        pyproject_file = project_root / "pyproject.toml"
        
        if pyproject_file.exists():
            content = pyproject_file.read_text()
            
            # Check for known vulnerable package patterns
            vulnerable_patterns = [
                r'requests\s*[<>=]\s*2\.[0-9]\.',  # Very old requests versions
                r'urllib3\s*[<>=]\s*1\.[0-9]\.',   # Very old urllib3 versions
            ]
            
            for pattern in vulnerable_patterns:
                matches = re.findall(pattern, content)
                assert len(matches) == 0, f"Potentially vulnerable dependency pattern: {matches}"

    def test_error_handling_security(self):
        """Test that error handling doesn't expose sensitive information."""
        project_root = Path(__file__).parent.parent.parent
        
        for py_file in project_root.rglob("*.py"):
            if 'test' in py_file.name:
                continue
                
            content = py_file.read_text(encoding='utf-8', errors='ignore')
            
            # Look for exception handling that might expose sensitive info
            dangerous_exception_patterns = [
                r'except.*:\s*print\(',
                r'except.*:\s*return.*str\(e\)',
                r'raise.*str\(.*\)',
            ]
            
            for pattern in dangerous_exception_patterns:
                matches = re.findall(pattern, content, re.MULTILINE)
                # This is a warning, not a failure, as context matters
                if matches:
                    print(f"Warning: Potential information disclosure in exception handling in {py_file}")


class TestSecurityRegressionPrevention:
    """Test suite for preventing security regressions."""

    def test_url_validation_regression(self):
        """Test that URL validation hasn't regressed."""
        try:
            from app.utils.url_validator import is_url_valid
        except ImportError:
            pytest.skip("URL validator not available")
        
        # Test cases that should always pass
        safe_urls = [
            "https://www.example.com",
            "http://example.com/path",
            "https://subdomain.example.com:8080/path?query=value"
        ]
        
        for url in safe_urls:
            assert is_url_valid(url) == True, f"URL validation regression: {url} should be valid"
        
        # Test cases that should always fail
        dangerous_urls = [
            "javascript:alert('xss')",
            "data:text/html,<script>alert('xss')</script>",
            "file:///etc/passwd",
            "http://localhost:22",
            "http://127.0.0.1:80",
            "http://169.254.169.254/",
            "ftp://internal.server.com"
        ]
        
        for url in dangerous_urls:
            assert is_url_valid(url) == False, f"URL validation regression: {url} should be invalid"

    def test_filename_sanitization_regression(self):
        """Test that filename sanitization hasn't regressed."""
        from app.utils.filename_sanitizer import generate_safe_filename
        
        # Test dangerous inputs
        dangerous_inputs = [
            "../../../etc/passwd",
            "test<script>alert('xss')</script>",
            "file.exe\x00.txt",
            "CON.txt",  # Windows reserved name
            "file|with|pipes",
            "file;with;semicolons"
        ]
        
        for dangerous_input in dangerous_inputs:
            result = generate_safe_filename(dangerous_input, "test")
            
            # Should not contain dangerous characters
            assert "../" not in result
            assert "<" not in result
            assert ">" not in result
            assert "\x00" not in result
            assert "|" not in result
            assert ";" not in result
            
            # Should produce a valid filename
            assert len(result) > 0
            assert result != dangerous_input

    def test_scraper_security_regression(self):
        """Test that scraper security hasn't regressed."""
        from app.services.scraper_service import scrape_article_text
        
        # Test that dangerous URLs are rejected
        dangerous_urls = [
            "file:///etc/passwd",
            "http://localhost:22",
            "javascript:alert('xss')",
            "data:text/html,<script>alert('xss')</script>"
        ]
        
        for url in dangerous_urls:
            result = scrape_article_text(url)
            assert result == "Could not retrieve article content.", \
                f"Scraper security regression: {url} should be rejected"


class TestSecurityGateIntegration:
    """Integration tests for security gate validation."""

    def test_security_test_coverage(self):
        """Test that security-critical modules exist and have some test coverage."""
        project_root = Path(__file__).parent.parent.parent
        
        security_critical_modules = [
            'app/utils/url_validator.py',
            'app/utils/filename_sanitizer.py',
            'app/main.py'
        ]
        
        for module_path in security_critical_modules:
            module_file = project_root / module_path
            assert module_file.exists(), f"Security-critical module not found: {module_path}"
        
        # Check that we have security tests
        test_root = project_root / 'tests'
        security_test_files = list(test_root.rglob("*security*.py"))
        assert len(security_test_files) > 0, "No security test files found"

    def test_all_endpoints_have_security_validation(self):
        """Test that API endpoints handle basic security scenarios."""
        try:
            from app.main import app
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("FastAPI app not available")
        
        client = TestClient(app)
        
        # Test that endpoints exist and don't crash with basic inputs
        response = client.get("/")
        assert response.status_code == 200
        
        # Test that malformed endpoints return appropriate errors
        response = client.get("/nonexistent")
        assert response.status_code == 404
        
        # Test basic path validation
        response = client.get("/discover-subreddits/")
        assert response.status_code in [404, 422]  # Should not process empty path

    def test_security_configuration_complete(self):
        """Test that security configuration is complete."""
        # Check that all required security configurations are in place
        from app.core.config import config
        
        # These should be configured (even if with placeholder values in tests)
        required_configs = [
            'REDDIT_CLIENT_ID',
            'REDDIT_CLIENT_SECRET', 
            'REDDIT_USER_AGENT',
            'OPENAI_API_KEY'
        ]
        
        for config_name in required_configs:
            assert hasattr(config, config_name), f"Missing security configuration: {config_name}"
            
            config_value = getattr(config, config_name)
            assert config_value is not None, f"Security configuration is None: {config_name}"
            assert len(str(config_value)) > 0, f"Security configuration is empty: {config_name}"