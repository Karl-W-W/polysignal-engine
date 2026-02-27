# PolySignal-OS: System Architecture & Epistemology

## 1. The Epistemology (RenTec First Principles)
* **Absolute Empiricism:** The market is a noisy communications channel. We do not predict; we decode.
* **No Fundamental Analysis:** Do not write code that looks at balance sheets, news sentiment, or macroeconomics. We only process mathematical signals, price, volume, and alternative data.
* **Friction Awareness:** Execution costs destroy theoretical alpha. All models must account for slippage and latency.

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
- `lab/signal.py` — Rich Pydantic Signal schema. ✅ `core/signal.py` renamed to `core/signal_model.py` (2026-02-27). Ready for promotion review.
- `lab/langsmith_eval.py` — LangSmith ecosystem verifier. ✅ Tested 2026-02-24.
- `lab/start_sh_fix.md` — ✅ APPLIED (Options A+B merged into start.sh).

## 6. The Lab Promotion Protocol
All new capabilities MUST follow this path before touching `/core`:
1. **Build** → Write in `/lab`.
2. **Test** → Standalone test passes with zero warnings.
3. **Review** → Human explicitly authorizes promotion.
4. **Promote** → Move to `/core` or `/workflows` only after approval.

