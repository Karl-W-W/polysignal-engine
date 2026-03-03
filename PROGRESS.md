# PolySignal-OS — Current System State
# Last updated: 2026-03-03 03:00 CET | Session 10 closing
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
| OpenClaw Sandbox | UP | Firejail :9001, 10 bind mounts |
| OpenClaw Gateway | UP | systemd, Claude Opus 4.6, heartbeat 30m |
| Telegram Bot | UP | `@OpenClawOnDGX_bot`, allowlist: [1822532651] |
| Frontend | LIVE | `polysignal-os.vercel.app` (Vercel) |
| Cloudflare Tunnel | UP | DGX → polysignal.app |
| LangSmith | ENABLED | EU endpoint, `LANGCHAIN_TRACING_V2=true` |
| GitHub | SYNCED | Mac current, DGX auto-syncs via cron |
| Tests | 190/190 PASS | Mac (1.5s) |
| Scanner | DEPLOYED | `polysignal-scanner.service` on DGX — increase to 10min if temps >80°C |
| DGX Thermal | ⚠️ 67-77°C | Scanner + Ollama sustained load. Throttle at 90°C. Monitor. |
| Outcome Tracker | WIRED | Records predictions, evaluates after time horizon |
| Risk Gate | PROMOTED | `core/risk_integration.py` — review → risk_gate → commit |
| MoltBook Publisher | WIRED | Non-blocking in commit_node (dry-run until JWT) |
| Learning Loop | WIRED | write_memory() in commit_node → memory.md → draft_node |
| Loop Autonomy | ACTIVE | TASKS.md mounted, heartbeat firing |

## Vault Inventory (`/opt/loop/core/` — 10 files)

| File | Purpose |
|------|---------|
| `perceive.py` | Polymarket Gamma API scanner |
| `predict.py` | Rule-based momentum detection (MVP — see roadmap) |
| `supervisor.py` | NVIDIA NIM + HMAC audit (fast/slow path) |
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
| **Prediction** | `if avg_move > 0.01 → bullish` | ML model (XGBoost → transformer) | **Critical** |
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

### Phase 2: REAL PREDICTION (next — waiting on 48-72h scanner data)
Replace rule-based predictor with ML. The DGX has a Blackwell GPU sitting idle.
- [ ] Feature engineering from observations table (price, volume, delta, time_horizon)
- [ ] XGBoost baseline model (interpretable, fast to train)
- [ ] Backtest against historical observations
- [ ] A/B: rule-based vs XGBoost confidence scores
- [ ] Promote if XGBoost beats baseline by >10% accuracy

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
| Learning loop | WIRED | memory.md grows per cycle |
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

## 🎯 NEXT STEP

**Monitor scanner data accumulation (48-72h), then start Phase 2: ML prediction.**

1. **Immediate (Loop/Antigravity):** Monitor DGX thermals — increase `SCAN_INTERVAL_SECONDS=600` if sustained >80°C
2. **Immediate (Loop):** Verify 190/190 tests on DGX after auto-sync, check outcome tracker writes to `/opt/loop/data/prediction_outcomes.json`
3. **48h gate:** After scanner has accumulated data, evaluate if enough labeled predictions for XGBoost baseline
4. **Phase 2 start:** Feature engineering from outcome_tracker data → XGBoost baseline → backtest → A/B vs rule-based
5. **Known bug (needs Vault auth):** `core/api.py:148` references dead `masterloop_orchestrator.run_cycle()` — KWW must authorize fix
