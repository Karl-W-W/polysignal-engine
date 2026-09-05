# PolySignal — Autonomy plan: from here to an evidence-based gate

Written 2026-09-05 on the Mac checkout. Nothing on the DGX was modified. Numbers come from
read-only copies of the live stores (`/opt/loop/data/prediction_outcomes.json`,
`/opt/loop/lab/trading_log.json`, `/opt/loop/data/clob_features_cache.json`, pulled
2026-09-05 17:31 CEST) and from `lab/BACKTEST-2026-09-04-no-bullish-below-0.5.md` and
`lab/EDGE-DIAGNOSIS-2026-09-05.md`.

## 0. The goal, restated as a machine-checkable condition

The live-trading gate **opens** on evidence and **stays open** on evidence, with no human in
the loop except for money decisions:

| Condition | Threshold | Window | Today (2026-09-05) |
|---|---|---|---|
| Directional accuracy | ≥ 50% | 30d and 7d | 54% / 56% (post-rung-0 replay: 70% / 72%) |
| Friction-adjusted win rate | ≥ 45% | 30d | 33% by 4 h drift; **not computable at resolution** (no fill fields) |
| Edge over market price | 95% CI lower bound > 0 | 30d, at ≥ 100 unique resolved markets | −6.0 pp ± 4.4 (364 markets, lifetime window) |
| Stays open | 7d edge_per_usd ≥ 0 on 3 consecutive truth-board days | rolling | n/a |

The third row is what "stays open because the edge is positive at 100+ unique resolved markets"
means in numbers. The first two are Karl's standing rule. Nothing below changes a threshold; the
foreman is not allowed to.

## 1. What the truth board must compute every 15 minutes

`lab/truth_board.py` runs on `polysignal-truth-board.timer` every 15 min. It currently writes
`accuracy_lifetime`, the resolution counters, the 4 h-drift `trade_eval`, and (rung 0)
`bullish_below_price_suppressed`. The gate needs the following set, each for lifetime / 30d / 7d
by prediction timestamp, written to `lab/.truth-board-status.json`:

| Metric | Definition | Source | Gate role |
|---|---|---|---|
| `directional_accuracy` | CORRECT / (CORRECT + INCORRECT), resolution-scored | `prediction_outcomes.json` `outcome` | Gate row 1 |
| `unique_resolved_markets` | distinct `market_id` among resolved rows | same | Denominator for every claim; effective N |
| `predictions_per_market` | resolved rows / unique markets | same | Repetition monitor (today ~12) |
| `edge_vs_price` | accuracy − mean(`price_at_prediction`) | same | Row-level edge (inflated by repetition) |
| `edge_market_level` + 95% CI | mean over unique markets of (outcome − mean price on that market); CI = 1.96·sd/√N | same | **Gate row 3** |
| `friction_win_rate` | share of scorable resolved rows with `friction_result == "win"` | `friction_result` (rung 1) | Gate row 2 |
| `edge_per_usd` + 95% CI | mean `friction_pnl_per_usd` over scorable rows; market-level variant as above | rung 1 fields | **Stays-open metric** |
| `mean_fill`, `mean_spread`, `fill_source_mix` | mean `fill_price`, mean `spread`, share with `fill_source == "mid_no_book"` | rung 1 fields | Data-quality guard: gate claims require ≥ 95% booked fills |
| `without_fill` | resolved rows with no fill logged (pre-rung history) | rung 1 | Shows how much history is unscorable |
| `calibration_by_price` | accuracy and edge per 0.1 price bucket, ≥ 0.5 only | `price_at_prediction` | Detects base-rate-only "accuracy" |
| `drift_win_rate` (legacy) | existing `trade_eval` from `trading_log.json` | unchanged | Continuity only; demoted from gate once `friction_win_rate` has ≥ 100 markets |
| `suppression_counters` | `bullish_below_price_suppressed` and future guards | `lab/.base-rate-suppressions.json` | Shows what the scanner refused |
| `price_staleness` | median |`price_at_prediction` − CLOB mid| for predictions within 3 h of `clob_features_cache.json` | cache | Today 0.000 median; alarm if > 0.02 |
| `gate` | the four conditions above evaluated to OPEN / CLOSED with reasons | all of the above | Rung 6 reads it |

### 1.1 Why the friction-adjusted win rate is not computable today, and the exact fields to log

`prediction_outcomes.json` records `price_at_prediction` (the gamma mid/last price) and a
resolution outcome. A win rate "after friction" needs what a trade would have cost. The scanner
must log, on **every prediction record** (`lab/outcome_tracker.PredictionRecord`) and on **every
paper trade** (`lab/polymarket_trader.TradeResult`):

| Field | Meaning | Where it comes from |
|---|---|---|
| `side` | `BUY` (Yes token) or `SELL` (No token) | hypothesis → side, same map as `lab/trade_proposal_bridge.py` |
| `outcome_token` | `Yes` / `No` | same |
| `fill_price` | price per token the trade would fill at: best ask for BUY, 1 − best bid for the No token | gamma `bestAsk` / `bestBid` on the market object |
| `fill_source` | `best_ask` / `one_minus_best_bid` / `mid_no_book` | derived; `mid_no_book` rows are excluded from gate claims |
| `best_bid`, `best_ask`, `spread`, `mid_price` | the quote at prediction time | gamma `bestBid`, `bestAsk`, `spread` |
| `fee_pp` | per-token fee assumed | `FRICTION_FEE_PP` env (0.0 today; Polymarket charges no taker fee on these markets) |
| `size_usdc` | stake the scanner would place | `MAX_POSITION_USDC` env (2.0), the same value `paper_trade` uses |
| `quote_timestamp` | when the quote was fetched | fetcher |

At evaluation the truth board then writes per record: `friction_pnl_per_usd` = (1 − fill − fee)/fill
on a win, (−fill − fee)/fill on a loss; `friction_pnl_usd` = that × `size_usdc`;
`friction_result` = win/loss. **Rung 1 implements exactly this** (branch `lever/log-friction-fields`).

Honesty note: for a binary token held to resolution, a "win" is simply a favourable resolution,
so `friction_win_rate` converges to directional accuracy on the booked subset. Friction shows up
in `edge_per_usd`, which is why that metric, not the win rate, is the stays-open criterion. The
gate keeps the ≥ 45% rule because Karl set it; the plan does not weaken it, it adds the metric that
actually moves.

## 2. The experiment ladder

One rung = one branch + one back-test + one acceptance number. Rungs are ordered so each one
either fixes a measurement or raises the number the next rung is judged on. Back-tests replay the
live stores read-only on the Mac (`lab/backtest_no_bullish_below.py` is the template).

| Rung | Branch | Change | Back-test | Acceptance number | Status |
|---|---|---|---|---|---|
| 0 | `lever/no-bullish-below-0.5` | No Bullish calls on markets priced < 0.50 (flag, default on) | `lab/BACKTEST-2026-09-04-no-bullish-below-0.5.md` | 30d directional accuracy ≥ 65% and 30d edge not worse | Done, pushed 2026-09-04; replay 54% → 70% |
| 1 | `lever/log-friction-fields` | Log side, token, fill price, bid/ask/spread, fee, size on every prediction and paper trade; truth board reports `friction_resolution` | none possible (logging); acceptance is data presence | After 48 h on the DGX: ≥ 95% of new resolved rows have `fill_source != mid_no_book` and `friction_resolution.7d.evaluated > 0` | Implemented 2026-09-05, pushed |
| 2 | `lever/one-call-per-market` | Record at most one prediction per market per resolution (re-predictions update, not append); keeps paper trades one per market | replay first-prediction-per-market: market-level edge −6.0 pp vs row-level −2.6 pp today | 7d `predictions_per_market` ≤ 1.5 and market-level accuracy ≥ 65% | Next |
| 3 | `lever/drop-obs-tick-source` | Disable `BaseRatePredictor.from_observations` (up-tick/down-tick counts); keep price-level and outcome sources | replay by source: obs-tick rows edge −5.0 pp (2,451 rows, 179 markets); price-level +0.6 pp | 30d row-level `edge_vs_price` ≥ −1.0 pp and unique markets/30d ≥ 60% of baseline | After 2 |
| 4 | `lever/breadth-100` | Reach ≥ 100 unique resolved markets per 30 d: raise `max_markets`, per-category quotas, stop the 12-market politics monoculture | replay: unique markets by category and horizon | ≥ 100 unique resolved markets in the trailing 30d with accuracy ≥ 50% | After 3 |
| 5 | `lever/edge-seeking-model` | Emit a call only when a calibrated P(YES) differs from the ask by more than spread + fee; base rate becomes a feature, not the model | walk-forward on resolved rows with rung-1 fields, market-level | market-level `edge_per_usd` 95% CI lower bound > 0 at ≥ 100 unique markets | After 4 |
| 6 | `lever/gate-automation` | Truth board writes `lab/.gate-status.json`; masterloop's short-circuit reads it; auto-close rule | tests + 7 days of consistent gate output in the status file | Gate evaluated every 15 min for 7 days with zero human edits | After 5 |
| 7 | live at minimum size | `TRADING_ENABLED` derived from the gate; $1 positions; kill switch | n/a | Karl's decision (money) | Needs Karl |

Power note that shapes the ladder: with today's variance, the market-level edge CI is ±4.4 pp at 364
markets and ≈ ±8 pp at 100 markets. So at N = 100 the edge must exceed +8 pp to open the gate, and
reaching ±2 pp would take ≈ 1,900 markets. Breadth (rung 4) is therefore on the critical path; the
model (rung 5) cannot be judged without it.

## 3. The foreman's merge rule

The foreman (Claude Code, autonomous) may merge a rung **by itself** only when all of these hold:

1. **Tests green**: full suite on the Mac (`-k 'not test_api'`) and the DGX auto-merge CI both pass.
2. **Target improves**: the rung's back-test moves the rung's named metric by at least its acceptance number, measured on the same stores and windows as the baseline.
3. **Edge not worse**: 30d `edge_vs_price` (and `edge_per_usd` once rung 1 has data) is not lower than baseline by more than 1.0 pp, and `unique_resolved_markets` is not reduced by more than 40%.
4. **Confined and reversible**: changes only in `lab/`, `workflows/`, `tests/`, `.gitignore`; behind an env flag defaulting to the new behaviour; no edits to `core/` (Vault), to gate thresholds, or to metric definitions.
5. **Data safety**: no store is rewritten or truncated; new fields default to `None` on old records; nothing is edited on the DGX (deploy is GitHub → CI → 10-minute mirror reset).

The foreman **must ask Karl** when any of:

- a condition above fails, or the back-test has fewer than 100 unique resolved markets and the claim is about edge (then the rung may only merge as logging/hygiene, never as an edge claim);
- the change touches `core/`, a gate threshold, a metric definition, model routing, or cost;
- anything spends money or acts outward: live trades, position size, Telegram beyond status lines, MoltBook posts;
- anything deletes or rewrites `prediction_outcomes.json`, `trading_log.json`, or `test.db`;
- rung 7, always.

Asking means: push the branch, write the back-test file, put one line in `lab/LOOP_TASKS.md` under "needs Karl", and stop. Never open the PR as merged.

## 4. Where the numbers stand, so the next session can check drift

| Number | Value | Source |
|---|---|---|
| Resolved rows in the 5,000-record window | 4,256 | `prediction_outcomes.json` 2026-09-05 17:31 |
| Unique resolved markets | 364 (273 at price ≥ 0.5) | same |
| Row-level edge vs price | −2.6 pp | same |
| Market-level edge (one row per market) | −6.0 pp ± 4.4 | same |
| Obs-tick source edge / price-level source edge | −5.0 pp / +0.6 pp | same, split on `confidence == price_at_prediction` |
| Price staleness (median |price − CLOB mid|) | 0.000 (45 predictions within 3 h of cache) | `clob_features_cache.json` |
| 4 h-drift friction win rate 30d | 33% | `trading_log.json` |
