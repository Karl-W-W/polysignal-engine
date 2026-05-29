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

### 2026-05-11 — Session 43: Operator Console + Agent Chat Real

Shipped as `f7363bf` on origin/main (rode in via `8a628fb`, the
auto-merge of loop/brain-s42, after a race condition cancelled
loop/sonnet-primary's own auto-merge — push got `! [rejected] main
-> main (fetch first)` because origin/main advanced between fetch
and push). Seat 6 operator REPL verified `> 7×8 → 56` on Sonnet 4.6
after gateway restart at 2026-05-11 18:37:41 CEST.

Five lessons that compound:

**1. `tmux new -As <name>` attach-vs-create gotcha.** When `<name>`
already exists, `-A` attaches and silently skips the inline command —
no error, no warning. Failure mode caught today:
`SEATS_FORCE_RECREATE=1 launch-seats polysignal` rebuilds only the
outer `ops_console` session; inner sessions (loop, brain, truth) from
prior days persist on the same tmux server. The new seat cmds *look*
applied (yaml dry-run passes) but the old content keeps showing
because nothing was re-executed in those panes. Workaround:
`tmux kill-session -t <name>` for each stale inner session, *then*
FORCE_RECREATE. Editor buffers are safe to kill — nano keeps its
inode while the session dies, so any saved file content is preserved.

**2. The OpenClaw runtime-model lever is ONE file, ONE path.**
`~/.openclaw/openclaw.json` → `.agents.defaults.model.{primary,fallbacks}`.
Not in `/opt/loop/` (the runtime config lives under `/home/cube/`,
outside the repo, so to "commit a config change" you commit a spec
doc that records the diff). Not in `~/.openclaw/agents/main/agent/models.json`
(that file is a provider catalog — pricing, context windows, model
IDs — not a router override). Gateway restart is required after any
edit: `systemctl show openclaw-gateway.service -p ExecReload` is
empty, and `lab/openclaw_heartbeat_config.md` calls out the restart.

**3. `openclaw agent` returns `"completed"` without `--json`.**
Without the flag, stdout shows only the run-end token; the agent's
actual reply text is buried at `result.payloads[*].text` in the
JSON payload. Extract pattern:
`--json | jq '..|.text? // empty'`. Recursive descent over `..text`
works cleanly because Claude content blocks use `{type, text}` shape
and only the assistant-text variant exposes `text` at any depth —
tool-use and thinking blocks carry different keys.

**4. IDENTITY.md vs runtime drift is a recurring failure mode.**
IDENTITY.md is descriptive prose ("the character thinks it's X");
`openclaw.json` is prescriptive ("X is what actually runs"). Today
IDENTITY claimed `claude-sonnet-4-6 (primary)` while runtime had
been routing to Haiku 4.5 since Session 40. Two-step rule for future
sessions when these disagree: (a) query the runtime via
`openclaw agents` to see which model actually wins — never trust the
identity doc alone; (b) pick a direction explicitly and change one
side, not both, after thinking about which side is the source of
truth. Today's fix moved runtime to match IDENTITY's claim, not the
other way around.

**5. mDNS gateway probing loop is cosmetic when chat goes over loopback.**
Seat 6's top pane shows `[bonjour] watchdog detected non-announced
service ... state=probing` cycling every 10–15s, never reaching
`announced`. That means `openclaw.local` won't resolve via Bonjour
across the LAN. But `openclaw agent` over localhost works fine — the
gateway is healthy on port 18789 itself, just not advertising its
name on multicast. Don't chase the probing loop unless something on
the LAN actually needs Bonjour discovery of the gateway.

Sonnet vs Haiku for the operator chat: Haiku 4.5 read `"Reply with
exactly: the cube root of 729."` literally and replied with the
literal string `"the cube root of 729."` instead of computing 9.
Sonnet 4.6 parses the directive/content split correctly (verified
on `What is 7 times 8? Respond with just the number.` → `"56"`). For
the Seat 6 REPL — where every operator message is a directive plus
its content — Sonnet is worth the 3× input + 3× output cost. For the
120-min heartbeat, which produces ≤300-char acks (~75 output tokens),
Haiku stays: output-only delta if heartbeat were also swapped is
~$0.20/month, against near-zero functional gain on structured acks.

### 2026-05-21 — Session 44: Short-Horizon Universe (built + verified, NOT deployed)

No evaluable track record yet. Three changes built and individually verified
against the live DGX code, committed to branch `s44-short-horizon-universe`
(6de6253, 5b131ef, 8fc48f8 on top of 92d5da2). NOT deployed — see lesson 1.

**1. The DGX `/opt/loop` is a read-only mirror of GitHub `origin/main`.**
Cron runs `*/10 * * * * git fetch origin && git reset --hard origin/main`.
Any direct edit to a tracked file under `/opt/loop` is wiped within 10 minutes
— the reflog is wall-to-wall `reset: moving to origin/main`. The ONLY durable
deploy path is commit → push to GitHub `origin/main` → the cron pulls it.
Editing files on the DGX and restarting does NOT persist. `brain/memory.md`
is itself caught in this: the scanner appends to it every cycle and the cron
wipes it every 10 min — it cannot be durably hand-edited on the DGX.

**2. The three changes** (verified in isolation on the live code, in the
windows between cron resets):
- Change A (`lab/experiments/bitcoin_signal.py`): `fetch_all_liquid_markets()`
  restricted to markets resolving in 0.25–7 days via gamma's
  end_date_min/end_date_max window plus a client-side endDate re-check;
  pagination fixed (100/page). Pairs with MIN_LIQUIDITY 500000→1000 (drop-in).
  Verified: returns 300 markets, all 0.25–7d, 0 long-horizon.
- Change B (`lab/feedback_loop.py`): `.retrain-trigger` auto-write gated behind
  AUTO_RETRAIN_ENABLED (default false). Verified: feedback_loop tests 13/13.
  The stale trigger from this morning was deleted.
- META-GATE (`workflows/masterloop.py`): the sub-40%-accuracy auto-halt in
  prediction_node gated behind META_GATE_ENABLED (default false). Verified:
  flag on → halts, flag off → no halt.

**3. State.** The resolution backtest (2026-05-21) found the 598-record
history is 4 distinct predictions, all long-horizon, only 1 resolved (0/1).
Once the three changes deploy, a short-horizon universe should yield ~2–3
predictions/day; N≥30 resolved — the first real edge measurement — is
reachable ~2nd week of June 2026.

**4. Live scanner is on the original known-good state.** The DGX edits were
reverted by the cron; the MIN_LIQUIDITY drop-in was restored to 500000 and the
scanner restarted clean ("66 liquid markets, min $500,000"). Nothing
half-applied is running.

**5. Next dominoes (named, not actioned).** (a) The Bearish ban
(`base_rate_predictor.py:64` + `masterloop.py:606`) — the track record will be
Bullish-only / favorite-skewed until it is lifted; lift after N≥30 exists.
(b) The 4h-drift evaluator (`outcome_tracker.py:343-357`, MIN_MOVE_THRESHOLD
0.0005) — the real fix is scoring against resolution; until then META_GATE and
AUTO_RETRAIN must stay off.

**6. Known issue surfaced during S45 prep (2026-05-25) — `:memory:` test pollution.**
`tests/test_masterloop_e2e.py` lines 271, 300, 383 do
`patch("workflows.masterloop.os.getenv", return_value=":memory:")` — patching
**every** `os.getenv` call in `workflows.masterloop` to return the literal
string `:memory:`. The intent was an in-memory sqlite handle for
`OUTCOMES_FILE`; the actual effect is that `record_predictions` does
`Path(":memory:")` → `open(":memory:", "w")` and writes to a real file at
`/opt/loop/:memory:`. The file is untracked but is listed in `.gitignore:24`
(so the pattern was known and silently tolerated). It accumulates across runs
— from 3083 bytes at S44 (2026-05-21) to 5051 bytes by S45 (2026-05-25). Once
≥10 identical `0xfake_btc Bullish@0.82` records accumulate, the masterloop
staleness detector (`masterloop.py:505-548`, S27/S31 code, untouched by S44)
fires on the test's "current cycle" and returns empty predictions —
silently failing any test that asserts `len(final["predictions"]) > 0` on a
non-cycle-6 final cycle (e.g. `test_xgboost_gate_passes_high_confidence`).
Confirmed 2026-05-25 by a clean experiment: delete `/opt/loop/:memory:`, run
the single test → PASS (0.66s); delete again, run the full suite → 510 passed
in 279s. Proper fix is to patch `OUTCOMES_FILE` specifically (the S42 path
helper resolves it lazily — `monkeypatch.setenv("OUTCOMES_FILE", str(tmp_path))`
is what `tests/test_feedback_loop.py` already uses correctly). Workaround
until then: `rm -f /opt/loop/:memory:` before any pytest run. NOT FIXED in S44
— out of scope.

### 2026-05-25 — Session 45: S44 Deployment — Verified Live, Not Merged

S44's three changes deployed to the DGX in a verified-quiet window. The pipeline
produced real predictions on real short-horizon markets — Alphabet and Apple at
$0.83, Bullish, conf 0.833. **S44 works end-to-end.** Branch pushed to origin at
`0334e38`, **not merged** — the staleness detector tripped the first two cycles
and is the next domino to address before a clean merge.

**1. The full deploy-vector map (the headline finding).** The DGX `/opt/loop` is
a read-only mirror of `origin/main` via a `*/10` cron `git reset --hard`. But
that cron is NOT the only thing that resets the tree or restarts the scanner —
there is a second autonomous vector: `polysignal-deploy.path` watches
`lab/.deploy-trigger`, fires `deploy-handler.sh`, which does
`git fetch origin && git reset --hard origin/main` then
`systemctl restart polysignal-scanner.service`. **Loop itself writes that
trigger** from inside the sandbox per `AUTONOMY_SPEC.md:52` ("Deploy: writing to
.deploy-trigger, pushing to CI branches, merging PRs") and
`LOOP_TASKS.md:46`. Loop fired the trigger at 14:14:53 mid-S45, wiping a
mid-flight checkout. Loop runs continuously on `openclaw-gateway.service` — not
just on its 120-min heartbeat. Pausing the gateway is the upstream control over
every trigger file (`.deploy-trigger`, `.restart-scanner`, `.git-push-request`,
`.retrain-trigger`).

**2. The full pause set for a deploy window (verified safe — held a clean 10-min
pytest + a 22-min live-cycle window):**
- cron `*/10 cd /opt/loop && git fetch origin && git reset --hard origin/main`
- cron `*/5 /opt/loop/scripts/watchdog-host.sh` (crash-only, but pause for total quiet)
- `polysignal-deploy.path` + `polysignal-deploy.service`
- `polysignal-truth-board.timer` (writes `prediction_outcomes.json` every 15 min)
- `polysignal-scanner-restart.path`
- `polysignal-git-push.path`
- `polysignal-retrain.path`
- `openclaw-gateway.service` — **LAST**, since it's the source of every trigger
Re-enable in reverse safe order: delete any trigger files Loop dropped during
the pause → start the four `.path` units → start truth-board timer → restore
crontab from backup → start openclaw-gateway LAST.

**3. Live cycle evidence — what S44's code actually did** (PID 3070362,
2026-05-25 15:13:39 → 15:55:16 CEST):
- Cycle 1 (47s): 300 short-horizon markets observed, 0 predictions. Volatility
  gate filtered 35/35 candidates — the new short-horizon universe has cold-start
  observation history.
- Cycle 2 (51s): 0 predictions. 2 candidates reached the predictor (1 base-rate +
  1 momentum-Neutral on a Trump market). **Staleness check** (`masterloop.py:505-548`)
  blocked them — the last-10 records in `prediction_outcomes.json` were the S44-era
  PSG/US-Iran pattern (2 unique signatures), `current_sigs ≤ 2` failed the
  diverse-batch override, cooldown branch fired (`cycle % 6 != 0`).
- **Cycle 3 (51s): 2 predictions recorded.** The volatility gate started letting
  more markets through; `current_sigs > 2` triggered the staleness override.
- Cycle 4: 2 / Cycle 5: 3 / Cycle 6: 3 / Cycle 7: 4 / Cycle 8: 5. Steady-state
  throughput from Cycle 5 onwards ≈ 3–5 predictions per 5-min cycle ≈
  **35–60 predictions/day**. Far above the static-census ~2–3/day estimate.
- Cycle 6 detail: 300 → 265 near-decided filtered → 35 → 14 frozen → 21 to
  predictor → 14 base-rate + 7 momentum. `🔍 Base rate gate (>=0.5): 3 passed,
  11 suppressed`. Momentum gate: 0/7 passed. 3 hypotheses → 3 records → 2 paper
  trades to `trading_log.json` (Alphabet $0.83, Apple $0.83).
- All 28 new records in `prediction_outcomes.json` over 25 min were **Bullish**
  (Bearish ban active end-to-end). Markets: `569343, 1999690, 1999660, 1972137,
  2118910` — entirely new short-horizon markets, none of the S44-era stale 4.

**4. The staleness detector is the next real domino** (`masterloop.py:505-548`,
S27/S31 code, untouched by S44). It works correctly in steady state — the
override `current_sigs > 2 → "current batch diverse — allowing through"` handles
the common case. But it cold-start-blocks for ~10 minutes after any universe
change, because immediately after a fresh start the volatility gate has no 7-day
swing history for the new markets, the candidate pool collapses to ≤2 unique,
and the cooldown reasoning fires: "history says stuck, current confirms stuck,
wait until cycle % 6 == 0." But if the universe has just CHANGED, the "stuck"
history is meaningless — those records are about the OLD universe's stale
markets. Two viable fixes for next session:
- **Time-recency over position-recency**: replace `predictions[-10:]` with
  `predictions where timestamp >= now - N_minutes`. New-universe records dominate
  the recent window quickly; old stale markets age out of consideration.
- **Universe-size-aware threshold**: scale the "≤2 unique" trigger by the
  current candidate pool. With 1–2 candidates, "all same signature" is normal;
  only flag stale if ≥5 candidates all coincide.
Either decouples staleness detection from "small batch on a fresh universe."

**5. The `:memory:` known-issue cleanup is also blocked on the same merge.**
The S44 entry's point 6 documented the `tests/test_masterloop_e2e.py` global
`os.getenv` patch that creates `/opt/loop/:memory:` test pollution. That fix
should ride along with the staleness fix on the merged branch.

**6. Branch state at session end.** `s44-short-horizon-universe` at `0334e38`
on `origin`, **5 commits ahead of `main`**:
- `6de6253` — Change A (short-horizon market filter)
- `5b131ef` — Change B (auto-retrain stop-loss)
- `8fc48f8` — META-GATE (default-off auto-halt)
- `fb32a02` — S44 brain entry (built, verified, not deployed)
- `0334e38` — `:memory:` known-issue note
**NOT merged to `main`**. Awaits the staleness fix to land beside it.

**7. Live system at session end.** DGX reverted to `main` (`92d5da2`), scanner
restarted on old code (PID 3156536, MIN_LIQUIDITY=500000), all paused mechanisms
re-enabled in safe order, no trigger files lingering, all six previously-paused
units active, all three crons active. Pre-S45 known-good state, exactly.

**Next session — single line:** *Fix the staleness detector on a branch, verify,
then merge it together with `s44-short-horizon-universe`.*

### 2026-05-25 (evening) — Session 45 continued: Staleness Fix Shipped + Merged

The "next session" became "later this session." Staleness fix landed on
`s44-short-horizon-universe`, merged to `main` via direct fast-forward push.
The whole S44+S45 set is now live on `main` at `69a4760`.

**The fix** (`workflows/masterloop.py`). Replaced `predictions[-10:]`
(position-based) with `predictions where timestamp >= now − 30 minutes`
(time-based). Extracted into module-level `_check_staleness(stored, current,
cycle_number, …)` so it's unit-testable. Module-level constants:
`STALE_LOOKBACK_MINUTES=30` (env-overridable), `STALE_MIN_RECENT=5` (skip
the check on thin batches — prevents cold-start false-positive),
`STALE_COOLDOWN=6` (unchanged). Old-universe records now age out
automatically after any universe change — robust to ANY change, not just
the S44 one.

**Tests** (`tests/test_staleness_detector.py`). 7 unit tests; two
(`test_old_stale_records_do_not_block_fresh_universe`,
`test_s44_psg_us_iran_history_does_not_block_new_universe`) FAIL on the
old position-based logic and PASS on the time-based one — the fix is
verified, not asserted. The other five pin behavior: recent stuck loop still
caught, cooldown still works every N cycles, diverse-current override
unchanged, thin window allowed silently, diverse history allowed silently.

**Deploy + verification (2026-05-25 16:55–17:12 CEST, scanner PID 3264991).**
- Full pytest on branch code: **517 passed, 4 deselected** in 8:07, HEAD-
  stable both ends (510 baseline + 7 new tests).
- Restart on the new code, `MIN_LIQUIDITY=1000` confirmed in `/proc/environ`.
- 3 cycles watched. **No STALE messages in any cycle.** Cycle 2's cold-start
  block from earlier today is gone — `_check_staleness` returned the
  "insufficient recent data" path on all three cycles (`len(recent) <
  STALE_MIN_RECENT`).

**The honest twist: 0 predictions in cycles 1–3 today, from a DIFFERENT
cause.** Perception entered signal-mode (2 / 2 / 7 signals detected on
Iran/oil/crypto markets that recently moved ≥5pp). Signal-observations
reached the predictors and produced candidates (1+1, 1+1, 4+2). All were
suppressed downstream:
- Base-rate gate suppressed **0/4 in Cycle 3** — likely 4 low-priced
  longshots → `from_price_levels` Bearish → `BAN_BEARISH_OUTPUT` →
  Neutral conf=0.0 → gate `if Neutral: continue`.
- Momentum gate suppressed **0/2 in Cycle 3** — two already-Bullish
  `predict_market_moves` outputs at 0.80, killed by the **XGBoost gate**
  because the Apr-15 model (trained on noise-labelled
  `prediction_outcomes.json`) returned `p_correct < 0.5`.

This is NOT a staleness failure and does not block the merge per Karl's
rule. It's the **Bearish ban + XGBoost-trained-on-noise** dominoes already
on the post-N≥30 list, made visible by a signal-mode cold start (yesterday
was a no-signal-mode cold start, where the same dominoes were dormant).

**Throughput / N≥30 — revised.** Yesterday's no-signal mode (2026-05-25
15:13–15:55) produced 35–60 predictions/day steady-state from Cycle 5
onwards. Today's signal-mode (post-fix, 16:55–17:12) produced **0** in
17 minutes. The honest read: throughput is **highly mode-dependent**;
N≥30 resolved is still reachable on the order of 1–3 weeks, but the
spread is wider than the static census suggested. Mid-June is still
plausible; late-June is now in the realistic envelope.

**Final state on `main` (`origin/main` at `69a4760`).**
- 7 commits ahead of the pre-S44 baseline `92d5da2`: Change A (short-horizon
  filter + pagination fix), Change B (auto-retrain stop-loss), META-GATE
  (default-off auto-halt), S44 brain entry, `:memory:` known-issue note,
  S45 in-progress brain entry, S45 staleness fix + tests.
- DGX on `main` at `69a4760`. Scanner active PID 3264991 with
  `MIN_LIQUIDITY=1000` in `/proc/environ`. ActiveEnterTimestamp 16:55:31.
- All six previously-paused units re-enabled in safe order: four `.path`
  units → truth-board timer → both crons (restored verbatim from
  `/home/cube/crontab.bak-s45-redeploy-2026-05-25.txt`) →
  `openclaw-gateway` (Loop) LAST. No trigger files were lingering.
- The `*/10 git reset --hard origin/main` cron is back; from now on, any
  push to `main` propagates to the DGX within 10 minutes.

**Next dominoes — named, not actioned, in order of priority for the next
real edge measurement.**
1. **Bearish ban** (`lab/base_rate_predictor.py:64` `BAN_BEARISH_OUTPUT` +
   `workflows/masterloop.py:606` momentum bearish skip). Until lifted, the
   track record is Bullish-only / favorite-skewed and the system can't
   predict any of the low-priced longshots that signal-mode finds. Lift
   only AFTER N≥30 exists AND the evaluator is fixed.
2. **XGBoost gate trained on noise** (`workflows/masterloop.py:582+` calling
   `lab.xgboost_baseline.load_model()`; model at
   `/opt/loop/data/models/xgboost_baseline.pkl` dated 2026-04-15). Currently
   rejects 100% of momentum Bullish predictions because the training labels
   are from the broken 4h-drift evaluator. Do NOT retrain it until the
   evaluator is fixed — otherwise we'd just lock in the noise.
3. **The 4h-drift evaluator itself** (`lab/outcome_tracker.py:343-357`,
   `MIN_MOVE_THRESHOLD = 0.0005`). The real fix scores resolution rather
   than 4h price drift. Until that lands, `META_GATE_ENABLED` and
   `AUTO_RETRAIN_ENABLED` must stay false.

Architecture map (Karl's Job 2) is the next thing on the table.

> **Next session START HERE:** make the live evaluator score market resolution (port `eval/resolution_backtest.py` logic into `outcome_tracker`). This is the keystone — it unblocks the Bearish ban, XGBoost retrain, and META-GATE.

### 2026-05-26 — Session 46: Evaluator Port — Built + PR'd, NOT LIVE

**State at session end:** the live system on the DGX is still `dd70650` —
the broken 4h-drift evaluator (`lab/outcome_tracker.py:343-357`,
`MIN_MOVE_THRESHOLD=0.0005`) is **still scoring noise** and the truth-board
is still writing the 36% accuracy reading-itself number on every fire. The
fix is **built, tested, pushed, and PR'd** but **NOT MERGED, NOT
DEPLOYED, NOT MIGRATED**. PR #1 — `s46-evaluator-resolution-scoring` →
`main` — awaits Karl's review.

**The keystone (the one verified result):** a single test
(`tests/test_outcome_tracker_resolution.py::TestKeystone`) fails on
`dd70650` with `assert 'CORRECT' == 'INCORRECT'` because the drift scorer
marks a +0.01 price-noise move on a resolved-NO market (Man City EPL,
566188) as CORRECT. The same test passes on the branch because the
resolution scorer asks gamma, sees `closed=true, outcome0_price=0.0`,
marks INCORRECT. Same input, opposite verdict — verified by
checking out the dd70650 evaluator in place and re-running the same
test file. That swap is the proof, not the assertion.

**Branch contents (`git log dd70650..origin/s46-evaluator-resolution-scoring`):**
- `59b00ef` — `eval/` into git (the S44 `resolution_backtest.py` was
  the most important untracked file in the repo until this commit) +
  `lab/LOOP_TASKS.md` S46 stand-down block (durable backstop for the
  in-session Loop ACK).
- `4f08117` — the evaluator port itself: `lab/_resolution_lookup.py`
  (extracted gamma fetch + status mapping, HTTP-mockable), the
  `evaluate_outcomes` rewrite (resolution-based scoring; drops horizon
  gate; drops dual-horizon sibling write; pollution guard for fake IDs;
  per-call cache so N rows on the same market cost 1 HTTP),
  `eval/migrate_outcomes_to_resolution.py` (one-shot wipe + backup),
  and four test files (28 new tests; 2 dual-horizon cases deleted).

**Test count:** 542 passed + 1 skip + 4 deselected on the branch (up
from 516+1+4 on `dd70650`). Net +26.

**Why I did NOT push to main directly** (Karl's call, lesson logged):
this change rewrites how the system scores itself AND requires a
destructive 692-label migration on the prod outcomes file. That class
of change goes through a reviewed PR, not a raw push. The PR includes
an explicit "POST-MERGE STEP" section — the merge alone leaves the
data in a mixed state; `eval/migrate_outcomes_to_resolution.py` must
run inside a controlled deploy window (same full pause set as S44/S45)
or the new evaluator will be staring at the old noise labels.

**Loop stand-down — in force until deploy is actually done.**
- 2026-05-26 19:11 CEST: Loop ACKed in-session with the literal
  string `S46-STAND-DOWN ACK` plus the line "the 36% number is the
  broken ruler measuring itself — understood. Will stay read-only on
  diagnostics until S46 is lifted." Hard stops: no `train_model()`,
  no `.retrain-trigger`, no edits to the evaluator chain
  (`outcome_tracker.py` / `feedback_loop.py` / `masterloop.py` /
  `base_rate_predictor.py` / `xgboost_baseline.py`), no
  `.deploy-trigger` / `.restart-scanner`.
- The stand-down ALSO lives in `lab/LOOP_TASKS.md` on the branch (so
  it survives a gateway restart — once the PR merges and the cron
  pulls main, the file becomes the durable record).
- Heartbeat that fired at 19:21 CEST (post-ACK) confirmed: status-only
  report, no retrain ask, no code-change offer. **Loop is honoring it.**
- Until the deploy is verified done, this stand-down REMAINS IN FORCE.
  After deploy, next session should explicitly clear it (Telegram
  message + remove the P0 block from `lab/LOOP_TASKS.md` + commit).

**The honest framing — DO NOT misread this session as "accuracy
fixed."** Post-deploy the real accuracy will be ~0/1 on the single
resolved market currently in the file (Man City EPL — Bullish call,
resolved NO, 0/1 = 0%). The number will look bad. That is the
**correct, expected** outcome of fixing the instrument — a true
small number replacing a fake big one. The edge verdict (does
PolySignal beat the market) still requires **N≥30 resolved
markets**, reachable on the order of 1–3 weeks per the S45
throughput notes (35–60/day quiet-mode, 0 in signal-mode under the
suppression vectors still in place). This session's achievement is
**an honest instrument**, not an accuracy number.

**Downstream dominoes — unblocked but explicitly out of scope:**
1. **Lift the Bearish ban** — only after N≥30 resolved AND first
   honest verdict is produced.
2. **Retrain XGBoost** — only after migration + truth-board has
   re-labelled enough rows. The 2026-04-15 model was trained on
   noise; it must be discarded, not patched.
3. **Re-enable `META_GATE_ENABLED`** — only after rolling accuracy is
   computed from real resolution-scored verdicts.
Do them in that order, after N≥30 exists.

**DGX live state at session end:**
- HEAD: `dd70650` (unchanged from session start).
- Scanner: `polysignal-scanner.service` active (PID 3264991 still,
  from S45 redeploy 16:55:31 CEST 2026-05-25).
- All six previously-paused units active. Both crons active. No
  trigger files armed.
- `prediction_outcomes.json`: 774 records, 692 evaluated under the
  **broken** drift instrument (201W/356L/135N, 36.1%), 22 unique
  (market_id, hypothesis) pairs, all Bullish (Bearish ban active
  end-to-end as expected).

(The above "NOT LIVE" entry is historical — it was true at PR time.
The deployment happened across 2026-05-27/28; see the S46b entry below.)

### 2026-05-28 — Session 46b: Deployed + the in-line-eval contamination bug

**S46 + S46b are LIVE on `main` and on the DGX.** The evaluator now scores
against actual Polymarket resolution (YES/NO). `origin/main` at `7e6059e`
(= the S46b merge `6b62276` + a doc-only stand-down-clear commit). DGX on
`7e6059e`, scanner running clean code.

**The bug that the S46 deploy exposed (the real lesson).** S46 merged (PR #1,
`57e44df`) and the controlled deploy ran: migration wiped the 788 drift labels,
truth-board re-scored, market 566188 (Man City) correctly scored
resolved_no/INCORRECT. **But within minutes the file re-filled with drift
labels.** Root cause: `workflows/masterloop.py` (`perception_node`) called
`evaluate_outcomes` **in-line every cycle** — the S14-S42 "in-line fallback"
that S42 Phase 11 was meant to retire and never did. The live scanner process
was running **pre-S46 code in memory** (never restarted since the S45
redeploy), so its in-line eval re-labelled the freshly-migrated rows with
**drift scoring** every 5 min. Observed: 213 drift-labelled records, **28 of
them NEUTRAL** (a status the S46 resolution scorer never emits) — the smoking
gun — masquerading as 54.7% "accuracy" while the one truly resolved market sat
correctly at 0/1.

**The fix (PR #2, `188f415`/`6b62276`): retire the in-line eval.** Deleted the
`evaluate_outcomes` call from `perception_node`. Evaluation now lives in ONE
place: `polysignal-truth-board.timer` → `lab/truth_board.py` (~15 min). The
scanner predicts; the truth-board evaluates. Guard test
`tests/test_no_inline_outcome_eval.py` (AST-based) fails if the call reappears
anywhere in masterloop; a third case asserts truth_board still calls it (can't
be "fixed" by deleting evaluation). Verified by re-adding the call and watching
the guard fail.

**The recovery order that mattered: scanner-on-clean-code FIRST, then migrate.**
The second deploy did: reset DGX to `6b62276` → pytest (546) → **restart scanner
on clean code** (new PID, verified one cycle wrote ZERO outcome labels) →
**then** re-migrate (wipe the 213 drift labels) → fire truth-board once → clean
read. Doing it in this order means no live process can re-poison the wiped file.
(I also briefly stopped the scanner for the wipe+rescore itself, to avoid a
`record_predictions` save-back race, then restarted it on the same clean code.)

**The clean distribution (verified, then independently re-verified by Loop).**
- evaluated rows: 51 — **0 NEUTRAL, 0 with resolution_status=null** (proof the
  instrument is purely resolution-scored).
- Per unique market (37 total): resolved_yes 3, resolved_no 1, unresolved 33.
- **Deduped honest accuracy: 3/4 = 75%** — markets 2074208, 2132799, 2132817
  (Bullish → resolved YES → CORRECT) and 566188 Man City (Bullish → resolved
  NO → INCORRECT).
- **This is NOT an edge signal. N=4.** The Wilson 95% CI on 3/4 spans roughly
  [30%, 95%] — includes a coin flip. It rose from the predicted 0/1 only
  because 3 short-horizon markets resolved YES in the ~24h between fires. The
  achievement is the *instrument*, not the number.
- Loop ran its own exec commands and reported identical numbers (HEAD,
  0 NEUTRAL, 0 null-status, 3/4, scanner PID 3107773, ORIGINAL backup present)
  → two independent confirmations agree.

**RUNBOOK FIX (the durable lesson — fold into every future deploy).** The S44/S45
pause set was a *named-unit list* (crons + 4 .path units + truth-board + gateway).
That list omitted the **scanner**, because S44/S45 didn't touch the eval path — so
nobody noticed the scanner also evaluates. S46 changed the eval path and the
omission became a data-corruption bug. **The rule going forward: the deploy pause
set must cover ANYTHING that writes `prediction_outcomes.json`, derived from what
actually writes the file — not a fixed list of names.** Today that set is: the
scanner (`record_predictions` + formerly in-line eval), the truth-board timer, and
any migration script. Before a deploy that changes the schema or scoring of a
shared state file, enumerate every writer of that file and pause/repoint all of
them. A process running stale code in memory is a writer too.

**Backups (DGX `/opt/loop/data/`):**
- `prediction_outcomes.json.pre-s46-bak.ORIGINAL-2026-05-27` — the pristine
  pre-S46 file (788 drift labels, the real "before"). DO NOT delete; it's the
  only copy of the original drift-labelled history.
- `prediction_outcomes.json.pre-s46b-recovery-2026-05-28-170602` — the
  contaminated mid-deploy state.
- `prediction_outcomes.json.pre-s46-bak` — migration's own backup (contaminated
  state).

**Loop stand-down: CLEARED.** The S46 P0 block is removed from
`lab/LOOP_TASKS.md` (replaced with a "shipped" note). Loop ACKed the one
remaining standing rule (`N30-GATE ACK`): no XGBoost retrain until N≥30 resolved
markets; `AUTO_RETRAIN_ENABLED` stays false; Bearish ban + META_GATE stay parked.
Loop's words: "gate is mine to enforce, not yours to remind me of."

**Live state at session end:** DGX on `7e6059e`. Scanner active clean (PID
3107773). All re-enabled in reverse safe order: 4 .path units → truth-board timer
→ both crons (restored from `/home/cube/crontab.bak-s46-deploy-2026-05-27-1840.txt`)
→ openclaw-gateway LAST (reachable, verified `--agent main` → GATEWAY_OK). Two
stale failed-service flags (deploy 2026-05-25, retrain 2026-04-04) reset — both
old residue, not from this window; notably retrain.service last ran in April,
confirming no retrain has happened.

**Next milestone — there is nothing to build. Just wait.** N≈4 → N≥30 resolved
markets, ~1–3 weeks of short-horizon markets resolving on their own. When N≥30:
re-run `eval/resolution_backtest.py` for the first real edge verdict (with a
Wilson CI that actually means something), THEN — and only then — open the
downstream dominoes in order: (1) Bearish ban, (2) XGBoost retrain on real
labels, (3) `META_GATE_ENABLED`. Until then the system runs honestly and
accrues data; the correct action is patience, not code.

**Closing confirmation (S46b clock-out).** The truth-board TIMER (not a manual
fire) ran unattended on its 15-min cadence — 17:26:13 and 17:41:45 CEST, both
`evaluated=0 errors=[none]`, each querying gamma (~4s) — proving `lab/truth_board.py`
is the live sole evaluator and fires on schedule with nothing to do yet (the 33
pending markets haven't resolved). The "B" proof (timer alive) is locked. The "A"
proof (an autonomously-written resolution label) happens on its own the next time
a pending market resolves — it'll be in the truth-board journal and
`prediction_outcomes.json` whenever next checked; no one needs to fire it.

> **Next session START HERE:** nothing to build. System is live and accruing toward N≥30 resolved markets (~1–3 weeks). When N≥30: re-run `eval/resolution_backtest.py` for the first real edge verdict, THEN open the dominoes in order — Bearish ban, XGBoost retrain, META_GATE. Until then: glance at the resolved count, leave the box alone.

**"A" proof CONFIRMED (2026-05-28 18:43 CEST, post-clock-out).** A *scheduled*
truth-board fire — no manual trigger — autonomously detected market `2074253`
resolved YES and wrote 6 `resolution_status=resolved_yes → CORRECT` labels
(`evaluated=6 errors=[none]`). Integrity held: 0 NEUTRAL, 0 null-status. Deduped
resolved count went 4 → 5 markets (4 CORRECT, still the lone Man City INCORRECT) =
4/5, still N=5 and meaningless as an edge signal — but the unattended evaluator is
now *proven*, not just argued. S46b is fully validated end-to-end: scanner predicts,
truth-board alone evaluates against resolution, on schedule, with no hand. Resolved
count just ticks toward N≥30 from here.

