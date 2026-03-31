# DGX Spark Infrastructure Roadmap
# Created: Session 23 (2026-03-11) | Blueprint → Implementation Plan
# Hardware: NVIDIA DGX Spark — GB10 Grace Blackwell Superchip
# Architecture: aarch64, CUDA 13.0, 128GB unified LPDDR5x, 4TB NVMe

---

## Current State (Level ~20)

| Component | Status | Utilization |
|-----------|--------|-------------|
| GPU (Blackwell) | XGBoost `device=cuda` working | ~0% idle, spikes for llama3.3:70b heartbeats |
| CPU (20-core ARM) | Scanner + Ollama + OpenClaw gateway | ~5% |
| RAM (128GB unified) | ~4GB idle, ~46GB when llama3.3:70b loaded | ~4-36% |
| NVMe (4TB) | 167GB used | ~5% |
| Ollama | llama3.3:70b (Loop primary), 3 small models. Nemotron UNLOADED. | Host 0.0.0.0, reachable from containers |
| PyTorch | Installed but sm_121 NOT SUPPORTED by pip wheel | Needs NGC container |
| RAPIDS | Not installed | - |
| NIM | Not installed | - |
| Triton | Not installed | - |
| Swap | 16GB ON | Should be OFF per blueprint |

## Phase 1: Immediate Wins (Done or In Progress)

### XGBoost GPU Training
- **Status**: DONE (Session 23)
- `device="cuda"` auto-detected on DGX, CPU fallback on Mac
- XGBoost 3.2.0 has CUDA 12.9 built-in, confirmed working on GB10
- Impact: Faster retrains as dataset grows (currently ~50 samples, GPU shines at 10K+)

### Retrain Systemd Watcher
- **Status**: DONE (Session 23)
- `polysignal-retrain.path` watching for `.retrain-trigger`
- Auto-runs retrain pipeline, replaces model if better, restarts scanner
- Loop can trigger from sandbox: `echo "retrain" > /mnt/polysignal/lab/.retrain-trigger`

### Prediction Market Backtester
- **Status**: DONE (Session 23)
- Binary outcome P&L model, Kelly criterion, threshold sweep
- 23 tests, validates strategy before enabling live trading

## Phase 2: NGC Container Stack (Next Session)

### PyTorch via NGC Container
- **Why**: pip wheel for PyTorch doesn't support Blackwell sm_121
- **How**:
  ```bash
  # Install NGC CLI
  pip install ngc-cli
  # or download: https://ngc.nvidia.com/setup/installers/cli

  # Pull NGC PyTorch container (ARM64 + Blackwell optimized)
  docker pull nvcr.io/nvidia/pytorch:25.03-py3

  # Run with GPU access and mount our codebase
  docker run --gpus all -it --rm \
    -v /opt/loop:/opt/loop \
    --ipc=host \
    nvcr.io/nvidia/pytorch:25.03-py3 bash
  ```
- **NGC API Key needed**: Get from https://ngc.nvidia.com/ → Setup → Generate API Key
- **Impact**: Enables transformer models, fine-tuning, embeddings, sentiment analysis on GPU

### NVIDIA NIM (LLM Inference)
- **Why**: TensorRT-LLM optimized inference (2-5x faster than Ollama)
- **When**: Only if we need local model serving faster than Ollama
- **Current assessment**: Low priority. Loop uses Claude via OpenClaw, not local models.
  Ollama serves llama3.3:70b adequately for non-Loop inference.
- **How** (when ready):
  ```bash
  docker pull nvcr.io/nim/meta/llama-3.1-70b-instruct:latest
  docker run --gpus all -p 8000:8000 \
    -e NGC_API_KEY=<key> \
    nvcr.io/nim/meta/llama-3.1-70b-instruct:latest
  ```

## Phase 3: Data Infrastructure (When Scale Demands)

### TimescaleDB (Replace SQLite)
- **Why**: Concurrent writers (scanner + Loop + retrain all touch DB),
  time-series functions, compression, continuous aggregates
- **When**: When concurrent write locks become a bottleneck or data > 1M rows
- **Current scale**: ~4,320 rows/day across 15 markets. SQLite is fine for now.
- **How**:
  ```bash
  # Add to docker-compose.yml
  docker pull timescale/timescaledb:latest-pg16
  ```
- **Migration**: `sqlite3 → psycopg2` adapter, continuous aggregates auto-compute hourly/daily stats

### RAPIDS (cuDF/cuML)
- **Why**: GPU-accelerated pandas and scikit-learn
- **When**: When feature engineering or backtesting becomes the bottleneck (100K+ rows)
- **Current assessment**: Low priority. 15 markets × 19 features runs in milliseconds on CPU.
- **How**: Conda install on aarch64 or NGC container
  ```bash
  docker pull nvcr.io/nvidia/rapidsai/notebooks:25.02-cuda13.0-py3.12
  ```

## Phase 4: Renaissance Tech Skills (Medium-Term)

### VectorBT (GPU-Accelerated Backtesting)
- **Status**: Custom backtester built (Session 23) — handles prediction market binary outcomes
- **VectorBT PRO**: $50-150/month, designed for traditional markets (continuous price action)
- **Decision**: Skip PRO. Our custom backtester is purpose-built for binary prediction markets.
  VectorBT free (`pip install vectorbt`) useful for visualization only.

### Advanced Math Toolkit
- **Status**: scipy 1.17.1 already installed
- **Needed**: statsmodels for cointegration/stationarity tests
- **Install**: `pip install statsmodels` on DGX venv

### Time-Series Database
- See TimescaleDB above. ClickHouse is overkill (optimized for OLAP at TB scale).

## Phase 5: Hardware Orchestration (Level 100 Target)

### Disable Swap
- **Why**: Swap to NVMe ruins deterministic execution times
- **Current**: 16GB swap.img active, 137MB used
- **Risk**: Low usage suggests it's not needed. Disabling saves NVMe bandwidth.
- **How**: `sudo swapoff -a && sudo sed -i '/swap/d' /etc/fstab`
- **CAUTION**: Verify no process depends on swap before disabling

### GPUDirect Storage (cuFile)
- **Assessment**: NOT NEEDED on DGX Spark
- **Why**: GB10 uses unified memory — CPU and GPU share the same physical RAM.
  There's no CPU→GPU memory copy to eliminate. cuFile provides zero benefit.

### Full Hardware Utilization Map
```
ARM CPU (20 cores):
  ├── Scanner (5-min cycles, Restart=always)
  ├── Ollama host process (llama3.3:70b on demand)
  ├── OpenClaw gateway — RUNNING (Session 31, llama3.3:70b)
  ├── Squid proxy
  ├── Cron (git sync)
  └── WebSocket feeds (future)

Blackwell GPU:
  ├── XGBoost training (device=cuda) ✅
  ├── Ollama inference (via host)
  ├── PyTorch models (needs NGC container)
  └── RAPIDS dataframes (when scale demands)

Unified Memory (128GB):
  ├── Market observations (SQLite → TimescaleDB future)
  ├── Model weights (XGBoost ~50KB, llama3.3:70b ~42GB on demand)
  ├── Apache Arrow dataframes (when RAPIDS active)
  └── ~82 GB available when llama3.3:70b loaded, ~124 GB when idle
```

### The Level 100 HITL Workflow
1. **Autonomous Hunt**: Scanner runs 24/7, GPU agent finds statistical anomalies
2. **The Breakpoint**: When EV breaches threshold (Sharpe > 2.5), agent halts
3. **The Tear Sheet**: Backtester compiles report with charts
4. **The Human Check**: KWW reviews on Telegram/dashboard
5. **Live Execution**: Approved trades fire via py-clob-client Builder API

---

## NemoClaw Stack (Session 34 — REBUILT)

| Component | Version | Status |
|-----------|---------|--------|
| NemoClaw CLI | v0.1.0 (latest source) | `~/.npm-global/bin/nemoclaw` |
| OpenShell CLI | **v0.0.19** | `~/.local/bin/openshell` (upgraded from v0.0.12) |
| OpenShell Gateway | **v0.0.19** | Docker `openshell-cluster-nemoclaw` |
| Host OpenClaw Gateway | **v2026.3.28** | Port 18789, owns Telegram, workspace at `~/.openclaw/workspace/` |
| Sandbox | `nemoclaw` | Ready, Landlock+seccomp+netns |
| Inference | ollama-local | llama3.3:70b via OpenShell routing |
| Policies | pypi, npm, telegram | + claude_code, clawhub, github, nvidia, openclaw |
| File sync | cron 5min | `~/sync-to-sandbox.sh` → `openshell sandbox upload` |
| `nemoclaw-telegram.service` | **DISABLED** | Was source of 409 conflicts |

**Key commands:**
```bash
nemoclaw nemoclaw status            # Check sandbox health
nemoclaw nemoclaw connect           # Connect to sandbox
nemoclaw status                     # Show sandboxes + services
openshell sandbox list -g nemoclaw  # List sandboxes
openshell inference get -g nemoclaw # Check inference route
systemctl --user status openclaw-gateway.service  # Host gateway
```

**DGX SSH recovery (after reboot):**
```bash
# If cloudflared is down:
sudo systemctl restart cloudflared

# If Ollama only on localhost (containers can't reach):
sudo mkdir -p /etc/systemd/system/ollama.service.d
echo -e '[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0"' | sudo tee /etc/systemd/system/ollama.service.d/override.conf
sudo systemctl daemon-reload && sudo systemctl restart ollama

# If OpenShell gateway is stopped:
openshell gateway start

# Restart scanner:
systemctl --user start polysignal-scanner.service
```

---

## Priority Execution Order

| # | Item | Effort | Impact | Status |
|---|------|--------|--------|--------|
| 1 | XGBoost GPU | 30 min | Medium | DONE |
| 2 | Retrain watcher | 15 min | High | DONE |
| 3 | Backtester | 2 hours | High | DONE |
| 4 | Disable swap | 5 min | Low | Pending (needs verification) |
| 5 | Install statsmodels | 5 min | Medium | Pending |
| 6 | NGC CLI + PyTorch container | 1 hour | High | Next session |
| 7 | TimescaleDB | 4 hours | Medium | When scale demands |
| 8 | NIM containers | 2 hours | Low | When needed |
| 9 | RAPIDS | 2 hours | Low | When scale demands |
