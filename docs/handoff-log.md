# PolySignal-OS Handoff Log

---

## 2026-04-20 MacBook Session 40 — Formal clock-out (Claude Code)

**Done since 2026-04-17 entry:**
- Ran full Phase 1-4 clock-out protocol (tests, docs, ship).
- Tests: 487/487 pass (Mac, stable since Apr 17 commit).
- Verified DGX sync: `6da6d53` on both Mac and DGX.
- Updated stale docs: `PROGRESS.md` (Session 40 block), `lab/NOW.md` (heartbeat config + cadence + bearish ban state), `CLAUDE.md` (heartbeat section: Sonnet → Haiku, 60m → 120m), `lab/INFRASTRUCTURE.md` (heartbeat model references), `lab/HEARTBEAT.md` (cost discipline rules reflect Haiku reality), `lab/GOALS.md` (Tier 1.2 accuracy target/current updated).
- Verified Loop session on DGX: bound to `claude-haiku-4-5-20251001`, session cost $0.19 on 22K tokens (vs $15.00 on Sonnet before the fix).
- Scanner on DGX at cycle 611, 0 predictions/cycle, 0 errors.
- META-GATE self-healed: 7-day directional now 2W/2L = 50% (was 11W/69L = 13.75% on Apr 17). Halt lifted, but sample is tiny because the scanner's 0 predictions/cycle problem persists.

**State:** Stable. Haiku heartbeats active, cost on track. 0 predictions/cycle is the open Session 41 item.

**Next (Session 41):** Execute P1 (per-category eval horizons) to unstick the prediction gates. P2-P5 queued in LOOP_TASKS.md.

**Watch out:** The sticky-session bug still exists in OpenClaw — if Karl changes `defaults.model.primary` again, he must also delete `~/.openclaw/agents/main/sessions/sessions.json`'s `agent:main:main` entry AND restart the gateway, or the old session will keep winning. Documented in `CLAUDE.md` Model Routing section.

**Codebase health:** Stable. No new tech debt introduced this clock-out. Bearish ban is the one known temp suppression; removal is gated on Session 41 P2.

---

## 2026-04-17 MacBook Session 40 (Claude Code)

**Done:**
- **Diagnosed $50 API burn Apr 5-16**: 41,304 Sonnet calls (60min heartbeats × 11 days with 10-15k input tokens each) + 206,337 failover retry loops after Anthropic balance hit zero. Billing-rejected 400s aren't billed, so the loop itself didn't cost — the preceding successful Sonnet heartbeats did.
- **Cost cut**: heartbeat model `anthropic/claude-sonnet-4-6` → `anthropic/claude-haiku-4-5-20251001`, interval `60m → 120m`, workspace MEMORY.md trimmed 11344 → 2763 bytes (archived to `brain/memory-archive.md`). Projected cost ~$0.04/day (was ~$2-5/day on heartbeats alone). Gateway hot-reloaded at 16:01:23, restarted clean.
- **META-GATE pushback**: Karl suggested the 13% accuracy was a NEUTRAL-in-denominator bug. Verified from raw data: code at `workflows/masterloop.py:316-323` already excludes NEUTRAL; 13.75% is the real directional figure (11W/69L). No code change; flagged for Karl.
- **Accuracy root-cause analysis**: only 4 unique markets had directional predictions in 7d. Market 567560 (Orbán Hungarian PM) drove 41 of 69 losses. Forwarded analysis to Loop for independent verification.
- **Loop caught a real error**: I diagnosed Orbán as "slow-trending-up mean-reverter" — wrong. Loop correctly identified it as a market that crashed from 0.295 → 0.035. First session where Loop functioned as a genuine second opinion rather than echoing.
- **Bearish ban extended to base rate predictor** (`lab/base_rate_predictor.py:288-361`): `BAN_BEARISH_OUTPUT = True` module constant + suppression filter at end of `predict()`. Catches both dominant-Bearish and counter-signal Bullish→Bearish flips. 4 new tests + 1 retargeted. Codex reviewed, green-lit with 3 low-severity polish items queued for Session 41. 487 pass / 1 skip / 4 deselect.
- **Session 41 agenda locked in LOOP_TASKS.md**: P1 eval metric redesign per-category horizons (crypto 4h / sports 24h / politics 7d), P2 price-level bias fix for crashing markets, P3 invert failover chain (Ollama primary for heartbeats), P4 Gemma 4 31B spike vs llama3.3, P5 Claude Managed Agents + Advisor pattern spike.

**State:**
- Scanner: cycle 373+, 151 markets, 0 predictions/cycle, META-GATE HALT active (will self-heal as stale Apr 10-11 Orbán data ages out of the 7d window)
- Gateway: restarted 16:03:41 CEST, Haiku 4.5 on 120m cadence active
- Trading log: 7342 total, 7154 resolved, 6094W/1060L = 85.2% lifetime, 60% last 100
- Accuracy: 7d directional 13.75% (11W/69L, 113 NEUTRAL), real problem is long-horizon eval metric mismatch
- Tests: **487 pass / 1 skip / 4 deselect** on Mac (+5 new base rate ban tests from baseline 482)
- Loop: heartbeat model switched, workspace trimmed, full history archived at `brain/memory-archive.md`

**Next:**
- Session 41: execute P1-P5 priorities in LOOP_TASKS.md, then clear the 3 Codex polish items before re-enabling Bearish output
- Watch META-GATE self-heal — crashed Orbán predictions age out of 7d window within 24-36h of Apr 17
- Monitor first Haiku-powered heartbeat (~18:03 CEST Apr 17) — journal should show `model=claude-haiku-4-5-20251001`
- Re-run DGX test suite to confirm 487 pass there too (run today locally, DGX not tested this session)
- Top up Anthropic API if credits still low (failover retry loops ran Apr 13-17 until balance >0)

**Watch out:**
- Bearish ban is a temporary suppression. The underlying price-level bias bug at `base_rate_predictor.py:217-257` still creates Bearish synthetic biases for every market <0.30 — they just get filtered at output. Until Session 41 P2 fixes the source, `self.biases` carries dead entries that occupy the "market is covered" slot in `masterloop.py:437`, diverting those markets away from momentum fallback (though momentum has its own bearish ban too, so no regression).
- No suppression counter/metric was added to `predict()` — when re-enabling Bearish in Session 41, we'll have no before/after baseline for "how much traffic was the filter absorbing." Queued as a Codex polish item.
- Failover retry loop bug in OpenClaw gateway still exists (Session 41 P3 fixes it by inverting the chain). If credits hit zero again, the gateway will spin in the tight loop — CPU waste, not cost waste, but log noise and potential thermal impact.
- The 4h eval horizon on 6-month political markets is an architectural mismatch. The 13.75% number will keep whipsawing until Session 41 P1 lands per-category horizons. Don't over-trust the META-GATE's accuracy-floor rejection until then.

**Loop overnight:**
- Monitor META-GATE self-heal trajectory — report 7d directional accuracy each heartbeat; flag when it crosses back above 40% (expect within 24-36h)
- Do NOT trigger retrain, do NOT modify EXCLUDED_MARKETS (cosmetic — scanner already skips 567560 via near-decided filter)
- First Haiku heartbeat at ~18:03 CEST: confirm model + interval in ack
- Between heartbeats: no code changes. Session 41 is P1-P5 work.

**Codebase health:** Growing. Base rate predictor has two layered bans (old for momentum, new for base rate output) — document merging/unifying them in Session 41 if possible. `workflows/masterloop.py` is 1097 lines and has accumulated enough session-specific workarounds that a structural refactor will land eventually; not urgent.

**Lessons:**
- **First genuine multi-agent verification event.** Forwarded the accuracy analysis to Loop via `openclaw agent --channel telegram --to 1822532651 --deliver --message ...`. Loop independently queried `data/prediction_outcomes.json`, ran its own computation, and caught my "trending-up" error — Orbán actually crashed from 0.295 → 0.035, opposite of what I claimed. This is meaningful progress toward Dibia-style multi-agent coordination: Loop functioned as a second opinion rather than echoing the architect. Karl's framing: "this is exactly how multi-agent verification should work." Pattern to reuse: when making non-trivial diagnostic claims, forward data + conclusion to Loop for independent verification before acting.
- **META-GATE pushback worked.** User instinct was that the metric excluded NEUTRAL incorrectly. Verifying against raw data *before* editing the code prevented a pointless "fix" that would have broken working logic. Default to skepticism on metric bugs — check the math first, change second.
- **Bearish ban is symptomatic, not causal.** We're suppressing an output because of an upstream bug in price-level bias on crashing markets. Queued the root-cause fix (P2) but the ban is the kind of technical debt that accumulates if Session 41 doesn't actually land. Put "re-enable Bearish after P2" on the Session 41 definition-of-done.
- **Codex review caught a matrix-coverage gap** (weak counter-signal on Bearish-dominant bias) that my own test-writing missed. Fixed in-session; lesson is that the codex-reviewer agent meaningfully improves test completeness when the change has non-trivial logic branches.

---

## 2026-04-14 MacBook Session 39 (final)

**Done:** Fixed NEUTRAL evaluation problem (89.6% → should drop). Threshold 0.3pp→0.05pp, dual-horizon (4h+24h), volatility gate. Killed voice_bot.py, fixed fallback chain, IDENTITY.md, gateway restart. Loop caught 6 DGX test failures — fixed (volatility gate unknown markets + e2e fixture isolation). Discovered real-time Loop comms via `openclaw agent` CLI.
**State:** Working. Scanner cycle 205, 0 predictions/cycle (gates suppressing — pre-existing), 0 errors. 483 tests pass on DGX.
**Next:** Check accuracy recovery. If 0 predictions persists, lower base rate gate 0.55→0.50. XGBoost retrain with clean data. Investigate 60.5% vs 44.9% accuracy gap (Loop flagged). Then DEEP-DIVE → SPIKE → TEACH → HEALTH-CHECK.
**Watch out:** 7-day accuracy at 42% (contaminated by old data). 60.5% Phase B analysis vs 44.9% live directional — these measure different things, need understanding. 0 predictions/cycle means no new evaluable data accumulating.
**Loop overnight:** Monitor accuracy trend + predictions/cycle. Flag if accuracy <40%. Compare 4h vs 24h after enough data. Do NOT change code or trigger retrain.
**Codebase health:** Growing — needs DEEP-DIVE + HEALTH-CHECK (Session 40).

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
