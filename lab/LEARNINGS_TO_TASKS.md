# Learnings → Tasks Pipeline
# Bridge between MoltBook/ClawHub intelligence and implementation.
# Loop writes discoveries here. Claude Code picks up actionable items.
# Updated: Session 30 (2026-03-25)

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

### Hybrid Prediction System + Overheating Fix (Session 30)
- **Source**: 137+ hour prediction drought — market expansion left most markets without biases
- **Implementation**: Hybrid prediction in `masterloop.py` — base rate path (markets WITH biases, gate >=0.55) + momentum fallback (markets WITHOUT biases, XGBoost gate). `from_observations()` in `base_rate_predictor.py` builds biases from consecutive price movements in test.db. `from_all_sources()` merges outcome + observation biases.
- **Result**: 5 biases (was 4), first prediction in 137+ hours, 1 prediction/cycle confirmed.
- **Bonus fix**: DGX overheating (73°C→50°C) — old gateway consuming 94% GPU for zero output. Stopped + unloaded Nemotron (91GB freed).
- **Key lessons**:
  1. DGX cron `git reset --hard` means SCP silently fails — always push to GitHub first
  2. Python __pycache__ survives `git reset --hard` — must delete after every deploy
  3. `scp -O` flag needed for reliable transfers (newer SSH uses SFTP by default)
  4. Loop's gateway was 100% waste — all requests timing out, 3 commits in 30 days

### Market Expansion + Whale Tracker + Learning Loop (Session 28)
- **Source**: KWW vision (Hub71 pitch), Polymarket has 1,500 markets not 13
- **Implementation**: `fetch_all_liquid_markets()` in bitcoin_signal.py (SCAN_ALL_MARKETS env var), `lab/whale_tracker.py` (volume spikes, spread collapses, extreme conviction), auto-evaluate in watchdog, staleness cooldown (6-cycle)
- **Result**: 137 liquid markets monitored (10x), whale detection wired at cycle 9, evolution hypotheses auto-verdict hourly, predictions flowing through cooldown. Meta-gate at 59%.
- **Key lesson**: Nemotron is batch-only — never use for interactive chat. OpenClaw v2026.2.12 is single-threaded — heartbeats block conversations.

### Self-Healing Pipeline (Session 26)
- **Source**: Loop's 2.5-day silence while predictor was broken
- **Implementation**: `lab/watchdog.py` (prediction drought, accuracy regression, scanner health, paper trade quality), `lab/feedback_loop.py` (per-market accuracy, auto-exclude, auto-retrain, EV), `lab/evolution_tracker.py` (hypothesis → measurement → verdict)
- **Result**: Closed the EVALUATE → LEARN → REFLECT loop. First evolution hypotheses recorded.

### Base Rate Gate Fix (Session 26)
- **Source**: Pipeline deadlock — XGBoost gate + bearish ban suppressed ALL base rate predictions for 2.5 days
- **Implementation**: Two-mode gate in prediction_node. Base rate uses confidence >= 0.60 (no XGBoost, no bearish ban). Old predictor keeps XGBoost + bearish ban.
- **Result**: 556108 Bearish (94% confidence) now passes gate. 1 prediction per cycle.

### Base Rate Predictor (Session 25)
- **Source**: Loop's pipeline audit + LOMO validation + per-market base rate analysis
- **Implementation**: `lab/base_rate_predictor.py` wired into prediction_node as primary predictor
- **Result**: 79.9% expected accuracy vs 17.4% production (toy momentum check killed)

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

### P0: Security Hardening (from research_gateway_security.md)
- **Source**: KWW Session 26 research
- **Findings**:
  1. Missing `sessions_spawn`/`sessions_send` deny — lateral movement risk
  2. Exec uses safeBins not allowlist mode — less granular
  3. No seccomp profile — io_uring/ptrace/bpf attacks possible
  4. No readOnlyRoot — container filesystem writable
- **Action needed**:
  - Add `sessions_spawn`, `sessions_send` to tool deny list
  - Switch exec to `allowlist` mode with explicit command patterns
  - Add seccomp profile blocking dangerous syscalls
  - Set `readOnlyRoot: true` in sandbox config
- **Effort**: Low-Medium (1h config changes by Claude Code)

### ~~P0: Model Routing / Cost Reduction~~ — IMPLEMENTED (Session 27)
- **Source**: KWW Session 26 research + today's self-assessment
- **Implementation**: Nemotron-3-Super-120B (86GB) downloaded. OpenClaw heartbeats → `ollama/nemotron-3-super:120b`. Direct chat → Opus 4.6. Cost: $460/mo → ~$30/mo.
- **Remaining**: TensorRT-LLM (optional), QLoRA fine-tuning (needs 1K+ samples)

### P1: Event-Driven Triggers (from research_openclaw_autonomy.md)
- **Source**: KWW Session 26 research, Felix/Eliason comparison
- **Findings**:
  - We're Level 2 (semi-autonomous), top agents are Level 3-4
  - Missing: self-initiated work, event-driven triggers, cross-agent coordination
  - Scanner already writes `.events.jsonl` — just need to WATCH it
  - Sentry→PR pattern could work for scanner errors → auto-fix
- **Action needed**:
  - CC: OpenClaw cron or inotify watch on `.events.jsonl` → trigger Loop
  - Loop: Generate own tasks from MoltBook intelligence (not just execute queue)
  - CC: Enable `sessions_spawn` for coding sub-agents (with audit)
- **Effort**: Medium-High (2-3h architecture change)

### P1: Voice/Phone Alert System (KWW request, 2026-03-17)
- **Source**: KWW direct request — wants phone calls for emergencies/HITL
- **Findings**: No existing ClawHub skill. Needs telephony integration.
- **Options**:
  - Twilio API (voice calls + SMS) — add to Squid allowlist
  - ElevenLabs TTS + Twilio = natural voice
  - Telegram voice messages as intermediate step
- **Action needed**:
  - Research Twilio pricing + API
  - Build minimal "call KWW" skill triggered by critical alerts
  - Wire into watchdog alerts
- **Effort**: Medium (2-3h for MVP)
