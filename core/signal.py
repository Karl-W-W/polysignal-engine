"""
core/signal.py
==============
THE CANONICAL SIGNAL SCHEMA — PolySignal-OS Vault.

Promoted from: lab/signal_schema.py (2026-02-23)
Promotion criteria all met:
  ✅ Human approved
  ✅ Unit tests passed with zero warnings
  ✅ Pydantic V2 compliant

RenTec Principle: Absolute Empiricism.
A Signal is NOT a gut-feeling. It is a decoded mathematical observation.
Every field must be backed by observable data.
"""

import uuid as _uuid
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from datetime import datetime, timezone


class SignalSource(BaseModel):
    """Provenance: exactly what math triggered this signal."""
    method: str = Field(..., description="e.g. 'price_momentum', 'volume_spike', 'hmm_regime_shift'")
    raw_value: float = Field(..., description="The raw numeric observation (e.g. 0.08 price delta)")
    baseline: Optional[float] = Field(None, description="Historical baseline for comparison")
    threshold: Optional[float] = Field(None, description="Threshold breached to trigger signal")


class Signal(BaseModel):
    """
    The canonical PolySignal signal object.
    Every signal emitted by the MasterLoop MUST conform to this schema.
    No raw dicts. No informal observations. Typed signals only.
    """

    # Identity
    signal_id: str = Field(
        default_factory=lambda: str(_uuid.uuid4()),
        description="Unique UUID for this signal"
    )
    market_id: str = Field(..., description="Polymarket internal market ID")
    cycle_number: int = Field(default=0, description="MasterLoop cycle that generated this")
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Market Reference — required for actionability
    title: str = Field(..., description="Human-readable market question")
    outcome: str = Field(..., description="Specific outcome being traded (e.g. 'Yes', 'Trump', 'No')")
    polymarket_url: str = Field(
        ...,
        description="Direct link to execute. Format: https://polymarket.com/event/{slug}"
    )

    # Mathematical Signal Data — no vibes
    current_price: float = Field(..., ge=0.0, le=1.0, description="Current implied probability (0–1)")
    volume_24h: float = Field(..., ge=0, description="24h trading volume in USD")
    change_since_last: float = Field(default=0.0, description="Price delta since last observation")

    # Hypothesis
    hypothesis: Literal["Bullish", "Bearish", "Neutral"] = Field(
        default="Neutral",
        description="Bullish = probability rising, Bearish = falling"
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Model confidence (0–1)")

    # Provenance — mandatory for RenTec empiricism
    source: SignalSource = Field(..., description="What math generated this signal")
    reasoning: str = Field(..., description="1–2 sentence explanation citing the data")

    # Risk Management
    time_horizon: Literal["1h", "4h", "24h", "7d"] = Field(
        default="24h", description="Expected signal validity window"
    )

    @field_validator("polymarket_url")
    @classmethod
    def url_must_be_polymarket(cls, v: str) -> str:
        if "polymarket.com" not in v:
            raise ValueError("polymarket_url must point to polymarket.com")
        return v

    def to_telegram_message(self) -> str:
        """Format for Telegram human-in-the-loop alert."""
        stars = "⭐" * max(1, int(self.confidence * 5))
        arrow = "📈" if self.hypothesis == "Bullish" else ("📉" if self.hypothesis == "Bearish" else "➡️")
        return (
            f"{arrow} *SIGNAL DETECTED*\n"
            f"*Market:* {self.title}\n"
            f"*Outcome:* {self.outcome}\n"
            f"*Price:* {self.current_price:.2%} implied probability\n"
            f"*Change:* {self.change_since_last:+.2%} since last scan\n"
            f"*Signal:* {self.hypothesis} ({self.confidence:.0%} confidence) {stars}\n"
            f"*Why:* {self.reasoning}\n"
            f"*Horizon:* {self.time_horizon}\n"
            f"*Trade:* {self.polymarket_url}"
        )

    def to_dict(self) -> dict:
        """Serialise for JSON/state storage."""
        return self.model_dump()


# ============================================================================
# STANDALONE TEST
# ============================================================================

if __name__ == "__main__":
    sig = Signal(
        market_id="0xabc123",
        title="Will Bitcoin exceed $100k by end of Q1 2026?",
        outcome="Yes",
        polymarket_url="https://polymarket.com/event/will-bitcoin-exceed-100k-q1-2026",
        current_price=0.71,
        volume_24h=1_250_000.0,
        change_since_last=0.08,
        hypothesis="Bullish",
        confidence=0.72,
        source=SignalSource(
            method="price_momentum",
            raw_value=0.08,
            baseline=0.63,
            threshold=0.05
        ),
        reasoning="Price moved +8pp against a baseline of +1.5pp avg. Volume confirms accumulation.",
    )
    print("✅ core/signal.py validation passed")
    print(sig.model_dump_json(indent=2))
    print("\n--- TELEGRAM PREVIEW ---")
    print(sig.to_telegram_message())
