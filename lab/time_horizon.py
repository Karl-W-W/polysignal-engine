#!/usr/bin/env python3
"""
lab/time_horizon.py
===================
Derives time_horizon from observable market data.
Kills the dead field — makes it computed instead of always "24h".

Promotion target: utility function, called by bitcoin_signal.py and predict.py
"""

from typing import Literal

TimeHorizon = Literal["1h", "4h", "24h", "7d"]


def derive_time_horizon(
    volume_24h: float,
    abs_price_delta: float,
    num_recent_signals: int = 0,
) -> TimeHorizon:
    """
    Derive signal validity window from market observables.

    Logic:
    - High volatility + high volume = fast-moving → 1h (signal decays fast)
    - Medium activity → 4h
    - Low activity → 24h
    - Very quiet → 7d (slow resolution market)

    Args:
        volume_24h: 24h trading volume in USD
        abs_price_delta: Absolute price change (0-1 scale, e.g. 0.08 = 8pp)
        num_recent_signals: Number of signals detected in this scan (cluster = shorter horizon)
    """
    # Cluster penalty: many signals at once = volatile environment
    cluster_boost = min(num_recent_signals * 0.02, 0.06)
    effective_delta = abs_price_delta + cluster_boost

    # Session 15: 4h horizon had 0% accuracy (0W/17L across 134 evals).
    # Prediction markets move too slowly for 4h windows.
    # Collapsed 4h → 24h. Only 1h survives for extreme volatility.
    if effective_delta > 0.10 or volume_24h > 5_000_000:
        return "1h"
    elif effective_delta > 0.02 or volume_24h > 200_000:
        return "24h"
    else:
        return "7d"


# ============================================================================
# TESTS
# ============================================================================

def _run_tests():
    print("=" * 60)
    print("time_horizon derivation — Tests")
    print("=" * 60)

    passed = 0
    failed = 0

    def assert_test(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"  ✅ {name}")
            passed += 1
        else:
            print(f"  ❌ {name}: {detail}")
            failed += 1

    # Test 1: High volatility → 1h
    print("\n[Test 1] High volatility")
    assert_test("Large delta → 1h", derive_time_horizon(500_000, 0.12) == "1h")
    assert_test("Huge volume → 1h", derive_time_horizon(6_000_000, 0.01) == "1h")

    # Test 2: Medium activity → 24h (4h collapsed to 24h — Session 15)
    print("\n[Test 2] Medium activity")
    assert_test("Medium delta → 24h", derive_time_horizon(500_000, 0.07) == "24h")
    assert_test("Medium volume → 24h", derive_time_horizon(2_000_000, 0.01) == "24h")

    # Test 3: Low activity → 24h
    print("\n[Test 3] Low activity")
    assert_test("Small delta → 24h", derive_time_horizon(300_000, 0.03) == "24h")

    # Test 4: Very quiet → 7d
    print("\n[Test 4] Very quiet market")
    assert_test("Tiny delta + low vol → 7d", derive_time_horizon(50_000, 0.005) == "7d")

    # Test 5: Cluster boost
    print("\n[Test 5] Signal cluster boosts urgency")
    # Without cluster: 0.04 delta, 300k vol → 24h
    assert_test("No cluster → 24h", derive_time_horizon(300_000, 0.04, 0) == "24h")
    # With 3 signals: 0.04 + 0.06 = 0.10 → bumps to 1h
    assert_test("3 signals → 1h", derive_time_horizon(300_000, 0.04, 3) == "1h")

    # Test 6: Boundary values
    print("\n[Test 6] Boundaries")
    assert_test("Exact 0.10 → 24h", derive_time_horizon(0, 0.10) == "24h")  # >0.10, not >=
    assert_test("Just over 0.10 → 1h", derive_time_horizon(0, 0.101) == "1h")
    assert_test("Exact 5M vol → 24h", derive_time_horizon(5_000_000, 0.0) == "24h")  # >5M, not >=
    assert_test("Just over 5M → 1h", derive_time_horizon(5_000_001, 0.0) == "1h")

    # Summary
    print("\n" + "=" * 60)
    total = passed + failed
    if failed == 0:
        print(f"✅ ALL {total} TESTS PASSED")
    else:
        print(f"❌ {failed}/{total} TESTS FAILED")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    success = _run_tests()
    exit(0 if success else 1)
