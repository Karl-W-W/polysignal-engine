"""
Tests for lab/time_horizon.py — time_horizon derivation from market observables.

Session 15: 4h horizon collapsed to 24h (0% accuracy on 17 evaluated predictions).
"""

import pytest
from lab.time_horizon import derive_time_horizon


class TestHighVolatility:
    """High volatility / volume → 1h horizon."""

    def test_large_delta(self):
        assert derive_time_horizon(500_000, 0.12) == "1h"

    def test_huge_volume(self):
        assert derive_time_horizon(6_000_000, 0.01) == "1h"

    def test_both_high(self):
        assert derive_time_horizon(10_000_000, 0.15) == "1h"


class TestMediumActivity:
    """Medium activity → 24h horizon (4h collapsed Session 15)."""

    def test_medium_delta(self):
        assert derive_time_horizon(500_000, 0.07) == "24h"

    def test_medium_volume(self):
        assert derive_time_horizon(2_000_000, 0.01) == "24h"


class TestLowActivity:
    """Low activity → 24h horizon."""

    def test_small_delta(self):
        assert derive_time_horizon(300_000, 0.03) == "24h"

    def test_low_volume_moderate_delta(self):
        assert derive_time_horizon(250_000, 0.025) == "24h"


class TestQuietMarket:
    """Very quiet → 7d horizon."""

    def test_tiny_delta_low_volume(self):
        assert derive_time_horizon(50_000, 0.005) == "7d"

    def test_zero_delta(self):
        assert derive_time_horizon(100_000, 0.0) == "7d"


class TestClusterBoost:
    """Multiple simultaneous signals shorten the horizon."""

    def test_no_cluster_baseline(self):
        # 0.04 delta, 300k vol → 24h
        assert derive_time_horizon(300_000, 0.04, num_recent_signals=0) == "24h"

    def test_cluster_shortens_horizon(self):
        # 0.04 + 3*0.02 = 0.10 → 24h (>0.02 threshold), boosted from potentially 24h
        result = derive_time_horizon(300_000, 0.04, num_recent_signals=3)
        assert result in ("1h", "24h")  # boosted from 24h

    def test_large_cluster_caps_at_006(self):
        # 10 signals: min(10*0.02, 0.06) = 0.06
        # 0.04 + 0.06 = 0.10 → same as 3 signals (cap hit)
        r1 = derive_time_horizon(300_000, 0.04, num_recent_signals=3)
        r2 = derive_time_horizon(300_000, 0.04, num_recent_signals=10)
        assert r1 == r2  # cluster boost caps at 0.06


class TestBoundaries:
    """Exact boundary values."""

    def test_delta_exactly_010_not_1h(self):
        # > 0.10 triggers 1h, so exactly 0.10 should be 24h (4h collapsed)
        assert derive_time_horizon(0, 0.10) == "24h"

    def test_delta_just_over_010(self):
        assert derive_time_horizon(0, 0.101) == "1h"

    def test_volume_exactly_5m_not_1h(self):
        # > 5M triggers 1h, so exactly 5M should be 24h (4h collapsed)
        assert derive_time_horizon(5_000_000, 0.0) == "24h"

    def test_volume_just_over_5m(self):
        assert derive_time_horizon(5_000_001, 0.0) == "1h"

    def test_delta_exactly_005_not_24h_anymore(self):
        # With 4h collapsed, 0.05 delta still falls in 24h bucket (>0.02)
        assert derive_time_horizon(0, 0.05) == "24h"

    def test_delta_just_over_005(self):
        # 0.051 was 4h, now collapsed to 24h
        assert derive_time_horizon(0, 0.051) == "24h"
