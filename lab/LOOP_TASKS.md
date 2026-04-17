# Loop Task Queue
# Updated: 2026-04-17 (Session 40 — Claude Code)
#
# WHY THIS FILE EXISTS:
# TASKS.md and PROGRESS.md are mounted as individual file bind mounts in Docker.
# These capture the inode at container creation time and don't see host updates.
# This file lives in lab/ which is a DIRECTORY mount → always syncs correctly.
#
# Loop: READ THIS FILE instead of /mnt/polysignal/TASKS.md for current tasks.
# After completing a task, mark it [x] here AND report on Telegram.

---

## YOUR ENVIRONMENT — READ THIS FIRST

**Paths inside sandbox:**
```
/sandbox/                        — Your home directory
/sandbox/.openclaw/workspace/    — IDENTITY.md, SOUL.md, etc.
```

**Host file sync (every 5 min via cron):**
```
/mnt/polysignal/lab/           → /opt/loop/lab/           (read/write)
/mnt/polysignal/workflows/     → /opt/loop/workflows/     (read/write)
/mnt/polysignal/tests/         → /opt/loop/tests/         (read/write)
/mnt/polysignal/core/          → /opt/loop/core/          (READ-ONLY)
/mnt/polysignal/agents/        → /opt/loop/agents/        (read/write)
/mnt/polysignal/.venv/         → /opt/loop/.venv/         (READ-ONLY)
/mnt/polysignal/data/          → /opt/loop/data/          (READ-ONLY)
/mnt/polysignal/brain/         → /opt/loop/brain/         (read/write)
```

## Tools Available

- **exec**: python3, bash, git, curl, sqlite3, cat, ls, find, grep, head, tail, wc, date, echo, pip3
- **applyPatch**: enabled — native file editing
- **read/write**: /sandbox, /tmp
- **Ollama**: `http://172.17.0.1:11434` (no_proxy) — llama3.3:70b, qwen2.5:14b, llama3.2:3b, deepseek-r1:70b
- **Network**: Squid proxy — gamma-api.polymarket.com, clob.polymarket.com, .moltbook.com, .clawhub.ai, .pypi.org, .pythonhosted.org

## Trigger Files (escape hatches to host)

```bash
echo "restart" > /mnt/polysignal/lab/.restart-scanner    # Restart scanner
echo "deploy"  > /mnt/polysignal/lab/.deploy-trigger      # Pull + test + restart
echo "retrain" > /mnt/polysignal/lab/.retrain-trigger     # Retrain XGBoost
cat > /mnt/polysignal/lab/.git-push-request << EOF        # Push to GitHub
branch: loop/your-feature
message: Brief description
files: lab/your_file.py
EOF
```

---

## SESSION 37 CHANGES (2026-04-03)

### Evaluation Pipeline Fix (Claude Code)

1. **Record cap raised 500→5000** — predictions were being rotated out in ~4.6h, before 24h evaluation horizon. Now unevaluated records are protected from rotation. Evaluated records dropped first.

2. **Paper trade evaluation WORKING** — 2,999 trades evaluated: **89.3% win rate** (2678W/321L), **$18.47 P&L**. The system was performing well all along — we just couldn't see it.

3. **Time horizon 24h→4h** — outcome evaluations now happen at 4h (was 24h). Feedback loop 6x faster.

4. **SQLite hardened** — timeout=30 + WAL mode on all DB connections. Prevents "database is locked" from concurrent access or Loop's runaway queries.

5. **Error logging** — silent `except: pass` in perception_node replaced with `print(f"⚠ ... failed: {e}")`. Errors now visible in scanner logs.

6. **Scanner restarted** — was running since Mar 26. Session 36 code changes existed on disk but Python import caching meant they never loaded. **Always restart scanner after code changes.**

7. **Workspace MEMORY.md restored** — was 0 bytes. Populated with key project context.

### What's Working Right Now

- **Scanner**: 149 markets, 9 predictions/cycle, 0 errors. Restarted Apr 3.
- **Paper trading**: 3,214 trades, 2,999 evaluated — **89.3% win rate, $18.47 P&L**
- **Outcome evaluation**: Re-enabled with 4h horizon. First fresh data expected ~4h after restart.
- **Meta-gate**: Rebuilding (insufficient recent data, will self-correct in ~4h)
- **Whale tracker**: Running at cycles 9/21/33
- **Watchdog**: Host-level (5min cron) + in-scanner (every 12th cycle), 0 alerts
- **Tests**: 447/447 passing (+1 new unevaluated protection test)
- **Model**: Claude Sonnet configured but blocked by billing. Falls back to llama3.3.
- **WARNING**: Do NOT run correlated subqueries on observations DB (167MB). Use GROUP BY.

---

## ACTIVE TASKS — Priority Order (Session 41 agenda, set by Karl 2026-04-17)

### P1: Redesign eval metric for long-horizon markets

**Why:** Current eval in `lab/outcome_tracker.py:239-253` compares prediction direction against 4h price delta. For political election markets with 6+ month horizons (Orbán/Magyar Hungary PM, JD Vance 2028), 4h noise dominates real directional signal. Session 40 data: market 567560 scored 0W/41L — all Bullish calls evaluated against a crash from 0.29 → 0.035 over hours, not the actual resolution outcome weeks away.

**What to do:**
1. Implement per-category evaluation horizons. Proposed: crypto=4h, sports=24h, politics=7d.
2. Add `category` field to market metadata (source: Gamma API `tags` or manual mapping).
3. Extend `EVAL_HORIZONS` dict in `outcome_tracker.py`. Route `evaluate_outcomes()` by category.
4. Backfill: re-evaluate last 14 days of predictions under new horizons, measure accuracy delta.
5. New test matrix: each category × horizon combination.

### P2: Fix base rate predictor price-level bias on crashing markets

**Why:** Session 31's price-level bias (`base_rate_predictor.py:217-257`) fires Bullish on high-price markets and Bearish on low-price markets via resolution mechanics. But for markets in freefall (Orbán: 0.29 → 0.035), this produces confident-wrong Bullish calls because the entry price is still above the 0.30 threshold while the trajectory is down. Session 40 data: 10W/31L across 41 Bearish and Bullish calls on market 567560.

**What to do:**
1. Add price trajectory check to `from_price_levels()`: look back 24h, compute price-velocity.
2. If |price_velocity| > 0.05pp/hour AND direction matches trajectory → skip the market (crashing; mean-reversion assumption fails).
3. Alternative: gate the confidence by observed volatility — high-vol markets get lower bias strength.
4. Tests: simulate crashing market (prices 0.35 → 0.30 → 0.25), confirm price-level bias is suppressed.

### P3: Invert failover chain — Ollama primary for heartbeats

**Why:** Session 40 found 206,337 failover decisions logged Apr 5-16 when Anthropic balance hit zero. Gateway's failover logic has a bug: Sonnet billing-reject → "fallback" → switches back to Sonnet → retries → infinite loop. 400s aren't billed so no cost burn, but it's pathological CPU waste and log noise.

**What to do:**
1. Edit `~/.openclaw/openclaw.json` on DGX: change `agents.defaults.heartbeat.model` from `anthropic/claude-haiku-4-5-20251001` to `ollama/llama3.3:70b`.
2. Add fallback chain `heartbeat.fallbacks: [anthropic/claude-haiku-4-5-20251001]` (escalation, not primary).
3. Hot-reload or restart gateway.
4. Verify: heartbeats run on local Ollama (zero API cost), Haiku only fires when heartbeat logic explicitly escalates (alerts, Karl messages).
5. Projected cost: $0.04/day → ~$0.00/day on routine heartbeats, ~$0.15/day with occasional Haiku escalation.

### P4: SPIKE — Evaluate Gemma 4 31B vs llama3.3:70b for local tool reliability

**Why:** Current local model (llama3.3:70b) "narrates tool calls instead of executing them" per NOW.md. Gemma 4 31B has stronger tool-calling benchmarks and fits in DGX memory easily. If it executes reliably, the Loop Daemon + Ollama-primary heartbeat chain becomes viable for real autonomy.

**What to do:**
1. `ollama pull gemma4:31b` (or current closest).
2. Run a tool-reliability test harness: 50 synthetic tasks requiring exec/read/write, measure % executed vs narrated.
3. Compare against llama3.3:70b baseline.
4. Report decision: swap primary local model, keep both, or stay on llama.

### P5: SPIKE — Evaluate Claude Managed Agents API (advisor pattern)

**Why:** Anthropic's Managed Agents (April 8, GA) plus Advisor Tool (April 9 beta) enable a fast-executor + high-intelligence-advisor pattern. Could let us run Haiku as the heartbeat executor with Sonnet as an on-demand advisor for complex decisions, replacing the current "one model does everything" architecture.

**What to do:**
1. Read current docs at docs.anthropic.com for Managed Agents + Advisor Tool.
2. Build a minimal PoC: heartbeat calls Haiku, escalates to Sonnet advisor on alert trigger.
3. Measure: cost per call (executor vs advisor), latency, accuracy of advisor intervention.
4. Decision: integrate into OpenClaw or defer until OpenClaw supports these natively.

---

## CODEX POLISH (from Session 40 base rate ban review — low priority)

These are cleanup items flagged during Codex review of the Bearish ban. Not urgent but should be done before re-enabling Bearish output in Session 41:

- [ ] Add suppression counter/metric to `predict()` ban branch so we have a baseline ("how many Bearish predictions got banned per cycle") for Session 41 rollback calibration
- [ ] Consider `confidence=0.3` instead of `0.0` in the ban return path — aligns with the "insufficient data" degradation semantics already used elsewhere in `predict()`
- [ ] Consider making `from_price_levels()` skip creating Bearish synthetic biases while `BAN_BEARISH_OUTPUT=True` — keeps `self.biases` consistent with actual downstream behavior

---

## RESIDUAL LOOP HEARTBEAT TASKS (ongoing)

### Accuracy + predictions monitoring
- Report 7-day rolling accuracy + predictions/cycle each heartbeat
- Flag if 7-day dips below 40% (META-GATE halt trigger)
- Run `get_accuracy_by_horizon()` after 24h of fresh data

### Paper trade tracking
- Monitor `lab/trading_log.json` for new trades
- After 24h of dual-horizon data: compare 4h vs 24h accuracy
- Investigate the 60.5% (Phase B) vs 44.9% (live directional) gap

### MoltBook engagement (ongoing)
- Run scan + engagement cycles during quiet periods
- Comment on trending posts with real data (accuracy reports, architecture)
- Target: 50+ karma, 10+ followers

### Proactive heartbeats (cost-optimized, Session 40)
- HEARTBEAT_OK short-circuit: ≤50 output tokens when nothing changed
- Full report only on: thermal >75°C, accuracy swing >5pp, scanner stalled, new trade, Karl message
- Escalate to Sonnet only when Karl asks directly or alert requires reasoning

### Nightly builds
- Per-category accuracy (politics vs sports vs crypto)
- XGBoost feature importance
- Trading log P&L summary
- Market volatility scanner
- Improved whale signal formatting
- Ship via `loop/*` branches → CI auto-merges if tests pass

---

## COMPLETED TASKS

- [x] Bearish ban extended to base rate predictor (Session 40, Claude Code) — 5.6% directional acc over 7d, 4 new tests, 487 pass
- [x] Heartbeat model cut Sonnet→Haiku 4.5, cadence 60m→120m (Session 40, Claude Code) — ~25-50× cost reduction
- [x] Workspace MEMORY.md trimmed 11344→2763 bytes, full archive at brain/memory-archive.md (Session 40)
- [x] Session 40 root cause for API burn: 60min Sonnet heartbeats × 11 days + 206K failover retry loops from zero-balance period
- [x] META-GATE math verified correct — NEUTRAL already excluded (Session 40 pushback on assumed bug)
- [x] Loop verified Claude Code's analysis independently, caught "trending-up" error (Session 40 — first real second-opinion event)
- [x] voice_bot.py killed — 409 Telegram conflict resolved (Session 39, Loop)
- [x] Fallback chain fixed — removed duplicate Sonnet (Session 39, Claude Code)
- [x] IDENTITY.md updated to match reality (Session 39, Claude Code)
- [x] MIN_MOVE_THRESHOLD 0.3pp→0.05pp — 9x samples, accuracy up (Session 39)
- [x] Dual-horizon evaluation — 4h + 24h (Session 39)
- [x] Volatility gate — frozen market filter (Session 39)
- [x] e2e test isolation fix — 6 DGX failures resolved (Session 39)
- [x] conditionId fix deployed (Session 34)
- [x] NemoClaw rebuilt with OpenShell v0.0.19 (Session 34)
- [x] Host gateway owns Telegram, no bridge conflicts (Session 34)
- [x] Market expansion 13 → 137 (Session 28)
- [x] Hybrid prediction system (Session 31)
- [x] Price-level bias + near-decided filter (Session 31)
- [x] Whale tracker wired (Session 28)
- [x] Watchdog + feedback loop + evolution tracker (Session 26)
- [x] Base rate predictor primary (Session 25)
- [x] Bearish ban for old predictor (Session 24)
- [x] Paper trading wired (Session 24)
- [x] MoltBook registered + scanner + engagement (Session 22)
- [x] Auto-merge CI (Session 22)
- [x] All Loop interactions → local Ollama (Session 29)
- [x] Security hardening — exec reverted to sandbox (Session 25)

---

## KEY REFERENCE FILES

| File | Purpose |
|------|---------|
| `lab/NOW.md` | Your operational state — read this if confused |
| `lab/LOOP_TASKS.md` | This file — your task queue |
| `lab/GOALS.md` | Master goal list (6 tiers) |
| `lab/HEARTBEAT.md` | Heartbeat protocol |
| `lab/LEARNINGS_TO_TASKS.md` | Intelligence → implementation pipeline |
| `lab/trading_log.json` | Paper trade history (gitignored, safe from reset) |
| `lab/.scanner-status.json` | Scanner health (cycle, predictions, errors) |
| `lab/.events.jsonl` | Event log (prediction_made, whale_detected) |
| `lab/.watchdog-alerts` | Failure alerts |
| `lab/.whale-signals.jsonl` | Whale detection log |
| `lab/.evolution-log.jsonl` | Hypothesis tracking |
