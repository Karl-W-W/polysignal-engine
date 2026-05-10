# PolySignal-OS: System Architecture & Epistemology

## 1. The Epistemology (RenTec First Principles)
* **Absolute Empiricism:** The market is a noisy communications channel. We do not predict; we decode.
* **No Fundamental Analysis:** Do not write code that looks at balance sheets, news sentiment, or macroeconomics. We only process mathematical signals, price, volume, and alternative data.
* **Friction Awareness:** Execution costs destroy theoretical alpha. All models must account for slippage and latency.

### 1.A Documented Drifts (S42 audit, 2026-05-07)
Four practice-vs-principle gaps catalogued during the S42 deep-dive. Two
fixed, two flagged for review.

1. **Friction Awareness vs friction-free PnL** — `lab/polymarket_trader.py`
   `evaluate_paper_trades` computed `pnl = (price_delta / entry_price) * size`
   with zero slippage and zero fees. Introduced commit `594388e`
   (2026-03-11, S23). **Fixed S42 Phase 5**: 0.5pp default slippage,
   `FRICTION_SLIPPAGE_PP` env override, `slippage_pp`/`fee_pp` recorded on
   each TradeResult. Backfill produced lifetime 83.7% → 1.86% win rate.

2. **Decode-not-predict vs uniform 4h horizon on long-horizon markets** —
   `lab/outcome_tracker.py:DEFAULT_HORIZON = "4h"` was applied to every
   prediction regardless of resolution timescale. Political markets (Orbán,
   Vance) resolving in months were scored against 4h noise (13% accuracy).
   Introduced commit at S37 (2026-04-03) when crypto horizon was lowered
   24h → 4h. **Fixed S42 Phase 6**: `EVAL_HORIZONS_BY_CATEGORY = {crypto:4h,
   sports:24h, politics:7d, default:4h}`. Observation factories tag
   `category`. Old records can't be re-classified (no `title` persisted).

3. **Absolute Empiricism vs `BAN_BEARISH_OUTPUT`** — `lab/base_rate_predictor.py`
   suppresses Bearish outputs at the predict() boundary instead of fixing the
   upstream price-level bias bug on crashing markets (S41 P2). Introduced
   S40 (2026-04-17). **TODO**: re-enable Bearish after S41 P2 lands the
   price-velocity guard in `from_price_levels`. Justification check next
   architect session.

4. **Friction Awareness vs `MIN_MOVE_THRESHOLD = 0.0005`** —
   `lab/outcome_tracker.py:46` treats sub-tick (0.05pp) movement as
   directional truth. 0.05pp is below the typical Polymarket spread, so
   "directional" outcomes at this threshold encode noise more than signal.
   Lowered from 0.003 → 0.0005 in commit `1f64716` (2026-04-13, S39).
   **TODO**: re-evaluate after Phase 6 per-category horizons accumulate
   2 weeks of data — likely raise to 0.005 (0.5pp) to align with the
   friction-model assumption used by paper-trade PnL. Decision next
   architect session.

## 2. The Folder Structure (Strictly Enforced)
* `/core`: The vault. The working PolySignal-OS engine. (READ ONLY unless explicitly authorized).
* `/agents`: Individual logic nodes (e.g., scraping, decoding).
* `/workflows`: LangGraph state machines tying agents together.
* `/lab`: Your scratchpad. This is the ONLY place you are allowed to test new code, break things, and experiment.

## 3. Technology Stack
* **Hardware:** NVIDIA DGX Spark (Use local NIM containers for repetitive LLM tasks).
* **Framework:** LangGraph (using perceive-decide-act-evaluate-learn-repeat loops).
* **Tracing:** LangSmith EU (`eu.api.smith.langchain.com`). Set `LANGCHAIN_TRACING_V2=true` for debugging ONLY. Default = false.
* **Observability:** `/monitor` dashboard page pulls live traces from LangSmith EU via `/api/langsmith` proxy.
* **Bridge:** OpenClaw + Telegram (Strict `exec approvals` required for security).

## 4. Agent Directives
1. You are a "shift worker." You have no memory of past chats. 
2. Your memory is this file and `PROGRESS.md`.
3. NEVER assume the state of the codebase. Always read the actual files first.

## 5. Vault Inventory (Approved `/core` Contents)
The following files are **officially in the Vault** and must not be rewritten without explicit authorization:
- `core/perceive.py` — Perception node (Polymarket Gamma API).
- `core/predict.py` — Prediction node (pattern matching from `polysignal.db`). ✅ Promoted 2026-02-23.
- `core/supervisor.py` — NVIDIA Supervisor (HMAC audit + security, NIM endpoint `integrate.api.nvidia.com/v1`).
- `core/bridge.py` — OpenClaw LangChain tool wrapper. ✅ Fixed `StructuredTool` import (2026-02-24).
- `core/api.py` — Flask API server. ✅ Fixed orchestrator import → `workflows.masterloop` (2026-02-24).
- `core/signal_model.py` — Canonical Pydantic Signal schema. ✅ Renamed from `signal.py` to fix stdlib shadow (2026-02-27).
- `core/risk.py` — Risk management gate (kill switch, position caps, loss caps, HITL). ✅ Promoted from lab Session 7 (2026-03-01).
- `core/notifications.py` — Telegram alert dispatcher.
- `core/openclaw_api.py` — OpenClaw API client.

**Agents (NOT the Vault, but tracked):**
- `agents/streaming.py` — ✅ Migrated from `AgentExecutor` to `langgraph.prebuilt.create_react_agent` (2026-02-27).

**Workflows (NOT the Vault, but stable):**
- `workflows/masterloop.py` — MasterLoop LangGraph engine. **5/5 clean proof on DGX 2026-02-24** (OpenClaw audit logs confirm full chain).

**Infrastructure:**
- `start.sh` — ✅ Fixed PYTHONPATH shadow, `-m` invocation, Option B independent restarts (2026-02-24).
- `requirements.txt` — ✅ Pinned to LangChain 1.x era matching bare-metal 5/5 proof (2026-02-24).

**Lab (Under Development — NOT production):**
- `lab/polymarket/risk.py` — ✅ PROMOTED to `core/risk.py` (Session 7, 2026-03-01). 7/7 self-tests + 11/11 pytest.
- `lab/signal.py` — Rich Pydantic Signal schema. ✅ `core/signal.py` renamed to `core/signal_model.py` (2026-02-27). Ready for promotion review.
- `lab/langsmith_eval.py` — LangSmith ecosystem verifier. ✅ Tested 2026-02-24.
- `lab/start_sh_fix.md` — ✅ APPLIED (Options A+B merged into start.sh).

## 6. The Lab Promotion Protocol
All new capabilities MUST follow this path before touching `/core`:
1. **Build** → Write in `/lab`.
2. **Test** → Standalone test passes with zero warnings.
3. **Review** → Human explicitly authorizes promotion.
4. **Promote** → Move to `/core` or `/workflows` only after approval.

