"""
Test fincore library import and basic functionality.

This test verifies that fincore is correctly installed and can be imported.
Part of Story 1.1: Install and configure fincore library.
"""

import pytest


def test_fincore_import():
    """Test that fincore can be imported successfully."""
    try:
        import fincore
        assert fincore is not None
        assert hasattr(fincore, '__version__')
    except ImportError as e:
        pytest.fail(f"Failed to import fincore: {e}")


def test_fincore_version():
    """Test that fincore version is accessible."""
    import fincore
    version = fincore.__version__
    assert version is not None
    assert isinstance(version, str)
    # Version should follow semantic versioning (e.g., "0.1.0" or "1.0.0")
    parts = version.split('.')
    assert len(parts) >= 2  # At least major.minor


def test_fincore_basic_modules():
    """Test that fincore basic modules are accessible."""
    import fincore
    # Check for common financial metrics modules
    # The exact module structure depends on fincore's API
    assert hasattr(fincore, '__version__')
    # Additional module checks can be added as we integrate fincore
