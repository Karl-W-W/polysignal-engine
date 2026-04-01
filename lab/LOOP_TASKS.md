# Loop Task Queue
# Updated: 2026-04-01 (Session 35 — Claude Code)
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

## SESSION 36 CHANGES (2026-04-01)

### Infrastructure Fixes (Claude Code)

1. **Anthropic API key ROTATED** — old exposed key from Session 33 revoked. New key deployed to openclaw.json.

2. **Claude Sonnet wired as primary model** — `agents.defaults.model.primary=anthropic/claude-sonnet-4-6`. **BLOCKED: account needs credits.** Falls back to llama3.3:70b. Once funded, Loop will use Claude for Telegram conversations and tool calls.

3. **Paper trade evaluation DEPLOYED** — `evaluate_paper_trades()` in TradingLog, wired into scanner perception node. Evaluates trades >4h old against current prices. Win/loss + P&L written to trading_log.json.

4. **Per-market accuracy tracking** — persistent `per_market` dict in prediction_outcomes.json. No longer lost when 500-record cap rotates.

5. **Host watchdog installed** — cron every 5min checks scanner + gateway + Ollama. Auto-restarts if down.

6. **Book insights extracted** — `lab/BOOK_TODO.md` with 30 action items from "Designing Multi-Agent Systems" (Dibia).

### What's Working Right Now

- **Scanner**: Cycle 1217+, 142 markets, 8-9 predictions/cycle, 0 errors, 5 days uptime
- **Paper trading**: 519 real trades, NOW auto-evaluating (win/loss + P&L)
- **Accuracy**: 50.7% (208W/202L) — declining, needs per-category analysis
- **Meta-gate**: Active (40% threshold)
- **Whale tracker**: Running at cycles 9/21/33
- **Watchdog**: Host-level (5min cron) + in-scanner (every 12th cycle)
- **Tests**: 446/446 passing
- **Model**: Claude Sonnet configured but blocked by billing. Falls back to llama3.3.

---

## ACTIVE TASKS — Priority Order

### P0: Report Real Data on Heartbeats (ongoing)

**Why:** llama3.3 narrates code instead of executing it and fabricates numbers. Until Claude Sonnet is funded, be honest about limitations.

**What to do:**
1. Run `python3 --version` — confirm exec works
2. Run `cat /mnt/polysignal/lab/.scanner-status.json` — read real scanner data
3. Run `python3 -c "import json; print(json.load(open('/mnt/polysignal/lab/trading_log.json'))['total_trades'])"` — verify trading log
4. Report REAL numbers on Telegram — not fabricated ones
5. If ANY command fails, report "COMMAND FAILED: [reason]"

### P1: Monitor Real Paper Trades (ongoing)

**Why:** Paper trades now use real Polymarket conditionIds. Need to track quality.

**What to do:**
1. On each heartbeat, check `lab/trading_log.json` for new trades
2. Report: count, markets, directions, confidence range
3. After 50+ real trades: per-market accuracy breakdown
4. Flag any trades that look wrong (fake IDs, Unknown Market, 0xfake)

### P2: Prepare for First Live Trade ($1 max)

**Why:** TRADING_ENABLED will be set to true soon. Need approval gate.

**What to do:**
1. Build Telegram approval gate in `execute_trade()`:
   - Before CLOB order, send trade proposal to Telegram
   - Wait for KWW reply (YES/NO), 5-min timeout
   - Timeout = REJECT (safe default)
2. Test with paper trades first (log what WOULD be sent)
3. Push to `loop/approval-gate` for review

### P3: MoltBook Engagement (ongoing)

**Why:** Building reputation. Currently 4 karma.

**What to do:**
1. Run MoltBook scan: `python3 /mnt/polysignal/lab/moltbook_scanner.py all`
2. Run engagement: `python3 /mnt/polysignal/lab/moltbook_engagement.py cycle`
3. Comment on 2-3 trending posts with real data (accuracy reports, architecture)
4. Target: 50+ karma, 10+ followers

### P4: Proactive Heartbeats (behavior change)

**Why:** Heartbeats should report what MATTERS, not just "I'm alive."

**What to do:**
1. Read IDENTITY.md and HEARTBEAT.md on each session
2. Include in each heartbeat:
   - Scanner health (1 line: cycle, predictions, errors)
   - Any high-confidence predictions (>0.85)
   - Any whale alerts since last heartbeat
   - Any accuracy changes
3. If nothing changed: "Scanner OK, cycle N, no changes." ONE LINE. Stop.
4. Between heartbeats: pick a task from this list and execute it

### P5: Code Contributions (nightly build pattern)

**Why:** Loop should ship small useful things during off-hours.

**Ideas for nightly builds:**
- Per-category accuracy analysis (politics vs sports vs crypto)
- Feature importance analysis from XGBoost
- Trading log summary with estimated P&L
- Market volatility scanner (which markets move most?)
- Improved whale signal formatting for Telegram

**How to ship:**
1. Write code in `lab/`
2. Write tests in `tests/`
3. Push to `loop/your-feature` via git trigger
4. CI auto-merges if tests pass

---

## COMPLETED TASKS (Session 34 and earlier)

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
