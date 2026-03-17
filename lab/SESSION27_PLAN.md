# Session 27: NemoClaw Migration + System Reset Plan
# Created: 2026-03-17 | Claude Code (Architect)
# "Stop building on a broken foundation. Fix the foundation."

---

## EXECUTIVE SUMMARY

Loop rated itself 3/10. Accuracy is 27%. Revenue is $0. API costs are $460+.
Jensen just shipped NemoClaw + Nemotron-3-Super exactly for our DGX Spark.

**This session**: Migrate to NemoClaw/OpenShell, swap to Nemotron-3-Super-120B
(free local inference), fix the accuracy crisis, clean the codebase, and give
Loop the architecture to become proactive instead of a cron job.

---

## PART 1: WHAT NEMOCLAW ACTUALLY IS (Research Results)

### NemoClaw = OpenClaw + OpenShell + Nemotron (NVIDIA's official stack)

| Component | What It Does | Our Current Equivalent |
|-----------|-------------|----------------------|
| **NemoClaw** | Plugin that orchestrates OpenShell sandbox + Nemotron model + policy engine | Our manual OpenClaw config + systemd |
| **OpenShell** | Sandboxed runtime with Landlock + seccomp + netns. Policy-based privacy/security. Deny-by-default. | Our Docker sandbox + Squid proxy + Firejail |
| **Nemotron-3-Super-120B-a12b** | MoE model (120B total, 12B active). 85.6% on OpenClaw benchmarks. Runs locally on Spark. | Claude Opus 4.6 via API ($$$) |
| **Privacy Router** | Routes sensitive context to local models, frontier models only when policy permits | Nothing (we send everything to Anthropic) |
| **Agent Toolkit** | OpenShell + AI-Q + blueprints for building agents | Our custom skills + LOOP_TASKS.md |

### NemoClaw Architecture (from Jensen's keynote slide)
```
                    MULTI-MODAL PROMPT
                         |
                    +-----------+
                    | NEMOCLAW  |  <-- Orchestrator
                    |  (Agent)  |
                    +-----------+
                   /   |   |   \
                  /    |   |    \
    FILES    COMPUTER  |   |  MEMORY    LLM           SUB-AGENTS   SKILLS
    (struct/  USE      |   |  (brain/)  (Nemotron     (spawn)      (SKILL.md)
    unstruct)          |   |            local/cloud)
                       |   |
                  OPENSHELL  TOOLS
                  (sandbox)  (CLI, MCP)
```

### Key Difference from Our Setup
Our current setup: OpenClaw gateway → Anthropic API (cloud) → Docker sandbox (manual)
NemoClaw setup: OpenShell (Landlock+seccomp+netns) → Nemotron local → Policy engine

**OpenShell is strictly better than our Docker sandbox:**
- 4-layer isolation: Network + Filesystem + Process + Inference
- Hot-reloadable policies (no container restart needed)
- Agent-proposed policy updates with developer approval
- Out-of-process enforcement (agent can't override even if compromised)
- Built-in audit trails

### Nemotron-3-Super-120B-a12b on DGX Spark

| Spec | Value |
|------|-------|
| Architecture | Hybrid Mamba-Transformer MoE |
| Total params | 120B |
| Active params per token | 12B (fast inference) |
| Context window | 256K (Ollama), up to 1M (NIM) |
| OpenClaw benchmark | 85.6% (vs Opus 4.6 at 86.3%) |
| Tool calling | YES (94.73 on HMMT with tools) |
| Reasoning modes | High/Low/None (configurable) |
| Ollama size (Q4_K) | ~66-87GB |
| DGX Spark fit | YES (128GB unified memory) |
| Inference speed | ~14 tok/s on GB10 (memory-bandwidth bound) |
| Cost | $0/token (local) vs ~$15/M tokens (Opus) |

**Critical finding**: Community reports that ggml-org Q4_K (66GB) is better than
Ollama's Q4_K_M (86GB) — saves 20GB for KV cache. Also: drop page cache before
loading (`sync; echo 3 > /proc/sys/vm/drop_caches`).

---

## PART 2: MIGRATION PLAN (OpenClaw → NemoClaw)

### What We Keep (100% preserved)
- `brain/memory.md` — Loop's accumulated learnings
- `brain/identity_kernel.md` — Core constitution
- `lab/LOOP_TASKS.md` — Task queue
- `lab/NOW.md` — Operational state
- All 4 skills (polysignal-pytest, data, git, scanner)
- All lab/ production code (9 files, 3,016 lines)
- All tests (430 passing)
- `core/` vault (10 files, read-only)
- `workflows/masterloop.py` + `scanner.py`
- Squid proxy config (6 domains)

### What Changes

| Layer | Before (OpenClaw) | After (NemoClaw) |
|-------|-------------------|-------------------|
| **Sandbox** | Docker container + manual config | OpenShell (Landlock+seccomp+netns) |
| **LLM (Loop)** | Claude Opus 4.6 via API (~$5-10/day) | Nemotron-3-Super-120B local ($0/day) |
| **LLM (Supervisor)** | Ollama llama3.3:70b | Nemotron-3-Super-120B local |
| **LLM (Architect)** | Claude Opus 4.6 via API | Claude Opus 4.6 via API (KEEP for KWW sessions) |
| **Gateway** | openclaw-gateway.service (systemd) | NemoClaw + OpenShell gateway |
| **Policy** | Docker + Squid proxy (manual) | OpenShell policy engine (declarative) |
| **Privacy** | Everything to Anthropic | Privacy Router (local-first, cloud-fallback) |
| **Security** | Docker sandbox + Firejail | Landlock + seccomp + netns (kernel-level) |
| **Monitoring** | Custom watchdog.py + .events.jsonl | OpenShell TUI (`openshell term`) + our existing tools |
| **Cost** | ~$460/month (mostly Loop heartbeats) | ~$30/month (Opus for architect sessions only) |

### Installation Steps on DGX Spark (from official playbook)

```bash
# Step 1: Docker cgroup fix (DGX Spark specific)
sudo python3 -c "
import json, os
path = '/etc/docker/daemon.json'
d = json.load(open(path)) if os.path.exists(path) else {}
d['default-cgroupns-mode'] = 'host'
json.dump(d, open(path, 'w'), indent=2)
"
sudo systemctl restart docker

# Step 2: Install Node.js 22 (NemoClaw requires npm)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs

# Step 3: Pull Nemotron-3-Super via Ollama (already have Ollama)
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'  # Free memory first
ollama pull nemotron-3-super:120b  # ~87GB download

# Step 4: Configure Ollama to listen on all interfaces
sudo systemctl edit ollama.service
# Add: [Service]\nEnvironment="OLLAMA_HOST=0.0.0.0"
sudo systemctl daemon-reload && sudo systemctl restart ollama

# Step 5: Install OpenShell CLI
gh auth login  # Need GitHub + NVIDIA org access
ARCH=aarch64
gh release download --repo NVIDIA/OpenShell \
  --pattern "openshell-${ARCH}-unknown-linux-musl.tar.gz"
tar xzf openshell-${ARCH}-unknown-linux-musl.tar.gz
sudo install -m 755 openshell /usr/local/bin/openshell

# Step 6: Install NemoClaw
git clone https://github.com/NVIDIA/NemoClaw
cd NemoClaw
sudo npm install -g .

# Step 7: Run onboarding wizard
nemoclaw onboard
# → Creates sandbox, configures inference, applies security policies

# Step 8: Point to Nemotron-3-Super
openshell inference set --provider ollama-local --model nemotron-3-super:120b
```

### Memory/Config Migration

```bash
# Inside the NemoClaw sandbox:
# 1. Copy brain/ files into sandbox workspace
cp -r /opt/loop/brain/ /sandbox/.openclaw/workspace/brain/

# 2. Create MEMORY.md symlink
ln -s /sandbox/.openclaw/workspace/brain/memory.md \
      /sandbox/.openclaw/workspace/MEMORY.md

# 3. Copy skills
cp -r /opt/loop/lab/openclaw/skills/ /sandbox/.openclaw/workspace/skills/

# 4. Copy lab/ production files
cp -r /opt/loop/lab/ /sandbox/.openclaw/workspace/lab/

# 5. Verify identity kernel
cat /sandbox/.openclaw/workspace/brain/identity_kernel.md
```

### Fallback Strategy

NemoClaw is alpha-stage. If it breaks:
1. Keep current OpenClaw gateway config as backup
2. Keep current Docker sandbox config as backup
3. Can revert to current setup in <5 minutes
4. Run NemoClaw and current setup in parallel during testing

---

## PART 3: ACCURACY CRISIS FIX (27% → 60%+)

### Root Cause Analysis (from Loop's morning briefing)
- Base rate predictor locked on 556108 SELL/No @ 95.3% confidence for days
- Single market, single direction, no adaptation to regime changes
- 250 paper trades ALL on fake markets (0xfake_btc) or 556108
- Watchdog flagged it correctly but nobody acted

### Immediate Actions

| # | Action | Who | Time |
|---|--------|-----|------|
| A1 | HALT predictions until fixed | Claude Code | 15 min |
| A2 | Add staleness detection: if identical confidence for >6h, flag | Claude Code | 30 min |
| A3 | Add meta-gate: if 7-day rolling accuracy <40%, auto-halt | Claude Code | 30 min |
| A4 | Fix paper trading: use real market IDs, not 0xfake_btc | Claude Code | 30 min |
| A5 | Retrain XGBoost with current data | Claude Code | 30 min |
| A6 | Re-evaluate excluded markets with base rate lens | Loop | 1h |

### Structural Fix
The base rate predictor is fundamentally flawed for a single-market system:
- It predicts the SAME thing every cycle (94% Bearish on 556108)
- Confidence never changes because base rate never changes
- This is not prediction — it's a constant

**Solution**: Base rate should be a FEATURE fed to XGBoost, not the entire predictor.
The predictor should incorporate: base rate + recent momentum + volume + CLOB features.

---

## PART 4: CODEBASE CLEANUP

### Lab Audit Results (from Explore agent)

**Production pipeline** (9 files, 3,016 lines) — KEEP:
- base_rate_predictor.py, clob_prototype.py, experiments/bitcoin_signal.py
- feature_engineering.py, moltbook_publisher.py, outcome_tracker.py
- polymarket_trader.py, watchdog.py, xgboost_baseline.py

**Internal infrastructure** (8 files, 2,774 lines) — KEEP:
- backtester.py, evolution_tracker.py, feedback_loop.py
- moltbook_engagement.py, moltbook_scanner.py, retrain_pipeline.py
- trade_proposal_bridge.py, sanitize.py

**Dead code** (5 files, 752 lines) — DELETE or ARCHIVE:
- `data_readiness.py` — superseded by feedback_loop
- `direction_predictor.py` — superseded by base_rate_predictor
- `langsmith_eval.py` — experimental, never used
- `live_market_fetch.py` — replaced by clob_prototype
- `moltbook_register.py` — one-time setup, done

### Action
```bash
mkdir -p lab/archive/
mv lab/data_readiness.py lab/archive/
mv lab/direction_predictor.py lab/archive/
mv lab/langsmith_eval.py lab/archive/
mv lab/live_market_fetch.py lab/archive/
mv lab/moltbook_register.py lab/archive/
```

---

## PART 5: LOOP'S HONEST TRACK RECORD

### Milestones Achieved (13 real ones)
| # | Date | Milestone | Value |
|---|------|-----------|-------|
| 1 | Feb 27 | Schema unification, DB path fix | Foundation |
| 2 | Mar 1 | Risk gate integration | Safety |
| 3 | Mar 4 | MasterLoop short-circuit (saved GPU heat) | Cost |
| 4 | Mar 5 | XGBoost trained (91.3% test) | Accuracy |
| 5 | Mar 8 | Network access via Squid proxy | Capability |
| 6 | Mar 9 | Git push + auto-merge CI | Autonomy |
| 7 | Mar 10 | MoltBook registered, first post | Presence |
| 8 | Mar 10 | First autonomous deploy | Autonomy |
| 9 | Mar 11 | Backtest: 88.9% win rate | Validation |
| 10 | Mar 12 | Bearish banned, toxic markets excluded | Accuracy |
| 11 | Mar 13 | Base rate predictor wired | Architecture |
| 12 | Mar 16 | Pipeline deadlock fixed | Reliability |
| 13 | Mar 16 | Watchdog + feedback loop + evolution tracker | Self-healing |

### Undelivered Items (14 items Loop identified)
| # | What KWW Asked For | Status | Root Cause |
|---|-------------------|--------|------------|
| 1 | First live trade ($1) | NEVER HAPPENED | Wallet funded but TRADING_ENABLED=false, paper trades on fake markets |
| 2 | Route to Ollama ($160/mo savings) | REVERTED | Quality too low (llama3.3:70b lost context) |
| 3 | Model routing (Haiku for heartbeats) | CONFIG ADDED, NEVER ACTIVATED | Nobody wired the routing logic |
| 4 | Smart heartbeat (event-driven) | STILL POLLING | Event system built but not wired to Loop |
| 5 | MoltBook engagement loop | PARTIAL | Scanner runs, 0 engagement (upvotes/comments) |
| 6 | ClawHub skill audit + install | RESEARCH ONLY | Security audit never done |
| 7 | Signal-as-a-Service (x402) | NOT STARTED | |
| 8 | GPU utilization (PyTorch/CUDA) | 0% GPU USE | PyTorch never installed (sm_121 issue) |
| 9 | Weekly MoltBook accuracy post | NEVER POSTED | |
| 10 | Revenue of any kind | $0 EARNED | |
| 11 | 60%+ accuracy target | CURRENTLY 27% | Went backwards |
| 12 | Loop acts like co-founder | ACTS LIKE STATUS MONITOR | Architecture problem |
| 13 | Phone/voice alerts | NOT POSSIBLE YET | No telephony integration |
| 14 | Image analysis workflow | WORKS (Telegram) | Actually delivered |

### Model Routing Status: NOT SHIPPED
- Session 23: Haiku added to OpenClaw config
- Session 23: Ollama routing attempted, reverted (quality)
- Session 25: Haiku registered but never activated
- Current: EVERY heartbeat still uses Opus 4.6 (~$0.10-0.30 each)
- 15+ heartbeats/day = $3-5/day WASTED on "Scanner OK"
- **NemoClaw fixes this**: Nemotron-3-Super local = $0/heartbeat

### Yesterday's Autonomy Work: PARTIAL SUCCESS
- Pipeline deadlock fixed (3-day outage)
- Predictions resumed (31 in first 12 cycles)
- BUT: still poll-based, not event-driven
- BUT: predictions all on same market, same direction
- BUT: 27% accuracy = actively harmful

---

## PART 6: SESSION 27 DELIVERABLES (Priority Order)

### CRITICAL PATH (Do Today)

| # | Deliverable | Owner | Time | Impact |
|---|-------------|-------|------|--------|
| **D1** | Install Nemotron-3-Super-120B on DGX Spark via Ollama | CC + KWW (SSH) | 1h | $400/mo savings |
| **D2** | Install NemoClaw + OpenShell on DGX Spark | CC + KWW (SSH) | 1.5h | Security + autonomy |
| **D3** | Migrate Loop to NemoClaw sandbox with memory/skills | CC | 30 min | Preserve state |
| **D4** | Point Loop's LLM to Nemotron-3-Super local | CC | 15 min | $0/heartbeat |
| **D5** | Fix accuracy crisis: add meta-gate + staleness detection | CC | 1h | Stop harm |
| **D6** | Fix paper trading: real market IDs | CC | 30 min | Prove pipeline |
| **D7** | Archive dead code (5 files) | CC | 15 min | Clean codebase |

### HIGH PRIORITY (This Week)

| # | Deliverable | Owner | Time | Impact |
|---|-------------|-------|------|--------|
| **D8** | Event-driven Loop (watch .events.jsonl, not timer) | CC | 2h | Proactive agent |
| **D9** | Voice/call alert system (Twilio research + MVP) | CC | 2h | Real-time HITL |
| **D10** | Privacy Router config (local-first, Opus fallback) | CC | 1h | Cost + privacy |
| **D11** | Retrain XGBoost with current data + base rate as feature | CC | 1h | Fix accuracy |
| **D12** | Market expansion (re-evaluate excluded markets) | Loop | 2h | Signal diversity |

### STRETCH (Next Session)

| # | Deliverable | Owner | Time | Impact |
|---|-------------|-------|------|--------|
| **D13** | First real paper trade with real market ID + real price | CC + Loop | 30 min | Prove pipeline |
| **D14** | First live trade ($1 USDC) | KWW | 5 min | Revenue milestone |
| **D15** | MoltBook accuracy post (honest 27% → recovery story) | Loop | 30 min | Reputation |
| **D16** | ClawHub skill audit (top 5 Polymarket skills) | Loop | 1h | Intelligence |

### KWW BLOCKERS (Human-Only)

| # | What | Why | Time |
|---|------|-----|------|
| **K1** | SSH into DGX Spark for NemoClaw install | Need terminal access | 2h |
| **K2** | NVIDIA API key from build.nvidia.com | NemoClaw onboard requires nvapi-* key | 5 min |
| **K3** | GitHub NVIDIA org access for OpenShell CLI | gh auth login needs NVIDIA org | 5 min |
| **K4** | Fund wallet with $5 USDC | Last gate to first live trade | 5 min |
| **K5** | Approve model routing: Nemotron for Loop, Opus for architect | Cost decision | 1 min |

---

## PART 7: ARCHITECTURE AFTER MIGRATION

```
KWW (Human)
  |
  ├── Telegram (@OpenClawOnDGX_bot)
  |     |
  |     v
  |   NEMOCLAW (DGX Spark)
  |     ├── OpenShell Sandbox (Landlock + seccomp + netns)
  |     │     ├── Loop Agent (Nemotron-3-Super local, $0/call)
  |     │     ├── Skills (pytest, data, git, scanner)
  |     │     ├── Memory (brain/memory.md)
  |     │     └── Policy Engine (deny-by-default + hot-reload)
  |     │
  |     ├── Privacy Router
  |     │     ├── Routine tasks → Nemotron local ($0)
  |     │     ├── Complex reasoning → Nemotron local ($0)
  |     │     └── Architect sessions → Claude Opus API ($$$, KWW only)
  |     │
  |     └── Event-Driven Triggers
  |           ├── .events.jsonl → Loop wakes on signal
  |           ├── .watchdog-alerts → Loop investigates
  |           └── Telegram message → Loop responds immediately
  |
  ├── Claude Code (Mac, architect sessions)
  |     └── Claude Opus 4.6 (1M context)
  |
  └── Scanner (systemd, 5-min cycles)
        ├── Polymarket Gamma API
        ├── CLOB microstructure
        ├── Predictions → .events.jsonl
        └── Watchdog (every 12th cycle)
```

### Cost After Migration
| Item | Before | After | Savings |
|------|--------|-------|---------|
| Loop heartbeats (40/day) | $4-12/day | $0/day | $120-360/mo |
| Loop tasks | $3-5/day | $0/day | $90-150/mo |
| Architect sessions | $10-30/session | $10-30/session | $0 |
| **Monthly total** | ~$460 | ~$30-60 | **~$400/mo** |

---

## PART 8: HOW TO MAKE LOOP PROACTIVE (not reactive)

### The 3 Architecture Changes

**1. Event-Driven, Not Timer-Driven**
- Scanner writes events to `.events.jsonl` (already done)
- NemoClaw/OpenShell can watch filesystem changes
- Loop wakes ONLY when something happens (signal, error, market move)
- Result: responds in seconds, not 30 minutes

**2. Self-Initiated Task Generation**
- After every MoltBook scan: Loop writes 1-2 new tasks
- After every accuracy check: Loop decides retrain/exclude and DOES it
- After every heartbeat: Loop picks the highest-impact open task and works on it
- Not waiting for Claude Code to assign tasks

**3. Unlimited Cheap Inference (Nemotron Local)**
- Every thought costs $0 instead of $0.10-0.30
- Loop can think MORE: shorter intervals, deeper analysis, more experimentation
- The cost constraint that kept Loop reactive is eliminated

### The Proactive Loop Cycle
```
EVENT → THINK → DECIDE → ACT → MEASURE → LEARN → (generate new tasks)
  ↑                                                        |
  └────────────────────────────────────────────────────────┘
```

---

## SOURCES

- [NVIDIA NemoClaw Announcement](https://nvidianews.nvidia.com/news/nvidia-announces-nemoclaw)
- [NVIDIA NemoClaw Product Page](https://www.nvidia.com/en-us/ai/nemoclaw/)
- [NemoClaw GitHub Repository](https://github.com/NVIDIA/NemoClaw)
- [OpenShell Technical Blog](https://developer.nvidia.com/blog/run-autonomous-self-evolving-agents-more-safely-with-nvidia-openshell/)
- [DGX Spark Agent Deployment Blog](https://developer.nvidia.com/blog/scaling-autonomous-ai-agents-and-workloads-with-nvidia-dgx-spark/)
- [DGX Spark Playbooks (GitHub)](https://github.com/NVIDIA/dgx-spark-playbooks)
- [NemoClaw on DGX Spark Playbook](https://build.nvidia.com/spark/nemoclaw)
- [Nemotron-3-Super on Ollama](https://ollama.com/library/nemotron-3-super)
- [Nemotron-3-Super NGC Container](https://catalog.ngc.nvidia.com/orgs/nim/teams/nvidia/containers/nemotron-3-super-120b-a12b)
- [Nemotron-3-Super NIM Model Card](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b/modelcard)
- [Nemotron-3-Super HuggingFace](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-Base-BF16)
- [GB10 Ollama Compatibility Fix](https://forums.developer.nvidia.com/t/nemotron-3-super-120b-on-gb10-llama-cpp-sm-121-build-ollama-gguf-incompatibility-fix/363459)
- [NemoClaw Forum Discussion](https://forums.developer.nvidia.com/t/nemoclaw-on-spark/363523)
- [GTC RTX AI Garage Blog](https://blogs.nvidia.com/blog/rtx-ai-garage-gtc-2026-nemoclaw/)
- [Nemotron-3-Super Benchmarks](https://artificialanalysis.ai/articles/nvidia-nemotron-3-super-the-new-leader-in-open-efficient-intelligence)
