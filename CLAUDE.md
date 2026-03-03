# PolySignal-OS — Agent Instructions

## What This Is
PolySignal-OS is an AI-native prediction market intelligence system. It scans Polymarket, detects signals through a 7-node MasterLoop (LangGraph), and surfaces ~5 high-confidence signals/week. Hardware: NVIDIA DGX Spark (Munich). Frontend: Vercel.

Pipeline: `perception → prediction → draft → review → risk_gate → wait_approval → commit`

## Boot-Up Checklist
1. Read `ARCHITECTURE.md` — folder constraints, Vault rules, RenTec empiricism
2. Read `PROGRESS.md` — current system state, open issues, priorities
3. Check `TASKS.md` — see if Loop completed any tasks (check DGX: `cat /opt/loop/TASKS.md`)
4. Run tests: `cd /opt/loop && .venv/bin/python3 -m pytest tests/ --tb=short -k 'not test_api'`
5. Report: what Loop accomplished, test results, next priority

## Three-Agent System
- **Antigravity** (you, Claude Code) — architect, infrastructure, test runner, DGX access
- **Loop** (OpenClaw, Telegram `@OpenClawOnDGX_bot`) — autonomous developer, writes code in lab/workflows
- **Karl** — router, Vault authorizer, human-only tasks (MoltBook registration, DNS, credentials)

## Folder Rules
- `core/` — **VAULT. Read-only.** Never modify without Karl's explicit authorization.
- `lab/` — Scratchpad. Build here, test, request promotion.
- `workflows/` — Editable with justification. Not Vault.
- `agents/` — Editable. Agent logic.
- `tests/` — Editable. Add tests freely.

## Running Tests
```bash
# On DGX
cd /opt/loop && .venv/bin/python3 -m pytest tests/ --tb=short -k 'not test_api'

# On Mac (from polysignal-engine/)
.venv/bin/python3 -m pytest tests/ --tb=short -k 'not test_api'
```
Expected: 241/241 pass. `test_api` excluded (needs Flask in venv).

## Working with Loop
- Assign tasks via `/opt/loop/TASKS.md` — Loop reads on heartbeat (every 30m, 07:00–01:00 CET)
- Loop writes code to `lab/` and `workflows/` via sandbox mounts at `/mnt/polysignal/`
- Loop reports via Telegram — check messages for overnight work
- Loop CAN run pytest (Python 3.12.3 in sandbox since Session 12) — but you verify on Mac too
- One task at a time. Wait for completion before assigning next.

## Critical Rules
- Docker config changes need container **destruction** (`docker rm -f`), not restart
- Never re-add `"api": "anthropic-messages"` to `openclaw.json`
- `loop-telegram` service removed (Session 9) — OpenClaw owns Telegram now
- No credentials in markdown files
- `docker compose up -d --force-recreate` for env/code changes in containers

## Key Paths on DGX
```
/opt/loop/                    — Project root
/opt/loop/core/               — Vault (10 files)
/opt/loop/workflows/          — MasterLoop + scanner
/opt/loop/lab/                — Experiments (feature_engineering, xgboost_baseline)
/opt/loop/tests/              — Pytest suite (241 tests)
/opt/loop/data/               — polysignal.db, prediction_outcomes.json
/opt/loop/brain/memory.md     — Compounding learnings (gitignored)
/opt/loop/TASKS.md            — Loop's task queue
/opt/loop/.venv/              — Python 3.13 virtualenv
/home/cube/.openclaw/         — OpenClaw config + workspace
/home/cube/.openclaw/openclaw.json — Gateway config (12 bind mounts)
```
