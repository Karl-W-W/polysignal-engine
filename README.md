# PolySignal-OS

Autonomous prediction market intelligence system built on LangGraph.

## What it does

PolySignal-OS continuously scans Polymarket crypto markets, detects price signals using rolling time-window analysis, generates directional predictions, and tracks their accuracy over time. The system is building toward ML-powered autonomous trading — currently in data collection mode, accumulating labeled predictions to train an XGBoost model that will replace the rule-based predictor.

## Architecture

```
┌─────────────┐    ┌──────────────┐    ┌───────────────────────────────────┐
│  perception  │───▶│  prediction   │───▶│  TRADING_ENABLED?                 │
│  (scan +     │    │  (detect +    │    │                                   │
│   evaluate)  │    │   record)     │    │  false → END (short-circuit)      │
└─────────────┘    └──────────────┘    │  true  → draft → review → risk   │
                                        │          → approve → commit       │
                                        └───────────────────────────────────┘
```

**7-node LangGraph StateGraph pipeline:**
1. **perception** — Fetch markets from Polymarket Gamma API, evaluate past predictions
2. **prediction** — Detect signals via rolling windows (15m/1h/4h), generate hypotheses, record for tracking
3. **draft** — LLM generates execution plan (skipped when trading disabled)
4. **review** — LLM supervisor audit (skipped when trading disabled)
5. **risk_gate** — Position limits, loss caps, kill switch enforcement
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
  outcome_tracker.py   Prediction recording + time-horizon evaluation
  feature_engineering.py 18-feature extraction pipeline
  xgboost_baseline.py   ML training + inference (Phase 2)
  data_readiness.py     Monitors progress toward ML training threshold
  moltbook_publisher.py Signal publishing (dry-run until JWT)
  ...

workflows/      LangGraph pipelines
  masterloop.py   7-node MasterLoop (the core engine)
  scanner.py      Continuous scanning service (5-min intervals)

tests/          256 tests (pytest)
agents/         Telegram bot
brain/          Runtime memory (gitignored)
```

### Lab Promotion Protocol

All new capabilities follow: **Build** (in lab/) → **Test** (pytest) → **Review** (human approval) → **Promote** (move to core/ or workflows/).

## Tech Stack

- **Python 3.13** with LangGraph, LangChain, Pydantic
- **XGBoost + scikit-learn** for ML prediction (Phase 2)
- **NVIDIA DGX Spark** — Ollama with llama3.3:70b for LLM inference
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

**Phase 1.95** — Data collection and prediction evaluation.

| Metric | Value |
|--------|-------|
| Tests | 256 passing |
| Predictions | 170+ accumulated |
| Accuracy | ~67% (rule-based baseline) |
| Markets tracked | 14 crypto markets |
| Observations | 4,300+ |

**Next milestone:** 50 evaluated predictions → train XGBoost → if accuracy >55% → wire into pipeline.

## Multi-Agent System

Three agents collaborate on development:

- **Claude Code** — Architect. Strategy, complex implementations, code quality, testing.
- **Loop** (OpenClaw on DGX) — Autonomous agent. Code reviews, data analysis, proactive monitoring. Runs 24/7 on heartbeat.
- **Antigravity** — Infrastructure agent. DGX operations, Docker, deployments, systemd services.

Agents coordinate through `TASKS.md` (Loop's task queue), `PROGRESS.md` (shared state), and Telegram.

## Design Philosophy

> *"The market is a noisy communications channel. We do not predict; we decode."*

- **Absolute empiricism** — No fundamental analysis. Only mathematical signals: price, volume, alternative data.
- **Friction awareness** — All models account for execution costs and slippage.
- **Lab-first development** — New code starts in lab/, gets tested, then promotes to core/ with human approval.
- **Find, don't build** — Leverage existing tools (py-clob-client, Polymarket/agents) over reinventing.
