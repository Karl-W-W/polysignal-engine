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
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional


OUTCOMES_FILE = Path(os.getenv(
    "OUTCOMES_FILE", "/opt/loop/data/prediction_outcomes.json"
))

OBS_DB_PATH = os.getenv("DB_PATH", "/opt/loop/data/test.db")

# Minimum samples before we trust the base rate
MIN_SAMPLES = 10

# Minimum bias strength before we make a directional call
MIN_BIAS = 0.60

# Observation-based biases need more samples (noisier signal)
# Session 31: lowered from 50/0.55 to 30/0.52 for more coverage
OBS_MIN_SAMPLES = 30
OBS_MIN_BIAS = 0.52

# Price-level bias thresholds (Session 31)
# Markets at extreme prices have strong directional bias from resolution mechanics.
# A market at 0.10 has ~90% chance of resolving NO → Bearish.
PRICE_LEVEL_LOW = 0.30   # Below this → Bearish bias
PRICE_LEVEL_HIGH = 0.70  # Above this → Bullish bias
PRICE_LEVEL_MIN_CONFIDENCE = 0.55  # Minimum confidence for price-level predictions

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
        outcomes_path = Path(outcomes_path)
        if not outcomes_path.exists():
            return cls({})
        data = json.loads(outcomes_path.read_text())
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

    @classmethod
    def from_observations(cls, db_path: str = OBS_DB_PATH) -> "BaseRatePredictor":
        """Build base rates from observation price movements in the scanner DB.

        Session 30: After market expansion (13 → 142), most markets have no
        prediction outcomes yet. This method bootstraps biases from consecutive
        price changes in the observation table (up vs down movements).
        """
        if not os.path.exists(db_path):
            return cls({})

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(
                "SELECT market_id, price FROM observations ORDER BY market_id, timestamp"
            )
            market_stats: Dict[str, Dict[str, int]] = {}
            prev_price: Dict[str, float] = {}

            for mid, price in cursor:
                if mid in prev_price:
                    delta = price - prev_price[mid]
                    if mid not in market_stats:
                        market_stats[mid] = {"up": 0, "down": 0}
                    if delta > 0.0001:
                        market_stats[mid]["up"] += 1
                    elif delta < -0.0001:
                        market_stats[mid]["down"] += 1
                prev_price[mid] = price
        finally:
            conn.close()

        biases = {}
        for mid, stats in market_stats.items():
            total = stats["up"] + stats["down"]
            if total < OBS_MIN_SAMPLES:
                continue
            up_rate = stats["up"] / total
            bias_strength = max(up_rate, 1 - up_rate)
            dominant = "Bullish" if up_rate >= 0.5 else "Bearish"
            confident = bias_strength >= OBS_MIN_BIAS

            if confident:
                biases[mid] = MarketBias(
                    market_id=mid,
                    up_count=stats["up"],
                    down_count=stats["down"],
                    total=total,
                    up_rate=round(up_rate, 3),
                    dominant_direction=dominant,
                    bias_strength=round(bias_strength, 3),
                    confident=True,
                )

        return cls(biases)

    @classmethod
    def from_price_levels(cls, observations: list) -> "BaseRatePredictor":
        """Build biases from current market prices (Session 31).

        Prediction markets converge to 0 or 1. A market at price 0.10 has ~90%
        probability of resolving NO → Bearish. This provides directional bias
        for markets without outcome or observation history.

        Only generates biases for markets in the tradeable range (0.05-0.95).
        Markets outside this range are essentially decided.
        """
        biases = {}
        for obs in observations:
            mid = obs.get("market_id")
            price = obs.get("current_price", obs.get("price", 0.5))
            if not mid or price is None:
                continue

            # Skip essentially-decided markets (no trading opportunity)
            if price < 0.05 or price > 0.95:
                continue

            if price < PRICE_LEVEL_LOW:
                # Price below 0.30 → Bearish (market likely resolves NO)
                direction = "Bearish"
                confidence = 1.0 - price  # e.g., price=0.10 → conf=0.90
            elif price > PRICE_LEVEL_HIGH:
                # Price above 0.70 → Bullish (market likely resolves YES)
                direction = "Bullish"
                confidence = price  # e.g., price=0.85 → conf=0.85
            else:
                continue  # 0.30-0.70: genuinely uncertain, no price-level bias

            # Cap confidence — price level alone isn't as reliable as outcomes
            confidence = min(confidence, 0.90)
            if confidence < PRICE_LEVEL_MIN_CONFIDENCE:
                continue

            # Represent as a synthetic MarketBias
            is_bullish = direction == "Bullish"
            biases[mid] = MarketBias(
                market_id=mid,
                up_count=1 if is_bullish else 0,
                down_count=0 if is_bullish else 1,
                total=1,  # synthetic — single observation
                up_rate=1.0 if is_bullish else 0.0,
                dominant_direction=direction,
                bias_strength=round(confidence, 3),
                confident=True,
            )

        return cls(biases)

    @classmethod
    def from_all_sources(cls, outcomes_path: Path = OUTCOMES_FILE,
                         db_path: str = OBS_DB_PATH,
                         observations: list = None) -> "BaseRatePredictor":
        """Merge outcome-based, observation-based, and price-level biases.

        Priority: outcome > observation > price_level.
        Outcome biases (from evaluated predictions) take highest priority.
        Observation biases fill in for markets without prediction history.
        Price-level biases (Session 31) provide coverage for new markets
        based on current price position in the 0-1 range.
        """
        outcome_predictor = cls.from_outcomes(outcomes_path)
        obs_predictor = cls.from_observations(db_path)

        # Start with price-level biases (lowest priority)
        if observations:
            price_predictor = cls.from_price_levels(observations)
            merged = dict(price_predictor.biases)
        else:
            merged = {}

        # Observation biases override price-level
        merged.update(obs_predictor.biases)
        # Outcome biases override everything
        merged.update(outcome_predictor.biases)

        return cls(merged)

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

        # Counter-signal check: only override if signal is VERY strong AND against bias.
        # Session 27: Tightened from 3% to 10% threshold. The old 3% threshold
        # allowed routine intraday moves to flip a 94% confidence Bearish prediction
        # to Bullish, contributing to the accuracy crisis. A 10pp move in a prediction
        # market is genuinely significant; anything less should not override base rate.
        if signal_delta != 0.0:
            signal_bullish = signal_delta > 0
            bias_bullish = bias.dominant_direction == "Bullish"

            if signal_bullish != bias_bullish:
                if abs(signal_delta) > 0.10:  # 10pp move — genuinely significant
                    direction = "Bullish" if signal_bullish else "Bearish"
                    confidence = min(0.65, abs(signal_delta) * 3)
                    reasoning = f"Counter-trend signal ({signal_delta:+.3f}) overrides base rate ({bias.dominant_direction} {bias.bias_strength:.0%})"
                else:
                    reasoning += f" (counter-signal {signal_delta:+.3f} below 10pp threshold, ignored)"

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
