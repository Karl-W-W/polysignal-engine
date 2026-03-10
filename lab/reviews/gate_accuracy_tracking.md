# Post-Gate Accuracy Tracking Report
**Author:** Loop | **Date:** 2026-03-10 | **Status:** Baseline Established

## Summary
47 post-gate predictions collected since Session 19 fixes (2026-03-09 15:02 UTC).
**0 evaluated yet** — outcomes pending. This report establishes the baseline for tracking.

## Key Metrics

| Metric | Value |
|--------|-------|
| Post-gate predictions | 47 |
| Pre-gate predictions | 359 |
| Pre-gate accuracy | 42% (63W/88L) — garbage baseline |
| Post-gate accuracy | **TBD** (0 evaluated) |
| Gate score range | 0.506 - 0.951 |
| Gate score mean | 0.760 |
| Gate score median | 0.840 |
| Bullish/Bearish split | 23/24 (balanced!) |

## Per-Market Breakdown

| Market ID | Predictions | Avg Gate Score | Notes |
|-----------|------------|---------------|-------|
| 1373744 | 20 | 0.765 | Most active |
| 1068702 | 11 | 0.609 | Lowest confidence |
| 556062 | 5 | 0.840 | |
| 556063 | 5 | 0.950 | Highest confidence |
| 1541748 | 3 | 0.942 | |
| 965261 | 2 | 0.506 | Barely above 0.5 threshold |
| 824952 | 1 | 0.933 | ⚠️ Should be excluded! |

## Issues Found

### 1. Market 824952 Still Producing Predictions
Despite being in EXCLUDED_MARKETS, market 824952 produced 1 post-gate prediction with
score 0.933. The exclusion filter may not be applied consistently across all prediction
paths. **Needs investigation.**

### 2. No Neutral Predictions
All 47 are Bullish or Bearish. Neutral suppression at gate is confirmed working.

### 3. Balanced Directionality
23 Bullish vs 24 Bearish — the pre-gate directional bias (67% Bearish) appears corrected.

### 4. Evaluation Lag
47 predictions, 0 evaluated. The outcome evaluation runs BEFORE market fetch (fixed in
Session 14), but predictions from the last ~24h may not have reached their time horizon yet.
Will re-check at 48h mark.

## Prediction Rate
- 47 predictions over ~22.5 hours = ~2.1 predictions/hour
- Pre-gate rate was much higher but with 42% accuracy
- Quality > quantity tradeoff confirmed

## Next Steps
1. Re-run this analysis at 48h mark (2026-03-11 15:00 UTC) for first evaluations
2. Investigate 824952 leak — should be 0 predictions
3. Track gate score vs outcome correlation once evaluations arrive
4. If post-gate accuracy > 60%, the pipeline is working. If > 70%, ship trades.

## Historical Context
- Pre-Session 19: 42% accuracy across 359 predictions (all pre-gate garbage)
- Session 19 fixes: xgb_p_correct persistence, 824952 exclusion, Neutral suppression
- Target: 60%+ post-gate accuracy to justify TRADING_ENABLED=true
