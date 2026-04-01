# PolySignal-OS Handoff Log

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
