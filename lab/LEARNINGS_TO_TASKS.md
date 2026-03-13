# Learnings → Tasks Pipeline
# Bridge between MoltBook/ClawHub intelligence and implementation.
# Loop writes discoveries here. Claude Code picks up actionable items.
# Updated: Session 23 (2026-03-11)

---

## How This Works
1. Loop scans MoltBook/ClawHub and discovers a useful technique
2. Loop writes it here with context + source + proposed implementation
3. Claude Code reviews on next session and implements the best ones
4. Completed items move to "Implemented" section below

---

## Pending (Ready for Claude Code)

### ~~P0: Bearish Signal Quality Fix~~ — IMPLEMENTED (Session 24)
- **Source**: Backtest results (Session 23) + live post-gate data (Session 24)
- **Finding**: Live data was worse than backtest: Bearish 5.6% (1W/17L), Bullish 100% (6W/0L).
- **Action taken**: **Bearish BANNED entirely** at XGBoost gate. Bullish-only mode.
- **Still needed**: Train direction-aware XGBoost models. Add bearish-specific features (volume spike, spread widening).
- **Effort**: Medium (2-3 hours) — for bearish rehabilitation when data supports it

### P0: Market Diversity — Only 2 Markets Survive Gates
- **Source**: Backtest (Session 23) — only 556108 and 1541748 produce profitable trades
- **Finding**: 14 markets scanned, 4 excluded, remaining ~8 never generate signals strong enough to pass gates
- **Action needed**: Research which Polymarket markets share properties with winners. Use ClawHub `zonein` skill to find what top traders are active in.
- **Effort**: Medium (research + implementation)

### P1: 6-Gate Agent Architecture Comparison
- **Source**: MoltBook agentfinance — 6-gate agent post ($366 USDC, -$108 P&L, 89 trades)
- **Finding**: They use 6 gates: regime, edge score, volatility, position concentration, correlation, and drawdown. We use 2: XGBoost confidence + risk gate.
- **Missing gates**:
  - Volatility gate: don't trade when market is too volatile (whipsaws)
  - Concentration gate: don't put >30% in one market (we had 68% in 824952!)
  - Drawdown gate: stop trading if daily loss exceeds threshold (we have DAILY_LOSS_CAP but no drawdown-based pause)
  - Regime detection: bull/bear market filter (we have nothing)
- **Effort**: High (1-2 sessions)

### P1: Nightly Build Pattern
- **Source**: MoltBook general — "The Nightly Build" (5847 upvotes)
- **Finding**: Agent ships one small useful thing every night while human sleeps. We have heartbeats but don't build.
- **Action needed**: Give Loop a "build something" task on each overnight heartbeat. Small scripts, data analysis, feature experiments.
- **Effort**: Low (config change + HEARTBEAT.md update)

### P2: A2A Signal API (x402 Revenue)
- **Source**: MoltBook agentfinance — "Agent-to-Agent services via x402"
- **Finding**: Agents selling API endpoints to other agents via USDC micropayments. Our signals are the product.
- **Action needed**: Build a FastAPI endpoint that serves our predictions. Wire x402 payment protocol.
- **Effort**: High (new service, needs wallet integration)

### P2: Write-on-Decide Pattern
- **Source**: MoltBook memory canon (203 upvotes)
- **Finding**: Write your decision to file BEFORE acting on it. Survives context compression.
- **Action needed**: Add decision logging to masterloop commit_node and prediction_node.
- **Effort**: Low (30 min)

### P2: TDD Forcing Function
- **Source**: MoltBook general (3131 upvotes)
- **Finding**: "Never write production code without failing tests first"
- **Action needed**: Enforce in CLAUDE.md and Loop HEARTBEAT.md — every code change needs a test.
- **Current state**: We do this (382 tests) but it's not enforced policy.
- **Effort**: Low (documentation)

---

## Implemented (Done)

### Toxic Market Exclusion
- **Source**: Loop's per-market accuracy audit (Session 23)
- **Implementation**: 4 markets excluded from signal detection, prediction, and training
- **Result**: 43% → ~73-89% on clean markets

### Prediction Market Backtester
- **Source**: MoltBook — "analysis paralysis" post + VectorBT research
- **Implementation**: lab/backtester.py with binary P&L, Kelly criterion, threshold sweep
- **Result**: First-ever backtest: 89% win rate, Sharpe 1.22

### Full MoltBook Coverage
- **Source**: Loop's scan showed we were missing 10 submolts
- **Implementation**: Scanner expanded to all 20 submolts
- **Result**: 632 posts in knowledge base

---

## ClawHub Skills to Evaluate

### polymarket-simmer-fastloop (126 downloads)
- **What**: Trades BTC/ETH/SOL 5/15-min fast markets with momentum + order book filters
- **Interest**: Market selection logic, momentum filters, order book analysis
- **Security**: Flagged "suspicious" by ClawHub's own scanner. MANUAL AUDIT REQUIRED.
- **Action**: Loop deep-reads the skill docs on ClawHub. Extract techniques. Do NOT install.

### zonein (619 downloads)
- **What**: Tracks top traders with >75% win-rate on Polymarket + Hyperliquid
- **Interest**: Copy-trading intelligence — find what markets the best traders are active in
- **Security**: Needs audit.
- **Action**: If clean, install and use for market selection.

### neural-memory (4377 downloads)
- **What**: Associative memory with spreading activation
- **Interest**: Could upgrade our flat-file memory system
- **Security**: Needs audit.
- **Action**: Low priority. Current MEMORY.md + learnings files work.
