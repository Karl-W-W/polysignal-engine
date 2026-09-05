# Edge diagnosis — why PolySignal's edge over the market price is negative (2026-09-05)

Question: the sub-0.5 lever fixes measured accuracy (54% → 70% on 30d), but edge vs price stays
negative (−3.6 pp on 30d after the lever) and the 4 h-drift friction win rate sits at ~33%. Is
the cause (a) the ~12 politics markets at ~0.8 re-predicted every ~32 minutes (effective N),
(b) stale prices, or (c) the base-rate model itself?

**Answer: (c), specifically the observation-tick base-rate source, with (a) hiding how bad it
is. Prices are not stale.**

## Data

Read-only copies pulled 2026-09-05 17:31 CEST via scp from the DGX:

| File | Size | Used for |
|---|---|---|
| `/opt/loop/data/prediction_outcomes.json` | 3,032,211 B; 5,000-record window since 2026-05-04; 4,256 resolved rows on 364 markets | accuracy, edge, repetition, source split |
| `/opt/loop/data/clob_features_cache.json` | 9,310,885 B; 21,914 markets, cache timestamp 2026-09-05T14:10Z | staleness test (bid/ask/mid/last trade) |
| `/opt/loop/lab/trading_log.json` | 8,049,565 B | market titles only |

Edge is defined throughout as accuracy − mean `price_at_prediction`. Every stored prediction is
Bullish, so for each row the price is the market's own probability of CORRECT; a zero edge means
"the scanner is the market". Script: `diag.py` in the session scratchpad (replayable from the
files above; no DGX writes).

## Hypothesis (a): effective N — the 12 politics markets re-predicted every 32 min

| View | Rows | Unique markets | Accuracy | Mean price | Edge |
|---|---|---|---|---|---|
| All resolved rows | 4,256 | 364 | 59.2% | 61.8% | **−2.6 pp** |
| First prediction per market | 364 | 364 | 56.3% | 61.4% | **−5.1 pp** |
| Last prediction per market | 364 | 364 | 56.3% | 63.0% | −6.7 pp |
| Rows weighted 1/n per market | — | 364 | 56.3% | 62.3% | −6.0 pp |
| Market-level mean of (outcome − mean price) | — | 364 | — | — | **−6.0 pp, 95% CI ± 4.4** |

Edge by how often a market was re-predicted:

| Predictions per market | Rows | Markets | Accuracy | Price | Edge |
|---|---|---|---|---|---|
| 1 | 68 | 68 | 54.4% | 61.5% | −7.1 pp |
| 2–5 | 409 | 129 | 59.2% | 65.5% | −6.3 pp |
| 6–15 | 725 | 78 | 51.7% | 55.0% | −3.2 pp |
| 16–40 | 1,508 | 61 | 57.0% | 59.5% | −2.5 pp |
| 41+ | 1,546 | 28 | 65.1% | 66.4% | −1.3 pp |

The 12 most-repeated markets (59–75 rows each) are eleven 100%-correct politics/CPI markets at
0.74–0.79 and a few 0%-correct ones; together they contribute ~780 rows from 12 markets.
Repetition therefore **inflates N ten-fold and makes the row-level edge look better** (−2.6 pp)
than the market-level truth (−6.0 pp, CI excluding zero). It does not create the negative edge:
the once-predicted markets are the worst bucket (−7.1 pp). Verdict: real problem for evidence
(effective N is 364, not 4,256), not the cause of the sign.

## Hypothesis (b): stale prices

| Test | Result |
|---|---|
| Consecutive same-market predictions with an identical price | 2,025 / 3,892 = 52% (markets simply do not move in 32 min) |
| Markets with ≥ 5 predictions over > 24 h and a single price value | 0 |
| Predictions within 3 h of the CLOB cache that have a live book | 45 |
| median / mean / max of |`price_at_prediction` − CLOB mid| | **0.0000 / 0.0053 / 0.0900** |
| Spread on those 45 markets (mean / median) | 6.9 pp / 5.0 pp |
| Spread on the 208 resolved markets still in the cache (mean / median) | 0.5 pp / 0.1 pp (resolved → book collapsed) |

The scanner's price is the live mid to within a tick. Verdict: **not stale**. (Note the 5–7 pp
spreads on the currently predicted set: a 0.5 pp friction assumption is optimistic; rung 1 logs
the real one.)

## Hypothesis (c): the base-rate model

`BaseRatePredictor.from_all_sources` merges three sources: outcome history, **observation
up-tick/down-tick counts** from `test.db` (`from_observations`: a market is "Bullish" if it had
more up-ticks than down-ticks, ≥ 30 ticks, bias ≥ 0.52), and price level (Bullish if price >
0.70, confidence = price). The record does not store the source, but price-level calls have
`confidence == price_at_prediction` exactly, so the split is clean:

| Source (by confidence == price) | Rows | Markets | Accuracy | Price | Edge |
|---|---|---|---|---|---|
| Price-level (conf == price) | 1,805 | 232 | 77.7% | 77.1% | **+0.6 pp** |
| Outcome / observation-tick bias (conf ≠ price) | 2,451 | 179 | 45.5% | 50.6% | **−5.0 pp** |
| … of which price ≥ 0.5 | 1,240 | 88 | 68.8% | 70.3% | −1.5 pp |
| … of which price < 0.5 | 1,211 | 109 | 21.7% | 30.4% | −8.7 pp |

By category and horizon (same rows):

| Slice | Rows | Markets | Accuracy | Price | Edge |
|---|---|---|---|---|---|
| politics | 2,252 | 94 | 62.3% | 63.9% | −1.6 pp |
| politics, price ≥ 0.5 | 1,686 | 67 | 78.1% | 76.3% | +1.8 pp |
| default (uncategorised) | 1,873 | 260 | 55.2% | 59.7% | −4.5 pp |
| default, price ≥ 0.5 | 1,273 | 198 | 67.4% | 72.1% | **−4.7 pp** |
| horizon 1h (momentum, signal-enhanced) | 352 | 113 | 47.7% | 58.9% | **−11.2 pp** |
| horizon 4h | 3,591 | 317 | 60.2% | 62.4% | −2.2 pp |
| horizon 24h | 313 | 90 | 60.4% | 59.1% | +1.3 pp |

Calibration on the post-lever population (price ≥ 0.5):

| Price bucket | Rows | Markets | Accuracy | Edge |
|---|---|---|---|---|
| 0.5–0.6 | 291 | 35 | 44.0% | −11.0 pp |
| 0.6–0.7 | 250 | 38 | 62.8% | −2.1 pp |
| 0.7–0.8 | 1,637 | 195 | 77.7% | +2.9 pp |
| 0.8–0.9 | 867 | 113 | 80.6% | −2.0 pp |

Market-level, price ≥ 0.5 only: 273 markets, edge −4.1 pp ± 5.3 (CI includes zero). Row-level
on the same rows: −0.2 pp.

Reading: the price-level source is the market and scores exactly like it (+0.6 pp). Everything
negative comes from the observation-tick source: it emits Bullish on markets the price says are
NO (the < 0.5 half, −8.7 pp, which rung 0 now blocks) and still loses on the ≥ 0.5 half
(−1.5 pp), worst in the uncategorised "default" markets (−4.7 pp) and in the 0.5–0.6 bucket
(−11 pp) where it disagrees with the price the most. The count of up-ticks versus down-ticks in
5-minute observations has no relationship to how a market resolves; it is a momentum proxy
applied to markets that mean-revert. The momentum/1h path is worse still (−11 pp) but small.

## Verdict

1. **Single most likely cause: the observation-tick base-rate source** (`from_observations` in
   `lab/base_rate_predictor.py`). It produces 58% of resolved rows and all of the negative edge;
   the price-level source is edge-neutral by construction. Rung 3 in `lab/AUTONOMY.md` disables
   it; the replay above predicts row-level edge moving from −2.6 pp to about 0.
2. **Effective N is the evidence problem, not the sign problem.** 364 unique markets, and
   re-prediction makes the row-level number 3.4 pp too kind. Any gate claim has to be made at
   market level (rung 2), and at 100 markets the CI is ± 8 pp, so breadth (rung 4) is on the
   critical path.
3. **Prices are not stale.** Median gap to the CLOB mid is zero. What is wrong about prices is
   the friction assumption: live spreads on the predicted set are 5–7 pp, not 0.5 pp; rung 1 now
   records the real ask and spread on every call.
4. After rungs 0 and 3 the predictor is the market price. That is the floor, not the goal: an
   edge-seeking model (rung 5) is what has to be built and proved at ≥ 100 unique resolved markets.
