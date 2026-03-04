# Oracle Research: Polymarket Ecosystem (Session 14)

## Key Finding

Our MasterLoop architecture already mirrors the best patterns. The execution gap is narrow:
we need `py-clob-client` + position tracking + Kelly sizing when TRADING_ENABLED goes true.

---

## 1. py-clob-client (Official Polymarket SDK) — PRODUCTION READY

- Official Python client for Polymarket's CLOB (Central Limit Order Book)
- Order placement, cancellation, market data, position management
- Client-side EIP-712 signing (private key never leaves machine)
- Token ID mapping: each market has YES/NO token IDs (orders reference tokens, not markets)
- URL: `https://github.com/Polymarket/py-clob-client`

**Integration path**: `pip install py-clob-client` → `lab/execution.py` → wire into commit_node

## 2. Polymarket/agents (Official Agent Framework) — EXPERIMENTAL

- Polymarket's own open-source trading agent
- Architecture: Researcher → Trader → Executor (maps to our perception → prediction → commit)
- Kelly criterion for position sizing: `edge = p_estimate - p_market`
- Market filtering by volume, liquidity, time-to-resolution
- URL: `https://github.com/Polymarket/agents`

**Reusable patterns**: Kelly sizing module, market filtering logic, dry-run mode

## 3. ClawHub Polymarket Skills — NONE EXIST YET

No published OpenClaw/ClawHub skills for Polymarket trading. We'd be first.
Opportunity: build `polymarket-trade` skill for Loop.

## 4. Architecture Mapping

| Their Pattern | Our Equivalent | Status |
|---------------|---------------|--------|
| Researcher | perception_node | Done |
| Estimator | prediction_node | Done (rule-based → XGBoost pending) |
| Risk checks | risk_gate_node | Done |
| HITL approval | wait_approval_node | Stub (hardcoded True) |
| Executor | commit_node | Needs py-clob-client wiring |
| Position tracking | — | Not built yet |
| Kelly sizing | — | Not built yet |

## 5. What to Build for Order Execution (Phase 5)

1. `lab/execution.py` wrapping py-clob-client: `place_limit_order()`, `cancel_order()`, `get_positions()`
2. Position tracking table in polysignal.db
3. Kelly sizing: `edge = xgboost_confidence - market_price` → bet size
4. Execution splitting: TWAP across 3 tranches over ~5 minutes
5. Reconciliation: local state vs API state on each cycle

## 6. Trading Agent Best Practices

- **Execution splitting**: never full position in one order (3-5 tranches, TWAP/VWAP)
- **Position tracking**: local DB, reconcile with API each cycle
- **Risk layers**: per-position max, portfolio max, correlation limits, liquidity gate
- **Graceful degradation**: if LLM/API fails, pause — don't trade blind
- **Audit trail**: every decision logged (our LangGraph state already does this)
