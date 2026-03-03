# PolySignal-OS — Current System State
# Last updated: 2026-03-03 15:10 CET | Session 11 active
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
| GitHub | SYNCED | Mac current, DGX cron: `git reset --hard` (respects .gitignore) |
| Tests | 217/217 PASS | Mac (1.5s) — +27 feature engineering tests (Loop) |
| Scanner | DEPLOYED | `polysignal-scanner.service` — signal-enhanced predictions (Session 11) |
| DGX Thermal | OK 51-52°C | Cooled from 67-77°C (Session 10). Monitor. |
| Outcome Tracker | WIRED | Signal-enhanced predictions now recording (was broken — Session 11 fix) |
| Risk Gate | PROMOTED | `core/risk_integration.py` — review → risk_gate → commit |
| MoltBook Publisher | WIRED | Non-blocking in commit_node (dry-run until JWT) |
| Learning Loop | WIRED | write_memory() in commit_node — brain/memory.md gitignored (Session 11 fix) |
| Loop Autonomy | ACTIVE | TASKS.md rewritten (Session 11), supervisor JSON fix deployed |
| Feature Eng. | LAB | `lab/feature_engineering.py` — 18 features, labeled dataset builder (Loop) |

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
| **Prediction** | Rule-based + signal enhancement (Session 11) | ML model (XGBoost → transformer) | **Critical** — feature eng ready, waiting on labeled data |
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

### Phase 2: REAL PREDICTION (in progress — data now flowing)
Replace rule-based predictor with ML. The DGX has a Blackwell GPU sitting idle.
- [x] Feature engineering from observations table — `lab/feature_engineering.py` (Loop, Session 11)
- [ ] Accumulate 50+ labeled predictions (signal enhancement now recording — ~24-48h)
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
| Learning loop | WIRED | memory.md now persistent (gitignored, Session 11) |
| Feature engineering | READY | 18 features, awaiting 50+ labeled predictions |
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

## 🎯 NEXT STEPS (Session 11)

**Data pipeline fixed. Signal-enhanced predictions now recording. Phase 2 ML is next.**

1. **Verify (now):** Confirm outcome_tracker recording non-Neutral predictions after scanner restart
2. **Accumulate (24-48h):** 50+ labeled predictions needed for XGBoost baseline
3. **Phase 2 (when data ready):** Train XGBoost on feature vectors from `lab/feature_engineering.py`
4. **MoltBook JWT (human):** Twitter verification → env var `MOLTBOOK_JWT` → live publishing
5. **Phase 4 (after Phase 2):** Real HITL — Telegram YES/NO buttons
6. **Known bug (needs Vault auth):** `core/api.py:148` references dead `masterloop_orchestrator.run_cycle()`

### Revenue Critical Path
```
MoltBook JWT (human) → Live publishing → Reputation → Polymarket wallet → Trading
         ↓                                    ↓
   Write signals              MoltBook read pipeline (Phase 5 — needs isolation)
```
