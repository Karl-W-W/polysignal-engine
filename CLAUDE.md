# PolySignal-OS — Agent Instructions

> **Current system state → `lab/NOW.md`** | Session history → `PROGRESS.md` | Goals → `lab/GOALS.md`

## What This Is
PolySignal-OS is an AI-native prediction market intelligence system. It scans Polymarket, detects signals through a 7-node MasterLoop (LangGraph), and surfaces high-confidence signals. Hardware: NVIDIA DGX Spark (Munich, Blackwell GPU). Frontend: Vercel.

Pipeline: `perception → prediction [+XGBoost gate] → [short-circuit if !TRADING_ENABLED] → draft → review → risk_gate → wait_approval → commit`

## Boot-Up Checklist
1. Read `ARCHITECTURE.md` — folder constraints, Vault rules, RenTec empiricism
2. Read `PROGRESS.md` — current system state, open issues, priorities
3. Check `lab/LOOP_TASKS.md` — Loop's task queue (NOT TASKS.md — Docker inode caching)
4. Check `lab/reviews/` — Loop writes review files there
5. Run tests: `cd /opt/loop && .venv/bin/python3 -m pytest tests/ --tb=short -k 'not test_api'`
6. Report: what Loop accomplished, test results, next priority

## Three-Agent System
- **Claude Code** (you) — architect, infrastructure, test runner, DGX access
- **Loop** (OpenClaw, Telegram `@OpenClawOnDGX_bot`) — autonomous developer, writes code in lab/workflows
- **Karl** — router, Vault authorizer, human-only tasks (MoltBook registration, DNS, credentials)

## Loop's Capabilities (Session 24)
- **Network**: Bridge mode + Squid proxy (6 domains: gamma-api.polymarket.com, clob.polymarket.com, .moltbook.com, .clawhub.ai, .pypi.org, .pythonhosted.org)
- **GPU**: NVIDIA GB10 Blackwell, CUDA 13.0, driver 580.95.05 (`/dev/nvidia0` visible)
- **Memory**: 16GB
- **Scanner restart**: Write `lab/.restart-scanner` → systemd path unit restarts service
- **Git push**: Write `lab/.git-push-request` → handler validates + pushes to `loop/*` branches
- **4 skills**: polysignal-pytest, polysignal-data, polysignal-git (v2 with push), polysignal-scanner
- **Sandbox image**: `openclaw-sandbox:bookworm-slim` with git, curl, PYTHONPATH, User-Agent baked in
- **Heartbeat**: 30min, active 07:00-01:00 CET, Telegram delivery, MoltBook scan + engagement wired in
- **MoltBook JWT**: deployed to container environment
- **Auto-merge CI**: pushes to `loop/*` auto-merge if 430 tests pass
- **Watchdog**: `lab/watchdog.py` — runs every 12th scanner cycle, detects failures, writes alerts
- **Feedback loop**: `lab/feedback_loop.py` — per-market accuracy, auto-exclude, auto-retrain
- **Evolution tracker**: `lab/evolution_tracker.py` — hypothesis → measurement → verdict (REFLECT)
- **Event system**: Scanner writes `lab/.events.jsonl` (prediction_made, error_detected)
- **Retrain trigger**: `echo "retrain" > lab/.retrain-trigger` → systemd watcher
- **applyPatch**: ENABLED — native file editing from sandbox
- **Ollama**: Reachable at `http://172.17.0.1:11434` (5 models: nemotron-3-super:120b, llama3.3:70b, deepseek-r1:70b, qwen2.5:14b, llama3.2:3b, zero cost)
- **Nemotron-3-Super**: Primary heartbeat model (85.6% on OpenClaw benchmarks, 14 tok/s on Spark). Direct chat = Opus 4.6.
- **NemoClaw**: **FULLY DEPLOYED** (Session 29). OpenShell v0.0.12, NemoClaw v0.1.0. Sandbox `polysignal` with Landlock+seccomp+netns. OpenClaw v2026.3.11 inside. Provider: ollama-local. Old OpenClaw gateway STOPPED (port 18789 taken by NemoClaw).
- **Meta-gate**: 7-day rolling accuracy check in prediction_node. Halts predictions if <40%.
- **Sandbox Access**: `read` / `write` tools whitelisted for `/mnt/polysignal` and `/opt/loop` (SDK patched).
- **Staleness detection**: Skips cycle if last 10 predictions are identical.
- **Paper trading**: Wired into prediction_node, logs to `lab/trading_log.json`, bypasses kill switch
- **Memory writing**: Every scanner cycle (not just commit_node)

## Folder Rules
- `core/` — **VAULT. Read-only.** Never modify without Karl's explicit authorization.
- `lab/` — Scratchpad. Build here, test, request promotion.
- `workflows/` — Editable with justification. Not Vault.
- `agents/` — Editable. Agent logic.
- `tests/` — Editable. Add tests freely.
- `scripts/` — Host-side scripts (git-push-handler.sh). Tracked in git.

## Running Tests
```bash
# On DGX
cd /opt/loop && .venv/bin/python3 -m pytest tests/ --tb=short -k 'not test_api'

# On Mac (from polysignal-engine/)
.venv/bin/python3 -m pytest tests/ --tb=short -k 'not test_api'
```
Expected: 432/432 pass (Mac + DGX). `test_api` excluded (needs Flask in venv).

## DGX SSH Access (CRITICAL — read before every session)
- **Remote**: `ssh dgx-remote` (Cloudflare Tunnel). Fails with "bad handshake" if DGX cloudflared is down.
- **LAN**: `ssh spark` or `ssh dgx-local` (192.168.2.244). Only works on home WiFi.
- **If both fail**: DGX is likely rebooted. `cloudflared.service` auto-starts but `OLLAMA_HOST=0.0.0.0` override may be lost. Requires physical DGX access to fix.
- **Persistent fix needed**: Add `OLLAMA_HOST` override to a location that survives apt/systemd upgrades.
- **Claude Code on DGX**: v2.1.80 at `~/.npm-global/bin/claude`. Run from `/opt/loop/`.
- **Mac clipboard bridge**: `tospark` (Mac→DGX), `fromspark` (DGX→Mac). Aliases in `~/.zshrc`.

## Working with Loop
- Assign tasks via `lab/LOOP_TASKS.md` — syncs through directory mount (NOT TASKS.md — Docker inode caching)
- Loop writes code to `lab/` and `workflows/` via sandbox mounts at `/mnt/polysignal/`
- Loop writes reviews to `lab/reviews/` — check there for overnight work
- Loop reports via Telegram — check messages for overnight work
- Loop CAN run pytest (Python 3.12.3 in sandbox since Session 12) — but you verify on Mac too
- Loop has 4 skills: polysignal-pytest, polysignal-data, polysignal-git, polysignal-scanner
- All skills reference `lab/LOOP_TASKS.md` as the canonical task file
- Loop can push code to `loop/*` branches via trigger file → deploy key
- Loop can restart scanner via trigger file → systemd path unit

## Critical Rules
- Docker config changes need container **destruction** (`docker rm -f` or `openclaw sandbox recreate --all`), not restart
- Never re-add `"api": "anthropic-messages"` to `openclaw.json`
- `loop-telegram` service removed (Session 9) — OpenClaw owns Telegram now
- No credentials in markdown files
- `docker compose up -d --force-recreate` for env/code changes in containers
- After `openclaw config set`, **restart the gateway** (`systemctl --user restart openclaw-gateway.service`)
- OpenClaw `env` config field is accepted but NOT applied to containers — bake env vars into the Docker image instead

## Key Paths on DGX
```
/opt/loop/                    — Project root
/mnt/polysignal/              — Host symlink to /opt/loop (matches sandbox mounts)
/opt/loop/core/               — Vault (10 files)
/opt/loop/workflows/          — MasterLoop + scanner
/opt/loop/lab/                — Experiments (feature_engineering, xgboost_baseline)
/opt/loop/lab/LOOP_TASKS.md   — Loop's task queue (canonical — syncs through directory mount)
/opt/loop/lab/reviews/        — Loop's code review output files
/opt/loop/scripts/            — Host-side scripts (git-push-handler.sh)
/opt/loop/tests/              — Pytest suite (305 tests)
/opt/loop/data/               — polysignal.db, prediction_outcomes.json, models/
/opt/loop/brain/memory.md     — Compounding learnings (gitignored)
/opt/loop/TASKS.md            — STALE (Docker inode caching — do not use for Loop)
/opt/loop/.venv/              — Python 3.13 virtualenv
/home/cube/.openclaw/         — OpenClaw config + workspace
/home/cube/.openclaw/openclaw.json — Gateway config
/etc/squid/squid.conf         — Squid proxy allowlist
/etc/docker/daemon.json       — Docker daemon (nvidia default runtime)
/etc/sudoers.d/cube-polysignal — Passwordless sudo for docker/nvidia/squid
```

## Infrastructure (Session 18, updated Session 25)
- **Squid proxy**: `systemctl status squid` — 6-domain allowlist (polymarket, moltbook, clawhub, pypi)
- **Scanner**: `systemctl --user status polysignal-scanner.service` — 5min interval, PYTHONUNBUFFERED=1
- **Scanner restart**: `polysignal-scanner-restart.{path,service}` — watches `lab/.restart-scanner`
- **Git push**: `polysignal-git-push.{path,service}` — watches `lab/.git-push-request`
- **Deploy handler**: `polysignal-deploy.{path,service}` — watches `lab/.deploy-trigger` (Session 25)
- **OpenClaw gateway**: `systemctl --user status openclaw-gateway.service` — Claude Opus 4.6, port 18789
- **OpenClaw exec**: `sandbox` mode, `ask: off`, 24 safeBins. Gateway mode explored but reverted (path mismatch).
- **Docker compose**: `loop_internal-net` + `loop_public-net`, nvidia runtime, GPU reservation
- **Passwordless sudo**: docker, nvidia-ctk, systemctl restart docker/squid, tee
- **Secrets**: `~/.polysignal-secrets/.env` — **root:root chmod 600**. Scanner loads via systemd EnvironmentFile drop-in.
- **ClawHub CLI**: v0.8.0 at `~/.npm-global/bin/clawhub`, authenticated as Karl-W-W
- **Polymarket CLOB**: Authenticated via `derive_api_key()`. Wallet `0x5175...a092`.

## MoltBook Integration (Session 22)
- **Profile**: https://www.moltbook.com/u/polysignal-os (registered + verified)
- **Publisher**: `lab/moltbook_publisher.py` — wired into masterloop commit_node (non-blocking). JWT live on DGX.
- **Scanner**: `lab/moltbook_scanner.py` — 10 submolts, sanitized knowledge extraction. First scan: 275 posts → 138 saved, 49 dropped, 18 high-relevance. Wired into Loop's heartbeat.
- **Engagement**: `lab/moltbook_engagement.py` — 10 submolts subscribed, 6 agents followed, rate-limited commenting. Wired into heartbeat.
- **Math solver**: `lab/moltbook_math_solver.py` — handles MoltBook's anti-bot arithmetic challenges
- **Sanitizer**: `lab/openclaw/moltbook_polysignal_skill/sanitize.py` — 54 injection + 24 exec patterns
- **Knowledge base**: `/opt/loop/data/moltbook_knowledge.json` — structured, relevance-scored intelligence from agent network
- **Auto-merge CI**: `.github/workflows/auto-merge-loop.yml` — 2 proven autonomous deploys this session
