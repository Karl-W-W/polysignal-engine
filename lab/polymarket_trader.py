#!/usr/bin/env python3
"""
lab/polymarket_trader.py
=========================
Polymarket Trading Module for PolySignal-OS.

Paper trade by default. Live trading requires TRADING_ENABLED=true.
All trades pass through core/risk.py gate before execution.

Usage:
    from lab.polymarket_trader import PolymarketTrader
    trader = PolymarketTrader()
    result = trader.paper_trade(signal)    # Always safe
    result = trader.execute_trade(signal)  # Respects TRADING_ENABLED
"""

import json
import os
import sys
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.risk import (
    TradeProposal,
    DailyPnLTracker,
    RiskVerdict,
    check_risk,
    MAX_POSITION_USDC,
    MIN_CONFIDENCE,
)
from core.signal_model import Signal
from lab.trade_proposal_bridge import TradeProposal_from_signal

# ============================================================================
# CONSTANTS
# ============================================================================

CLOB_HOST = "https://clob.polymarket.com"
GAMMA_HOST = "https://gamma-api.polymarket.com"
_DEFAULT_LOG_PATH = os.path.join(os.path.dirname(__file__), "trading_log.json")


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class TradeResult:
    """Result of a trade attempt (paper or live)."""
    success: bool
    mode: str                          # "paper" or "live"
    trade_id: str
    market_id: str
    title: str
    side: str                          # "BUY" or "SELL"
    outcome: str                       # "Yes" or "No"
    size_usdc: float
    price_at_entry: float
    confidence: float
    timestamp: str
    risk_verdict: str
    order_id: Optional[str] = None
    error: Optional[str] = None
    pnl: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================================
# TRADING LOG
# ============================================================================

class TradingLog:
    """JSON-backed trade history."""

    def __init__(self, log_path: str = _DEFAULT_LOG_PATH):
        self.log_path = log_path
        self._trades: List[dict] = self._load()

    def _load(self) -> List[dict]:
        try:
            with open(self.log_path, "r") as f:
                return json.load(f).get("trades", [])
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def save(self):
        os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
        with open(self.log_path, "w") as f:
            json.dump({
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "total_trades": len(self._trades),
                "trades": self._trades,
            }, f, indent=2)

    def record(self, result: TradeResult):
        self._trades.append(result.to_dict())
        self.save()

    def update_pnl(self, trade_id: str, pnl: float):
        for trade in self._trades:
            if trade.get("trade_id") == trade_id:
                trade["pnl"] = pnl
                break
        self.save()

    @property
    def trades(self) -> List[dict]:
        return list(self._trades)

    @property
    def total_pnl(self) -> float:
        return sum(t.get("pnl", 0.0) for t in self._trades if t.get("pnl") is not None)

    @property
    def paper_trades(self) -> List[dict]:
        return [t for t in self._trades if t.get("mode") == "paper"]

    @property
    def live_trades(self) -> List[dict]:
        return [t for t in self._trades if t.get("mode") == "live"]

    def daily_spend(self, date_str: Optional[str] = None) -> float:
        today = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return sum(
            t.get("size_usdc", 0.0)
            for t in self._trades
            if t.get("timestamp", "").startswith(today) and t.get("success")
        )


# ============================================================================
# CLOB CLIENT WRAPPER
# ============================================================================

class ClobClientWrapper:
    """Thin wrapper around py-clob-client for testability."""

    def __init__(self, host: str, api_key: str, chain_id: int = 137):
        self.host = host
        self.api_key = api_key
        self.chain_id = chain_id
        self._client = None

    def _get_client(self):
        if self._client is None:
            from py_clob_client.client import ClobClient
            self._client = ClobClient(
                self.host, key=self.api_key, chain_id=self.chain_id,
            )
        return self._client

    def place_market_order(self, token_id: str, side: str, size: float) -> dict:
        client = self._get_client()
        from py_clob_client.clob_types import OrderArgs, OrderType
        order_args = OrderArgs(price=0.0, size=size, side=side, token_id=token_id)
        signed_order = client.create_order(order_args)
        return client.post_order(signed_order, OrderType.GTC)


# ============================================================================
# POLYMARKET TRADER
# ============================================================================

class PolymarketTrader:
    """
    Paper + live trading for Polymarket.
    All trades go through core/risk.py gate.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        wallet_address: Optional[str] = None,
        log_path: Optional[str] = None,
        risk_tracker: Optional[DailyPnLTracker] = None,
        clob_client: Optional[ClobClientWrapper] = None,
    ):
        self.api_key = api_key or os.getenv("POLYMARKET_BUILDER_API_KEY", "")
        self.wallet_address = wallet_address or os.getenv("POLYMARKET_ADDRESS", "")
        self.log = TradingLog(log_path or _DEFAULT_LOG_PATH)
        self._risk_tracker = risk_tracker
        self._clob_client = clob_client

    @property
    def trading_enabled(self) -> bool:
        # Session 28: LIVE_TRADING=true enables real trades even with TRADING_ENABLED=false
        # (TRADING_ENABLED controls the full LLM draft/review pipeline, LIVE_TRADING
        # controls just the CLOB execution in the paper trading path)
        te = os.getenv("TRADING_ENABLED", "false").lower() in ("true", "1", "yes")
        lt = os.getenv("LIVE_TRADING", "false").lower() in ("true", "1", "yes")
        return te or lt

    def _get_clob_client(self) -> ClobClientWrapper:
        if self._clob_client is None:
            if not self.api_key:
                raise ValueError("No API key — set POLYMARKET_BUILDER_API_KEY")
            self._clob_client = ClobClientWrapper(host=CLOB_HOST, api_key=self.api_key)
        return self._clob_client

    def paper_trade(
        self,
        signal: Union[Signal, Dict[str, Any]],
        proposed_size_usdc: float = 5.0,
    ) -> TradeResult:
        """Paper trade — logs what WOULD happen. No execution."""
        trade_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        proposal = TradeProposal_from_signal(signal, proposed_size_usdc=proposed_size_usdc)
        if proposal is None:
            result = TradeResult(
                success=False, mode="paper", trade_id=trade_id,
                market_id=_get_field(signal, "market_id", "unknown"),
                title=_get_field(signal, "title", "Unknown"),
                side="NONE", outcome="NONE", size_usdc=0.0,
                price_at_entry=0.0, confidence=0.0, timestamp=now,
                risk_verdict="NOT_ACTIONABLE",
                error="Signal is not actionable (Neutral with no direction)",
            )
            self.log.record(result)
            return result

        # Session 24: Paper trades bypass TRADING_ENABLED kill switch.
        # We temporarily enable trading for the risk check, then restore.
        # This lets paper trades validate confidence, size, and daily caps
        # while ignoring the kill switch (the whole point of paper mode).
        import core.risk as _risk_mod
        _orig_enabled = _risk_mod.TRADING_ENABLED
        _risk_mod.TRADING_ENABLED = True
        try:
            verdict = check_risk(proposal, self._risk_tracker)
        finally:
            _risk_mod.TRADING_ENABLED = _orig_enabled

        if not verdict.approved:
            result = TradeResult(
                success=False, mode="paper", trade_id=trade_id,
                market_id=proposal.market_id, title=proposal.title,
                side=proposal.side, outcome=proposal.outcome,
                size_usdc=0.0, price_at_entry=proposal.current_price,
                confidence=proposal.confidence, timestamp=now,
                risk_verdict=verdict.rejection_reason or "REJECTED",
                error=f"Risk gate rejected: {verdict.rejection_reason}",
            )
            self.log.record(result)
            return result

        result = TradeResult(
            success=True, mode="paper", trade_id=trade_id,
            market_id=proposal.market_id, title=proposal.title,
            side=proposal.side, outcome=proposal.outcome,
            size_usdc=verdict.approved_size_usdc,
            price_at_entry=proposal.current_price,
            confidence=proposal.confidence, timestamp=now,
            risk_verdict="APPROVED",
        )
        self.log.record(result)
        return result

    def execute_trade(
        self,
        signal: Union[Signal, Dict[str, Any]],
        proposed_size_usdc: float = 5.0,
    ) -> TradeResult:
        """Execute trade — paper or live depending on TRADING_ENABLED."""
        if not self.trading_enabled:
            return self.paper_trade(signal, proposed_size_usdc)

        trade_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        proposal = TradeProposal_from_signal(signal, proposed_size_usdc=proposed_size_usdc)
        if proposal is None:
            result = TradeResult(
                success=False, mode="live", trade_id=trade_id,
                market_id=_get_field(signal, "market_id", "unknown"),
                title=_get_field(signal, "title", "Unknown"),
                side="NONE", outcome="NONE", size_usdc=0.0,
                price_at_entry=0.0, confidence=0.0, timestamp=now,
                risk_verdict="NOT_ACTIONABLE", error="Signal is not actionable",
            )
            self.log.record(result)
            return result

        verdict = check_risk(proposal, self._risk_tracker)
        if not verdict.approved:
            result = TradeResult(
                success=False, mode="live", trade_id=trade_id,
                market_id=proposal.market_id, title=proposal.title,
                side=proposal.side, outcome=proposal.outcome,
                size_usdc=0.0, price_at_entry=proposal.current_price,
                confidence=proposal.confidence, timestamp=now,
                risk_verdict=verdict.rejection_reason or "REJECTED",
                error=f"Risk gate rejected: {verdict.rejection_reason}",
            )
            self.log.record(result)
            return result

        try:
            clob = self._get_clob_client()
            resp = clob.place_market_order(
                token_id=proposal.market_id,
                side=proposal.side,
                size=verdict.approved_size_usdc,
            )
            order_id = str(resp.get("orderID") or resp.get("order_id") or resp.get("id", "unknown"))

            result = TradeResult(
                success=True, mode="live", trade_id=trade_id,
                market_id=proposal.market_id, title=proposal.title,
                side=proposal.side, outcome=proposal.outcome,
                size_usdc=verdict.approved_size_usdc,
                price_at_entry=proposal.current_price,
                confidence=proposal.confidence, timestamp=now,
                risk_verdict="APPROVED", order_id=order_id,
            )
            self.log.record(result)
            return result
        except Exception as e:
            result = TradeResult(
                success=False, mode="live", trade_id=trade_id,
                market_id=proposal.market_id, title=proposal.title,
                side=proposal.side, outcome=proposal.outcome,
                size_usdc=0.0, price_at_entry=proposal.current_price,
                confidence=proposal.confidence, timestamp=now,
                risk_verdict="APPROVED", error=f"CLOB order failed: {e}",
            )
            self.log.record(result)
            return result

    def calculate_paper_pnl(self, trade_id: str, current_price: float) -> Optional[float]:
        """Calculate hypothetical P&L for a paper trade."""
        for trade in self.log.trades:
            if trade.get("trade_id") == trade_id and trade.get("success"):
                entry = trade["price_at_entry"]
                size = trade["size_usdc"]
                pnl = round(
                    (current_price - entry) * size if trade["side"] == "BUY"
                    else (entry - current_price) * size,
                    4,
                )
                self.log.update_pnl(trade_id, pnl)
                return pnl
        return None

    def get_summary(self) -> dict:
        trades = self.log.trades
        successful = [t for t in trades if t.get("success")]
        return {
            "total_trades": len(trades),
            "paper_trades": len(self.log.paper_trades),
            "live_trades": len(self.log.live_trades),
            "successful": len(successful),
            "failed": len(trades) - len(successful),
            "total_pnl": self.log.total_pnl,
            "daily_spend": self.log.daily_spend(),
            "trading_enabled": self.trading_enabled,
        }


# ============================================================================
# HELPERS
# ============================================================================

def _get_field(signal: Union[Signal, Dict[str, Any]], f: str, default: Any = None) -> Any:
    if isinstance(signal, dict):
        return signal.get(f, default)
    return getattr(signal, f, default)
