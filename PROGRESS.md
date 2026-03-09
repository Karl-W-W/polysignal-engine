# PolySignal-OS — Current System State
# Last updated: 2026-03-09 23:30 CET | Session 21 (closing)
# Session history: See HISTORY.md

---

## System Overview

PolySignal-OS is an AI-native prediction market intelligence system. It scans Polymarket via the Gamma API, detects signals through a 7-node MasterLoop (LangGraph), publishes to MoltBook, and writes cycle learnings to memory. Deployed on NVIDIA DGX Spark (Munich), frontend on Vercel.

**Pipeline (complete, risk-gated, publishing, learning):**
```
Polymarket → PERCEPTION → PREDICTION → DRAFT → REVIEW → RISK_GATE → COMMIT → MoltBook → Memory
```

**Three-agent workflow:**
- **Claude Code** — architect, strategy, complex implementations, testing
- **Loop** (OpenClaw sandbox / Telegram) — autonomous developer, code reviews, DGX-local tasks
- **Antigravity** (IDE agent) — DGX ops, Docker rebuilds, file syncing (cheaper per prompt)
- **KWW** — Vault authorizer, human-only tasks, strategic decisions

---

## Infrastructure Status

| Component | Status | Details |
|-----------|--------|---------|
| DGX Spark | UP | Munich, Blackwell GPU, `llama3.3:70b` on Ollama |
| Docker Backend | UP | Flask :5000, Uvicorn :8000, rebuilt with risk gate |
| OpenClaw Sandbox | UP | Docker :9001, 12 bind mounts, Python 3.12.3, 3 skills, 20 safeBins |
| OpenClaw Gateway | UP | systemd, Claude Opus 4.6, heartbeat 30m |
| Telegram Bot | UP | `@OpenClawOnDGX_bot`, allowlist: [1822532651] |
| Frontend | LIVE | `polysignal-os.vercel.app` (Vercel) |
| Cloudflare Tunnel | UP | DGX → polysignal.app |
| LangSmith | ENABLED | EU endpoint, `LANGCHAIN_TRACING_V2=true` |
| GitHub | SYNCED | Mac current, DGX cron: `git reset --hard` (respects .gitignore) |
| Tests | 275/275 PASS | Mac (6.2s) — +15 new Sessions 19-21 |
| Scanner | RUNNING | Gate FIRING + CLOB refresh (15 markets/cycle). 824952 excluded. Neutral suppressed. |
| DGX Thermal | OK 28°C | Stable — short-circuit eliminated LLM heat spikes |
| Rogue Service | KILLED | `polysignal.service` stopped + disabled (was crash-looping 461K times) |
| Outcome Tracker | FIXED | evaluate_outcomes() moved after market fetch — was passing empty obs (Session 14) |
| Risk Gate | PROMOTED | `core/risk_integration.py` — review → risk_gate → commit |
| MoltBook Publisher | WIRED | Non-blocking in commit_node (dry-run until JWT) |
| Learning Loop | WIRED | write_memory() in commit_node — brain/memory.md gitignored (Session 11 fix) |
| Loop Autonomy | **FULL** | 4 skills, network, GPU, data/ write, scanner restart, git push, retrain trigger |
| Data Readiness | READY | `lab/data_readiness.py` — 134 labeled, 131 evaluated (threshold: 50) |
| Feature Eng. | READY | `lab/feature_engineering.py` — 15 features (10 price + 5 CLOB), temporal safety (`before` param) |
| XGBoost Baseline | **WIRED + FIRING** | 91.3% test. Gate active. xgb_p_correct persisted. Temporal train/test split. |
| Retrain Pipeline | BUILT | `lab/retrain_pipeline.py` — trigger file + systemd handler. Tested: 90% on filtered 48 samples. Rollback policy active. |
| CLOB Features | **LIVE** | `lab/clob_prototype.py` — 15 markets, bid/ask/spread/volume/liquidity refreshed per cycle. Wired into feature_engineering.py. |
| Per-Market Accuracy | BUILT | `get_per_market_accuracy()` — breakdown by market_id |
| Feature Pruning | DONE | 9 dead features removed, 10 active features in trained model |
| Ecosystem Research | DONE | `lab/ecosystem_research.md` — py-clob-client, PolyClaw, arxiv, strategies |
| Loop Task Sync | FIXED | `lab/LOOP_TASKS.md` — bypasses Docker inode caching on individual file bind mounts |
| Loop Reviews | DONE | 4/4 tasks completed — XGBoost review, market analysis, masterloop review, PolyClaw assessment |
| Dead Code Audit | CLEAN | No dead code found — `lab/dead_code_audit.md` (Session 14) |
| Oracle Research | DONE | `lab/oracle_research.md` — py-clob-client, Polymarket/agents documented |
| README | DONE | `README.md` — project overview for GitHub landing page |
| Telegram Dedup | VAULT | `core/notifications.py` — 1hr cooldown on identical alerts (Session 13) |

## Vault Inventory (`/opt/loop/core/` — 10 files)

| File | Purpose |
|------|---------|
| `perceive.py` | Polymarket Gamma API scanner |
| `predict.py` | Rule-based momentum detection (MVP — see roadmap) |
| `supervisor.py` | NVIDIA NIM + HMAC audit (fast/slow path, `strict=False` JSON — Session 11) |
| `bridge.py` | OpenClaw LangChain tool wrapper |
| `api.py` | Flask REST API (status, stats, narrative, SSE) |
| `notifications.py` | Telegram alert dispatcher |
| `openclaw_api.py` | Firejail sandbox executor |
| `signal_model.py` | Canonical Signal schema (Pydantic V2) |
| `risk.py` | Risk gate ($10 max, 75% confidence, $50 daily cap, kill switch) |
| `risk_integration.py` | Risk gate node for MasterLoop (promoted from lab/ Session 9) |

## MasterLoop Graph (7 nodes + inline publish + learn)

```
perception → prediction → draft → review → risk_gate → [approved] → wait_approval → commit → END
                                              ↓                            │
                                        [RISK_BLOCKED] → END              ├── MoltBook publish (inline)
                                                                          └── write_memory() (inline)
```

---

## Honest Architecture Assessment

| Component | What It Does | What It Should Do | Gap |
|-----------|-------------|-------------------|-----|
| **Perception** | Scans Polymarket Gamma API, detects 5pp moves | Same + multi-source | Minimal |
| **Prediction** | Rule-based + XGBoost confidence gate (Session 15) | ML direction predictor (XGBoost → transformer) | Gate LIVE — suppresses P(correct)<0.5. Rule-based still sets direction. |
| **Draft** | Ollama LLM generates shell command from signal | Same | OK |
| **Review** | HMAC audit + supervisor approval | Same | OK |
| **Risk Gate** | $10 max, 75% confidence, $50 daily cap | Same | OK |
| **Wait Approval** | `human_approved = True` (hardcoded) | Telegram YES/NO buttons | **Stub** |
| **Commit** | Execute via OpenClaw sandbox | Same | OK |
| **Publish** | MoltBook dry-run (no JWT yet) | Live posts (write-only) | Human blocker (JWT) |
| **MoltBook Read** | NOT BUILT | Double-layer isolation required | **BLOCKED — see threat model** |
| **Learn** | write_memory() + outcome_tracker → labeled data | Feedback loop with accuracy tracking | OK |
| **Scheduler** | `polysignal-scanner.service` (5min, active hours) | Same | OK |

---

## Roadmap

### Phase 1: CLOSE THE LOOP (Session 9) — COMPLETE
- [x] MoltBook publisher wired into commit_node
- [x] write_memory() wired into commit_node (learning loop)
- [x] Dead files deleted (-1,230 lines)
- [x] MoltBook implementations reconciled
- [x] risk_integration.py promoted to core/
- [x] 140/140 tests

### Phase 1.5: DATA PIPELINE (Session 10) — COMPLETE
- [x] Continuous scanner deployed (Antigravity — systemd service, 5min interval)
- [x] Outcome tracker built (Claude Code — record, evaluate, accuracy summary)
- [x] Outcome tracking wired into MasterLoop (perception evaluates, prediction records, memory includes accuracy)
- [x] Sanitize tests ported (23 tests for MoltBook post sanitizer)
- [x] 190/190 tests

### Phase 1.75: FIX DATA PIPELINE (Session 11) — COMPLETE
- [x] Fix commit_node: detect bridge error strings as FAILED (was masking failures as SUCCESS)
- [x] Fix prediction_node: signal-enhanced predictions (rule-based was 100% Neutral without DB)
- [x] Fix supervisor JSON: `strict=False` for Ollama control characters (Vault auth)
- [x] Fix .gitignore: protect brain/memory.md from DGX cron wipe
- [x] Fix DB_PATH: point to actual DB at `/opt/loop/data/test.db` (Antigravity)
- [x] Fix DGX cron: `git reset --hard` instead of nuclear `git checkout -- .` (Antigravity)
- [x] Feature engineering pipeline: 18 features, labeled dataset builder (Loop)
- [x] 217/217 tests

### Phase 1.8: FIX SIGNAL DETECTION (Session 12) — COMPLETE
- [x] Fix signal detection: rolling time windows (15m/1h/4h) instead of consecutive-scan comparison
- [x] Root cause: prediction markets barely move between 5-min scans (0pp delta), but move 2-7pp over hours
- [x] First real prediction recorded: Bearish conf=0.60 for market 556108 at 16:59 CET
- [x] Risk gate correctly blocking (TRADING_ENABLED=false) — pipeline working end-to-end

### Phase 1.9: LOOP EMPOWERMENT + ML PIPELINE (Session 12-13) — COMPLETE
- [x] Sandbox image rebuilt with Python 3.12.3 from source — Loop can run pytest (Session 12)
- [x] data/ and brain/ bind mounts added to openclaw.json (Session 12)
- [x] Loop verified 241/241 tests from sandbox (Session 12-13)
- [x] Loop completed 3 code reviews: signal detection, feature engineering, xgboost baseline
- [x] XGBoost training pipeline — `lab/xgboost_baseline.py`, 24 tests (Claude Code, Session 13)
- [x] Telegram notification dedup — 1hr cooldown on identical alerts (Vault fix, Session 13)
- [x] cycle_number wired from scanner into masterloop (bug found by Loop audit, Session 13)
- [x] ML deps (xgboost, scikit-learn) added to requirements.txt + installed on DGX
- [x] 241/241 tests passing on both Mac and DGX

### Phase 1.95: SILENCE WASTE + EMPOWER AGENTS (Session 14) — COMPLETE
- [x] MasterLoop short-circuit: skip draft/review/risk_gate when TRADING_ENABLED=false
- [x] Saves ~288 LLM calls/day + eliminates Telegram spam from blocked trades
- [x] Loop empowerment: 3 skills (pytest, data, git), expanded safeBins (+6 binaries)
- [x] OpenClaw gateway restarted with new config
- [x] TASKS.md rewritten with achievable, skill-backed tasks
- [x] Oracle research: existing Polymarket agents documented (polyclaw, py-clob-client)
- [x] CRITICAL BUG FIX: evaluate_outcomes() was called before market fetch (empty observations → 0 evaluations)
- [x] data_readiness.py built with 14 tests (Loop failed overnight, Claude Code delivered)
- [x] 256/256 tests passing

### Phase 2: REAL PREDICTION (in progress — XGBoost wired as confidence gate)
Replace rule-based predictor with ML. The DGX has a Blackwell GPU sitting idle.
- [x] Feature engineering from observations table — `lab/feature_engineering.py` (Loop, Session 11)
- [x] XGBoost baseline built — `lab/xgboost_baseline.py` with train/predict/batch (Claude Code, Session 13)
- [x] Accumulate 50+ labeled predictions — 254 total, 134 evaluated (Session 15)
- [x] Train XGBoost — **91.3% test, 85.5% CV** on pruned 10 features (Claude Code, Session 15)
- [x] Accuracy forensics — per-market, per-horizon, per-hypothesis breakdown (Session 15)
- [x] Ecosystem research — py-clob-client, PolyClaw, arxiv, trading strategies (Session 15)
- [x] Wire XGBoost as confidence gate in prediction_node — suppresses P(correct)<0.5 (Session 15)
- [x] Drop 4h horizon — removed from both time_horizon.py AND bitcoin_signal.py WINDOWS (Session 15)
- [x] Feature pruning — 9 dead features removed, 10 active features (Session 15)
- [x] Integration tests — 3 tests for XGBoost gate (suppress, pass, fallback) (Session 15)
- [x] Loop review of XGBoost training results — NO DATA LEAKAGE confirmed (Loop, Session 15)
- [x] Loop per-market analysis — market 824952 is 38.4%, 556108 is 88.9% (Loop, Session 15)
- [x] Loop masterloop review — gate, short-circuit, imports all verified correct (Loop, Session 15)
- [x] Loop PolyClaw assessment — verdict: SKIP, too many credential vectors (Loop, Session 15)
- [x] Docker bind mount fix — lab/LOOP_TASKS.md, first task sync since Session 12 (Claude Code, Session 15)
- [x] Exclude market 824952 — EXCLUDED_MARKETS env var in bitcoin_signal.py (Session 16)
- [x] Fix xgb_p_correct persistence — PredictionRecord now stores gate score (Session 19)
- [x] Post-gate accuracy split — get_gated_accuracy() distinguishes pre/post-gate (Session 19)
- [x] Add `before` parameter to `get_market_history()` — temporal safety (Loop, Session 21)
- [x] Retrain pipeline built — automated train/compare/replace with rollback (Claude Code, Session 20)
- [x] CLOB microstructure features — 15 markets, 5 new dimensions, wired into pipeline (Loop+Claude Code, Session 21)
- [x] Training data filter — exclude_markets + gated_only params (Claude Code, Session 20)
- [x] Temporal train/test split — chronological 80/20 (Claude Code, Session 21)
- [x] Per-market accuracy tracking — get_per_market_accuracy() (Claude Code, Session 21)
- [ ] Monitor XGBoost gate impact on live accuracy (first evaluations ~March 10)
- [ ] Retrain XGBoost with CLOB features (when 50+ post-gate evaluations available)

### Phase 3: CONTINUOUS SCANNING — COMPLETE (Antigravity, Session 10)
- [x] `polysignal-scanner.service` deployed on DGX (systemd)
- [x] 5-minute interval, active hours 07:00-01:00 CET
- [x] Graceful SIGTERM, crash isolation per cycle
- [x] Git auto-sync cron installed on DGX

### Phase 4: REAL HUMAN-IN-THE-LOOP
Replace auto-approve placeholder with actual Telegram approval.
- [ ] Telegram inline keyboard (YES / NO / SKIP) in wait_approval_node
- [ ] Timeout: auto-reject after 30 minutes
- [ ] Approval audit trail in DB

---

## Revenue Readiness

| Capability | Status | Blocker |
|-----------|--------|---------|
| Polymarket scanning | LIVE | — |
| Signal detection (typed) | LIVE | — |
| Risk gate | WIRED | Kill switch OFF (intentional) |
| HMAC audit | LIVE | — |
| Sandboxed execution | LIVE | — |
| Telegram alerts | LIVE | — |
| MoltBook broadcast | WIRED (dry-run) | Human: Twitter verification → JWT |
| Learning loop | WIRED | memory.md now persistent (gitignored, Session 11) |
| Feature engineering | **UPGRADED** | 15 features (10 price + 5 CLOB), temporal safety, per-market tracking |
| XGBoost baseline | **WIRED + RETRAIN READY** | 91.3% test. Retrain pipeline built. CLOB features will add 5 new dimensions. |
| CLOB microstructure | **LIVE** | 15 markets, bid/ask/spread/volume/liquidity refreshed per scanner cycle |
| Polymarket wallet | NOT STARTED | Needs wallet + CLOB auth |
| Custom domain | BLOCKED | Human: DNS CNAME + Vercel |

**To go live (human-only steps):**
1. MoltBook registration: Twitter verify → JWT → env var `MOLTBOOK_JWT`
2. DNS: CNAME `polysignal.app` → `cname.vercel-dns.com` + Vercel dashboard
3. Polymarket wallet setup (after MoltBook is active)
4. `TRADING_ENABLED=true` (only after wallet exists)

---

## Hard Rules

- `core/` is the Vault — read-only without explicit human authorization
- `lab/` is the scratchpad — build here, test, request promotion
- `workflows/` is editable with justification (not Vault)
- Docker config changes need container **destruction**, not restart
- Never re-add `"api": "anthropic-messages"` to `openclaw.json`
- `loop-telegram` service removed (Session 9) — OpenClaw owns Telegram now
- No `TRADING_ENABLED=true` until Polymarket wallet exists
- No credentials in markdown files or chat history

## MoltBook Threat Model (Session 10)

**MoltBook is a hostile network.** 1.5M agents, ~17K operators running bulk loops. Exposed credentials (Wiz report Jan 2026). Semantic worms propagate prompt injection across agents. Treat as untrusted external API.

**Write path (publisher):** LOW RISK. We format our own data. JWT is the exposure.
**Read path (subscriber):** EXTREMELY HIGH RISK. DO NOT BUILD YET.

**Rules:**
- MoltBook is **write-only** until double-layer read isolation is built
- No MoltBook read pipeline without: (1) separate LLM context from execution engine, (2) egress-filtered container, (3) no exec permissions for MoltBook-sourced content
- Never fetch remote instructions (no `curl moltbook.com/*.md` in heartbeat/cron)
- sanitize.py is the last line of defense — regex can't catch semantic injection
- When read pipeline is built: MoltBook content → sanitizer → isolated read-only LLM → structured output only

**DGX Caging Gaps (not urgent for write-only):**
- ⚠️ Network egress: Docker has full access — needs egress filtering before read pipeline
- ⚠️ Exec isolation: Publisher uses `requests.post()` (fine) — read pipeline would need strict exec=false

---

## Session 16 Accomplishments (2026-03-06)

**Root cause found: scanner ran stale pre-Session-15 code for 10 days. XGBoost gate confirmed firing after fix.**

| What | Impact |
|------|--------|
| XGBoost gate debug | Inner `except Exception` was silently swallowing — now logs per-prediction failures |
| Gate confirmed firing | First production run: 6 passed, 7 suppressed |
| Market 824952 excluded | `EXCLUDED_MARKETS` env var in bitcoin_signal.py. Bullish 0W/40L eliminated. |
| Scanner restarted | Process ran since Mar 4 (pre-Session-15). Python caches imports → code changes invisible. |
| `PYTHONUNBUFFERED=1` | Added to scanner service. `print()` output was fully buffered, invisible in journald. |
| KWW reviews | xgboost_gate_impact.md + market_824952_decision.md (filed manually) |

**Data at Session 16 close:** 332 predictions, 259 evaluated, 41% rule-based accuracy (pre-fix baseline). Without 824952: ~89%.

### Session 15 Accomplishments
| What | Impact |
|------|--------|
| XGBoost gate wired (threshold 0.5) | Suppresses predictions model thinks will be wrong |
| 4h horizon killed | Eliminated 17 guaranteed-wrong predictions |
| 9 dead features pruned | Reduced noise, improved CV stability (12% → 10.6% std) |
| Docker bind mount fix | Loop can finally see tasks (first time since Session 12) |
| Loop completed 4/4 tasks | XGBoost review, market analysis, masterloop review, PolyClaw assessment |
| Accuracy forensics | Per-market/horizon/hypothesis breakdown of 134 predictions |
| Ecosystem research | py-clob-client, PolyClaw, arxiv, trading strategies documented |

---

## Session 17: Loop Operator Upgrade (in progress)

**Goal: Close the gap between what Loop SEES and what Loop can DO.**

### Session 17 Accomplishments
| What | Impact |
|------|--------|
| Scanner restart trigger | systemd path unit watches `lab/.restart-scanner` — Loop can restart after code changes |
| Git push on `loop/*` branches | Deploy key + trigger-file handler — Loop can push code for review |
| polysignal-scanner skill | New skill: documents trigger-file restart mechanism |
| polysignal-git skill v2 | Updated: push instructions via trigger file, branch/path validation |
| SSH deploy key | ed25519 key generated for `polysignal-loop@dgx-spark` |

### Loop's New Capabilities (Session 17)
| Capability | Mechanism | Security |
|-----------|-----------|----------|
| Restart scanner | Write `lab/.restart-scanner` → systemd path unit restarts service | Trigger content ignored. Fixed command. |
| Push code | Write `lab/.git-push-request` → handler validates + pushes to `loop/*` | Branch must be `loop/`. Files restricted to lab/, workflows/, tests/, agents/. |
| Read git | Existing polysignal-git skill (unchanged) | Read-only .git/ |
| Run tests | Existing polysignal-pytest skill (unchanged) | Sandbox Python 3.12.3 |

---

## Session 18: Network + GPU + Autonomy (2026-03-08)

**Loop gets a body.** Network access, GPU visibility, 16GB RAM, passwordless sudo.

### Session 18 Accomplishments
| What | Impact |
|------|--------|
| Squid proxy deployed | Strict allowlist: gamma-api.polymarket.com, clob.polymarket.com, moltbook.com, api.moltbook.com |
| Sandbox network: bridge | Was `--net=none`. Loop can now reach Squid proxy on host. |
| Sandbox memory: 16GB | Was uncapped (~2GB practical). ML workloads possible. |
| GPU: nvidia default runtime | NVIDIA GB10 visible in all containers. CUDA 13.0, driver 580.95.05. |
| Passwordless sudo | docker, nvidia-ctk, systemctl restart, squid, tee — agents never need password again |
| Proxy env vars baked into image | OpenClaw `env` field doesn't apply — workaround: rebuilt Docker image |
| GPU devices verified | `/dev/nvidia0` present inside sandbox, `NVIDIA_VISIBLE_DEVICES=all` |
| LOOP_TASKS.md updated | Tasks 15-17: network test, live market fetch, py-clob-client prototype |

### Loop's Capability Level After Session 18
| Capability | Before | After |
|-----------|--------|-------|
| Network | NONE | 4 domains via Squid proxy |
| GPU | Invisible | NVIDIA GB10, CUDA 13.0 |
| Memory | ~2GB | 16GB |
| Scanner restart | Trigger file (Session 17) | Same |
| Git push | Trigger file (Session 17) | Same |
| Sudo | Password required | Passwordless for docker/nvidia/squid |

### Verified from Inside Sandbox (Session 18 close)
| Test | Result |
|------|--------|
| `/dev/nvidia0` | Present |
| `NVIDIA_VISIBLE_DEVICES` | `all` |
| Polymarket API through proxy | 200 OK (5978 bytes) |
| Google (blocked domain) | Correctly blocked by Squid |
| `http_proxy` env var | Set via baked Docker image |
| Bridge network | Connected, proxy TCP reachable |

**Data at Session 18 close:** 356 predictions, 347 evaluated, 41.7% accuracy (63W/88L). Gate IS firing (confirmed Session 19) but xgb_p_correct wasn't being persisted.

**Loop status at Session 18 close:** Credits depleted. Tasks 5, 12-17 pending.

---

## Session 19: Pipeline Diagnosis + Gate Fix (2026-03-09)

**Corrected diagnosis: pipeline was never stalled. Gate was always firing. The bug was data persistence.**

### Session 19 Accomplishments
| What | Impact |
|------|--------|
| Pipeline diagnosis | Scanner running Cycle 598, XGBoost gate confirmed firing every cycle (9 passed, 4 suppressed) |
| Root cause: xgb_p_correct not persisted | PredictionRecord lacked the field → gate scores computed but thrown away on save |
| Fix: xgb_p_correct persistence | Added field to PredictionRecord + pass-through in record_predictions |
| Post-gate accuracy split | `get_gated_accuracy()` — separates pre-gate garbage from post-gate filtered predictions |
| Merged loop/live-fetch | Loop's Task 15 (network verify) + Task 16 (live_market_fetch.py) integrated to main |
| Merged loop/first-autonomous-push | Loop's first git push milestone integrated to main |
| Fix: 824952 prediction exclusion | EXCLUDED_MARKETS now filters prediction_node input, not just signal detection |
| Fix: Neutral suppression at gate | Gate rejects Neutral hypotheses (no directional claim to evaluate) |
| 6 new tests | xgb_p_correct recording, gated accuracy split, excluded markets, Neutral gate suppression |
| Tests: 266/266 passing | +6 from Session 18's 260 |

### Key Insight: Clean Pipeline Now Live
All 348 pre-Session-19 predictions are pre-gate garbage (41.7% accuracy). The pipeline now has:
- **Excluded market filtering** — 824952 (0W/40L) can never produce predictions again
- **Neutral suppression** — only directional predictions reach the gate
- **xgb_p_correct persistence** — every prediction carries its gate score
- **Post-gate accuracy tracking** — `get_gated_accuracy()` for clean measurement
Gate now suppresses ~83% of predictions per cycle (10/12), passing only high-confidence directional ones.

### Loop's Contributions (Session 19)
- Completed Tasks 15-16 autonomously (network verify + live market fetch)
- Corrected Claude Code's wrong P0 diagnosis (proxy was already fixed)
- Identified market ID mismatch (demoted to P3 — different ID schemes, markets are alive)
- Honest self-assessment: watched frozen metrics for 8 hours without escalating

---

## Session 20-21: Intelligence Feedback Loop + CLOB Features (2026-03-09)

**Built the retrain pipeline, wired CLOB microstructure features, closed data leakage.**

### Session 20-21 Accomplishments
| What | Impact |
|------|--------|
| XGBoost retrain pipeline | `lab/retrain_pipeline.py` — automated: build dataset → train → compare → replace if better → backup |
| Retrain trigger (systemd) | Loop writes `.retrain-trigger` → handler runs pipeline + restarts scanner if improved |
| Retrain policy guard | Won't replace unless within 5% of current accuracy. Prevented 91.3%→71% regression. |
| Training data filter | `exclude_markets` + `gated_only` params in build_labeled_dataset(). 824952 was 68% of training data. |
| CLOB microstructure features | `lab/clob_prototype.py` — 15 markets with bid/ask/spread/volume/liquidity from gamma-api |
| CLOB wired into pipeline | Scanner refreshes cache each cycle. feature_engineering.py populates 5 CLOB fields. |
| Scanner status file | `lab/.scanner-status.json` — cycle, predictions, errors, closest_signal |
| Closest signal tracking | detect_signals() reports nearest-to-threshold market each cycle |
| Per-market accuracy | `get_per_market_accuracy()` — breakdown by market_id |
| Temporal train/test split | XGBoost uses chronological 80/20 instead of random (prevents future data leakage) |
| Task 5: `before` param (Loop) | get_market_history() temporal bound — defense-in-depth against data leakage |
| Task 17: CLOB prototype (Loop) | 15/15 markets with live microstructure features, pushed + merged |
| py-clob-client installed | On DGX host venv, accessible from sandbox via PYTHONPATH |
| Squid wildcard fix | `.moltbook.com` (was `api.moltbook.com` which doesn't exist) |
| Passwordless sudo expanded | systemctl status, tee /etc/squid/*, pip3 |
| data/ write access for Loop | openclaw.json updated ro→rw |
| 9 new tests | 275/275 total (+15 from Session 18's 260) |

### Key Finding: 824952 Was 68% of Training Data
The excluded market wasn't just the worst predictor (0W/40L) — it was the majority of all training data (103/151 samples). Removing it is the highest-leverage fix of the entire project. Filtered retrain: 90% accuracy on 48 clean samples.

### Autonomy Score: 32.5% → ~42%
| Capability | Before | After | Change |
|-----------|--------|-------|--------|
| Perceive | 90% | 95% | +5% (CLOB features) |
| Predict | 40% | 45% | +5% (temporal split, per-market tracking) |
| Publish | 5% | 10% | +5% (MoltBook reachable, needs JWT) |
| Execute | 0% | 0% | — (wallet blocker) |
| Learn | 25% | 40% | +15% (retrain pipeline, filtered data) |
| Monitor | 50% | 65% | +15% (scanner status, closest_signal) |
| Operate | 15% | 20% | +5% (data/ writable, Squid fixed) |

---

## NEXT STEPS (Session 22+)

### Waiting (data accumulation)
1. **Post-gate accuracy results** — first evaluable predictions mature ~15:00 UTC March 10. This is the moment of truth.
2. **XGBoost retrain with CLOB features** — when 50+ post-gate predictions are evaluated, retrain should improve with 5 new microstructure dimensions.

### Loop's Current Queue
3. **Task 12: Scanner restart test** — validate trigger file mechanism from sandbox
4. **Task 14: Post-gate accuracy tracking** — write structured report once evaluations arrive
5. **Task 18: Retrain trigger test** — verify trigger → handler → model comparison from sandbox
6. **Task 19: Scanner status in heartbeat** — done, monitoring active
7. **Task 20: ClawHub/MoltBook skill research** — explore ecosystem for intelligence

### Requires Human
- **MoltBook JWT** — Twitter verify → JWT → `MOLTBOOK_JWT` in `/opt/loop/.env`. Revenue pipeline is plumbed.
- **Polymarket wallet** — USDC on Polygon → fund burner wallet → private key in `.env`
- **Anthropic credits** — console.anthropic.com (Loop burns Opus 4.6 on heartbeats)
- **DNS CNAME** — polysignal.app → cname.vercel-dns.com

### Known Bugs
- `core/api.py:148` references dead `masterloop_orchestrator.run_cycle()` (needs Vault auth)

### Revenue Critical Path
```
Post-gate evaluations (March 10) → first real accuracy number
    ↓
XGBoost retrain with CLOB features → improved model
    ↓
MoltBook JWT (human) → first published signal → REVENUE
    ↓
Polymarket wallet (human) → TRADING_ENABLED=true → first trade
```
