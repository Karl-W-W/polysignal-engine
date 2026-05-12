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
