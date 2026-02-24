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
    except ImportError as e:
        pytest.fail(f"Failed to import fincore: {e}")


def test_fincore_version():
    """Test that fincore version is accessible (if provided)."""
    import fincore
    # Some installations expose __version__, others don't (namespace package)
    if hasattr(fincore, '__version__'):
        version = fincore.__version__
        assert isinstance(version, str)
        parts = version.split('.')
        assert len(parts) >= 2  # At least major.minor


def test_fincore_basic_modules():
    """Test that fincore basic modules are accessible."""
    import fincore
    # Verify the module is importable and is a proper module object
    assert hasattr(fincore, '__name__')
    assert fincore.__name__ == 'fincore'
    # Additional module checks can be added as we integrate fincore
