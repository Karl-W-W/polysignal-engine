"""
core/risk.py
============
PolySignal-OS Risk Management Module.
Promoted from lab/polymarket/risk.py — Session 7 (2026-03-01).

HARD RULES — non-negotiable:
  • MAX_POSITION_USDC = 10     → max $10 per trade
  • MIN_CONFIDENCE = 0.75      → minimum MasterLoop predictor confidence
  • DAILY_LOSS_CAP_USDC = 50   → hard stop, no more trades today if hit
  • HUMAN_APPROVAL_FIRST_N = 5 → first 5 live trades require Telegram YES
  • TRADING_ENABLED = False     → kill switch, default OFF

RenTec Principle: Friction Awareness.
Execution costs destroy theoretical alpha. All limits are intentionally tight.

Lab Promotion Protocol: ✅ COMPLETED
  1. Built in /lab ✅
  2. Standalone test passes (7/7 self-test + 11/11 pytest) ✅
  3. Human explicitly authorized promotion (Session 7) ✅
  4. Moved to /core ✅
"""

import os
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict, field
from typing import Optional, List, Tuple

# ============================================================================
# HARD LIMITS — CHANGE THESE ONLY WITH EXPLICIT HUMAN AUTHORIZATION
# ============================================================================

MAX_POSITION_USDC: float = 10.0       # Max $10 per trade
MIN_CONFIDENCE: float = 0.75          # Minimum predictor confidence (0–1)
DAILY_LOSS_CAP_USDC: float = 50.0     # Hard stop for the day
HUMAN_APPROVAL_FIRST_N: int = 5       # First N trades need Telegram YES
TRADING_ENABLED: bool = False         # Kill switch — default OFF

# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class TradeProposal:
    """A proposed trade that must pass all risk checks before execution."""
    market_id: str
    title: str
    outcome: str              # "Yes" or "No"
    side: str                 # "BUY" or "SELL"
    confidence: float         # From MasterLoop predictor (0–1)
    proposed_size_usdc: float # Requested position size
    current_price: float      # Current implied probability (0–1)
    signal_id: str            # UUID from the Signal that triggered this
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RiskVerdict:
    """Result of a risk check — either approved or rejected with reason."""
    approved: bool
    trade: TradeProposal
    approved_size_usdc: float  # May be clamped down from proposed
    rejection_reason: Optional[str] = None
    requires_human_approval: bool = False
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)

    def to_telegram_message(self) -> str:
        """Format for Telegram human-in-the-loop alert."""
        status = "✅ APPROVED" if self.approved else "❌ REJECTED"
        msg = (
            f"{'🔒' if self.requires_human_approval else '🤖'} TRADE RISK CHECK: {status}\n"
            f"Market: {self.trade.title}\n"
            f"Side: {self.trade.side} {self.trade.outcome}\n"
            f"Size: ${self.approved_size_usdc:.2f} USDC.e\n"
            f"Confidence: {self.trade.confidence:.0%}\n"
            f"Price: {self.trade.current_price:.2%}\n"
        )
        if self.requires_human_approval:
            msg += "\n⚠️ HUMAN APPROVAL REQUIRED — Reply YES to execute, NO to cancel."
        if self.rejection_reason:
            msg += f"\nReason: {self.rejection_reason}"
        return msg


# ============================================================================
# DAILY P&L TRACKER
# ============================================================================

class DailyPnLTracker:
    """
    Tracks daily realized P&L and trade count.
    Persists to a JSON file so state survives restarts.
    """

    def __init__(self, state_path: str = "/opt/loop/data/risk_state.json"):
        self.state_path = state_path
        self._state = self._load()

    def _load(self) -> dict:
        """Load state from disk, or initialize fresh."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        default = {
            "date": today,
            "total_trades": 0,
            "daily_loss_usdc": 0.0,
            "trades_today": 0,
            "trade_log": [],
        }
        try:
            with open(self.state_path, "r") as f:
                state = json.load(f)
                # Reset if it's a new day
                if state.get("date") != today:
                    return default
                return state
        except (FileNotFoundError, json.JSONDecodeError):
            return default

    def save(self):
        """Persist state to disk."""
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            with open(self.state_path, "w") as f:
                json.dump(self._state, f, indent=2)
        except Exception as e:
            print(f"⚠ Risk state save failed: {e}")

    @property
    def total_trades(self) -> int:
        return self._state["total_trades"]

    @property
    def trades_today(self) -> int:
        return self._state["trades_today"]

    @property
    def daily_loss_usdc(self) -> float:
        return self._state["daily_loss_usdc"]

    def record_trade(self, trade: TradeProposal, size_usdc: float):
        """Record an executed trade."""
        self._state["total_trades"] += 1
        self._state["trades_today"] += 1
        self._state["trade_log"].append({
            "signal_id": trade.signal_id,
            "market_id": trade.market_id,
            "side": trade.side,
            "size_usdc": size_usdc,
            "timestamp": trade.timestamp,
        })
        self.save()

    def record_loss(self, loss_usdc: float):
        """Record a realized loss (positive number = loss amount)."""
        self._state["daily_loss_usdc"] += abs(loss_usdc)
        self.save()

    def is_daily_cap_hit(self) -> bool:
        return self._state["daily_loss_usdc"] >= DAILY_LOSS_CAP_USDC

    def needs_human_approval(self) -> bool:
        return self._state["total_trades"] < HUMAN_APPROVAL_FIRST_N


# ============================================================================
# RISK GATE — THE CORE FUNCTION
# ============================================================================

def check_risk(trade: TradeProposal, tracker: Optional[DailyPnLTracker] = None) -> RiskVerdict:
    """
    Run all risk checks on a proposed trade.
    Returns a RiskVerdict with approval status.

    Checks (in order):
      1. Kill switch (TRADING_ENABLED)
      2. Confidence threshold (MIN_CONFIDENCE)
      3. Position size cap (MAX_POSITION_USDC)
      4. Daily loss cap (DAILY_LOSS_CAP_USDC)
      5. Human approval gate (first N trades)
    """
    checks_passed = []
    checks_failed = []

    # --- Check 1: Kill switch ---
    if not TRADING_ENABLED:
        return RiskVerdict(
            approved=False,
            trade=trade,
            approved_size_usdc=0.0,
            rejection_reason="TRADING_ENABLED=false — kill switch is active",
            checks_failed=["kill_switch"],
        )
    checks_passed.append("kill_switch")

    # --- Check 2: Confidence threshold ---
    if trade.confidence < MIN_CONFIDENCE:
        return RiskVerdict(
            approved=False,
            trade=trade,
            approved_size_usdc=0.0,
            rejection_reason=(
                f"Confidence {trade.confidence:.2f} < MIN_CONFIDENCE {MIN_CONFIDENCE}"
            ),
            checks_passed=checks_passed,
            checks_failed=["min_confidence"],
        )
    checks_passed.append("min_confidence")

    # --- Check 3: Position size cap ---
    approved_size = min(trade.proposed_size_usdc, MAX_POSITION_USDC)
    if trade.proposed_size_usdc > MAX_POSITION_USDC:
        # Clamp, don't reject — but note the clamping
        checks_passed.append(f"position_size_clamped_{trade.proposed_size_usdc}->{approved_size}")
    else:
        checks_passed.append("position_size")

    # --- Check 4: Daily loss cap ---
    if tracker and tracker.is_daily_cap_hit():
        return RiskVerdict(
            approved=False,
            trade=trade,
            approved_size_usdc=0.0,
            rejection_reason=(
                f"Daily loss cap reached: ${tracker.daily_loss_usdc:.2f} >= "
                f"${DAILY_LOSS_CAP_USDC:.2f} — no more trades today"
            ),
            checks_passed=checks_passed,
            checks_failed=["daily_loss_cap"],
        )
    checks_passed.append("daily_loss_cap")

    # --- Check 5: Human approval gate ---
    needs_human = tracker.needs_human_approval() if tracker else True
    if needs_human:
        checks_passed.append("human_approval_required")

    return RiskVerdict(
        approved=True,
        trade=trade,
        approved_size_usdc=approved_size,
        requires_human_approval=needs_human,
        checks_passed=checks_passed,
        checks_failed=checks_failed,
    )


# ============================================================================
# STANDALONE TEST — Run with: python3 lab/polymarket/risk.py
# ============================================================================

def _run_tests():
    """Self-contained test suite. Zero external dependencies."""
    print("=" * 60)
    print("PolySignal-OS Risk Module — Self-Test")
    print("=" * 60)
    passed = 0
    failed = 0

    def assert_test(name: str, condition: bool, detail: str = ""):
        nonlocal passed, failed
        if condition:
            print(f"  ✅ {name}")
            passed += 1
        else:
            print(f"  ❌ {name}: {detail}")
            failed += 1

    # --- Synthetic trade proposals ---
    good_trade = TradeProposal(
        market_id="0xtest1",
        title="Bitcoin above $70k by March 2026",
        outcome="Yes",
        side="BUY",
        confidence=0.82,
        proposed_size_usdc=8.0,
        current_price=0.71,
        signal_id="test-signal-001",
    )

    low_confidence_trade = TradeProposal(
        market_id="0xtest2",
        title="ETH above $5k by April 2026",
        outcome="Yes",
        side="BUY",
        confidence=0.60,  # Below MIN_CONFIDENCE
        proposed_size_usdc=5.0,
        current_price=0.45,
        signal_id="test-signal-002",
    )

    oversized_trade = TradeProposal(
        market_id="0xtest3",
        title="SOL above $300 by March 2026",
        outcome="Yes",
        side="BUY",
        confidence=0.90,
        proposed_size_usdc=50.0,  # Way over MAX_POSITION_USDC
        current_price=0.55,
        signal_id="test-signal-003",
    )

    # Use in-memory tracker (no disk I/O during tests)
    class MockTracker(DailyPnLTracker):
        def __init__(self):
            self._state = {
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "total_trades": 0,
                "daily_loss_usdc": 0.0,
                "trades_today": 0,
                "trade_log": [],
            }
        def save(self): pass  # No disk writes during test

    tracker = MockTracker()

    # ---- TEST 1: Kill switch blocks all trades ----
    print("\n[Test 1] Kill switch (TRADING_ENABLED=false)")
    # TRADING_ENABLED is False by default
    v = check_risk(good_trade, tracker)
    assert_test("Kill switch blocks trade", not v.approved)
    assert_test("Reason mentions kill switch", "kill switch" in (v.rejection_reason or "").lower())

    # ---- Enable trading for remaining tests ----
    global TRADING_ENABLED
    TRADING_ENABLED = True

    # ---- TEST 2: Confidence threshold ----
    print("\n[Test 2] Confidence threshold (MIN_CONFIDENCE=0.75)")
    v = check_risk(low_confidence_trade, tracker)
    assert_test("Low confidence rejected", not v.approved)
    assert_test("Reason mentions confidence",
                "confidence" in (v.rejection_reason or "").lower())

    v = check_risk(good_trade, tracker)
    assert_test("Good confidence approved", v.approved)

    # ---- TEST 3: Position size clamping ----
    print("\n[Test 3] Position size cap (MAX_POSITION_USDC=10)")
    v = check_risk(oversized_trade, tracker)
    assert_test("Oversized trade still approved (clamped)", v.approved)
    assert_test(f"Size clamped to ${MAX_POSITION_USDC}",
                v.approved_size_usdc == MAX_POSITION_USDC,
                f"got {v.approved_size_usdc}")

    v = check_risk(good_trade, tracker)
    assert_test("Normal size passes unclamped",
                v.approved_size_usdc == good_trade.proposed_size_usdc)

    # ---- TEST 4: Daily loss cap ----
    print("\n[Test 4] Daily loss cap (DAILY_LOSS_CAP_USDC=50)")
    tracker.record_loss(51.0)  # Exceed the cap
    v = check_risk(good_trade, tracker)
    assert_test("Trade blocked after daily cap hit", not v.approved)
    assert_test("Reason mentions daily loss",
                "daily loss cap" in (v.rejection_reason or "").lower())

    # Reset for next tests
    tracker._state["daily_loss_usdc"] = 0.0

    # ---- TEST 5: Human approval gate ----
    print("\n[Test 5] Human approval gate (first N=5 trades)")
    tracker._state["total_trades"] = 0
    v = check_risk(good_trade, tracker)
    assert_test("Trade #1 requires human approval", v.requires_human_approval)

    tracker._state["total_trades"] = 4
    v = check_risk(good_trade, tracker)
    assert_test("Trade #5 still requires human approval", v.requires_human_approval)

    tracker._state["total_trades"] = 5
    v = check_risk(good_trade, tracker)
    assert_test("Trade #6 does NOT require human approval", not v.requires_human_approval)

    # ---- TEST 6: Telegram message formatting ----
    print("\n[Test 6] Telegram message formatting")
    tracker._state["total_trades"] = 0
    v = check_risk(good_trade, tracker)
    msg = v.to_telegram_message()
    assert_test("Message contains market title", good_trade.title in msg)
    assert_test("Message contains APPROVED", "APPROVED" in msg)
    assert_test("Message mentions human approval", "HUMAN APPROVAL" in msg)

    # ---- TEST 7: Trade recording ----
    print("\n[Test 7] Trade recording")
    tracker._state["total_trades"] = 0
    tracker._state["trades_today"] = 0
    tracker.record_trade(good_trade, 8.0)
    assert_test("Total trades incremented", tracker.total_trades == 1)
    assert_test("Trades today incremented", tracker.trades_today == 1)
    assert_test("Trade log has entry", len(tracker._state["trade_log"]) == 1)

    # ---- SUMMARY ----
    print("\n" + "=" * 60)
    total = passed + failed
    if failed == 0:
        print(f"✅ ALL {total} TESTS PASSED — risk.py is ready for review")
    else:
        print(f"❌ {failed}/{total} TESTS FAILED")
    print("=" * 60)

    # Reset kill switch
    TRADING_ENABLED = False
    return failed == 0


if __name__ == "__main__":
    _run_tests()
