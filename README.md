# PolySignal-OS

Autonomous prediction market intelligence system built on LangGraph.

## What it does

PolySignal-OS continuously scans Polymarket crypto markets, detects price signals using rolling time-window analysis, generates directional predictions with XGBoost confidence gating, and tracks their accuracy over time. The system runs a trained XGBoost meta-predictor that suppresses low-confidence predictions before they reach the trading pipeline.

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
1. **perception** — Fetch markets from Polymarket Gamma API, evaluate past predictions against outcomes
2. **prediction** — Detect signals via rolling windows (15m/1h), generate hypotheses, XGBoost confidence gate suppresses P(correct)<0.5, record for tracking
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
  outcome_tracker.py     Prediction recording + time-horizon evaluation
  feature_engineering.py 19-feature extraction pipeline (10 active after pruning)
  xgboost_baseline.py   XGBoost training + inference — 91.3% test accuracy
  time_horizon.py        Derives signal validity window from market observables
  data_readiness.py      Monitors progress toward ML training threshold
  moltbook_publisher.py  Signal publishing (dry-run until JWT)
  ecosystem_research.md  py-clob-client, PolyClaw, arxiv, trading strategies
  LOOP_TASKS.md          Loop's canonical task queue (syncs through directory mount)
  reviews/               Loop's code review output files
  ...

workflows/      LangGraph pipelines
  masterloop.py   7-node MasterLoop with XGBoost confidence gate
  scanner.py      Continuous scanning service (5-min intervals)

tests/          260 tests (pytest)
agents/         Telegram bot
brain/          Runtime memory (gitignored)
```

### Lab Promotion Protocol

All new capabilities follow: **Build** (in lab/) → **Test** (pytest) → **Review** (human approval) → **Promote** (move to core/ or workflows/).

## Tech Stack

- **Python 3.13** with LangGraph, LangChain, Pydantic
- **XGBoost + scikit-learn** for ML prediction (Phase 2)
- **NVIDIA DGX Spark** (Blackwell GB10 GPU) — Ollama with llama3.3:70b for LLM inference
- **Polymarket Gamma API** — Market data source
- **Telegram** — Notifications and alerts
- **OpenClaw** — Autonomous agent (Loop) running on DGX
- **GitHub Actions** — CI (pytest on push)

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

**Session 18** — Full infrastructure operational. Loop agent has network, GPU, scanner control, and git push.

| Metric | Value |
|--------|-------|
| Tests | 260 passing |
| Predictions | 356 accumulated, 347 evaluated |
| Accuracy | 41.7% rule-based (63W/88L) — 89% excluding market 824952 |
| XGBoost gate | LIVE — suppresses P(correct)<0.5 (91.3% test accuracy) |
| Markets tracked | 14 crypto (market 824952 excluded from predictions) |
| Observations | 9,691+ across 14 markets |
| Scanner | Running 24/7 on DGX, 5-min intervals |
| Loop capabilities | Network (Squid proxy), GPU (Blackwell GB10), scanner restart, git push |

**Next:** Anthropic credit refill → Loop validates network → py-clob-client orderbook features → XGBoost retrain on GPU → MoltBook JWT → first published signal.

## Multi-Agent System

Three agents collaborate on development:

- **Claude Code** — Architect. Strategy, complex implementations, code quality, testing.
- **Loop** (OpenClaw on DGX) — Autonomous agent. Code reviews, data analysis, live market data fetch, proactive monitoring. Runs 24/7 on heartbeat with network access (Squid proxy), GPU (Blackwell GB10), scanner restart, and git push to `loop/*` branches.
- **Antigravity** — Infrastructure agent. DGX operations, Docker, deployments, systemd services.

Agents coordinate through `lab/LOOP_TASKS.md` (Loop's task queue), `PROGRESS.md` (shared state), `lab/reviews/` (Loop's review output), and Telegram.

## Design Philosophy

> *"The market is a noisy communications channel. We do not predict; we decode."*

- **Absolute empiricism** — No fundamental analysis. Only mathematical signals: price, volume, alternative data.
- **Friction awareness** — All models account for execution costs and slippage.
- **Lab-first development** — New code starts in lab/, gets tested, then promotes to core/ with human approval.
- **Find, don't build** — Leverage existing tools (py-clob-client, Polymarket/agents) over reinventing.
