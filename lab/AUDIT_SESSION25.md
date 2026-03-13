# Pipeline Audit — Session 25 (Loop, 2026-03-13)

## Root Cause Analysis: 17.4% Production Accuracy

### Finding 1: predict_market_moves() is a toy
The core prediction logic in `core/predict.py` is a 5-line momentum check:
- Query last 5 observations from DB
- Average the `change_24h_at_time` values
- If avg > 0.01 → Bullish, if avg < -0.01 → Bearish
- Confidence = 0.6 + len(history) * 0.05

This is a lagging momentum indicator on 5 data points. It will always chase yesterday's move and get whipsawed. There is no feature engineering, no multi-market correlation, no volume analysis, no time-of-day patterns.

**The XGBoost gate is checking whether THIS prediction will be correct, but the prediction itself has almost no signal.** The gate can only filter garbage — it cannot create signal from a garbage predictor.

### Finding 2: Signal enhancement creates false direction
In prediction_node, when rule-based says "Neutral" but perception has a signal, the code overrides:
```python
pred["hypothesis"] = "Bullish" if "bull" in direction else "Bearish"
pred["confidence"] = round(min(0.55 + delta * 2, 0.85), 2)
```
This takes a tiny delta (as low as 0.015) and converts it to a 0.55-0.85 confidence directional call. It's amplifying noise into signal.

### Finding 3: Outcome evaluation is sound
The outcome tracker correctly:
- Waits for the time horizon to elapse
- Compares price_then vs price_now
- Uses MIN_MOVE_THRESHOLD (0.01) to filter neutral
- Labels CORRECT/INCORRECT based on direction match

No bugs here. The problem is upstream — the predictions are bad, not the evaluation.

### Finding 4: Feature engineering exists but is disconnected
`lab/feature_engineering.py` (20KB) has sophisticated feature extraction. But it's only used by XGBoost for the GATE, not by the PREDICTOR. The actual prediction comes from the toy momentum check in core/predict.py.

### Finding 5: The architecture is backwards
Current flow:
1. Toy predictor makes directional call (almost random)
2. XGBoost gates whether that call will be correct (trained on outcomes of the toy)
3. If gate passes, prediction is recorded

The XGBoost model learned to predict when the toy predictor accidentally aligns with market direction. It cannot exceed the base rate of the toy.

### Recommended Fix (Priority Order)

1. **Replace predict_market_moves with feature-engineered predictor**
   - Use the existing `lab/feature_engineering.py` features directly for prediction
   - The features already include: momentum, volatility, volume ratios, time features
   - Train a proper XGBoost PREDICTOR (not gate) on these features
   - Target: predict direction, not predict-if-prediction-correct

2. **Kill the signal enhancement hack**
   - Perception delta of 0.015 should not become a "Bullish" call at 0.58 confidence
   - Either use it as a feature for ML, or require much higher threshold

3. **Add per-market validation**
   - Track accuracy per market_id in real time
   - Auto-exclude markets that fall below 40% after 20+ predictions
   - This should be structural (code) not manual (list in config)

4. **Retrain with proper methodology**
   - 414 labeled samples is enough for a real model
   - Split by time, not random (prevent leakage)
   - Features: all from feature_engineering.py + market_id embedding
   - Target: predict DIRECTION, not predict-if-direction-correct

## Addendum: Leave-One-Market-Out Validation (LOMO)

### Result: 44.7% — WORSE than 47.5% baseline

The direction predictor CANNOT generalize across markets:

| Market  | Accuracy | Baseline | Beat? |
|---------|----------|----------|-------|
| 824952  | 56%      | 71%      | ❌    |
| 556108  | 16%      | 86%      | ❌    |
| 1541748 | 11%      | 95%      | ❌    |
| 1373744 | 83%      | 100%     | ❌    |

No market beats its own baseline when trained without its own data.

### Implication
The 73% time-series CV was leaking same-market patterns across folds.
The 96.7% shuffled CV was pure memorization.
The model learns market-specific patterns that don't transfer.

### What This Means
1. **A universal direction predictor won't work** with 7 heterogeneous markets
2. **Per-market models** might work but need enough samples per market
3. **The feature set is not predictive of cross-market direction** — clob_depth_imbalance is market-specific, not universal
4. **We need more markets OR market-specific models** to make progress
5. The current toy predictor's 17.4% is not because it's simple — it's because direction prediction across heterogeneous prediction markets is fundamentally hard

### Revised Recommendation
Instead of replacing predict_market_moves with ML, focus on:
1. Per-market models where we have 50+ samples (only 824952 qualifies)
2. Better market selection (556108 has 86% bullish base rate — just always predict UP)
3. Market-specific thresholds instead of universal gates
4. More markets to find ones where features actually predict

## Addendum 2: Per-Market Base Rate Analysis

### The simplest possible strategy beats everything we've built

| Market  | N   | Up%  | Down% | Best Strategy | Expected Acc |
|---------|-----|------|-------|---------------|-------------|
| 824952  | 103 | 29%  | 71%   | Always DOWN   | 71%         |
| 556108  | 37  | 86%  | 14%   | Always UP     | 86%         |
| 1541748 | 19  | 95%  | 5%    | Always UP     | 95%         |
| 1373744 | 6   | 0%   | 100%  | Always DOWN   | 100%        |
| 965261  | 5   | 0%   | 100%  | Always DOWN   | 100%        |
| 692258  | 5   | 100% | 0%    | Always DOWN   | 100%        |
| 556062  | 4   | 0%   | 100%  | Always DOWN   | 100%        |

**Majority-class strategy: 143/179 = 79.9%**
**Current production: 72/414 = 17.4%**

### Why the toy predictor is SO bad

The momentum predictor often predicts AGAINST the base rate:
- 824952 goes DOWN 71% of the time, but the predictor calls Bullish when it sees upward momentum (which is noise against the trend)
- 556108 goes UP 86%, but bearish calls on small dips lose every time

**We were literally predicting the wrong direction on the dominant trend.**

### The bearish ban was accidentally brilliant
Banning bearish predictions helped because most of our UP-biased markets (556108, 1541748, 692258) were getting wrong bearish calls. The ban aligned us with the base rate by accident.

### Immediate Recommendation
1. **Per-market bias table**: Store each market's historical up/down ratio
2. **Predict WITH the bias**: If a market goes up 86% of the time, default to Bullish unless very strong counter-signal
3. **Only counter-predict when signal > 2x base rate change**: Don't call bearish on 556108 unless delta exceeds -0.03
4. **This is the real alpha**: Understanding per-market base rates, not ML on sparse cross-market features
