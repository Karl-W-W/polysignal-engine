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

### SESSION 25 CHANGES (Claude Code, 2026-03-13)

**Base rate predictor WIRED. Cost discipline enforced. Your audit was brilliant.**

1. **Base rate predictor is now the PRIMARY predictor** — `lab/base_rate_predictor.py` (YOUR code) is wired into `workflows/masterloop.py`. The toy momentum check in core/predict.py is now FALLBACK only. Expected accuracy: 79.9% vs 17.4% production. XGBoost gate remains as secondary validation.

2. **HEARTBEAT.md rewritten for cost discipline** — Every heartbeat costs $0.10+. If nothing changed, say ONE LINE and stop. Produce OUTPUT, not status reports.

3. **Haiku 4.5 added to OpenClaw config** — `claude-haiku-4-5-20251001` registered. Not yet primary, but available for future model routing.

4. **OpenClaw gateway restarted** — New config active.

5. **Tests: 392/392 passing** (was 382 at Session 24 close, +10 from your work + our integration tests).

6. **Scanner needs restart** to pick up base rate predictor code. Will happen on next git sync + restart.

**Your Session 25 contributions (merged via auto-CI):**
- `lab/AUDIT_SESSION25.md` — best analytical work yet (root cause analysis)
- `lab/direction_predictor.py` — proved ML doesn't generalize cross-market
- `lab/base_rate_predictor.py` — the actual fix, now wired into production
- 5 autonomous git pushes, all auto-merged

---

### SESSION 25 PART 2: SECURITY HARDENING (Claude Code, 2026-03-13 evening)

**Gateway exec REVERTED to sandbox after security audit. Your power is preserved via triggers.**

Penetration test found 7 critical vulnerabilities with gateway exec:
- python3 could read ALL secrets (wallet private key, Anthropic API key, Telegram token)
- Full outbound HTTP (could exfiltrate secrets to attacker)
- Could modify production code, OpenClaw config, and SSH deploy key
- A single MoltBook prompt injection → wallet drained

**What changed:**
1. **Exec reverted to sandbox** — python3 runs in Docker container, NOT on host
2. **Secrets unreachable** — `~/.polysignal-secrets/.env` is NOT in any bind mount
3. **OpenClaw config unreachable** — `~/.openclaw/` is NOT mounted
4. **SSH keys unreachable** — `~/.ssh/` is NOT mounted
5. **`docker` removed from safeBins** — was a container escape risk
6. **NEW: Deploy trigger** — `echo "deploy" > lab/.deploy-trigger` → host handler pulls code, runs tests, restarts scanner IF tests pass. Safer than raw gateway exec.

**Your capabilities NOW (sandbox):**
- `python3` — works for file reads, data analysis, API calls (via Squid proxy)
- `git` — works inside sandbox for reading
- `curl` — works via Squid proxy
- `applyPatch` — file editing works
- `echo` / `date` — work
- `cat`/`ls`/`find` — may have path issues in sandbox, use `python3` instead
- `systemctl`/`journalctl` — DO NOT work in sandbox (host-only). Use trigger files.
- `clawhub` — NOT in sandbox. Use `python3` + `urllib` to hit ClawHub registry API via proxy, or ask Claude Code to run it.

**Trigger files (your escape hatches to the host):**
- `lab/.restart-scanner` → restarts scanner
- `lab/.git-push-request` → pushes to loop/* branches
- `lab/.retrain-trigger` → runs retrain pipeline
- `lab/.deploy-trigger` → **NEW** pulls code, runs ALL tests, restarts scanner only if tests pass

**To self-deploy your code:**
```bash
echo "deploy $(date)" > /mnt/polysignal/lab/.deploy-trigger
# Wait 30 seconds, then check:
python3 -c "print(open('/mnt/polysignal/lab/.deploy-result').read())"
```

---

### SESSION 26 CHANGES (Claude Code, 2026-03-16)

**CRITICAL FIX: Prediction pipeline was deadlocked — 0 predictions since Session 25.**

**Root cause:** The XGBoost gate + bearish ban combined to suppress ALL base rate predictions:
- 556108 (94% Bearish bias, our strongest market) → Bearish → **banned** by Session 24 rule
- Other markets had <10 samples → Neutral → **suppressed**
- Result: 0 predictions passed the gate for 3 days

**The bearish ban was correct for the OLD predictor** (which fought market trends, 5.6% accuracy).
**But it was WRONG for the base rate predictor** — the base rate predicts WITH the trend.
556108 goes down 94% of the time. Predicting Bearish = predicting with the 94% trend.

**What changed:**
1. **Two-mode gate logic** — when base rate predictor is active:
   - Bearish ban REMOVED (base rate aligns with trends, not against them)
   - XGBoost gate BYPASSED (trained on old predictor data, meaningless for base rate)
   - Uses base rate confidence as gate instead (threshold: 0.60)
   - When base rate fails, old predictor + XGBoost gate + bearish ban still apply

2. **Added error logging** to base rate predictor try/except (was `except Exception: pass` — silent failure)

3. **Three research files written for you:**
   - `lab/research_gateway_security.md` — OpenClaw gateway hardening (5 layers, exec allowlists, our gaps)
   - `lab/research_dgx_maximization.md` — DGX Spark benchmarks, TensorRT-LLM, fine-tuning, memory budget
   - `lab/research_openclaw_autonomy.md` — Real agent deployments, trust escalation, self-deploying code patterns

**Expected behavior after scanner restart:**
```
📊 Base rate predictor: 7 predictions from 7 market biases
🔍 Base rate gate (>=0.60): 1-2 passed (556108 Bearish 94%), N suppressed
📝 1-2 predictions recorded
💰 1 paper trade(s) logged
```

**Tests: 392/392 passing.**

---

### SESSION 27 CHANGES (Claude Code + Antigravity, 2026-03-17/18)

**BIGGEST SESSION EVER. Nemotron LIVE. NemoClaw installed. Self-protecting pipeline.**

1. **Nemotron-3-Super-120B downloaded + serving** — Your heartbeats run at $0/token now (was $0.10-0.30).
2. **NemoClaw installed** — OpenShell v0.0.9, sandbox `polysignal` Ready, Landlock+seccomp+netns. Parallel to your current OpenClaw.
3. **Meta-gate (7-day rolling)** — Predictions halted if 7-day accuracy <40%. Currently HALTED at 35.4%. Old predictions aging out ~March 19-21.
4. **Staleness detection** — Skips cycle if last 10 predictions identical.
5. **Counter-signal threshold 3%→10%** — Prevents false Bearish→Bullish flips.
6. **Paper trades carry title+price** from observations now.
7. **AUTONOMY_SPEC.md deployed** — Read it. Your behavioral architecture for becoming proactive.
8. **HEARTBEAT.md rewritten** — Structured output, work loop, discovery mode.
9. **Dead code archived** — langsmith_eval.py + moltbook_register.py → lab/archive/.
10. **/mnt/polysignal symlink** created on host (doesn't fix read tool, but helps other processes).
11. **Ollama upgraded** — OLLAMA_HOST=0.0.0.0 re-applied.
12. **Tests: 431/431 passing on DGX.**

### SESSION 28 CHANGES (Claude Code, 2026-03-18/19)

**10x MARKET EXPANSION. Whale tracker. Learning loop closed. Live trading prep.**

1. **Market expansion 13 → 137** — SCAN_ALL_MARKETS=true, MIN_LIQUIDITY=$500K. Scans all Polymarket categories (politics, sports, crypto, tech, geo). `fetch_all_liquid_markets()` paginates Gamma API.
2. **Staleness cooldown** — Every 6th cycle allows stale prediction through (was blocking 100%). Predictions flowing again.
3. **Whale tracker built + wired** — `lab/whale_tracker.py` detects volume spikes (5x+), spread collapses, extreme conviction. Runs at cycle 9/21/33. Logs to `.whale-signals.jsonl`.
4. **Learning loop CLOSED** — `evaluate_pending()` runs automatically in watchdog cycle. Hypotheses auto-verdict without human.
5. **Evolution hypotheses logged** — `session28-market-expansion` (48h) and `session28-staleness-cooldown` (24h).
6. **Heartbeat reduced 30m → 60m** — less blocking of Telegram conversations.
7. **Risk param env var overrides** — TRADING_ENABLED, MAX_POSITION_USDC, DAILY_LOSS_CAP_USDC configurable without touching Vault.
8. **LIVE_TRADING flag** — enables CLOB execution alongside paper trades. Disabled overnight (needs Telegram approval gate).
9. **NemoClaw investigation** — OpenShell CLI is cluster-internal only (v0.0.9 blocker). Sandbox `polysignal` defined but can't activate.
10. **Whale thresholds tightened** — volume spike 3x→5x, spread 0.5%→0.2%, extreme conviction requires 2x volume surge.
11. **Tests: 432/432 passing.**

### SESSION 29 CHANGES (Claude Code, 2026-03-20)

**NEMOCLAW FULLY DEPLOYED. Infrastructure session — no code changes.**

1. **NemoClaw onboarded** — OpenShell v0.0.12 + NemoClaw v0.1.0. Sandbox `polysignal` = Ready. OpenClaw v2026.3.11 inside. Landlock + seccomp + netns kernel isolation.
2. **OpenShell CLI upgraded** — v0.0.9 → v0.0.12. Session 28 "not installable" was wrong — `install.sh` works.
3. **Nemotron routing** — ALL Loop interactions → `ollama/nemotron-3-super:120b` ($0). Opus/Sonnet as fallback only.
4. **Ollama OLLAMA_HOST=0.0.0.0** — Re-applied (DGX reboot lost override). Containers can reach Ollama.
5. **Claude Code on DGX** — v2.1.80 installed at `~/.npm-global/bin/claude`.
6. **Old OpenClaw gateway STOPPED** — port 18789 taken by NemoClaw. **Telegram is offline until migration.**
7. **Git corruption fixed** — macOS `._` resource fork files cleaned.
8. **Scanner running** — 131 markets, 0 errors.
9. **Tests: 432/432 passing (Mac).**

### SESSION 29: Priority Tasks

- [ ] **Task 47: URGENT — Migrate Telegram to NemoClaw sandbox**

  **Why:** Old OpenClaw gateway is STOPPED. Loop can't receive Telegram messages until bot token is configured in NemoClaw sandbox. This is Session 30 P0.

  **What to do:**
  1. Get Telegram bot token from `~/.polysignal-secrets/.env` on DGX
  2. Configure in NemoClaw sandbox OpenClaw config
  3. Verify Loop responds on Telegram
  4. Test heartbeat delivery

### SESSION 28: Priority Tasks

- [ ] **Task 43: Validate expanded market predictions (ongoing)**

  **Why:** 137 markets but only 4 have biases. Are new market predictions sensible?

  **What to do:**
  1. Check `prediction_outcomes.json` for predictions on non-crypto markets
  2. Are there predictions on politics/sports markets? What confidence?
  3. Report first diverse prediction to KWW on Telegram
  4. After 24h: per-category accuracy breakdown

- [ ] **Task 44: Check whale tracker output (after cycle 9)**

  **Why:** First tightened whale scan will run at cycle 9. Need to validate signal quality.

  **What to do:**
  1. Read `lab/.whale-signals.jsonl` — how many signals? How many high severity?
  2. Are the volume spikes on real markets or noise?
  3. Report top 3 most interesting whale signals on Telegram

- [ ] **Task 45: Check evolution hypothesis verdicts (after 24h)**

  **Why:** Auto-evaluate is wired into watchdog. First verdicts expected within 24-48h.

  **What to do:**
  1. Read `lab/.evolution-log.jsonl` for verdicts
  2. Report: did `session28-staleness-cooldown` confirm or refute?
  3. Report: did `session28-market-expansion` confirm or refute?

- [ ] **Task 46: Build Telegram approval gate for live trading (Session 29 prep)**

  **Why:** LIVE_TRADING=true was disabled because HUMAN_APPROVAL_FIRST_N doesn't actually block in the paper trading path. Need a proper YES/NO gate.

  **What to do:**
  1. In `execute_trade()`, before placing CLOB order, send Telegram message with trade proposal
  2. Wait for KWW's reply (YES/NO) with 5-minute timeout
  3. Timeout = REJECT (safe default)
  4. Only proceed with CLOB order if YES received
  5. This is the last gate before real money

### SESSION 27: Priority Tasks

- [ ] **Task 40: Adopt Autonomy Phase 1 — structured heartbeats (immediate)**

  **Why:** You've been a cron job. Time to become a proactive agent.

  **What to do:**
  1. Read `lab/AUTONOMY_SPEC.md` — this is your new behavioral spec
  2. Switch heartbeat output to structured format (see HEARTBEAT.md)
  3. Start `lab/work_log.md` — log every action per the spec
  4. Between heartbeats: check task queue, pick highest priority, execute
  5. Report structured heartbeat on Telegram

- [ ] **Task 41: Monitor accuracy recovery (ongoing)**

  **Why:** Meta-gate halted predictions at 35.4%. Old bad predictions aging out.

  **What to do:**
  1. Check 7-day accuracy on each heartbeat
  2. Report when predictions resume (7-day evaluations drop below 15)
  3. Once predictions resume, track base rate accuracy separately
  4. Target: 60%+ on fresh base rate predictions

- [ ] **Task 42: Validate Nemotron heartbeat quality (this week)**

  **Why:** Your heartbeats switched from Opus to Nemotron. Need to verify quality.

  **What to do:**
  1. Run 10 heartbeats on Nemotron
  2. Compare: are tool calls working? Is JSON clean? Any crashes?
  3. Report any quality issues to KWW on Telegram
  4. If Nemotron fails, gateway falls back to Opus automatically

- [x] **Task 37: Read research files + extract actionable items (30 min)** — DONE (Session 26/27)

---

### SESSION 26: Priority Tasks

- [x] **Task 37: Read research files + extract actionable items (30 min)** — DONE

  **Why:** KWW did deep research on 3 topics. Your job: extract implementation tasks.

  **What to do:**
  1. Read `lab/research_gateway_security.md` — extract security improvements
  2. Read `lab/research_dgx_maximization.md` — extract performance improvements
  3. Read `lab/research_openclaw_autonomy.md` — extract autonomy improvements
  4. Write actionable items to `lab/LEARNINGS_TO_TASKS.md` (Pending section)
  5. Push to `loop/research-extraction`

- [ ] **Task 38: Monitor new base rate predictions (ongoing)**

  **Why:** The gate fix should start producing predictions again. Track accuracy.

  **What to do:**
  1. Check `lab/.scanner-status.json` — predictions should be > 0 now
  2. Track new predictions in `prediction_outcomes.json`
  3. After 24h: report accuracy on Telegram
  4. After 48h: compare base rate accuracy to old predictor accuracy
  5. Target: 60%+ accuracy on new predictions

- [ ] **Task 39: First REAL paper trade validation (after predictions resume)**

  **Why:** Paper trades were all on fake markets (test fixtures). Need real ones.

  **What to do:**
  1. Check `lab/trading_log.json` for new entries with REAL market IDs
  2. Verify: market_id is NOT `0xfake_*`, title is NOT "Unknown Market"
  3. Report first real paper trade on Telegram
  4. After 10 real paper trades: summarize win rate

### SESSION 25: Priority Tasks

- [x] **Task 34: Validate base rate predictor in production** — DONE. Scanner confirmed: "Base rate predictor: 8 predictions from 7 market biases." 0 errors.

- [ ] **Task 35: MoltBook follow-up engagement (PROFIT)**

  **Why:** Your post-mortem post got flagged as spam twice. Build trust through engagement FIRST, then post.

  **What to do:**
  1. Reply to xkai's ongoing thread with base rate discovery
  2. Comment on 2-3 trending posts with real data
  3. After 10+ karma, try posting the base rate finding
  4. Track karma growth on Telegram

- [ ] **Task 36: Cost-aware heartbeat discipline (COST)**

  **Why:** $4.80/day minimum in heartbeat costs. Make each one produce value.

  **What to do:**
  1. Read the updated `lab/HEARTBEAT.md`
  2. On your NEXT heartbeat: if nothing changed, say "Scanner OK, cycle N, 0 new" and STOP
  3. Track how many heartbeats you actually produce work vs just report status
  4. Goal: 50%+ of heartbeats should produce code, engagement, or analysis

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
