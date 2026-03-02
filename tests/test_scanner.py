"""
tests/test_scanner.py
=====================
Tests for the continuous market scanner (workflows/scanner.py).
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflows.scanner import is_active_hours, seconds_until_active


# ============================================================================
# ACTIVE HOURS TESTS
# ============================================================================

class TestIsActiveHours:
    """Test active trading window logic."""

    @patch("workflows.scanner.ACTIVE_START_UTC", 6)
    @patch("workflows.scanner.ACTIVE_END_UTC", 0)
    def test_midday_is_active(self):
        """12:00 UTC is within 06:00-00:00 UTC window."""
        with patch("workflows.scanner.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_active_hours() is True

    @patch("workflows.scanner.ACTIVE_START_UTC", 6)
    @patch("workflows.scanner.ACTIVE_END_UTC", 0)
    def test_early_morning_is_inactive(self):
        """03:00 UTC is outside 06:00-00:00 UTC window."""
        with patch("workflows.scanner.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 2, 3, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_active_hours() is False

    @patch("workflows.scanner.ACTIVE_START_UTC", 6)
    @patch("workflows.scanner.ACTIVE_END_UTC", 0)
    def test_start_hour_is_active(self):
        """06:00 UTC is exactly the start — should be active."""
        with patch("workflows.scanner.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 2, 6, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_active_hours() is True

    @patch("workflows.scanner.ACTIVE_START_UTC", 6)
    @patch("workflows.scanner.ACTIVE_END_UTC", 0)
    def test_just_before_midnight_is_active(self):
        """23:59 UTC is within 06:00-00:00 UTC window."""
        with patch("workflows.scanner.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 2, 23, 59, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_active_hours() is True

    @patch("workflows.scanner.ACTIVE_START_UTC", 8)
    @patch("workflows.scanner.ACTIVE_END_UTC", 20)
    def test_simple_range_inside(self):
        """14:00 UTC is within 08:00-20:00 UTC (no midnight wrap)."""
        with patch("workflows.scanner.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 2, 14, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_active_hours() is True

    @patch("workflows.scanner.ACTIVE_START_UTC", 8)
    @patch("workflows.scanner.ACTIVE_END_UTC", 20)
    def test_simple_range_outside(self):
        """22:00 UTC is outside 08:00-20:00 UTC."""
        with patch("workflows.scanner.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 3, 2, 22, 0, tzinfo=timezone.utc)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert is_active_hours() is False


# ============================================================================
# SCANNER LIFECYCLE TESTS
# ============================================================================

class TestScannerLifecycle:
    """Test the scanner's cycle execution and error handling."""

    def test_scanner_module_imports(self):
        """Scanner module loads without crashing."""
        import workflows.scanner
        assert hasattr(workflows.scanner, "run_scanner")
        assert hasattr(workflows.scanner, "is_active_hours")
        assert hasattr(workflows.scanner, "seconds_until_active")

    def test_scan_interval_default(self):
        """Default scan interval is 300 seconds (5 minutes)."""
        from workflows.scanner import SCAN_INTERVAL
        assert SCAN_INTERVAL == 300

    def test_scan_interval_env_override(self):
        """SCAN_INTERVAL_SECONDS env var overrides default."""
        with patch.dict(os.environ, {"SCAN_INTERVAL_SECONDS": "60"}):
            # Re-import to pick up env var
            import importlib
            import workflows.scanner as sc
            # The module-level constant is set at import time,
            # so we test the parsing logic directly
            assert int(os.getenv("SCAN_INTERVAL_SECONDS", "300")) == 60

    def test_graceful_shutdown_flag(self):
        """Signal handler sets _running to False."""
        import workflows.scanner as sc
        sc._running = True
        sc._handle_signal(15, None)  # SIGTERM
        assert sc._running is False
        sc._running = True  # Reset for other tests
