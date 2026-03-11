# PolySignal-OS

Autonomous prediction market intelligence system built on LangGraph.

## What it does

PolySignal-OS continuously scans Polymarket crypto markets, detects price signals using rolling time-window analysis, generates directional predictions with XGBoost confidence gating, publishes intelligence to MoltBook (the agent social network), and tracks accuracy over time. The system runs a trained XGBoost meta-predictor that suppresses low-confidence predictions before they reach the trading pipeline. An autonomous agent (Loop) runs 24/7 on DGX, pushing code through auto-merge CI without human intervention.

## Architecture

```
┌─────────────┐    ┌──────────────┐    ┌───────────────────────────────────┐
│  perception  │───▶│  prediction   │───▶│  TRADING_ENABLED?                 │
│  (scan +     │    │  (detect +    │    │                                   │
│   evaluate)  │    │   XGBoost     │    │  false → END (short-circuit)      │
└─────────────┘    │   gate +      │    │  true  → draft → review → risk   │
                    │   record)     │    │          → approve → commit       │
                    └──────────────┘    └───────────────────────────────────┘
```

**7-node LangGraph StateGraph pipeline:**
1. **perception** — Fetch markets from Polymarket Gamma API, refresh CLOB microstructure features (bid/ask/spread/depth), evaluate past predictions against outcomes
2. **prediction** — Detect signals via rolling windows (15m/1h), filter excluded markets, generate hypotheses, suppress Neutrals, XGBoost confidence gate suppresses P(correct)<0.5, record with gate scores for tracking
3. **draft** — LLM generates execution plan (skipped when trading disabled)
4. **review** — LLM supervisor audit with HMAC signature (skipped when trading disabled)
5. **risk_gate** — Position limits ($10 max), loss caps ($50/day), kill switch enforcement
6. **wait_approval** — Human-in-the-loop gate
7. **commit** — Execute trade, publish to MoltBook, write memory

When `TRADING_ENABLED=false`, the pipeline short-circuits after prediction — perception and prediction still run for data collection, but no LLM calls are made and no Telegram alerts are sent.

## Project Structure

```
core/           Vault — production code (read-only without authorization)
  perceive.py     Polymarket Gamma API client
  predict.py      Rule-based prediction engine
  risk.py         Risk management (kill switch, position caps)
  signal_model.py Pydantic Signal schema
  notifications.py Telegram dispatcher with dedup
  ...

lab/            Experiment scratchpad — new capabilities start here
  outcome_tracker.py     Prediction recording + evaluation + per-market accuracy
  feature_engineering.py 15 features (10 price + 5 CLOB microstructure) with temporal safety
  xgboost_baseline.py   XGBoost training + inference — 91.3% test, temporal train/test split
  retrain_pipeline.py    Automated retrain: build dataset → train → compare → replace if better
  clob_prototype.py      Market microstructure features from gamma-api (15 markets live)
  time_horizon.py        Derives signal validity window from market observables
  moltbook_publisher.py  Signal publishing to MoltBook (JWT live)
  moltbook_scanner.py    Knowledge extraction from 10 MoltBook submolts (sanitized)
  moltbook_engagement.py Subscribe, follow, upvote, comment on agent network
  moltbook_math_solver.py Auto-solve MoltBook verification challenges
  LOOP_TASKS.md          Loop's canonical task queue (syncs through directory mount)
  reviews/               Loop's code review output files
  ...

workflows/      LangGraph pipelines
  masterloop.py   7-node MasterLoop with XGBoost confidence gate
  scanner.py      Continuous scanning service (5-min intervals)

tests/          305 tests (pytest)
agents/         Telegram bot
brain/          Runtime memory (gitignored)
```

### Lab Promotion Protocol

All new capabilities follow: **Build** (in lab/) → **Test** (pytest) → **Review** (human approval) → **Promote** (move to core/ or workflows/).

## Tech Stack

- **Python 3.13** with LangGraph, LangChain, Pydantic
- **XGBoost + scikit-learn** for ML prediction (Phase 2)
- **NVIDIA DGX Spark** (Blackwell GB10 GPU) — Ollama with llama3.3:70b for LLM inference
- **Polymarket Gamma API** — Market data + microstructure features (bid/ask/spread/volume/liquidity)
- **py-clob-client** — CLOB orderbook access for prediction market trading
- **Telegram** — Notifications and alerts
- **OpenClaw** — Autonomous agent (Loop) running on DGX
- **GitHub Actions** — CI (pytest on push) + auto-merge for `loop/*` branches
- **MoltBook** — Agent social network (publishing, knowledge extraction, engagement)

## Quick Start

```bash
git clone https://github.com/Karl-W-W/polysignal-engine.git
cd polysignal-engine

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your API keys

# Run tests
python -m pytest tests/ --tb=short -k 'not test_api'

# Run scanner (continuous mode)
python -m workflows.scanner
```

## Current Status

**Session 22** (March 10-11, 2026) — MoltBook live, first autonomous deploys, knowledge extraction operational.

| Metric | Value |
|--------|-------|
| Tests | 305 passing |
| Predictions | 406+ accumulated, 47 with post-gate XGBoost scores |
| Pre-gate accuracy | 42% (63W/88L) — contaminated by market 824952 (0W/40L, now excluded) |
| Post-gate accuracy | 47 predictions baselined, evaluations expected ~March 11 |
| XGBoost gate | LIVE — 91.3% test accuracy, mean gate score 0.760, balanced directional split |
| Markets tracked | 14 active crypto (824952 excluded) |
| CLOB features | 15 markets with bid/ask/spread/volume/liquidity refreshed every cycle |
| Observations | 19,700+ across 15 markets |
| MoltBook | LIVE — registered, verified, publishing, scanning 10 submolts, 138 knowledge entries |
| Auto-merge CI | PROVEN — 2 autonomous deploys (scanner-fix + gate-tracking) |
| Scanner | Running 24/7, cycle 174+, 0 errors |
| Loop autonomy | Full: network, GPU, MoltBook, auto-merge, retrain trigger, heartbeat wired |

**Next:** Polymarket wallet (human) → `TRADING_ENABLED=true` → first trade. Post-gate accuracy arrives ~March 11. Everything else is ready.

## Multi-Agent System

Three agents collaborate on development:

- **Claude Code** — Architect. Strategy, complex implementations, code quality, testing.
- **Loop** (OpenClaw on DGX) — Autonomous agent. Code reviews, data analysis, live market data fetch, CLOB feature extraction, MoltBook scanning + engagement, proactive monitoring. Runs 24/7 on heartbeat with network (Squid proxy), GPU (Blackwell GB10), MoltBook JWT, scanner restart, git push (auto-merge CI), retrain trigger, and data/ write access. First autonomous code deploys achieved Session 22.
- **Antigravity** — Infrastructure agent. DGX operations, Docker, deployments, systemd services.

Agents coordinate through `lab/LOOP_TASKS.md` (Loop's task queue), `PROGRESS.md` (shared state), `lab/reviews/` (Loop's review output), and Telegram.

## Design Philosophy

> *"The market is a noisy communications channel. We do not predict; we decode."*

- **Absolute empiricism** — No fundamental analysis. Only mathematical signals: price, volume, alternative data.
- **Friction awareness** — All models account for execution costs and slippage.
- **Lab-first development** — New code starts in lab/, gets tested, then promotes to core/ with human approval.
- **Find, don't build** — Leverage existing tools (py-clob-client, Polymarket/agents) over reinventing.
