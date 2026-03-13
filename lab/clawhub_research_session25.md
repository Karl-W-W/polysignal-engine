# ClawHub Research - Session 25

## argus-edge (CLEAN)
EV = our_P(win) - market_price. Bet when edge >= 10 pct. Kelly sizing. Freshness guard: <30 min markets hit 77.8 pct vs 56.6 pct overall. Counter-consensus rule: 5x payout.

## prediction-market-aggregator (SUSPICIOUS)
Metaculus superforecaster consensus as ground truth. When disagrees >15 pct with Polymarket = edge. DO NOT install.

## polyedge (SUSPICIOUS)
Correlation analysis. External API red flag. DO NOT install. Math is clean.

## Actionable
1. Compute EV = base_rate - market_price
2. Only trade when EV > 10 pct
3. Add freshness filter
4. Query Metaculus API for cross-reference
