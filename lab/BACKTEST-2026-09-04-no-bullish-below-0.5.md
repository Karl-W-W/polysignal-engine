# Backtest 2026-09-04 — no Bullish calls on markets priced below 0.50

Branch `lever/no-bullish-below-0.5`. Replay of the live DGX stores, read-only, run on the Mac.
Nothing on the DGX was modified. The lever is the one named in
`~/brain/dashboards/polysignal-accuracy-2026-09-04.md` as the only change that moves
the gate numbers materially.

## What changed in code

- `lab/base_rate_predictor.py`: one guarded condition at the end of `predict()`. If
  `SUPPRESS_BULLISH_BELOW_PRICE` (env, default ON) and the direction is Bullish and the
  market's latest price is below `BULLISH_MIN_PRICE` (env, default 0.50), the call is
  returned as Neutral with confidence 0.0 and a reasoning string that names the
  suppression. The price comes from the explicit `current_price` argument or, when the
  predictor was built via `from_all_sources(observations=...)` as the masterloop does,
  from the price captured off those observations. No masterloop change needed.
- Counter: `predictor.suppressed_bullish_below_price` in-process, plus a cumulative
  total persisted atomically to `lab/.base-rate-suppressions.json` (gitignored;
  `BASE_RATE_SUPPRESSION_FILE` overrides the path).
- `lab/truth_board.py`: status file and journal line gain
  `bullish_below_price_suppressed=<cumulative total>` so the truth board shows how many
  calls the guard has swallowed.
- `lab/backtest_no_bullish_below.py`: the replay used below (`python3 -m
  lab.backtest_no_bullish_below --outcomes ... --trades ...`).
- Tests: `tests/test_bullish_below_price_guard.py` (guard, flag off, threshold override,
  counter persistence, truth-board field, replay helpers) and an autouse fixture in
  `tests/conftest.py` that keeps the counter file out of `lab/` during tests.

## Data

| Store | Copied from | mtime on DGX |
|---|---|---|
| Predictions | `dgx-remote:/opt/loop/data/prediction_outcomes.json` (3,023,415 bytes) | 2026-09-04 22:19:53 CEST |
| Paper trades | `dgx-remote:/opt/loop/lab/trading_log.json` (7,970,008 bytes) | 2026-09-04 22:04:53 CEST |

Window cut: `now = 2026-09-04T20:30:00Z`, by record timestamp. Directional N counts records
with outcome CORRECT or INCORRECT (resolution-scored by `lab/outcome_tracker.py`);
ambiguous and pending records are excluded from both arms. The `predictions` list is
capped at 5,000 records by `OutcomeState.save`, so "lifetime" here starts 2026-05-04; the
store's lifetime counters (24,384 predictions, 13,552 / 10,041, 57.4%) cannot be replayed
per record because they no longer carry the price. Win rate uses the pnl already written by
`TradingLog.evaluate_paper_trades` (4 h-plus drift minus 0.5 pp slippage), so it is
computable only for evaluated trades. "Dropped" = resolved directional predictions or
evaluated trades removed by the lever in that window.

Arm A = baseline (everything the scanner emitted). Arm B = lever (drop Bullish predictions
with `price_at_prediction` < 0.50 and BUY paper trades with `price_at_entry` < 0.50).

## Directional accuracy and edge vs price

| Window | Arm | Directional N | Correct | Accuracy | Mean price | Edge vs price | Unique markets | Dropped |
|---|---|---|---|---|---|---|---|---|
| lifetime | A | 4209 | 2472 | 58.7% | 61.7% | -2.9 pp | 355 | — |
| lifetime | B | 2973 | 2208 | 74.3% | 74.6% | -0.4 pp | 264 | 1236 |
| 30d | A | 3204 | 1738 | 54.2% | 59.9% | -5.7 pp | 287 | — |
| 30d | B | 2187 | 1536 | 70.2% | 73.8% | -3.6 pp | 211 | 1017 |
| 7d | A | 315 | 181 | 57.5% | 64.2% | -6.7 pp | 43 | — |
| 7d | B | 231 | 166 | 71.9% | 76.0% | -4.2 pp | 32 | 84 |

## Friction-adjusted paper win rate (where computable)

| Window | Arm | Evaluated trades | Wins | Win rate | PnL ($1 stakes) | Unique markets | Dropped |
|---|---|---|---|---|---|---|---|
| lifetime | A | 3556 | 1046 | 29.4% | -27.65 | 380 | — |
| lifetime | B | 3546 | 1038 | 29.3% | -28.18 | 377 | 10 |
| 30d | A | 896 | 298 | 33.3% | -3.56 | 147 | — |
| 30d | B | 889 | 292 | 32.8% | -4.06 | 145 | 7 |
| 7d | A | 185 | 70 | 37.8% | +0.75 | 34 | — |
| 7d | B | 185 | 70 | 37.8% | +0.75 | 34 | 0 |

## Reading

- **Directional accuracy** rises 15.6 pp lifetime (58.7% → 74.3%), 16.0 pp in 30d
  (54.2% → 70.2%), 14.4 pp in 7d (57.5% → 71.9%). The removed predictions (1,236 lifetime,
  1,017 in 30d, 84 in 7d) were right 21.4%, 19.9% and 17.9% of the time respectively.
- **Edge vs price** improves but stays at or below zero: −2.9 → −0.4 pp lifetime, −5.7 →
  −3.6 pp in 30d, −6.7 → −4.2 pp in 7d. After the lever the predictor is the market price
  (74.3% accuracy at a 74.6% mean price). It is no longer worse than the market; it is not
  better than it either.
- **Friction-adjusted win rate is unchanged** (29.4 → 29.3% lifetime, 33.3 → 32.8% in
  30d, 37.8 → 37.8% in 7d). The risk gate's `MIN_CONFIDENCE 0.75` already rejects every
  trade the lever would remove, so only 10 evaluated trades lifetime (7 in 30d, 0 in 7d)
  sat below 0.50. The 45% bar stays 15.7 / 12.2 / 7.2 pp away.
- **Unique markets** shrink by about a quarter (355 → 264 lifetime, 43 → 32 in 7d); the
  suppressed markets are the 0.2–0.4 politics/default markets that were re-predicted every
  cycle. Directional samples per market stay high (~11 lifetime), so effective N is still
  the unique-market count, not the row count.

## Gate status after the lever

| Gate | Lifetime | 30d | 7d |
|---|---|---|---|
| Directional accuracy ≥ 50% | 74.3% (pass, +24.3 pp) | 70.2% (pass, +20.2 pp) | 71.9% (pass, +21.9 pp) |
| Friction-adjusted win rate ≥ 45% | 29.3% (**fail**, −15.7 pp) | 32.8% (**fail**, −12.2 pp) | 37.8% (**fail**, −7.2 pp) |

**The live-trading gate stays CLOSED.** The lever fixes the measured accuracy number and
stops the scanner emitting predictions with a known 80% failure rate; it does not create
edge and does not move the win-rate gate. What would: scoring edge against the market price
as a first-class metric, and a trade evaluator that scores on resolution rather than 4 h
tick drift against a 0.5 pp spread (both noted in the 2026-09-04 dashboard).

## Reproduce

```bash
scp dgx-remote:/opt/loop/data/prediction_outcomes.json dgx-remote:/opt/loop/lab/trading_log.json /tmp/bt/
python3 -m lab.backtest_no_bullish_below --outcomes /tmp/bt/prediction_outcomes.json \
    --trades /tmp/bt/trading_log.json --now 2026-09-04T20:30:00+00:00 --markdown /tmp/bt/tables.md
```
