# Loop Task Queue (lab/ mirror)
# Updated: 2026-03-08 (Session 18 — Claude Code)
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
- XGBoost gate fires every cycle (6 passed, 7 suppressed on first run)
- Market 824952 excluded from signal detection (0W/40L Bullish)
- Scanner restart + git push capabilities operational

---

## Active Tasks

- [ ] **Task 5: Add `before` parameter to `get_market_history()` (20 min)**

  **Why:** `get_market_history()` fetches 72h of observations regardless of `ref_time`.
  Defense-in-depth against future data leakage.

  **What to do:**
  1. Read `lab/feature_engineering.py` — find `get_market_history()` function
  2. Add an optional `before: datetime = None` parameter
  3. If `before` is set, filter the SQL query to `timestamp <= before`
  4. Update `extract_features()` to pass `ref_time` as `before` when available
  5. Add test(s) to `tests/test_feature_engineering.py` verifying temporal correctness
  6. Run full test suite — must still be 260/260
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

- [ ] **Task 15: Test network access (5 min)**

  **Why:** Session 18 gave you internet through Squid proxy. Verify it works from sandbox.

  **What to do:**
  1. `curl -s https://gamma-api.polymarket.com/events?limit=1 | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['title'])"`
  2. Verify blocked domain: `curl -s https://google.com` (should fail/empty)
  3. Report on Telegram: "Network access verified — Polymarket API reachable, non-allowlisted domains blocked"

- [ ] **Task 16: Live Polymarket data fetch from sandbox (15 min)**

  **Why:** Now that you have network, you can fetch live market data directly.

  **What to do:**
  1. Write a small Python script `lab/live_market_fetch.py` that:
     - Fetches current crypto markets from gamma-api.polymarket.com
     - Prints market titles, prices, volumes
     - Compares with observations in `/mnt/polysignal/data/test.db`
  2. Run it: `python3 /mnt/polysignal/lab/live_market_fetch.py`
  3. Push to `loop/live-fetch`
  4. Report on Telegram

- [ ] **Task 17: py-clob-client Level 0 prototype (30 min)**

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

---

## Reminders

- **Do NOT run any `.sh` scripts.** Do NOT hallucinate `./polymarket_scan.sh`.
- **Network is limited:** Only gamma-api.polymarket.com, clob.polymarket.com, moltbook.com, api.moltbook.com are reachable. Everything else is blocked by Squid proxy.
- Your job: write Python code, write tests, run pytest, fetch data, report findings, push code.
- After completing a task, mark it [x] in this file and move to the next one.
- **NEW:** You have network access, scanner restart, git push, and 16GB RAM. Use them.

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
