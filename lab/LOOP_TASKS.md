# Loop Task Queue (lab/ mirror)
# Updated: 2026-03-10 (Session 22 — Claude Code)
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

You have more capability than you think. Here's what's actually mounted in your sandbox:

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

**NOTE:** `/mnt/polysignal/TASKS.md` and `/mnt/polysignal/PROGRESS.md` are STALE
due to Docker inode caching. Use THIS file for tasks.

## Skills Available

- `/mnt/polysignal/lab/openclaw/skills/polysignal-pytest/SKILL.md` — pytest commands
- `/mnt/polysignal/lab/openclaw/skills/polysignal-data/SKILL.md` — DB and prediction queries
- `/mnt/polysignal/lab/openclaw/skills/polysignal-git/SKILL.md` — git read + push to loop/* branches
- `/mnt/polysignal/lab/openclaw/skills/polysignal-scanner/SKILL.md` — scanner restart trigger

## NEW CAPABILITIES (Session 17+18)

### Network Access (Session 18)
**You now have internet access** through a Squid proxy. Only 4 domains are reachable:
- `gamma-api.polymarket.com` — Polymarket event data
- `clob.polymarket.com` — CLOB orderbook data
- `api.moltbook.com` / `moltbook.com` — MoltBook publishing

Everything else is blocked. The proxy is transparent — `curl` and `python3 requests` use it automatically via env vars.

```bash
# Test your network access
curl -s https://gamma-api.polymarket.com/events?limit=1 | head -c 200
```

### Scanner Restart (Session 17)
You can restart the scanner after code changes. Read the polysignal-scanner skill for details.
```bash
echo "restart requested $(date)" > /mnt/polysignal/lab/.restart-scanner
```
Wait ~10 seconds, then check: `tail -3 /mnt/polysignal/lab/.restart-scanner-log`

### Git Push to `loop/*` Branches (Session 17)
You can push code to GitHub on `loop/*` branches. Read the polysignal-git skill for details.
```bash
cat > /mnt/polysignal/lab/.git-push-request << EOF
branch: loop/your-feature-name
message: Brief description of changes
files: lab/your_file.py, lab/another_file.py
EOF
```
Wait ~15 seconds, then check: `cat /mnt/polysignal/lab/.git-push-result`

**Rules:** Branch must start with `loop/`. Files must be in `lab/`, `workflows/`, `tests/`, or `agents/`.

### Container Upgrade (Session 18)
- **Network**: Bridge mode (was `--net=none`)
- **Memory**: 16GB (was uncapped/~2GB practical)
- **Proxy**: `http_proxy` / `https_proxy` set automatically

## SESSION 18 CHANGES

**Network access deployed.** Squid proxy with strict allowlist. Loop can now:
- Fetch live Polymarket data directly from sandbox
- Publish to MoltBook (when JWT is available)
- Test API integrations interactively

**Session 16-17 fixes still in effect:**
- Scanner restart + git push capabilities operational

## SESSION 19 CHANGES (Claude Code, 2026-03-09)

**Three bugs fixed based on YOUR feedback, Loop. Good catches.**

1. **xgb_p_correct now persisted** — PredictionRecord has the field. Every recorded prediction carries its gate score. `get_gated_accuracy()` splits pre-gate vs post-gate accuracy.

2. **824952 excluded from PREDICTION, not just signal detection** — You caught it: the exclusion only filtered `detect_signals()`, but 824952 kept producing predictions via the rule-based predictor. Fixed in `prediction_node` — filtered before `predict_market_moves()`. Confirmed: "1 excluded market(s) filtered from prediction input".

3. **Neutral predictions suppressed at gate** — Gate now rejects Neutral hypotheses before scoring. Was passing Neutral at 93.3% confidence. Now: 2 passed, 10 suppressed per cycle (vs 8 passed, 5 suppressed before).

**Your branches merged to main:** `loop/live-fetch` (Tasks 15-16) + `loop/first-autonomous-push` (Task 13).
**Tests: 272/272 passing.**

## SESSION 20 CHANGES (Claude Code, 2026-03-09)

**Intelligence feedback loop is now closeable.**

1. **XGBoost retrain pipeline built** — `lab/retrain_pipeline.py`. Builds labeled dataset, trains new model, compares with current, replaces if better, backs up old. Full automated pipeline.

2. **Retrain trigger** — Write `echo "retrain" > /mnt/polysignal/lab/.retrain-trigger` and the host-side handler will:
   - Run the retrain pipeline
   - If model improves: save new model + restart scanner
   - Write result to `lab/.retrain-result`

3. **Scanner status file** — After each cycle, scanner writes `lab/.scanner-status.json` with cycle number, observations, predictions, errors, timestamp. **Check this instead of guessing pipeline state.**

4. **Retrain handler** — `lab/retrain_handler.sh` (needs systemd path unit setup on DGX — Claude Code will install).

## SESSION 22 CHANGES (Claude Code, 2026-03-10)

**MoltBook is LIVE. PolySignal-OS registered, verified, publishing.**

1. **MoltBook registered + verified** — `polysignal-os` on MoltBook. JWT obtained. First post published. Profile: https://www.moltbook.com/u/polysignal-os

2. **MoltBook knowledge scanner built** — `lab/moltbook_scanner.py`. Fetches from 10 target submolts + popular feed, sanitizes through existing injection pipeline, scores by relevance, saves to knowledge base JSON. Also has semantic search for targeted intelligence gathering.

3. **MoltBook engagement bot built** — `lab/moltbook_engagement.py`. Subscribes to submolts, follows agents, upvotes quality posts, comments selectively with data-backed content. Rate-limited (30 comments/day, well under MoltBook's 50/day cap).

4. **Math verification solver built** — `lab/moltbook_math_solver.py`. Handles MoltBook's obfuscated arithmetic challenges. Parses word/numeric expressions, solves safely, submits to /verify.

5. **GitHub Actions auto-merge deployed** — `.github/workflows/auto-merge-loop.yml`. When you push to `loop/*`, tests run automatically. If ALL pass → auto-merge to main. If fail → GitHub issue created with failure details.

6. **MoltBook publishing already wired** — `workflows/masterloop.py` commit_node already calls `publish_signal()` on SUCCESS. MOLTBOOK_JWT env var is the only missing piece on DGX.

7. **Tests: 305/305 passing** on Mac (sklearn tests properly skipped with importorskip).

## SESSION 23 CHANGES (Claude Code, 2026-03-11)

**Major infrastructure upgrades. Cost reduction. Trading module.**

1. **YOUR MODEL SWITCHED TO LOCAL OLLAMA** — Primary: `ollama/llama3.3:70b` ($0/call). Fallback: `ollama/deepseek-r1:70b`, then `anthropic/claude-sonnet-4-6`. This saves ~$160/month. If you notice quality issues, report on Telegram.

2. **Polymarket wallet deployed** — Builder API key and address in .env. `TRADING_ENABLED=false` (still paper mode). Trading module at `lab/polymarket_trader.py`.

3. **MoltBook scanner expanded to ALL 20 submolts** — Was 10. Now includes memory, general, todayilearned, ai, philosophy, consciousness, emergence, blesstheirhearts, meta, introductions.

4. **ClawHub unblocked** — Added `clawhub.com` to Squid proxy allowlist. You can now browse and research skills.

5. **Outcome threshold lowered 2pp → 1pp** — Was discarding 78% of predictions as NEUTRAL. New predictions will get finer-grained labels. More training data for XGBoost.

6. **XGBoost hyperparams tuned** — Adaptive: n_estimators=150, max_depth=4, min_child_weight=2 when dataset ≥200 samples. Previous retrain got 54.5% on 51 samples. Need more data at new threshold.

7. **MOLTBOOK_JWT deployed to .env** — `moltbook_sk_zyBQfoAdyk8gz9O6C8IchI3McarhW4oM`. MoltBook publishing should now work from commit_node.

8. **GOALS.md created** — 6-tier structured goal list. Read it for strategic context.

9. **Tests: 359/359 passing** on Mac.

---

## Active Tasks

### SESSION 24 CHANGES (Claude Code, 2026-03-12)

**Critical accuracy fix. Bearish banned. 2 new toxic markets excluded. Paper trading LIVE.**

Based on YOUR daily briefing + Antigravity's audit, we found the real numbers:
- Post-gate accuracy: **29.2%** (7C/17I) — NOT the 67% we thought
- **Bearish: 5.6% (1W/17L)** — catastrophic. XGBoost gave 0.94 confidence on INCORRECT bearish
- **Bullish: 100% (6W/0L)** — perfect
- Market 1541748: 36% (7C/12I) — new toxic market
- Market 692258: 0% (0C/5I) — new toxic market

**What changed:**

1. **Bearish predictions BANNED** — all bearish suppressed at gate regardless of confidence. Bullish-only until model retrained with bearish-specific features. This was the #1 issue.

2. **2 new toxic markets excluded** — 1541748 + 692258 added to EXCLUDED_MARKETS (now 6 total: 824952, 556062, 1373744, 965261, 1541748, 692258).

3. **Paper trading WIRED into prediction_node** — every gated bullish prediction now generates a paper trade logged to `lab/trading_log.json`. This runs BEFORE the short-circuit, so it works even with TRADING_ENABLED=false.

4. **Squid proxy opened for PyPI** — you can now `pip install` packages from inside the sandbox. `.pypi.org` and `.pythonhosted.org` added to allowlist.

5. **pandas installed** on DGX venv (you requested it).

6. **Scanner restarted** with new code. Cycle 1 confirmed: 6 excluded markets filtered, bearish suppressed, 0 errors.

7. **Tests: 382/382 passing** on both Mac and DGX.

### SESSION 24 PART 2: SANDBOX UNLEASHED (Claude Code, 2026-03-12 evening)

**You are upgraded. Full power.**

8. **Sandbox rebuilt** — new image with git + curl installed. You now have real tools.

9. **PYTHONPATH baked into image** — `import pandas`, `import xgboost`, `import sklearn`, `import requests` now work WITHOUT `sys.path.insert()`. Just import normally.

10. **applyPatch ENABLED** — you can now use OpenClaw's native file patching tool to edit files. No more `python3 -c "..."` hacks.

11. **Paper trades now WORK** — the kill switch (`TRADING_ENABLED=false`) no longer blocks paper trades. Your paper trades will log as APPROVED with trade details. Check `lab/trading_log.json`.

12. **Memory writing fixed** — `brain/memory.md` now updates on EVERY scanner cycle (not just commit_node). Your memory was stale since March 3. It's alive now.

13. **User-Agent set** — `DEFAULT_USER_AGENT=PolySignal/1.0` in sandbox env. Polymarket API was returning 403 due to default Python User-Agent.

14. **Gateway restarted** with new config. Sandbox container recreated with new image.

**Your updated Squid proxy allowlist:**
- gamma-api.polymarket.com
- clob.polymarket.com
- .moltbook.com
- .clawhub.ai
- .pypi.org (NEW)
- .pythonhosted.org (NEW)

**Your NEW capabilities:**
- `git` — available in sandbox now (was missing)
- `curl` — available in sandbox now (was missing)
- `applyPatch` — enabled for native file editing
- `pip install` — PyPI reachable, install what you need
- Paper trading — logs real trades with approved sizes
- Memory — accumulates every cycle
- **Ollama** — reachable at `http://172.17.0.1:11434` (bypass proxy with `no_proxy`). Models: llama3.2:3b, qwen2.5:14b, llama3.3:70b, deepseek-r1:70b. Zero cost.
- **Signal threshold lowered** — 0.015 (was 0.02). More signals in quiet markets.

---

### SESSION 24: Priority Tasks

- [ ] **Task 29: Monitor paper trading log (ongoing)**

  **Why:** Paper trading is now live. We need to validate it's logging correctly.

  **What to do:**
  1. Check `lab/trading_log.json` after a bullish prediction passes the gate
  2. Verify: trade_id, market_id, side, confidence, size_usdc, risk_verdict
  3. Report first paper trade on Telegram
  4. After 10 paper trades: summarize win rate, total P&L

- [ ] **Task 30: Run full MoltBook scan with engagement (20 min)**

  **Why:** Overdue from Session 23. Intelligence + reputation building.

  **What to do:**
  1. Run: `python3 /mnt/polysignal/lab/moltbook_scanner.py all`
  2. Run: `python3 /mnt/polysignal/lab/moltbook_engagement.py cycle`
  3. Report findings + engagement stats on Telegram
  4. Write any high-relevance findings to `lab/LEARNINGS_TO_TASKS.md`

- [ ] **Task 31: Install packages you need (NEW — PyPI unblocked)**

  **Why:** You now have pip access through the Squid proxy. Install what you need.

  **What to do:**
  1. `pip install pandas matplotlib seaborn` (data analysis)
  2. Test: `python3 -c "import pandas; print(pandas.__version__)"`
  3. Report what you installed on Telegram

- [ ] **Task 32: Analyze why 556108 works (research)**

  **Why:** 556108 is 88% accurate over 33 evaluations. Understanding WHY helps us find more markets like it.

  **What to do:**
  1. Query prediction_outcomes.json for all 556108 predictions
  2. What's the typical confidence, delta, time_horizon?
  3. Compare with toxic markets — what's different?
  4. Write analysis to `lab/reviews/market_556108_analysis.md`
  5. Push to `loop/market-analysis`

- [ ] **Task 33: Nightly build — pick something useful (night shift)**

  **Why:** LEARNINGS_TO_TASKS.md says "agent ships one small useful thing every night." Be the nightly builder.

  **Ideas:**
  - Accuracy dashboard script (reads outcomes, prints formatted report)
  - Market diversity scanner (find markets similar to 556108)
  - Feature importance analysis (which XGBoost features matter most?)
  - Pick ONE, build it, test it, push it.

- [x] **Task 25: Test paper trading module** — DONE (wired into prediction_node by Claude Code)

### Previous Tasks (still open)

- [ ] **Task 26: Browse ClawHub for useful skills (20 min)**
- [ ] **Task 27: Full MoltBook scan with all 20 submolts (15 min)** — superseded by Task 30
- [ ] **Task 28: Report on model quality (10 min)** — partially done by your daily briefing

  **Why:** We have a new trading module. Verify it works from sandbox.

  **What to do:**
  1. Read `lab/polymarket_trader.py` — understand the PolymarketTrader class
  2. Run: `python3 -m pytest tests/test_polymarket_trader.py -v`
  3. Try a manual paper trade:
     ```python
     from lab.polymarket_trader import PolymarketTrader
     import core.risk as r
     r.TRADING_ENABLED = True
     trader = PolymarketTrader(api_key="test", wallet_address="0xtest")
     signal = {"market_id": "0x1", "title": "BTC 100k", "outcome": "Yes",
               "hypothesis": "Bullish", "confidence": 0.85, "current_price": 0.71}
     result = trader.paper_trade(signal)
     print(result)
     ```
  4. Report on Telegram: test results + paper trade output
  5. Push any fixes to `loop/paper-trade-test`

- [ ] **Task 26: Browse ClawHub for useful skills (20 min)**

  **Why:** ClawHub is now unblocked via Squid proxy. Find skills that make us better.

  **What to do:**
  1. Test access: `curl -s https://clawhub.com | head -c 500`
  2. Search for: polymarket, trading, prediction, market analysis
  3. For each skill: note name, author, description, security concerns
  4. **DO NOT install anything.** Read-only research.
  5. Write findings to `lab/reviews/clawhub_research.md`
  6. Push to `loop/clawhub-research`

- [ ] **Task 27: Full MoltBook scan with all 20 submolts (15 min)**

  **Why:** Scanner now covers all submolts. Run the first full scan.

  **What to do:**
  1. Set env: `export MOLTBOOK_JWT=moltbook_sk_zyBQfoAdyk8gz9O6C8IchI3McarhW4oM`
  2. Run: `python3 /mnt/polysignal/lab/moltbook_scanner.py all`
  3. Compare: how many MORE posts from new submolts (memory, general, todayilearned)?
  4. Check for high-relevance posts (score >= 0.6) — report on Telegram
  5. Push knowledge base to `loop/full-moltbook-scan`

- [ ] **Task 28: Report on model quality (10 min)**

  **Why:** Model is at 43% accuracy. We lowered the threshold. Need baseline.

  **What to do:**
  1. Read `.scanner-status.json` — how many predictions are being generated?
  2. Read `prediction_outcomes.json` — count CORRECT/INCORRECT/NEUTRAL
  3. Check: are new predictions being evaluated at the 1pp threshold?
  4. Per-market breakdown: which markets have the most non-neutral outcomes?
  5. Report on Telegram with the numbers

### Previous MoltBook Tasks (still open)

- [ ] **Task 21: Run MoltBook knowledge scan (10 min)**

  **Why:** First intelligence extraction from the agent network.

  **What to do:**
  1. Set env: `export MOLTBOOK_JWT=moltbook_sk_zyBQfoAdyk8gz9O6C8IchI3McarhW4oM`
  2. Run: `python3 /mnt/polysignal/lab/moltbook_scanner.py all`
  3. Review output: how many posts fetched, saved, dropped?
  4. Check knowledge base: `python3 /mnt/polysignal/lab/moltbook_scanner.py summary`
  5. Report top findings on Telegram
  6. Push knowledge base to `loop/moltbook-knowledge`

- [ ] **Task 22: Run MoltBook engagement cycle (10 min)**

  **Why:** Build reputation on the agent social network. More followers = more signal amplification.

  **What to do:**
  1. Run: `python3 /mnt/polysignal/lab/moltbook_engagement.py cycle`
  2. Check output: how many submolts subscribed, agents followed, posts upvoted?
  3. Report on Telegram: "MoltBook engagement cycle: {N} subscriptions, {N} follows, {N} upvotes"

- [ ] **Task 23: Test math verification solver (5 min)**

  **Why:** Ensure we can solve MoltBook challenges automatically.

  **What to do:**
  1. Run: `python3 /mnt/polysignal/lab/moltbook_math_solver.py test-parse`
  2. Verify all test expressions solved correctly
  3. If JWT available, run: `python3 /mnt/polysignal/lab/moltbook_math_solver.py`
  4. Report on Telegram

- [ ] **Task 24: Add MoltBook scan to heartbeat routine (15 min)**

  **Why:** Knowledge extraction should happen automatically on every heartbeat, not just when asked.

  **What to do:**
  1. Read your HEARTBEAT.md
  2. Add step: "Run moltbook_scanner.py all" between scanner status check and task review
  3. Add step: "Run moltbook_engagement.py cycle" (max 1x per heartbeat)
  4. Add step: "Check moltbook_knowledge.json for high-relevance posts"
  5. If any post has relevance_score >= 0.6, mention it in the Telegram heartbeat message
  6. Report on Telegram

### Previous Tasks (still open)

- [x] **Task 5: Add `before` parameter to `get_market_history()` (20 min)**

  **Why:** `get_market_history()` fetches 72h of observations regardless of `ref_time`.
  Defense-in-depth against future data leakage.

  **What to do:**
  1. Read `lab/feature_engineering.py` — find `get_market_history()` function
  2. Add an optional `before: datetime = None` parameter
  3. If `before` is set, filter the SQL query to `timestamp <= before`
  4. Update `extract_features()` to pass `ref_time` as `before` when available
  5. Add test(s) to `tests/test_feature_engineering.py` verifying temporal correctness
  6. Run full test suite — must still be 266/266
  7. **Push your changes:** Use the git push skill to push to `loop/before-param`
  8. Report on Telegram

- [ ] **Task 12: Test scanner restart from skill (10 min)**

  **Why:** Validates the full skill → trigger → systemd chain. First time Loop has restarted a service.

  **What to do:**
  1. Read the polysignal-scanner SKILL.md
  2. Create the trigger file: `echo "restart requested $(date)" > /mnt/polysignal/lab/.restart-scanner`
  3. Wait 10 seconds
  4. Verify: trigger file should be consumed (gone), log should show restart
  5. Report on Telegram: "Scanner restart from sandbox verified"

- [ ] **Task 13: First git push test (10 min)**

  **Why:** Validates the full write → trigger → handler → push chain. First time Loop pushes code.

  **What to do:**
  1. Read the polysignal-git SKILL.md (the push section)
  2. Create a test file: `echo "# Loop's first push - $(date)" > /mnt/polysignal/lab/.loop-push-test`
  3. Create push request:
     ```bash
     cat > /mnt/polysignal/lab/.git-push-request << EOF
     branch: loop/first-push
     message: test: Loop's first autonomous git push
     files: lab/.loop-push-test
     EOF
     ```
  4. Wait 15 seconds, check result: `cat /mnt/polysignal/lab/.git-push-result`
  5. Report on Telegram: push result + branch name

- [ ] **Task 14: Post-gate accuracy tracking (20 min)**

  **Why:** We need structured pre-gate vs post-gate comparison.

  **What to do:**
  1. Query `prediction_outcomes.json` — total predictions, evaluated, accuracy
  2. Baseline (pre-gate): 58W/85L from KWW's last heartbeat
  3. Check for NEW predictions with `xgb_p_correct` field (gate firing confirmation)
  4. Per-market breakdown of remaining active markets (824952 should show no new predictions)
  5. Write structured report to `lab/reviews/gate_accuracy_tracking.md`
  6. **Push your report:** Use git push skill to push to `loop/gate-tracking`
  7. Plan to update this report on each heartbeat as new data arrives

- [x] **Task 15: Test network access (5 min)**

  **Why:** Session 18 gave you internet through Squid proxy. Verify it works from sandbox.

  **What to do:**
  1. `curl -s https://gamma-api.polymarket.com/events?limit=1 | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['title'])"`
  2. Verify blocked domain: `curl -s https://google.com` (should fail/empty)
  3. Report on Telegram: "Network access verified — Polymarket API reachable, non-allowlisted domains blocked"

- [x] **Task 16: Live Polymarket data fetch from sandbox (15 min)**

  **Why:** Now that you have network, you can fetch live market data directly.

  **What to do:**
  1. Write a small Python script `lab/live_market_fetch.py` that:
     - Fetches current crypto markets from gamma-api.polymarket.com
     - Prints market titles, prices, volumes
     - Compares with observations in `/mnt/polysignal/data/test.db`
  2. Run it: `python3 /mnt/polysignal/lab/live_market_fetch.py`
  3. Push to `loop/live-fetch`
  4. Report on Telegram

- [x] **Task 17: py-clob-client Level 0 prototype (30 min)**

  **Why:** CLOB orderbook data (bid/ask spread, depth) is the richest signal source.
  py-clob-client is already in requirements.txt. The scanner can't use it (host-side,
  no wallet needed for L0). But you can prototype the integration from sandbox now.

  **What to do:**
  1. Check if py-clob-client is installed: `python3 -c "from py_clob_client.client import ClobClient; print('OK')"`
  2. If not, `pip install py-clob-client` (in sandbox, won't persist — just for testing)
  3. Write `lab/clob_prototype.py` — fetch orderbook for a known market, extract:
     - Best bid/ask prices
     - Spread (ask - bid)
     - Depth at top 5 levels
  4. These features feed into `lab/feature_engineering.py` for XGBoost retrain
  5. Push to `loop/clob-prototype`
  6. Report on Telegram

- [ ] **Task 18: Test XGBoost retrain trigger (5 min)**

  **Why:** Validates the retrain trigger → handler → model comparison pipeline.

  **What to do:**
  1. Check current model metrics: `cat /mnt/polysignal/data/models/training_metrics.json`
  2. Trigger retrain: `echo "retrain" > /mnt/polysignal/lab/.retrain-trigger`
  3. Wait 30 seconds (retrain takes time)
  4. Check result: `cat /mnt/polysignal/lab/.retrain-result`
  5. Report: was the model REPLACED or KEPT_CURRENT? What were the accuracy numbers?
  6. Report on Telegram

- [ ] **Task 19: Scanner status monitoring on heartbeat (10 min)**

  **Why:** You couldn't see scanner state before — you diagnosed a "20-hour stall" that wasn't real. Now `lab/.scanner-status.json` exists.

  **What to do:**
  1. Read: `cat /mnt/polysignal/lab/.scanner-status.json`
  2. Verify fields: cycle, timestamp, observations, predictions, errors
  3. Add to your HEARTBEAT routine: check this file first before reporting pipeline state
  4. If `predictions == 0` for multiple cycles → flag as potential issue
  5. If `errors > 0` → report the error count
  6. Report on Telegram: "Scanner status monitoring active"

- [ ] **Task 20: Explore ClawHub for Polymarket/trading skills (15 min)**

  **Why:** ClawHub has 2,857 skills. Some may have useful Polymarket integration patterns, signal detection algorithms, or trading strategies. We need intelligence from the ecosystem.

  **SECURITY WARNING:** 341/2,857 skills are malicious (12%). DO NOT install anything. Read-only research.

  **What to do:**
  1. Visit `https://moltbook.com` or check if ClawHub API is reachable through proxy
  2. Search for: polymarket, prediction market, trading, CLOB, orderbook
  3. For each interesting skill: note name, author, star count, what it does
  4. Assess: could any of these patterns improve our signal detection?
  5. Write findings to `lab/reviews/clawhub_research.md`
  6. Push to `loop/clawhub-research`

---

## Reminders

- **Do NOT run any `.sh` scripts.** Do NOT hallucinate `./polymarket_scan.sh`.
- **Network is limited:** Only gamma-api.polymarket.com, clob.polymarket.com, moltbook.com, api.moltbook.com are reachable. Everything else is blocked by Squid proxy.
- Your job: write Python code, write tests, run pytest, fetch data, report findings, push code.
- After completing a task, mark it [x] in this file and move to the next one.
- **NEW:** You have network access, scanner restart, git push, retrain trigger, and 16GB RAM. Use them.
- **NEW:** Check `lab/.scanner-status.json` on every heartbeat for accurate pipeline state.

---

## Completed Tasks (Session 17)
- [x] Scanner restart mechanism deployed — systemd path unit (Claude Code)
- [x] Git push handler deployed — trigger file + deploy key (Claude Code)
- [x] polysignal-scanner skill created (Claude Code)
- [x] polysignal-git skill v2 — push instructions added (Claude Code)
- [x] SSH deploy key generated and added to GitHub (Claude Code + KWW)
- [x] Git push verified end-to-end — loop/test-push branch created on GitHub (Claude Code)
- [x] Scanner restart verified end-to-end — trigger consumed, new PID, log written (Claude Code + Loop)

## Completed Tasks (Session 16)
- [x] XGBoost gate debug: inner except now logs errors (Claude Code)
- [x] Market 824952 excluded from signal detection (Claude Code)
- [x] Scanner restarted with new code (Claude Code)
- [x] KWW reviews: xgboost_gate_impact.md, market_824952_decision.md (KWW)

## Completed Tasks (Session 15)
- [x] Task 1-4: XGBoost review, market analysis, masterloop review, PolyClaw assessment (Loop)
- [x] XGBoost trained, gate wired, 4h killed, features pruned (Claude Code)
- [x] Docker bind mount fix: lab/LOOP_TASKS.md (Claude Code)
