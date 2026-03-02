# Loop Task Queue
# Updated: 2026-03-03 00:15 CET (Session 9 — Claude Code)
# Loop reads this on every heartbeat. Pick the first unchecked [ ] item.

---

## Active Tasks

- [ ] **Port sanitize.py self-tests to pytest**

  **Goal:** `lab/openclaw/moltbook_polysignal_skill/sanitize.py` has 7 inline self-tests (run via `__main__`). Port them to `tests/test_sanitize.py` for CI coverage.

  **Where to write:** `tests/test_sanitize.py` (new file)

  **What to do:**
  1. Read `lab/openclaw/moltbook_polysignal_skill/sanitize.py` — understand the 7 self-tests
  2. Convert each to a pytest test with proper assertions
  3. Include edge cases: empty post, missing fields, very long content
  4. Run `python3 -m pytest tests/test_sanitize.py -v` — all must pass
  5. Report on Telegram when done

- [ ] **Verify MoltBook publisher dry-run end-to-end on DGX**

  **Goal:** The publisher is now wired into masterloop commit_node. Verify the full pipeline fires on DGX with `MOLTBOOK_DRY_RUN=true`.

  **What to do:**
  1. Pull latest: `cd /opt/loop && git pull origin main`
  2. Run tests: `python3 -m pytest tests/ --tb=short -k 'not test_api'` — expect 140/140
  3. Run dry-run smoke test from lab/reviews/moltbook_verification.md §4
  4. Report results on Telegram

## Completed Tasks

- [x] Risk gate wired into MasterLoop (Session 8 — architect + Loop collab)
- [x] Schema unification — bitcoin_signal.py returns Signal objects (Session 6)
- [x] Architecture report — full codebase review (Session 6)
- [x] health_check.py — thermal, disk, DB freshness (Session 7)
- [x] test_risk_edge_cases.py — boundary tests for risk.py (Session 7)
- [x] schema_review.md — field usage audit (Session 7)
- [x] trade_proposal_bridge.py — typed Signal→TradeProposal bridge (Session 9 — Loop)
- [x] time_horizon.py — derives time_horizon from volatility (Session 9 — Loop)
- [x] time_horizon_audit.md — dead field audit (Session 9 — Loop)
- [x] cycle_number fix — wired from LoopState into observations (Session 9 — Claude Code)
- [x] MasterLoop e2e smoke test — 4 tests (Session 9 — Claude Code)
- [x] route_after_risk_gate END bug fix (Session 9 — Claude Code + Loop independently)
- [x] telegram service removed from docker-compose.yml (Session 9 — Claude Code)
- [x] time_horizon wired into perception pipeline (Session 9 — Claude Code)
- [x] MoltBook publisher built with 17 tests (Session 9 — Claude Code)
- [x] risk_integration.py promoted from lab/ to core/ — 140/140 tests (Session 9 — Claude Code)
- [x] test_trade_proposal_bridge.py — 14 pytest tests ported (Session 9 — Loop)
- [x] test_time_horizon.py — 16 pytest tests ported (Session 9 — Loop)
- [x] MoltBook publisher verified on DGX (Session 9 — Loop)
- [x] MoltBook publisher wired into commit_node (Session 9 — Claude Code)
- [x] Dead files deleted: lab/signal.py, lab/polymarket/risk.py, lab/masterloop_perception_patch.py, lab/risk_integration.py (Session 9 — Claude Code)
- [x] MoltBook implementations reconciled: publisher=canonical posting, SKILL.md=design spec, sanitize.py=future read pipeline (Session 9 — Claude Code)
- [x] dgx_config.md marked SUPERSEDED by model_upgrade.md (Session 9 — Claude Code)
