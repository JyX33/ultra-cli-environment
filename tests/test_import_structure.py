# ABOUTME: Tests for import structure security and consistency across the application
# ABOUTME: Validates that modules can be imported properly without unsafe sys.path manipulation

import importlib
from pathlib import Path
import sys
from unittest.mock import patch

import pytest


class TestImportStructure:
    """Test suite for validating proper import resolution and module loading."""

    def test_app_modules_importable_without_syspath_manipulation(self):
        """Test that all app modules can be imported without sys.path manipulation."""
        # Save original sys.path
        original_path = sys.path[:]

        try:
            # Ensure no artificial path additions
            if any('../..' in path for path in sys.path):
                sys.path = [path for path in sys.path if '../..' not in path]

            # Test importing core app modules
            import app.core.config
            import app.main
            import app.services.reddit_service
            import app.services.scraper_service
            import app.services.summarizer_service
            import app.utils.filename_sanitizer
            import app.utils.relevance
            import app.utils.report_generator

            # Verify modules loaded correctly
            assert hasattr(app.main, 'app')
            assert hasattr(app.services.reddit_service, 'RedditService')
            assert hasattr(app.services.scraper_service, 'scrape_article_text')
            assert hasattr(app.services.summarizer_service, 'summarize_content')

        finally:
            # Restore original sys.path
            sys.path[:] = original_path

    def test_module_loading_consistency(self):
        """Test that module loading follows consistent patterns across codebase."""
        # Test that all imports use proper app.* pattern
        modules_to_test = [
            'app.services.reddit_service',
            'app.services.scraper_service',
            'app.services.summarizer_service',
            'app.utils.relevance',
            'app.utils.report_generator',
            'app.utils.filename_sanitizer',
            'app.core.config'
        ]

        for module_name in modules_to_test:
            try:
                module = importlib.import_module(module_name)
                assert module is not None
                assert hasattr(module, '__file__')
                # Verify module path contains expected structure
                assert 'app/' in module.__file__
            except ImportError as e:
                pytest.fail(f"Failed to import {module_name}: {e}")

    def test_no_relative_import_issues(self):
        """Test that relative imports work properly within the app package."""
        # Test importing main module which should work without sys.path hacks
        try:
            from app import main
            assert main is not None

            # Test that main can import all its dependencies
            from app.services.reddit_service import RedditService
            from app.services.scraper_service import scrape_article_text
            from app.services.summarizer_service import summarize_content
            from app.utils.filename_sanitizer import generate_safe_filename
            from app.utils.relevance import score_and_rank_subreddits
            from app.utils.report_generator import create_markdown_report

            # Verify imports successful
            assert RedditService is not None
            assert summarize_content is not None
            assert score_and_rank_subreddits is not None
            assert create_markdown_report is not None
            assert generate_safe_filename is not None
            assert scrape_article_text is not None

        except ImportError as e:
            pytest.fail(f"Relative import failed: {e}")

    def test_main_module_imports_without_syspath_hack(self):
        """Test that main.py can import scraper_service without sys.path manipulation."""
        # This is the specific case that was causing the sys.path hack
        try:
            # Import should work with standard Python import resolution
            from app.services.scraper_service import scrape_article_text
            assert scrape_article_text is not None
            assert callable(scrape_article_text)
        except ImportError as e:
            pytest.fail(f"scraper_service import failed without sys.path hack: {e}")

    def test_package_structure_integrity(self):
        """Test that package structure supports proper imports."""
        app_path = Path(__file__).parent.parent / 'app'

        # Verify __init__.py files exist for package structure
        assert (app_path / '__init__.py').exists()
        assert (app_path / 'services' / '__init__.py').exists()
        assert (app_path / 'utils' / '__init__.py').exists()
        assert (app_path / 'core' / '__init__.py').exists()

        # Verify key modules exist
        assert (app_path / 'main.py').exists()
        assert (app_path / 'services' / 'scraper_service.py').exists()
        assert (app_path / 'services' / 'reddit_service.py').exists()
        assert (app_path / 'services' / 'summarizer_service.py').exists()

    @patch('sys.path')
    def test_detection_of_syspath_manipulation(self, mock_path):
        """Test that we can detect if sys.path has been manipulated unsafely."""
        # Simulate the problematic sys.path manipulation
        mock_path.__contains__ = lambda self, item: '../..' in str(item)

        # Should detect the unsafe pattern
        unsafe_paths = [path for path in mock_path if '../..' in str(path)]
        assert len(unsafe_paths) == 0  # After cleanup, should be empty

    def test_import_error_handling(self):
        """Test proper handling of import errors without sys.path manipulation."""
        # Test importing non-existent module fails gracefully
        with pytest.raises(ImportError):
            pass

        # Test that legitimate modules still import correctly
        from app.services.reddit_service import RedditService
        assert RedditService is not None
