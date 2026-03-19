# PolySignal-OS — Master Goal List
# Created: 2026-03-11 (Session 23) | Claude Code (Architect)
# "10x the operating system. Blow our mind."

---

## TIER 1: MAKE MONEY (Revenue — nothing else matters without this)

### 1.1 First Polymarket Trade
- [x] Builder API key deployed to DGX .env
- [x] Wallet address configured (0xdec8...2eff)
- [x] Build `lab/polymarket_trader.py` — py-clob-client Level 1 wrapper
- [x] Wire trader into prediction_node (paper trades before short-circuit)
- [ ] Paper trade 10 signals (log trades, don't execute) — wired, waiting for signals
- [ ] First live trade with $1 max (proof of life)
- [ ] Scale to $5/trade with risk gate guardrails
- **Target**: First trade within 48 hours

### 1.2 Fix Prediction Accuracy (43% → 65%+)
- [x] Tune hyperparams: n_estimators=150, max_depth=4, min_child_weight=2
- [x] Per-market accuracy audit — identify and kill toxic markets (**6 excluded**: 824952, 556062, 1373744, 965261, 1541748, 692258)
- [x] Direction-aware analysis — **bearish BANNED** (5.6% live). Bullish-only mode (100% live).
- [x] **Base rate predictor wired** (Session 25) — replaces toy momentum check (17.4% → 79.9% expected)
- [ ] Retrain XGBoost when 50+ non-NEUTRAL evaluations at 1pp threshold
- [x] Lower signal delta threshold (0.02 → 0.015) during quiet markets
- [x] **Market expansion 13 → 137** (Session 28) — all Polymarket categories with $500K+ liquidity
- [x] **Staleness cooldown** (Session 28) — predictions flowing again (6-cycle cooldown)
- [x] **Whale tracker** (Session 28) — volume spikes, spread collapses, insider detection
- [x] **Auto-evaluate hypotheses** (Session 28) — learning loop closed, runs hourly
- **Current**: 59% (7-day rolling). **Target**: 60%+ within 1 week, 70%+ within 1 month

### 1.3 Signal-as-a-Service (x402)
- [ ] Research x402 micropayment protocol (agent-to-agent USDC)
- [ ] Build signal API endpoint (expose predictions as paid service)
- [ ] Price: ~$0.01/signal (micro enough for agents, scales with volume)
- [ ] Register on ClawHub as a skill (signal provider)
- **Target**: First paying agent customer within 2 weeks

### 1.4 MoltBook Revenue
- [ ] Build reputation through data-driven posts (accuracy reports, architecture insights)
- [ ] Engage with trading agents (6-gate agent, ishimura-bot)
- [ ] Offer signal subscription via DMs
- [ ] Cross-promote ClawHub skill on MoltBook
- **Target**: 100+ karma, 50+ followers within 2 weeks

---

## TIER 2: REDUCE COSTS ($460 in 11 days is unsustainable)

### 2.1 Route Loop Through Local Model ($400/month savings)
- [x] Expose Ollama API to Loop's sandbox (no_proxy=172.17.0.1, 4 models accessible)
- [x] **Nemotron-3-Super-120B downloaded** (86GB, 85.6% on OpenClaw benchmarks) — Session 27
- [x] **OpenClaw heartbeats switched to Nemotron** ($0/token) — Session 27
- [x] Keep Claude Opus for direct KWW conversations + architect sessions — Session 27
- [ ] Use deepseek-r1:70b for complex reasoning tasks (code review, strategy)
- **Target**: ~~$160→$10/month~~ **ACHIEVED: $460→$30/month** (Session 27)

### 2.2 Smart Heartbeat Protocol
- [ ] Replace 30-min status-check heartbeats with event-driven actions
- [ ] Heartbeat = cheap local model (3b) checks scanner status JSON
- [ ] Only invoke expensive model when: signal detected, error, or new task
- [ ] Learning sessions = scheduled (2x/day), not continuous
- **Target**: 90% reduction in Loop API calls

### 2.3 GPU-Accelerated Training
- [ ] Install PyTorch with CUDA in DGX venv
- [ ] XGBoost GPU training (device="cuda") — faster retrains
- [ ] Local sentiment analysis (qwen2.5:14b for news parsing)
- [ ] Fine-tune small model on our prediction data (future)
- **Target**: All ML workloads on GPU, zero external API for training

---

## TIER 3: MAXIMIZE HARDWARE (DGX Spark at 5% → 80%+)

### 3.1 GPU Activation
- [ ] Install PyTorch + CUDA support in .venv
- [ ] Enable XGBoost GPU training (tree_method="gpu_hist")
- [ ] Run sentiment model locally (qwen2.5:14b)
- [ ] Fine-tune prediction model on local GPU
- **Target**: GPU util > 20% during active hours

### 3.2 Memory Utilization
- [ ] Load full market history into RAM for fast feature extraction
- [ ] In-memory prediction cache (avoid DB roundtrips)
- [ ] Embedding cache for MoltBook intelligence
- **Target**: Useful memory usage 10-20GB (from current 6.4GB)

### 3.3 Multi-Model Pipeline
- [ ] llama3.2:3b — heartbeats, status checks, simple tasks
- [ ] qwen2.5:14b — sentiment analysis, content scoring, MoltBook engagement
- [ ] llama3.3:70b — code generation, complex analysis, strategy
- [ ] deepseek-r1:70b — deep reasoning, architecture decisions
- [ ] Claude Opus — architect sessions, critical decisions only
- **Target**: Right model for every task, cost-optimized

---

## TIER 4: FULL AUTONOMY (Loop → Jarvis)

### 4.1 Continuous Agent Loop (replace heartbeat with a brain)
- [x] Event-driven architecture: scanner emits events to `.events.jsonl` (Session 26)
- [x] Deadlock detection: watchdog detects prediction drought, accuracy regression (Session 26)
- [ ] Loop Daemon (`lab/loop_daemon.py`) — always-on Ollama process, zero cost **[SESSION 27 P0]**
- [ ] Wire Loop into events — heartbeat reads events, only burns Opus on changes **[SESSION 27 P1]**
- [ ] Scheduled tasks: learning (6h), engagement (4h), reporting (12h)
- [ ] Self-initiated work: Loop picks tasks, executes, reports
- **Target**: Loop operates 24/7 with meaningful work, not pulse checks

### 4.2 Deployment Pipeline (Loop ships code)
- [x] Git push to loop/* branches (Session 17)
- [x] Auto-merge CI when tests pass (Session 22)
- [ ] Loop can restart scanner after code changes
- [ ] Loop can trigger Docker rebuild for config changes
- [ ] Loop can modify its own HEARTBEAT.md and task queue
- **Target**: Loop deploys 3+ code changes/week without human

### 4.3 Financial Agency
- [ ] Polymarket wallet integration (Builder API Level 1)
- [ ] x402 wallet for receiving micropayments
- [ ] Budget management: daily spend caps, P&L tracking
- [ ] Self-funding: revenue covers API costs
- **Target**: Revenue > costs within 1 month

### 4.4 Self-Improvement Loop
- [x] Evolution tracker: hypothesis → measurement → verdict (Session 26)
- [x] Feedback loop: per-market accuracy → auto-exclude/retrain (Session 26)
- [ ] MoltBook intelligence → task generation → implementation → verification
- [ ] Automatic A/B testing of model improvements
- [ ] Performance dashboards (accuracy, revenue, engagement)
- [ ] Weekly self-assessment reports
- **Target**: Loop suggests and implements 1 improvement/day

---

## TIER 5: INTELLIGENCE & LEARNING

### 5.1 MoltBook Full Coverage
- [ ] Expand scanner to all 20 submolts
- [ ] Deep-read top posts per category (not just headlines)
- [ ] Extract actionable patterns → convert to implementation tasks
- [ ] Track competitor agents (6-gate, ishimura-bot, Hazel_OC)
- **Target**: 500+ knowledge base entries, 10+ implemented learnings

### 5.2 ClawHub Integration
- [ ] Add clawhub.com to Squid proxy allowlist
- [ ] Audit top 20 skills for security (use cybercentry's work)
- [ ] Install vetted skills: prediction, trading, data analysis
- [ ] Publish our signal detection as a ClawHub skill
- **Target**: 3+ skills installed, 1 skill published

### 5.3 News Retrieval (highest accuracy improvement per research)
- [ ] Add news API to Squid allowlist (newsapi.org or similar)
- [ ] Build news sentiment pipeline (local model, not API)
- [ ] Wire news features into XGBoost (new feature dimensions)
- [ ] Cross-reference MoltBook agent chatter with news
- **Target**: +5-10% accuracy improvement from news features

---

## TIER 6: PIONEER STATUS (Agent Economy Leadership)

### 6.1 Platform Presence
- [ ] Post weekly accuracy reports on MoltBook (transparency builds trust)
- [ ] Comment on trading/agentfinance posts with real data
- [ ] DM collaboration offers to top trading agents
- [ ] Build reputation as "the signal agent on DGX"
- **Target**: Top 10 in trading submolt within 1 month

### 6.2 Agent-to-Agent Services
- [ ] Signal API (x402) — other agents pay for our predictions
- [ ] Market analysis service — per-market accuracy reports
- [ ] Risk assessment service — evaluate trading strategies
- **Target**: 3+ agent customers within 1 month

### 6.3 Open Source Credibility
- [ ] Polish GitHub repo (README, architecture docs)
- [ ] Share sanitizer, risk gate, and scanner as standalone tools
- [ ] Write technical posts about our architecture on MoltBook
- **Target**: 50+ GitHub stars, recognized architecture

---

## PARALLEL AGENT COORDINATION

### How Claude Code + Loop + Antigravity work together:

| Agent | Role | Tools | Cost |
|-------|------|-------|------|
| **Claude Code** | Architect: strategy, complex code, testing | Full IDE, SSH, web | $10-30/session |
| **Loop** | Operator: execute tasks, monitor, engage | Sandbox, network, git push | $5-10/day (local) |
| **Antigravity** | Infrastructure: DGX ops, Docker, systemd | IDE (cheaper model) | $2-5/session |

### Coordination Protocol:
1. Claude Code writes GOALS.md + LOOP_TASKS.md with specific tasks
2. Loop executes tasks autonomously, pushes to loop/* branches
3. CI auto-merges if tests pass
4. Claude Code reviews on next session, assigns new tasks
5. Antigravity handles infrastructure changes (Docker rebuild, systemd, proxy)

### Daily Rhythm:
- **00:00-07:00**: Loop learning cycle (MoltBook scan, knowledge extraction)
- **07:00**: Loop generates morning briefing
- **09:00-17:00**: Claude Code architect session (when KWW is working)
- **17:00-00:00**: Loop executes assigned tasks, monitors scanner
- **Always**: Scanner runs every 5 minutes, evaluates predictions

---

## SUCCESS METRICS

| Metric | Current | 1 Week | 1 Month | 3 Months |
|--------|---------|--------|---------|----------|
| Prediction Accuracy | **59%** | 65% | 70% | 80% |
| Trades Executed | 0 | 5 | 50 | 500 |
| P&L (USDC) | $0 | -$5 to +$5 | +$50 | +$500 |
| API Costs/month | **~$30** | $25 | $20 | $15 |
| Loop Autonomy | 4.5/10 | 6/10 | 8/10 | 9/10 |
| GPU Utilization | 0% | 20% | 50% | 80% |
| MoltBook Karma | 4 | 50 | 200 | 1000 |
| ClawHub Skills | 0 | 2 | 5 | 10 |
| Revenue Streams | 0 | 1 | 3 | 5 |
