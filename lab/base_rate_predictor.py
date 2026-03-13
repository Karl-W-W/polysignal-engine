#!/usr/bin/env python3
"""
lab/base_rate_predictor.py
==========================
Per-market base rate predictor — predicts the historically dominant direction.

Session 25 finding: majority-class strategy = 79.9% vs 17.4% production.
Each market has a strong directional bias. Predicting WITH the bias
beats any ML model we've trained.

Usage:
    from lab.base_rate_predictor import BaseRatePredictor
    
    predictor = BaseRatePredictor.from_outcomes("/opt/loop/data/prediction_outcomes.json")
    result = predictor.predict("556108")
    # {'direction': 'Bullish', 'confidence': 0.86, 'samples': 37, 'bias': 0.86}

Promotion target: wire into prediction_node as primary predictor,
with momentum/ML as secondary signal for counter-trend detection.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


OUTCOMES_FILE = Path(os.getenv(
    "OUTCOMES_FILE", "/opt/loop/data/prediction_outcomes.json"
))

# Minimum samples before we trust the base rate
MIN_SAMPLES = 10

# Minimum bias strength before we make a directional call
MIN_BIAS = 0.60

# Counter-signal threshold: only override base rate if delta exceeds this
# relative to the market's typical volatility
COUNTER_SIGNAL_MULTIPLIER = 2.0


@dataclass
class MarketBias:
    """Stored base rate for a single market."""
    market_id: str
    up_count: int
    down_count: int
    total: int
    up_rate: float
    dominant_direction: str  # "Bullish" or "Bearish"
    bias_strength: float  # max(up_rate, 1-up_rate)
    confident: bool  # True if total >= MIN_SAMPLES and bias >= MIN_BIAS


@dataclass
class PredictionResult:
    """Output of base rate prediction."""
    market_id: str
    direction: str  # "Bullish", "Bearish", or "Neutral"
    confidence: float
    reasoning: str
    samples: int
    bias: float
    source: str = "base_rate"


class BaseRatePredictor:
    """Predicts market direction from historical base rates."""

    def __init__(self, biases: Dict[str, MarketBias]):
        self.biases = biases

    @classmethod
    def from_outcomes(cls, outcomes_path: Path = OUTCOMES_FILE) -> "BaseRatePredictor":
        """Build base rates from prediction outcome history."""
        data = json.loads(Path(outcomes_path).read_text())
        preds = data.get("predictions", [])

        # Count directional outcomes per market
        market_stats: Dict[str, Dict[str, int]] = {}

        for p in preds:
            if not p.get("evaluated"):
                continue
            if "fake" in str(p.get("market_id", "")):
                continue
            outcome = p.get("outcome")
            if outcome not in ("CORRECT", "INCORRECT"):
                continue

            mid = p["market_id"]
            hyp = p.get("hypothesis", "Unknown")

            if mid not in market_stats:
                market_stats[mid] = {"up": 0, "down": 0}

            # Derive actual direction
            if hyp == "Bullish":
                went_up = outcome == "CORRECT"
            else:
                went_up = outcome == "INCORRECT"

            if went_up:
                market_stats[mid]["up"] += 1
            else:
                market_stats[mid]["down"] += 1

        # Build bias objects
        biases = {}
        for mid, stats in market_stats.items():
            total = stats["up"] + stats["down"]
            up_rate = stats["up"] / total if total > 0 else 0.5
            bias_strength = max(up_rate, 1 - up_rate)
            dominant = "Bullish" if up_rate >= 0.5 else "Bearish"
            confident = total >= MIN_SAMPLES and bias_strength >= MIN_BIAS

            biases[mid] = MarketBias(
                market_id=mid,
                up_count=stats["up"],
                down_count=stats["down"],
                total=total,
                up_rate=round(up_rate, 3),
                dominant_direction=dominant,
                bias_strength=round(bias_strength, 3),
                confident=confident,
            )

        return cls(biases)

    def predict(self, market_id: str, signal_delta: float = 0.0) -> PredictionResult:
        """Predict direction for a market.
        
        Args:
            market_id: Market to predict
            signal_delta: Current perception signal delta (for counter-trend override)
        
        Returns:
            PredictionResult with direction, confidence, reasoning
        """
        if market_id not in self.biases:
            return PredictionResult(
                market_id=market_id,
                direction="Neutral",
                confidence=0.1,
                reasoning="No historical data for this market (cold start)",
                samples=0,
                bias=0.5,
            )

        bias = self.biases[market_id]

        if not bias.confident:
            return PredictionResult(
                market_id=market_id,
                direction="Neutral",
                confidence=0.3,
                reasoning=f"Insufficient data ({bias.total} samples) or weak bias ({bias.bias_strength:.0%})",
                samples=bias.total,
                bias=bias.bias_strength,
            )

        # Default: predict dominant direction
        direction = bias.dominant_direction
        confidence = bias.bias_strength
        reasoning = f"Base rate: {bias.dominant_direction} wins {bias.bias_strength:.0%} of the time ({bias.total} samples)"

        # Counter-signal check: only override if signal is strong AND against bias
        if signal_delta != 0.0:
            # Is the signal going against the base rate?
            signal_bullish = signal_delta > 0
            bias_bullish = bias.dominant_direction == "Bullish"

            if signal_bullish != bias_bullish:
                # Signal conflicts with base rate — only override if very strong
                if abs(signal_delta) > 0.03:  # 3% move is significant
                    direction = "Bullish" if signal_bullish else "Bearish"
                    confidence = min(0.65, abs(signal_delta) * 5)
                    reasoning = f"Counter-trend signal ({signal_delta:+.3f}) overrides base rate ({bias.dominant_direction} {bias.bias_strength:.0%})"
                else:
                    reasoning += f" (weak counter-signal {signal_delta:+.3f} ignored)"

        return PredictionResult(
            market_id=market_id,
            direction=direction,
            confidence=round(confidence, 3),
            reasoning=reasoning,
            samples=bias.total,
            bias=bias.bias_strength,
        )

    def summary(self) -> str:
        """Print summary of all market biases."""
        lines = ["Market Base Rates:", "=" * 50]
        for mid, b in sorted(self.biases.items(), key=lambda x: -x[1].total):
            flag = "✅" if b.confident else "⚠️"
            lines.append(
                f"  {flag} {mid}: {b.dominant_direction} {b.bias_strength:.0%} "
                f"({b.up_count}↑/{b.down_count}↓, n={b.total})"
            )
        return "\n".join(lines)


if __name__ == "__main__":
    predictor = BaseRatePredictor.from_outcomes()
    print(predictor.summary())
    print()

    # Simulate predictions for all known markets
    correct = 0
    total = 0
    for mid, bias in predictor.biases.items():
        result = predictor.predict(mid)
        if result.direction != "Neutral":
            expected_acc = bias.bias_strength
            n = bias.total
            correct += int(expected_acc * n)
            total += n
            print(f"  {mid}: predict {result.direction} ({result.confidence:.0%}) → expected {expected_acc:.0%} on {n} samples")

    if total:
        print(f"\nExpected overall: {correct}/{total} = {correct/total:.1%}")
