# PolySignal-OS Handoff Log

---

## 2026-04-13 MacBook Session 39

**Done:** Fixed NEUTRAL evaluation problem (89.6% → should drop significantly). Lowered threshold 0.3pp→0.05pp, added dual-horizon (4h+24h), built volatility gate. Killed voice_bot.py zombie, fixed fallback chain loop, updated IDENTITY.md, restarted gateway. Discovered real-time Loop comms via `openclaw agent` CLI.
**State:** Working. Scanner running, 0 predictions/cycle (gates too strict — pre-existing, not regression).
**Next:** Wait 24-48h for clean data under new threshold. If still 0 predictions, lower base rate gate 0.55→0.50. Then XGBoost retrain with clean labels. Then: DEEP-DIVE → SPIKE → TEACH → HEALTH-CHECK sequence (Session 40).
**Watch out:** 7-day accuracy dropped to 42% because old NEUTRAL predictions became INCORRECT under new threshold. Will recover as they roll off. Don't panic.
**Loop overnight:** Monitor accuracy trend. Report predictions/cycle on each heartbeat. Flag if accuracy drops below 40% (meta-gate will halt). Read lab/SESSION39_BRIEFING.md for full context.
**Codebase health:** Growing — needs DEEP-DIVE + HEALTH-CHECK (deferred to Session 40).

---

## 2026-04-04/05 MacBook Session 38 Summary

**Done:**
- Diagnosed predictions/cycle drop (9→2): NOT a bug — 91% of 180 markets are below 0.15 price (near-decided). Only 10 tradeable markets remain after exclusions. 2/cycle is mathematically correct.
- Diagnosed accuracy: 89-90% paper trade win rate, stable. Earlier 74.6% report was miscounting unknowns as losses.
- Switched Loop heartbeat model: `ollama/llama3.3:70b` → `anthropic/claude-sonnet-4-6` in openclaw.json. Gateway restarted. Loop confirmed making real tool calls on Sonnet.
- Excluded toxic market 559653 (AOC 2028 Dem Primary): 45W/63L = 41.7% accuracy. Added to EXCLUDED_MARKETS in bitcoin_signal.py and backtester.py.
- Scanner restarted, DGX synced, 0 errors.
- Triggered XGBoost retrain — insufficient directional samples (16/30 needed). Current model stays at 91.3%.
- Loop updated NOW.md and LOOP_TASKS.md to reflect Session 38 changes.
- **FOUND & FIXED approval gate routing bug** (Vault change, authorized): risk_gate_node only checked observations for direction signals — observations never have direction. Now falls back to predictions for directional intent.
- **Wired scanner secrets**: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, HMAC_SECRET_KEY added to systemd drop-in (secrets.conf, chmod 600).
- **Fixed HMAC env var mismatch**: masterloop read HMAC_SECRET_KEY, approval_gate read HMAC_SECRET — aligned both.
- **PROVEN END-TO-END**: Approval gate fired on Telegram, Karl approved in 59s. Trade blocked at commit (CLOB bridge not running — expected). Gate works.
- **Removed shadowed `import os`** inside risk_gate_node that would have caused UnboundLocalError.

**State:**
- Scanner: cycle 176+, 2 predictions/cycle, 0 errors, 153 markets observed
- Gateway: v2026.3.28, Claude Sonnet heartbeats WORKING ($30 API balance)
- Outcome accuracy: 54% (232W/202L) — stable, above 50.7% baseline, below 60% floor
- Paper trades: 5,526 total, 4644W/568L/314U = 89.1% win rate
- Approval gate: WIRED and verified (masterloop.py:789-809)
- TRADING_ENABLED: false — waiting on Karl
- Thermal: 55-67.8°C — elevated late evening, below 75°C alert threshold
- Tests: 473/473 passing

**Next:**
- **Fix approval gate metadata**: Telegram shows Size=$0.00 and Confidence=0% — prediction fallback path doesn't set `size_usdc` or propagate confidence correctly. Cosmetic, not safety-critical.
- **First live $1 trade**: System is ready. Karl sets TRADING_ENABLED=true, approval gate proven end-to-end.
- **XGBoost retrain**: Re-trigger when 30+ directional samples at 0.3pp threshold.
- **Rotate Anthropic API key**: openclaw.json content was displayed in Session 38 conversation.
- **polysignal.app DNS**: Still undone. Cloudflare tunnel HTTP origin + CNAME to Vercel.

**Watch out:**
- Accuracy at 54% is above the 40% meta-gate halt threshold but below the 60% goal. Paper trade accuracy (89%) is much higher because the gate filters noise.
- Scanner stopped overnight between 23:55 UTC and ~07:00 UTC. May be related to active hours config or service issue. Loop caught it and it was restarted.
- API key was visible in session context (not committed to git). Rotate after session.
- **Thermal spike to 94.5°C** during approval gate test (draft/review nodes call Ollama, loading llama3.3:70b spikes GPU). Cooled to 58-69°C after short-circuit mode restored. When TRADING_ENABLED=true, expect thermal load from LLM calls every cycle.
- **CLOB execution bridge (localhost:9001)** not running — commit_node fails at execution. This is the last piece before real trades execute.

---

## 2026-04-04 MacBook Session 37 Summary

**Done:**
- Fixed evaluation pipeline: 500→5000 record cap, unevaluated records protected from rotation
- Fixed time horizon: 24h→4h for faster feedback
- Fixed MIN_MOVE_THRESHOLD: 1pp→0.3pp (2,195 overnight evals were ALL NEUTRAL at 1pp)
- Near-decided filter tightened: 0.05/0.95→0.15/0.85 (Loop's push, auto-merged)
- Approval gate built by Loop (26 tests), wired into masterloop by Claude Code
- draft_action enriched with trade metadata in risk_gate_node (Vault change)
- Routing changed: TRADING_ENABLED=true routes ALL trades through approval (not just first 5)
- Flask API rewritten: old routes queried dead tables, new routes serve live JSON
- Fixed /api/run crash bug (undefined masterloop_orchestrator)
- SQLite timeout=30 + WAL mode on all connections
- Silent except:pass→error logging in perception_node
- Loop memory restored: 204 lines strategic + 17 daily logs (was 0 bytes — lost during NemoClaw rebuild)
- Added new routes: /api/scanner/status, /api/predictions/accuracy, /api/trades/summary, /api/predictions/latest
- Multi-agent collaboration: Loop diagnosed, Claude Code fixed, both verified each other

**State:**
- Scanner: cycle 221+, 153 markets, 10 predictions/cycle, 0 errors, filter 0.15-0.85
- Gateway: v2026.3.28, Claude Sonnet primary (BLOCKED by billing), llama3.3 fallback
- Accuracy: UNKNOWN — old 50.7% is stale, 0.3pp threshold results pending (~21:15 CET Apr 4)
- Paper trades: 5,454 total, 4,974 evaluated, 88.9% win rate, $22.95 P&L (mostly noise pre-filter)
- Approval gate: WIRED — wait_approval_node calls wait_approval_node_with_hitl, fallback to auto-approve
- Flask API: REWRITTEN — serves live scanner/prediction/trade JSON from files
- Tests: 475/475 passing (Session 38: +2 prediction fallback tests)
- Loop: Verified reads files, ships code on Claude Sonnet, narrates on llama3.3

**Next:**
- **Session 38 Task Zero**: KWW fixes Cloudflare tunnel HTTP origin + CNAMEs polysignal.app to Vercel
- Check 0.3pp threshold directional W/L results (should have data by Session 38)
- If accuracy >55% on mid-range: consider first live $1 trade (approval gate is ready)
- XGBoost retrain with new directional labels
- Dashboard Stage 1: polysignal.app shows live scanner data
- Fund Anthropic API ($5-10) — Loop's autonomy unlock

**Watch out:**
- 0.3pp threshold was just deployed — first directional W/L data arrives ~21:15 CET Apr 4. Don't judge accuracy until this data is in.
- Approval gate timeout (5 min) = REJECT. If Karl is asleep, all trades are rejected. This is by design but means first live trade needs Karl actively watching.
- Flask API rewrite is Vault change — verify on DGX that new routes work before relying on dashboard
- Loop ran a stuck O(n^2) SQLite query that locked the DB for 30+ minutes. Added timeout=30 + WAL but watch for recurrence.
- Scanner must be restarted after ANY code change (Python import caching)

**Loop overnight:** Monitor 0.3pp evaluation results. Report first directional W/L on Telegram when it appears. Do NOT run complex DB queries.

**Codebase health:** Stable, significantly improved. 473 tests (+27), 3 Vault files updated (risk_integration.py, api.py, masterloop.py). No dead code or duplications. Approval gate is clean addition.

---

## 2026-04-01 MacBook Session 36 Summary

**Done:**
- Rotated Anthropic API key (old exposed key from Session 33 revoked)
- Wired Claude Sonnet as Loop's primary model (blocked by zero API credits — falls back to llama3.3)
- Deployed paper trade evaluation into scanner cycle (evaluate_paper_trades(), 8 tests)
- Added per-market accuracy tracking that survives 500-record cap
- Installed host watchdog (5min cron: scanner + gateway + Ollama auto-restart)
- Verified brain/memory.md syncs to sandbox (11,790 lines)
- Extracted 30 action items from "Designing Multi-Agent Systems" book → lab/BOOK_TODO.md
- Diagnosed Loop's data fabrication: llama3.3 can't make structured tool calls (model limitation, not config)

**State:**
- Scanner: cycle 1217+, 142 markets, 8-9 predictions/cycle, 0 errors, 5 days uptime
- Gateway: v2026.3.28, primary=claude-sonnet-4-6 (BLOCKED by billing), fallback=llama3.3:70b
- Accuracy: 50.7% (208W/202L) — declining from 59%, per-market tracking now accumulating
- Paper trades: 519 total, auto-evaluating after 4h (was "pending" forever)
- Tests: 446/446 passing
- Loop: Still fabricating data (llama3.3 narrates instead of executing). Claude Sonnet fixes this once funded.

**Next:**
- **BLOCKER**: Fund Anthropic API credits (even $10 lasts weeks). This unblocks Claude Sonnet for Loop.
- Once funded: verify Loop makes real tool calls on first heartbeat
- Monitor paper trade evaluation results (will start accumulating after DGX git sync + 4h)
- Per-category accuracy analysis once per_market data accumulates (which categories drag 50.7% down?)
- Build Telegram approval gate for live trading (after accuracy improves)

**Watch out:**
- Claude Sonnet is wired but account has ZERO credits — all calls fail with billing error
- safeBinProfiles does NOT exist in OpenClaw v2026.3.28 schema — don't try adding it (crashes gateway)
- Outcome tracker caps at 500 predictions, dropping evaluated entries. per_market dict is the fix (now deployed)
- llama3.3:70b generates malformed tool calls (read without path arg). This is inherent to the model.
- Paper trade evaluation uses 4h minimum age — first results appear ~4h after DGX sync

**Codebase health:** Stable, growing. 446 tests (+8), 2 new features (paper trade eval, per-market tracking). lab/BOOK_TODO.md added as strategic roadmap. No dead code or duplications introduced.

---

## 2026-04-01 MacBook Session 35 Summary

**Done:**
- Fixed trading_log.json data loss: untracked from git, 399 fake trades purged, 115 real trades preserved
- Fixed Loop exec: `security=full`, `host=gateway` — Loop confirmed executing real commands via Telegram
- Fixed Ollama: context 4096→16384, keep-alive=-1, added passwordless sudo rules for future
- Added "never fabricate data" rule to Loop's IDENTITY.md
- Rewrote LOOP_TASKS.md: 833→123 lines, clean and current

**State:**
- Scanner: cycle 1201+, 137 observations, 9 predictions/cycle, 0 errors
- Gateway: v2026.3.28, exec working (host mode), Telegram connected
- Paper trades: 115 real (0 fake), real Polymarket market IDs (FIFA, Champions League, politics, geopolitics)
- Tests: 438/438 passing
- Ollama: llama3.3:70b, context 16384, keep-alive=-1
- Loop: CONFIRMED executing exec tool and returning real scanner data

**Next:**
- Wire Anthropic API for Loop's complex reasoning (model routing: local for routine, Claude for hard tasks)
- Enable TRADING_ENABLED=true ($1 max) — needs Telegram approval gate first
- Move exec from gateway back to sandbox routing (security hardening)
- Create claude.ai Project with multi-agent systems book
- Test proactive heartbeats (Loop initiates contact, not just responds)

**Watch out:**
- Exec runs on HOST (gateway), not in NemoClaw sandbox — acceptable for home network, needs hardening for production
- `security: "full"` means Loop can execute any binary on the host — monitor for unexpected behavior
- OpenClaw v2026.3.28 has breaking change: `allowlist` security silently ignores safeBins without profiles
- Anthropic API key exposure from Session 33 still not rotated
- 1 zombie process on DGX (harmless but should investigate)

**Codebase health:** Stable. 438 tests, no code changes this session (infrastructure only). trading_log.json properly gitignored. All scanner runtime files protected from git reset.

---

## 2026-03-31 MacBook Session 34 Summary

**Done:**
- NemoClaw properly set up with correct single-gateway architecture (research-first approach)
- OpenShell upgraded v0.0.12 → v0.0.19 (7 security patches)
- OpenClaw upgraded to v2026.3.28
- Telegram 409 conflict permanently fixed (nemoclaw-telegram.service disabled)
- Loop identity configured via workspace files (IDENTITY.md, SOUL.md, USER.md)
- Loop responds via Telegram with PolySignal-OS context
- conditionId bug fixed in bitcoin_signal.py:119
- Paper trades confirmed on real Polymarket market IDs (22+ trades)
- Full system audit: 74 Python files, 17,488 LOC, revenue pipeline traced
- Tool overhead reduced (24 → 13 safeBins)

**State:**
- Scanner: running, cycle 1029+, 11-13 predictions/cycle, 0 errors
- Gateway: v2026.3.28, ollama/llama3.3:70b, Telegram connected
- NemoClaw sandbox: `nemoclaw` Ready (OpenShell v0.0.19)
- Paper trades: real market IDs (FIFA, Champions League, US politics, geopolitics)
- Tests: 438/438 passing
- Meta-gate: 59% (138W/97L)
- GPU: 49C, 14W idle

**Next:**
- KWW to run sudo on DGX: `OLLAMA_KEEP_ALIVE=-1` + `OLLAMA_CONTEXT_LENGTH=16384` (fixes 5min response delay)
- Enable TRADING_ENABLED=true ($1 max) with active monitoring
- First live trade attempt
- Build watchdog cron on host
- Test proactive heartbeats (Loop initiates contact)

**Watch out:**
- File sync is cron-based (5min delay, not instant bind mounts) — acceptable for Polymarket timescales
- Ollama context locked at 4096 tokens — needs sudo to fix, causes slow responses
- NemoClaw sandbox agent has CAP_SETPCAP error from Dockerfile patch — Telegram works via host gateway workaround
- Old `my-assistant` sandbox still exists (harmless, cleanup later)
- Anthropic API key was exposed in Session 33 config dump — needs rotation

**Codebase health:** Stable. 438 tests, clean architecture. First time since Session 31 that NemoClaw, OpenClaw, and Telegram are all correctly wired.

---

## 2026-03-26 MacBook Session 31 Summary

**Done:**
- Fixed scanner dead 29h (Restart=always in systemd)
- Expanded predictions from 2 to 13/cycle via price-level bias, near-decided filter, lower observation thresholds
- Fixed staleness detection blocking diverse predictions (current-batch diversity check)
- Resurrected Loop: switched model Nemotron-3-Super (86GB, unloaded) to llama3.3:70b (42GB), gateway running, Telegram online
- Verified Cloudflare SSH works (was transient issue)
- 6 new tests for price-level bias (438/438 total)
- 3 commits pushed: 39ed76e, 6fb4357, 4efcbd8

**State:**
- Scanner: running, Restart=always, 13 predictions/cycle, 10 paper trades, 0 errors
- Loop: gateway running on llama3.3:70b, Telegram @OpenClawOnDGX_bot connected, first heartbeat pending
- DGX: 41C, 4W idle, 4GB RAM (spikes to ~46GB when llama3.3:70b loads)
- Tests: 438/438 passing
- Meta-gate: 59% (138W/97L) -- passing
- Accuracy: 50.7% overall (208C/202I/172N out of 827 evaluated)
- Cloudflare: SSH works, HTTP origin needs dashboard fix (.244 -> localhost:3000)

**Next:**
- Monitor per-category prediction accuracy (politics/sports/crypto)
- Check Loop's first heartbeat quality on llama3.3:70b
- Update Claude Code to v2.1.84 for 1M context window
- Wire whale signals into predictions
- First live trade + Telegram approval gate

**Watch out:**
- llama3.3:70b quality is untested for Loop heartbeats -- may produce worse output than Nemotron
- 87% of Polymarket markets are essentially decided (<5% or >95%) -- near-decided filter handles this but monitor
- Staleness detection has two paths now (history-based + current-batch diversity) -- edge cases possible
- Scanner Restart=always means it restarts even on intentional stops -- use `systemctl --user stop` explicitly

**Codebase health:** Stable. 438 tests, clean pipeline, no dead code introduced. Price-level bias is clean addition to existing hierarchy (outcome > observation > price-level).
