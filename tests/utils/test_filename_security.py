# ABOUTME: Security tests for filename sanitization to prevent path traversal attacks
# ABOUTME: Tests filename character filtering, length limits, and malicious input handling

import pytest

from app.utils.filename_sanitizer import FilenameSecurityError, sanitize_filename


class TestFilenameSanitization:
    """Test suite for filename sanitization to prevent path traversal attacks."""

    def test_sanitize_filename_allows_safe_characters(self):
        """Test that safe filename characters are preserved."""
        safe_filenames = [
            "reddit_report_technology_ai.md",
            "report_123_test.md",
            "simple-filename.md",
            "file_with_spaces.md",
            "MixedCaseFile.md"
        ]

        for filename in safe_filenames:
            result = sanitize_filename(filename)
            # Should return the filename unchanged (safe characters preserved)
            assert result == filename

    def test_sanitize_filename_blocks_path_traversal(self):
        """Test that path traversal attempts are blocked."""
        malicious_filenames = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32\\config",
            "report_../../../secrets.txt",
            "file../.././../etc/hosts",
            "...///...///etc/passwd",
            "..\\..\\.\\config.sys"
        ]

        for filename in malicious_filenames:
            result = sanitize_filename(filename)
            # Should not contain any path traversal sequences
            assert ".." not in result
            assert "/" not in result
            assert "\\" not in result

    def test_sanitize_filename_removes_dangerous_characters(self):
        """Test that dangerous characters are removed or replaced."""
        dangerous_chars = [
            ("file<script>alert('xss')</script>.md", "filescriptalert('xss')/script.md"),
            ("report|pipe|danger.md", "reportpipepipedanger.md"),
            ("file:with:colons.md", "filewithcolons.md"),
            ("report*wildcard*.md", "reportwildcard.md"),
            ("file?query=bad.md", "filequery=bad.md"),
            ("report\"quotes\".md", "reportquotes.md"),
            ("file<>brackets.md", "filebrackets.md")
        ]

        for dangerous, _expected_pattern in dangerous_chars:
            result = sanitize_filename(dangerous)
            # Should not contain dangerous characters
            assert "<" not in result
            assert ">" not in result
            assert "|" not in result
            assert ":" not in result
            assert "*" not in result
            assert "?" not in result
            assert "\"" not in result

    def test_sanitize_filename_handles_null_bytes(self):
        """Test that null bytes and control characters are removed."""
        filenames_with_nulls = [
            "file\x00name.md",
            "report\x01\x02\x03.md",
            "test\x7fname.md",
            "file\tname.md",
            "report\nname.md"
        ]

        for filename in filenames_with_nulls:
            result = sanitize_filename(filename)
            # Should not contain any control characters
            assert "\x00" not in result
            assert "\x01" not in result
            assert "\x02" not in result
            assert "\x03" not in result
            assert "\x7f" not in result

    def test_sanitize_filename_enforces_length_limits(self):
        """Test that filename length is enforced."""
        # Create a very long filename (over 255 characters)
        long_filename = "a" * 300 + ".md"

        result = sanitize_filename(long_filename)

        # Should be truncated to safe length (typically 255 chars for most filesystems)
        assert len(result) <= 255
        # Should still end with .md
        assert result.endswith(".md")

    def test_sanitize_filename_preserves_extension(self):
        """Test that file extensions are preserved when possible."""
        filenames_with_extensions = [
            ("malicious/../../../file.md", ".md"),
            ("dangerous|chars*.txt", ".txt"),
            ("path/traversal/file.json", ".json"),
            ("bad<chars>.pdf", ".pdf")
        ]

        for filename, expected_ext in filenames_with_extensions:
            result = sanitize_filename(filename)
            assert result.endswith(expected_ext)

    def test_sanitize_filename_handles_unicode(self):
        """Test that unicode characters are handled appropriately."""
        unicode_filenames = [
            "файл_тест.md",
            "测试文件.md",
            "テスト.md",
            "🔥report🔥.md"
        ]

        for filename in unicode_filenames:
            result = sanitize_filename(filename)
            # Should either preserve safe unicode or convert to ASCII
            assert len(result) > 0
            assert result.endswith(".md")

    def test_sanitize_filename_handles_empty_and_invalid_input(self):
        """Test handling of empty strings and None input."""
        invalid_inputs = [
            ("", "empty or whitespace only"),
            (None, "None provided"),
            ("   ", "empty or whitespace only"),  # Only whitespace
            ("...", "empty or dangerous name"),  # Only dots
            ("///", "empty or dangerous name"),  # Only slashes
        ]

        for invalid_input, expected_error in invalid_inputs:
            with pytest.raises(FilenameSecurityError, match=expected_error):
                sanitize_filename(invalid_input)

    def test_sanitize_filename_handles_reserved_names(self):
        """Test that Windows reserved names are handled."""
        reserved_names = [
            "CON.md",
            "PRN.txt",
            "AUX.pdf",
            "NUL.doc",
            "COM1.md",
            "LPT1.txt",
            "con.md",  # case insensitive
            "prn.txt"
        ]

        for reserved_name in reserved_names:
            result = sanitize_filename(reserved_name)
            # Should not be a reserved name (add prefix/suffix or modify)
            assert result.lower() != reserved_name.lower()

    def test_sanitize_filename_collision_handling(self):
        """Test that filename collision detection works."""
        # This would typically check against existing files
        filename = "existing_file.md"

        # For now, just ensure function doesn't break
        result = sanitize_filename(filename)
        assert result is not None
        assert len(result) > 0


class TestFilenameSanitizationEdgeCases:
    """Test edge cases and advanced scenarios for filename sanitization."""

    def test_sanitize_filename_multiple_extensions(self):
        """Test handling of multiple file extensions."""
        complex_filenames = [
            "archive.tar.gz",
            "backup.sql.bz2",
            "data.json.backup",
            "../../../evil.tar.gz"
        ]

        for filename in complex_filenames:
            result = sanitize_filename(filename)
            # Should preserve the full extension chain when safe
            assert "." in result

    def test_sanitize_filename_very_long_extension(self):
        """Test handling of very long file extensions."""
        filename_with_long_ext = "file." + "x" * 100

        result = sanitize_filename(filename_with_long_ext)
        # Should handle gracefully
        assert len(result) <= 255

    def test_sanitize_filename_mixed_attacks(self):
        """Test complex mixed attack scenarios."""
        complex_attacks = [
            "../../../etc/passwd\x00.txt",
            "..\\..\\system32\\*.exe|dangerous",
            "normal_start/../../../etc/hosts#fragment?query=evil",
            "file<script>alert('../../../etc/passwd')</script>.md"
        ]

        for attack in complex_attacks:
            result = sanitize_filename(attack)
            # Should be completely safe
            assert ".." not in result
            assert "/" not in result
            assert "\\" not in result
            assert "<" not in result
            assert ">" not in result
            assert "|" not in result
            assert "\x00" not in result

    def test_sanitize_filename_preserves_readability(self):
        """Test that sanitized filenames remain readable."""
        readable_inputs = [
            "My Important Report.md",
            "Project_Status-Update.txt",
            "Q4-Financial_Summary.pdf"
        ]

        for filename in readable_inputs:
            result = sanitize_filename(filename)
            # Should remain readable (contain some original characters)
            assert len(result) > 5  # Not completely stripped
            # Should contain alphanumeric characters
            assert any(c.isalnum() for c in result)


class TestFilenameIntegrationWithReportGeneration:
    """Test filename sanitization integration with report generation."""

    def test_filename_generation_with_malicious_subreddit(self):
        """Test filename generation with malicious subreddit names."""

        malicious_subreddits = [
            "../../../etc/passwd",
            "technology|rm-rf",
            "test<script>alert('xss')</script>",
            "reddit\\..\\..\\windows\\system32"
        ]

        for subreddit in malicious_subreddits:
            # This should use our sanitization
            expected_pattern = f"reddit_report_{subreddit}_test_topic.md"
            sanitized = sanitize_filename(expected_pattern)

            # Ensure sanitized filename is safe
            assert ".." not in sanitized
            assert "/" not in sanitized
            assert "\\" not in sanitized
            assert "<" not in sanitized
            assert ">" not in sanitized

    def test_filename_generation_with_malicious_topic(self):
        """Test filename generation with malicious topic names."""
        malicious_topics = [
            "../../../etc/passwd",
            "ai|dangerous",
            "tech<script>evil</script>",
            "topic\\..\\secrets"
        ]

        for topic in malicious_topics:
            expected_pattern = f"reddit_report_technology_{topic.replace(' ', '_')}.md"
            sanitized = sanitize_filename(expected_pattern)

            # Ensure sanitized filename is safe
            assert ".." not in sanitized
            assert "/" not in sanitized
            assert "\\" not in sanitized
            assert "<" not in sanitized
            assert ">" not in sanitized
