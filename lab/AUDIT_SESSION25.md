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
