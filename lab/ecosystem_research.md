# PolySignal Ecosystem Research (Session 15)

## Summary

Our LangGraph pipeline architecture is validated by the ecosystem. The gap is prediction quality
(50.9% baseline accuracy) and execution layer (no wallet yet). Research identified 4 high-ROI
integrations and confirmed the XGBoost approach is correct.

---

## 1. py-clob-client — MUST USE (Official SDK)

**Repo**: github.com/Polymarket/py-clob-client | **Stars**: 842 | **Active** (v0.34.6, Feb 2026)

Level 0 (no auth, use NOW):
- `get_order_book(token_id)` — orderbook depth
- `get_midpoint(token_id)` — mid-price
- `get_price(token_id, side)` — BUY/SELL price
- `get_last_trade_price(token_id)` — last trade

Level 1-2 (needs wallet):
- `create_order()`, `post_order()`, `cancel_order()`, `get_positions()`

**Integration**: `pip install py-clob-client` → enhance perception_node with spread/depth signals.

## 2. Polymarket/agents — REFERENCE ONLY

**Repo**: github.com/Polymarket/agents | **Stars**: 2,400 | **Stale** (18 months)

Architecture: Researcher → Estimator → Executor (mirrors our pipeline).
Useful patterns: Kelly criterion sizing, market filtering heuristics, RAG-based research.
NOT worth adopting wholesale — stale, OpenAI-only, LangChain-based (we use LangGraph).

## 3. PolyClaw — EVALUATE FOR LOOP

**Repo**: github.com/chainstacklabs/polyclaw | **Stars**: 166 | **Active** (Jan 2026)

OpenClaw skill for Polymarket: browse markets, execute trades, track positions, hedge discovery.
Split + CLOB execution, Cloudflare bypass via rotating proxy.
Dependencies: py-clob-client, web3.py, OpenRouter API.

**Risk**: Needs network access. Must vet for prompt injection vectors before installing.

## 4. Academic: News Retrieval is #1 Improvement

**Paper**: arxiv.org/abs/2402.18563 "Approaching Human-Level Forecasting with Language Models"

Three-stage pipeline:
1. **Retrieval**: LLM generates search queries → fetch news → rank by relevance → summarize
2. **Reasoning**: Structured scratchpad (rephrase, for/against, weight, calibrate)
3. **Ensembling**: 6 forecasts aggregated via trimmed mean

Key finding: **Retrieval improved Brier score by 0.027** (massive). Without retrieval, accuracy
collapsed. Our prediction_node does zero retrieval — this is the single highest-ROI improvement.

## 5. Profitable Strategies (ranked by fit)

| Strategy | Expected Edge | Win Rate | Our Fit |
|----------|-------------|----------|---------|
| **High-Probability Bonds** | 5% per trade | ~95% | Easy — detect >95% markets near resolution |
| **Information Arbitrage** | Highest alpha | Varies | Our LLM pipeline IS this |
| **Domain Specialization** | High (96%+) | High | What we're building toward |
| **Momentum** | 3-5% | 55-60% | Our current signal detection |
| **Mean Reversion** | 1-2% | 55-58% | Add as feature in XGBoost |

## 6. ClawHub Security Warning

Audit of 2,857 ClawHub skills found **341 malicious entries** including "ClawHavoc" campaign
(335 infostealers). A skill called "What Would Elon Do?" that reached #1 was malware.
**VET EVERY SKILL MANUALLY before installing on DGX.**

## 7. Backtesting Framework

**Repo**: github.com/clawdvandamme/polymarket-trading-bot

Implements 4 strategies with backtesting engine:
- Longshot Bias (2-3% edge, 58-62% win rate)
- Arbitrage (2-5% edge, ~95% win rate)
- Momentum (3-5% edge, 55-60% win rate)
- Mean Reversion (1-2% edge, 55-58% win rate)

Includes commission/slippage modeling, Sharpe ratio calculation. Could validate our XGBoost
predictions before going live.

---

## Integration Priority

### Immediate (Session 15-16)
1. XGBoost wired into masterloop — 91.3% vs 50.9% baseline ✅ TRAINED
2. py-clob-client Level 0 in perception_node — orderbook depth as new features
3. High-probability bond detection in scanner — free alpha
4. Drop 4h horizon (0% accuracy) and investigate market 824952

### Near-term (Session 17+)
5. News retrieval pipeline — biggest accuracy multiplier
6. PolyClaw evaluation for Loop (after Squid proxy + security audit)
7. Backtesting engine for strategy validation
8. Kelly sizing module for position management

### Requires Human
9. Polymarket wallet + CLOB auth (Karl)
10. MoltBook JWT (Karl)
11. Squid proxy domain allowlist approval (Karl)
