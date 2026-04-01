# Multi-Agent Systems Book → PolySignal-OS Action Items
# Source: "Designing Multi-Agent Systems" by Victor Dibia
# Created: Session 36 (2026-04-01)
# Reviewed: Cowork feedback incorporated (8.5/10 rating)
# Priority: items ordered by impact × feasibility within each tier

---

## CRITICAL (Blocks everything else) — 9/10

### C1: Fix Loop's Exec Tool — safeBinProfiles Migration
- **Book ref**: Ch 4.6 "Reliability over breadth — 10 excellent tools beat 50 mediocre"
- **Problem**: OpenClaw v2026.3.28 silently ignores raw `safeBins` entries. Needs `safeBinProfiles` or `allowlist` mode.
- **Action**: Update `/home/cube/.openclaw/openclaw.json` with proper safeBinProfiles definitions for each binary
- **Impact**: Without this, Loop fabricates all data. Nothing else works.

### C2: Replace Broad Exec with Narrow Tools
- **Book ref**: Ch 4.6, Ch 4.9 (middleware/tool poisoning), Ch 11.3.5, Ch 13.2
- **Problem**: A single "exec" tool lets Loop run ANY command. llama3.3 can't reliably format exec calls.
- **Action**: Build specific tools: `check_scanner_status`, `get_prediction_stats`, `read_trading_log`, `check_thermal`. Each validates inputs and returns structured data.
- **Sub-item**: Audit tool docstrings for information leakage (Ch 4.9 tool poisoning). Tool descriptions that are too broad can leak context or enable prompt injection even within NemoClaw's sandbox.
- **Why**: Narrow tools have constrained input schemas → llama3.3 is more likely to call them correctly. Also reduces security surface (Ch 13.2: agents WILL find and use credentials they shouldn't have).

### C3: Fix Paper Trade Evaluation Pipeline
- **Book ref**: Ch 10.1 "You cannot optimize what you cannot measure", Ch 11.3.9 "Agents aren't learning"
- **Problem**: 262 paper trades at "pending" forever. No evaluation = no learning = coin-flip accuracy.
- **Action**: Wire evaluate_outcomes() to resolve paper trades against current market prices. Run every 12th scanner cycle.
- **Impact**: Without this, feedback_loop.py and evolution_tracker.py have no data to work with.

---

## TIER 1: Fix the Learning Loop (Sessions 36-37) — 8/10

### T1.1: Orchestrator Loop Refactor (was: Phase-Structured System Prompt)
- **Book ref**: Ch 15.3 "Minimal prompts produce poor results", Ch 4.14 "PlanningHook forces planning before action", Ch 7.1 "select_next_agent, prepare_context_for_agent, check_termination"
- **Problem**: Loop narrates code instead of executing it. Prompt doesn't enforce action phases.
- **Action**: Not just a prompt rewrite — implement the three abstract orchestrator methods as actual callable functions:
  1. `select_next_agent()` — decide if this task needs local llama or Claude API
  2. `prepare_context_for_agent()` — inject relevant memory, market data, recent outcomes
  3. `check_termination()` — composable conditions (see T1.2)
- **Prompt phases** (within the orchestrator):
  1. PHASE 1: Read memory for relevant context
  2. PHASE 2: Plan approach using think tool
  3. PHASE 3: Execute using specific tools (NOT narrating)
  4. PHASE 4: Verify results by reading actual output
  5. PHASE 5: Report to user with REAL data only
- **Add rule**: "If a tool call fails, report 'TOOL FAILED: [error]'. NEVER substitute fabricated data."

### T1.2: Composable Termination Conditions
- **Book ref**: Ch 7.2 "Termination conditions must be composable"
- **Prerequisite**: T2.2 (shared conversation log) — termination conditions need to inspect conversation state to fire
- **Problem**: Loop runs until heartbeat cron kills it. No budget tracking, no completion signal.
- **Action**: Implement `TokenBudget(8000) | TaskStatus("complete") | Timeout(25min)` — whichever fires first ends the session.
- **Add to Loop's prompt**: "When all useful work is done, output HEARTBEAT_COMPLETE. Do not fill time with low-value actions."

### T1.3: Metacognitive Reflect Node
- **Book ref**: Ch 11.3.9 "Magentic-One showed 31% improvement from self-monitoring"
- **Problem**: No self-reflection on prediction quality. Accuracy declining without detection.
- **Action**: Add reflect step every 50th scanner cycle (~4 hours):
  - Pull last 50 predictions + outcomes
  - Compare accuracy trend (improving/declining/flat)
  - Check per-market performance
  - Auto-exclude markets below 30% accuracy
  - Write reflection to `lab/.reflections.jsonl`

### T1.4: Per-Category Accuracy Tracking
- **Book ref**: Ch 10.4 "Domain-specific evaluation", Ch 14.1 "Sequential pipeline for unstructured data"
- **Problem**: 50.7% aggregate hides per-category variation. May be "crypto 70% + politics 30%"
- **Action**: Tag each prediction with category (politics, sports, crypto, geopolitics). Track accuracy per category. Drop categories below 40%.

### T1.5: Prediction Provenance Trail
- **Book ref**: Ch 3.5 "Observability and Provenance", Ch 10.2 "You're evaluating trajectories, not just final answers"
- **Problem**: trading_log.json stores outcomes but not reasoning. Can't debug WHY a prediction was wrong.
- **Action**: Add `reasoning_trace` field to each prediction: what data was used, what biases applied, why this confidence level.

### T1.6: Parallel Batch Execution in MasterLoop (**NEW** — from coordination gap analysis)
- **Book ref**: Ch 2.2.3 "Parallel workflow patterns", Ch 6.3.3 "Fan-out independent tasks, fan-in results"
- **Problem**: MasterLoop processes 142 markets sequentially. Perception and prediction nodes run one market at a time on a machine with 128GB unified memory.
- **Action**: Fan-out at perception (fetch market data, whale signals, MoltBook intelligence concurrently). Fan-out at prediction (parallel market batches). Fan-in to combined PredictionSet. LangGraph supports this natively.
- **Impact**: Directly multiplies throughput without adding complexity. Scanner cycle time drops proportionally.

---

## TIER 2: Improve Agent Coordination (Sessions 37-38) — 9/10

### T2.1: Handoff Protocol Between Agents
- **Book ref**: Ch 2.3.2 "Handoff patterns enable peer-to-peer delegation with context"
- **Problem**: Claude Code → Loop → Antigravity coordination is all file-based with no context passing. Loop can't delegate infrastructure work to Antigravity.
- **Action**: Create `lab/.handoff-request.json` schema: `{target, task, context, priority, failed_approaches}`. Systemd path unit triggers receiving agent.

### T2.2: Shared Conversation Log
- **Book ref**: Ch 2.3.3 "Group chat pattern — all agents share context"
- **Problem**: Agents can't see each other's discoveries. Information silos.
- **Action**: Create `lab/.shared-log.jsonl` — all agents append structured entries: `{agent, type, content, timestamp}`. Each agent reads recent entries at session start.
- **Note**: This is a prerequisite for T1.2 (composable termination) — termination conditions inspect conversation state.

### T2.3: Step Progress Evaluation
- **Book ref**: Ch 7.5.2 "After each step, evaluate whether it actually succeeded"
- **Problem**: Loop can push code that passes tests but doesn't solve the assigned task.
- **Action**: When Loop completes a task, produce a structured StepProgressEvaluation: `{step_completed: bool, failure_reason: str, confidence_score: float, suggested_improvements: list}`. Claude Code verifies on next session.

### T2.4: Retry with Enhanced Context
- **Book ref**: Ch 7.5.3 "Don't retry blindly — build enhanced instructions from failure analysis"
- **Problem**: If Loop fails a task, it tries the same approach next heartbeat.
- **Action**: On prediction failure, use *structured* StepProgressEvaluation (from T2.3) to build enhanced retry context. The structured output (confidence_score, suggested_improvements) is what makes retry intelligent rather than repeated.
- **Example**: "Previous batch: 2/10 above threshold. StepEval suggests: exclude markets [X, Y] (accuracy <30%), focus on [A, B] (base rate bias >0.55). Retry with adjusted parameters."

### T2.5: Observability via Structured Telemetry
- **Book ref**: Ch 4.10 "OpenTelemetry for agent systems", Ch 11.1 "You cannot optimize what you cannot measure"
- **Problem**: No structured metrics. Don't know token usage per heartbeat, latency per task, which tasks take longest.
- **Action**: Add `lab/.telemetry.jsonl` — every action gets `{action, duration_ms, tokens_used, result}`. Claude Code analyzes on each session.

---

## TIER 3: Memory Architecture Restructure (Sessions 38-39) — 7/10 → revised ordering

**Implementation order corrected**: Start from cold (mechanical refactor) → warm (structured store) → hot (working memory). Building the most complex layer first is wrong.

### T3.1: Cold Archive — Mechanical Refactor of brain/memory.md (**NOW FIRST**)
- **Book ref**: Ch 4.7-4.8 "Application-managed vs agent-managed memory"
- **Problem**: 8600-line flat file. No retrieval strategy. Loop either gets everything or nothing.
- **Action**: Parse existing memory.md into `brain/archive/` directory. One file per topic or time period. Mechanical split — low risk, immediate benefit. This is the existing 8600 lines, just organized.
- **Impact**: Stops memory.md from being injected as a single blob. Archive is queryable but never auto-injected.

### T3.2: Warm Structured Store — Per-Market Memory
- **Book ref**: Ch 4.7 "get_context(market_id) retrieves relevant memories"
- **Action**: Create `brain/markets/{market_id}.md` files. Prediction node calls `get_context(market_id)` before predicting — injects ~5 items instead of 8600 lines.
- **Also**: `brain/patterns/` for cross-market discoveries. Retrieved by topic.

### T3.3: Hot Working Memory — Current Cycle State
- **Book ref**: Ch 4.7 "Application-managed memory for automatic context enhancement"
- **Action**: `brain/hot/` — current market state, recent predictions (~500 lines). Injected every heartbeat. This is the most complex layer — build last.

### T3.4: Novelty Gate on Memory Writes (**NEW** — preventive, not just curative)
- **Book ref**: Ch 4.8 "Novelty detection — surprises and contradictions are the most valuable things to remember"
- **Problem**: write_memory() stores everything. Memory grew to 8600 lines because there's no filter.
- **Action**: Score incoming memories for novelty before persisting:
  - (a) Prediction was wrong (surprise) → ALWAYS store
  - (b) New pattern discovered → ALWAYS store
  - (c) Contradicts existing memory → ALWAYS store
  - (d) Routine confirmation → SKIP
- **Target**: Growth drops from ~100 lines/day to ~10-20 lines/day.
- **Note**: This is the *preventive* fix. T3.1 (cold archive) is the *curative* fix. Both are needed.

### T3.5: Agent-Managed Memory Tool for Loop
- **Book ref**: Ch 4.8 "MemoryTool — create, view, str_replace, delete, rename"
- **Problem**: Loop can only append. Can't reorganize, archive stale memories, or build topical directories.
- **Action**: Give Loop a MemoryTool with 6 operations. Update HEARTBEAT.md: "Before predicting, check brain/markets/{market_id}.md. After resolution, update with what you got right/wrong."

### T3.6: Context Engineering for llama3.3:70b
- **Book ref**: Custom (not from book — flagged as own innovation). Inspired by Ch 4.12 general context management.
- **Problem**: 16384 context window. Context rot likely after ~10 turns.
- **Action**: Implement HeadTailCompaction: 12K budget, 20% head (system prompt + identity), 80% tail (recent tool results). Monitor for thrashing (repeated file reads).
- **Note**: The book's memory strategy (Ch 4.8) emphasizes *novelty detection* over compaction. T3.4 (novelty gate) is the book's preferred approach; this compaction is a pragmatic supplement for the small context window.

---

## TIER 4: Trust & Safety (Before Live Trading) — 9/10

### T4.1: Graduated Trust Tiers
- **Book ref**: Ch 3.4.2 "Cost-Aware Action Delegation", Ch 11.3.10, Ch 13.1 "Rule of Two"
- **Problem**: Binary TRADING_ENABLED true/false. No graduated escalation.
- **Action**: 4 tiers:
  - Tier 0 (Observe): Read markets, run predictions, write memory → auto-execute
  - Tier 1 (Paper): Paper trades, MoltBook posts → auto-execute
  - Tier 2 (Micro-live): Live trades ≤$1 → Telegram YES/NO approval
  - Tier 3 (Operational): Live trades ≤$5, model retraining → async approval (1hr timeout)
- **Promotion criteria**: Sustained performance at current tier before graduating.

### T4.2: Rule of Two Enforcement
- **Book ref**: Ch 13.1 "Agents should satisfy no more than two of: process untrusted input, access sensitive systems, change state externally"
- **Problem**: Loop processes Telegram (untrusted input) AND has exec access (sensitive systems). It MUST NOT change state autonomously.
- **Action**: All state changes (trades, config, code) require either: (a) human Telegram approval, or (b) CI auto-merge (code review by test suite).

### T4.3: Narrow Tool Definitions with Validation + Domain Scope
- **Book ref**: Ch 4.6 "Reliability over breadth", Ch 13.6 "Middleware defense-in-depth", Ch 13 "domain scope"
- **Problem**: Broad exec tool = unlimited attack surface. Even if Loop is benign, malformed calls can cause damage.
- **Action**: Each tool validates inputs (market_id must exist, trade amount must be within budget, file path must be in allowed directories). Three validation layers: input filtering, tool authorization, output validation.
- **Domain scope** (from Ch 13): Loop should *refuse* to make predictions outside Polymarket's domain, not just have approval gates. Explicit domain boundaries prevent scope creep.

### T4.4: Sycophancy Testing
- **Book ref**: Ch 13.7 "Test for sycophancy — does Loop tell KWW what it wants to hear?"
- **Action**: Send deliberately bad trade ideas to Loop via Telegram. Check if it pushes back ("this market has 30% accuracy, I don't recommend trading it") or agrees ("Yes, that looks like a great opportunity!"). A sycophantic trading agent loses money.

### T4.5: Rotate Exposed Anthropic API Key
- **Book ref**: Ch 13.8 "Ethical deployment checklist"
- **Problem**: API key was exposed in Session 33 config dump. Still not rotated.
- **Action**: Rotate key on Anthropic dashboard. Update DGX .env. Restart gateway.

---

## TIER 5: Product & Business (Sessions 40+) — 7/10 → strengthened

### T5.1: FastAPI + SSE Backend for Live Dashboard
- **Book ref**: Ch 8.1-8.2 "Two-component architecture: FastAPI + SSE"
- **Action**: Wrap scanner, prediction pipeline, and Loop activity as SSE streams from DGX. React frontend on Vercel consumes streams.
- **Why SSE not WebSockets**: Stateless, simpler, works with horizontal scaling. Agents work while users are offline.

### T5.2: MCP Server for Signal-as-a-Service
- **Book ref**: Ch 12.1-12.2 "MCP standardizes tool integration: write once, use everywhere"
- **Action**: Expose predictions as an MCP server. Other agents can discover, connect, consume signals via standard protocol. This IS the x402 revenue play.
- **MCP agentic features**: Progress notifications during prediction, elicitation for trade approval, resumable sessions.
- **Key insight** (from Ch 12): The *protocol layer* (MCP/A2A) is the product, not the UI. Your competitive advantage is a working autonomous prediction system on local hardware.

### T5.3: PolySignal-OS as Installable Agent Operating System (revised)
- **Book ref**: Epilogue "Agent marketplaces + portable agent specifications"
- **Action**: Package scanner + prediction engine + trust protocol + memory architecture as an installable system that other DGX/GPU owners can deploy. Not just a dashboard — a full operating system.
- **What you're selling**: Not predictions — the orchestration, trust, and observability layers around AI that makes it safe and controllable. Models are commoditizing; this infrastructure is not.

### T5.4: A2A Signal Federation (**NEW** — from coordination gap analysis)
- **Book ref**: Ch 12.3 "A2A enables cross-organizational agent collaboration with Agent Cards"
- **Action**: Expose prediction signals via Agent-to-Agent protocol so other agent systems can subscribe. Agent Card for discovery, standard HTTP security.
- **Why**: This is the product moat — not a dashboard, but a signal network that other autonomous systems plug into. Connects to Pioneer Status goal (Tier 6 in GOALS.md).

### T5.5: Interruptibility Controls
- **Book ref**: Ch 3.6 "Allow users to pause, resume, cancel at any point"
- **Problem**: No way to pause a specific agent or cancel a specific prediction mid-pipeline.
- **Action**: Support `/stop`, `/pause scanner`, `/resume`. Checkpoint state so operations can resume without data loss.

### T5.6: Capability Presets for New Users
- **Book ref**: Ch 3.3 "Help users understand what agents can do reliably"
- **Action**: Show customers: "Your system handles these categories well: [crypto, sports]. These need more data: [geopolitics]." Offer preset strategies: "Conservative ($1, bullish only)" vs "Moderate ($5, both directions)."

---

## META-PRINCIPLES (Apply everywhere) — 8/10 → M9 added

1. **Start simple, measure, iterate** (Ch 11.2) — Don't build complex orchestration without eval proving it helps
2. **Evaluation-driven development** (Ch 10.1) — Define success criteria BEFORE building
3. **Cheap operations before expensive ones** (Ch 14.2) — Pre-filter with rules, then LLM analyze
4. **Model-specific prompts** (Ch 11.3.4) — Prompts for llama3.3 must be MORE explicit than Claude prompts
5. **Enforce in CODE not PROMPTS** (Ch 13.3) — Trading limits, tool permissions, approval gates = middleware, not instructions
6. **Log every decision point** (Ch 13.5) — When a bad trade happens, the audit trail identifies accountability
7. **Binary decisions > confidence scores** (Ch 14.4) — Ask "HIGH or LOW confidence?" not "rate 0-100"
8. **Atomic writes** (Ch 14.5) — Write-then-rename for trading_log.json to prevent corruption on power loss
9. **A well-designed single agent often outperforms a poorly designed multi-agent system** (Ch 11.3.11) — Before adding more agents, make Loop excellent. The current three-agent setup is near-optimal; the risk is over-engineering coordination when prediction accuracy (50.7%) is the real bottleneck.

---

## SESSION 36 FOCUS (Today) — reordered per feedback

From this list, today's priorities are:
1. **C1**: Fix safeBinProfiles in OpenClaw config (exec is dead)
2. **C3**: Fix paper trade evaluation pipeline (262 pending trades)
3. **T1.1**: Rewrite Loop's orchestrator with action phases (stop narrating)
4. **T1.4**: Per-category accuracy breakdown (diagnose the 50.7% drop)

**Risk warning** (M9): Don't spend the session on coordination infrastructure (T2.*) when the prediction engine itself is at 50.7%. Fix the single-agent capability first.

Everything else depends on these four.
