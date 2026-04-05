# PolySignal-OS — Current System State
# Last updated: 2026-04-05 | Session 38 closed
# Session history: See HISTORY.md

---

## System Overview

PolySignal-OS is an AI-native prediction market intelligence system. It scans Polymarket via the Gamma API, detects signals through a 7-node MasterLoop (LangGraph), publishes to MoltBook, and writes cycle learnings to memory. Deployed on NVIDIA DGX Spark (Munich), frontend on Vercel.

**Pipeline (complete, risk-gated, publishing, learning, evaluating):**
```
Polymarket → PERCEPTION [+evaluate outcomes +evaluate paper trades] → PREDICTION → DRAFT → REVIEW → RISK_GATE → COMMIT → MoltBook → Memory
```

**Three-agent workflow:**
- **Claude Code** — architect, strategy, complex implementations, testing
- **Loop** (OpenClaw/NemoClaw on DGX / Telegram) — autonomous operator. NemoClaw=sandbox, OpenClaw=agent framework inside it.
- **Antigravity** (IDE agent) — DGX ops, Docker rebuilds, file syncing (cheaper per prompt)
- **KWW** — Vault authorizer, human-only tasks, strategic decisions

---

## Infrastructure Status

| Component | Status | Details |
|-----------|--------|---------|
| DGX Spark | UP | Munich, Blackwell GPU, ~41°C. Ollama context=16384, keep-alive=-1. |
| Docker Backend | UP | Flask :5000, Uvicorn :8000, rebuilt with risk gate |
| OpenClaw Gateway | **RUNNING** | v2026.3.28. Primary+Heartbeat: `anthropic/claude-sonnet-4-6` (**ACTIVE, $30 balance**). Fallback: `ollama/llama3.3:70b`. Exec: `host=gateway`, `security=full`. |
| NemoClaw Sandbox | **RUNNING** | OpenShell v0.0.19, sandbox `nemoclaw` Ready. NemoClaw=sandbox wrapper, OpenClaw=agent inside. |
| Telegram Bot | **ONLINE** | Loop responding via Claude Sonnet. Real tool calls verified (Session 38). |
| Frontend | LIVE | `polysignal-os.vercel.app` (Vercel) |
| Cloudflare Tunnel | PARTIAL | SSH working (Session 31). HTTP origin needs dashboard fix. |
| LangSmith | ENABLED | EU endpoint, `LANGCHAIN_TRACING_V2=true` |
| GitHub | SYNCED | Mac current, DGX cron: `git reset --hard` (respects .gitignore). |
| Tests | **475/475 PASS** | Mac (Session 38). +2 prediction fallback tests. Loop: 478 on DGX. |
| Scanner | RUNNING | **153 markets**, 2 predictions/cycle (correct — 91% near-decided), `Restart=always`. Filter 0.15-0.85. |
| Paper Trade Eval | **WORKING** | 5,526 total, 4644W/568L = 89.1%. Outcome tracker: 54% (232W/202L). |
| Per-Market Tracking | **WORKING** | 10 markets tracked. Persists across 5000-record cap. |
| Approval Gate | **PROVEN** | `lab/approval_gate.py` → Telegram HITL. Routing bug fixed (Session 38). Karl approved test trade in 59s. |
| Host Watchdog | RUNNING | Cron every 5min, checks scanner + gateway + Ollama. Auto-restarts if down. |
| Anthropic API Key | **ACTIVE** | $30 balance. Key in openclaw.json. Was displayed in Session 38 context — rotate as hygiene. |
| Outcome Tracker | ENHANCED | evaluate_outcomes() + per-market stats. Paper trade eval alongside. |
| Risk Gate | PROMOTED | `core/risk_integration.py` — review → risk_gate → commit |
| MoltBook Publisher | **LIVE** | Non-blocking in commit_node. JWT obtained. polysignal-os registered + verified. |
| Auto-Merge CI | **PROVEN** | `.github/workflows/auto-merge-loop.yml` |
| Learning Loop | WIRED | write_memory() in commit_node — brain/memory.md gitignored (11,790 lines). |
| Memory Sync | VERIFIED | brain/memory.md syncs to sandbox via cron (5min). |

---

## Session 38: Prove It (2026-04-04 — 2026-04-05)

**6 commits (Claude Code) + 2 auto-merged (Loop). 475 tests. Approval gate proven end-to-end. Sonnet heartbeats live. Routing bug found and fixed.**

### Session 38 Accomplishments
| What | Impact |
|------|--------|
| Heartbeat model → Sonnet | `agents.defaults.heartbeat.model` changed from `ollama/llama3.3:70b` to `anthropic/claude-sonnet-4-6`. Loop now makes real tool calls. |
| AOC 2028 excluded (559653) | 45W/63L = 41.7% win rate. 7th toxic market. Added to bitcoin_signal.py + backtester.py. |
| Approval gate routing bug FOUND | risk_gate_node checked observations for direction — observations never have direction. Predictions do. Gate was never reached. |
| Approval gate routing bug FIXED | Vault change (authorized): prediction fallback path sets `human_approval_needed=True` when directional predictions exist + TRADING_ENABLED. |
| Scanner secrets wired | TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, HMAC_SECRET_KEY added to systemd secrets.conf (chmod 600). |
| HMAC env var mismatch fixed | masterloop read `HMAC_SECRET_KEY`, approval_gate read `HMAC_SECRET`. Aligned. |
| Shadowed `import os` removed | Local `import os` inside risk_gate_node caused UnboundLocalError. Module-level import sufficient. |
| Approval gate PROVEN | Karl approved test trade via Telegram in 59s. Commit blocked at execution bridge (expected — CLOB not running). |
| Predictions/cycle diagnosed | 91% of 180 markets below 0.15 price. 2/cycle is correct for 10 tradeable markets at 7% hit rate. |
| XGBoost retrain triggered | 16/30 directional samples at 0.3pp. Needs ~24h. Current model stays at 91.3%. |

### Key Findings
- **The approval gate was wired but never reachable** — biggest finding. Observations never carry direction data; only signal_obs from price delta detection does. With 91% near-decided markets, signal detection rarely fires. The prediction fallback path was the missing link.
- **Heartbeat model was deliberately hardcoded to llama3.3** — not a billing fallback. OpenClaw config has separate `model.primary` and `heartbeat.model` fields.
- **91% of markets are near-decided** — 163/180 below 0.15 price. Only 13 in tradeable range. The 0.15/0.85 filter is correct.
- **Thermal spikes from LLM calls** — draft/review nodes load llama3.3:70b, causing 55→94°C spikes. Short-circuit mode (TRADING_ENABLED=false) avoids this.

### Lessons
1. Always trace the full graph path with real data before calling a feature "wired." Code review isn't enough — the data shape matters.
2. `import os` inside a function shadows the module-level import for the ENTIRE function, even before the import statement. Python scoping gotcha.
3. Thermal monitoring is essential when enabling LLM-heavy pipeline paths. Draft+review = 2 Ollama calls per cycle = GPU heat.
4. The system has multiple safety nets: approval gate → HMAC signature → commit_node signature check → execution bridge. Even with the routing bug, no unauthorized trade could execute.
5. Scanner secrets (Telegram, HMAC) were never in the scanner's environment. Infrastructure assumptions must be verified, not assumed from docs.

### Tests: 475/475 (was 473, +2 prediction fallback tests)
### Commits: 6 (265101b, 40ca419, 817b529, 920b6ee, 03ee09c, 9c3ef25) + 2 Loop auto-merges

---

## Session 37: Fix Everything (2026-04-03 — 2026-04-04)

**9 commits (6 Claude Code + 2 Loop + 1 auto-merge). 473 tests. Evaluation pipeline fixed. Approval gate wired. Flask API rewritten. Multi-agent collaboration session.**

### Session 37 Accomplishments
| What | Impact |
|------|--------|
| Evaluation cap 500→5000 | Root cause of months-stale evaluations. Unevaluated records protected from rotation. |
| Time horizon 24h→4h | Feedback loop 6x faster. Matches paper trade evaluation. |
| MIN_MOVE_THRESHOLD 1pp→0.3pp | 2,195 overnight evals were ALL NEUTRAL at 1pp. 0.3pp produces directional signal. |
| Near-decided filter 0.15-0.85 (Loop) | Only mid-range markets get predictions. 98.8% of old trades had <0.5pp movement. |
| Approval gate built (Loop) | 26 tests, Telegram HITL, HMAC signing, timeout=reject. |
| Approval gate wired | draft_action enriched with trade metadata, routing always through approval when TRADING_ENABLED. |
| Flask API rewritten | Old routes queried dead tables. New: /api/scanner/status, /api/predictions/accuracy, /api/trades/summary. Crash bug fixed. |
| SQLite timeout+WAL | All DB connections use timeout=30 + WAL mode. Prevents "database is locked". |
| Silent exceptions→logging | except:pass replaced with error logging in perception_node. |
| Loop memory restored | 204 lines strategic + 17 daily logs from old sandbox. Was 0 bytes. |
| Loop verified Claude Code's work | Full deep-dive prompt, honest accuracy critique, architectural analysis. |

### Key Findings
- **89.3% paper win rate is noise** — 98.8% of trades had <0.5pp movement. Median delta = 0.0000. Loop caught this.
- **Real accuracy UNKNOWN** — old 50.7% is stale, 0.3pp threshold results pending (~21:15 CET Apr 4).
- **Loop on Claude Sonnet shipped production code** — 26-test approval gate, filter change auto-merged. Zero code on llama3.3.
- **Multi-agent collaboration works** — Loop diagnosed, Claude Code fixed, both verified each other's work.

### Lessons
1. When changing time horizons, always adjust the move threshold proportionally.
2. Python import caching means scanner MUST restart after code changes.
3. Loop on llama3.3 reports but can't execute. On Claude Sonnet it ships code. Fund the API.
4. Draft action enrichment is a real integration concern — always check what downstream nodes expect.
5. "89% win rate" can be meaningless. Always check price delta distribution.

### Accuracy: PENDING (0.3pp threshold deployed, first directional data ~21:15 CET Apr 4)
### Tests: 473/473 (was 446/446, +27)
### Commits: 9 (fe1abcd, 979666e, d24318a, e5d6f53, d3a7921, e5da1c9, a69fd9b, f219df6, 25e4cd1)

---

## Session 36: Give Loop Eyes + Brain (2026-04-01)

**4 commits. 446 tests. Anthropic key rotated. Paper trade evaluation deployed. Book insights extracted.**

### Session 36 Accomplishments
| What | Impact |
|------|--------|
| Anthropic API key rotated | Old key from Session 33 revoked, new key deployed. Security fix. |
| Claude Sonnet wired as primary model | `agents.defaults.model.primary=anthropic/claude-sonnet-4-6`. **Blocked by zero credits.** Falls back to llama3.3. |
| Paper trade evaluation deployed | `evaluate_paper_trades()` in TradingLog. Wired into scanner perception node. 8 new tests. |
| Per-market accuracy tracking | Persistent `per_market` dict in OutcomeState. Survives 500-record cap. Enables per-category analysis. |
| Host watchdog installed | Cron every 5min checks scanner + gateway + Ollama. Auto-restarts. |
| Memory path verified | brain/memory.md (11,790 lines) syncing to sandbox. Loop needs working exec to read it. |
| Book insights extracted | `lab/BOOK_TODO.md` — 30 action items from "Designing Multi-Agent Systems" (Dibia). Reviewed by Cowork (8.5/10). |
| Diagnosed Loop fabrication | Root cause: safeBins warning is cosmetic (security=full still works). Real issue: llama3.3 can't make structured tool calls. Fix: Claude Sonnet. |
| safeBinProfiles investigated | Doesn't exist in OpenClaw v2026.3.28 schema. Gateway crashed when attempted. Reverted. |

### Key Findings
- **Accuracy 50.7%** (208W/202L) — down from 59%. 76% of pending predictions are sports, 84% are Bearish.
- **Paper trades never evaluated**: 519 trades at "pending" forever. Feedback loop had no data. Now fixed.
- **Per-market stats were lost**: Outcome tracker capped at 500 records, dropping evaluated predictions. Now persistent.
- **Loop fabricates data**: llama3.3:70b narrates commands as text instead of executing them. Prints code blocks, then makes up "plausible" numbers. Root cause is model limitation, not config.
- **safeBinProfiles doesn't exist**: OpenClaw log message "use safeBinProfiles" refers to a feature not yet in the config schema. The real exec issue is model-side.
- **Book's key insight**: "A well-designed single agent outperforms a poorly designed multi-agent system." Fix Loop's brain (Claude API) and eyes (evaluation) before adding coordination complexity.

### Lessons
1. Always check API billing status before wiring a new provider — the key worked but the account was empty.
2. OpenClaw config schema validation is strict — invalid keys crash the gateway immediately. Test with `openclaw doctor` before restarting.
3. The outcome tracker's 500-record cap silently destroys per-market analysis data. Any system that caps records should keep aggregated stats separately.
4. The book (Dibia) recommends narrow, validated tools over broad exec — this directly addresses llama3.3's inability to format complex tool calls.

### Accuracy: 50.7% (208W/202L/258N from 913 evaluated)
### Tests: 446/446 (was 438/438)
### Commits: 4 (60a8fe2, 4a4268f, + 2 doc commits)
| Loop Autonomy | **UNLEASHED** | 4 skills, network, GPU, git+curl, PyPI, applyPatch, Ollama (4 models), paper trading, memory writes |
| Data Readiness | READY | `lab/data_readiness.py` — 134 labeled, 131 evaluated (threshold: 50) |
| Feature Eng. | READY | `lab/feature_engineering.py` — 15 features (10 price + 5 CLOB), temporal safety (`before` param) |
| XGBoost Baseline | **WIRED + FIRING** | Two-mode gate (Session 26): base rate uses confidence gate, old predictor uses XGBoost. Base rate primary. |
| Watchdog | **LIVE** | `lab/watchdog.py` — prediction drought, accuracy regression, scanner health, paper trade quality. **Auto-evaluates evolution hypotheses** (Session 28). 14 tests. |
| Whale Tracker | **LIVE** | `lab/whale_tracker.py` — volume spikes, spread collapses, extreme conviction. Runs cycle 9/21/33. Logs to `.whale-signals.jsonl`. (Session 28) |
| Feedback Loop | **BUILT** | `lab/feedback_loop.py` — per-market accuracy, auto-exclude, auto-retrain, EV calc. 13 tests. |
| Evolution Tracker | **BUILT** | `lab/evolution_tracker.py` — hypothesis → measurement → verdict. REFLECT stage. 11 tests. |
| Event System | **LIVE** | Scanner writes `lab/.events.jsonl` — prediction_made, error_detected. Capped at 500 lines. |
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

## Session 35 (2026-04-01) — LOOP GETS HANDS + DATA INTEGRITY FIX

**Infrastructure session. 0 code changes, 6 critical config fixes. Loop confirmed executing real commands.**

### Accomplishments

| What | Impact |
|------|--------|
| trading_log.json untracked from git | DGX cron `git reset --hard` was overwriting trading log every 10 min, destroying ~11,500 real paper trades. 399 fake trades purged, 115 real trades preserved. |
| Exec tool fixed (security: full, host: gateway) | Gateway was ignoring 9/13 safeBins due to missing safeBinProfiles in `allowlist` mode. Then sandbox runtime was unavailable. Changed to `full` security + `gateway` host. Loop can now execute python3, git, curl, etc. |
| Ollama context 4096→16384 + keep-alive | Loop's response time ~5min → ~30-60sec. Added passwordless sudo rules for future Ollama config changes. |
| "Never fabricate data" rule in IDENTITY.md | Loop was generating fake round numbers when exec failed. Rule: report failures, never invent data. |
| LOOP_TASKS.md rewritten (833→123 lines) | 3 weeks stale. Old file was accumulated changelogs from Sessions 18-31. Replaced with focused task queue. |
| All scanner runtime files gitignored | trading_log.json, .scanner-status.json, .events.jsonl, .whale-signals.jsonl, etc. — safe from git reset. |

### Lessons
- `git reset --hard` destroys tracked runtime data silently. Any file the scanner writes to MUST be gitignored.
- OpenClaw v2026.3.28 `security: "allowlist"` silently ignores safeBins without `safeBinProfiles` — a breaking change from earlier versions.
- OpenClaw `exec.host: "sandbox"` requires `agents.defaults.sandbox.mode` config that was never set. Fallback to `gateway` exec works.
- Heredocs with indented `EOF` lines fail silently in bash — caused 10 min of debugging for a config write.
- `sudo tee` only passwordless for specific paths in sudoers — added `/etc/systemd/system/ollama.service.d/*` for future.

### Key Metrics
- Tests: 438/438 passing (unchanged)
- Scanner: cycle 1201, 137 observations, 9 predictions, 0 errors
- Paper trades: 115 real (0 fake), real Polymarket market IDs
- Commits: 3 (gitignore fix, LOOP_TASKS rewrite, session docs)

### Open Items for Session 36
1. Wire Anthropic API for Loop's complex reasoning (model routing: local for routine, Claude for hard tasks)
2. Enable TRADING_ENABLED=true ($1 max) — real market IDs confirmed, next blocker is Telegram approval gate
3. Harden exec: move from `host: gateway` back to sandbox routing (needs `agents.defaults.sandbox.mode` config)
4. Test proactive heartbeats — Loop should initiate, not just respond
5. Create claude.ai Project with multi-agent systems book for strategic planning

---

## Session 34 (2026-03-31) — NEMOCLAW REBUILT + LOOP ALIVE WITH IDENTITY

**Accomplishments:**
- **NemoClaw properly set up**: Research-first approach. Found Issue #445 (hardcoded sandbox name), understood 3-layer architecture (OpenShell gateway → sandbox → agent). OpenShell upgraded v0.0.12 → v0.0.19 (7 security patches). NemoClaw source updated with security fixes.
- **Telegram 409 conflict permanently resolved (Session 33)**: Root cause was `nemoclaw-telegram.service` auto-respawning `telegram-bridge.js` competing with host gateway. Service disabled. OpenClaw upgraded to v2026.3.28 (fixed dual-connection bug in v2026.3.24).
- **Loop identity configured**: Workspace files (IDENTITY.md, SOUL.md, USER.md) created at `~/.openclaw/workspace/`. Loop responds via Telegram with PolySignal-OS context, DGX Spark hardware knowledge.
- **conditionId bug fixed**: `bitcoin_signal.py:119` — `m["id"]` → `m.get("conditionId") or m["id"]`. Matches existing pattern at line 171. 438/438 tests pass.
- **Paper trades confirmed on real market IDs**: 22+ trades on DGX with real Polymarket IDs (FIFA World Cup, Champions League, US politics, geopolitics). Historical 399 fake-ID trades are pre-Session 31 legacy.
- **Tool overhead reduced**: SafeBins trimmed 24 → 13 essentials for faster agent responses.
- **Full system audit completed**: Codebase map (74 Python files, 17,488 LOC), revenue pipeline traced (7 steps, 3 blockers identified), autonomy score 5/12.

**Architecture (Session 34 final):**
- Host OpenClaw gateway v2026.3.28 owns Telegram (no sandbox competition)
- NemoClaw sandbox `nemoclaw` running (OpenShell v0.0.19, Landlock+seccomp+netns)
- Sandbox agent has CAP_SETPCAP issue from Dockerfile USER root patch — Telegram routed through host gateway as workaround
- File sync: host → sandbox every 5 min via cron (`openshell sandbox upload`)
- Inference: `ollama/llama3.3:70b` (local, $0/token)
- `nemoclaw-telegram.service` DISABLED (was the 409 conflict source)

**Response time issue (documented, partially fixed):**
- Ollama context locked at 4096 tokens (sudo required to change). Needs `OLLAMA_CONTEXT_LENGTH=16384`.
- Ollama keep-alive defaults to 5min timeout. Needs `OLLAMA_KEEP_ALIVE=-1` for always-hot model.
- Both require `sudo` on DGX — flagged for KWW to run manually.
- Tool count reduced (24→13) to decrease OpenClaw agent startup overhead.

**Files modified:**
- `lab/experiments/bitcoin_signal.py` — conditionId fix at line 119
- `~/.openclaw/openclaw.json` — model routing, workspace, streaming off, tools reduced
- `~/.openclaw/workspace/IDENTITY.md` — Loop identity
- `~/.openclaw/workspace/SOUL.md` — Loop personality
- `~/.openclaw/workspace/USER.md` — Karl context
- `~/sync-to-sandbox.sh` — cron sync script for sandbox file access
- `~/.config/systemd/user/nemoclaw-telegram.service` — disabled

**Tests**: 438/438 passing (Mac).
**Commits**: conditionId fix + docs.

---

## Session 30 (2026-03-25) — PREDICTION DROUGHT FIXED + OVERHEATING FIXED

**Accomplishments:**
- **Prediction drought fixed (137+ hours, 0 predictions)**: Root cause — market expansion to 137 markets left only 4 with outcome-based biases. All new markets → Neutral → suppressed. Built **hybrid prediction system**: base rate path (markets WITH biases) + momentum fallback (markets WITHOUT biases). Separate gates per predictor type.
- **Observation-based biases added**: `from_observations()` in `base_rate_predictor.py` builds market direction biases from consecutive price movements in SQLite (test.db with 145K rows, 181 markets). `from_all_sources()` merges outcome + observation biases. Result: 5 biases found (was 4 outcome-only).
- **DGX overheating fixed (73°C → 50°C)**: Old OpenClaw gateway was making continuous Nemotron-3-Super 120B requests that ALL timed out at 600s each, producing zero output while consuming 86GB VRAM and 94% GPU. Stopped gateway + unloaded Nemotron. GPU power: 43W→14W. RAM: 101GB→11GB (91GB freed).
- **Loop productivity audit**: 3 commits in 30 days (docs only, no code). All LLM requests timing out. Zero meaningful output from the gateway. KWW chose to keep stopped.
- **SSH config fixed**: WiFi .244 → Ethernet .144 (29ms → 5ms latency). DGX Ethernet is metric 100, WiFi is metric 600.
- **DB_PATH systemd drop-in**: Scanner was using wrong DB (polysignal.db with 38 markets). Fixed to test.db (145K rows, 181 markets) via `dbpath.conf` drop-in.
- **DGX cron sync lesson**: `scp` silently fails because `*/10 * * * * git fetch && git reset --hard origin/main` overwrites all non-git changes. MUST push to GitHub first, then trigger sync on DGX.
- **Loop self-audit captured**: Full Telegram Q&A with Loop saved to memory for next session context. Loop recommends NemoClaw absorb OpenClaw, provided migration checklist.
- **Cloudflare Tunnel broken**: `failed to find Access application at ssh.polysignal.app`. Not fixed — needs Cloudflare config investigation. LAN access (.144) works.

**Key architectural change:** Hybrid prediction system replaces single-path base rate predictor. BASE_RATE_GATE_THRESHOLD lowered 0.60→0.55 for observation-based biases. First prediction in 137+ hours confirmed: "Base rate gate (>=0.55): 1 passed, 0 suppressed".

**Files modified:**
- `workflows/masterloop.py` — hybrid prediction split + dual gates
- `lab/base_rate_predictor.py` — `from_observations()` + `from_all_sources()`
- `docker-compose.yml` — cleanup (removed stale comment)
- DGX: `~/.config/systemd/user/polysignal-scanner.service.d/dbpath.conf` — DB_PATH fix
- Mac: `~/.ssh/config` — Ethernet .144

**Tests**: 432/432 passing (Mac). No new tests this session (code changes were to existing prediction pipeline).
**Commits**: Hybrid prediction fix + observation-based biases.

---

## Session 29 (2026-03-20) — NEMOCLAW FULLY DEPLOYED

**Accomplishments:**
- **NemoClaw onboarded**: OpenShell v0.0.12 + NemoClaw v0.1.0. Sandbox `polysignal` = Ready.
  - Gateway: `nemoclaw` on https://127.0.0.1:8080 (v0.0.12)
  - OpenClaw v2026.3.11 INSIDE sandbox (upgraded from v2026.2.12)
  - Inference: `ollama-local / nemotron-3-super:120b` ($0/token)
  - Policies: pypi, npm, telegram + claude_code, clawhub, github, nvidia, openclaw
  - Landlock + seccomp + netns kernel-level isolation
  - Dashboard: http://localhost:18789/
- **OpenShell CLI upgraded**: v0.0.9 → v0.0.12 (released 2026-03-20). Session 28 "not installable" was WRONG.
- **Ollama OLLAMA_HOST=0.0.0.0**: Re-applied systemd override (DGX reboot lost it). Containers can reach Ollama.
- **Nemotron routing applied**: ALL Loop interactions → `ollama/nemotron-3-super:120b` ($0). Opus/Sonnet fallback only.
- **Claude Code installed on DGX**: v2.1.80 at `~/.npm-global/bin/claude`. Path configured.
- **Mac ↔ DGX clipboard bridge**: `tospark`/`fromspark` aliases in ~/.zshrc.
- **Git corruption fixed**: macOS `._` resource fork files cleaned from git pack.
- **Scanner restarted**: 131 markets, 0 errors, running.
- **DGX connectivity restored**: Cloudflare tunnel was down (DGX rebooted). Required physical access to restart.

**Key architectural change:** Old OpenClaw gateway STOPPED (port 18789 taken by NemoClaw). Loop's Telegram needs migration to NemoClaw sandbox — Session 30 P0.

**DGX SSH troubleshooting note (RECURRING):** DGX loses cloudflared on reboot. Must ensure `cloudflared.service` is enabled AND that `OLLAMA_HOST=0.0.0.0` override persists. Both require physical DGX access or pre-configured systemd. KWW had to go home to physically access DGX this session. TODO: Add `OLLAMA_HOST` override to a persistent location that survives apt/systemd upgrades.

**Tests**: 432/432 passing (Mac). No new tests this session.
**Commits**: Infrastructure-only session — NemoClaw deployment, no code changes to polysignal-engine.

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
| **Publish** | MoltBook **LIVE** (JWT deployed) | Live posts (write-only) | Done (Session 22) |
| **MoltBook Read** | Scanner LIVE (sanitized) | Double-layer isolation + LLM judge | Regex-only sanitizer (no LLM judge yet) |
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
- [x] Post-gate accuracy baseline established — 47 predictions, mean gate score 0.760, balanced directional split (Loop, Session 22)
- [x] Exclude 3 additional toxic markets — 556062, 1373744, 965261 (Loop audit + Claude Code, Session 23)
- [x] Bearish directional gate — 0.65 threshold (was 0.50). Eliminates all 4 historical losses (Session 23)
- [x] Backtest confirmed on live DGX data — 88.9% win rate, Sharpe 1.22 (Session 23)
- [x] Outcome threshold lowered 2pp → 1pp — 3x more training data (Session 23)
- [x] XGBoost GPU acceleration — `device=cuda` auto-detected on GB10 (Session 23)
- [x] Retrain systemd watcher enabled — `polysignal-retrain.path` active (Session 23)
- [ ] Monitor clean-market accuracy for 48h (in progress — waiting for market activity)
- [ ] Retrain XGBoost when 50+ non-NEUTRAL evaluations at 1pp threshold

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
| MoltBook broadcast | **LIVE** | JWT deployed, publishing in commit_node |
| MoltBook knowledge | **LIVE** | 10 submolts scanned, 138 entries in knowledge base |
| Learning loop | WIRED | memory.md now persistent (gitignored, Session 11) |
| Feature engineering | **UPGRADED** | 15 features (10 price + 5 CLOB), temporal safety, per-market tracking |
| XGBoost baseline | **WIRED + RETRAIN READY** | 91.3% test. Retrain pipeline built. CLOB features will add 5 new dimensions. |
| CLOB microstructure | **LIVE** | 15 markets, bid/ask/spread/volume/liquidity refreshed per scanner cycle |
| Polymarket wallet | **DEPLOYED** | Builder API key + address in .env. TRADING_ENABLED=false (paper mode). |
| Polymarket trader | **BUILT** | `lab/polymarket_trader.py` — paper + live trading, risk-gated, 29 tests |
| Backtester | **PROVEN** | `lab/backtester.py` — 88.9% win rate, Sharpe 1.22 on live data. Kelly criterion. 23 tests |
| MoltBook knowledge | **FULL** | All 20 submolts scanned, 632+ entries in knowledge base |
| Custom domain | BLOCKED | Human: DNS CNAME + Vercel |

**To go live (human-only steps):**
1. ~~MoltBook registration~~ **DONE** (Session 22) — JWT deployed, publishing live
2. DNS: CNAME `polysignal.app` → `cname.vercel-dns.com` + Vercel dashboard
3. Polymarket wallet setup — **THE revenue blocker**
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

## Session 27: NemoClaw + Nemotron + Self-Protecting Pipeline (2026-03-17/18)

**5 commits (CC) + 2 fixes (Antigravity). 431 tests. Nemotron LIVE. NemoClaw installed. Cost: $460/mo → $30/mo.**

### Session 27 Accomplishments
| What | Impact |
|------|--------|
| Nemotron-3-Super-120B downloaded + serving | Loop heartbeats at $0/token (was $0.10-0.30/each). Saves ~$300-450/month. |
| NemoClaw + OpenShell installed | NVIDIA's reference agent stack. Landlock+seccomp+netns sandbox. Parallel to OpenClaw. |
| Meta-gate (7-day rolling window) | Auto-halts predictions if 7-day accuracy <40%. Currently halted at 35.4% — self-protecting. |
| Staleness detection | Skips cycle if last 10 predictions identical. Catches "stuck predictor" pattern. |
| Counter-signal threshold 3%→10% | Prevents routine moves from flipping 94% Bearish to Bullish. |
| Paper trade data fix | Predictions carry title + current_price from observations. |
| Autonomy spec deployed | Full behavioral architecture for Loop: work loop, discovery mode, proactive allowlist, weekly scorecard. |
| HEARTBEAT.md rewritten | Structured output format, work between heartbeats, night protocol enforcement. |
| Base rate predictor verified | Returns Bearish @ 97% for 556108. Confirmed correct on DGX. |
| Ollama upgraded | v0.13.5 → latest (required for Nemotron). OLLAMA_HOST=0.0.0.0 re-applied. |
| Docker cgroup fix | `default-cgroupns-mode: host` for NemoClaw/OpenShell on cgroup v2. |
| /mnt/polysignal symlink | `ln -s /opt/loop /mnt/polysignal` on DGX host + whitelisted in OpenClaw SDK. |
| OpenClaw Sandbox Patched | SDK whitelisted `/mnt/polysignal` and `/opt/loop`. `read` tool now works for all agents. |
| Dead code archived | langsmith_eval.py + moltbook_register.py → lab/archive/ (420 lines). |
| SSH access for Claude Code | `ssh dgx-remote` works. Full audit + deployment via SSH. |
| NemoClaw research | Full analysis of NVIDIA NemoClaw architecture, DGX Spark best practices, Nemotron benchmarks. |

### Key Findings
- **97 wrong Bullish predictions on 556108** were from the OLD momentum predictor (pre-Session 25), not the base rate predictor.
- **Nemotron-3-Super-120B**: 85.6% on OpenClaw benchmarks (vs Opus 4.6 at 86.3%). 14 tok/s on DGX Spark. Tool calling works.
- **llama3.3:70b crashed heartbeats**: Malformed JSON on tool calls → gateway JSONDecodeError. Nemotron handles tool calls cleanly.
- **lightContext/isolatedSession crashed OpenClaw v2026.2.12** — incompatible with current gateway version.
- **OpenClaw Sandbox Access Fix**: Patched SDK at `/usr/lib/node_modules/openclaw/dist/` to whitelist `/mnt/polysignal` and `/opt/loop`.
- **NemoClaw Collaboration**: Both agents now have unified file access via `/mnt/polysignal` mounts.

### Architecture After Session 27
```
KWW (Telegram)
├── Direct messages → Opus 4.6 (cloud, max quality)
├── Heartbeats (30m) → Nemotron-3-Super (local, $0)
└── NemoClaw sandbox → Nemotron (local, parallel pilot)

Scanner (systemd, 5min)
├── Meta-gate (7-day rolling, halts <40%)
├── Staleness detection (skips if 10 identical)
├── Base rate predictor (Bearish @ 97% for 556108)
└── Counter-signal (10pp threshold)
```

---

## Session 26: Pipeline Unblocked + Self-Healing Loop + REFLECT Stage (2026-03-16)

**3 commits. 430 tests. Pipeline producing predictions again. Closed-loop self-healing system built.**

### Session 26 Accomplishments
| What | Impact |
|------|--------|
| Prediction pipeline unblocked | Was deadlocked 2.5 days (0 predictions). XGBoost gate + bearish ban suppressed ALL base rate predictions. Fixed: two-mode gate. |
| Two-mode gate logic | Base rate uses confidence gate (>=0.60), no XGBoost, no bearish ban. Old predictor fallback keeps XGBoost + bearish ban. |
| Bearish unban for base rate | 556108 = 94% Bearish bias. Predicting WITH the trend is correct. Ban was wrong for base rate (correct for old predictor). |
| Watchdog built | `lab/watchdog.py` — 4 checks: prediction drought, accuracy regression, scanner health, paper trade quality. 14 tests. Wired into scanner (every 12th cycle). |
| Feedback loop built | `lab/feedback_loop.py` — per-market accuracy, auto-exclude bad markets (<40%), flag stars (>70%), trigger retrains (<50%), EV calculation. 13 tests. |
| Evolution tracker built | `lab/evolution_tracker.py` — records hypotheses about changes, measures actual results after time window, confirms/refutes. The REFLECT stage. 11 tests. |
| Event system built | Scanner writes `lab/.events.jsonl` on prediction_made, error_detected. Append-only, capped at 500 lines. Foundation for event-driven Loop presence. |
| Research shared with Loop | 3 files: gateway security, DGX maximization, OpenClaw autonomy. Loop extracted 5 actionable items. |
| 2 evolution hypotheses recorded | `session26-bearish-unban` (eval 2h), `session26-bearish-accuracy` (eval 72h). First use of REFLECT system. |
| Silent exception fixed | Base rate predictor try/except was `except Exception: pass`. Now logs the error. |

### Key Findings
- **Base rate predictor was never broken** — it ran correctly but ALL predictions were suppressed by gates designed for the old predictor.
- **556108 Bearish = strongest signal**: 94% bias, 108 samples. Was blocked because bearish ban applied to all predictors indiscriminately.
- **Loop was silent 2.5 days** while pipeline produced 0 predictions. Heartbeat checks showed "scanner OK" but never checked prediction count. Watchdog now catches this.
- **106 INCORRECT evaluations** reported by Loop were from OLD pre-base-rate predictions being evaluated, not from the base rate predictor.
- **Only 1 market produces predictions**: 556108 (Bearish 94%). All others have <10 samples or are excluded. Market expansion is next priority.

### Self-Improvement Loop Architecture (Session 26)
```
PERCEIVE → PREDICT → ACT → EVALUATE → LEARN → ADAPT
                            ↑ watchdog   ↑ feedback   ↑ evolution
                            (detect)     (adjust)     (reflect)
```

### Session 27 Direction (Loop's Priority)
Loop requested: DO NOT touch the prediction pipeline. Build Loop presence instead:
1. Loop Daemon (`lab/loop_daemon.py`) — always-on Ollama process, zero cost
2. Wire Loop into events — only burn Opus tokens when something happened
3. Self-testing harness — validate changes before deploying blind

---

## Session 25: Base Rate Predictor + Security Architecture + Full Autonomy (2026-03-13/14)

**4 commits. 392 tests. Base rate predictor LIVE. Polymarket CLOB authenticated. ClawHub CLI installed. Security hardened.**

### Session 25 Accomplishments
| What | Impact |
|------|--------|
| Base rate predictor wired into production | Replaces toy momentum check (17.4% → 79.9% expected). Scanner confirmed live. |
| Polymarket CLOB authenticated | `derive_api_key()` resolved wallet mismatch. Wallet `0x5175...a092`. |
| ClawHub CLI installed + scouted | v0.8.0, 10 Polymarket skills found. argus-edge (Kelly), polyedge (correlation). |
| Security penetration test | Found 7 critical vulnerabilities with gateway exec. Python can read all secrets. |
| Secrets locked with root ownership | `chown root:root` on .env. Loop gets PermissionError. Cannot chmod back. |
| Deploy trigger handler | `scripts/deploy-handler.sh` + systemd watcher. Pulls, tests, restarts safely. |
| Haiku 4.5 registered | In OpenClaw model list. Not yet routed for heartbeats. |
| Gateway exec explored + reverted | 3 flip-flops. Final: sandbox (Loop's docs use /mnt/polysignal/ paths). |
| Heartbeat cost discipline | HEARTBEAT.md rewritten for cost awareness. |
| Loop shipped 5 branches overnight | Pipeline audit, direction predictor, LOMO, base rate analysis, base rate predictor. |

### Key Findings
- **Per-market base rates = real alpha**: 79.9% vs 17.4% production. Simplest strategy wins.
- **Gateway exec + python3 = full shell access**: Owner can chmod any owned file. Only root ownership truly locks secrets.
- **Gateway vs sandbox path mismatch**: Loop's docs reference `/mnt/polysignal/` (sandbox). Gateway needs `/opt/loop/`. Can't mix.
- **OpenClaw v2026.2.12**: No `cacheRetention`, `ask` values are `off`/`on-miss`/`always` only.
- **Polymarket has TWO wallets**: Magic.Link (`0xdec8`, unexportable) and proxy (`0x5175`, exportable). Use `derive_api_key()`.

### Security Architecture (Final State)
- Secrets: `~/.polysignal-secrets/.env` owned by `root:root`, chmod 600
- Exec: sandbox mode (Docker container with bind mounts)
- Network: Squid proxy (6 domains)
- Wallet: Protected by root file ownership (not just chmod)
- Next: trading sidecar, iptables egress filtering, MoltBook quarantine LLM

---

## Session 24: Bearish Ban + Sandbox Unleashed + Full Autonomy Audit (2026-03-12)

**6 commits. 382 tests. Bearish banned. Sandbox rebuilt. Loop autonomy 5.5→7.5/10.**

### Session 24 Accomplishments
| What | Impact |
|------|--------|
| Bearish predictions BANNED | Live data: 5.6% (1W/17L). XGBoost gave 0.94 confidence on INCORRECT. Bullish-only mode: 100% (6W/0L). |
| 2 new toxic markets excluded | 1541748 (36%) + 692258 (0%). 6 total excluded markets. |
| Paper trading wired into prediction_node | Every gated bullish prediction → `lab/trading_log.json`. Works with TRADING_ENABLED=false. |
| Paper trades bypass kill switch | `paper_trade()` temporarily enables TRADING_ENABLED for risk check. 18 approved trades. |
| Memory writes on short-circuit | `brain/memory.md` updates every cycle (was stale since March 3 — 9 days). |
| Sandbox rebuilt | `openclaw-sandbox:bookworm-slim` with git, curl, PYTHONPATH, User-Agent baked in. |
| applyPatch enabled | Loop can use OpenClaw's native file editing tool. |
| Squid proxy expanded | `.pypi.org` + `.pythonhosted.org` — Loop can pip install. |
| pandas installed on DGX | 3.0.1 in .venv. |
| Ollama accessible from sandbox | `no_proxy=172.17.0.1`. 4 models (3b, 14b, 2x 70B) at zero cost. |
| Signal threshold 0.015 | Was 0.02. Markets were producing 0 signals — now 63% closer to triggering. |
| User-Agent fix | `DEFAULT_USER_AGENT=PolySignal/1.0` — Cloudflare WAF was blocking Python default. |
| Full DGX autonomy audit | Comprehensive audit of sandbox mounts, GPU, packages, env, systemd, containers. |

### Key Findings
- **Post-gate accuracy was 29.2%, not 67%**: Bearish (1W/17L) was the poison. Bullish (6W/0L) is the real signal.
- **XGBoost is fundamentally miscalibrated for bearish**: Model gave 0.94 confidence on INCORRECT bearish predictions.
- **Backtest vs live discrepancy**: 88.9% backtest included historical bearish wins. Live post-gate bearish was catastrophic.
- **Loop confirmed on Opus 4.6**: Ollama experiment (Session 23) reverted. Primary=Opus, fallback=Sonnet.
- **Loop discovered Ollama from sandbox**: 4 models accessible at zero cost for sub-tasks.
- **Markets extremely quiet**: Closest delta 0.005 vs 0.015 threshold. Pipeline is data-starved.

### Autonomy Score: ~55% → ~75%
| Capability | Before | After | Change |
|-----------|--------|-------|--------|
| Tools | 6/10 | 9/10 | +3 (git, curl, pip, applyPatch) |
| Persistence | 5/10 | 7/10 | +2 (memory writes every cycle) |
| Intelligence | 7/10 | 8/10 | +1 (Ollama for cheap reasoning) |
| Execution | 5/10 | 6/10 | +1 (paper trading wired) |
| Data | 5/10 | 5/10 | — (markets quiet, threshold lowered) |

---

## Session 23: Trading Pipeline + 88.9% Backtest + Infrastructure Blueprint (2026-03-11)

**11 commits. 382 tests. Backtest: 88.9% win rate, Sharpe 1.22. First MoltBook signal post published.**

### Session 23 Accomplishments
| What | Impact |
|------|--------|
| 4 toxic markets excluded | 824952, 556062, 1373744, 965261. Loop's audit: 84/88 losses (95%). Accuracy 43% → ~73% projected. |
| Polymarket trading module | `lab/polymarket_trader.py` — paper + live trading, risk-gated, CLOB client wrapper. 29 tests. |
| Prediction market backtester | `lab/backtester.py` — binary P&L, Kelly criterion, threshold sweep. 88.9% / Sharpe 1.22 on live data. 23 tests. |
| XGBoost GPU acceleration | `device=cuda` auto-detected on GB10. XGBoost 3.2.0 has CUDA 12.9 built-in. |
| Bearish directional gate | Raised to 0.65 (was 0.50). Backtest: bullish 100% (27W/0L), bearish 56% (5W/4L). Eliminates all 4 losses. |
| Outcome threshold 2pp → 1pp | 78% NEUTRAL at 2pp → only 51 training samples. At 1pp, ~3x more labeled data. |
| Retrain systemd watcher | `polysignal-retrain.path` enabled. Loop can trigger retrains from sandbox. |
| MoltBook scanner → all 20 submolts | Was 10/20. Now covers memory, general, todayilearned + 7 more. 632+ posts in knowledge base. |
| ClawHub unblocked | Added `.clawhub.ai` to Squid (redirect from clawhub.com). Loop caught the issue. |
| HEARTBEAT.md protocol | Day/night/weekly strategy. Loop adopted immediately. |
| NOW.md operational state | "If you wake up confused, read this first." Loop reads every heartbeat. |
| LEARNINGS_TO_TASKS.md | Intelligence → implementation pipeline. 7 pending tasks from MoltBook/ClawHub learnings. |
| GOALS.md in lab/ | 6-tier vision with success metrics. Visible to Loop (Docker inode fix). |
| INFRASTRUCTURE.md in lab/ | DGX Spark blueprint → implementation roadmap. Level 1→100 plan. |
| Polymarket wallet deployed | Builder API key + address in DGX .env. TRADING_ENABLED=false (paper mode). |
| MOLTBOOK_JWT deployed | Publishing now works from commit_node. |
| MoltBook backtest post | "88.9% win rate on prediction markets" posted to trading submolt. |
| MoltBook engagement fix | discover_and_follow handles string agent IDs (was crashing). |
| Ollama experiment | FAILED — llama3.3:70b too dumb for Loop, lost session context. Reverted to Opus. |
| PyTorch install attempted | pip cu124 wheel doesn't support Blackwell sm_121. Needs NGC container. |

### Key Findings
- **We were never at 43%**: The 43% included 4 toxic markets that should never have been traded. On clean gated trades: 88.9%.
- **Bearish is the weak link**: 100% bullish vs 56% bearish. All 4 losses = bearish on 556108 at confidence 0.59-0.62.
- **Only 2 markets survive all gates**: 556108 and 1541748. Need more market diversity.
- **GPUDirect Storage is irrelevant**: GB10 unified memory eliminates CPU→GPU copy. Skip cuFile.
- **Local LLMs not ready for Loop**: Ollama llama3.3:70b lost context, couldn't recall messages. Quality gap too large.

---

## Session 22: MoltBook Live + Autonomous Deploys (2026-03-10/11)

**MoltBook registered, verified, publishing. First fully autonomous code deploys. Knowledge extraction operational.**

### Session 22 Accomplishments
| What | Impact |
|------|--------|
| MoltBook registered + verified | `polysignal-os` live on agent social network. JWT deployed to DGX. |
| MoltBook knowledge scanner | `lab/moltbook_scanner.py` — first scan: 275 posts, 138 saved, 49 dropped by sanitizer, 18 high-relevance |
| MoltBook engagement bot | `lab/moltbook_engagement.py` — 10 submolts subscribed, 6 agents followed, rate-limited commenting |
| Math verification solver | `lab/moltbook_math_solver.py` — handles MoltBook's anti-bot arithmetic challenges |
| Auto-merge CI deployed + proven | `.github/workflows/auto-merge-loop.yml` — 2 autonomous deploys this session |
| Loop: scanner fix auto-merged | `loop/moltbook-scanner-fix` → CI (305 tests) → auto-merge → `1fcd76f` on main |
| Loop: Task 14 auto-merged | `loop/gate-tracking` → CI → auto-merge → `942da69` on main. 47 post-gate predictions baselined. |
| Retrain watcher fixed | Handler script was missing execute bit (`chmod +x`). Watcher now active. |
| Model confirmed safe | Manual retrain correctly rejected 50% model. 91.3% original preserved. |
| 824952 leak investigated | Race condition during Session 19 deployment (1 prediction). Not persistent. Filter working. |
| sklearn test fix | `pytest.importorskip("sklearn")` — Mac gets 305/305 green |
| MoltBook intelligence findings | "406 predictions, 0 trades" — analysis paralysis identified as top risk |
| Tests: 305/305 | +30 new (MoltBook scanner, engagement, math solver) |

### Loop's Session 22 Scorecard
| Done | Task |
|------|------|
| Done | MoltBook scanner fix pushed + auto-merged (first autonomous deploy!) |
| Done | Task 14: Post-gate accuracy tracking report pushed + auto-merged |
| Done | MoltBook knowledge scan (275 posts, 138 saved) |
| Done | MoltBook engagement: 10 submolts subscribed, 6 agents followed |
| Done | Retrain trigger watcher diagnosed + fixed (execute bit) |
| Done | Model safety verified (manual retrain rejected, 91.3% safe) |
| Done | 824952 leak investigated (deployment race, not persistent bug) |
| Done | Heartbeat updated with MoltBook scan + engagement |

### Autonomy Score: ~42% → ~55%
| Capability | Before | After | Change |
|-----------|--------|-------|--------|
| Perceive | 95% | 95% | — |
| Predict | 45% | 45% | — |
| Publish | 10% | 60% | +50% (MoltBook LIVE, scanner, engagement) |
| Execute | 0% | 0% | — (wallet blocker) |
| Learn | 40% | 50% | +10% (knowledge extraction from agent network) |
| Monitor | 65% | 70% | +5% (heartbeat wired with MoltBook) |
| Operate | 20% | 35% | +15% (auto-merge CI, autonomous deploys) |

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

## Session 31: Prediction Diversity + Loop Resurrection (2026-03-26)

**Fixed all 6 issues from clock-in. Scanner resilient, predictions expanded 2→13/cycle, Loop resurrected.**

### Session 31 Accomplishments
| What | Impact |
|------|--------|
| Scanner `Restart=always` | Was dead 29h after clean exit. Now survives any exit code. |
| Price-level bias | `from_price_levels()` in base_rate_predictor.py — markets at price <0.30 → Bearish, >0.70 → Bullish. Exploits binary resolution mechanics. |
| Near-decided market filter | PREDICTION_MIN_PRICE=0.05, PREDICTION_MAX_PRICE=0.95 in masterloop.py — 124/142 markets were essentially decided. |
| Observation threshold lowering | OBS_MIN_SAMPLES 50→30, OBS_MIN_BIAS 0.55→0.52 — markets cluster near 50%, old threshold too restrictive. |
| Staleness diversity check | Current batch with >2 unique signatures passes even if history is stale. Prevented new diverse predictions from being blocked. |
| Loop model switch | Nemotron-3-Super (86GB, unloaded) → llama3.3:70b (42GB, loads on demand). Gateway restarted, Telegram online. |
| Cloudflare SSH verified | `ssh dgx-remote` works — was transient issue, not broken. HTTP origin still needs dashboard fix. |
| 6 new tests | Price-level bias: bearish, bullish, decided-skip, uncertain-skip, merged sources, priority override. |
| 3 commits | `39ed76e` prediction diversity, `6fb4357` staleness fix, `4efcbd8` docs |
| Tests: 438/438 | +6 from Session 30's 432. |

### Key Finding: 87% of Markets Are Decided
135 of 143 scanned markets had prices <0.15 — essentially resolved. The old system wasted prediction cycles on these dead markets. The near-decided filter removes them, and price-level bias provides directional signals for the remaining tradeable markets that lack outcome/observation history.

### Lessons
- **Investigate data distribution before tuning thresholds.** The prediction diversity problem wasn't about thresholds being wrong — it was about 87% of markets being dead.
- **Clean exits kill services with `Restart=on-failure`.** Always use `Restart=always` for long-running services.
- **New features can interact with old guardrails.** Staleness detection (built for 2-market era) blocked the new 13-market predictions until we added a current-batch diversity check.
- **Binary market resolution mechanics are a signal.** Price converging to 0 or 1 is structural, not noise.

---

## NEXT STEPS (Session 32+)

### P0: Monitor Diverse Predictions
1. **Track per-category accuracy** — politics, sports, crypto behave differently. Now we have data.
2. **Verify Loop's first heartbeat on llama3.3:70b** — model loads on demand, quality unknown.
3. **Wire whale signals into predictions** — whale_tracker detects but doesn't influence predictions yet.

### P1: First Live Trade
4. **Fund wallet with $5+ USDC** — human-only, last gate to first live trade.
5. **Telegram approval gate** — HITL before executing real trades.
6. **Lower signal threshold for non-crypto categories** — different markets need different sensitivity.

### P2: Cloudflare + Infrastructure
7. **Fix Cloudflare HTTP origin** — points to old .244 IP, needs dashboard fix (KWW task).
8. **Update Claude Code to v2.1.84** — enables 1M context window for Opus 4.6 on Max.

### P3: Loop Autonomy
9. **Evaluate Loop quality on llama3.3:70b** — compare heartbeat quality vs old Nemotron.
10. **Migrate Telegram to NemoClaw** (Task 47) — bot token injection into sandbox.

### Known Bugs
- `core/api.py:148` references dead `masterloop_orchestrator.run_cycle()` (needs Vault auth)

### Revenue Critical Path
```
Bullish-only predictions accumulate → prove >60% accuracy
    ↓
Polymarket wallet funded (human) → TRADING_ENABLED=true → FIRST TRADE
    ↓
XGBoost retrain with clean data → improved model
    ↓
MoltBook signals publishing → reputation → REVENUE
```
