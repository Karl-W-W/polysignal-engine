# PolySignal Agent Memory — Compounding Learnings

> This file is read at the start of every MasterLoop cycle and appended after each cycle.
> It allows the agent to learn from past executions and compound intelligence over time.

## Genesis

The PolySignal Autonomous Agent was initialized on 2026-02-13.
- Architecture: Tri-State Protocol (DRAFT → REVIEW → COMMIT)
- Security: HMAC signature verification, Firejail sandbox, local LLM supervisor
- Brain: Identity Kernel (constitution), Auditor Prompt (review rules), and this memory file
- LLMs: Local Ollama on DGX (llama3.3:70b, deepseek-r1:70b, llama3.2:3b)

---

## Learnings

### 2026-05-11 — Session 42: Eval Pipeline Honesty Pass

Shipped as `b76e88b` on origin/main; DGX deploy ran 2026-05-10
16:15:46 → 16:20:15 CEST; scanner restarted clean (6 cycles, zero
KeyError); truth_board fired thrice with errors=[]. Phase 11 48h
watch under way, deadline ≈ 2026-05-12 16:15 CEST.

**1. The honesty trigger.** A 0.5pp paper-trade slippage turned the
story into the truth:

- Lifetime directional: 47.8% claimed → **31.0% real** (146/471).
  47.8% was a stats-key bug plus 110 0xfake_btc test-pollution rows
  covering for a layer that was never that good.
- Paper-trade win rate: 83.7% pre-friction → **1.86% friction-adjusted**
  (136W/7191L). The 81.8pp drop is honesty, not regression — pre-S42
  PnL booked +0.0001 ticks as wins on markets with 0.5–2pp spread.
- 7-day directional: **0% (0W/67L)**. META-GATE HALT firing at the
  40% floor exactly as designed.

Rule: a headline number without a re-derivation script you can run
today is fiction by default. `lab/cleanup_outcomes_pollution.py` and
`lab/refriction_trading_log.py` are the audit tools. Future "breakthrough
number" ships with one of these, or it doesn't ship.

**2. Import-time capture is a recurring bug class.** S41 fixed
`_DEFAULT_LOG_PATH` capturing prod paths at module-import time, which
let test fixtures pollute the prod trading log. S42 found the same
pattern in `OUTCOMES_FILE` and `EVOLUTION_LOG`; ported the fix across
`lab/outcome_tracker.py`, `lab/feedback_loop.py`, `lab/watchdog.py`,
`lab/evolution_tracker.py`. Module constants → `_resolve_*_file()`
helpers; nine function defaults moved from
`state_path: Path = OUTCOMES_FILE` → `state_path: Optional[Path] = None`
with body resolution. Five offenders remain (`SCANNER_STATUS_FILE`,
`ALERTS_FILE`, `TRADING_LOG_FILE`, `REPORT_FILE`, `RETRAIN_TRIGGER`
across watchdog + feedback_loop) — queued.

Rule: never capture a mutable env-derived path at module-import time.
Resolve at call time. Generalizable across the codebase, not a one-off.

**3. Structural changes worth keeping.**

- **Per-category EVAL_HORIZONS** (`crypto:4h, sports:24h, politics:7d,
  default:4h`). The uniform 4h horizon on 6-month political markets
  was the root of the stale 13.4%-on-14d signal — Orbán-crashed
  predictions evaluated against short-horizon noise, not resolution.
- **Friction on PnL** (slippage_pp=0.005, env-overridable via
  FRICTION_SLIPPAGE_PP). A trade isn't a win unless it beats the
  spread. Hard prereq for any live-trading gate.
- **Atomic writes** (`tmp + os.replace`) in `OutcomeState.save`,
  `TradingLog.save`, `EvolutionTracker._rewrite_log`. Required prereq
  for `truth_board.py` running concurrently with the masterloop's
  in-line eval.
- **In-line eval kept as fallback during cutover.** Both perception_node
  and truth_board.py write the outcomes file; dedupe is the `evaluated`
  flag at `outcome_tracker.py:221`. Phase 11 retires the in-line block
  after 48h of stable truth_board data.

**4. KR consequence.** We can finally measure what we're optimizing.
**Wisdom W3 (calibration plot)** is now *measurable* — pre-S42 the
underlying accuracy was a lie, and calibration against a lie isn't
calibration. **Justice J1 (reasoning trace evaluation)** is now
*evaluatable* — honest outcomes mean wrong-prediction reasoning can
be graded against the actual market path. Before S42 we were optimizing
a metric we couldn't measure, which is the most expensive class of
work there is.

**5. What's still wrong.** 31.0% directional on 471 evaluations means
the predictor is *worse than a coin flip* on markets where it commits.
S42 didn't fix this; S42 made it visible. The right next move is
structural — model, features, signal sources — not parameter-tuning
the gate. Visibility is the whole point of S42, and that's progress.
