#!/usr/bin/env python3
"""
lab/trade_proposal_bridge.py
============================
Typed bridge: Signal → TradeProposal

Eliminates manual dict-munging scattered across risk_integration.py and
future consumers. Single source of truth for the conversion.

Promotion target: core/trade_bridge.py (after human approval)

Usage:
    from lab.trade_proposal_bridge import TradeProposal_from_signal

    signal = Signal(...)         # or signal_dict from .to_dict()
    proposal = TradeProposal_from_signal(signal)
    if proposal:
        verdict = check_risk(proposal, tracker)
"""

import os
import sys
import uuid
from typing import Optional, Union, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.signal_model import Signal
from core.risk import TradeProposal, MAX_POSITION_USDC


# ============================================================================
# HYPOTHESIS → SIDE MAPPING
# ============================================================================

_HYPOTHESIS_TO_SIDE = {
    "Bullish":  ("BUY",  "Yes"),
    "Bearish":  ("SELL", "No"),
    "Neutral":  ("BUY",  "Yes"),  # Conservative default — don't sell on neutral
}

_DIRECTION_TO_SIDE = {
    "📈":       ("BUY",  "Yes"),
    "📉":       ("SELL", "No"),
    "Bullish":  ("BUY",  "Yes"),
    "Bearish":  ("SELL", "No"),
    "UP":       ("BUY",  "Yes"),
    "DOWN":     ("SELL", "No"),
}


# ============================================================================
# BRIDGE FUNCTION
# ============================================================================

def TradeProposal_from_signal(
    signal: Union[Signal, Dict[str, Any]],
    proposed_size_usdc: float = 5.0,
) -> Optional[TradeProposal]:
    """
    Convert a Signal (or signal dict) into a TradeProposal.

    Args:
        signal: A Signal object or dict from Signal.to_dict()
        proposed_size_usdc: Default position size (clamped to MAX_POSITION_USDC)

    Returns:
        TradeProposal if signal is actionable (Bullish/Bearish),
        None if Neutral with no clear direction.
    """
    # Handle both typed Signal and raw dict
    if isinstance(signal, dict):
        hypothesis = signal.get("hypothesis", "Neutral")
        confidence = signal.get("confidence", 0.5)
        market_id = signal.get("market_id", "unknown")
        title = signal.get("title", "Unknown Market")
        outcome = signal.get("outcome", "")
        current_price = signal.get("current_price", 0.5)
        signal_id = signal.get("signal_id", str(uuid.uuid4()))
        direction = signal.get("direction", "")  # From observation format
    else:
        hypothesis = signal.hypothesis
        confidence = signal.confidence
        market_id = signal.market_id
        title = signal.title
        outcome = signal.outcome
        current_price = signal.current_price
        signal_id = signal.signal_id
        direction = ""  # Signal objects use hypothesis, not direction

    # Determine side + outcome
    if hypothesis in _HYPOTHESIS_TO_SIDE and hypothesis != "Neutral":
        side, derived_outcome = _HYPOTHESIS_TO_SIDE[hypothesis]
    elif direction in _DIRECTION_TO_SIDE:
        side, derived_outcome = _DIRECTION_TO_SIDE[direction]
    else:
        # Neutral with no direction — not actionable
        return None

    # Use signal's outcome if present, otherwise derive from hypothesis
    if not outcome:
        outcome = derived_outcome

    # Clamp size
    size = min(proposed_size_usdc, MAX_POSITION_USDC)

    return TradeProposal(
        market_id=market_id,
        title=title,
        outcome=outcome,
        side=side,
        confidence=confidence,
        proposed_size_usdc=size,
        current_price=current_price,
        signal_id=signal_id,
    )


def from_observation_dict(
    obs: Dict[str, Any],
    proposed_size_usdc: float = 5.0,
) -> Optional[TradeProposal]:
    """
    Convert a masterloop observation dict to TradeProposal.

    Observation dicts come from _signal_to_observation() in masterloop.py
    and have a different shape than Signal objects (direction instead of
    hypothesis, no signal_id, etc).

    This replaces observation_to_trade_proposal() in risk_integration.py.
    """
    direction = obs.get("direction", "")
    if not direction or direction not in _DIRECTION_TO_SIDE:
        return None

    side, outcome = _DIRECTION_TO_SIDE[direction]
    size = min(proposed_size_usdc, MAX_POSITION_USDC)

    return TradeProposal(
        market_id=obs.get("market_id", "unknown"),
        title=obs.get("title", "Unknown Market"),
        outcome=outcome,
        side=side,
        confidence=obs.get("confidence", 0.5),
        proposed_size_usdc=size,
        current_price=obs.get("price", 0.5),
        signal_id=str(uuid.uuid4()),
    )


# ============================================================================
# TESTS
# ============================================================================

def _run_tests():
    from core.signal_model import Signal, SignalSource
    from core.risk import TradeProposal as TP

    print("=" * 60)
    print("TradeProposal Bridge — Tests")
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

    # --- Test 1: Bullish Signal object → BUY ---
    print("\n[Test 1] Bullish Signal → BUY TradeProposal")
    sig = Signal(
        market_id="0xabc",
        title="BTC above $100k",
        outcome="Yes",
        polymarket_url="https://polymarket.com/event/btc-100k",
        current_price=0.71,
        volume_24h=1_000_000,
        change_since_last=0.08,
        hypothesis="Bullish",
        confidence=0.85,
        source=SignalSource(method="momentum", raw_value=0.08, threshold=0.05),
        reasoning="Strong move up.",
    )
    tp = TradeProposal_from_signal(sig)
    assert_test("Not None", tp is not None)
    assert_test("Side is BUY", tp.side == "BUY")
    assert_test("Outcome is Yes", tp.outcome == "Yes")
    assert_test("Confidence carried", tp.confidence == 0.85)
    assert_test("Market ID carried", tp.market_id == "0xabc")
    assert_test("Price carried", tp.current_price == 0.71)
    assert_test("Default size $5", tp.proposed_size_usdc == 5.0)

    # --- Test 2: Bearish Signal object → SELL ---
    print("\n[Test 2] Bearish Signal → SELL TradeProposal")
    sig2 = Signal(
        market_id="0xdef",
        title="ETH above $5k",
        outcome="No",
        polymarket_url="https://polymarket.com/event/eth-5k",
        current_price=0.35,
        volume_24h=500_000,
        hypothesis="Bearish",
        confidence=0.78,
        source=SignalSource(method="volume_spike", raw_value=2.5, threshold=2.0),
        reasoning="Volume dropping.",
    )
    tp2 = TradeProposal_from_signal(sig2)
    assert_test("Side is SELL", tp2.side == "SELL")
    assert_test("Outcome preserved (No)", tp2.outcome == "No")

    # --- Test 3: Neutral Signal → None ---
    print("\n[Test 3] Neutral Signal → None (not actionable)")
    sig3 = Signal(
        market_id="0xghi",
        title="Quiet market",
        outcome="Yes",
        polymarket_url="https://polymarket.com/event/quiet",
        current_price=0.50,
        volume_24h=100_000,
        hypothesis="Neutral",
        confidence=0.5,
        source=SignalSource(method="baseline", raw_value=0.01, threshold=0.05),
        reasoning="No signal.",
    )
    tp3 = TradeProposal_from_signal(sig3)
    assert_test("Neutral returns None", tp3 is None)

    # --- Test 4: Signal dict (from .to_dict()) ---
    print("\n[Test 4] Signal dict → TradeProposal")
    sig_dict = sig.to_dict()
    tp4 = TradeProposal_from_signal(sig_dict)
    assert_test("Dict works", tp4 is not None)
    assert_test("Side correct", tp4.side == "BUY")
    assert_test("Confidence from dict", tp4.confidence == 0.85)

    # --- Test 5: Size clamping ---
    print("\n[Test 5] Size clamping to MAX_POSITION_USDC")
    tp5 = TradeProposal_from_signal(sig, proposed_size_usdc=100.0)
    assert_test(f"Clamped to ${MAX_POSITION_USDC}", tp5.proposed_size_usdc == MAX_POSITION_USDC)

    # --- Test 6: Observation dict (masterloop format) ---
    print("\n[Test 6] Observation dict → TradeProposal (from_observation_dict)")
    obs = {
        "market_id": "0xtest",
        "title": "BTC above $100k — Yes",
        "price": 0.71,
        "volume": 1_000_000,
        "change_24h": 0.05,
        "direction": "📈",
        "url": "https://polymarket.com/event/btc-100k",
        "source": "polymarket",
        "confidence": 0.82,
    }
    tp6 = from_observation_dict(obs)
    assert_test("Not None", tp6 is not None)
    assert_test("Direction 📈 → BUY", tp6.side == "BUY")
    assert_test("Price from obs", tp6.current_price == 0.71)

    # --- Test 7: Empty direction observation → None ---
    print("\n[Test 7] Quiet observation → None")
    obs_quiet = {"market_id": "0x", "title": "Test", "price": 0.5, "direction": ""}
    tp7 = from_observation_dict(obs_quiet)
    assert_test("Empty direction → None", tp7 is None)

    # --- Test 8: Signal with direction field (hybrid dict) ---
    print("\n[Test 8] Dict with direction but no hypothesis")
    hybrid = {
        "market_id": "0xhyb",
        "title": "Test hybrid",
        "current_price": 0.6,
        "direction": "📉",
        "confidence": 0.77,
        "hypothesis": "Neutral",  # Neutral hypothesis but bearish direction
    }
    tp8 = TradeProposal_from_signal(hybrid)
    assert_test("Falls back to direction", tp8 is not None)
    assert_test("Direction 📉 → SELL", tp8.side == "SELL")

    # --- Summary ---
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
